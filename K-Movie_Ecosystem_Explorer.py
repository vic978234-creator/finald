import streamlit as st
import pandas as pd
import requests
from operator import itemgetter
from datetime import datetime, timedelta

# ===============================================
# 1. 환경 설정 및 데이터 정의 (KOBIS API 사용)
# ===============================================

# --- API KEY ---
# 실제 발급받은 KOBIS API 키를 여기에 입력하세요. (32자리 문자열)
KOBIS_API_KEY = "YOUR_KOBIS_API_KEY_HERE" # <--- 이 부분을 실제 키로 교체해야 합니다.

# --- API URLS ---
# 1. 영화 목록 API: 영화 코드(movieCd)와 기본 정보를 가져옵니다.
LIST_URL = "http://www.kobis.or.kr/kobisopenapi/webservice/rest/movie/searchMovieList.json"
# 2. 영화 상세 정보 API: 누적 관객 수(audiAcc) 등 상세 정보를 가져옵니다.
DETAIL_URL = "http://www.kobis.or.kr/kobisopenapi/webservice/rest/movie/searchMovieInfo.json"

# ===============================================
# 2. 데이터 처리 및 큐레이션 로직 (2단계 API 호출)
# ===============================================

# st.cache_data를 사용하여 API 호출 결과를 캐시하여 재실행 시 속도를 높입니다.
@st.cache_data(show_spinner="🎬 1단계: 영화 목록을 불러오는 중...")
def fetch_movie_list(api_key):
    """
    KOBIS 영화 목록 API를 호출하여 영화 코드 리스트를 가져옵니다.
    """
    if api_key == "YOUR_KOBIS_API_KEY_HERE":
        st.error("🚨 KOBIS API 키를 'KOBIS_API_KEY' 변수에 입력해야 실제 데이터를 가져올 수 있습니다. 현재는 API 호출을 건너낍니다.")
        return None
        
    params = {
        'key': api_key,
        'itemPerPage': 100, # 최대 100개의 영화를 가져옵니다.
        # 'prdtYear': datetime.now().year # 필요하다면 특정 연도로 필터링 가능
    }
    
    try:
        response = requests.get(LIST_URL, params=params, timeout=10)
        response.raise_for_status() 
        data = response.json()
        
        movie_list = data.get('movieListResult', {}).get('movieList', [])
        
        if not movie_list:
            st.warning("⚠️ 영화 목록 데이터를 찾을 수 없습니다.")
            return None
            
        st.success(f"1단계 완료: 총 {len(movie_list)}개의 영화 코드를 성공적으로 가져왔습니다.")
        return movie_list

    except requests.exceptions.RequestException as e:
        st.error(f"❌ 1단계 API 요청 중 오류 발생: {e}")
        return None

