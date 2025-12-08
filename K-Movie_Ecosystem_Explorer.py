import streamlit as st
import pandas as pd
import requests
from collections import defaultdict
import plotly.express as px
from operator import itemgetter
from datetime import datetime, timedelta

# ===============================================
# 1. 환경 설정 및 데이터 정의 (KOBIS API)
# ===============================================

# --- API KEY ---
# KOBIS API에서 발급받은 두 가지 키를 여기에 직접 입력합니다.
# -----------------------------------------------------------
# 1. 주간/주말 박스오피스 키 (흥행 영화 목록 가져오기)
KOBIS_BOXOFFICE_KEY = "f6ae9fdbd8ba038eda177250d3e57b4c" 

# 2. 영화 상세 정보 (DETAIL) 키: 감독/회사 정보 가져오기
KOBIS_DETAIL_KEY = "f6ae9fdbd8ba038eda177250d3e57b4c" 
# -----------------------------------------------------------


# --- API URLS ---
BOXOFFICE_URL = "http://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchWeeklyBoxOfficeList.json"
DETAIL_URL = "http://www.kobis.or.kr/kobisopenapi/webservice/rest/movie/searchMovieInfo.json"
# 일별 박스오피스 URL
DAILY_URL = "http://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchDailyBoxOfficeList.json" 

# ===============================================
# 2. 데이터 처리 및 분석 로직
# ===============================================

@st.cache_data(show_spinner="🎬 1. 주간 박스오피스 목록을 불러오는 중...")
def fetch_boxoffice_list(api_key, target_date):
    """주간 박스오피스 API에서 상위 100개 영화 목록을 가져옵니다."""
    if not api_key or len(api_key) != 32: 
        st.error("🚨 KOBIS 박스오피스 API 키가 유효하지 않습니다. 32자리 키를 확인해 주세요.")
        return None
        
    params = {
        'key': api_key, 
        'targetDt': target_date,
        'weekGb': '0', # '0': 주간(월~일)
    }
    
    try:
        response = requests.get(BOXOFFICE_URL, params=params, timeout=10)
        response.raise_for_status() 
        data = response.json()
        
        if 'faultInfo' in data:
            error_msg = data['faultInfo'].get('message', '알 수 없는 오류')
            st.error(f"❌ API 호출 오류 (1단계): 키 인증 또는 권한 문제가 의심됩니다. (원인: {error_msg})")
            return None
            
        boxoffice_list = data.get('boxOfficeResult', {}).get('weeklyBoxOfficeList', [])
        st.success(f"1단계 완료: 총 {len(boxoffice_list)}개의 흥행 영화 코드를 가져왔습니다. (기준일: {target_date})")
        return boxoffice_list
    except requests.exceptions.RequestException as e:
        st.error(f"❌ API 요청 오류 (1단계): 네트워크/연결 실패. {e}")
        return None

def fetch_movie_details(detail_key, movie_code):
    """영화 상세 정보를 가져옵니다 (관객 수, 회사, 감독)."""
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
    """target_date로 끝나는 주간의 7일간 일별 관객 데이터를 가져옵니다."""
    daily_audience = defaultdict(int)
    
    # 7일 범위 계산 (월요일부터 일요일까지)
    target_date = target_date_dt
    start_date = target_date - timedelta(days=6)
    
    current_dt = start_date
    for _ in range(7):
        date_str = current_dt.strftime("%Y%m%d")
        
        params = {
            'key': api_key,
            'targetDt': date_str,
            'itemPerPage': 1,
            'movieCd': movie_code
        }
        
        try:
            response = requests.get(DAILY_URL, params=params, timeout=5)
            data = response.json()
            
            daily_list = data.get('boxOfficeResult', {}).get('dailyBoxOfficeList', [])
            
            if daily_list:
                audience = int(daily_list[0].get('audiCnt', 0))
                daily_audience[current_dt.weekday()] = audience # 0=월, 6=일
            
        except (requests.exceptions.RequestException, ValueError):
            pass # API 호출 실패 또는 데이터 오류 시 건너뜀
            
        current_dt += timedelta(days=1)
        
    return daily_audience

