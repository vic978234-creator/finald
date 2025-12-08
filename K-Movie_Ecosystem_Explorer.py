import streamlit as st
import pandas as pd
import requests
from collections import defaultdict
import plotly.express as px
from operator import itemgetter
from datetime import datetime, timedelta

# ===============================================
# 1. ENVIRONMENT SETTINGS AND DATA DEFINITION (KOBIS API)
# ===============================================

# --- API KEY ---
# Two keys are directly inserted here from the user.
# -----------------------------------------------------------
# 1. Weekly/Weekend Box Office Key (Used for fetching hit movie list)
KOBIS_BOXOFFICE_KEY = "f6ae9fdbd8ba038eda177250d3e57b4c" 

# 2. Movie Detail Key (Used for fetching detailed info like directors/companies)
KOBIS_DETAIL_KEY = "f6ae9fdbd8ba038eda177250d3e57b4c" 
# -----------------------------------------------------------


# --- API URLS ---
BOXOFFICE_URL = "http://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchWeeklyBoxOfficeList.json"
DETAIL_URL = "http://www.kobis.or.kr/kobisopenapi/webservice/rest/movie/searchMovieInfo.json"
# New URL for daily box office data
DAILY_URL = "http://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchDailyBoxOfficeList.json" 

# ===============================================
# 2. DATA PROCESSING AND ANALYSIS LOGIC
# ===============================================

@st.cache_data(show_spinner="🎬 1. Fetching Weekly Box Office List...")
def fetch_boxoffice_list(api_key, target_date):
    """Fetches the list of top 100 movies from the weekly box office API."""
    if not api_key or len(api_key) != 32: 
        st.error("🚨 KOBIS Box Office API Key is invalid. Please check the 32-digit key.")
        return None
        
    params = {
        'key': api_key, 
        'targetDt': target_date,
        'weekGb': '0', # '0': Weekly (Mon~Sun)
    }
    
    try:
        response = requests.get(BOXOFFICE_URL, params=params, timeout=10)
        response.raise_for_status() 
        data = response.json()
        
        if 'faultInfo' in data:
            error_msg = data['faultInfo'].get('message', 'Unknown error')
            st.error(f"❌ API Call Error (Step 1): Key authentication or permission issue suspected. (Reason: {error_msg})")
            return None
            
        boxoffice_list = data.get('boxOfficeResult', {}).get('weeklyBoxOfficeList', [])
        st.success(f"Step 1 Complete: Fetched {len(boxoffice_list)} hit movie codes. (Reference Date: {target_date})")
        return boxoffice_list
    except requests.exceptions.RequestException as e:
        st.error(f"❌ API Request Error (Step 1): Network/Connection failure. {e}")
        return None

