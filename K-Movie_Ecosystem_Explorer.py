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
# 고객님께서 제공해주신 새로운 API 키(f6ae9fdbd8ba038eda177250d3e57b4c)로 두 개의 키를 모두 업데이트합니다.
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

# @st.cache_data를 사용하여 API 호출 결과를 캐시하여 재실행 시 속도를 높입니다.
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

# start_year 매개변수는 이제 UI에서만 사용하며 API 호출에 직접 사용되지 않습니다.
def get_full_analysis_data(boxoffice_key, detail_key, target_date, start_year):
    """1, 2단계 API 호출을 통합하고 데이터 분석을 위한 DataFrame을 생성합니다."""
    
    if not boxoffice_key or not detail_key:
        return None 
        
    # 1단계: 흥행 영화 목록 가져오기 (BOXOFFICE_KEY 사용)
    boxoffice_list = fetch_boxoffice_list(boxoffice_key, target_date)
    
    if boxoffice_list is None:
        return None 

    st.markdown("---")
    st.subheader("🎬 2단계: 상세 정보 및 관계 데이터 수집 중...")
    progress_bar = st.progress(0, text="각 영화의 감독, 회사 정보를 수집 중입니다...")
    
    movie_records = []
    total_movies = len(boxoffice_list)
    
    # 목표 연도 설정
    target_year = str(start_year)
    
    for i, box_office_item in enumerate(boxoffice_list):
        movie_code = box_office_item['movieCd']
        
        # 2단계: 상세 정보 호출 (DETAIL_KEY 사용)
        detail_info = fetch_movie_details(detail_key, movie_code)
        
        if detail_info:
            open_dt = detail_info.get('openDt', '99991231')
            
            # Python 코드 내에서 연도 필터링 수행
            if len(open_dt) >= 4 and int(open_dt[:4]) < start_year:
                progress_bar.progress((i + 1) / total_movies)
                continue # 선택된 연도보다 이전 영화는 건너뜀
                
            # 누적 관객수(`audiAcc`)는 BoxOffice API에서 가져온 것을 사용합니다.
            audi_cnt = int(box_office_item.get('audiAcc', '0'))

            record = {
                'movieNm': box_office_item.get('movieNm'),
                'audiCnt': audi_cnt,
                'openDt': open_dt,
            }
            
            # 감독 정보 추출
            directors = [(d['peopleNm'], record['movieNm'], audi_cnt) for d in detail_info.get('directors', [])]
            record['directors'] = directors
            
            # 회사(제작사/배급사) 정보 추출
            companies = []
            for company in detail_info.get('companys', []):
                role = company.get('companyPartNm', '')
                if '제작' in role or '배급' in role:
                    companies.append((company.get('companyNm', '미상'), record['movieNm'], audi_cnt, role))
            record['companies'] = companies
            
            movie_records.append(record)

        progress_bar.progress((i + 1) / total_movies)
        
    progress_bar.empty()
    st.success("2단계 완료: 모든 영화의 상세 정보 및 관계 데이터 수집 완료.")
    
    return movie_records