@st.cache_data(show_spinner="🎬 2. 상세 정보 및 관계 데이터 수집 중...")
def get_full_analysis_data(boxoffice_key, detail_key, target_date):
    """1, 2단계 API 호출을 통합하고 분석용 데이터프레임을 생성합니다."""
    
    if not boxoffice_key or not detail_key:
        return None 
        
    boxoffice_list = fetch_boxoffice_list(boxoffice_key, target_date)
    
    if boxoffice_list is None:
        return None 

    st.markdown("---")
    st.subheader("🎬 2단계: 상세 데이터 수집 및 관계 구축 중...")
    progress_bar = st.progress(0, text="영화의 감독, 회사, 장르, 등급 정보를 수집 중입니다...")
    
    movie_records = []
    total_movies = len(boxoffice_list)
    
    # 박스오피스 기준일 (datetime 객체로 변환하여 연령 분석에 사용)
    target_date_dt = datetime.strptime(target_date, "%Y%m%d").date()
    
    for i, box_office_item in enumerate(boxoffice_list):
        movie_code = box_office_item['movieCd']
        
        detail_info = fetch_movie_details(detail_key, movie_code)
        
        # 일별 관객 데이터 가져오기 (새로운 기능)
        daily_audience_data = fetch_daily_boxoffice(boxoffice_key, movie_code, target_date_dt)
        
        rank_inten = int(box_office_item.get('rankInten', 0)) 
        
        if detail_info:
            open_dt = detail_info.get('openDt', '99991231')
            audi_cnt = int(box_office_item.get('audiAcc', '0'))
            watch_grade = detail_info.get('audits', [{}])[0].get('watchGradeNm', '등급 없음')

            record = {
                'movieNm': box_office_item.get('movieNm'),
                'audiCnt': audi_cnt,
                'openDt': open_dt,
                'watchGrade': watch_grade, 
                'targetDate': target_date_dt, 
                'rankInten': rank_inten, 
                'dailyAudience': daily_audience_data, # 일별 관객 데이터 추가
                'genres': [g['genreNm'] for g in detail_info.get('genres', [])],
            }
            
            directors = [(d['peopleNm'], record['movieNm'], audi_cnt, record['openDt']) for d in detail_info.get('directors', [])]
            record['directors'] = directors
            
            companies = []
            distributors = []
            for company in detail_info.get('companys', []):
                role = company.get('companyPartNm', '')
                if '제작' in role or '배급' in role:
                    companies.append((company.get('companyNm', '미상'), record['movieNm'], audi_cnt, role, record['openDt']))
                
                if '배급' in role:
                    distributors.append((company.get('companyNm', '미상'), record['movieNm'], audi_cnt, role, record['openDt']))

            record['companies'] = companies
            record['distributors'] = distributors
            
            movie_records.append(record)

        progress_bar.progress((i + 1) / total_movies)
        
    progress_bar.empty()
    st.success("2단계 완료: 상세 정보 및 관계 데이터 수집 완료.")
    
    return movie_records

def analyze_hitmaker_index(movie_records, entity_type='Director'):
    """감독 또는 회사의 총 관객 수 기여도를 분석합니다. (총 관객 수 기준 Top 30)"""
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
        st.error("데이터프레임 구조 오류: 분석 키('Sort_Index')를 찾을 수 없습니다.")
        return pd.DataFrame()

    df.index = df.index + 1
    df.index.name = 'Rank'
    
    df['Rank_Name'] = df.index.map(str) + ". " + df['Name']

    df['Total_Audience_Formatted'] = df['Total_Audience'].apply(lambda x: f"{x:,.0f} 명")
    
    return df

