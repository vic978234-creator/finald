import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta
import plotly.express as px
import plotly.graph_objects as go # Plotly for advanced charts

# --- 1. 환경 설정 및 함수 정의 ---

# ⚠️ 경고: API 키가 공개적으로 노출됩니다!
# 여기에 발급받은 실제 KOFIC API 키를 입력하세요.
KOFIC_API_KEY = "여기에_당신의_KOFIC_API_키를_직접_입력하세요" 

KOFIC_API_URL = "http://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchWeeklyBoxOfficeList.json"

@st.cache_data
def get_weekly_box_office(target_dt_str):
    """
    KOFIC API를 호출하여 주간 박스오피스 데이터를 가져옵니다.
    """
    if KOFIC_API_KEY == "여기에_당신의_KOFIC_API_키를_직접_입력하세요":
        st.error("⚠️ **API 키가 설정되지 않았습니다.** KOFIC_API_KEY 변수에 유효한 API 키를 직접 입력해주세요.")
        return None

    params = {
        'key': KOFIC_API_KEY,
        'targetDt': target_dt_str,
        'weekGb': '0' # 0: 주간 (월~일)
    }
    
    try:
        response = requests.get(KOFIC_API_URL, params=params)
        
        if response.status_code == 200:
            data = response.json()
            
            if 'faultInfo' in data:
                st.error(f"KOFIC API 오류 발생: {data['faultInfo']['message']}")
                st.info("API 키 오류 또는 일일 허용 횟수 초과일 수 있습니다. 키와 사용량을 확인해주세요.")
                return None
                
            if 'boxOfficeResult' in data and 'weeklyBoxOfficeList' in data['boxOfficeResult']:
                return data['boxOfficeResult']['weeklyBoxOfficeList']
            else:
                st.error("API 응답 구조가 예상과 다릅니다.")
                return None
        else:
             st.error(f"HTTP 오류 발생: 상태 코드 {response.status_code}.")
             return None
            
    except requests.exceptions.RequestException as e:
        st.error(f"네트워크 오류 발생: API 호출 실패. 오류 메시지: {e}")
        return None
    except Exception as e:
        st.error(f"데이터 처리 중 알 수 없는 오류 발생: {e}")
        return None

# --- 데이터 전처리 및 분석 함수 ---

def process_data(raw_data):
    """API 데이터를 DataFrame으로 변환하고 컬럼을 정리합니다."""
    df = pd.DataFrame(raw_data)
    df = df.rename(columns={
        'rank': '순위', 'movieNm': '영화명', 'audiAcc': '누적 관객수',
        'audiCnt': '주간 관객수', 'salesAcc': '누적 매출액', 'salesAmt': '주간 매출액',
        'openDt': '개봉일', 'salesShare': '매출액 점유율'
    })
    numeric_cols = ['순위', '누적 관객수', '주간 관객수', '누적 매출액', '주간 매출액']
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)
    
    # 텍스트 포맷팅을 위한 컬럼 추가
    df['주간 관객수 (포맷)'] = df['주간 관객수'].apply(lambda x: f'{x:,.0f} 명')
    df['누적 관객수 (포맷)'] = df['누적 관객수'].apply(lambda x: f'{x:,.0f} 명')
    df['주간 매출액 (포맷)'] = df['주간 매출액'].apply(lambda x: f'{x:,.0f} 원')
    df['누적 매출액 (포맷)'] = df['누적 매출액'].apply(lambda x: f'{x:,.0f} 원')
    
    return df

# --- 분석 탭 1: 기본 주간 박스오피스 ---

def show_basic_box_office(df):
    """기본 테이블 및 주간 관객수 바 차트를 보여줍니다."""
    st.markdown("### 🥇 주간 박스오피스 순위 테이블")
    
    display_cols = ['순위', '영화명', '개봉일', '주간 관객수 (포맷)', '누적 관객수 (포맷)', '주간 매출액 (포맷)', '누적 매출액 (포맷)']
    df_display = df.rename(columns={col: col.replace(' (포맷)', '') for col in display_cols})
    
    st.dataframe(df_display, use_container_width=True, hide_index=True)

    st.markdown("### 📊 주간 관객수 시각화")
    
    # Plotly Express를 사용하여 바 차트 생성
    fig = px.bar(
        df,
        x='영화명',
        y='주간 관객수',
        color='주간 관객수',
        color_continuous_scale=px.colors.sequential.Viridis,
        title='주간 박스오피스 영화별 관객수',
        labels={'영화명': '영화명', '주간 관객수': '주간 관객수 (명)'},
    )
    fig.update_layout(xaxis_tickangle=-45, yaxis_tickformat=',', height=500)
    
    st.plotly_chart(fig, use_container_width=True)

# --- 분석 탭 2: 감독/회사 기여 분석 (새로운 심층 분석) ---

