import streamlit as st
import pandas as pd
import requests
from collections import defaultdict
import plotly.express as px

# ===============================================
# 1. 환경 설정 및 데이터 정의 (KOBIS API 사용)
# ===============================================

# --- API KEY ---
# KOBIS API에서 발급받은 두 가지 키를 여기에 직접 입력합니다.
# -----------------------------------------------------------
# 1. 영화 목록 (LIST) API 키: searchMovieList 호출에 사용 (사용자 키 적용)
KOBIS_LIST_KEY = "cc5c76f4946f878b829af9b116062ad4" 

# 2. 영화 상세 정보 (DETAIL) API 키: searchMovieInfo 호출에 사용 (사용자 키 적용)
KOBIS_DETAIL_KEY = "6350d8964d4c5160f40135185663cb48" 
# -----------------------------------------------------------


# --- API URLS ---
LIST_URL = "http://www.kobis.or.kr/kobisopenapi/webservice/rest/movie/searchMovieList.json"
DETAIL_URL = "http://www.kobis.or.kr/kobisopenapi/webservice/rest/movie/searchMovieInfo.json"

# ===============================================
# 2. 데이터 처리 및 분석 로직
# ===============================================

@st.cache_data(show_spinner="🎬 1단계: 초기 영화 목록을 불러오는 중...")
def fetch_movie_list(list_key):
    """
    KOBIS 영화 목록 API를 호출하여 영화 코드 리스트를 가져옵니다.
    """
    if not list_key or list_key == "YOUR_LIST_API_KEY_HERE":
        st.error("🚨 영화 목록 키가 설정되지 않았습니다. 작업을 중단합니다.")
        return None
        
    params = {'key': list_key, 'itemPerPage': 100} # 최대 100개 영화
    try:
        response = requests.get(LIST_URL, params=params, timeout=10)
        response.raise_for_status() 
        data = response.json()
        movie_list = data.get('movieListResult', {}).get('movieList', [])
        st.success(f"1단계 완료: 총 {len(movie_list)}개의 영화 코드를 가져왔습니다.")
        return movie_list
    except requests.exceptions.RequestException as e:
        st.error(f"❌ 1단계 API 요청 중 오류 발생: {e}")
        return None

def fetch_movie_details(detail_key, movie_code):
    """영화 상세 정보(관객수, 회사, 감독)를 가져옵니다."""
    if not detail_key or detail_key == "YOUR_DETAIL_API_KEY_HERE":
        return None 
        
    params = {'key': detail_key, 'movieCd': movie_code}
    try:
        response = requests.get(DETAIL_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        return data.get('movieInfoResult', {}).get('movieInfo', {})
    except requests.exceptions.RequestException:
        return None

def get_full_analysis_data(list_key, detail_key):
    """1, 2단계 API 호출을 통합하고 데이터 분석을 위한 DataFrame을 생성합니다."""
    movie_list_data = fetch_movie_list(list_key)
    
    if movie_list_data is None:
        return None # 데이터가 없으면 None 반환

    st.markdown("---")
    st.subheader("🎬 2단계: 상세 정보 및 관계 데이터 수집 중...")
    progress_bar = st.progress(0, text="각 영화의 관객수, 감독, 회사 정보를 수집 중입니다...")
    
    movie_records = []
    total_movies = len(movie_list_data)
    
    for i, movie in enumerate(movie_list_data):
        movie_code = movie['movieCd']
        
        # 상세 정보 호출 시 DETAIL 키 사용
        detail_info = fetch_movie_details(detail_key, movie_code)
        
        if detail_info:
            # audiCnt가 없으면 '0', 있으면 콤마 제거 후 정수 변환
            audi_cnt = 0
            audi_cnt_str = detail_info.get('audiCnt', '0')
            try:
                if audi_cnt_str:
                    audi_cnt = int(audi_cnt_str.replace(',', ''))
            except ValueError:
                audi_cnt = 0

            # 영화 레코드 저장
            record = {
                'movieNm': detail_info.get('movieNm', movie['movieNm']),
                'audiCnt': audi_cnt,
                'openDt': detail_info.get('openDt', '정보 없음'),
            }
            
            # 감독 정보 추출
            directors = [(d['peopleNm'], detail_info['movieNm'], audi_cnt) for d in detail_info.get('directors', [])]
            record['directors'] = directors
            
            # 회사(제작사/배급사) 정보 추출
            companies = []
            for company in detail_info.get('companys', []):
                # 제작사와 배급사만 포함
                role = company.get('companyPartNm', '')
                if '제작' in role or '배급' in role:
                    companies.append((company['companyNm'], detail_info['movieNm'], audi_cnt, role))
            record['companies'] = companies
            
            movie_records.append(record)

        progress_percentage = (i + 1) / total_movies
        progress_bar.progress(progress_percentage)
        
    progress_bar.empty()
    st.success("2단계 완료: 모든 영화의 상세 정보 및 관계 데이터 수집 완료.")
    
    return movie_records

def analyze_hitmaker_index(movie_records, entity_type='Director'):
    """
    수집된 데이터를 기반으로 감독 또는 회사의 평균 흥행 지수를 계산합니다.
    """
    entity_data = defaultdict(lambda: {'total_audience': 0, 'movie_count': 0, 'movies': []})
    
    for movie in movie_records:
        if entity_type == 'Director':
            entities = movie['directors']
        elif entity_type == 'Company':
            entities = movie['companies']
        else:
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

    # --- [수정된 부분] results 리스트가 비어있는지 확인 ---
    if not results:
        # 이 경우, 흥행 기록이 있는 영화를 찾지 못했음을 의미합니다.
        return pd.DataFrame() 
    # --- [수정된 부분 끝] ---

    # Avg_Audience를 기준으로 내림차순 정렬
    df = pd.DataFrame(results).sort_values(by='Avg_Audience', ascending=False).reset_index(drop=True)
    df.index = df.index + 1
    df.index.name = 'Rank'
    
    # 누적 관객 수와 평균 관객 수를 보기 좋게 포맷팅
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
        layout="wide", # 넓은 레이아웃 사용
        initial_sidebar_state="auto"
    )

    st.title("🎬 K-Movie Ecosystem Explorer (영화 산업 분석)")
    st.markdown("---")
    
    # 1. 데이터 로드 (캐싱된 데이터 사용)
    movie_records = get_full_analysis_data(KOBIS_LIST_KEY, KOBIS_DETAIL_KEY)
    
    if movie_records is None or not movie_records: 
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
                    title=f"Top {top_n} {entity_selection} Average Audience Count",
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
                st.warning(f"데이터 부족 또는 흥행 기록이 없는 영화만 수집되어 분석할 수 없습니다. 검색 조건을 조정해 보세요.")

if __name__ == "__main__":
    main()
