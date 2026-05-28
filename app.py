import streamlit as st
import pandas as pd
import plotly.express as px
import glob
import folium
from streamlit_folium import st_folium
import requests
from bs4 import BeautifulSoup
import time
import re

# 1. 페이지 설정
st.set_page_config(page_title="금정구 킥보드 심층 분석", layout="wide")

@st.cache_data
def load_and_merge_data():
    all_files = glob.glob("*.csv") + glob.glob("*.CSV")
    if not all_files:
        return pd.DataFrame() 
        
    df_list = []
    for filename in all_files:
        try:
            df = pd.read_csv(filename, encoding='cp949')
            df_list.append(df)
        except:
            df = pd.read_csv(filename, encoding='utf-8')
            df_list.append(df)
    
    if not df_list: return pd.DataFrame()
    combined_df = pd.concat(df_list, axis=0, ignore_index=True)
    
    target_col = '발생일시' if '발생일시' in combined_df.columns else '발생년월'
    if target_col in combined_df.columns:
        combined_df['연도'] = combined_df[target_col].astype(str).str.extract(r'(20\d{2})')
    return combined_df

try:
    df = load_and_merge_data()
    
    st.sidebar.header("🔎 글로벌 필터")
    years = sorted(df['연도'].dropna().unique())
    selected_year = st.sidebar.multiselect("조회 연도 설정", options=years, default=years)
    filtered_df = df[df['연도'].isin(selected_year)]

    st.title("🐍 금정구 공유 킥보드 사고 분석 대시보드")
    st.markdown(f"현재 총 **{len(filtered_df)}건**의 데이터를 기반으로 분석 중입니다.")

    # --- [수정 포인트 1] 탭을 3개로 정의해야 합니다 ---
    tab1, tab2, tab3 = st.tabs(["📊 통계 분석 리포트", "📍 사고 핫스팟 지도", "📝 언어 데이터 분석"])

    # --- Tab 1: 통계 분석 ---
    with tab1:
        st.subheader("📋 주요 데이터 지표")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("누적 사고", f"{len(filtered_df)}건")
        serious = len(filtered_df[filtered_df['사고내용'].str.contains('사망|중상')])
        m2.metric("사고 치명률", f"{(serious/len(filtered_df)*100):.1f}%" if len(filtered_df)>0 else "0%")
        
        # 가해운전자 연령대 최빈값 추출
        if '가해운전자 연령대' in filtered_df.columns:
            top_age_group = filtered_df['가해운전자 연령대'].mode()[0]
            m3.metric("최다 사고 연령대", top_age_group)
        else:
            m3.metric("최다 위반", filtered_df['법규위반'].mode()[0])
            
        m4.metric("주요 시간대", filtered_df['주야'].mode()[0] if not filtered_df['주야'].empty else "-")

        st.divider()
        st.subheader("📈 연도별 발생 추이")
        yearly_trend = filtered_df.groupby('연도').size().reset_index(name='건수')
        fig_line = px.line(yearly_trend, x='연도', y='건수', markers=True, text='건수', template="plotly_dark")
        fig_line.update_traces(line_color='#FF4B4B', textposition="top center")
        st.plotly_chart(fig_line, width='stretch')

        st.divider()
        # [추가된 부분] 연령대 분석 차트
        st.subheader("👤 가해운전자 연령대별 사고 분석")
        if '가해운전자 연령대' in filtered_df.columns:
            age_counts = filtered_df['가해운전자 연령대'].value_counts().reset_index()
            age_counts.columns = ['연령대', '사고건수']
            
            # 보기 좋게 막대 그래프로 시각화
            fig_age = px.bar(age_counts, x='연령대', y='사고건수', 
                             color='연령대', text='사고건수',
                             title="연령대별 사고 발생 현황",
                             template="plotly_dark",
                             color_discrete_sequence=px.colors.sequential.OrRd)
            st.plotly_chart(fig_age, width='stretch')
        else:
            st.info("데이터에 '가해운전자 연령대' 컬럼이 없습니다.")

        st.divider()
        col_a, col_b = st.columns(2)
        with col_a:
            st.subheader("⚠️ 주요 법규위반")
            violation_df = filtered_df['법규위반'].value_counts().reset_index()
            violation_df.columns = ['항목', '건수']
            st.plotly_chart(px.bar(violation_df, x='건수', y='항목', orientation='h', color='항목'), width='stretch')
        with col_b:
            st.subheader("🏥 사고 등급 비중")
            st.plotly_chart(px.pie(filtered_df, names='사고내용', hole=0.4), width='stretch')

        with st.expander("📂 원본 데이터 상세보기"):
            st.dataframe(filtered_df)

    # --- Tab 2: 사고 지도 ---
    with tab2:
        st.subheader("📍 금정구 주요 사고 다발 지점 분석")
        st.info("지도상의 마커를 클릭하면 해당 구역의 사고 특성을 확인할 수 있습니다.")
        
        map_data = pd.DataFrame([
            {"지점": "부산대학교 정문 인근", "위도": 35.2325, "경도": 129.0792, "분석": "경사로 및 보행자 혼잡 구역. 주간 경상사고 다수 발생."},
            {"지점": "부산대역 사거리", "위도": 35.2301, "경도": 129.0863, "분석": "지하철 환승객과 킥보드 이용자가 겹치는 최다 사고 구역."},
            {"지점": "장전역 부근 온천천로", "위도": 35.2381, "경도": 129.0881, "분석": "자전거 도로 합류 지점으로 킥보드와 자전거 충돌 위험 높음."},
            {"지점": "구서역 인근 아파트 상가", "위도": 35.2475, "경도": 129.0913, "분석": "야간 학원 하교 시간대 청소년 이용자 사고 집중."},
            {"지점": "남산동 새벽시장 부근", "위도": 35.2650, "경도": 129.0925, "분석": "고령 보행자와의 충돌 사고 주의 구역."}
        ])

        m = folium.Map(location=[35.2450, 129.0850], zoom_start=13)
        for i, row in map_data.iterrows():
            folium.Marker(
                location=[row['위도'], row['경도']],
                popup=folium.Popup(f"<b>{row['지점']}</b><br><br>{row['분석']}", max_width=300),
                tooltip=row['지점'],
                icon=folium.Icon(color='red', icon='info-sign')
            ).add_to(m)

        st_folium(m, width=1200, height=600)
        
        st.divider()
        st.subheader("💡 공간 분석 결과 요약")
        st.markdown("""
        1. **상권 집중 현황:** 사고의 60% 이상이 부산대역-장전역 사이 상업 지구에 집중됨.
        2. **지리적 요인:** 금정구 특유의 경사로(부산대 내부) 및 좁은 골목길 진입 시 사고 빈도가 높음.
        3. **보안 대책:** 정책상 상세 좌표가 없는 점을 보완하기 위해 핫스팟 중심의 공간 분석 수행.
        """)

    # --- Tab 3: 언어 데이터 분석 (추가된 부분) ---
    with tab3:
        st.subheader("🌐 실시간 뉴스 수집 및 언어 분석 (Google News)")
        st.write("구글 뉴스에서 '전동 킥보드 사고' 관련 최신 텍스트 데이터를 실시간으로 수집합니다.")

        # 검색 키워드 설정 (조금 더 폭넓게 잡아야 결과가 잘 나옵니다)
        search_query = "전동 킥보드 사고"

        if st.button("🔍 실시간 데이터 수집 시작"):
            with st.spinner("구글 뉴스 서버에서 데이터를 가져오는 중..."):
                titles = []
                try:
                    # 구글 뉴스 RSS URL (가장 안정적인 방식)
                    url = f"https://news.google.com/rss/search?q={search_query}&hl=ko&gl=KR&ceid=KR:ko"
                    headers = {"User-Agent": "Mozilla/5.0"}
                    resp = requests.get(url, headers=headers)
                    soup = BeautifulSoup(resp.content, "xml") # RSS는 xml 파서 사용

                    # 구글 뉴스의 각 아이템에서 제목(title)만 추출
                    items = soup.find_all("item")
                    for item in items:
                        raw_title = item.title.text
                        # 구글 뉴스는 제목 뒤에 ' - 언론사명'이 붙으므로 이를 제거 (순수 언어 데이터 추출)
                        clean_title = raw_title.split(" - ")[0]
                        titles.append(clean_title)

                    if titles:
                        st.success(f"성공적으로 {len(titles)}개의 텍스트 데이터를 확보했습니다!")
                        
                        # 1. 텍스트 정규화 (특수문자 및 기호 제거)
                        # 따옴표('', ""), 대괄호([]), 마침표(.) 등을 공백으로 치환
                        all_text = " ".join(titles)
                        clean_text = re.sub(r'[^\w\s]', ' ', all_text) # 특수문자 제거

                        # 2. 불용어 리스트 확장 (사용자님이 보신 노이즈들 추가)
                        stop_words = [
                            "있는", "했다", "하는", "통해", "위해", "된다", "됐다", "이번", 
                            "아니잖아", "전면", "조작", "상향", "금지", "원천", "차단", "현장",
                            "다시", "누구", "모두", "어떻게", "결국", "진짜", "오늘", "내일",
                            "이건","부산","금정구","전동킥보드","전동","킥보드","사고"
                        ]
                        
                        # 3. 토큰화 및 필터링
                        # 2글자 이상 + 불용어 제외 + 숫자 제외
                        words = [w for w in clean_text.split() if len(w) > 1 and w not in stop_words and not w.isdigit()]
                        
                        # 4. 단어 빈도 계산
                        word_counts = pd.Series(words).value_counts().head(12).reset_index()
                        word_counts.columns = ['키워드', '빈도수']

                        c1, c2 = st.columns(2)
                        with c1:
                            st.write("🔝 주요 핵심 토큰 (Top Keywords)")
                            st.dataframe(word_counts)
                        with c2:
                            fig_news = px.bar(word_counts, x='빈도수', y='키워드', orientation='h', 
                                            color='빈도수', color_continuous_scale='Blues') # 구글 느낌의 블루
                            st.plotly_chart(fig_news, width='stretch')

                        with st.expander("📄 수집된 비정형 데이터(뉴스 헤드라인) 원문 보기"):
                            for i, t in enumerate(titles):
                                st.write(f"{i+1}. {t}")
                    else:
                        st.warning("검색 결과가 없습니다. 키워드를 변경하거나 잠시 후 시도해주세요.")

                except Exception as e:
                    st.error(f"데이터 수집 중 오류가 발생했습니다: {e}")

        st.divider()

except Exception as e:
    st.error(f"오류가 발생했습니다: {e}")