def analyze_genre_trends(movie_records):
    """장르별 주간 흥행 트렌드를 계산합니다. (총 관객 수, 점유율)."""
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
                'Movie_List': movie_display_list
            })

    if not results:
        return pd.DataFrame(), 0

    df = pd.DataFrame(results).sort_values(by='Total_Audience', ascending=False).reset_index(drop=True)
    df.index = df.index + 1
    df.index.name = 'Rank'
    
    df['Total_Audience_Formatted'] = df['Total_Audience'].apply(lambda x: f"{x:,.0f} 명")
    df['Audience_Share_Formatted'] = df['Audience_Share_Percentage'].apply(lambda x: f"{x:.1f} %")
    
    return df, total_market_audience

def analyze_rating_impact(movie_records):
    """등급별 흥행 효과를 분석합니다 (평균 관객 수, 점유율)."""
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
    
    df['Total_Audience_Formatted'] = df['Total_Audience'].apply(lambda x: f"{x:,.0f} 명")
    df['Avg_Audience_Formatted'] = df['Avg_Audience'].apply(lambda x: f"{x:,.0f} 명")
    df['Audience_Share_Formatted'] = df['Audience_Share_Percentage'].apply(lambda x: f"{x:.1f} %")
    
    return df, total_market_audience

def analyze_movie_age(movie_records, target_date):
    """영화 연령대별 흥행을 분석합니다 (신작/중기작/장기작)."""
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
    
    df['Total_Audience_Formatted'] = df['Total_Audience'].apply(lambda x: f"{x:,.0f} 명")
    df['Audience_Share_Formatted'] = df['Audience_Share_Percentage'].apply(lambda x: f"{x:.1f} %")
    
    return df, total_market_audience

def analyze_stability_rank(movie_records):
    """주간 순위 변동 폭을 기준으로 흥행 안정성을 분석합니다."""
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
    
    df['Total_Audience_Formatted'] = df['audiCnt'].apply(lambda x: f"{x:,.0f} 명")
    df['Rank_Inten_Formatted'] = df['rankInten'].apply(lambda x: f"{x:+d}")
    
    return df

def analyze_daily_trend(movie_records):
    """요일별 관객 트렌드를 분석합니다 (주말 의존도)."""
    
    # 요일 인덱스: 0=월, 6=일
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
        
        weekend_dependency = (weekend_aud / total_weekly_aud) * 100 if total_weekly_aud > 0 else 0
        
        results.append({
            'Movie_Name': movie['movieNm'],
            'Total_Weekly_Audience': total_weekly_aud,
            'Weekend_Audience': weekend_aud,
            'Weekday_Audience': weekday_aud,
            'Weekend_Dependency_Ratio': weekend_dependency, # 주말 의존도
            'Open_Date': movie['openDt']
        })

    if not results:
        return pd.DataFrame()

    df = pd.DataFrame(results).sort_values(by='Weekend_Dependency_Ratio', ascending=False).reset_index(drop=True)
    
    df.index = df.index + 1
    df.index.name = 'Rank'
    
    # 💡 그래프 Y축에 사용할 순위+이름 조합 컬럼 생성
    df['Rank_Name'] = df.index.map(str) + ". " + df['Movie_Name']
    
    # 표시용으로 포맷팅
    df['Total_Audience_Formatted'] = df['Total_Weekly_Audience'].apply(lambda x: f"{x:,.0f} 명")
    df['Weekend_Dependency_Formatted'] = df['Weekend_Dependency_Ratio'].apply(lambda x: f"{x:.1f} %")
    
    return df

# ===============================================
# 3. STREAMLIT APP 레이아웃 및 구현
# ===============================================

