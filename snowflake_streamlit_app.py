import streamlit as st
import pandas as pd
from snowflake.snowpark.context import get_active_session
import altair as alt
from datetime import date, timedelta
import calendar

st.set_page_config(layout="wide", page_title="영업현황 대시보드")

st.markdown("""
<style>
[data-testid="stAppViewContainer"] { background: #ffffff; }
[data-testid="stSidebar"] { background: #f8f9fa; }
[data-testid="stHeader"] { background: #ffffff; }
.kpi-card {
    background: #f0f2f6; border-radius: 8px; padding: 16px 12px;
    text-align: center; border: 1px solid #e0e0e0; margin-bottom: 8px;
}
.kpi-label   { color: #555555; font-size: 11px; margin-bottom: 6px; }
.kpi-value   { color: #1a1a1a; font-size: 22px; font-weight: 700; }
.kpi-value-lg{ color: #1a1a1a; font-size: 17px; font-weight: 700; }
.kpi-up      { color: #e03131; font-size: 11px; margin-top: 4px; }
.kpi-down    { color: #1971c2; font-size: 11px; margin-top: 4px; }
.kpi-neutral { color: #999999; font-size: 11px; margin-top: 4px; }
.section-title {
    color: #222222; font-size: 13px; font-weight: 600;
    margin: 20px 0 10px 0; padding-bottom: 5px;
    border-bottom: 2px solid #e0e0e0;
}
.empty-box {
    background: #f8f9fa; border-radius: 6px; padding: 20px;
    text-align: center; color: #aaaaaa; font-size: 12px;
    border: 1px dashed #cccccc;
}
.criteria-box {
    background: #f8f9fa; border-radius: 6px; padding: 12px 16px;
    font-size: 12px; color: #444; border-left: 3px solid #4c78a8;
    margin-bottom: 12px;
}
</style>
""", unsafe_allow_html=True)

# ── 세션 / 상수 ──
session = get_active_session()

CHART_BG = "#f0f2f6"
AXIS_C   = "#333333"
GRID_C   = "#dddddd"
BAR_MAIN = "#4c78a8"

MANAGER_LIST = ['김경선','김미희','박순미','송민선','신영란','이선','이선이','정혜령','최현정']

CH_EXPR = """
    CASE
        WHEN cv.REGISTRATION_TYPE = 'RENEWAL'  THEN '갱신'
        WHEN ca.CHANNEL_PATH = 'INBOUND'        THEN 'CS'
        WHEN ca.CHANNEL_PATH = 'DEALER_APP'     THEN '딜러앱'
        ELSE '기타'
    END
"""

# G속성: business_type + business_sub_type 조합
# 신차딜러는 DOMESTIC(국산)/IMPORTED(수입)으로 세분화
G_ATTR_EXPR = """
    CASE
        WHEN u.BUSINESS_TYPE = 'USED_CAR_DEALER' THEN '중고차딜러'
        WHEN u.BUSINESS_TYPE = 'INSURANCE_AGENT' THEN '보험설계사'
        WHEN u.BUSINESS_TYPE = 'AGENCY'          THEN '에이전시'
        WHEN u.BUSINESS_TYPE = 'NEW_CAR_DEALER' AND u.BUSINESS_SUB_TYPE = 'DOMESTIC'  THEN '신차딜러(국산)'
        WHEN u.BUSINESS_TYPE = 'NEW_CAR_DEALER' AND u.BUSINESS_SUB_TYPE = 'IMPORTED'  THEN '신차딜러(수입)'
        WHEN u.BUSINESS_TYPE = 'NEW_CAR_DEALER' THEN '신차딜러'
        ELSE '미분류'
    END
"""

USER_FILTER = "IS_ASSOCIATE = 0 AND USER_NAME NOT LIKE '%테스트%'"

# ── 날짜 계산 ──
today            = date.today()
this_month_start = today.replace(day=1)
last_month_end   = this_month_start - timedelta(days=1)
last_month_start = last_month_end.replace(day=1)
# ValueError 방지: 전월에 today.day가 없을 수 있음 (e.g. 7/31 → 6월은 30일까지)
same_period_end  = min(last_month_end,
                       last_month_start.replace(day=min(today.day, last_month_end.day)))


def apply_theme(chart):
    return (
        chart
        .configure_view(fill=CHART_BG, stroke=None)
        .configure_axis(
            labelColor=AXIS_C, titleColor=AXIS_C,
            gridColor=GRID_C, domainColor="#cccccc",
            labelFontSize=11, titleFontSize=11
        )
        .configure_legend(
            labelColor=AXIS_C, titleColor=AXIS_C,
            labelFontSize=11, titleFontSize=11,
            fillColor=CHART_BG, strokeColor="#e0e0e0"
        )
        .configure_title(color=AXIS_C)
    )


def fmt_won(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "-"
    v = int(v)
    if abs(v) >= 100_000_000:
        return f"{v/100_000_000:.1f}억"
    if abs(v) >= 10_000:
        return f"{v/10_000:.0f}만"
    return f"{v:,}"


def fmt_won_full(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "-"
    return f"{int(v):,}원"


def kpi_card(label, value, delta=None, delta_type="neutral"):
    delta_html = ""
    if delta is not None:
        cls = f"kpi-{delta_type}"
        delta_html = f'<div class="{cls}">{delta}</div>'
    return f"""
    <div class="kpi-card">
        <div class="kpi-label">{label}</div>
        <div class="kpi-value">{value}</div>
        {delta_html}
    </div>"""


st.title("영업현황 대시보드")

# ════════════════════════════════════
# 탭 구성
# ════════════════════════════════════
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 영업현황",
    "🏢 보험사별 현황",
    "❌ 취소건 현황",
    "💤 비활동 딜러 현황",
    "🔍 비견건수"
])

