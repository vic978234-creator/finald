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
            directors = [(d['peopleNm'], record['movieNm'], audi_cnt, record['openDt']) for d in detail_info.get('directors', [])]
            record['directors'] = directors
            
            # 회사(제작사/배급사) 정보 추출
            companies = []
            for company in detail_info.get('companys', []):
                role = company.get('companyPartNm', '')
                if '제작' in role or '배급' in role:
                    companies.append((company.get('companyNm', '미상'), record['movieNm'], audi_cnt, role, record['openDt']))
            record['companies'] = companies
            
            movie_records.append(record)

        progress_bar.progress((i + 1) / total_movies)
        
    progress_bar.empty()
    st.success("2단계 완료: 모든 영화의 상세 정보 및 관계 데이터 수집 완료.")
    
    return movie_records

def analyze_hitmaker_index(movie_records, entity_type='Director', index_type='Efficiency'):
    """
    수집된 데이터를 기반으로 감독 또는 회사의 다양한 흥행 지수를 계산하고 DataFrame을 생성합니다.
    """
    # movie_list 항목과 non_zero_count를 추가하여 참여 영화 목록을 저장합니다.
    entity_data = defaultdict(lambda: {
        'total_audience': 0, 
        'movie_count': 0, 
        'non_zero_count': 0, # 흥행 기록이 0이 아닌 영화의 수
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
            
            # 모든 참여 영화 수 증가
            entity_data[entity_name]['movie_count'] += 1
            
            if audience > 0:
                entity_data[entity_name]['total_audience'] += audience
                entity_data[entity_name]['non_zero_count'] += 1 # 흥행 영화 수
                
                # 참여 영화 목록 추가 (이름과 개봉일)
                entity_data[entity_name]['movie_list'].append({
                    'name': movie_name,
                    'open_dt': open_dt
                })
                
    results = []
    for name, data in entity_data.items():
        total_aud = data['total_audience']
        movie_cnt = data['movie_count']
        non_zero_cnt = data['non_zero_count']
        
        # 흥행 기록이 있는 영화가 최소 1편은 있어야 분석 대상으로 간주
        if non_zero_cnt > 0:
            
            # 1. 흥행 효율성 지수 (Efficiency Index) - 기존 평균 관객수
            efficiency_index = total_aud / non_zero_cnt 
            
            # 2. 흥행 안정성 지수 (Stability Index)
            # 정의: (평균 관객수) * (흥행 성공률) -> (Total Audience / Total Movies) * (Non-Zero Movies / Total Movies)
            if movie_cnt > 0:
                # 총 관객수 / 총 참여 영화 수
                average_per_total = total_aud / movie_cnt
                # 흥행 성공률 (0이 아닌 영화 수 / 총 참여 영화 수)
                success_rate = non_zero_cnt / movie_cnt
                
                stability_index = average_per_total * success_rate
            else:
                stability_index = 0
            
            
            # 정렬 기준 지수 설정
            sort_index = 0
            if index_type == 'Efficiency':
                sort_index = efficiency_index
            elif index_type == 'Stability':
                sort_index = stability_index
            elif index_type == 'Total':
                sort_index = total_aud
            
            # 영화 목록 정리
            sorted_movies = sorted(data['movie_list'], key=lambda x: x['open_dt'], reverse=True)
            movie_display_list = [f"{m['name']} ({m['open_dt'][:4]})" for m in sorted_movies]
            
            results.append({
                'Name': name,
                'Type': entity_type,
                'Movie_Count': movie_cnt,
                'Non_Zero_Count': non_zero_cnt,
                'Total_Audience': int(total_aud),
                'Efficiency_Index': int(efficiency_index),
                'Stability_Index': int(stability_index),
                'Sort_Index': sort_index,
                'Movie_List': movie_display_list 
            })

    # KeyError: 'Sort_Index' 방지: results가 비어있으면 빈 DataFrame 반환
    if not results:
        return pd.DataFrame() 

    # Sort_Index를 기준으로 내림차순 정렬
    try:
        df = pd.DataFrame(results).sort_values(by='Sort_Index', ascending=False).reset_index(drop=True)
    except KeyError:
        st.error("데이터프레임 구조 오류: 분석 키('Sort_Index')를 찾을 수 없습니다.")
        return pd.DataFrame()

    df.index = df.index + 1
    df.index.name = 'Rank'
    
    # 표시용 포맷팅
    df['Total_Audience'] = df['Total_Audience'].apply(lambda x: f"{x:,.0f} 명")
    df['Efficiency_Index'] = df['Efficiency_Index'].apply(lambda x: f"{x:,.0f} 명")
    df['Stability_Index'] = df['Stability_Index'].apply(lambda x: f"{x:,.0f}")
    
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
    
    # 주간 박스오피스 기준일
    today = datetime.today()
    days_to_subtract = today.weekday() + 1
    if days_to_subtract > 6: days_to_subtract = 7
    default_date = today - timedelta(days=days_to_subtract)
    target_date_dt = st.sidebar.date_input(
        "주간 박스오피스 기준일 (일요일):",
        value=default_date,
        max_value=today,
        help="선택한 날짜의 주간 박스오피스 상위 100개 영화를 기준으로 데이터를 가져옵니다."
    )
    target_date_str = target_date_dt.strftime("%Y%m%d")

    # 개봉 연도 필터
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

    # 1. 데이터 로드 (캐싱된 데이터 사용)
    movie_records = get_full_analysis_data(KOBIS_BOXOFFICE_KEY, KOBIS_DETAIL_KEY, target_date_str, start_year) 
    
    if movie_records is None or not movie_records: 
        st.warning("데이터 수집에 실패했거나, 흥행 기록이 있는 영화가 수집되지 않았습니다. 기준 날짜를 변경하거나 API 키를 확인해 주세요.")
        st.stop()
        
    st.markdown("---")
    st.subheader("📊 3단계: 데이터 분석 및 시각화")

    # -----------------------------------------------
    # 3.1 분석 대상 및 지표 선택
    # -----------------------------------------------
    
    col_select_1, col_select_2 = st.columns([1, 1])
    
    with col_select_1:
        entity_selection = st.radio(
            "분석 대상 선택:",
            ('Director', 'Company'),
            key='entity_select',
            index=0,
            help="감독 또는 회사(제작/배급)를 기준으로 흥행 지수를 분석합니다."
        )
    
    with col_select_2:
        index_selection = st.selectbox(
            "분석 지표 선택:",
            options=['Efficiency', 'Stability', 'Total'],
            format_func=lambda x: {
                'Efficiency': '흥행 효율성 지수 (평균 관객 수)',
                'Stability': '흥행 안정성 지수 (성공률 반영)',
                'Total': '총 관객 수 (절대적 규모)'
            }.get(x),
            key='index_select',
            help="분석 기준이 되는 지표를 선택하세요."
        )
        
    st.markdown("---")
    
    # -----------------------------------------------
    # 3.2 분석 실행 버튼 및 정보
    # -----------------------------------------------
    
    col_info_1, col_info_2 = st.columns([1, 3])
    
    with col_info_1:
        if 'initial_run' not in st.session_state:
            st.session_state['initial_run'] = True
        analyze_button = st.button(f"'{entity_selection}' 흥행 분석 실행", use_container_width=True)

    with col_info_2:
        index_description = {
            'Efficiency': "한 편당 동원하는 평균 관객 수로, 흥행 규모를 직관적으로 나타냅니다.",
            'Stability': "참여 영화의 평균 관객 수와 흥행 성공률(관객 0명 이상)을 결합하여, 꾸준하고 안정적인 흥행 능력을 평가합니다.",
            'Total': "참여 영화들의 누적 관객 수 합계로, 절대적인 시장 영향력을 평가합니다."
        }.get(index_selection, "분석 지표에 대한 설명입니다.")
        
        st.info(f"""
            **선택된 지표: {index_selection}**
            {index_description} (최소 1개 이상의 흥행 기록 영화 참여 필수)
        """)
        

    # -----------------------------------------------
    # 3.3 분석 결과 표시
    # -----------------------------------------------
    if analyze_button or st.session_state['initial_run']:
        if st.session_state['initial_run']:
            st.session_state['initial_run'] = False 

        with st.spinner(f"'{entity_selection}'의 '{index_selection}' 지수를 계산 중입니다..."):
            
            analysis_df = analyze_hitmaker_index(movie_records, entity_selection, index_selection)
            
            if not analysis_df.empty:
                
                top_n = 10
                top_df = analysis_df.head(top_n).copy()
                
                st.subheader(f"🏆 Top {top_n} {entity_selection} 흥행 분석 ({index_selection})")
                st.markdown(f"**기준:** {index_selection} 지수 (내림차순 정렬)")
                
                # Plotly 막대 차트 시각화
                fig = px.bar(
                    top_df,
                    x='Sort_Index', # 정렬에 사용된 지수 값을 사용
                    y='Name',
                    orientation='h',
                    title=f"Top {top_n} {entity_selection} 흥행 지수 ({index_selection})",
                    color='Sort_Index',
                    color_continuous_scale=px.colors.sequential.Teal,
                    hover_data={
                        'Sort_Index': ':.0f',
                        'Name': True,
                        'Movie_Count': True
                    }
                ) 
                
                fig.update_layout(
                    xaxis_title=index_selection + " 지수 값",
                    yaxis_title=entity_selection,
                    height=500
                )
                st.plotly_chart(fig, use_container_width=True)

                # 데이터 테이블 표시를 위해 컬럼명을 정리
                display_df = top_df.rename(columns={
                    'Name': '이름',
                    'Movie_Count': '총 참여 영화 수',
                    'Non_Zero_Count': '흥행 기록 영화 수',
                    'Total_Audience': '총 관객 수 (명)',
                    'Efficiency_Index': '효율성 지수 (평균 관객 수)',
                    'Stability_Index': '안정성 지수',
                })[['이름', '총 참여 영화 수', '흥행 기록 영화 수', '총 관객 수 (명)', '효율성 지수 (평균 관객 수)', '안정성 지수']]
                
                st.dataframe(display_df, use_container_width=True, hide_index=True)
                
                st.markdown("---")
                st.subheader("🎬 상세 참여 영화 목록")
                
                # 상세 영화 목록을 표시하는 부분
                for index, row in top_df.iterrows():
                    name = row['Name']
                    movie_list = row['Movie_List'] 
                    
                    with st.expander(f"**#{index}: {name} ({row['Movie_Count']}편, 흥행 성공률: {row['Non_Zero_Count'] / row['Movie_Count']:.1%})**", expanded=False):
                        if movie_list:
                            st.markdown("- " + "\n- ".join(movie_list))
                        else:
                            st.write("분석 기간 내 흥행 기록이 있는 참여 영화가 없습니다.")
                
            else:
                st.warning(f"분석 결과가 없습니다. 기준일에 흥행 기록이 있는 영화가 부족하거나, 설정된 개봉 연도 필터({start_year}년)와 일치하는 영화가 없습니다.")

if __name__ == "__main__":
    main()