def analyze_hitmaker_index(movie_records, entity_type='Director'):
    """
    수집된 데이터를 기반으로 감독 또는 회사의 평균 흥행 지수를 계산하고 DataFrame을 생성합니다.
    (이 함수는 이전과 동일하며, 안정성이 검증됨)
    """
    entity_data = defaultdict(lambda: {'total_audience': 0, 'movie_count': 0})
    
    for movie in movie_records:
        entities = movie.get('directors') if entity_type == 'Director' else movie.get('companies')
        if not entities:
            continue

        for entity_tuple in entities:
            entity_name = entity_tuple[0]
            audience = entity_tuple[2]
            
            if audience > 0:
                entity_data[entity_name]['total_audience'] += audience
                entity_data[entity_name]['movie_count'] += 1
                
    results = []
    for name, data in entity_data.items():
        if data['movie_count'] > 0:
            avg_audience = data['total_audience'] / data['movie_count']
            results.append({
                'Name': name,
                'Type': entity_type,
                'Movie_Count': data['movie_count'],
                'Total_Audience': data['total_audience'],
                'Avg_Audience': int(avg_audience),
            })

    # KeyError: 'Avg_Audience' 방지: results가 비어있으면 빈 DataFrame 반환
    if not results:
        return pd.DataFrame() 

    # Avg_Audience를 기준으로 내림차순 정렬
    try:
        df = pd.DataFrame(results).sort_values(by='Avg_Audience', ascending=False).reset_index(drop=True)
    except KeyError:
        st.error("데이터프레임 구조 오류: 분석 키('Avg_Audience')를 찾을 수 없습니다.")
        return pd.DataFrame()

    df.index = df.index + 1
    df.index.name = 'Rank'
    
    df['Total_Audience'] = df['Total_Audience'].apply(lambda x: f"{x:,.0f} 명")
    df['Avg_Audience_Formatted'] = df['Avg_Audience'].apply(lambda x: f"{x:,.0f} 명")
    
    return df

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
    
    # 주간 박스오피스는 기준일이 필요합니다.
    # 현재 날짜로부터 7일 전(지난 주)의 일요일 날짜를 기본값으로 사용
    today = datetime.today()
    # KOBIS는 일요일 기준 주간 박스오피스를 제공합니다. targetDt는 해당 주의 '일요일' 날짜여야 합니다.
    # 오늘이 일요일(6)이라면 오늘, 아니면 지난 주 일요일을 계산합니다.
    days_to_subtract = today.weekday() + 1
    if days_to_subtract > 6: days_to_subtract = 7 # 일요일은 0이 아닌 6을 반환하므로 조정
    
    default_date = today - timedelta(days=days_to_subtract)
    
    # 사용자에게 기준 날짜를 입력받습니다.
    target_date_dt = st.sidebar.date_input(
        "주간 박스오피스 기준일 (일요일):",
        value=default_date,
        max_value=today,
        help="선택한 날짜의 주간 박스오피스를 기준으로 영화 목록을 가져옵니다."
    )
    # KOBIS API 형식인 YYYYMMDD 문자열로 변환
    target_date_str = target_date_dt.strftime("%Y%m%d")

    # 개봉 연도 필터 (분석 데이터 필터링용)
    current_year = datetime.now().year
    start_year_options = list(range(2000, current_year + 1))
    default_index = start_year_options.index(2018) if 2018 in start_year_options else len(start_year_options) - 1
    
    start_year = st.sidebar.selectbox(
        "최소 개봉 연도 선택 (분석 필터):", 
        options=start_year_options,
        index=default_index, 
        key='start_year_select',
        help="이 연도 이후에 개봉된 영화만 분석에 사용됩니다."
    )
    st.sidebar.markdown("---")
    # --- 필터 설정 끝 ---


    # 1. 데이터 로드 (변경된 API 키와 인수를 사용)
    movie_records = get_full_analysis_data(KOBIS_BOXOFFICE_KEY, KOBIS_DETAIL_KEY, target_date_str, start_year) 
    
    if movie_records is None or not movie_records: 
        st.warning("데이터 수집에 실패했거나, 흥행 기록이 있는 영화가 수집되지 않았습니다. 기준 날짜를 변경하거나 API 키를 확인해 주세요.")
        st.stop()
        
    st.markdown("---")
    st.subheader("📊 3단계: 데이터 분석 및 시각화")

    # -----------------------------------------------
    # 3.1 분석 대상 선택 및 실행
    # -----------------------------------------------
    
    col1, col2 = st.columns([1, 3])
    
    with col1:
        entity_selection = st.radio(
            "분석 대상 선택:",
            ('Director', 'Company'),
            key='entity_select',
            index=0,
            help="감독 또는 회사(제작/배급)를 기준으로 흥행 지수를 분석합니다."
        )
        if 'initial_run' not in st.session_state:
            st.session_state['initial_run'] = True

        analyze_button = st.button(f"'{entity_selection}' 흥행 지수 분석 실행", use_container_width=True)

    with col2:
        st.info(f"""
            **분석 기준: {entity_selection} 흥행 지수**
            선택된 {entity_selection}이 참여한 모든 영화의 **평균 누적 관객 수**를 계산하여 
            가장 높은 평균 관객 수를 기록한 엔티티를 순위(Rank)로 표시합니다. (최소 1개 이상의 관객 기록 영화 참여 필수)
        """)
        

    # -----------------------------------------------
    # 3.2 분석 결과 표시
    # -----------------------------------------------
    if analyze_button or st.session_state['initial_run']:
        if st.session_state['initial_run']:
            st.session_state['initial_run'] = False 

        with st.spinner(f"'{entity_selection}'의 흥행 지수를 계산 중입니다..."):
            
            analysis_df = analyze_hitmaker_index(movie_records, entity_selection)
            
            if not analysis_df.empty:
                
                top_n = 10
                top_df = analysis_df.head(top_n).copy()
                
                st.subheader(f"🏆 Top {top_n} {entity_selection} 흥행 지수")
                st.markdown(f"**기준:** 영화 당 평균 누적 관객 수 (최소 1개 관객 기록 영화 참여)")
                
                # Plotly 막대 차트 시각화
                fig = px.bar(
                    top_df,
                    x='Avg_Audience',
                    y='Name',
                    orientation='h',
                    title=f"Top {top_n} {entity_selection} Average Audience Count (기준일: {target_date_str})",
                    color='Avg_Audience',
                    color_continuous_scale=px.colors.sequential.Teal,
                    hover_data={
                        'Avg_Audience': ':.0f',
                        'Name': True,
                        'Movie_Count': True
                    }
                ) 
                
                fig.update_layout(
                    xaxis_title="평균 누적 관객 수",
                    yaxis_title=entity_selection,
                    height=500
                )
                st.plotly_chart(fig, use_container_width=True)

                # 데이터 테이블 표시
                display_df = top_df.rename(columns={
                    'Name': '이름',
                    'Movie_Count': '참여 영화 수',
                    'Total_Audience': '총 관객 수',
                    'Avg_Audience_Formatted': '평균 관객 수'
                })[['이름', '참여 영화 수', '평균 관객 수', '총 관객 수']]
                
                st.dataframe(display_df, use_container_width=True)
                
            else:
                st.warning(f"분석 결과가 없습니다. 기준일에 흥행 기록이 있는 영화가 부족하거나, 설정된 개봉 연도 필터({start_year}년)와 일치하는 영화가 없습니다.")

if __name__ == "__main__":
    main()