def fetch_movie_details(detail_key, movie_code):
    """Fetches detailed movie information (audience count, company, director)."""
    if not detail_key or len(detail_key) != 32:
        return None 
        
    params = {'key': detail_key, 'movieCd': movie_code}
    try:
        response = requests.get(DETAIL_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if 'faultInfo' in data:
             return None
             
        return data.get('movieInfoResult', {}).get('movieInfo', {})
    except requests.exceptions.RequestException:
        return None

def fetch_daily_boxoffice(api_key, movie_code, target_date_dt):
    """Fetches daily audience data for a movie over the last 7 days ending at target_date."""
    daily_audience = defaultdict(int)
    
    # Calculate the 7-day range (Mon to Sun) ending at the target date
    target_date = target_date_dt
    start_date = target_date - timedelta(days=6)
    
    # KOBIS weekly uses Mon-Sun, so we need to iterate 7 days.
    
    current_dt = start_date
    for _ in range(7):
        date_str = current_dt.strftime("%Y%m%d")
        
        params = {
            'key': api_key,
            'targetDt': date_str,
            'itemPerPage': 1,
            'movieCd': movie_code # Search specifically for the movie code
        }
        
        try:
            response = requests.get(DAILY_URL, params=params, timeout=5)
            data = response.json()
            
            daily_list = data.get('boxOfficeResult', {}).get('dailyBoxOfficeList', [])
            
            if daily_list:
                audience = int(daily_list[0].get('audiCnt', 0))
                daily_audience[current_dt.weekday()] = audience # 0=Mon, 6=Sun
            
        except (requests.exceptions.RequestException, ValueError):
            pass # Skip if API call fails or data is malformed
            
        current_dt += timedelta(days=1)
        
    return daily_audience

@st.cache_data(show_spinner="🎬 2. Collecting Detailed Information and Relationship Data...")
def get_full_analysis_data(boxoffice_key, detail_key, target_date):
    """Integrates 1st and 2nd stage API calls and creates DataFrame for analysis."""
    
    if not boxoffice_key or not detail_key:
        return None 
        
    boxoffice_list = fetch_boxoffice_list(boxoffice_key, target_date)
    
    if boxoffice_list is None:
        return None 

    st.markdown("---")
    st.subheader("🎬 Step 2: Collecting Detailed Data and Relationships...")
    progress_bar = st.progress(0, text="Collecting director, company, genre, and rating data for each movie...")
    
    movie_records = []
    total_movies = len(boxoffice_list)
    
    target_date_dt = datetime.strptime(target_date, "%Y%m%d").date()
    
    for i, box_office_item in enumerate(boxoffice_list):
        movie_code = box_office_item['movieCd']
        
        detail_info = fetch_movie_details(detail_key, movie_code)
        
        # 💡 Fetch daily audience data (new functionality)
        daily_audience_data = fetch_daily_boxoffice(boxoffice_key, movie_code, target_date_dt)
        
        rank_inten = int(box_office_item.get('rankInten', 0)) 
        
        if detail_info:
            open_dt = detail_info.get('openDt', '99991231')
            audi_cnt = int(box_office_item.get('audiAcc', '0'))
            watch_grade = detail_info.get('audits', [{}])[0].get('watchGradeNm', 'Not Rated')

            record = {
                'movieNm': box_office_item.get('movieNm'),
                'audiCnt': audi_cnt,
                'openDt': open_dt,
                'watchGrade': watch_grade, 
                'targetDate': target_date_dt, 
                'rankInten': rank_inten, 
                'dailyAudience': daily_audience_data, # Daily audience data added
                'genres': [g['genreNm'] for g in detail_info.get('genres', [])],
            }
            
            directors = [(d['peopleNm'], record['movieNm'], audi_cnt, record['openDt']) for d in detail_info.get('directors', [])]
            record['directors'] = directors
            
            companies = []
            distributors = []
            for company in detail_info.get('companys', []):
                role = company.get('companyPartNm', '')
                if 'Producer' in role or 'Distributor' in role or '제작' in role or '배급' in role:
                    companies.append((company.get('companyNm', 'Unknown'), record['movieNm'], audi_cnt, role, record['openDt']))
                
                if 'Distributor' in role or '배급' in role:
                    distributors.append((company.get('companyNm', 'Unknown'), record['movieNm'], audi_cnt, role, record['openDt']))

            record['companies'] = companies
            record['distributors'] = distributors
            
            movie_records.append(record)

        progress_bar.progress((i + 1) / total_movies)
        
    progress_bar.empty()
    st.success("Step 2 Complete: Detailed information and relationship data collection complete.")
    
    return movie_records

def analyze_hitmaker_index(movie_records, entity_type='Director'):
    """Analyzes Total Audience Contribution by Director or Company (Top 30)."""
    entity_data = defaultdict(lambda: {
        'total_audience': 0, 
        'movie_count': 0, 
        'movie_list': []
    })
    
    for movie in movie_records:
        entities = movie.get('directors') if entity_type == 'Director' else movie.get('companies')
        if not entities:
            continue

        for entity_tuple in entities:
            entity_name = entity_tuple[0]
            audience = entity_tuple[2]
            movie_name = entity_tuple[1]
            open_dt = entity_tuple[3] if entity_type == 'Director' else entity_tuple[4]
            
            entity_data[entity_name]['movie_count'] += 1
            
            if audience > 0:
                entity_data[entity_name]['total_audience'] += audience
                
                entity_data[entity_name]['movie_list'].append({
                    'name': movie_name,
                    'open_dt': open_dt
                })
                
    results = []
    for name, data in entity_data.items():
        total_aud = data['total_audience']
        movie_cnt = data['movie_count']
        
        if total_aud > 0:
            sort_index = total_aud 
            
            sorted_movies = sorted(data['movie_list'], key=lambda x: x['open_dt'], reverse=True)
            movie_display_list = [f"{m['name']} ({m['open_dt'][:4]})" for m in sorted_movies]
            
            results.append({
                'Name': name,
                'Type': entity_type,
                'Movie_Count': movie_cnt,
                'Total_Audience': int(total_aud),
                'Sort_Index': sort_index,
                'Movie_List': movie_display_list 
            })

    if not results:
        return pd.DataFrame() 

    try:
        df = pd.DataFrame(results).sort_values(by='Sort_Index', ascending=False).reset_index(drop=True)
    except KeyError:
        st.error("DataFrame Structure Error: Analysis key ('Sort_Index') not found.")
        return pd.DataFrame()

    df.index = df.index + 1
    df.index.name = 'Rank'
    
    df['Rank_Name'] = df.index.map(str) + ". " + df['Name']

    df['Total_Audience_Formatted'] = df['Total_Audience'].apply(lambda x: f"{x:,.0f} people")
    
    return df

def analyze_genre_trends(movie_records):
    """Calculates weekly box office trends by genre (Total Audience, Share)."""
    genre_data = defaultdict(lambda: {'total_audience': 0, 'movie_count': 0, 'movie_list': []})
    total_market_audience = sum(movie['audiCnt'] for movie in movie_records)
    
    for movie in movie_records:
        audience = movie['audiCnt']
        genres = movie.get('genres')
        
        if not genres:
            continue

        for genre_name in genres:
            genre_data[genre_name]['total_audience'] += audience
            genre_data[genre_name]['movie_count'] += 1
            
            if audience > 0:
                genre_data[genre_name]['movie_list'].append({
                    'name': movie['movieNm'],
                    'open_dt': movie['openDt']
                })
            
    results = []
    for name, data in genre_data.items():
        if data['total_audience'] > 0:
            share = (data['total_audience'] / total_market_audience) * 100 if total_market_audience > 0 else 0
            
            sorted_movies = sorted(data['movie_list'], key=lambda x: x['open_dt'], reverse=True)
            movie_display_list = [f"{m['name']} ({m['open_dt'][:4]})" for m in sorted_movies]
            
            results.append({
                'Genre_Name': name,
                'Total_Audience': int(data['total_audience']),
                'Movie_Count': data['movie_count'],
                'Audience_Share_Percentage': share,
                'Movie_List': movie_display_list # Movie list added
            })

    if not results:
        return pd.DataFrame(), 0

    df = pd.DataFrame(results).sort_values(by='Total_Audience', ascending=False).reset_index(drop=True)
    df.index = df.index + 1
    df.index.name = 'Rank'
    
    df['Total_Audience_Formatted'] = df['Total_Audience'].apply(lambda x: f"{x:,.0f} people")
    df['Audience_Share_Formatted'] = df['Audience_Share_Percentage'].apply(lambda x: f"{x:.1f} %")
    
    return df, total_market_audience

def analyze_rating_impact(movie_records):
    """Calculates the box office impact by age rating (Avg. Audience, Share)."""
    rating_data = defaultdict(lambda: {'total_audience': 0, 'movie_count': 0, 'movie_list': []})
    total_market_audience = sum(movie['audiCnt'] for movie in movie_records)
    
    for movie in movie_records:
        audience = movie['audiCnt']
        rating = movie.get('watchGrade')
        
        if not rating or audience <= 0:
            continue

        rating_data[rating]['total_audience'] += audience
        rating_data[rating]['movie_count'] += 1
        
        rating_data[rating]['movie_list'].append({
            'name': movie['movieNm'],
            'open_dt': movie['openDt']
        })
            
    results = []
    for name, data in rating_data.items():
        if data['movie_count'] > 0:
            avg_audience = data['total_audience'] / data['movie_count']
            share = (data['total_audience'] / total_market_audience) * 100 if total_market_audience > 0 else 0
            
            sorted_movies = sorted(data['movie_list'], key=lambda x: x['open_dt'], reverse=True)
            movie_display_list = [f"{m['name']} ({m['open_dt'][:4]})" for m in sorted_movies]
            
            results.append({
                'Rating_Name': name,
                'Total_Audience': int(data['total_audience']),
                'Movie_Count': data['movie_count'],
                'Avg_Audience': int(avg_audience),
                'Audience_Share_Percentage': share,
                'Movie_List': movie_display_list
            })

    if not results:
        return pd.DataFrame(), 0

    df = pd.DataFrame(results).sort_values(by='Avg_Audience', ascending=False).reset_index(drop=True)
    df.index = df.index + 1
    df.index.name = 'Rank'
    
    df['Total_Audience_Formatted'] = df['Total_Audience'].apply(lambda x: f"{x:,.0f} people")
    df['Avg_Audience_Formatted'] = df['Avg_Audience'].apply(lambda x: f"{x:,.0f} people")
    df['Audience_Share_Formatted'] = df['Audience_Share_Percentage'].apply(lambda x: f"{x:.1f} %")
    
    return df, total_market_audience

def analyze_movie_age(movie_records, target_date):
    """Analyzes box office performance by movie age (New, Mid-Term, Veteran)."""
    age_data = defaultdict(lambda: {'total_audience': 0, 'movie_count': 0, 'movie_list': []})
    total_market_audience = sum(movie['audiCnt'] for movie in movie_records)
    
    for movie in movie_records:
        audience = movie['audiCnt']
        open_dt_str = movie.get('openDt')
        
        if audience <= 0 or not open_dt_str or open_dt_str == '99991231':
            continue

        try:
            open_date = datetime.strptime(open_dt_str, "%Y%m%d").date()
            days_since_open = (target_date - open_date).days
        except ValueError:
            continue

        if days_since_open <= 7:
            age_group = "신작 (New Release)"
        elif days_since_open <= 28:
            age_group = "중기작 (Mid-Term)"
        else:
            age_group = "장기작 (Veteran)"
            
        age_data[age_group]['total_audience'] += audience
        age_data[age_group]['movie_count'] += 1
        
        age_data[age_group]['movie_list'].append({
            'name': movie['movieNm'],
            'open_dt': movie['openDt']
        })
            
    results = []
    for name, data in age_data.items():
        if data['total_audience'] > 0:
            share = (data['total_audience'] / total_market_audience) * 100 if total_market_audience > 0 else 0
            
            sorted_movies = sorted(data['movie_list'], key=lambda x: x['open_dt'], reverse=True)
            movie_display_list = [f"{m['name']} ({m['open_dt'][:4]})" for m in sorted_movies]
            
            results.append({
                'Age_Group': name,
                'Total_Audience': int(data['total_audience']),
                'Movie_Count': data['movie_count'],
                'Audience_Share_Percentage': share,
                'Movie_List': movie_display_list
            })

    if not results:
        return pd.DataFrame(), 0

    df = pd.DataFrame(results).sort_values(by='Total_Audience', ascending=False).reset_index(drop=True)
    df.index = df.index + 1
    df.index.name = 'Rank'
    
    df['Total_Audience_Formatted'] = df['Total_Audience'].apply(lambda x: f"{x:,.0f} people")
    df['Audience_Share_Formatted'] = df['Audience_Share_Percentage'].apply(lambda x: f"{x:.1f} %")
    
    return df, total_market_audience

def analyze_stability_rank(movie_records):
    """Analyzes ranking stability based on the absolute change in rank (rankInten)."""
    stability_data = [
        {
            'movieNm': movie['movieNm'],
            'audiCnt': movie['audiCnt'],
            'rankInten': movie['rankInten'],
            'absRankInten': abs(movie['rankInten']), 
            'openDt': movie['openDt']
        }
        for movie in movie_records if abs(movie['rankInten']) != 9999 
    ]

    if not stability_data:
        return pd.DataFrame()

    df = pd.DataFrame(stability_data).sort_values(
        by='absRankInten', 
        ascending=True 
    ).reset_index(drop=True)
    
    df.index = df.index + 1
    df.index.name = 'Rank'
    
    df['Total_Audience_Formatted'] = df['audiCnt'].apply(lambda x: f"{x:,.0f} people")
    df['Rank_Inten_Formatted'] = df['rankInten'].apply(lambda x: f"{x:+d}")
    
    return df

def analyze_daily_trend(movie_records):
    """Analyzes weekly audience split: Weekday (Mon-Fri) vs. Weekend (Sat-Sun)."""
    
    # Day indices: 0=Mon, 1=Tue, 2=Wed, 3=Thu, 4=Fri, 5=Sat, 6=Sun
    weekday_indices = [0, 1, 2, 3, 4]
    weekend_indices = [5, 6]
    
    results = []
    
    for movie in movie_records:
        daily_aud = movie.get('dailyAudience', {})
        total_weekly_aud = movie['audiCnt']
        
        if not daily_aud or total_weekly_aud == 0:
            continue
            
        weekday_aud = sum(daily_aud[i] for i in weekday_indices)
        weekend_aud = sum(daily_aud[i] for i in weekend_indices)
        
        # Calculate dependency and efficiency
        weekend_dependency = (weekend_aud / total_weekly_aud) * 100 if total_weekly_aud > 0 else 0
        
        # We calculate the relative strength of weekdays vs. weekends
        # If Weekend Dependency is low, Weekday Efficiency is considered high.
        
        results.append({
            'Movie_Name': movie['movieNm'],
            'Total_Weekly_Audience': total_weekly_aud,
            'Weekend_Audience': weekend_aud,
            'Weekday_Audience': weekday_aud,
            'Weekend_Dependency_Ratio': weekend_dependency, # High ratio means high weekend reliance
            'Open_Date': movie['openDt']
        })

    if not results:
        return pd.DataFrame()

    df = pd.DataFrame(results).sort_values(by='Weekend_Dependency_Ratio', ascending=False).reset_index(drop=True)
    df.index = df.index + 1
    df.index.name = 'Rank'
    
    # Format columns for display
    df['Total_Audience_Formatted'] = df['Total_Weekly_Audience'].apply(lambda x: f"{x:,.0f} people")
    df['Weekend_Dependency_Formatted'] = df['Weekend_Dependency_Ratio'].apply(lambda x: f"{x:.1f} %")
    
    return df

# ===============================================
# 3. STREAMLIT APP LAYOUT AND IMPLEMENTATION
# ===============================================

def main():
    """Streamlit App Main Function"""
    
    st.set_page_config(
        page_title="K-Movie Ecosystem Explorer",
        layout="wide",
        initial_sidebar_state="auto"
    )

    st.title("🎬 K-Movie Ecosystem Explorer (Box Office Analysis)")
    st.markdown("---")
    
    # --- Sidebar Filter Settings ---
    st.sidebar.header("🔍 Data Filter Settings")
    
    # Weekly Box Office Reference Date (Setting to the most recent Sunday)
    today = datetime.today()
    days_to_subtract = (today.weekday() - 6) % 7
    default_date = today - timedelta(days=days_to_subtract)
    target_date_dt = st.sidebar.date_input(
        "Weekly Box Office Reference Date (Sunday):",
        value=default_date,
        max_value=today,
        help="Data is collected based on the top 100 movies from the weekly box office ending on this date."
    )
    target_date_str = target_date_dt.strftime("%Y%m%d")

    st.sidebar.markdown("---")
    # --- Filter Settings End ---

    # 1. Data Load (Cashed Data Used)
    movie_records = get_full_analysis_data(KOBIS_BOXOFFICE_KEY, KOBIS_DETAIL_KEY, target_date_str) 
    
    if movie_records is None or not movie_records: 
        st.warning("Data collection failed, or no valid box office records were collected. Please check the reference date or API keys.")
        st.stop()
        
    st.markdown("---")
    st.subheader("📊 Step 3: Data Analysis and Visualization")

    # -----------------------------------------------
    # 3.1 Tab Structure for Analysis Types (6 Tabs)
    # -----------------------------------------------
    
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([ 
        "Director/Company Contribution", 
        "Genre Trend Analysis", 
        "Rating Impact",
        "Movie Age Analysis (New/Mid/Veteran)",
        "Stability Analysis (Rank Change)",
        "Daily Trend Analysis (Weekend Reliance)" # New Tab
    ])
    
    # Tab 1: Director/Company Contribution
    with tab1:
        st.subheader("👨‍💼 Director and Company Total Audience Contribution Analysis")
        
        col_select_1, col_select_2 = st.columns([1, 1])
        
        with col_select_1:
            entity_selection = st.radio(
                "Select Entity for Analysis:",
                ('Director', 'Company'),
                key='entity_select',
                index=0,
                help="Analyzes box office index based on Director or Company (Production/Distribution)."
            )
        
        st.markdown("---")
        
        col_info_1, col_info_2 = st.columns([1, 3])
        
        with col_info_1:
            if 'initial_run' not in st.session_state:
                st.session_state['initial_run'] = True
            analyze_button = st.button(f"Analyze '{entity_selection}' Box Office", use_container_width=True, key='analyze_tab1_btn')

        with col_info_2:
            st.info(f"""
                **Analysis Criterion: Total Audience (Absolute Volume)**
                The ranking is determined by the **sum of cumulative audience count** for all movies the selected {entity_selection} participated in.
            """)
            
        if analyze_button or st.session_state.get('initial_run', True):
            st.session_state['initial_run'] = False 
            
            with st.spinner(f"Calculating '{entity_selection}' total audience contribution..."):
                analysis_df = analyze_hitmaker_index(movie_records, entity_selection)
                
                if not analysis_df.empty:
                    top_n = 30 
                    top_df = analysis_df.head(top_n).copy()
                    
                    st.subheader(f"🏆 Top {top_n} {entity_selection} Box Office Analysis (Total Audience)")
                    
                    fig = px.bar(
                        top_df,
                        x='Sort_Index', 
                        y='Rank_Name', 
                        orientation='h',
                        title=f"Top {top_n} {entity_selection} Total Audience Count (Reference Date: {target_date_str})",
                        color='Sort_Index',
                        color_continuous_scale=px.colors.sequential.Teal,
                        hover_data={'Sort_Index': ':.0f', 'Movie_Count': True}
                    ) 
                    
                    top_df_names_in_order = top_df['Rank_Name'].tolist()
                    
                    fig.update_layout(
                        xaxis_title="Total Cumulative Audience", 
                        yaxis_title=entity_selection, 
                        yaxis={
                            'categoryorder': 'array',
                            'categoryarray': top_df_names_in_order, 
                            'autorange': 'reversed' 
                        }, 
                        xaxis={
                             'range': [0, top_df['Sort_Index'].max() * 1.1] 
                        },
                        height=max(500, top_n * 30)
                    )
                    st.plotly_chart(fig, use_container_width=True) 

                    display_df = top_df.rename(columns={
                        'Name': 'Name',
                        'Movie_Count': 'Total Movies Participated',
                        'Total_Audience_Formatted': 'Total Audience (people)',
                    })[['Name', 'Total Movies Participated', 'Total Audience (people)']] 
                    
                    st.dataframe(display_df, use_container_width=True, hide_index=True)
                    
                    st.markdown("---")
                    st.subheader("🎬 Detailed List of Participated Movies")
                    
                    for index, row in top_df.iterrows():
                        name = row['Name']
                        movie_list = row['Movie_List'] 
                        with st.expander(f"**#{index}: {name} ({row['Movie_Count']} movies)**", expanded=False):
                            st.markdown("- " + "\n- ".join(movie_list) if movie_list else "No box office record movies found in the analysis period.")
                else:
                    st.warning(f"No analysis results. Check if there are enough movies with box office records for the period.")

    # Tab 2: Genre Trend Analysis
    with tab2:
        st.subheader("📈 Genre Weekly Box Office Trend Analysis")
        st.markdown("Analyzes total audience and market share by genre based on the top weekly box office movies.")
        
        genre_df, total_audience = analyze_genre_trends(movie_records)
        
        if not genre_df.empty:
            st.markdown(f"**Total Audience Analyzed:** {total_audience:,.0f} people")
            
            fig_pie = px.pie(
                genre_df,
                values='Total_Audience',
                names='Genre_Name',
                title='Weekly Audience Share by Genre',
                color_discrete_sequence=px.colors.qualitative.Pastel
            )
            fig_pie.update_traces(textinfo='percent+label', marker=dict(line=dict(color='#000000', width=1)))
            st.plotly_chart(fig_pie, use_container_width=True) 
            
            display_genre_df = genre_df.rename(columns={
                'Genre_Name': 'Genre',
                'Movie_Count': 'Total Movies',
                'Total_Audience_Formatted': 'Total Audience (people)',
                'Audience_Share_Formatted': 'Audience Share',
            })[['Genre', 'Total Movies', 'Total Audience (people)', 'Audience Share']]
            st.dataframe(display_genre_df, use_container_width=True, hide_index=False)
            
            st.markdown("---")
            st.subheader("🎬 Detailed List of Movies per Genre")
            for index, row in genre_df.iterrows():
                name = row['Genre_Name']
                movie_list = row['Movie_List'] 
                with st.expander(f"**#{index}: {name} ({row['Movie_Count']} movies)**", expanded=False):
                    st.markdown("- " + "\n- ".join(movie_list) if movie_list else "No box office record movies found in this genre.")

        else:
            st.warning("No genre data for analysis.")

    # Tab 3: Rating Impact Analysis
    with tab3:
        st.subheader("🔞 Box Office Impact Analysis by Age Rating")
        st.markdown("Analyzes the average audience count by age rating among the top weekly box office movies (Evaluating rating potential).")
        
        rating_df, total_audience = analyze_rating_impact(movie_records)
        
        if not rating_df.empty:
            st.markdown(f"**Total Audience Analyzed:** {total_audience:,.0f} people")
            
            fig_bar = px.bar(
                rating_df,
                x='Avg_Audience',
                y='Rating_Name',
                orientation='h',
                title='Average Audience Count per Movie by Rating',
                color='Audience_Share_Percentage',
                color_continuous_scale=px.colors.sequential.Sunset,
                hover_data={'Avg_Audience': ':.0f', 'Movie_Count': True, 'Audience_Share_Percentage': ':.1f'}
            )
            fig_bar.update_layout(
                xaxis_title="Average Audience Count", 
                yaxis_title="Age Rating", 
                yaxis={'categoryorder': 'total ascending'}, 
                xaxis={'autorange': True}, 
                height=400
            )
            st.plotly_chart(fig_bar, use_container_width=True) 
            
            display_rating_df = rating_df.rename(columns={
                'Rating_Name': 'Age Rating',
                'Movie_Count': 'Total Movies',
                'Total_Audience_Formatted': 'Total Audience (people)',
                'Avg_Audience_Formatted': 'Average Audience (people)',
                'Audience_Share_Formatted': 'Audience Share',
            })[['Age Rating', 'Total Movies', 'Average Audience (people)', 'Total Audience (people)', 'Audience Share']]
            st.dataframe(display_rating_df, use_container_width=True, hide_index=False)
            
            st.markdown("---")
            st.subheader("🎬 Detailed List of Movies per Rating")
            for index, row in rating_df.iterrows():
                name = row['Rating_Name']
                movie_list = row['Movie_List'] 
                with st.expander(f"**#{index}: {name} ({row['Movie_Count']} movies)**", expanded=False):
                    st.markdown("- " + "\n- ".join(movie_list) if movie_list else "No box office record movies found in this rating.")

        else:
            st.warning("No rating data for analysis.")

    # Tab 4: Movie Age Analysis
    with tab4:
        st.subheader("📅 Movie Age Market Dynamics Analysis (New/Mid-Term/Veteran)")
        st.markdown("Analyzes the audience share of New Release, Mid-Term, and Veteran movies by comparing the opening date and reference date.")
        
        movie_age_df, total_audience = analyze_movie_age(movie_records, target_date_dt)
        
        if not movie_age_df.empty:
            st.markdown(f"**Total Audience Analyzed:** {total_audience:,.0f} people")
            
            fig_pie = px.pie(
                movie_age_df,
                values='Total_Audience',
                names='Age_Group',
                title='Market Audience Share by Movie Age',
                color_discrete_sequence=px.colors.qualitative.Bold
            )
            fig_pie.update_traces(textinfo='percent+label', marker=dict(line=dict(color='#000000', width=1)))
            st.plotly_chart(fig_pie, use_container_width=True) 
            
            display_age_df = movie_age_df.rename(columns={
                'Age_Group': 'Movie Age Group',
                'Movie_Count': 'Total Movies in Group',
                'Total_Audience_Formatted': 'Total Audience (people)',
                'Audience_Share_Formatted': 'Audience Share',
            })[['Movie Age Group', 'Total Movies in Group', 'Total Audience (people)', 'Audience Share']]
            st.dataframe(display_age_df, use_container_width=True, hide_index=False)
            
            st.markdown("---")
            st.subheader("🎬 Detailed List of Movies per Age Group")
            for index, row in movie_age_df.iterrows():
                name = row['Age_Group']
                movie_list = row['Movie_List'] 
                with st.expander(f"**#{index}: {name} ({row['Movie_Count']} movies)**", expanded=False):
                    st.markdown("- " + "\n- ".join(movie_list) if movie_list else "No box office record movies found in this age group.")

        else:
            st.warning("No movie age data for analysis.")
            
    # Tab 5: Stability Analysis (Rank Change)
    with tab5:
        st.subheader("📉 Stability Analysis via Weekly Rank Change")
        st.markdown("Analyzes the rank of the most stable hit movies among the top 100 based on the absolute change in weekly rank.")
        
        stability_df = analyze_stability_rank(movie_records)
        
        if not stability_df.empty:
            st.markdown(f"**Criterion:** Lower absolute rank change (`abs(rankInten)`) means higher stability, ranking #1.")
            
            display_stability_df = stability_df.rename(columns={
                'movieNm': 'Movie Title',
                'Total_Audience_Formatted': 'Cumulative Audience',
                'Rank_Inten_Formatted': 'Rank Change',
                'openDt': 'Open Date',
            })[['Movie Title', 'Cumulative Audience', 'Rank Change', 'Open Date']]
            
            st.dataframe(display_stability_df, use_container_width=True, hide_index=False)
            
        else:
            st.warning("No stability data for analysis. (Rank change information is missing or no valid hit movies were found.)")

    # Tab 6: Daily Trend Analysis (New Feature)
    with tab6:
        st.subheader("📅 Daily Trend Analysis: Weekend vs. Weekday Reliance")
        st.markdown("Analyzes the audience split between weekdays (Mon-Fri) and weekends (Sat-Sun) to determine the movie's reliance on weekend traffic.")
        
        daily_trend_df = analyze_daily_trend(movie_records)
        
        if not daily_trend_df.empty:
            st.markdown("**Criterion:** Sorted by Weekend Dependency Ratio (Highest ratio = highest weekend reliance).")

            # Plotly Bar Chart: Weekend Dependency Ratio
            fig_bar = px.bar(
                daily_trend_df.head(15), # Show Top 15 movies by weekend dependency
                x='Weekend_Dependency_Ratio',
                y='Movie_Name',
                orientation='h',
                title='Top 15 Movies by Weekend Dependency Ratio',
                color='Weekend_Dependency_Ratio',
                color_continuous_scale=px.colors.sequential.Viridis,
                hover_data={'Total_Weekly_Audience': ':.0f', 'Weekend_Dependency_Ratio': ':.1f'}
            )
            
            fig_bar.update_layout(
                xaxis_title="Weekend Dependency Ratio (%)", 
                yaxis_title="Movie Title", 
                yaxis={'categoryorder': 'total ascending'},
                height=500
            )
            st.plotly_chart(fig_bar, use_container_width=True) 
            
            # Data Table
            display_daily_df = daily_trend_df.rename(columns={
                'Movie_Name': 'Movie Title',
                'Total_Weekly_Audience': 'Total Weekly Audience',
                'Weekend_Audience': 'Weekend Audience (Sat-Sun)',
                'Weekday_Audience': 'Weekday Audience (Mon-Fri)',
                'Weekend_Dependency_Formatted': 'Weekend Dependency (%)',
                'Open_Date': 'Open Date'
            })[['Movie Title', 'Total Weekly Audience', 'Weekend Audience (Sat-Sun)', 'Weekday Audience (Mon-Fri)', 'Weekend Dependency (%)']]
            
            st.dataframe(display_daily_df, use_container_width=True, hide_index=False)

        else:
            st.warning("No daily audience data found for analysis. This may indicate a temporary issue with the API or data collection.")


if __name__ == "__main__":
    main()