# ════════════════════════════════════════════════════════════════
# TAB 1 — 영업현황
# ════════════════════════════════════════════════════════════════
with tab1:

    st.markdown('<div class="section-title">실시간 지표</div>', unsafe_allow_html=True)

    @st.cache_data(ttl=300)
    def get_kpi_premium():
        # COUNSEL_STATUS: JOIN_COMPLETED + COMPARISON_COMPLETED 모두 포함
        r = session.sql(f"""
            SELECT
                SUM(CASE WHEN DATE_TRUNC('MONTH', ca.JOIN_COMPLETED_AT) = DATE_TRUNC('MONTH', CURRENT_DATE)
                         THEN cv.CONTRACT_AMOUNT ELSE 0 END) AS cur_month,
                SUM(CASE WHEN ca.JOIN_COMPLETED_AT::DATE BETWEEN '{last_month_start}' AND '{same_period_end}'
                         THEN cv.CONTRACT_AMOUNT ELSE 0 END) AS last_same
            FROM AJDCAR_PROD.PUBLIC.COUNSEL_APPLICATION ca
            LEFT JOIN AJDCAR_PROD.PUBLIC.COUNSEL_VEHICLE cv
                ON ca.COUNSEL_ID = cv.COUNSEL_ID
                AND (cv.IS_DELETED = FALSE OR cv.IS_DELETED IS NULL)
            WHERE ca.COUNSEL_STATUS IN ('JOIN_COMPLETED', 'COMPARISON_COMPLETED')
              AND ca.JOIN_COMPLETED_AT IS NOT NULL
              AND (ca.IS_DELETED = FALSE OR ca.IS_DELETED IS NULL)
        """).collect()
        return r[0]

    @st.cache_data(ttl=300)
    def get_kpi_users():
        r = session.sql(f"""
            SELECT
                COUNT(CASE WHEN DATE_TRUNC('MONTH', CREATED_AT) = DATE_TRUNC('MONTH', CURRENT_DATE)
                           THEN 1 END) AS this_month,
                COUNT(*) AS total
            FROM AJDCAR_PROD.PUBLIC.USERS
            WHERE {USER_FILTER}
        """).collect()
        return r[0]

    @st.cache_data(ttl=300)
    def get_kpi_active_dealer():
        r = session.sql(f"""
            SELECT COUNT(DISTINCT ca.USER_ID) AS active_60
            FROM AJDCAR_PROD.PUBLIC.COUNSEL_APPLICATION ca
            JOIN AJDCAR_PROD.PUBLIC.USERS u ON ca.USER_ID = u.ID
            WHERE ca.COUNSEL_STATUS IN ('JOIN_COMPLETED', 'COMPARISON_COMPLETED')
              AND ca.JOIN_COMPLETED_AT >= DATEADD('DAY', -60, CURRENT_DATE)
              AND (ca.IS_DELETED = FALSE OR ca.IS_DELETED IS NULL)
              AND u.IS_ASSOCIATE = 0
              AND u.USER_NAME NOT LIKE '%테스트%'
        """).collect()
        total_r = session.sql(f"""
            SELECT COUNT(*) AS total_dealer
            FROM AJDCAR_PROD.PUBLIC.USERS
            WHERE {USER_FILTER}
        """).collect()
        active = r[0]["ACTIVE_60"]
        total  = total_r[0]["TOTAL_DEALER"]
        rate   = (active / total * 100) if total else 0
        return active, total, rate

    kpi_prem = get_kpi_premium()
    kpi_usr  = get_kpi_users()
    active60, total_users, active_rate = get_kpi_active_dealer()

    cur = kpi_prem["CUR_MONTH"] or 0
    lst = kpi_prem["LAST_SAME"] or 0
    if lst > 0:
        pct      = (cur - lst) / lst * 100
        diff_amt = cur - lst
        pct_txt  = f"전월동기 대비 {'+' if pct>=0 else ''}{pct:.1f}%"
        amt_txt  = f"({'+' if diff_amt>=0 else ''}{fmt_won_full(diff_amt)})"
        d_type   = "up" if pct >= 0 else "down"
        delta_lines = f'<div class="kpi-{d_type}">{pct_txt}</div><div class="kpi-{d_type}">{amt_txt}</div>'
    else:
        delta_lines = '<div class="kpi-neutral">전월동기 데이터 없음</div>'

    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-label">당월 총 원수보험료</div>
            <div class="kpi-value">{fmt_won_full(cur)}</div>
            {delta_lines}
        </div>""", unsafe_allow_html=True)
    with col2:
        st.markdown(kpi_card("당월 앱 가입자수", f"{kpi_usr['THIS_MONTH']:,}명"), unsafe_allow_html=True)
    with col3:
        st.markdown(kpi_card("누적 앱 가입자수", f"{kpi_usr['TOTAL']:,}명"), unsafe_allow_html=True)

    col4, col5, col6 = st.columns(3)
    with col4:
        st.markdown(kpi_card("직전 60일 활동딜러", f"{active60:,}명"), unsafe_allow_html=True)
    with col5:
        st.markdown(kpi_card("활동률", f"{active_rate:.1f}%", f"전체 {total_users:,}명 중"), unsafe_allow_html=True)
    with col6:
        st.markdown('<div class="kpi-card"><div class="kpi-label">오프영업팀 가입건</div><div class="kpi-value-lg" style="color:#aaa;">-</div><div class="kpi-neutral">데이터 준비중</div></div>', unsafe_allow_html=True)

    # ── 앱 가입현황 G속성별 ──
    st.markdown('<div class="section-title">앱 가입현황 (딜러 G속성별)</div>', unsafe_allow_html=True)
    st.markdown('<div class="criteria-box">📌 G속성 기준: USERS.business_type (USED_CAR_DEALER/INSURANCE_AGENT/AGENCY/NEW_CAR_DEALER) + business_sub_type (DOMESTIC/IMPORTED) 조합으로 분류</div>', unsafe_allow_html=True)

    @st.cache_data(ttl=300)
    def get_g_attr_signup():
        df = session.sql(f"""
            SELECT
                {G_ATTR_EXPR} AS "G속성",
                COUNT(*) AS "총가입수",
                COUNT(CASE WHEN DATE_TRUNC('MONTH', CREATED_AT) = DATE_TRUNC('MONTH', CURRENT_DATE)
                           THEN 1 END) AS "당월가입"
            FROM AJDCAR_PROD.PUBLIC.USERS u
            WHERE {USER_FILTER}
            GROUP BY 1
            ORDER BY 2 DESC
        """).to_pandas()
        df.columns = ["G속성", "총가입수", "당월가입"]
        return df

    df_g = get_g_attr_signup()
    if not df_g.empty:
        g_cols = st.columns(len(df_g))
        for i, row in df_g.iterrows():
            with g_cols[i]:
                st.markdown(kpi_card(
                    row["G속성"],
                    f"{int(row['총가입수']):,}명",
                    f"당월 {int(row['당월가입']):,}명",
                    "neutral"
                ), unsafe_allow_html=True)
    else:
        st.info("데이터 없음")

    # ── 계약체결 구간별 딜러 분포 ──
    st.markdown('<div class="section-title">계약체결 구간별 딜러 분포</div>', unsafe_allow_html=True)

    DIST_ORDER = ["1건", "2건", "3건", "4~6건", "7건 이상"]

    @st.cache_data(ttl=300)
    def get_dealer_dist(days):
        df = session.sql(f"""
            WITH dealer_cnt AS (
                SELECT ca.USER_ID, COUNT(*) AS cnt
                FROM AJDCAR_PROD.PUBLIC.COUNSEL_APPLICATION ca
                JOIN AJDCAR_PROD.PUBLIC.USERS u ON ca.USER_ID = u.ID
                WHERE ca.COUNSEL_STATUS IN ('JOIN_COMPLETED', 'COMPARISON_COMPLETED')
                  AND ca.JOIN_COMPLETED_AT >= DATEADD('DAY', -{days}, CURRENT_DATE)
                  AND (ca.IS_DELETED = FALSE OR ca.IS_DELETED IS NULL)
                  AND u.IS_ASSOCIATE = 0
                  AND u.USER_NAME NOT LIKE '%테스트%'
                GROUP BY 1
            )
            SELECT
                CASE
                    WHEN cnt = 1  THEN '1건'
                    WHEN cnt = 2  THEN '2건'
                    WHEN cnt = 3  THEN '3건'
                    WHEN cnt <= 6 THEN '4~6건'
                    ELSE '7건 이상'
                END AS "구간",
                COUNT(*) AS "딜러수",
                SUM(cnt)  AS "체결건수"
            FROM dealer_cnt
            GROUP BY 1
            ORDER BY MIN(cnt)
        """).to_pandas()
        df.columns = ["구간", "딜러수", "체결건수"]
        df["구간"] = pd.Categorical(df["구간"], categories=DIST_ORDER, ordered=True)
        df = df.sort_values("구간").reset_index(drop=True)
        return df

    dcol1, dcol2 = st.columns(2)
    with dcol1:
        st.caption("직전 60일 딜러 분포")
        df60 = get_dealer_dist(60)
        if not df60.empty:
            st.dataframe(
                df60,
                column_config={
                    "구간":    st.column_config.TextColumn("체결건수 구간", width="small"),
                    "딜러수":  st.column_config.ProgressColumn("딜러수", min_value=0,
                                max_value=int(df60["딜러수"].max()), format="%d"),
                    "체결건수": st.column_config.ProgressColumn("체결건수", min_value=0,
                                max_value=int(df60["체결건수"].max()), format="%d"),
                },
                hide_index=True, use_container_width=True
            )
        else:
            st.info("데이터 없음")

    with dcol2:
        st.caption("직전 90일 딜러 분포")
        df90 = get_dealer_dist(90)
        if not df90.empty:
            st.dataframe(
                df90,
                column_config={
                    "구간":    st.column_config.TextColumn("체결건수 구간", width="small"),
                    "딜러수":  st.column_config.ProgressColumn("딜러수", min_value=0,
                                max_value=int(df90["딜러수"].max()), format="%d"),
                    "체결건수": st.column_config.ProgressColumn("체결건수", min_value=0,
                                max_value=int(df90["체결건수"].max()), format="%d"),
                },
                hide_index=True, use_container_width=True
            )
        else:
            st.info("데이터 없음")

    # ── 추이 차트 ──
    st.markdown('<div class="section-title">추이 차트</div>', unsafe_allow_html=True)
    ch_left, ch_right = st.columns(2)

    with ch_left:
        st.caption("직전 50일 일별 총 원수보험료")

        @st.cache_data(ttl=300)
        def get_daily50():
            df = session.sql("""
                SELECT
                    DATE_TRUNC('DAY', ca.JOIN_COMPLETED_AT)::DATE AS "일자",
                    SUM(cv.CONTRACT_AMOUNT) AS "원수보험료"
                FROM AJDCAR_PROD.PUBLIC.COUNSEL_APPLICATION ca
                LEFT JOIN AJDCAR_PROD.PUBLIC.COUNSEL_VEHICLE cv
                    ON ca.COUNSEL_ID = cv.COUNSEL_ID
                    AND (cv.IS_DELETED = FALSE OR cv.IS_DELETED IS NULL)
                WHERE ca.COUNSEL_STATUS IN ('JOIN_COMPLETED', 'COMPARISON_COMPLETED')
                  AND ca.JOIN_COMPLETED_AT IS NOT NULL
                  AND DATE_TRUNC('DAY', ca.JOIN_COMPLETED_AT)::DATE
                      >= DATEADD('DAY', -50, CURRENT_DATE)
                GROUP BY 1 ORDER BY 1
            """).to_pandas()
            df.columns = ["일자", "원수보험료"]
            df["일자"] = pd.to_datetime(df["일자"])
            return df

        df50 = get_daily50()
        if not df50.empty:
            avg_val = df50["원수보험료"].mean()
            bar50 = alt.Chart(df50).mark_bar(color=BAR_MAIN, size=7).encode(
                x=alt.X("일자:T", title="일자",
                        axis=alt.Axis(format="%m/%d", labelAngle=-45, tickCount=10)),
                y=alt.Y("원수보험료:Q", title="원수보험료(원)", axis=alt.Axis(format=",.0f")),
                tooltip=[
                    alt.Tooltip("일자:T", title="날짜", format="%Y-%m-%d"),
                    alt.Tooltip("원수보험료:Q", title="원수보험료", format=",.0f")
                ]
            )
            avg_rule = alt.Chart(pd.DataFrame({"avg": [avg_val]})).mark_rule(
                color="#e03131", strokeDash=[4,3], strokeWidth=1.5
            ).encode(y="avg:Q")
            avg_text = alt.Chart(pd.DataFrame({
                "avg": [avg_val], "x": [df50["일자"].iloc[-1]],
                "lbl": [f"평균 {avg_val/10000:.0f}만"]
            })).mark_text(
                align="right", dx=-4, dy=-8, color="#e03131", fontSize=10
            ).encode(x="x:T", y="avg:Q", text="lbl:N")
            st.altair_chart(
                apply_theme((bar50 + avg_rule + avg_text).properties(height=260, background=CHART_BG)),
                use_container_width=True
            )
        else:
            st.info("데이터 없음")

    with ch_right:
        st.caption("월별/주차별 앱 가입현황")
        view_unit = st.radio("조회 단위", ["월별", "주차별"], horizontal=True, key="signup_unit")

        @st.cache_data(ttl=300)
        def get_signup(unit):
            if unit == "월별":
                sql = f"""
                    SELECT TO_CHAR(CREATED_AT, 'YYYY-MM') AS "기간_str",
                           COUNT(*) AS "가입수"
                    FROM AJDCAR_PROD.PUBLIC.USERS
                    WHERE CREATED_AT IS NOT NULL AND {USER_FILTER}
                    GROUP BY 1 ORDER BY 1 DESC
                """
            else:
                sql = f"""
                    SELECT TO_CHAR(DATE_TRUNC('WEEK', CREATED_AT), 'YYYY-MM-DD') AS "기간_str",
                           COUNT(*) AS "가입수"
                    FROM AJDCAR_PROD.PUBLIC.USERS
                    WHERE CREATED_AT IS NOT NULL AND {USER_FILTER}
                    GROUP BY 1 ORDER BY 1 DESC
                """
            df = session.sql(sql).to_pandas()
            df.columns = ["기간_str", "가입수"]
            return df

        df_sg = get_signup(view_unit)
        if not df_sg.empty:
            order = list(df_sg["기간_str"])
            bar_sg = alt.Chart(df_sg).mark_bar(color=BAR_MAIN).encode(
                x=alt.X("기간_str:N", title="기간", sort=order,
                        axis=alt.Axis(labelAngle=-45)),
                y=alt.Y("가입수:Q", title="가입수"),
                tooltip=[
                    alt.Tooltip("기간_str:N", title="기간"),
                    alt.Tooltip("가입수:Q", title="가입수", format=",")
                ]
            )
            lbl_sg = bar_sg.mark_text(dy=-6, fontSize=10, color="#333333").encode(
                text=alt.Text("가입수:Q", format=",")
            )
            st.altair_chart(
                apply_theme((bar_sg + lbl_sg).properties(height=260, background=CHART_BG)),
                use_container_width=True
            )
        else:
            st.info("데이터 없음")

    # ── 필터 섹션 ──
    st.markdown('<div class="section-title">상세 분석 (필터)</div>', unsafe_allow_html=True)

    f1, f2, f3, f4 = st.columns(4)
    with f1:
        date_from = st.date_input("시작일", value=date(today.year, today.month, 1))
    with f2:
        date_to = st.date_input("종료일", value=today)
    with f3:
        mgr_opts = ["전체"] + MANAGER_LIST
        sel_mgr  = st.selectbox("담당매니저", mgr_opts)
    with f4:
        ch_opts = ["전체", "갱신", "CS", "딜러앱", "기타"]
        sel_ch  = st.selectbox("영업채널", ch_opts)

    mgr_filter = "" if sel_mgr == "전체" else f"AND m.NAME = '{sel_mgr}'"
    ch_filter  = "" if sel_ch  == "전체" else f"AND {CH_EXPR} = '{sel_ch}'"

    # ── 체결월별 영업채널 원수보험료 ──
    st.markdown('<div class="section-title">체결월별 영업채널 원수보험료</div>', unsafe_allow_html=True)
    period_unit = st.radio("기간 단위", ["월별", "주차별"], horizontal=True, key="period_unit")

    @st.cache_data(ttl=300)
    def get_channel_premium(d_from, d_to, mgr_f, ch_f, unit):
        grp = "TO_CHAR(ca.JOIN_COMPLETED_AT, 'YYYY-MM')" if unit == "월별" \
              else "TO_CHAR(DATE_TRUNC('WEEK', ca.JOIN_COMPLETED_AT), 'YYYY-MM-DD')"
        df = session.sql(f"""
            SELECT
                {grp} AS "기간",
                {CH_EXPR} AS "채널",
                SUM(cv.CONTRACT_AMOUNT) AS "원수보험료"
            FROM AJDCAR_PROD.PUBLIC.COUNSEL_APPLICATION ca
            LEFT JOIN AJDCAR_PROD.PUBLIC.COUNSEL_VEHICLE cv
                ON ca.COUNSEL_ID = cv.COUNSEL_ID
                AND (cv.IS_DELETED = FALSE OR cv.IS_DELETED IS NULL)
            LEFT JOIN AJDCAR_PROD.PUBLIC.USERS u ON ca.USER_ID = u.ID
            LEFT JOIN AJDCAR_PROD.PUBLIC.MANAGER m ON ca.COUNSEL_MANAGER_ID = m.ID
            WHERE ca.COUNSEL_STATUS IN ('JOIN_COMPLETED', 'COMPARISON_COMPLETED')
              AND ca.JOIN_COMPLETED_AT IS NOT NULL
              AND ca.JOIN_COMPLETED_AT::DATE BETWEEN '{d_from}' AND '{d_to}'
              AND (m.NAME IS NULL OR m.NAME NOT LIKE '%테스트%')
              {mgr_f} {ch_f}
            GROUP BY 1,2 ORDER BY 1 DESC
        """).to_pandas()
        df.columns = ["기간", "채널", "원수보험료"]
        return df

    df_ch = get_channel_premium(date_from, date_to, mgr_filter, ch_filter, period_unit)
    if not df_ch.empty:
        order_ch = sorted(df_ch["기간"].unique(), reverse=True)
        totals_ch = df_ch.groupby("기간")["원수보험료"].sum().reset_index()
        totals_ch.columns = ["기간", "합계"]
        bar_ch = alt.Chart(df_ch).mark_bar().encode(
            x=alt.X("기간:N", sort=order_ch, title="기간", axis=alt.Axis(labelAngle=-45)),
            y=alt.Y("원수보험료:Q", title="원수보험료(원)", axis=alt.Axis(format=",.0f")),
            color=alt.Color("채널:N", legend=alt.Legend(title="채널")),
            tooltip=[alt.Tooltip("기간:N"), alt.Tooltip("채널:N"),
                     alt.Tooltip("원수보험료:Q", format=",.0f")]
        )
        lbl_ch = alt.Chart(totals_ch).mark_text(dy=-6, fontSize=10, color="#333333").encode(
            x=alt.X("기간:N", sort=order_ch),
            y=alt.Y("합계:Q"),
            text=alt.Text("합계:Q", format=",.0f")
        )
        st.altair_chart(
            apply_theme((bar_ch + lbl_ch).properties(height=280, background=CHART_BG)),
            use_container_width=True
        )
    else:
        st.info("데이터 없음")

    # ── 딜러 현황 ──
    st.markdown('<div class="section-title">딜러 현황</div>', unsafe_allow_html=True)
    dl1, dl2 = st.columns(2)

    with dl1:
        st.caption("체결월별 가동딜러수")

        @st.cache_data(ttl=300)
        def get_active_dealer_monthly(d_from, d_to, mgr_f):
            df = session.sql(f"""
                SELECT
                    TO_CHAR(ca.JOIN_COMPLETED_AT, 'YYYY-MM') AS "월",
                    COUNT(DISTINCT ca.USER_ID) AS "가동딜러수"
                FROM AJDCAR_PROD.PUBLIC.COUNSEL_APPLICATION ca
                LEFT JOIN AJDCAR_PROD.PUBLIC.MANAGER m ON ca.COUNSEL_MANAGER_ID = m.ID
                WHERE ca.COUNSEL_STATUS IN ('JOIN_COMPLETED', 'COMPARISON_COMPLETED')
                  AND ca.JOIN_COMPLETED_AT IS NOT NULL
                  AND (ca.IS_DELETED = FALSE OR ca.IS_DELETED IS NULL)
                  AND ca.JOIN_COMPLETED_AT::DATE BETWEEN '{d_from}' AND '{d_to}'
                  AND (m.NAME IS NULL OR m.NAME NOT LIKE '%테스트%')
                  {mgr_f}
                GROUP BY 1 ORDER BY 1 DESC
            """).to_pandas()
            df.columns = ["월", "가동딜러수"]
            return df

        df_adm = get_active_dealer_monthly(date_from, date_to, mgr_filter)
        if not df_adm.empty:
            order_adm = list(df_adm["월"])
            c = apply_theme(
                alt.Chart(df_adm).mark_bar(color="#6a9fd8").encode(
                    x=alt.X("월:N", sort=order_adm, title=None, axis=alt.Axis(labelAngle=-30)),
                    y=alt.Y("가동딜러수:Q", title="가동딜러수"),
                    tooltip=[alt.Tooltip("월:N"), alt.Tooltip("가동딜러수:Q", format=",")]
                ).properties(height=220, background=CHART_BG)
            )
            st.altair_chart(c, use_container_width=True)
        else:
            st.info("데이터 없음")

    with dl2:
        st.caption("G속성별 인당 원수보험료")

        @st.cache_data(ttl=300)
        def get_per_dealer(d_from, d_to):
            df = session.sql(f"""
                SELECT
                    {G_ATTR_EXPR} AS "G속성",
                    SUM(cv.CONTRACT_AMOUNT) / NULLIF(COUNT(DISTINCT ca.USER_ID), 0) AS "인당원수보험료"
                FROM AJDCAR_PROD.PUBLIC.COUNSEL_APPLICATION ca
                LEFT JOIN AJDCAR_PROD.PUBLIC.COUNSEL_VEHICLE cv
                    ON ca.COUNSEL_ID = cv.COUNSEL_ID
                    AND (cv.IS_DELETED = FALSE OR cv.IS_DELETED IS NULL)
                LEFT JOIN AJDCAR_PROD.PUBLIC.USERS u ON ca.USER_ID = u.ID
                WHERE ca.COUNSEL_STATUS IN ('JOIN_COMPLETED', 'COMPARISON_COMPLETED')
                  AND ca.JOIN_COMPLETED_AT IS NOT NULL
                  AND ca.JOIN_COMPLETED_AT::DATE BETWEEN '{d_from}' AND '{d_to}'
                  AND u.USER_NAME NOT LIKE '%테스트%'
                GROUP BY 1 ORDER BY 2 DESC
            """).to_pandas()
            df.columns = ["G속성", "인당원수보험료"]
            return df

        df_pd = get_per_dealer(date_from, date_to)
        if not df_pd.empty:
            c = apply_theme(
                alt.Chart(df_pd).mark_bar(color="#f4a261").encode(
                    y=alt.Y("G속성:N", sort="-x", title=None),
                    x=alt.X("인당원수보험료:Q", title="인당 원수보험료(원)", axis=alt.Axis(format=",.0f")),
                    tooltip=[alt.Tooltip("G속성:N"),
                             alt.Tooltip("인당원수보험료:Q", format=",.0f")]
                ).properties(height=220, background=CHART_BG)
            )
            st.altair_chart(c, use_container_width=True)
        else:
            st.info("데이터 없음")

    # ── 인입채널별 현황 ──
    st.markdown('<div class="section-title">인입채널별 현황 (오프팀/상조회/B2B)</div>', unsafe_allow_html=True)
    st.markdown('<div class="empty-box">데이터 준비중입니다</div>', unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════
# TAB 2 — 보험사별 현황
# ════════════════════════════════════════════════════════════════
with tab2:

    st.markdown("""
    <div class="criteria-box">
    📌 <b>집계 기준</b><br>
    • 상태: JOIN_COMPLETED + COMPARISON_COMPLETED (가입완료 + 비견완료)<br>
    • 보험사 구분: COUNSEL_VEHICLE.JOIN_INSURER_CODE 기준<br>
    • 테스트 매니저(이름에 '테스트' 포함) 제외<br>
    • 삭제된 상담 (IS_DELETED=TRUE) 제외
    </div>
    """, unsafe_allow_html=True)

    # 필터
    bi1, bi2, bi3 = st.columns(3)
    with bi1:
        ins_date_from = st.date_input("시작일", value=date(today.year, 1, 1), key="ins_from")
    with bi2:
        ins_date_to = st.date_input("종료일", value=today, key="ins_to")
    with bi3:
        ins_mgr_opts = ["전체"] + MANAGER_LIST
        ins_sel_mgr  = st.selectbox("담당매니저", ins_mgr_opts, key="ins_mgr")

    ins_mgr_filter = "" if ins_sel_mgr == "전체" else f"AND m.NAME = '{ins_sel_mgr}'"

    # 당월 보험사별 KPI
    st.markdown('<div class="section-title">당월 보험사별 현황</div>', unsafe_allow_html=True)

    @st.cache_data(ttl=300)
    def get_insurer_monthly():
        df = session.sql("""
            SELECT
                COALESCE(cv.JOIN_INSURER_CODE, '미정') AS "보험사",
                SUM(cv.CONTRACT_AMOUNT)               AS "원수보험료",
                COUNT(*)                               AS "건수"
            FROM AJDCAR_PROD.PUBLIC.COUNSEL_APPLICATION ca
            LEFT JOIN AJDCAR_PROD.PUBLIC.COUNSEL_VEHICLE cv
                ON ca.COUNSEL_ID = cv.COUNSEL_ID
                AND (cv.IS_DELETED = FALSE OR cv.IS_DELETED IS NULL)
            WHERE ca.COUNSEL_STATUS IN ('JOIN_COMPLETED', 'COMPARISON_COMPLETED')
              AND ca.JOIN_COMPLETED_AT IS NOT NULL
              AND (ca.IS_DELETED = FALSE OR ca.IS_DELETED IS NULL)
              AND DATE_TRUNC('MONTH', ca.JOIN_COMPLETED_AT) = DATE_TRUNC('MONTH', CURRENT_DATE)
            GROUP BY 1 ORDER BY 2 DESC NULLS LAST
        """).to_pandas()
        df.columns = ["보험사", "원수보험료", "건수"]
        return df

    df_ins = get_insurer_monthly()
    ins1, ins2 = st.columns(2)
    with ins1:
        st.caption("당월 보험사별 원수보험료")
        if not df_ins.empty:
            c = apply_theme(
                alt.Chart(df_ins).mark_bar(color=BAR_MAIN).encode(
                    y=alt.Y("보험사:N", sort="-x", title=None),
                    x=alt.X("원수보험료:Q", title="원수보험료(원)", axis=alt.Axis(format=",.0f")),
                    tooltip=[alt.Tooltip("보험사:N"),
                             alt.Tooltip("원수보험료:Q", format=",.0f"),
                             alt.Tooltip("건수:Q", format=",")]
                ).properties(height=240, background=CHART_BG)
            )
            st.altair_chart(c, use_container_width=True)
    with ins2:
        st.caption("당월 보험사별 체결건수")
        if not df_ins.empty:
            c = apply_theme(
                alt.Chart(df_ins).mark_bar(color="#5ba85a").encode(
                    y=alt.Y("보험사:N", sort="-x", title=None),
                    x=alt.X("건수:Q", title="건수"),
                    tooltip=[alt.Tooltip("보험사:N"), alt.Tooltip("건수:Q", format=",")]
                ).properties(height=240, background=CHART_BG)
            )
            st.altair_chart(c, use_container_width=True)

    # 월별 보험사 추이 (기간 필터 적용)
    st.markdown('<div class="section-title">월별 보험사별 원수보험료 추이</div>', unsafe_allow_html=True)

    @st.cache_data(ttl=300)
    def get_insurer_trend(d_from, d_to, mgr_f):
        df = session.sql(f"""
            SELECT
                TO_CHAR(ca.JOIN_COMPLETED_AT, 'YYYY-MM')     AS "월",
                COALESCE(cv.JOIN_INSURER_CODE, '미정')        AS "보험사",
                SUM(cv.CONTRACT_AMOUNT)                       AS "원수보험료",
                COUNT(*)                                       AS "건수"
            FROM AJDCAR_PROD.PUBLIC.COUNSEL_APPLICATION ca
            LEFT JOIN AJDCAR_PROD.PUBLIC.COUNSEL_VEHICLE cv
                ON ca.COUNSEL_ID = cv.COUNSEL_ID
                AND (cv.IS_DELETED = FALSE OR cv.IS_DELETED IS NULL)
            LEFT JOIN AJDCAR_PROD.PUBLIC.MANAGER m ON ca.COUNSEL_MANAGER_ID = m.ID
            WHERE ca.COUNSEL_STATUS IN ('JOIN_COMPLETED', 'COMPARISON_COMPLETED')
              AND ca.JOIN_COMPLETED_AT IS NOT NULL
              AND (ca.IS_DELETED = FALSE OR ca.IS_DELETED IS NULL)
              AND ca.JOIN_COMPLETED_AT::DATE BETWEEN '{d_from}' AND '{d_to}'
              AND (m.NAME IS NULL OR m.NAME NOT LIKE '%테스트%')
              {mgr_f}
            GROUP BY 1,2 ORDER BY 1 DESC, 3 DESC NULLS LAST
        """).to_pandas()
        df.columns = ["월", "보험사", "원수보험료", "건수"]
        return df

    df_it = get_insurer_trend(ins_date_from, ins_date_to, ins_mgr_filter)
    if not df_it.empty:
        order_it = sorted(df_it["월"].unique(), reverse=True)
        c_it = apply_theme(
            alt.Chart(df_it).mark_bar().encode(
                x=alt.X("월:N", sort=order_it, title="월", axis=alt.Axis(labelAngle=-45)),
                y=alt.Y("원수보험료:Q", title="원수보험료(원)", axis=alt.Axis(format=",.0f")),
                color=alt.Color("보험사:N", legend=alt.Legend(title="보험사")),
                tooltip=[alt.Tooltip("월:N"), alt.Tooltip("보험사:N"),
                         alt.Tooltip("원수보험료:Q", format=",.0f"),
                         alt.Tooltip("건수:Q", format=",")]
            ).properties(height=300, background=CHART_BG)
        )
        st.altair_chart(c_it, use_container_width=True)
    else:
        st.info("데이터 없음")

    # 보험사별 피벗 표 (직전 6개월)
    st.markdown('<div class="section-title">보험사별 월별 피벗 (직전 6개월)</div>', unsafe_allow_html=True)

    @st.cache_data(ttl=300)
    def get_insurer_pivot():
        df = session.sql(f"""
            SELECT
                TO_CHAR(ca.JOIN_COMPLETED_AT, 'YYYY-MM')  AS "월",
                COALESCE(cv.JOIN_INSURER_CODE, '미정')     AS "보험사",
                {CH_EXPR}                                   AS "채널",
                SUM(cv.CONTRACT_AMOUNT)                    AS "원수보험료",
                COUNT(*)                                    AS "건수"
            FROM AJDCAR_PROD.PUBLIC.COUNSEL_APPLICATION ca
            LEFT JOIN AJDCAR_PROD.PUBLIC.COUNSEL_VEHICLE cv
                ON ca.COUNSEL_ID = cv.COUNSEL_ID
                AND (cv.IS_DELETED = FALSE OR cv.IS_DELETED IS NULL)
            WHERE ca.COUNSEL_STATUS IN ('JOIN_COMPLETED', 'COMPARISON_COMPLETED')
              AND ca.JOIN_COMPLETED_AT IS NOT NULL
              AND (ca.IS_DELETED = FALSE OR ca.IS_DELETED IS NULL)
              AND ca.JOIN_COMPLETED_AT >= DATEADD('MONTH', -6, DATE_TRUNC('MONTH', CURRENT_DATE))
            GROUP BY 1,2,3 ORDER BY 1 DESC,2,3
        """).to_pandas()
        df.columns = ["월", "보험사", "채널", "원수보험료", "건수"]
        return df

    df_ipv = get_insurer_pivot()
    pv_view = st.radio("피벗 지표", ["원수보험료", "건수"], horizontal=True, key="ins_pv_view")
    if not df_ipv.empty:
        pivot = df_ipv.pivot_table(
            index=["보험사", "채널"],
            columns="월",
            values=pv_view,
            aggfunc="sum",
            fill_value=0
        ).reset_index()
        month_cols = sorted([c for c in pivot.columns if c not in ["보험사","채널"]], reverse=True)
        pivot = pivot[["보험사","채널"] + month_cols]
        for c in month_cols:
            if pv_view == "원수보험료":
                pivot[c] = pivot[c].apply(lambda x: f"{int(x):,}" if x else "-")
            else:
                pivot[c] = pivot[c].apply(lambda x: f"{int(x):,}건" if x else "-")
        st.dataframe(pivot, use_container_width=True, hide_index=True)
    else:
        st.info("데이터 없음")

    # G속성별 × 보험사별 분포
    st.markdown('<div class="section-title">G속성별 × 보험사별 원수보험료 분포</div>', unsafe_allow_html=True)

    @st.cache_data(ttl=300)
    def get_g_insurer(d_from, d_to):
        df = session.sql(f"""
            SELECT
                {G_ATTR_EXPR} AS "G속성",
                COALESCE(cv.JOIN_INSURER_CODE, '미정') AS "보험사",
                SUM(cv.CONTRACT_AMOUNT) AS "원수보험료",
                COUNT(*) AS "건수"
            FROM AJDCAR_PROD.PUBLIC.COUNSEL_APPLICATION ca
            LEFT JOIN AJDCAR_PROD.PUBLIC.COUNSEL_VEHICLE cv
                ON ca.COUNSEL_ID = cv.COUNSEL_ID
                AND (cv.IS_DELETED = FALSE OR cv.IS_DELETED IS NULL)
            LEFT JOIN AJDCAR_PROD.PUBLIC.USERS u ON ca.USER_ID = u.ID
            WHERE ca.COUNSEL_STATUS IN ('JOIN_COMPLETED', 'COMPARISON_COMPLETED')
              AND ca.JOIN_COMPLETED_AT IS NOT NULL
              AND (ca.IS_DELETED = FALSE OR ca.IS_DELETED IS NULL)
              AND ca.JOIN_COMPLETED_AT::DATE BETWEEN '{d_from}' AND '{d_to}'
              AND u.USER_NAME NOT LIKE '%테스트%'
            GROUP BY 1,2 ORDER BY 1, 3 DESC NULLS LAST
        """).to_pandas()
        df.columns = ["G속성", "보험사", "원수보험료", "건수"]
        return df

    df_gi = get_g_insurer(ins_date_from, ins_date_to)
    if not df_gi.empty:
        c_gi = apply_theme(
            alt.Chart(df_gi).mark_bar().encode(
                x=alt.X("G속성:N", title="G속성"),
                y=alt.Y("원수보험료:Q", title="원수보험료(원)", axis=alt.Axis(format=",.0f")),
                color=alt.Color("보험사:N", legend=alt.Legend(title="보험사")),
                tooltip=[alt.Tooltip("G속성:N"), alt.Tooltip("보험사:N"),
                         alt.Tooltip("원수보험료:Q", format=",.0f"),
                         alt.Tooltip("건수:Q", format=",")]
            ).properties(height=300, background=CHART_BG)
        )
        st.altair_chart(c_gi, use_container_width=True)
    else:
        st.info("데이터 없음")


# ════════════════════════════════════════════════════════════════
# TAB 3 — 취소건 현황
# ════════════════════════════════════════════════════════════════
with tab3:

    st.markdown("""
    <div class="criteria-box">
    📌 <b>취소건 집계 기준</b><br>
    • <b>취소건</b>: COUNSEL_STATUS = 'JOIN_CANCELLED' 인 상담 건<br>
    • <b>삭제건</b>: IS_DELETED = TRUE 인 상담 건 (status 무관)<br>
    • 테스트 매니저(이름에 '테스트' 포함) 제외<br>
    • 날짜 기준: CREATED_AT (취소 처리 일자 기준으로 집계)
    </div>
    """, unsafe_allow_html=True)

    # 필터
    cc1, cc2, cc3 = st.columns(3)
    with cc1:
        cancel_from = st.date_input("시작일", value=date(today.year, 1, 1), key="cancel_from")
    with cc2:
        cancel_to = st.date_input("종료일", value=today, key="cancel_to")
    with cc3:
        cancel_mgr_opts = ["전체"] + MANAGER_LIST
        cancel_sel_mgr  = st.selectbox("담당매니저", cancel_mgr_opts, key="cancel_mgr")

    cancel_mgr_filter = "" if cancel_sel_mgr == "전체" else f"AND m.NAME = '{cancel_sel_mgr}'"

    # KPI
    @st.cache_data(ttl=300)
    def get_cancel_kpi(d_from, d_to, mgr_f):
        r = session.sql(f"""
            SELECT
                COUNT(CASE WHEN ca.COUNSEL_STATUS = 'JOIN_CANCELLED' THEN 1 END)    AS "취소건수",
                COUNT(CASE WHEN ca.IS_DELETED = TRUE THEN 1 END)                    AS "삭제건수",
                COUNT(CASE WHEN DATE_TRUNC('MONTH', ca.CREATED_AT) = DATE_TRUNC('MONTH', CURRENT_DATE)
                                AND ca.COUNSEL_STATUS = 'JOIN_CANCELLED' THEN 1 END) AS "당월취소",
                SUM(CASE WHEN ca.COUNSEL_STATUS = 'JOIN_CANCELLED'
                         THEN cv.CONTRACT_AMOUNT ELSE 0 END)                         AS "취소보험료합계"
            FROM AJDCAR_PROD.PUBLIC.COUNSEL_APPLICATION ca
            LEFT JOIN AJDCAR_PROD.PUBLIC.COUNSEL_VEHICLE cv
                ON ca.COUNSEL_ID = cv.COUNSEL_ID
            LEFT JOIN AJDCAR_PROD.PUBLIC.MANAGER m ON ca.COUNSEL_MANAGER_ID = m.ID
            WHERE ca.CREATED_AT::DATE BETWEEN '{d_from}' AND '{d_to}'
              AND (m.NAME IS NULL OR m.NAME NOT LIKE '%테스트%')
              {mgr_f}
        """).collect()
        return r[0]

    ck = get_cancel_kpi(cancel_from, cancel_to, cancel_mgr_filter)
    ck1, ck2, ck3, ck4 = st.columns(4)
    with ck1:
        st.markdown(kpi_card("취소건수", f"{ck['취소건수'] or 0:,}건"), unsafe_allow_html=True)
    with ck2:
        st.markdown(kpi_card("당월 취소건수", f"{ck['당월취소'] or 0:,}건"), unsafe_allow_html=True)
    with ck3:
        st.markdown(kpi_card("삭제건수", f"{ck['삭제건수'] or 0:,}건"), unsafe_allow_html=True)
    with ck4:
        cancel_prem = ck["취소보험료합계"] or 0
        st.markdown(kpi_card("취소 원수보험료 합계", fmt_won_full(cancel_prem)), unsafe_allow_html=True)

    # 월별 취소 추이
    st.markdown('<div class="section-title">월별 취소건수 추이</div>', unsafe_allow_html=True)

    @st.cache_data(ttl=300)
    def get_cancel_monthly(d_from, d_to, mgr_f):
        df = session.sql(f"""
            SELECT
                TO_CHAR(ca.CREATED_AT, 'YYYY-MM')             AS "월",
                COUNT(*)                                        AS "취소건수",
                SUM(cv.CONTRACT_AMOUNT)                         AS "취소보험료"
            FROM AJDCAR_PROD.PUBLIC.COUNSEL_APPLICATION ca
            LEFT JOIN AJDCAR_PROD.PUBLIC.COUNSEL_VEHICLE cv
                ON ca.COUNSEL_ID = cv.COUNSEL_ID
            LEFT JOIN AJDCAR_PROD.PUBLIC.MANAGER m ON ca.COUNSEL_MANAGER_ID = m.ID
            WHERE ca.COUNSEL_STATUS = 'JOIN_CANCELLED'
              AND ca.CREATED_AT::DATE BETWEEN '{d_from}' AND '{d_to}'
              AND (m.NAME IS NULL OR m.NAME NOT LIKE '%테스트%')
              {mgr_f}
            GROUP BY 1 ORDER BY 1 DESC
        """).to_pandas()
        df.columns = ["월", "취소건수", "취소보험료"]
        return df

    df_cm = get_cancel_monthly(cancel_from, cancel_to, cancel_mgr_filter)
    cmc1, cmc2 = st.columns(2)
    with cmc1:
        st.caption("월별 취소건수")
        if not df_cm.empty:
            order_cm = list(df_cm["월"])
            c = apply_theme(
                alt.Chart(df_cm).mark_bar(color="#e03131").encode(
                    x=alt.X("월:N", sort=order_cm, title=None, axis=alt.Axis(labelAngle=-45)),
                    y=alt.Y("취소건수:Q", title="취소건수"),
                    tooltip=[alt.Tooltip("월:N"), alt.Tooltip("취소건수:Q", format=",")]
                ).properties(height=240, background=CHART_BG)
            )
            st.altair_chart(c, use_container_width=True)
        else:
            st.info("데이터 없음")
    with cmc2:
        st.caption("월별 취소 원수보험료")
        if not df_cm.empty:
            order_cm = list(df_cm["월"])
            c = apply_theme(
                alt.Chart(df_cm).mark_bar(color="#f4a261").encode(
                    x=alt.X("월:N", sort=order_cm, title=None, axis=alt.Axis(labelAngle=-45)),
                    y=alt.Y("취소보험료:Q", title="원수보험료(원)", axis=alt.Axis(format=",.0f")),
                    tooltip=[alt.Tooltip("월:N"), alt.Tooltip("취소보험료:Q", format=",.0f")]
                ).properties(height=240, background=CHART_BG)
            )
            st.altair_chart(c, use_container_width=True)
        else:
            st.info("데이터 없음")

    # 보험사별 취소 현황
    st.markdown('<div class="section-title">보험사별 취소 현황</div>', unsafe_allow_html=True)

    @st.cache_data(ttl=300)
    def get_cancel_by_insurer(d_from, d_to, mgr_f):
        df = session.sql(f"""
            SELECT
                COALESCE(cv.JOIN_INSURER_CODE, '미정') AS "보험사",
                COUNT(*)                                AS "취소건수",
                SUM(cv.CONTRACT_AMOUNT)                 AS "취소보험료"
            FROM AJDCAR_PROD.PUBLIC.COUNSEL_APPLICATION ca
            LEFT JOIN AJDCAR_PROD.PUBLIC.COUNSEL_VEHICLE cv
                ON ca.COUNSEL_ID = cv.COUNSEL_ID
            LEFT JOIN AJDCAR_PROD.PUBLIC.MANAGER m ON ca.COUNSEL_MANAGER_ID = m.ID
            WHERE ca.COUNSEL_STATUS = 'JOIN_CANCELLED'
              AND ca.CREATED_AT::DATE BETWEEN '{d_from}' AND '{d_to}'
              AND (m.NAME IS NULL OR m.NAME NOT LIKE '%테스트%')
              {mgr_f}
            GROUP BY 1 ORDER BY 2 DESC NULLS LAST
        """).to_pandas()
        df.columns = ["보험사", "취소건수", "취소보험료"]
        return df

    df_ci = get_cancel_by_insurer(cancel_from, cancel_to, cancel_mgr_filter)
    if not df_ci.empty:
        st.dataframe(df_ci, use_container_width=True, hide_index=True)
    else:
        st.info("데이터 없음")

    # 채널별 취소 현황
    st.markdown('<div class="section-title">채널별 취소 현황</div>', unsafe_allow_html=True)

    @st.cache_data(ttl=300)
    def get_cancel_by_channel(d_from, d_to, mgr_f):
        df = session.sql(f"""
            SELECT
                {CH_EXPR} AS "채널",
                COUNT(*)   AS "취소건수",
                SUM(cv.CONTRACT_AMOUNT) AS "취소보험료"
            FROM AJDCAR_PROD.PUBLIC.COUNSEL_APPLICATION ca
            LEFT JOIN AJDCAR_PROD.PUBLIC.COUNSEL_VEHICLE cv
                ON ca.COUNSEL_ID = cv.COUNSEL_ID
            LEFT JOIN AJDCAR_PROD.PUBLIC.MANAGER m ON ca.COUNSEL_MANAGER_ID = m.ID
            WHERE ca.COUNSEL_STATUS = 'JOIN_CANCELLED'
              AND ca.CREATED_AT::DATE BETWEEN '{d_from}' AND '{d_to}'
              AND (m.NAME IS NULL OR m.NAME NOT LIKE '%테스트%')
              {mgr_f}
            GROUP BY 1 ORDER BY 2 DESC
        """).to_pandas()
        df.columns = ["채널", "취소건수", "취소보험료"]
        return df

    df_cc = get_cancel_by_channel(cancel_from, cancel_to, cancel_mgr_filter)
    if not df_cc.empty:
        ccc1, ccc2 = st.columns(2)
        with ccc1:
            c = apply_theme(
                alt.Chart(df_cc).mark_bar(color="#e03131").encode(
                    y=alt.Y("채널:N", sort="-x", title=None),
                    x=alt.X("취소건수:Q", title="취소건수"),
                    tooltip=[alt.Tooltip("채널:N"), alt.Tooltip("취소건수:Q", format=",")]
                ).properties(height=200, background=CHART_BG)
            )
            st.altair_chart(c, use_container_width=True)
        with ccc2:
            st.dataframe(df_cc, use_container_width=True, hide_index=True)
    else:
        st.info("데이터 없음")

    # 취소건 상세 목록
    st.markdown('<div class="section-title">취소건 상세 목록</div>', unsafe_allow_html=True)

    @st.cache_data(ttl=300)
    def get_cancel_detail(d_from, d_to, mgr_f):
        df = session.sql(f"""
            SELECT
                ca.COUNSEL_ID          AS "상담ID",
                ca.CREATED_AT::DATE    AS "생성일",
                m.NAME                 AS "담당매니저",
                u.USER_NAME            AS "딜러명",
                COALESCE(cv.JOIN_INSURER_CODE, '미정') AS "보험사",
                {CH_EXPR}              AS "채널",
                cv.CONTRACT_AMOUNT     AS "원수보험료",
                ca.COUNSEL_STATUS      AS "상태"
            FROM AJDCAR_PROD.PUBLIC.COUNSEL_APPLICATION ca
            LEFT JOIN AJDCAR_PROD.PUBLIC.COUNSEL_VEHICLE cv
                ON ca.COUNSEL_ID = cv.COUNSEL_ID
            LEFT JOIN AJDCAR_PROD.PUBLIC.USERS u ON ca.USER_ID = u.ID
            LEFT JOIN AJDCAR_PROD.PUBLIC.MANAGER m ON ca.COUNSEL_MANAGER_ID = m.ID
            WHERE ca.COUNSEL_STATUS = 'JOIN_CANCELLED'
              AND ca.CREATED_AT::DATE BETWEEN '{d_from}' AND '{d_to}'
              AND (m.NAME IS NULL OR m.NAME NOT LIKE '%테스트%')
              {mgr_f}
            ORDER BY ca.CREATED_AT DESC
            LIMIT 500
        """).to_pandas()
        df.columns = ["상담ID", "생성일", "담당매니저", "딜러명", "보험사", "채널", "원수보험료", "상태"]
        return df

    with st.expander("취소건 상세 목록 보기 (최대 500건)"):
        df_cd = get_cancel_detail(cancel_from, cancel_to, cancel_mgr_filter)
        if not df_cd.empty:
            st.dataframe(df_cd, use_container_width=True, hide_index=True)
            csv_cd = df_cd.to_csv(index=False, encoding="utf-8-sig")
            st.download_button("⬇ CSV 다운로드", csv_cd, "cancel_detail.csv", "text/csv")
        else:
            st.info("데이터 없음")


# ════════════════════════════════════════════════════════════════
# TAB 4 — 비활동 딜러 현황
# ════════════════════════════════════════════════════════════════
with tab4:

    st.markdown("""
    <div class="criteria-box">
    📌 <b>비활동 딜러 분류 기준</b><br>
    • <b>유형1 — 미체결 딜러</b>: 정회원(IS_ASSOCIATE=0), 가입 후 60일 초과, 누적 체결 0건<br>
    • <b>유형2 — 1회 체결 후 미활동</b>: 정회원(IS_ASSOCIATE=0), 누적 체결 1건, 직전 60일 내 체결 없음<br>
    • <b>유형3 — 2회 이상 체결 후 미활동</b>: 정회원(IS_ASSOCIATE=0), 누적 체결 ≥2건, 직전 60일 내 체결 없음<br>
    • <b>유형4 — 준회원 미활동</b>: 준회원(IS_ASSOCIATE=1), 누적 체결 ≥1건, 직전 60일 내 체결 없음<br>
    • 기준일: 선택한 월의 말일 / 직전 60일: 기준일-60일 ~ 기준일<br>
    • G속성: USERS.business_type + business_sub_type 기준 분류
    </div>
    """, unsafe_allow_html=True)

    ret_months = []
    _d = today.replace(day=1)
    for _ in range(12):
        ret_months.append(_d.strftime("%Y-%m"))
        _d = (_d - timedelta(days=1)).replace(day=1)

    ina1, ina2 = st.columns(2)
    with ina1:
        sel_base_month = st.selectbox("기준월 선택", ret_months, key="ret_base_month")
    with ina2:
        ina_mgr_opts = ["전체"] + MANAGER_LIST
        ina_sel_mgr  = st.selectbox("담당매니저 필터", ina_mgr_opts, key="ina_mgr")

    _y, _m = int(sel_base_month[:4]), int(sel_base_month[5:7])
    _last_day = calendar.monthrange(_y, _m)[1]
    base_date = date(_y, _m, _last_day)
    base_str  = base_date.strftime("%Y-%m-%d")
    ref_60    = (base_date - timedelta(days=60)).strftime("%Y-%m-%d")

    ina_mgr_cond = "" if ina_sel_mgr == "전체" else f"AND m.NAME = '{ina_sel_mgr}'"

    st.caption(f"기준일: {base_str} (해당 월 말일 기준) / 직전 60일: {ref_60} ~ {base_str}")

    @st.cache_data(ttl=600)
    def get_inactive_summary(base_str, ref_60, mgr_cond):
        r = session.sql(f"""
            WITH contract_summary AS (
                SELECT
                    u.ID                AS user_id,
                    u.IS_ASSOCIATE,
                    u.CREATED_AT::DATE  AS reg_date,
                    COUNT(ca.COUNSEL_ID) AS total_cnt,
                    MAX(CASE WHEN ca.COUNSEL_STATUS IN ('JOIN_COMPLETED','COMPARISON_COMPLETED')
                                  AND ca.JOIN_COMPLETED_AT::DATE BETWEEN '{ref_60}' AND '{base_str}'
                             THEN 1 ELSE 0 END) AS recent_act
                FROM AJDCAR_PROD.PUBLIC.USERS u
                LEFT JOIN AJDCAR_PROD.PUBLIC.MANAGER m ON u.MANAGER_ID = m.ID
                LEFT JOIN AJDCAR_PROD.PUBLIC.COUNSEL_APPLICATION ca
                    ON u.ID = ca.USER_ID
                    AND ca.COUNSEL_STATUS IN ('JOIN_COMPLETED','COMPARISON_COMPLETED')
                    AND ca.JOIN_COMPLETED_AT::DATE <= '{base_str}'
                    AND (ca.IS_DELETED = FALSE OR ca.IS_DELETED IS NULL)
                WHERE u.USER_NAME NOT LIKE '%테스트%'
                  AND (m.NAME IS NULL OR m.NAME NOT LIKE '%테스트%')
                  {mgr_cond}
                GROUP BY 1,2,3
            )
            SELECT
                SUM(CASE WHEN IS_ASSOCIATE = 0 AND total_cnt = 0
                              AND reg_date <= DATEADD('DAY', -60, '{base_str}') THEN 1 ELSE 0 END) AS cat1,
                SUM(CASE WHEN IS_ASSOCIATE = 0 AND total_cnt = 1 AND recent_act = 0 THEN 1 ELSE 0 END) AS cat2,
                SUM(CASE WHEN IS_ASSOCIATE = 0 AND total_cnt >= 2 AND recent_act = 0 THEN 1 ELSE 0 END) AS cat3,
                SUM(CASE WHEN IS_ASSOCIATE = 1 AND total_cnt >= 1 AND recent_act = 0 THEN 1 ELSE 0 END) AS cat4
            FROM contract_summary
        """).collect()
        return r[0]

    @st.cache_data(ttl=600)
    def get_inactive_raw(category, base_str, ref_60, mgr_cond):
        if category == 1:
            cond = f"IS_ASSOCIATE = 0 AND total_cnt = 0 AND reg_date <= DATEADD('DAY', -60, '{base_str}')"
        elif category == 2:
            cond = "IS_ASSOCIATE = 0 AND total_cnt = 1 AND recent_act = 0"
        elif category == 3:
            cond = "IS_ASSOCIATE = 0 AND total_cnt >= 2 AND recent_act = 0"
        else:
            cond = "IS_ASSOCIATE = 1 AND total_cnt >= 1 AND recent_act = 0"

        df = session.sql(f"""
            WITH contract_summary AS (
                SELECT
                    u.ID                           AS user_id,
                    u.USER_ID                      AS login_id,
                    u.USER_NAME                    AS dealer_name,
                    u.IS_ASSOCIATE,
                    u.CREATED_AT::DATE             AS reg_date,
                    m.NAME                         AS manager_name,
                    {G_ATTR_EXPR}                  AS g_attr,
                    COUNT(ca.COUNSEL_ID)            AS total_cnt,
                    MAX(ca.JOIN_COMPLETED_AT::DATE) AS last_contract_date,
                    MAX(CASE WHEN ca.COUNSEL_STATUS IN ('JOIN_COMPLETED','COMPARISON_COMPLETED')
                                  AND ca.JOIN_COMPLETED_AT::DATE BETWEEN '{ref_60}' AND '{base_str}'
                             THEN 1 ELSE 0 END) AS recent_act
                FROM AJDCAR_PROD.PUBLIC.USERS u
                LEFT JOIN AJDCAR_PROD.PUBLIC.MANAGER m ON u.MANAGER_ID = m.ID
                LEFT JOIN AJDCAR_PROD.PUBLIC.COUNSEL_APPLICATION ca
                    ON u.ID = ca.USER_ID
                    AND ca.COUNSEL_STATUS IN ('JOIN_COMPLETED','COMPARISON_COMPLETED')
                    AND ca.JOIN_COMPLETED_AT::DATE <= '{base_str}'
                    AND (ca.IS_DELETED = FALSE OR ca.IS_DELETED IS NULL)
                WHERE u.USER_NAME NOT LIKE '%테스트%'
                  AND (m.NAME IS NULL OR m.NAME NOT LIKE '%테스트%')
                  {mgr_cond}
                GROUP BY 1,2,3,4,5,6,7
            )
            SELECT
                login_id           AS "로그인ID",
                dealer_name        AS "딜러명",
                manager_name       AS "담당매니저",
                g_attr             AS "G속성",
                IS_ASSOCIATE       AS "준회원여부",
                reg_date           AS "가입일",
                total_cnt          AS "총체결건수",
                last_contract_date AS "마지막체결일"
            FROM contract_summary
            WHERE {cond}
            ORDER BY total_cnt DESC, reg_date
        """).to_pandas()
        df.columns = ["로그인ID", "딜러명", "담당매니저", "G속성", "준회원여부", "가입일", "총체결건수", "마지막체결일"]
        return df

    ina_summary = get_inactive_summary(base_str, ref_60, ina_mgr_cond)

    cat_labels = [
        ("미체결 딜러", "cat1", "정회원, 가입 60일↑, 체결 0건"),
        ("1회 체결 후 미활동", "cat2", "정회원, 총 1건, 직전 60일 없음"),
        ("2회↑ 체결 후 미활동", "cat3", "정회원, 총 ≥2건, 직전 60일 없음"),
        ("준회원 미활동", "cat4", "준회원, 체결 ≥1건, 직전 60일 없음"),
    ]

    rc1, rc2, rc3, rc4 = st.columns(4)
    for col, (lbl, key, desc), cat_num in zip(
        [rc1, rc2, rc3, rc4], cat_labels, [1, 2, 3, 4]
    ):
        cnt = ina_summary[key.upper()] or 0
        with col:
            st.markdown(kpi_card(lbl, f"{cnt:,}명", desc, "neutral"), unsafe_allow_html=True)

    # G속성별 비활동 딜러 분포
    st.markdown('<div class="section-title">G속성별 비활동 딜러 분포</div>', unsafe_allow_html=True)

    @st.cache_data(ttl=600)
    def get_inactive_g_dist(base_str, ref_60, mgr_cond):
        df = session.sql(f"""
            WITH contract_summary AS (
                SELECT
                    u.ID               AS user_id,
                    u.IS_ASSOCIATE,
                    u.CREATED_AT::DATE AS reg_date,
                    {G_ATTR_EXPR}      AS g_attr,
                    COUNT(ca.COUNSEL_ID) AS total_cnt,
                    MAX(CASE WHEN ca.COUNSEL_STATUS IN ('JOIN_COMPLETED','COMPARISON_COMPLETED')
                                  AND ca.JOIN_COMPLETED_AT::DATE BETWEEN '{ref_60}' AND '{base_str}'
                             THEN 1 ELSE 0 END) AS recent_act
                FROM AJDCAR_PROD.PUBLIC.USERS u
                LEFT JOIN AJDCAR_PROD.PUBLIC.MANAGER m ON u.MANAGER_ID = m.ID
                LEFT JOIN AJDCAR_PROD.PUBLIC.COUNSEL_APPLICATION ca
                    ON u.ID = ca.USER_ID
                    AND ca.COUNSEL_STATUS IN ('JOIN_COMPLETED','COMPARISON_COMPLETED')
                    AND ca.JOIN_COMPLETED_AT::DATE <= '{base_str}'
                    AND (ca.IS_DELETED = FALSE OR ca.IS_DELETED IS NULL)
                WHERE u.USER_NAME NOT LIKE '%테스트%'
                  AND (m.NAME IS NULL OR m.NAME NOT LIKE '%테스트%')
                  {mgr_cond}
                GROUP BY 1,2,3,4
            )
            SELECT
                g_attr AS "G속성",
                SUM(CASE WHEN IS_ASSOCIATE = 0 AND total_cnt = 0
                              AND reg_date <= DATEADD('DAY', -60, '{base_str}') THEN 1 ELSE 0 END) AS "미체결",
                SUM(CASE WHEN IS_ASSOCIATE = 0 AND total_cnt = 1 AND recent_act = 0 THEN 1 ELSE 0 END) AS "1회후미활동",
                SUM(CASE WHEN IS_ASSOCIATE = 0 AND total_cnt >= 2 AND recent_act = 0 THEN 1 ELSE 0 END) AS "2회이상후미활동",
                SUM(CASE WHEN IS_ASSOCIATE = 1 AND total_cnt >= 1 AND recent_act = 0 THEN 1 ELSE 0 END) AS "준회원미활동"
            FROM contract_summary
            GROUP BY 1 ORDER BY 2 DESC
        """).to_pandas()
        df.columns = ["G속성", "미체결", "1회후미활동", "2회이상후미활동", "준회원미활동"]
        return df

    df_ig = get_inactive_g_dist(base_str, ref_60, ina_mgr_cond)
    if not df_ig.empty:
        df_ig_melt = df_ig.melt("G속성", var_name="유형", value_name="딜러수")
        c_ig = apply_theme(
            alt.Chart(df_ig_melt).mark_bar().encode(
                x=alt.X("G속성:N", title="G속성"),
                y=alt.Y("딜러수:Q", title="딜러수"),
                color=alt.Color("유형:N", legend=alt.Legend(title="비활동 유형")),
                tooltip=[alt.Tooltip("G속성:N"), alt.Tooltip("유형:N"),
                         alt.Tooltip("딜러수:Q", format=",")]
            ).properties(height=300, background=CHART_BG)
        )
        st.altair_chart(c_ig, use_container_width=True)
        st.dataframe(df_ig, use_container_width=True, hide_index=True)
    else:
        st.info("데이터 없음")

    # 유형별 상세 목록
    st.markdown('<div class="section-title">유형별 상세 딜러 목록</div>', unsafe_allow_html=True)
    for cat_num, (lbl, key, desc) in enumerate(cat_labels, 1):
        cnt = ina_summary[key.upper()] or 0
        with st.expander(f"▶ 유형{cat_num}: {lbl} ({cnt:,}명) 상세"):
            df_raw = get_inactive_raw(cat_num, base_str, ref_60, ina_mgr_cond)
            if df_raw.empty:
                st.info("해당 딜러 없음")
            else:
                st.dataframe(df_raw, use_container_width=True, hide_index=True)
                csv = df_raw.to_csv(index=False, encoding="utf-8-sig")
                st.download_button(
                    label="⬇ CSV 다운로드",
                    data=csv,
                    file_name=f"inactive_cat{cat_num}_{sel_base_month}.csv",
                    mime="text/csv",
                    key=f"ina_dl_{cat_num}"
                )


# ════════════════════════════════════════════════════════════════
# TAB 5 — 비견건수
# ════════════════════════════════════════════════════════════════
with tab5:

    st.markdown("""
    <div class="criteria-box">
    📌 <b>비견건수 집계 기준</b><br>
    • <b>비견 요청</b>: comparison_estimate 테이블 기준 (비견 견적서 생성 = 비견 요청 1건)<br>
    • <b>비견 완료</b>: counsel_application.COUNSEL_STATUS = 'COMPARISON_COMPLETED' 건<br>
    • <b>비견→체결 전환</b>: COMPARISON_COMPLETED 후 JOIN_COMPLETED 로 상태 변경된 건<br>
    • 테스트 매니저 제외 / 삭제건 제외<br>
    • ERD 연결: counsel_application → counsel_vehicle → comparison_estimate → comparison_request_vehicle
    </div>
    """, unsafe_allow_html=True)

    # 필터
    cmp1, cmp2, cmp3 = st.columns(3)
    with cmp1:
        cmp_from = st.date_input("시작일", value=date(today.year, 1, 1), key="cmp_from")
    with cmp2:
        cmp_to = st.date_input("종료일", value=today, key="cmp_to")
    with cmp3:
        cmp_mgr_opts = ["전체"] + MANAGER_LIST
        cmp_sel_mgr  = st.selectbox("담당매니저", cmp_mgr_opts, key="cmp_mgr")

    cmp_mgr_filter = "" if cmp_sel_mgr == "전체" else f"AND m.NAME = '{cmp_sel_mgr}'"

    # 월별 비견건수 KPI
    @st.cache_data(ttl=300)
    def get_cmp_kpi(d_from, d_to, mgr_f):
        r = session.sql(f"""
            SELECT
                COUNT(DISTINCT ca.COUNSEL_ID)                      AS "전체상담건수",
                COUNT(DISTINCT CASE WHEN ca.COUNSEL_STATUS = 'COMPARISON_COMPLETED'
                                    THEN ca.COUNSEL_ID END)         AS "비견완료건수",
                COUNT(DISTINCT CASE WHEN ca.COUNSEL_STATUS = 'JOIN_COMPLETED'
                                    THEN ca.COUNSEL_ID END)         AS "가입완료건수",
                COUNT(DISTINCT ce.ID)                              AS "비견견적건수"
            FROM AJDCAR_PROD.PUBLIC.COUNSEL_APPLICATION ca
            LEFT JOIN AJDCAR_PROD.PUBLIC.COUNSEL_VEHICLE cv
                ON ca.COUNSEL_ID = cv.COUNSEL_ID
                AND (cv.IS_DELETED = FALSE OR cv.IS_DELETED IS NULL)
            LEFT JOIN AJDCAR_PROD.PUBLIC.COMPARISON_ESTIMATE ce
                ON cv.ID = ce.COUNSEL_VEHICLE_ID
            LEFT JOIN AJDCAR_PROD.PUBLIC.MANAGER m ON ca.COUNSEL_MANAGER_ID = m.ID
            WHERE ca.CREATED_AT::DATE BETWEEN '{d_from}' AND '{d_to}'
              AND (ca.IS_DELETED = FALSE OR ca.IS_DELETED IS NULL)
              AND (m.NAME IS NULL OR m.NAME NOT LIKE '%테스트%')
              {mgr_f}
        """).collect()
        return r[0]

    ck = get_cmp_kpi(cmp_from, cmp_to, cmp_mgr_filter)
    total_ca  = ck["전체상담건수"] or 0
    cmp_done  = ck["비견완료건수"] or 0
    join_done = ck["가입완료건수"] or 0
    est_cnt   = ck["비견견적건수"] or 0
    cmp_rate  = (cmp_done / total_ca * 100) if total_ca else 0
    join_rate = (join_done / cmp_done * 100) if cmp_done else 0

    kc1, kc2, kc3, kc4, kc5 = st.columns(5)
    with kc1:
        st.markdown(kpi_card("전체 상담건수", f"{total_ca:,}건"), unsafe_allow_html=True)
    with kc2:
        st.markdown(kpi_card("비견 견적건수", f"{est_cnt:,}건"), unsafe_allow_html=True)
    with kc3:
        st.markdown(kpi_card("비견완료건수", f"{cmp_done:,}건", f"상담 대비 {cmp_rate:.1f}%"), unsafe_allow_html=True)
    with kc4:
        st.markdown(kpi_card("가입완료건수", f"{join_done:,}건"), unsafe_allow_html=True)
    with kc5:
        st.markdown(kpi_card("비견→가입 전환율", f"{join_rate:.1f}%", f"비견완료 {cmp_done:,}건 중"), unsafe_allow_html=True)

    # 월별 비견건수 추이
    st.markdown('<div class="section-title">월별 비견건수 추이</div>', unsafe_allow_html=True)

    @st.cache_data(ttl=300)
    def get_cmp_monthly(d_from, d_to, mgr_f):
        df = session.sql(f"""
            SELECT
                TO_CHAR(ca.CREATED_AT, 'YYYY-MM') AS "월",
                COUNT(DISTINCT ca.COUNSEL_ID)       AS "전체상담",
                COUNT(DISTINCT ce.ID)               AS "비견견적",
                COUNT(DISTINCT CASE WHEN ca.COUNSEL_STATUS = 'COMPARISON_COMPLETED'
                                    THEN ca.COUNSEL_ID END) AS "비견완료",
                COUNT(DISTINCT CASE WHEN ca.COUNSEL_STATUS = 'JOIN_COMPLETED'
                                    THEN ca.COUNSEL_ID END) AS "가입완료"
            FROM AJDCAR_PROD.PUBLIC.COUNSEL_APPLICATION ca
            LEFT JOIN AJDCAR_PROD.PUBLIC.COUNSEL_VEHICLE cv
                ON ca.COUNSEL_ID = cv.COUNSEL_ID
                AND (cv.IS_DELETED = FALSE OR cv.IS_DELETED IS NULL)
            LEFT JOIN AJDCAR_PROD.PUBLIC.COMPARISON_ESTIMATE ce
                ON cv.ID = ce.COUNSEL_VEHICLE_ID
            LEFT JOIN AJDCAR_PROD.PUBLIC.MANAGER m ON ca.COUNSEL_MANAGER_ID = m.ID
            WHERE ca.CREATED_AT::DATE BETWEEN '{d_from}' AND '{d_to}'
              AND (ca.IS_DELETED = FALSE OR ca.IS_DELETED IS NULL)
              AND (m.NAME IS NULL OR m.NAME NOT LIKE '%테스트%')
              {mgr_f}
            GROUP BY 1 ORDER BY 1 DESC
        """).to_pandas()
        df.columns = ["월", "전체상담", "비견견적", "비견완료", "가입완료"]
        return df

    df_cm2 = get_cmp_monthly(cmp_from, cmp_to, cmp_mgr_filter)
    if not df_cm2.empty:
        df_cm2_melt = df_cm2.melt("월", var_name="구분", value_name="건수")
        order_cm2 = list(df_cm2["월"])
        c_cm2 = apply_theme(
            alt.Chart(df_cm2_melt).mark_line(point=True).encode(
                x=alt.X("월:N", sort=order_cm2, title="월", axis=alt.Axis(labelAngle=-45)),
                y=alt.Y("건수:Q", title="건수"),
                color=alt.Color("구분:N", legend=alt.Legend(title="구분")),
                tooltip=[alt.Tooltip("월:N"), alt.Tooltip("구분:N"),
                         alt.Tooltip("건수:Q", format=",")]
            ).properties(height=300, background=CHART_BG)
        )
        st.altair_chart(c_cm2, use_container_width=True)
        st.dataframe(df_cm2, use_container_width=True, hide_index=True)
    else:
        st.info("데이터 없음")

    # 매니저별 비견건수
    st.markdown('<div class="section-title">매니저별 비견 현황</div>', unsafe_allow_html=True)

    @st.cache_data(ttl=300)
    def get_cmp_by_manager(d_from, d_to):
        df = session.sql(f"""
            SELECT
                COALESCE(m.NAME, '미배정') AS "담당매니저",
                COUNT(DISTINCT ca.COUNSEL_ID)   AS "전체상담",
                COUNT(DISTINCT ce.ID)            AS "비견견적",
                COUNT(DISTINCT CASE WHEN ca.COUNSEL_STATUS = 'COMPARISON_COMPLETED'
                                    THEN ca.COUNSEL_ID END) AS "비견완료",
                COUNT(DISTINCT CASE WHEN ca.COUNSEL_STATUS = 'JOIN_COMPLETED'
                                    THEN ca.COUNSEL_ID END) AS "가입완료",
                ROUND(COUNT(DISTINCT CASE WHEN ca.COUNSEL_STATUS = 'COMPARISON_COMPLETED'
                                    THEN ca.COUNSEL_ID END)
                      / NULLIF(COUNT(DISTINCT ca.COUNSEL_ID), 0) * 100, 1) AS "비견완료율"
            FROM AJDCAR_PROD.PUBLIC.COUNSEL_APPLICATION ca
            LEFT JOIN AJDCAR_PROD.PUBLIC.COUNSEL_VEHICLE cv
                ON ca.COUNSEL_ID = cv.COUNSEL_ID
                AND (cv.IS_DELETED = FALSE OR cv.IS_DELETED IS NULL)
            LEFT JOIN AJDCAR_PROD.PUBLIC.COMPARISON_ESTIMATE ce
                ON cv.ID = ce.COUNSEL_VEHICLE_ID
            LEFT JOIN AJDCAR_PROD.PUBLIC.MANAGER m ON ca.COUNSEL_MANAGER_ID = m.ID
            WHERE ca.CREATED_AT::DATE BETWEEN '{d_from}' AND '{d_to}'
              AND (ca.IS_DELETED = FALSE OR ca.IS_DELETED IS NULL)
              AND (m.NAME IS NULL OR m.NAME NOT LIKE '%테스트%')
            GROUP BY 1 ORDER BY 3 DESC
        """).to_pandas()
        df.columns = ["담당매니저", "전체상담", "비견견적", "비견완료", "가입완료", "비견완료율(%)"]
        return df

    df_mgr_cmp = get_cmp_by_manager(cmp_from, cmp_to)
    if not df_mgr_cmp.empty:
        st.dataframe(df_mgr_cmp, use_container_width=True, hide_index=True)
    else:
        st.info("데이터 없음")

    # 비견 요청 차량 현황
    st.markdown('<div class="section-title">비견 요청 차량 현황</div>', unsafe_allow_html=True)

    @st.cache_data(ttl=300)
    def get_cmp_vehicle(d_from, d_to, mgr_f):
        df = session.sql(f"""
            SELECT
                TO_CHAR(ca.CREATED_AT, 'YYYY-MM')     AS "월",
                COUNT(DISTINCT crv.ID)                  AS "비견요청차량수",
                COUNT(DISTINCT ce.ID)                   AS "비견견적수",
                COUNT(DISTINCT ca.COUNSEL_ID)           AS "상담건수"
            FROM AJDCAR_PROD.PUBLIC.COUNSEL_APPLICATION ca
            LEFT JOIN AJDCAR_PROD.PUBLIC.COUNSEL_VEHICLE cv
                ON ca.COUNSEL_ID = cv.COUNSEL_ID
                AND (cv.IS_DELETED = FALSE OR cv.IS_DELETED IS NULL)
            LEFT JOIN AJDCAR_PROD.PUBLIC.COMPARISON_ESTIMATE ce
                ON cv.ID = ce.COUNSEL_VEHICLE_ID
            LEFT JOIN AJDCAR_PROD.PUBLIC.COMPARISON_REQUEST_VEHICLE crv
                ON ce.ID = crv.COMPARISON_ESTIMATE_ID
            LEFT JOIN AJDCAR_PROD.PUBLIC.MANAGER m ON ca.COUNSEL_MANAGER_ID = m.ID
            WHERE ca.CREATED_AT::DATE BETWEEN '{d_from}' AND '{d_to}'
              AND (ca.IS_DELETED = FALSE OR ca.IS_DELETED IS NULL)
              AND (m.NAME IS NULL OR m.NAME NOT LIKE '%테스트%')
              {mgr_f}
            GROUP BY 1 ORDER BY 1 DESC
        """).to_pandas()
        df.columns = ["월", "비견요청차량수", "비견견적수", "상담건수"]
        return df

    df_crv = get_cmp_vehicle(cmp_from, cmp_to, cmp_mgr_filter)
    if not df_crv.empty:
        st.dataframe(df_crv, use_container_width=True, hide_index=True)
    else:
        st.info("데이터 없음")

    # 상담 상태 이력 (counsel_status_log) 기반 비견 전환 분석
    st.markdown('<div class="section-title">상태 이력 기반 비견 전환 분석</div>', unsafe_allow_html=True)
    st.caption("counsel_status_log 기준: 상태별 건수 및 전환 흐름")

    @st.cache_data(ttl=300)
    def get_status_log_summary(d_from, d_to):
        df = session.sql(f"""
            SELECT
                csl.STATUS           AS "상태",
                TO_CHAR(csl.CREATED_AT, 'YYYY-MM') AS "월",
                COUNT(*)             AS "건수"
            FROM AJDCAR_PROD.PUBLIC.COUNSEL_STATUS_LOG csl
            WHERE csl.CREATED_AT::DATE BETWEEN '{d_from}' AND '{d_to}'
            GROUP BY 1, 2 ORDER BY 2 DESC, 3 DESC
        """).to_pandas()
        df.columns = ["상태", "월", "건수"]
        return df

    df_sl = get_status_log_summary(cmp_from, cmp_to)
    if not df_sl.empty:
        pivot_sl = df_sl.pivot_table(
            index="상태", columns="월", values="건수", aggfunc="sum", fill_value=0
        ).reset_index()
        month_cols_sl = sorted([c for c in pivot_sl.columns if c != "상태"], reverse=True)
        pivot_sl = pivot_sl[["상태"] + month_cols_sl]
        st.dataframe(pivot_sl, use_container_width=True, hide_index=True)
    else:
        st.info("데이터 없음")