def fetch_movie_details(api_key, movie_code):
    """
    KOBIS 영화 상세 정보 API를 호출하여 누적 관객 수를 포함한 상세 정보를 가져옵니다.
    """
    params = {
        'key': api_key,
        'movieCd': movie_code # 영화 목록에서 가져온 영화 코드를 사용
    }
    
    try:
        response = requests.get(DETAIL_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        # 'movieInfo' 필드 안에 실제 영화 상세 정보가 담겨 있습니다.
        movie_info = data.get('movieInfoResult', {}).get('movieInfo', {})
        
        return movie_info

    except requests.exceptions.RequestException:
        # 상세 정보 조회에 실패해도 전체 앱이 멈추지 않도록 처리합니다.
        return None

# 이 함수는 @st.cache_data를 사용하지 않습니다. 1단계 함수만 캐시하여 
# API 키 변경이나 Streamlit 재실행 시 1단계 호출만 반복되도록 합니다.
def get_curated_movie_list(api_key):
    """
    2단계 API 호출을 통해 관객 수 정보를 포함한 최종 큐레이션 리스트를 생성하고 정렬합니다.
    """
    movie_list_data = fetch_movie_list(api_key)
    
    if movie_list_data is None:
        return pd.DataFrame() # 데이터가 없으면 빈 DataFrame 반환
    
    st.markdown("---")
    st.subheader("🎬 2단계: 상세 정보 및 누적 관객 수 확인 중...")

    # 프로그레스 바를 표시하여 사용자에게 진행 상황을 알립니다.
    progress_bar = st.progress(0, text="영화 상세 정보 (누적 관객수)를 확인 중입니다...")
    
    final_curated_list = []
    total_movies = len(movie_list_data)
    
    for i, movie in enumerate(movie_list_data):
        movie_code = movie['movieCd']
        
        # 2단계 호출: 영화 상세 정보 가져오기
        detail_info = fetch_movie_details(api_key, movie_code)
        
        if detail_info:
            # 관객수 정보 추출 (누적 관객수 또는 0)
            audience_count = 0
            if detail_info.get('audiCnt'):
                # audiCnt 필드는 "123,456" 형태일 수 있으므로, 콤마를 제거하고 정수로 변환합니다.
                try:
                    audience_count = int(detail_info['audiCnt'].replace(',', ''))
                except ValueError:
                    # 숫자가 아닌 값이 포함된 경우 0으로 처리
                    audience_count = 0 
            
            # 감독 이름 추출 (여러 명일 경우 쉼표로 연결)
            directors = ", ".join([d['peopleNm'] for d in detail_info.get('directors', [])])
            
            # 장르 이름 추출
            genres = ", ".join([g['genreNm'] for g in detail_info.get('genres', [])])
            
            # 최종 리스트에 추가할 데이터 구성
            final_curated_list.append({
                'movieNm': movie['movieNm'],
                'audiCnt': audience_count,
                'director': directors if directors else '정보 없음',
                'genre': genres if genres else '정보 없음',
                'openDt': detail_info.get('openDt', '정보 없음'),
            })

        # 프로그레스 바 업데이트
        progress_percentage = (i + 1) / total_movies
        progress_bar.progress(progress_percentage)
        
    progress_bar.empty() # 작업 완료 후 프로그레스 바 제거

    if not final_curated_list:
        st.warning("⚠️ 상세 정보를 가져온 영화가 없습니다. API 키를 확인하거나 KOBIS API 상태를 확인해 보세요.")
        return pd.DataFrame()
        
    # 3. 데이터를 'audiCnt' 기준으로 오름차순 정렬 (Lowest to Highest)
    sorted_movies = sorted(final_curated_list, key=itemgetter('audiCnt'))
    
    # 4. 정렬된 리스트에 'rank' (순위/번호)를 부여하고 DataFrame으로 변환
    final_with_rank = []
    for i, movie in enumerate(sorted_movies):
        movie_data = movie.copy()
        movie_data['rank'] = i + 1
        final_with_rank.append(movie_data)
        
    df = pd.DataFrame(final_with_rank)
    
    st.success(f"2단계 완료: 총 {len(df)}개의 영화가 관객 수 오름차순으로 큐레이션 되었습니다.")
    
    return df

# ===============================================
# 3. Streamlit 앱 레이아웃 및 기능 구현
# ===============================================

def main():
    """Streamlit 앱의 메인 함수"""
    
    st.set_page_config(
        page_title="K-Movie List Curator (Advanced)",
        layout="centered",
        initial_sidebar_state="auto"
    )

    st.title("🎬 K-Movie List Curator (고급 버전: 영화 목록 API)")
    st.markdown("---")
    
    st.markdown("""
        이 앱은 **KOBIS 영화 목록 API** (1단계)와 **영화 상세 정보 API** (2단계)를
        순차적으로 호출하여 데이터를 가져온 후, **누적 관객 수 오름차순**으로 정렬합니다.
        가장 적은 누적 관객 수의 영화가 **1번**입니다.
    """)

    # 큐레이션된 영화 리스트 로드 (API 키를 인자로 사용)
    movie_df = get_curated_movie_list(KOBIS_API_KEY)
    
    # [수정된 부분] movie_df가 None일 가능성을 명시적으로 처리하여 AttributeError를 방지합니다.
    if movie_df is None or movie_df.empty: 
        st.stop()
        
    total_movies = len(movie_df)

    # -----------------------------------------------
    # 3.1 사용자 입력 인터페이스
    # -----------------------------------------------
    
    st.header("🔍 관객 수 순위로 검색")
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        rank_input = st.number_input(
            f"검색할 순위 번호를 입력하세요 (1 ~ {total_movies}):",
            min_value=1,
            max_value=total_movies,
            value=1,
            step=1,
            format="%d",
            help="1위는 누적 관객 수가 가장 적은 영화입니다."
        )

    with col2:
        st.write(" ")
        search_button = st.button("영화 검색", use_container_width=True)


    # -----------------------------------------------
    # 3.2 검색 결과 표시
    # -----------------------------------------------

    if search_button:
        if 1 <= rank_input <= total_movies:
            # 해당 순위에 맞는 영화 정보 추출
            selected_movie_data = movie_df[movie_df['rank'] == rank_input].iloc[0]
            
            # 관객수를 보기 좋게 포맷팅
            formatted_audiCnt = f"{selected_movie_data['audiCnt']:,} 명"
            
            st.markdown("---")
            st.subheader(f"✅ 순위 #{rank_input} 영화 정보")
            
            with st.container(border=True):
                
                # 제목 및 감독
                st.markdown(f"**<span style='font-size: 1.8em; color: #3B82F6;'>{selected_movie_data['movieNm']}</span>**", unsafe_allow_html=True)
                
                # 메타데이터 (관객수, 감독, 장르, 개봉일)
                st.markdown("---")
                st.markdown(f"**관객 수 오름차순 순위:** <span style='color: #E63946; font-weight: bold;'>#{selected_movie_data['rank']}</span>", unsafe_allow_html=True)
                st.markdown(f"**누적 관객 수:** {formatted_audiCnt}")
                st.markdown(f"**감독:** {selected_movie_data['director']}")
                st.markdown(f"**장르:** {selected_movie_data['genre']}")
                st.markdown(f"**개봉일:** {selected_movie_data['openDt']}")
                
        else:
            st.error("유효한 순위 번호를 입력해 주세요.")

    # -----------------------------------------------
    # 3.3 전체 목록 미리보기
    # -----------------------------------------------

    st.markdown("---")
    st.header("📚 전체 큐레이션 목록 미리보기")
    st.caption(f"총 {total_movies}개 영화. 누적 관객 수 오름차순 정렬 (1위: 관객 수가 가장 적은 영화)")
    
    # 필요한 컬럼만 선택하여 미리보기
    preview_df = movie_df[['rank', 'movieNm', 'audiCnt', 'director', 'genre']]
    
    # 컬럼 이름 변경 (가독성 향상)
    preview_df.columns = ['순위', '영화 제목', '누적 관객 수', '감독', '장르']
    
    st.dataframe(preview_df, use_container_width=True, hide_index=True)


if __name__ == "__main__":
    main()