def main():
    """Streamlit 앱 메인 함수"""
    
    st.set_page_config(
        page_title="K-Movie 생태계 탐색기",
        layout="wide",
        initial_sidebar_state="auto"
    )

    st.title("🎬 K-Movie 생태계 탐색기 (박스오피스 분석)")
    st.markdown("---")
    
    # --- 사이드바 필터 설정 ---
    st.sidebar.header("🔍 데이터 필터 설정")
    
    # 주간 박스오피스 기준일 (최근 일요일로 설정)
    today = datetime.today()
    days_to_subtract = (today.weekday() - 6) % 7
    default_date = today - timedelta(days=days_to_subtract)
    target_date_dt = st.sidebar.date_input(
        "주간 박스오피스 기준일 (일요일):",
        value=default_date,
        max_value=today,
        help="선택한 날짜의 주간 박스오피스 상위 100개 영화를 기준으로 데이터를 가져옵니다."
    )
    target_date_str = target_date_dt.strftime("%Y%m%d")

    st.sidebar.markdown("---")
    # --- 필터 설정 끝 ---

    # 1. 데이터 로드 (캐싱된 데이터 사용)
    movie_records = get_full_analysis_data(KOBIS_BOXOFFICE_KEY, KOBIS_DETAIL_KEY, target_date_str) 
    
    if movie_records is None or not movie_records: 
        st.warning("데이터 수집에 실패했거나, 흥행 기록이 있는 영화가 수집되지 않았습니다. 기준 날짜를 변경하거나 API 키를 확인해 주세요.")
        st.stop()
        
    st.markdown("---")
    st.subheader("📊 3단계: 데이터 분석 및 시각화")

    # -----------------------------------------------
    # 3.1 탭 구조로 분석 유형 분리
    # -----------------------------------------------
    
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([ 
        "감독/회사 기여 분석", 
        "장르 트렌드 분석", 
        "등급 영향력 분석",
        "영화 연령 분석 (신작/중기작/장기작)",
        "흥행 안정성 분석 (순위 변동)",
        "요일별 트렌드 분석 (주말 의존도)" 
    ])
    
    # Tab 1: 감독/회사 흥행 분석
    with tab1:
        st.subheader("👨‍💼 감독 및 회사별 총 관객 수 기여 분석")
        
        col_select_1, col_select_2 = st.columns([1, 1])
        
        with col_select_1:
            entity_selection = st.radio(
                "분석 대상 선택:",
                ('Director', 'Company'),
                key='entity_select',
                index=0,
                format_func=lambda x: '감독' if x == 'Director' else '회사 (제작/배급)',
                help="감독 또는 회사(제작/배급)를 기준으로 흥행 지수를 분석합니다."
            )
            entity_display = '감독' if entity_selection == 'Director' else '회사'
        
        st.markdown("---")
        
        col_info_1, col_info_2 = st.columns([1, 3])
        
        with col_info_1:
            if 'initial_run' not in st.session_state:
                st.session_state['initial_run'] = True
            analyze_button = st.button(f"'{entity_display}' 흥행 분석 실행", use_container_width=True, key='analyze_tab1_btn')

        with col_info_2:
            st.info(f"""
                **분석 기준: 총 관객 수 (절대적 규모)**
                선택된 {entity_display}가 참여한 모든 영화의 **누적 관객 수 합계**를 기준으로 순위가 결정됩니다.
            """)
            
        if analyze_button or st.session_state.get('initial_run', True):
            st.session_state['initial_run'] = False 
            
            with st.spinner(f"'{entity_display}'의 총 관객수를 계산 중입니다..."):
                analysis_df = analyze_hitmaker_index(movie_records, entity_selection)
                
                if not analysis_df.empty:
                    top_n = 30 
                    top_df = analysis_df.head(top_n).copy()
                    
                    st.subheader(f"🏆 Top {top_n} {entity_display} 흥행 분석 (총 관객 수)")
                    
                    fig = px.bar(
                        top_df,
                        x='Sort_Index', 
                        y='Rank_Name', 
                        orientation='h',
                        title=f"Top {top_n} {entity_display} 총 관객 수 (기준일: {target_date_str})",
                        color='Sort_Index',
                        color_continuous_scale=px.colors.sequential.Teal,
                        hover_data={'Sort_Index': ':.0f', 'Movie_Count': True}
                    ) 
                    
                    top_df_names_in_order = top_df['Rank_Name'].tolist()
                    
                    fig.update_layout(
                        xaxis_title="총 누적 관객 수", 
                        yaxis_title=entity_display, 
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
                        'Name': '이름',
                        'Movie_Count': '총 참여 영화 수',
                        'Total_Audience_Formatted': '총 관객 수 (명)',
                    })[['이름', '총 참여 영화 수', '총 관객 수 (명)']] 
                    
                    st.dataframe(display_df, use_container_width=True, hide_index=True)
                    
                    st.markdown("---")
                    st.subheader("🎬 상세 참여 영화 목록")
                    
                    for index, row in top_df.iterrows():
                        name = row['Name']
                        movie_list = row['Movie_List'] 
                        with st.expander(f"**#{index}: {name} ({row['Movie_Count']}편)**", expanded=False):
                            st.markdown("- " + "\n- ".join(movie_list) if movie_list else "분석 기간 내 흥행 기록이 있는 참여 영화가 없습니다.")
                else:
                    st.warning(f"분석 결과가 없습니다. 기준일에 흥행 기록이 있는 영화가 부족합니다.")

    # Tab 2: 장르별 흥행 트렌드
    with tab2:
        st.subheader("📈 장르별 주간 흥행 트렌드 분석")
        st.markdown("선택된 주간 박스오피스 상위 영화를 기준으로 장르별 총 관객 수와 시장 점유율을 분석합니다.")
        
        genre_df, total_audience = analyze_genre_trends(movie_records)
        
        if not genre_df.empty:
            st.markdown(f"**총 분석 관객 수:** {total_audience:,.0f} 명")
            
            fig_pie = px.pie(
                genre_df,
                values='Total_Audience',
                names='Genre_Name',
                title='장르별 주간 관객 수 점유율',
                color_discrete_sequence=px.colors.qualitative.Pastel
            )
            fig_pie.update_traces(textinfo='percent+label', marker=dict(line=dict(color='#000000', width=1)))
            st.plotly_chart(fig_pie, use_container_width=True) 
            
            display_genre_df = genre_df.rename(columns={
                'Genre_Name': '장르',
                'Movie_Count': '총 참여 영화 수',
                'Total_Audience_Formatted': '총 관객 수 (명)',
                'Audience_Share_Formatted': '관객 점유율',
            })[['장르', '총 참여 영화 수', '총 관객 수 (명)', '관객 점유율']]
            st.dataframe(display_genre_df, use_container_width=True, hide_index=False)
            
            st.markdown("---")
            st.subheader("🎬 장르별 상세 참여 영화 목록")
            for index, row in genre_df.iterrows():
                name = row['Genre_Name']
                movie_list = row['Movie_List'] 
                with st.expander(f"**#{index}: {name} ({row['Movie_Count']}편)**", expanded=False):
                    st.markdown("- " + "\n- ".join(movie_list) if movie_list else "분석 기간 내 흥행 기록이 있는 참여 영화가 없습니다.")

        else:
            st.warning("분석할 장르 데이터가 없습니다. (KOBIS API에서 장르 정보가 누락되었거나, 흥행 영화가 없습니다.)")

    # Tab 3: 등급별 흥행 효과 분석
    with tab3:
        st.subheader("🔞 등급별 평균 흥행력 및 시장 기여도 분석")
        st.markdown("선택된 주간 박스오피스 상위 영화를 기준으로 관람 등급별 평균 관객 수를 분석합니다. (등급별 흥행 잠재력 평가)")
        
        rating_df, total_audience = analyze_rating_impact(movie_records)
        
        if not rating_df.empty:
            st.markdown(f"**총 분석 관객 수:** {total_audience:,.0f} 명")
            
            fig_bar = px.bar(
                rating_df,
                x='Avg_Audience',
                y='Rating_Name',
                orientation='h',
                title='등급별 영화 1편당 평균 관객 수',
                color='Audience_Share_Percentage',
                color_continuous_scale=px.colors.sequential.Sunset,
                hover_data={'Avg_Audience': ':.0f', 'Movie_Count': True, 'Audience_Share_Percentage': ':.1f'}
            )
            fig_bar.update_layout(
                xaxis_title="평균 관객 수", 
                yaxis_title="관람 등급", 
                yaxis={'categoryorder': 'total ascending'}, 
                xaxis={'autorange': True}, 
                height=400
            )
            st.plotly_chart(fig_bar, use_container_width=True) 
            
            display_rating_df = rating_df.rename(columns={
                'Rating_Name': '관람 등급',
                'Movie_Count': '총 참여 영화 수',
                'Total_Audience_Formatted': '총 관객 수 (명)',
                'Avg_Audience_Formatted': '평균 관객 수 (명)',
                'Audience_Share_Formatted': '관객 점유율',
            })[['관람 등급', '총 참여 영화 수', '평균 관객 수 (명)', '총 관객 수 (명)', '관객 점유율']]
            st.dataframe(display_rating_df, use_container_width=True, hide_index=False)
            
            st.markdown("---")
            st.subheader("🎬 등급별 상세 참여 영화 목록")
            for index, row in rating_df.iterrows():
                name = row['Rating_Name']
                movie_list = row['Movie_List'] 
                with st.expander(f"**#{index}: {name} ({row['Movie_Count']}편)**", expanded=False):
                    st.markdown("- " + "\n- ".join(movie_list) if movie_list else "분석 기간 내 흥행 기록이 있는 참여 영화가 없습니다.")

        else:
            st.warning("분석할 등급 데이터가 없습니다. (KOBIS API에서 등급 정보가 누락되었거나, 흥행 영화가 없습니다.)")

    # Tab 4: 영화 연령별 흥행 분석
    with tab4:
        st.subheader("📅 영화 연령별 시장 역동성 분석 (신작/중기작/장기작)")
        st.markdown("개봉일과 기준일을 비교하여 신작, 중기작, 장기 흥행작의 관객 점유율을 분석합니다. (시장 역동성 파악)")
        
        movie_age_df, total_audience = analyze_movie_age(movie_records, target_date_dt)
        
        if not movie_age_df.empty:
            st.markdown(f"**총 분석 관객 수:** {total_audience:,.0f} 명")
            
            fig_pie = px.pie(
                movie_age_df,
                values='Total_Audience',
                names='Age_Group',
                title='시장 관객 수 점유율 (영화 연령별)',
                color_discrete_sequence=px.colors.qualitative.Bold
            )
            fig_pie.update_traces(textinfo='percent+label', marker=dict(line=dict(color='#000000', width=1)))
            st.plotly_chart(fig_pie, use_container_width=True) 
            
            display_age_df = movie_age_df.rename(columns={
                'Age_Group': '영화 연령 그룹',
                'Movie_Count': '그룹 내 영화 수',
                'Total_Audience_Formatted': '총 관객 수 (명)',
                'Audience_Share_Formatted': '관객 점유율',
            })[['영화 연령 그룹', '그룹 내 영화 수', '총 관객 수 (명)', '관객 점유율']]
            st.dataframe(display_age_df, use_container_width=True, hide_index=False)
            
            st.markdown("---")
            st.subheader("🎬 연령 그룹별 상세 참여 영화 목록")
            for index, row in movie_age_df.iterrows():
                name = row['Age_Group']
                movie_list = row['Movie_List'] 
                with st.expander(f"**#{index}: {name} ({row['Movie_Count']}편)**", expanded=False):
                    st.markdown("- " + "\n- ".join(movie_list) if movie_list else "분석 기간 내 흥행 기록이 있는 참여 영화가 없습니다.")

        else:
            st.warning("분석할 연령 데이터가 없습니다. (개봉일 정보가 누락되었거나, 흥행 영화가 없습니다.)")
            
    # Tab 5: 흥행 안정성 분석 (새로 추가)
    with tab5:
        st.subheader("📉 주간 순위 변동을 통한 흥행 안정성 분석")
        st.markdown("주간 박스오피스 상위 100개 영화 중 순위 변동 폭이 가장 작은 영화(안정적인 흥행작) 순위를 분석합니다.")
        
        stability_df = analyze_stability_rank(movie_records)
        
        if not stability_df.empty:
            st.markdown(f"**기준:** 순위 변동 폭 (`abs(rankInten)`)이 낮을수록 안정적이며, 1위입니다.")
            
            display_stability_df = stability_df.rename(columns={
                'movieNm': '영화 제목',
                'Total_Audience_Formatted': '누적 관객 수',
                'Rank_Inten_Formatted': '순위 변동',
                'openDt': '개봉일',
            })[['영화 제목', '누적 관객 수', '순위 변동', '개봉일']]
            
            st.dataframe(display_stability_df, use_container_width=True, hide_index=False)
            
        else:
            st.warning("분석할 흥행 안정성 데이터가 없습니다. (순위 변동 정보가 없거나, 유효한 흥행 영화가 없습니다.)")

    # Tab 6: Daily Trend Analysis (New Feature)
    with tab6:
        st.subheader("📅 요일별 트렌드 분석: 주말 vs. 주중 의존도")
        st.markdown("주중(월~금)과 주말(토~일) 관객 비율을 분석하여 영화의 주말 의존도를 파악합니다.")
        
        daily_trend_df = analyze_daily_trend(movie_records)
        
        if not daily_trend_df.empty:
            st.markdown("**기준:** 주말 의존도 비율 (비율이 높을수록 주말 흥행 의존도가 높음)에 따라 정렬됩니다.")

            # Plotly Bar Chart: Weekend Dependency Ratio
            fig_bar = px.bar(
                daily_trend_df.head(15), 
                x='Weekend_Dependency_Ratio',
                y='Rank_Name', 
                orientation='h',
                title='주말 의존도 상위 15개 영화',
                color='Weekend_Dependency_Ratio',
                color_continuous_scale=px.colors.sequential.Viridis,
                hover_data={
                    'Weekend_Dependency_Ratio': ':.1f',
                    'Total_Weekly_Audience': ':.0f'
                }
            )

            top_daily_names_in_order = daily_trend_df['Rank_Name'].head(15).tolist()

            fig_bar.update_layout(
                xaxis_title="주말 의존도 비율 (%)", 
                yaxis_title="영화 제목", 
                yaxis={
                    'categoryorder': 'array',
                    'categoryarray': top_daily_names_in_order,
                    'autorange': 'reversed'
                },
                xaxis={'range': [0, daily_trend_df['Weekend_Dependency_Ratio'].max() * 1.1]},
                height=500
            )
            st.plotly_chart(fig_bar, use_container_width=True) 
            
            # Data Table
            display_daily_df = daily_trend_df.rename(columns={
                'Movie_Name': '영화 제목',
                'Total_Weekly_Audience': '총 주간 관객 수',
                'Weekend_Audience': '주말 관객 수 (토-일)',
                'Weekday_Audience': '주중 관객 수 (월-금)',
                'Weekend_Dependency_Formatted': '주말 의존도 (%)',
                'Open_Date': '개봉일'
            })[['영화 제목', '총 주간 관객 수', '주말 관객 수 (토-일)', '주중 관객 수 (월-금)', '주말 의존도 (%)']]
            
            st.dataframe(display_daily_df, use_container_width=True, hide_index=False)

        else:
            st.warning("분석할 일별 관객 데이터가 부족합니다. (API 문제 또는 데이터 수집 실패)")


if __name__ == "__main__":
    main()