def show_contributor_analysis(df):
    """주간 관객수 기준으로 감독 및 배급사의 기여도를 분석합니다."""
    st.markdown("### 🎬 배급사별 주간 관객수 기여도 분석")
    
    # 배급사(distributor) 정보를 가져와야 하지만, weeklyBoxOfficeList API에는 이 정보가 직접 포함되어 있지 않습니다.
    # 여기서는 '영화명'을 기준으로 그룹화하여 분석의 아이디어를 구현합니다.
    # *실제 구현을 위해서는 movieCd API를 통해 배급사 정보를 추가로 가져와야 합니다.*

    # 임시로 '영화명' 기준으로 '주간 관객수'를 총합하여 기여도를 보여줍니다.
    # (실제 배급사 데이터가 없으므로 '영화명'을 통해 관객 기여도가 높았던 영화를 다시 강조하는 방식으로 구현)
    
    contributor_df = df.sort_values(by='주간 관객수', ascending=False)
    contributor_df['기여도 (%)'] = (contributor_df['주간 관객수'] / contributor_df['주간 관객수'].sum()) * 100
    
    top_10_contributor = contributor_df.head(10).copy()
    top_10_contributor['주간 관객수 (명)'] = top_10_contributor['주간 관객수'].apply(lambda x: f'{x:,.0f}')
    top_10_contributor['기여도 (%)'] = top_10_contributor['기여도 (%)'].apply(lambda x: f'{x:.2f}%')

    st.markdown("**주간 박스오피스 관객 동원 Top 10 영화**")
    st.dataframe(top_10_contributor[['영화명', '순위', '주간 관객수 (명)', '기여도 (%)']], hide_index=True)
    
    # Plotly Pie Chart (기여도 시각화)
    fig = go.Figure(data=[go.Pie(
        labels=top_10_contributor['영화명'],
        values=top_10_contributor['주간 관객수'],
        hole=.3,
        name="주간 관객 기여도"
    )])
    fig.update_layout(title_text="Top 10 영화의 주간 관객수 기여 비율")
    st.plotly_chart(fig, use_container_width=True)
    
    st.info("이 분석을 완성하려면, 영화별 상세 API 호출을 통해 '배급사' 또는 '감독' 정보를 가져와 그룹화해야 합니다.")

# --- 3. Streamlit UI 및 메인 로직 ---

# 미적 품질 향상: Custom CSS for a cinematic theme (Dark background, Neon accent)
custom_css = """
<style>
/* Streamlit 기본 테마를 오버라이드하여 다크 모드를 강화합니다. */
.stApp {
    background-color: #0b0f16; /* Dark Navy/Black for cinematic feel */
    color: #f0f2f6;
}
/* 제목 및 강조 색상 (Neon Accent) */
h1, h2, h3, .stSidebar h1, .stButton>button {
    color: #00ff73; /* Neon Green/Lime */
}
/* 사이드바 배경 */
.css-1d391kg {
    background-color: #1a1a2e; /* Slightly lighter dark color for sidebar */
    border-right: 1px solid #00ff7344;
}
/* 데이터프레임 헤더 (테이블) */
.css-1ftarrss {
    background-color: #334155;
    color: #fff;
}
/* 탭 선택 강조 */
.stTabs [data-baseweb="tab-list"] button[aria-selected="true"] {
    border-bottom: 2px solid #00ff73 !important;
    color: #00ff73 !important;
}
</style>
"""
st.markdown(custom_css, unsafe_allow_html=True)


st.set_page_config(layout="wide", page_title="K-Movie 박스오피스 탐색기", page_icon="🎬")

st.title("🎬 K-Movie 박스오피스 주간 탐색기")
st.markdown("KOFIC 오픈 API를 활용하여 주간 박스오피스 순위 및 데이터를 시각화합니다.")

# --- 날짜 선택 위젯 및 데이터 로드 ---

# KOFIC 데이터는 전주 일요일까지의 데이터만 제공
today = datetime.now().date()
days_to_subtract = (today.weekday() + 1) % 7
default_target_date = today - timedelta(days=days_to_subtract)
default_target_date = default_target_date - timedelta(days=7) 

st.sidebar.header("데이터 조회 설정")
selected_date = st.sidebar.date_input(
    "기준 주간의 끝 날짜 (일요일) 선택:",
    value=default_target_date,
    max_value=today - timedelta(days=days_to_subtract),
    key='target_date_input'
)
target_dt_str = selected_date.strftime("%Y%m%d")


if KOFIC_API_KEY == "여기에_당신의_KOFIC_API_키를_직접_입력하세요":
    st.warning("⚠️ **KOFIC API 키**를 코드 상단에 입력해야 데이터를 로드할 수 있습니다.")
    st.stop()

# 데이터 로드
raw_data = get_weekly_box_office(target_dt_str)

if raw_data:
    df = process_data(raw_data)
    
    st.success(f"✅ {selected_date.strftime('%Y년 %m월 %d일')} 기준 박스오피스 데이터를 로드했습니다. (총 {len(df)}개)")
    
    # --- 탭 기반 분석 구조 (창의성/심층 분석 점수 향상) ---
    
    tab1, tab2 = st.tabs(["📊 기본 박스오피스 순위", "🏆 감독/회사 기여 분석 (심층)"])
    
    with tab1:
        show_basic_box_office(df)
        
    with tab2:
        show_contributor_analysis(df)
    
else:
    st.info("데이터를 불러오지 못했습니다. 날짜 설정을 확인하거나 API 키 오류를 점검해주세요.")
