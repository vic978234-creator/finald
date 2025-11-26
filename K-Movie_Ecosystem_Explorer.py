import streamlit as st
import pandas as pd
import requests
from collections import defaultdict
import plotly.express as px
from operator import itemgetter
from datetime import datetime, timedelta

# ===============================================
# 1. 환경 설정 및 데이터 정의 (KOBIS API 사용)
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
# 1. 주간/주말 박스오피스 API로 변경 (흥행 영화 목록 확보 목적)
BOXOFFICE_URL = "http://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchWeeklyBoxOfficeList.json"
# 2. 영화 상세 정보 API는 그대로 유지
DETAIL_URL = "http://www.kobis.or.kr/kobisopenapi/webservice/rest/movie/searchMovieInfo.json"

# ===============================================
# 2. 데이터 처리 및 분석 로직
# ===============================================

@st.cache_data(show_spinner="🎬 1단계: 주간 박스오피스 목록을 불러오는 중...")
def fetch_boxoffice_list(api_key, target_date):
    """
    KOBIS 주간 박스오피스 API를 호출하여 흥행 영화 목록을 가져옵니다.
    :param target_date: 주간 박스오피스 기준일 (YYYYMMDD 형식)
    """
    if not api_key or len(api_key) != 32: 
        st.error("🚨 KOBIS BOXOFFICE API 키가 유효하지 않습니다. 32자리 키를 확인해 주세요.")
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
            st.error(f"❌ 1단계 API 호출 오류: 키 인증 실패 또는 권한 오류가 의심됩니다. (원인: {error_msg})")
            return None
            
        boxoffice_list = data.get('boxOfficeResult', {}).get('weeklyBoxOfficeList', [])
        st.success(f"1단계 완료: 총 {len(boxoffice_list)}개의 흥행 영화 코드를 가져왔습니다. (기준일: {target_date})")
        return boxoffice_list
    except requests.exceptions.RequestException as e:
        st.error(f"❌ 1단계 API 요청 중 네트워크/연결 오류 발생: {e}")
        return None

def fetch_movie_details(detail_key, movie_code):
    """영화 상세 정보(관객수, 회사, 감독)를 가져옵니다."""
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

@st.cache_data(show_spinner="🎬 2단계: 상세 정보 및 관계 데이터 수집 중...")
def get_full_analysis_data(boxoffice_key, detail_key, target_date):
    """
    1, 2단계 API 호출을 통합하고 데이터 분석을 위한 DataFrame을 생성합니다.
    (최소 개봉 연도 필터링 로직 제거 - 연도 필터링은 이제 사용하지 않음)
    """
    
    if not boxoffice_key or not detail_key:
        return None 
        
    # 1단계: 흥행 영화 목록 가져오기 (BOXOFFICE_KEY 사용)
    boxoffice_list = fetch_boxoffice_list(boxoffice_key, target_date)
    
    if boxoffice_list is None:
        return None 

    st.markdown("---")
    st.subheader("🎬 2단계: 상세 정보 및 관계 데이터 수집 중...")
    progress_bar = st.progress(0, text="각 영화의 감독, 회사, 장르, 등급 정보를 수집 중입니다...")
    
    movie_records = []
    total_movies = len(boxoffice_list)
    
    # 박스오피스 기준일 (datetime 객체로 변환하여 연령 분석에 사용)
    target_date_dt = datetime.strptime(target_date, "%Y%m%d").date()
    
    for i, box_office_item in enumerate(boxoffice_list):
        movie_code = box_office_item['movieCd']
        
        # 2단계: 상세 정보 호출 (DETAIL_KEY 사용)
        detail_info = fetch_movie_details(detail_key, movie_code)
        
        if detail_info:
            open_dt = detail_info.get('openDt', '99991231')
            
            # 누적 관객수(`audiAcc`)는 BoxOffice API에서 가져온 것을 사용합니다.
            audi_cnt = int(box_office_item.get('audiAcc', '0'))
            
            # 관람 등급 정보 추출
            watch_grade = detail_info.get('audits', [{}])[0].get('watchGradeNm', '등급 없음')

            record = {
                'movieNm': box_office_item.get('movieNm'),
                'audiCnt': audi_cnt,
                'openDt': open_dt,
                'watchGrade': watch_grade, 
                'targetDate': target_date_dt, 
                # 장르 정보 추출
                'genres': [g['genreNm'] for g in detail_info.get('genres', [])],
            }
            
            # 감독 정보 추출
            directors = [(d['peopleNm'], record['movieNm'], audi_cnt, record['openDt']) for d in detail_info.get('directors', [])]
            record['directors'] = directors
            
            # 회사(제작사/배급사) 및 순수 배급사 정보 추출
            companies = []
            distributors = []
            for company in detail_info.get('companys', []):
                role = company.get('companyPartNm', '')
                if '제작' in role or '배급' in role:
                    companies.append((company.get('companyNm', '미상'), record['movieNm'], audi_cnt, role, record['openDt']))
                
                # 순수 배급사 목록 (시장 점유율 분석용)
                if '배급' in role:
                    distributors.append((company.get('companyNm', '미상'), record['movieNm'], audi_cnt, role, record['openDt']))

            record['companies'] = companies
            record['distributors'] = distributors
            
            movie_records.append(record)

        progress_bar.progress((i + 1) / total_movies)
        
    progress_bar.empty()
    st.success("2단계 완료: 모든 영화의 상세 정보 및 관계 데이터 수집 완료.")
    
    return movie_records

def analyze_hitmaker_index(movie_records, entity_type='Director'):
    """
    감독 또는 회사의 총 관객 수(Total Audience)를 계산하고 DataFrame을 생성합니다.
    (총 관객 수 기준 Top 30)
    """
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
        # Sort_Index (총 관객 수) 기준으로 내림차순 정렬
        df = pd.DataFrame(results).sort_values(by='Sort_Index', ascending=False).reset_index(drop=True)
    except KeyError:
        st.error("데이터프레임 구조 오류: 분석 키('Sort_Index')를 찾을 수 없습니다.")
        return pd.DataFrame()

    df.index = df.index + 1
    df.index.name = 'Rank'
    
    # 💡 Y축에 사용할 순위+이름 조합 컬럼 생성
    df['Rank_Name'] = df.index.map(str) + ". " + df['Name']

    # ❌ Plotly 차트에 전달할 데이터는 정수(int) 형태의 Total_Audience여야 하므로, 
    # 포맷팅은 차트 생성 후 테이블 표시 직전에만 합니다.
    df['Total_Audience_Formatted'] = df['Total_Audience'].apply(lambda x: f"{x:,.0f} 명")
    
    return df

def analyze_genre_trends(movie_records):
    """
    수집된 데이터를 기반으로 장르별 흥행 트렌드(총 관객 수, 영화 수, 점유율)를 계산합니다.
    """
    genre_data = defaultdict(lambda: {'total_audience': 0, 'movie_count': 0})
    total_market_audience = sum(movie['audiCnt'] for movie in movie_records)
    
    for movie in movie_records:
        audience = movie['audiCnt']
        genres = movie.get('genres')
        
        if not genres:
            continue

        for genre_name in genres:
            genre_data[genre_name]['total_audience'] += audience
            genre_data[genre_name]['movie_count'] += 1
            
    results = []
    for name, data in genre_data.items():
        if data['total_audience'] > 0:
            share = (data['total_audience'] / total_market_audience) * 100 if total_market_audience > 0 else 0
            
            results.append({
                'Genre_Name': name,
                'Total_Audience': int(data['total_audience']),
                'Movie_Count': data['movie_count'],
                'Audience_Share_Percentage': share
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
    """
    수집된 데이터를 기반으로 등급별 흥행 효과(평균 관객 수, 점유율)를 계산합니다.
    """
    rating_data = defaultdict(lambda: {'total_audience': 0, 'movie_count': 0})
    total_market_audience = sum(movie['audiCnt'] for movie in movie_records)
    
    for movie in movie_records:
        audience = movie['audiCnt']
        rating = movie.get('watchGrade')
        
        if not rating or audience <= 0:
            continue

        rating_data[rating]['total_audience'] += audience
        rating_data[rating]['movie_count'] += 1
            
    results = []
    for name, data in rating_data.items():
        if data['movie_count'] > 0:
            avg_audience = data['total_audience'] / data['movie_count']
            share = (data['total_audience'] / total_market_audience) * 100 if total_market_audience > 0 else 0
            
            results.append({
                'Rating_Name': name,
                'Total_Audience': int(data['total_audience']),
                'Movie_Count': data['movie_count'],
                'Avg_Audience': int(avg_audience),
                'Audience_Share_Percentage': share
            })

    if not results:
        return pd.DataFrame(), 0

    # 평균 관객 수 기준으로 내림차순 정렬
    df = pd.DataFrame(results).sort_values(by='Avg_Audience', ascending=False).reset_index(drop=True)
    df.index = df.index + 1
    df.index.name = 'Rank'
    
    df['Total_Audience_Formatted'] = df['Total_Audience'].apply(lambda x: f"{x:,.0f} 명")
    df['Avg_Audience_Formatted'] = df['Avg_Audience'].apply(lambda x: f"{x:,.0f} 명")
    df['Audience_Share_Formatted'] = df['Audience_Share_Percentage'].apply(lambda x: f"{x:.1f} %")
    
    return df, total_market_audience

def analyze_movie_age(movie_records, target_date):
    """
    개봉일과 기준일을 비교하여 영화 연령대별 흥행을 분석합니다.
    (그룹 이름을 신작, 중기작, 장기작으로 변경)
    """
    age_data = defaultdict(lambda: {'total_audience': 0, 'movie_count': 0})
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
            # 개봉일 데이터 형식이 잘못된 경우 스킵
            continue

        # 그룹 이름을 신작, 중기작, 장기작으로 변경
        if days_since_open <= 7:
            age_group = "신작 (New Release)"
        elif days_since_open <= 28: # 2~4주차
            age_group = "중기작 (Mid-Term)"
        else:
            age_group = "장기작 (Veteran)"
            
        age_data[age_group]['total_audience'] += audience
        age_data[age_group]['movie_count'] += 1
            
    results = []
    for name, data in age_data.items():
        if data['total_audience'] > 0:
            share = (data['total_audience'] / total_market_audience) * 100 if total_market_audience > 0 else 0
            
            results.append({
                'Age_Group': name,
                'Total_Audience': int(data['total_audience']),
                'Movie_Count': data['movie_count'],
                'Audience_Share_Percentage': share
            })

    if not results:
        return pd.DataFrame(), 0

    df = pd.DataFrame(results).sort_values(by='Total_Audience', ascending=False).reset_index(drop=True)
    df.index = df.index + 1
    df.index.name = 'Rank'
    
    df['Total_Audience_Formatted'] = df['Total_Audience'].apply(lambda x: f"{x:,.0f} 명")
    df['Audience_Share_Formatted'] = df['Audience_Share_Percentage'].apply(lambda x: f"{x:.1f} %")
    
    return df, total_market_audience

# ===============================================
# 3. Streamlit 앱 레이아웃 및 기능 구현
# ===============================================

def main():
    """Streamlit 앱의 메인 함수"""
    
    st.set_page_config(
        page_title="K-Movie Ecosystem Explorer",
        layout="wide",
        initial_sidebar_state="auto"
    )

    st.title("🎬 K-Movie Ecosystem Explorer (영화 산업 분석 - 박스오피스 기반)")
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
    # 최소 개봉 연도 선택 (분석 필터)는 제거됨
    target_date_str = target_date_dt.strftime("%Y%m%d")

    st.sidebar.markdown("---")
    # --- 필터 설정 끝 ---

    # 1. 데이터 로드 (캐싱된 데이터 사용)
    # 최소 개봉 연도 필터(start_year)를 사용하지 않으므로 인자에서 제거
    movie_records = get_full_analysis_data(KOBIS_BOXOFFICE_KEY, KOBIS_DETAIL_KEY, target_date_str) 
    
    if movie_records is None or not movie_records: 
        st.warning("데이터 수집에 실패했거나, 흥행 기록이 있는 영화가 수집되지 않았습니다. 기준 날짜를 변경하거나 API 키를 확인해 주세요.")
        st.stop()
        
    st.markdown("---")
    st.subheader("📊 3단계: 데이터 분석 및 시각화")

    # -----------------------------------------------
    # 3.1 탭 구조로 분석 유형 분리
    # (배급사 시장 점유율 탭 제거, 총 4개 탭)
    # -----------------------------------------------
    
    tab1, tab2, tab3, tab4 = st.tabs([
        "감독/회사 흥행 분석", 
        "장르별 흥행 트렌드", 
        "등급별 흥행 효과",
        "영화 연령별 흥행 (신작/중기작/장기작)" # 탭 이름 변경
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
                help="감독 또는 회사(제작/배급)를 기준으로 흥행 지수를 분석합니다."
            )
        
        st.markdown("---")
        
        col_info_1, col_info_2 = st.columns([1, 3])
        
        with col_info_1:
            if 'initial_run' not in st.session_state:
                st.session_state['initial_run'] = True
            analyze_button = st.button(f"'{entity_selection}' 흥행 분석 실행", use_container_width=True, key='analyze_tab1_btn')

        with col_info_2:
            st.info(f"""
                **분석 기준: 총 관객 수 (절대적 규모)**
                선택된 {entity_selection}이 참여한 모든 영화의 **누적 관객 수 합계**를 기준으로 순위가 결정됩니다.
            """)
            
        if analyze_button or st.session_state.get('initial_run', True):
            st.session_state['initial_run'] = False 
            
            with st.spinner(f"'{entity_selection}'의 총 관객수를 계산 중입니다..."):
                analysis_df = analyze_hitmaker_index(movie_records, entity_selection)
                
                if not analysis_df.empty:
                    top_n = 30 
                    top_df = analysis_df.head(top_n).copy()
                    
                    st.subheader(f"🏆 Top {top_n} {entity_selection} 흥행 분석 (총 관객 수)")
                    
                    # 💡 그래프 순서 최종 수정 (Rank_Name 컬럼 사용)
                    # Plotly bar chart
                    fig = px.bar(
                        top_df,
                        x='Total_Audience', 
                        y='Rank_Name', # 순위+이름 조합 컬럼 사용
                        orientation='h',
                        title=f"Top {top_n} {entity_selection} Total Audience Count (기준일: {target_date_str})",
                        color='Total_Audience',
                        color_continuous_scale=px.colors.sequential.Teal,
                        hover_data={'Total_Audience': ':.0f', 'Movie_Count': True}
                    ) 
                    
                    # Y축 순서를 데이터프레임의 순서(1위부터 30위까지)와 일치시키고,
                    # Y축을 강제로 뒤집어(reversed) 1위 항목이 그래프의 가장 위에 오도록 합니다.
                    top_df_names_in_order = top_df['Rank_Name'].tolist()
                    
                    fig.update_layout(
                        xaxis_title="총 누적 관객 수", 
                        yaxis_title=entity_selection, 
                        # Y축: 순위대로 정렬 (1위가 가장 위에 오도록 reversed)
                        yaxis={
                            'categoryorder': 'array',
                            'categoryarray': top_df_names_in_order, 
                            'autorange': 'reversed' 
                        }, 
                        # X축: 값이 클수록 막대가 길어지도록 정방향으로 설정 (가장 긴 막대가 가장 큰 값)
                        # 💡 수정: X축의 최솟값을 0으로 강제하기 위해 'autorange'를 제거하고 'range'만 사용
                        xaxis={
                             # X축 범위를 0부터 데이터 최대값의 1.1배까지 설정하여 0에서 시작하도록 강제
                             'range': [0, top_df['Sort_Index'].max() * 1.1] 
                        },
                        height=max(500, top_n * 30)
                    )
                    st.plotly_chart(fig, use_container_width=True) 

                    display_df = top_df.rename(columns={
                        'Name': '이름',
                        'Movie_Count': '총 참여 영화 수',
                        'Total_Audience': '총 관객 수 (명)',
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
                    st.warning(f"분석 결과가 없습니다. 기준일에 흥행 기록이 있는 영화가 부족하거나, 설정된 개봉 연도 필터와 일치하는 영화가 없습니다.")

    # Tab 2: 장르별 흥행 트렌드 (탭 순서 변경됨)
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
        else:
            st.warning("분석할 장르 데이터가 없습니다. (KOBIS API에서 장르 정보가 누락되었거나, 흥행 영화가 없습니다.)")

    # Tab 3: 등급별 흥행 효과 분석 (탭 순서 변경됨)
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
            # Y축 순서를 평균 관객 수 기준으로 정렬 (내림차순)
            fig_bar.update_layout(
                xaxis_title="평균 관객 수", 
                yaxis_title="관람 등급", 
                yaxis={'categoryorder': 'total ascending'}, # 평균 관객 수 기준으로 정렬하여 1위가 위에 오도록 함
                xaxis={'autorange': True}, # X축 순서가 바뀌는 것을 방지
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
        else:
            st.warning("분석할 등급 데이터가 없습니다. (KOBIS API에서 등급 정보가 누락되었거나, 흥행 영화가 없습니다.)")

    # Tab 4: 영화 연령별 흥행 분석 (탭 순서 변경 및 이름 변경됨)
    with tab4:
        st.subheader("📅 영화 연령별 시장 역동성 분석 (신작, 중기작, 장기작)")
        st.markdown("개봉일과 기준일을 비교하여 신작, 중기작, 장기 흥행작의 관객 점유율을 분석합니다. (시장 역동성 파악)")
        
        movie_age_df, total_audience = analyze_movie_age(movie_records, target_date_dt)
        
        if not movie_age_df.empty:
            st.markdown(f"**총 분석 관객 수:** {total_audience:,.0f} 명")
            
            # 도넛 차트 (Plotly)
            fig_pie = px.pie(
                movie_age_df,
                values='Total_Audience',
                names='Age_Group',
                title='시장 관객 수 점유율 (영화 연령별)',
                color_discrete_sequence=px.colors.qualitative.Bold
            )
            fig_pie.update_traces(textinfo='percent+label', marker=dict(line=dict(color='#000000', width=1)))
            st.plotly_chart(fig_pie, use_container_width=True)             
            # 데이터 테이블
            display_age_df = movie_age_df.rename(columns={
                'Age_Group': '영화 연령 그룹',
                'Movie_Count': '그룹 내 영화 수',
                'Total_Audience_Formatted': '총 관객 수 (명)',
                'Audience_Share_Formatted': '관객 점유율',
            })[['영화 연령 그룹', '그룹 내 영화 수', '총 관객 수 (명)', '관객 점유율']]
            st.dataframe(display_age_df, use_container_width=True, hide_index=False)
        else:
            st.warning("분석할 연령 데이터가 없습니다. (개봉일 정보가 누락되었거나, 흥행 영화가 없습니다.)")


if __name__ == "__main__":
    main()
