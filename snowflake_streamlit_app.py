import streamlit as st
import pandas as pd
from snowflake.snowpark.context import get_active_session
import altair as alt
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
import calendar

st.set_page_config(layout="wide", page_title="영업현황 대시보드")

st.markdown("""
<style>
[data-testid="stAppViewContainer"] { background: #ffffff; }
[data-testid="stSidebar"]          { background: #f8f9fa; }
[data-testid="stHeader"]           { background: #ffffff; }

/* ── 탭바 고정 (스크롤해도 상단 고정) ── */
div[data-testid="stTabs"] > div:first-child {
    position: sticky;
    top: 2.875rem;
    z-index: 999;
    background-color: #ffffff;
    padding-bottom: 4px;
    border-bottom: 1px solid #e0e0e0;
}
.kpi-card {
    background: #f0f2f6;
    border-radius: 8px;
    padding: 16px 12px;
    text-align: center;
    border: 1px solid #e0e0e0;
    margin-bottom: 8px;
    min-height: 100px;
    display: flex;
    flex-direction: column;
    justify-content: center;
}
.kpi-label    { color: #555555; font-size: 11px; margin-bottom: 6px; }
.kpi-value    { color: #1a1a1a; font-size: 22px; font-weight: 700; line-height: 1.2; }
.kpi-value-sm { color: #1a1a1a; font-size: 16px; font-weight: 700; line-height: 1.4; }
.kpi-value-lg { color: #aaaaaa; font-size: 17px; font-weight: 700; }
.kpi-up       { color: #e03131; font-size: 11px; margin-top: 4px; }
.kpi-down     { color: #1971c2; font-size: 11px; margin-top: 4px; }
.kpi-neutral  { color: #999999; font-size: 11px; margin-top: 4px; }
.section-title {
    color: #222222; font-size: 13px; font-weight: 600;
    margin: 24px 0 10px 0; padding-bottom: 5px;
    border-bottom: 2px solid #e0e0e0;
}
.chart-caption {
    color: #555555; font-size: 12px; font-weight: 600;
    margin-bottom: 4px;
}
.empty-box {
    background: #f8f9fa; border-radius: 6px; padding: 20px;
    text-align: center; color: #aaaaaa; font-size: 12px;
    border: 1px dashed #cccccc;
}
.criteria-box {
    background: #f0f4ff; border-radius: 6px; padding: 10px 14px;
    font-size: 12px; color: #333; border-left: 3px solid #4c78a8;
    margin-bottom: 14px; line-height: 1.7;
}
</style>
""", unsafe_allow_html=True)

session = get_active_session()

CHART_BG = "#f0f2f6"
AXIS_C   = "#333333"
GRID_C   = "#dddddd"
BAR_MAIN = "#4c78a8"

MANAGER_LIST = ['김경선','김미희','박순미','송민선','신영란','이선','이선이','정혜령','최현정']

# 탈퇴회원(IS_DELETED=TRUE) 및 테스트 계정 제외
USER_FILTER = "IS_ASSOCIATE = 0 AND USER_NAME NOT LIKE '%테스트%' AND (IS_DELETED = FALSE OR IS_DELETED IS NULL)"

# CH_EXPR: cv alias 필요 (counsel_vehicle join 필수)
CH_EXPR = """
    CASE
        WHEN cv.REGISTRATION_TYPE = 'RENEWAL' THEN '갱신'
        WHEN ca.CHANNEL_PATH = 'INBOUND'      THEN 'CS'
        WHEN ca.CHANNEL_PATH = 'DEALER_APP'   THEN '딜러앱'
        ELSE '기타'
    END
"""

# G속성: business_type + business_sub_type 조합
# NEW_CAR_DEALER는 DOMESTIC(국산)/IMPORTED(수입)으로 세분화
G_ATTR_EXPR = """
    CASE
        WHEN u.BUSINESS_TYPE = 'NEW_CAR_DEALER' AND u.BUSINESS_SUB_TYPE = 'IMPORTED' THEN 'G1(수입)'
        WHEN u.BUSINESS_TYPE = 'NEW_CAR_DEALER' AND u.BUSINESS_SUB_TYPE = 'DOMESTIC' THEN 'G2(국산)'
        WHEN u.BUSINESS_TYPE = 'USED_CAR_DEALER'                                     THEN 'G3(중고차)'
        WHEN u.BUSINESS_TYPE = 'INSURANCE_AGENT'                                     THEN 'G4(보험설계)'
        WHEN u.BUSINESS_TYPE = 'AGENCY'                                              THEN 'G5(에이전시)'
        WHEN u.BUSINESS_TYPE = 'NEW_CAR_DEALER'                                      THEN 'G1/G2(신차)'
        ELSE '미분류'
    END
"""

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

def kpi_card(label, value, delta=None, delta_type="neutral", small=False):
    val_class  = "kpi-value-sm" if small else "kpi-value"
    delta_html = f'<div class="kpi-{delta_type}">{delta}</div>' if delta else ""
    return (f'<div class="kpi-card"><div class="kpi-label">{label}</div>'
            f'<div class="{val_class}">{value}</div>{delta_html}</div>')

def kpi_card_two_delta(label, value, delta1, delta2, delta_type="neutral", small=False):
    val_class = "kpi-value-sm" if small else "kpi-value"
    return (f'<div class="kpi-card"><div class="kpi-label">{label}</div>'
            f'<div class="{val_class}">{value}</div>'
            f'<div class="kpi-{delta_type}">{delta1}</div>'
            f'<div class="kpi-{delta_type}">{delta2}</div></div>')

# ══════════════════════════════════════════════
st.title("영업현황")

today            = date.today()
this_month_start = today.replace(day=1)
last_month_end   = this_month_start - timedelta(days=1)
last_month_start = last_month_end.replace(day=1)
# ValueError 방지: 7/31 → 6/30 초과 시 min으로 보정
same_period_end  = min(last_month_end,
                       last_month_start.replace(day=min(today.day, last_month_end.day)))

# ════════════════════════════════════
# 탭 구성
# ════════════════════════════════════
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 영업현황",
    "🏢 보험사별 현황",
    "❌ 취소건 현황",
    "💤 비활동 딜러 현황",
    "🔍 비견건수",
])

# ═══════════════════════════════════════════════════════════════
# TAB 1 — 영업현황 (기존 코드 유지)
# ═══════════════════════════════════════════════════════════════
with tab1:

    # ── KPI ──────────────────────────────────────
    st.markdown('<div class="section-title">실시간 지표</div>', unsafe_allow_html=True)

    @st.cache_data(ttl=300)
    def get_kpi_premium(lms, spe):
        r = session.sql(f"""
            SELECT
                SUM(CASE WHEN DATE_TRUNC('MONTH', ca.JOIN_COMPLETED_AT) = DATE_TRUNC('MONTH', CURRENT_DATE)
                         THEN cv.CONTRACT_AMOUNT ELSE 0 END) AS cur_month,
                SUM(CASE WHEN ca.JOIN_COMPLETED_AT::DATE BETWEEN '{lms}' AND '{spe}'
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
        r = session.sql("""
            SELECT COUNT(DISTINCT ca.USER_ID) AS active_60
            FROM AJDCAR_PROD.PUBLIC.COUNSEL_APPLICATION ca
            WHERE ca.COUNSEL_STATUS = 'JOIN_COMPLETED'
              AND ca.JOIN_COMPLETED_AT >= DATEADD('DAY', -60, CURRENT_DATE)
              AND (ca.IS_DELETED = FALSE OR ca.IS_DELETED IS NULL)
        """).collect()
        t = session.sql("""
            SELECT COUNT(*) AS total_dealer
            FROM AJDCAR_PROD.PUBLIC.USERS
            WHERE USER_NAME NOT LIKE '%테스트%'
              AND (IS_DELETED = FALSE OR IS_DELETED IS NULL)
        """).collect()
        active = r[0]["ACTIVE_60"]
        total  = t[0]["TOTAL_DEALER"]
        return active, total, (active / total * 100) if total else 0

    kpi_prem                = get_kpi_premium(last_month_start, same_period_end)
    kpi_usr                 = get_kpi_users()
    active60, total_u, rate = get_kpi_active_dealer()

    cur  = kpi_prem["CUR_MONTH"] or 0
    lst  = kpi_prem["LAST_SAME"] or 0
    diff = cur - lst

    if lst > 0:
        pct        = diff / lst * 100
        pct_str    = f"전월동기 대비 {'+' if pct>=0 else ''}{pct:.1f}%"
        diff_str   = f"({'▲' if diff>=0 else '▼'} {abs(int(diff)):,}원 차이)"
        delta_type = "up" if pct >= 0 else "down"
    else:
        pct_str    = "전월동기 데이터 없음"
        diff_str   = ""
        delta_type = "neutral"

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(kpi_card_two_delta("당월 총 원수보험료", f"{int(cur):,}원",
                                       pct_str, diff_str, delta_type, small=True), unsafe_allow_html=True)
    with c2:
        st.markdown(kpi_card("당월 앱 가입자수", f"{kpi_usr['THIS_MONTH']:,}명"), unsafe_allow_html=True)
    with c3:
        st.markdown(kpi_card("누적 앱 가입자수", f"{kpi_usr['TOTAL']:,}명"), unsafe_allow_html=True)

    c4, c5, c6 = st.columns(3)
    with c4:
        st.markdown(kpi_card("직전 60일 활동딜러", f"{active60:,}명"), unsafe_allow_html=True)
    with c5:
        st.markdown(kpi_card("활동률", f"{rate:.1f}%", f"전체 {total_u:,}명 중"), unsafe_allow_html=True)
    with c6:
        st.markdown('<div class="kpi-card"><div class="kpi-label">오프영업팀 가입건</div>'
                    '<div class="kpi-value-lg">-</div>'
                    '<div class="kpi-neutral">데이터 준비중</div></div>', unsafe_allow_html=True)

    # ── G1~G5 ────────────────────────────────────
    st.markdown('<div class="section-title">앱 가입현황 (딜러그룹별)</div>', unsafe_allow_html=True)

    @st.cache_data(ttl=300)
    def get_g_attr_users():
        df = session.sql(f"""
            SELECT
                {G_ATTR_EXPR} AS g_attr,
                COUNT(*) AS cnt,
                COUNT(CASE WHEN DATE_TRUNC('MONTH', CREATED_AT) = DATE_TRUNC('MONTH', CURRENT_DATE)
                           THEN 1 END) AS this_month
            FROM AJDCAR_PROD.PUBLIC.USERS u
            WHERE {USER_FILTER}
            GROUP BY 1
        """).to_pandas()
        df.columns = ["g_attr", "cnt", "this_month"]
        return df

    df_g = get_g_attr_users()
    G_ORDER = ["G1(수입)", "G2(국산)", "G3(중고차)", "G4(보험설계)", "G5(에이전시)"]
    g_map = dict(zip(df_g["g_attr"], zip(df_g["cnt"], df_g["this_month"])))

    gcols = st.columns(5)
    for col, g in zip(gcols, G_ORDER):
        vals = g_map.get(g, (0, 0))
        total_g, month_g = int(vals[0]), int(vals[1])
        with col:
            st.markdown(kpi_card(g, f"{total_g:,}명",
                                 f"당월 +{month_g:,}명", "neutral"), unsafe_allow_html=True)

    # ── 계약체결 구간별 딜러 분포 ─────────────────
    st.markdown('<div class="section-title">계약체결 구간별 딜러 분포</div>', unsafe_allow_html=True)

    @st.cache_data(ttl=300)
    def get_dealer_dist(days):
        df = session.sql(f"""
            WITH dc AS (
                SELECT USER_ID, COUNT(*) AS cnt
                FROM AJDCAR_PROD.PUBLIC.COUNSEL_APPLICATION
                WHERE COUNSEL_STATUS = 'JOIN_COMPLETED'
                  AND JOIN_COMPLETED_AT >= DATEADD('DAY', -{days}, CURRENT_DATE)
                  AND (IS_DELETED = FALSE OR IS_DELETED IS NULL)
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
                COUNT(*) AS "딜러수"
            FROM dc GROUP BY 1 ORDER BY MIN(cnt)
        """).to_pandas()
        df.columns = ["구간", "딜러수"]
        return df

    SORT_ORDER = ["1건","2건","3건","4~6건","7건 이상"]
    d1, d2 = st.columns(2)
    with d1:
        st.caption("직전 60일")
        df60 = get_dealer_dist(60)
        if not df60.empty:
            st.altair_chart(apply_theme(
                alt.Chart(df60).mark_bar(color=BAR_MAIN).encode(
                    x=alt.X("구간:N", sort=SORT_ORDER, title=None),
                    y=alt.Y("딜러수:Q", title="딜러수"),
                    tooltip=[alt.Tooltip("구간:N"), alt.Tooltip("딜러수:Q", format=",")]
                ).properties(height=220, background=CHART_BG)
            ), use_container_width=True)

    with d2:
        st.caption("직전 90일")
        df90 = get_dealer_dist(90)
        if not df90.empty:
            st.altair_chart(apply_theme(
                alt.Chart(df90).mark_bar(color="#5ba85a").encode(
                    x=alt.X("구간:N", sort=SORT_ORDER, title=None),
                    y=alt.Y("딜러수:Q", title="딜러수"),
                    tooltip=[alt.Tooltip("구간:N"), alt.Tooltip("딜러수:Q", format=",")]
                ).properties(height=220, background=CHART_BG)
            ), use_container_width=True)

    # ── 추이 차트 ─────────────────────────────────
    st.markdown('<div class="section-title">추이 차트</div>', unsafe_allow_html=True)

    st.markdown('<div class="chart-caption">직전 50일 일별 총 원수보험료</div>', unsafe_allow_html=True)

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
            WHERE ca.COUNSEL_STATUS = 'JOIN_COMPLETED'
              AND ca.JOIN_COMPLETED_AT IS NOT NULL
              AND (ca.IS_DELETED = FALSE OR ca.IS_DELETED IS NULL)
              AND ca.JOIN_COMPLETED_AT::DATE >= DATEADD('DAY', -50, CURRENT_DATE)
            GROUP BY 1 ORDER BY 1 DESC
        """).to_pandas()
        df.columns = ["일자", "원수보험료"]
        df["일자"] = pd.to_datetime(df["일자"])
        df = df.sort_values("일자", ascending=False).reset_index(drop=True)
        return df

    df50 = get_daily50()
    if not df50.empty:
        avg_val = df50["원수보험료"].mean()
        bars = alt.Chart(df50).mark_bar(color=BAR_MAIN, size=10).encode(
            x=alt.X("일자:T", title="일자",
                    scale=alt.Scale(reverse=True),
                    axis=alt.Axis(format="%m/%d", labelAngle=-45, tickCount=15)),
            y=alt.Y("원수보험료:Q", title="원수보험료(원)", axis=alt.Axis(format=",.0f")),
            tooltip=[alt.Tooltip("일자:T", format="%Y-%m-%d"),
                     alt.Tooltip("원수보험료:Q", format=",.0f")]
        )
        rule = alt.Chart(pd.DataFrame({"avg": [avg_val]})).mark_rule(
            color="#e03131", strokeDash=[4,3], strokeWidth=1.5
        ).encode(y="avg:Q")
        label_chart = alt.Chart(pd.DataFrame({
            "avg": [avg_val], "x": [df50["일자"].iloc[0]],
            "lbl": [f"평균 {avg_val/10000:.0f}만"]
        })).mark_text(align="left", dx=4, dy=-8, color="#e03131", fontSize=11
        ).encode(x="x:T", y="avg:Q", text="lbl:N")
        st.altair_chart(apply_theme(
            (bars + rule + label_chart).properties(height=280, background=CHART_BG)
        ), use_container_width=True)
    else:
        st.info("데이터 없음")

    h1, h2 = st.columns([3, 2])
    with h1:
        st.markdown('<div class="chart-caption" style="padding-top:6px;">월별/주차별 앱 가입현황</div>',
                    unsafe_allow_html=True)
    with h2:
        view_unit = st.radio("조회 단위", ["월별", "주차별"], horizontal=True,
                             key="signup_unit", label_visibility="collapsed")

    @st.cache_data(ttl=300)
    def get_signup(unit):
        grp = "TO_CHAR(CREATED_AT, 'YYYY-MM')" if unit == "월별" \
              else "TO_CHAR(DATE_TRUNC('WEEK', CREATED_AT), 'YYYY-MM-DD')"
        df = session.sql(f"""
            SELECT {grp} AS "기간_str", COUNT(*) AS "가입수"
            FROM AJDCAR_PROD.PUBLIC.USERS
            WHERE CREATED_AT IS NOT NULL
              AND USER_NAME NOT LIKE '%테스트%'
            GROUP BY 1 ORDER BY 1 DESC
        """).to_pandas()
        df.columns = ["기간_str", "가입수"]
        return df

    df_sg = get_signup(view_unit)
    if not df_sg.empty:
        period_order = list(df_sg["기간_str"])
        bar_sg = alt.Chart(df_sg).mark_bar(color=BAR_MAIN).encode(
            x=alt.X("기간_str:N", title="기간", sort=period_order,
                    axis=alt.Axis(labelAngle=-45)),
            y=alt.Y("가입수:Q", title="가입수"),
            tooltip=[alt.Tooltip("기간_str:N", title="기간"),
                     alt.Tooltip("가입수:Q", format=",")]
        )
        lbl_sg = alt.Chart(df_sg).mark_text(dy=-6, fontSize=11, fontWeight=600,
                                             color="#333333").encode(
            x=alt.X("기간_str:N", sort=period_order),
            y=alt.Y("가입수:Q"),
            text=alt.Text("가입수:Q", format=",")
        )
        st.altair_chart(apply_theme(
            (bar_sg + lbl_sg).properties(height=280, background=CHART_BG)
        ), use_container_width=True)
    else:
        st.info("데이터 없음")

    # ── 필터 ──────────────────────────────────────
    st.markdown('<div class="section-title">상세 분석 (필터)</div>', unsafe_allow_html=True)

    default_from = this_month_start - relativedelta(months=4)
    f1, f2, f3, f4 = st.columns(4)
    with f1: date_from = st.date_input("시작일", value=default_from)
    with f2: date_to   = st.date_input("종료일", value=today)
    with f3: sel_mgr   = st.selectbox("담당매니저", ["전체"] + MANAGER_LIST)
    with f4: sel_ch    = st.selectbox("영업채널", ["전체", "갱신", "CS", "딜러앱", "기타"])

    mgr_filter = "" if sel_mgr == "전체" else f"AND m.NAME = '{sel_mgr}'"
    ch_filter  = "" if sel_ch  == "전체" else f"AND ({CH_EXPR}) = '{sel_ch}'"

    # ── 체결월별 영업채널 보험료 ───────────────────
    st.markdown('<div class="section-title">체결월별 영업채널 원수보험료</div>', unsafe_allow_html=True)

    ph1, ph2 = st.columns([5, 1])
    with ph1:
        st.markdown('<div class="chart-caption" style="padding-top:6px;">월별 &nbsp;/&nbsp; 주차별 →</div>',
                    unsafe_allow_html=True)
    with ph2:
        period_unit = st.radio("기간 단위", ["월별", "주차별"], horizontal=True,
                               key="period_unit", label_visibility="collapsed")

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
            WHERE ca.COUNSEL_STATUS = 'JOIN_COMPLETED'
              AND ca.JOIN_COMPLETED_AT IS NOT NULL
              AND (ca.IS_DELETED = FALSE OR ca.IS_DELETED IS NULL)
              AND ca.JOIN_COMPLETED_AT::DATE BETWEEN '{d_from}' AND '{d_to}'
              AND (m.NAME IS NULL OR m.NAME NOT LIKE '%테스트%')
              {mgr_f} {ch_f}
            GROUP BY 1, 2 ORDER BY 1 DESC
        """).to_pandas()
        df.columns = ["기간", "채널", "원수보험료"]
        return df

    df_ch = get_channel_premium(date_from, date_to, mgr_filter, ch_filter, period_unit)
    if not df_ch.empty:
        period_order_ch = list(df_ch["기간"].unique())
        totals_ch = df_ch.groupby("기간")["원수보험료"].sum().reset_index()
        totals_ch.columns = ["기간", "합계"]
        bar_ch = alt.Chart(df_ch).mark_bar().encode(
            x=alt.X("기간:N", sort=period_order_ch, title="기간",
                    axis=alt.Axis(labelAngle=-45)),
            y=alt.Y("원수보험료:Q", title="원수보험료(원)", axis=alt.Axis(format=",.0f")),
            color=alt.Color("채널:N", legend=alt.Legend(title="채널")),
            tooltip=[alt.Tooltip("기간:N"), alt.Tooltip("채널:N"),
                     alt.Tooltip("원수보험료:Q", format=",.0f")]
        )
        lbl_ch = alt.Chart(totals_ch).mark_text(dy=-6, fontSize=11, color="#333333").encode(
            x=alt.X("기간:N", sort=period_order_ch),
            y=alt.Y("합계:Q"),
            text=alt.Text("합계:Q", format=",.0f")
        )
        st.altair_chart(apply_theme(
            (bar_ch + lbl_ch).properties(height=300, background=CHART_BG)
        ), use_container_width=True)
    else:
        st.info("데이터 없음")

    # ── 딜러 현황 ─────────────────────────────────
    st.markdown('<div class="section-title">딜러 현황</div>', unsafe_allow_html=True)
    dl1, dl2 = st.columns(2)

    with dl1:
        st.markdown('<div class="chart-caption">체결월별 가동딜러수</div>', unsafe_allow_html=True)

        @st.cache_data(ttl=300)
        def get_active_dealer_monthly(d_from, d_to, mgr_f):
            df = session.sql(f"""
                SELECT
                    TO_CHAR(ca.JOIN_COMPLETED_AT, 'YYYY-MM') AS "월",
                    COUNT(DISTINCT ca.USER_ID) AS "가동딜러수"
                FROM AJDCAR_PROD.PUBLIC.COUNSEL_APPLICATION ca
                LEFT JOIN AJDCAR_PROD.PUBLIC.MANAGER m ON ca.COUNSEL_MANAGER_ID = m.ID
                WHERE ca.COUNSEL_STATUS = 'JOIN_COMPLETED'
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
            month_order = list(df_adm["월"])
            st.altair_chart(apply_theme(
                alt.Chart(df_adm).mark_bar(color="#6a9fd8").encode(
                    x=alt.X("월:N", sort=month_order, title=None,
                            axis=alt.Axis(labelAngle=-30)),
                    y=alt.Y("가동딜러수:Q", title="가동딜러수"),
                    tooltip=[alt.Tooltip("월:N"), alt.Tooltip("가동딜러수:Q", format=",")]
                ).properties(height=220, background=CHART_BG)
            ), use_container_width=True)
        else:
            st.info("데이터 없음")

    with dl2:
        st.markdown('<div class="chart-caption">딜러그룹별 인당 원수보험료</div>', unsafe_allow_html=True)

        @st.cache_data(ttl=300)
        def get_per_dealer(d_from, d_to):
            df = session.sql(f"""
                SELECT
                    COALESCE(u.BUSINESS_TYPE, '미분류') AS "딜러유형",
                    SUM(cv.CONTRACT_AMOUNT) / NULLIF(COUNT(DISTINCT ca.USER_ID), 0) AS "인당원수보험료"
                FROM AJDCAR_PROD.PUBLIC.COUNSEL_APPLICATION ca
                LEFT JOIN AJDCAR_PROD.PUBLIC.COUNSEL_VEHICLE cv
                    ON ca.COUNSEL_ID = cv.COUNSEL_ID
                    AND (cv.IS_DELETED = FALSE OR cv.IS_DELETED IS NULL)
                LEFT JOIN AJDCAR_PROD.PUBLIC.USERS u ON ca.USER_ID = u.ID
                WHERE ca.COUNSEL_STATUS = 'JOIN_COMPLETED'
                  AND ca.JOIN_COMPLETED_AT IS NOT NULL
                  AND (ca.IS_DELETED = FALSE OR ca.IS_DELETED IS NULL)
                  AND ca.JOIN_COMPLETED_AT::DATE BETWEEN '{d_from}' AND '{d_to}'
                  AND u.USER_NAME NOT LIKE '%테스트%'
                GROUP BY 1 ORDER BY 2 DESC
            """).to_pandas()
            df.columns = ["딜러유형", "인당원수보험료"]
            return df

        df_pd = get_per_dealer(date_from, date_to)
        if not df_pd.empty:
            st.altair_chart(apply_theme(
                alt.Chart(df_pd).mark_bar(color="#f4a261").encode(
                    y=alt.Y("딜러유형:N", sort="-x", title=None),
                    x=alt.X("인당원수보험료:Q", title="인당 원수보험료(원)",
                            axis=alt.Axis(format=",.0f")),
                    tooltip=[alt.Tooltip("딜러유형:N"),
                             alt.Tooltip("인당원수보험료:Q", format=",.0f")]
                ).properties(height=220, background=CHART_BG)
            ), use_container_width=True)
        else:
            st.info("데이터 없음")

    # ── 당월 보험사별 현황 ─────────────────────────
    # JOIN_INSURER_CODE는 COUNSEL_APPLICATION(ca)에 있음
    st.markdown('<div class="section-title">당월 보험사별 현황</div>', unsafe_allow_html=True)

    @st.cache_data(ttl=300)
    def get_insurer_monthly():
        df = session.sql("""
            SELECT
                COALESCE(ca.JOIN_INSURER_CODE, '미분류') AS "보험사",
                SUM(cv.CONTRACT_AMOUNT) AS "원수보험료",
                COUNT(*) AS "건수"
            FROM AJDCAR_PROD.PUBLIC.COUNSEL_APPLICATION ca
            LEFT JOIN AJDCAR_PROD.PUBLIC.COUNSEL_VEHICLE cv
                ON ca.COUNSEL_ID = cv.COUNSEL_ID
                AND (cv.IS_DELETED = FALSE OR cv.IS_DELETED IS NULL)
            WHERE ca.COUNSEL_STATUS = 'JOIN_COMPLETED'
              AND ca.JOIN_COMPLETED_AT IS NOT NULL
              AND (ca.IS_DELETED = FALSE OR ca.IS_DELETED IS NULL)
              AND DATE_TRUNC('MONTH', ca.JOIN_COMPLETED_AT) = DATE_TRUNC('MONTH', CURRENT_DATE)
            GROUP BY 1 ORDER BY 2 DESC
        """).to_pandas()
        df.columns = ["보험사", "원수보험료", "건수"]
        return df

    df_ins = get_insurer_monthly()
    i1, i2 = st.columns(2)
    with i1:
        st.markdown('<div class="chart-caption">원수보험료</div>', unsafe_allow_html=True)
        if not df_ins.empty:
            st.altair_chart(apply_theme(
                alt.Chart(df_ins).mark_bar(color=BAR_MAIN).encode(
                    y=alt.Y("보험사:N", sort="-x", title=None),
                    x=alt.X("원수보험료:Q", title="원수보험료(원)",
                            axis=alt.Axis(format=",.0f")),
                    tooltip=[alt.Tooltip("보험사:N"),
                             alt.Tooltip("원수보험료:Q", format=",.0f")]
                ).properties(height=220, background=CHART_BG)
            ), use_container_width=True)
        else:
            st.info("데이터 없음")

    with i2:
        st.markdown('<div class="chart-caption">건수</div>', unsafe_allow_html=True)
        if not df_ins.empty:
            st.altair_chart(apply_theme(
                alt.Chart(df_ins).mark_bar(color="#5ba85a").encode(
                    y=alt.Y("보험사:N", sort="-x", title=None),
                    x=alt.X("건수:Q", title="건수"),
                    tooltip=[alt.Tooltip("보험사:N"), alt.Tooltip("건수:Q", format=",")]
                ).properties(height=220, background=CHART_BG)
            ), use_container_width=True)
        else:
            st.info("데이터 없음")

    # ── 직전 3개월 피벗 표 ────────────────────────
    st.markdown('<div class="section-title">직전 3개월 보험사 × 채널별 원수보험료</div>',
                unsafe_allow_html=True)

    @st.cache_data(ttl=300)
    def get_pivot_3m():
        df = session.sql(f"""
            SELECT
                TO_CHAR(ca.JOIN_COMPLETED_AT, 'YYYY-MM') AS "월",
                COALESCE(ca.JOIN_INSURER_CODE, '미분류') AS "보험사",
                {CH_EXPR} AS "채널",
                SUM(cv.CONTRACT_AMOUNT) AS "원수보험료"
            FROM AJDCAR_PROD.PUBLIC.COUNSEL_APPLICATION ca
            LEFT JOIN AJDCAR_PROD.PUBLIC.COUNSEL_VEHICLE cv
                ON ca.COUNSEL_ID = cv.COUNSEL_ID
                AND (cv.IS_DELETED = FALSE OR cv.IS_DELETED IS NULL)
            WHERE ca.COUNSEL_STATUS = 'JOIN_COMPLETED'
              AND ca.JOIN_COMPLETED_AT IS NOT NULL
              AND (ca.IS_DELETED = FALSE OR ca.IS_DELETED IS NULL)
              AND ca.JOIN_COMPLETED_AT >= DATEADD('MONTH', -3, DATE_TRUNC('MONTH', CURRENT_DATE))
            GROUP BY 1, 2, 3 ORDER BY 1 DESC, 2, 3
        """).to_pandas()
        df.columns = ["월", "보험사", "채널", "원수보험료"]
        return df

    df_pv = get_pivot_3m()
    if not df_pv.empty:
        month_cols = sorted(df_pv["월"].unique(), reverse=True)
        pivot = df_pv.pivot_table(
            index=["보험사", "채널"], columns="월",
            values="원수보험료", aggfunc="sum", fill_value=0
        ).reset_index()
        ordered_cols = ["보험사", "채널"] + [c for c in month_cols if c in pivot.columns]
        pivot = pivot[ordered_cols]
        for c in month_cols:
            if c in pivot.columns:
                pivot[c] = pivot[c].apply(lambda x: f"{int(x):,}" if x else "-")
        st.dataframe(pivot, use_container_width=True, hide_index=True)
    else:
        st.info("데이터 없음")

    # ── 인입채널 빈 표 ────────────────────────────
    st.markdown('<div class="section-title">인입채널별 현황 (오프팀/상조회/B2B)</div>',
                unsafe_allow_html=True)
    st.markdown('<div class="empty-box">데이터 준비중입니다</div>', unsafe_allow_html=True)

    # ── 리텐션 딜러 현황 ──────────────────────────
    st.markdown('<div class="section-title">리텐션 딜러 현황</div>', unsafe_allow_html=True)

    ret_months = []
    _d = today.replace(day=1)
    for _ in range(12):
        ret_months.append(_d.strftime("%Y-%m"))
        _d = (_d - timedelta(days=1)).replace(day=1)

    sel_base_month = st.selectbox("기준월 선택", ret_months, key="ret_base_month")
    _y, _m = int(sel_base_month[:4]), int(sel_base_month[5:7])
    _last_day = calendar.monthrange(_y, _m)[1]
    base_date = date(_y, _m, _last_day)
    base_str  = base_date.strftime("%Y-%m-%d")
    ref_60    = (base_date - timedelta(days=60)).strftime("%Y-%m-%d")

    st.caption(f"기준일: {base_str} (해당 월 말일 기준)")

    @st.cache_data(ttl=600)
    def get_retention_summary(base_str, ref_60):
        r = session.sql(f"""
            WITH contract_summary AS (
                SELECT
                    u.ID                AS user_id,
                    u.USER_NAME,
                    u.IS_ASSOCIATE,
                    u.CREATED_AT::DATE  AS reg_date,
                    COUNT(ca.COUNSEL_ID) AS total_cnt,
                    MAX(CASE WHEN ca.COUNSEL_STATUS = 'JOIN_COMPLETED'
                                  AND ca.JOIN_COMPLETED_AT::DATE BETWEEN '{ref_60}' AND '{base_str}'
                             THEN 1 ELSE 0 END) AS recent_act
                FROM AJDCAR_PROD.PUBLIC.USERS u
                LEFT JOIN AJDCAR_PROD.PUBLIC.COUNSEL_APPLICATION ca
                    ON u.ID = ca.USER_ID
                    AND ca.COUNSEL_STATUS = 'JOIN_COMPLETED'
                    AND ca.JOIN_COMPLETED_AT::DATE <= '{base_str}'
                    AND (ca.IS_DELETED = FALSE OR ca.IS_DELETED IS NULL)
                WHERE u.USER_NAME NOT LIKE '%테스트%'
                GROUP BY 1,2,3,4
            )
            SELECT
                SUM(CASE WHEN IS_ASSOCIATE = 0 AND total_cnt = 1  AND recent_act = 0 THEN 1 ELSE 0 END) AS cat1,
                SUM(CASE WHEN IS_ASSOCIATE = 0 AND total_cnt >= 2 AND recent_act = 0 THEN 1 ELSE 0 END) AS cat2,
                SUM(CASE WHEN IS_ASSOCIATE = 0 AND total_cnt = 0
                              AND reg_date <= DATEADD('DAY', -60, '{base_str}') THEN 1 ELSE 0 END) AS cat3,
                SUM(CASE WHEN IS_ASSOCIATE = 1 AND total_cnt >= 1 AND recent_act = 0 THEN 1 ELSE 0 END) AS cat4
            FROM contract_summary
        """).collect()
        return r[0]

    @st.cache_data(ttl=600)
    def get_retention_raw(category, base_str, ref_60):
        if category == 1:
            cond = "IS_ASSOCIATE = 0 AND total_cnt = 1 AND recent_act = 0"
        elif category == 2:
            cond = "IS_ASSOCIATE = 0 AND total_cnt >= 2 AND recent_act = 0"
        elif category == 3:
            cond = f"IS_ASSOCIATE = 0 AND total_cnt = 0 AND reg_date <= DATEADD('DAY', -60, '{base_str}')"
        else:
            cond = "IS_ASSOCIATE = 1 AND total_cnt >= 1 AND recent_act = 0"

        df = session.sql(f"""
            WITH contract_summary AS (
                SELECT
                    u.ID                AS user_id,
                    u.USER_ID           AS login_id,
                    u.USER_NAME         AS dealer_name,
                    u.IS_ASSOCIATE,
                    u.CREATED_AT::DATE  AS reg_date,
                    m.NAME              AS manager_name,
                    COUNT(ca.COUNSEL_ID)            AS total_cnt,
                    MAX(ca.JOIN_COMPLETED_AT::DATE) AS last_contract_date,
                    MAX(CASE WHEN ca.COUNSEL_STATUS = 'JOIN_COMPLETED'
                                  AND ca.JOIN_COMPLETED_AT::DATE BETWEEN '{ref_60}' AND '{base_str}'
                             THEN 1 ELSE 0 END) AS recent_act
                FROM AJDCAR_PROD.PUBLIC.USERS u
                LEFT JOIN AJDCAR_PROD.PUBLIC.MANAGER m ON u.MANAGER_ID = m.ID
                LEFT JOIN AJDCAR_PROD.PUBLIC.COUNSEL_APPLICATION ca
                    ON u.ID = ca.USER_ID
                    AND ca.COUNSEL_STATUS = 'JOIN_COMPLETED'
                    AND ca.JOIN_COMPLETED_AT::DATE <= '{base_str}'
                    AND (ca.IS_DELETED = FALSE OR ca.IS_DELETED IS NULL)
                WHERE u.USER_NAME NOT LIKE '%테스트%'
                GROUP BY 1, 2, 3, 4, 5, 6
            )
            SELECT
                login_id           AS "로그인ID",
                dealer_name        AS "딜러명",
                manager_name       AS "담당매니저",
                IS_ASSOCIATE       AS "준회원여부",
                reg_date           AS "가입일",
                total_cnt          AS "총체결건수",
                last_contract_date AS "마지막체결일"
            FROM contract_summary
            WHERE {cond}
            ORDER BY total_cnt DESC, reg_date
        """).to_pandas()
        df.columns = ["로그인ID", "딜러명", "담당매니저", "준회원여부", "가입일", "총체결건수", "마지막체결일"]
        return df

    ret_summary = get_retention_summary(base_str, ref_60)
    cat_labels = [
        ("1회 체결 후 미활동", "cat1", "IS_ASSOCIATE=0, 총 체결 1건, 직전 60일 미활동"),
        ("2회 이상 체결 후 미활동", "cat2", "IS_ASSOCIATE=0, 총 체결 ≥2건, 직전 60일 미활동"),
        ("미체결 딜러", "cat3", "IS_ASSOCIATE=0, 계약 0건, 가입 후 60일 초과"),
        ("준회원 미활동", "cat4", "IS_ASSOCIATE=1, 체결 ≥1건, 직전 60일 미활동"),
    ]

    rc1, rc2, rc3, rc4 = st.columns(4)
    for col, (lbl, key, desc), cat_num in zip(
        [rc1, rc2, rc3, rc4], cat_labels, [1, 2, 3, 4]
    ):
        cnt = ret_summary[key.upper()] or 0
        with col:
            st.markdown(kpi_card(lbl, f"{cnt:,}명", desc, "neutral"), unsafe_allow_html=True)

    for cat_num, (lbl, key, desc) in enumerate(cat_labels, 1):
        cnt = ret_summary[key.upper()] or 0
        with st.expander(f"▶ {lbl} ({cnt:,}명) 상세"):
            df_raw = get_retention_raw(cat_num, base_str, ref_60)
            if df_raw.empty:
                st.info("해당 딜러 없음")
            else:
                st.dataframe(df_raw, use_container_width=True, hide_index=True)
                csv = df_raw.to_csv(index=False, encoding="utf-8-sig")
                st.download_button(
                    label="⬇ CSV 다운로드", data=csv,
                    file_name=f"retention_cat{cat_num}_{sel_base_month}.csv",
                    mime="text/csv", key=f"dl_{cat_num}"
                )


# ═══════════════════════════════════════════════════════════════
# TAB 2 — 보험사별 현황
# ═══════════════════════════════════════════════════════════════
with tab2:

    st.markdown("""
    <div class="criteria-box">
    📌 <b>집계 기준</b><br>
    • 보험사 구분: <code>COUNSEL_APPLICATION.JOIN_INSURER_CODE</code> 기준<br>
    • 집계 대상 상태: JOIN_COMPLETED + COMPARISON_COMPLETED<br>
    • 테스트 매니저(이름에 '테스트' 포함) 제외 / 삭제건(IS_DELETED=TRUE) 제외<br>
    • G속성: USERS.BUSINESS_TYPE + BUSINESS_SUB_TYPE 조합
    </div>
    """, unsafe_allow_html=True)

    bi1, bi2, bi3 = st.columns(3)
    with bi1: ins_from  = st.date_input("시작일", value=date(today.year, 1, 1), key="ins_from")
    with bi2: ins_to    = st.date_input("종료일", value=today, key="ins_to")
    with bi3: ins_mgr   = st.selectbox("담당매니저", ["전체"] + MANAGER_LIST, key="ins_mgr")

    ins_mgr_f = "" if ins_mgr == "전체" else f"AND m.NAME = '{ins_mgr}'"

    # 당월 KPI
    st.markdown('<div class="section-title">당월 보험사별 현황</div>', unsafe_allow_html=True)

    @st.cache_data(ttl=300)
    def get_ins_cur_month():
        df = session.sql("""
            SELECT
                COALESCE(ca.JOIN_INSURER_CODE, '미분류') AS "보험사",
                SUM(cv.CONTRACT_AMOUNT) AS "원수보험료",
                COUNT(*) AS "건수"
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

    df_ic = get_ins_cur_month()
    ic1, ic2 = st.columns(2)
    with ic1:
        st.caption("원수보험료")
        if not df_ic.empty:
            st.altair_chart(apply_theme(
                alt.Chart(df_ic).mark_bar(color=BAR_MAIN).encode(
                    y=alt.Y("보험사:N", sort="-x", title=None),
                    x=alt.X("원수보험료:Q", title="원수보험료(원)", axis=alt.Axis(format=",.0f")),
                    tooltip=[alt.Tooltip("보험사:N"),
                             alt.Tooltip("원수보험료:Q", format=",.0f"),
                             alt.Tooltip("건수:Q", format=",")]
                ).properties(height=240, background=CHART_BG)
            ), use_container_width=True)
        else:
            st.info("데이터 없음")
    with ic2:
        st.caption("체결건수")
        if not df_ic.empty:
            st.altair_chart(apply_theme(
                alt.Chart(df_ic).mark_bar(color="#5ba85a").encode(
                    y=alt.Y("보험사:N", sort="-x", title=None),
                    x=alt.X("건수:Q", title="건수"),
                    tooltip=[alt.Tooltip("보험사:N"), alt.Tooltip("건수:Q", format=",")]
                ).properties(height=240, background=CHART_BG)
            ), use_container_width=True)
        else:
            st.info("데이터 없음")

    # 월별 추이
    st.markdown('<div class="section-title">월별 보험사별 원수보험료 추이</div>', unsafe_allow_html=True)

    @st.cache_data(ttl=300)
    def get_ins_trend(d_from, d_to, mgr_f):
        df = session.sql(f"""
            SELECT
                TO_CHAR(ca.JOIN_COMPLETED_AT, 'YYYY-MM') AS "월",
                COALESCE(ca.JOIN_INSURER_CODE, '미분류') AS "보험사",
                SUM(cv.CONTRACT_AMOUNT) AS "원수보험료",
                COUNT(*) AS "건수"
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
            GROUP BY 1, 2 ORDER BY 1 DESC, 3 DESC NULLS LAST
        """).to_pandas()
        df.columns = ["월", "보험사", "원수보험료", "건수"]
        return df

    df_it = get_ins_trend(ins_from, ins_to, ins_mgr_f)
    if not df_it.empty:
        order_it = sorted(df_it["월"].unique(), reverse=True)
        st.altair_chart(apply_theme(
            alt.Chart(df_it).mark_bar().encode(
                x=alt.X("월:N", sort=order_it, title="월", axis=alt.Axis(labelAngle=-45)),
                y=alt.Y("원수보험료:Q", title="원수보험료(원)", axis=alt.Axis(format=",.0f")),
                color=alt.Color("보험사:N", legend=alt.Legend(title="보험사")),
                tooltip=[alt.Tooltip("월:N"), alt.Tooltip("보험사:N"),
                         alt.Tooltip("원수보험료:Q", format=",.0f"),
                         alt.Tooltip("건수:Q", format=",")]
            ).properties(height=300, background=CHART_BG)
        ), use_container_width=True)
    else:
        st.info("데이터 없음")

    # 피벗 표 (직전 6개월)
    st.markdown('<div class="section-title">보험사별 월별 피벗 (직전 6개월)</div>', unsafe_allow_html=True)

    pv_view = st.radio("지표", ["원수보험료", "건수"], horizontal=True, key="ins_pv")

    @st.cache_data(ttl=300)
    def get_ins_pivot():
        df = session.sql(f"""
            SELECT
                TO_CHAR(ca.JOIN_COMPLETED_AT, 'YYYY-MM') AS "월",
                COALESCE(ca.JOIN_INSURER_CODE, '미분류') AS "보험사",
                {CH_EXPR} AS "채널",
                SUM(cv.CONTRACT_AMOUNT) AS "원수보험료",
                COUNT(*) AS "건수"
            FROM AJDCAR_PROD.PUBLIC.COUNSEL_APPLICATION ca
            LEFT JOIN AJDCAR_PROD.PUBLIC.COUNSEL_VEHICLE cv
                ON ca.COUNSEL_ID = cv.COUNSEL_ID
                AND (cv.IS_DELETED = FALSE OR cv.IS_DELETED IS NULL)
            WHERE ca.COUNSEL_STATUS IN ('JOIN_COMPLETED', 'COMPARISON_COMPLETED')
              AND ca.JOIN_COMPLETED_AT IS NOT NULL
              AND (ca.IS_DELETED = FALSE OR ca.IS_DELETED IS NULL)
              AND ca.JOIN_COMPLETED_AT >= DATEADD('MONTH', -6, DATE_TRUNC('MONTH', CURRENT_DATE))
            GROUP BY 1, 2, 3 ORDER BY 1 DESC, 2, 3
        """).to_pandas()
        df.columns = ["월", "보험사", "채널", "원수보험료", "건수"]
        return df

    df_ipv = get_ins_pivot()
    if not df_ipv.empty:
        pivot = df_ipv.pivot_table(
            index=["보험사", "채널"], columns="월",
            values=pv_view, aggfunc="sum", fill_value=0
        ).reset_index()
        m_cols = sorted([c for c in pivot.columns if c not in ["보험사","채널"]], reverse=True)
        pivot  = pivot[["보험사","채널"] + m_cols]
        for c in m_cols:
            if pv_view == "원수보험료":
                pivot[c] = pivot[c].apply(lambda x: f"{int(x):,}" if x else "-")
            else:
                pivot[c] = pivot[c].apply(lambda x: f"{int(x):,}건" if x else "-")
        st.dataframe(pivot, use_container_width=True, hide_index=True)
    else:
        st.info("데이터 없음")

    # G속성 × 보험사 분포
    st.markdown('<div class="section-title">G속성별 × 보험사별 원수보험료 분포</div>', unsafe_allow_html=True)

    @st.cache_data(ttl=300)
    def get_g_ins(d_from, d_to):
        df = session.sql(f"""
            SELECT
                {G_ATTR_EXPR} AS "G속성",
                COALESCE(ca.JOIN_INSURER_CODE, '미분류') AS "보험사",
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
            GROUP BY 1, 2 ORDER BY 1, 3 DESC NULLS LAST
        """).to_pandas()
        df.columns = ["G속성", "보험사", "원수보험료", "건수"]
        return df

    df_gi = get_g_ins(ins_from, ins_to)
    if not df_gi.empty:
        st.altair_chart(apply_theme(
            alt.Chart(df_gi).mark_bar().encode(
                x=alt.X("G속성:N", title="G속성"),
                y=alt.Y("원수보험료:Q", title="원수보험료(원)", axis=alt.Axis(format=",.0f")),
                color=alt.Color("보험사:N", legend=alt.Legend(title="보험사")),
                tooltip=[alt.Tooltip("G속성:N"), alt.Tooltip("보험사:N"),
                         alt.Tooltip("원수보험료:Q", format=",.0f"),
                         alt.Tooltip("건수:Q", format=",")]
            ).properties(height=300, background=CHART_BG)
        ), use_container_width=True)
    else:
        st.info("데이터 없음")


# ═══════════════════════════════════════════════════════════════
# TAB 3 — 취소건 현황
# ═══════════════════════════════════════════════════════════════
with tab3:

    st.markdown("""
    <div class="criteria-box">
    📌 <b>취소건 집계 기준</b><br>
    • <b>취소건</b>: COUNSEL_STATUS = 'JOIN_CANCELLED'<br>
    • <b>삭제건</b>: IS_DELETED = TRUE (status 무관)<br>
    • 날짜 기준: CREATED_AT (취소 처리 일자)<br>
    • 테스트 매니저(이름에 '테스트' 포함) 제외
    </div>
    """, unsafe_allow_html=True)

    cc1, cc2, cc3 = st.columns(3)
    with cc1: cancel_from = st.date_input("시작일", value=date(today.year, 1, 1), key="cancel_from")
    with cc2: cancel_to   = st.date_input("종료일", value=today, key="cancel_to")
    with cc3: cancel_mgr  = st.selectbox("담당매니저", ["전체"] + MANAGER_LIST, key="cancel_mgr")

    cancel_mgr_f = "" if cancel_mgr == "전체" else f"AND m.NAME = '{cancel_mgr}'"

    @st.cache_data(ttl=300)
    def get_cancel_kpi(d_from, d_to, mgr_f):
        r = session.sql(f"""
            SELECT
                COUNT(CASE WHEN ca.COUNSEL_STATUS = 'JOIN_CANCELLED' THEN 1 END)          AS "취소건수",
                COUNT(CASE WHEN ca.IS_DELETED = TRUE THEN 1 END)                          AS "삭제건수",
                COUNT(CASE WHEN DATE_TRUNC('MONTH', ca.CREATED_AT) = DATE_TRUNC('MONTH', CURRENT_DATE)
                                AND ca.COUNSEL_STATUS = 'JOIN_CANCELLED' THEN 1 END)      AS "당월취소",
                SUM(CASE WHEN ca.COUNSEL_STATUS = 'JOIN_CANCELLED'
                         THEN cv.CONTRACT_AMOUNT ELSE 0 END)                              AS "취소보험료합계"
            FROM AJDCAR_PROD.PUBLIC.COUNSEL_APPLICATION ca
            LEFT JOIN AJDCAR_PROD.PUBLIC.COUNSEL_VEHICLE cv ON ca.COUNSEL_ID = cv.COUNSEL_ID
            LEFT JOIN AJDCAR_PROD.PUBLIC.MANAGER m ON ca.COUNSEL_MANAGER_ID = m.ID
            WHERE ca.CREATED_AT::DATE BETWEEN '{d_from}' AND '{d_to}'
              AND (m.NAME IS NULL OR m.NAME NOT LIKE '%테스트%')
              {mgr_f}
        """).collect()
        return r[0]

    ck = get_cancel_kpi(cancel_from, cancel_to, cancel_mgr_f)
    ck1, ck2, ck3, ck4 = st.columns(4)
    with ck1: st.markdown(kpi_card("취소건수",      f"{ck['취소건수'] or 0:,}건"), unsafe_allow_html=True)
    with ck2: st.markdown(kpi_card("당월 취소건수",  f"{ck['당월취소'] or 0:,}건"), unsafe_allow_html=True)
    with ck3: st.markdown(kpi_card("삭제건수",      f"{ck['삭제건수'] or 0:,}건"), unsafe_allow_html=True)
    with ck4: st.markdown(kpi_card("취소 원수보험료 합계",
                                    fmt_won(ck["취소보험료합계"] or 0)), unsafe_allow_html=True)

    st.markdown('<div class="section-title">월별 취소건수 추이</div>', unsafe_allow_html=True)

    @st.cache_data(ttl=300)
    def get_cancel_monthly(d_from, d_to, mgr_f):
        df = session.sql(f"""
            SELECT
                TO_CHAR(ca.CREATED_AT, 'YYYY-MM') AS "월",
                COUNT(*) AS "취소건수",
                SUM(cv.CONTRACT_AMOUNT) AS "취소보험료"
            FROM AJDCAR_PROD.PUBLIC.COUNSEL_APPLICATION ca
            LEFT JOIN AJDCAR_PROD.PUBLIC.COUNSEL_VEHICLE cv ON ca.COUNSEL_ID = cv.COUNSEL_ID
            LEFT JOIN AJDCAR_PROD.PUBLIC.MANAGER m ON ca.COUNSEL_MANAGER_ID = m.ID
            WHERE ca.COUNSEL_STATUS = 'JOIN_CANCELLED'
              AND ca.CREATED_AT::DATE BETWEEN '{d_from}' AND '{d_to}'
              AND (m.NAME IS NULL OR m.NAME NOT LIKE '%테스트%')
              {mgr_f}
            GROUP BY 1 ORDER BY 1 DESC
        """).to_pandas()
        df.columns = ["월", "취소건수", "취소보험료"]
        return df

    df_cm = get_cancel_monthly(cancel_from, cancel_to, cancel_mgr_f)
    cmc1, cmc2 = st.columns(2)
    with cmc1:
        st.caption("월별 취소건수")
        if not df_cm.empty:
            order_cm = list(df_cm["월"])
            st.altair_chart(apply_theme(
                alt.Chart(df_cm).mark_bar(color="#e03131").encode(
                    x=alt.X("월:N", sort=order_cm, title=None, axis=alt.Axis(labelAngle=-45)),
                    y=alt.Y("취소건수:Q", title="취소건수"),
                    tooltip=[alt.Tooltip("월:N"), alt.Tooltip("취소건수:Q", format=",")]
                ).properties(height=240, background=CHART_BG)
            ), use_container_width=True)
        else:
            st.info("데이터 없음")
    with cmc2:
        st.caption("월별 취소 원수보험료")
        if not df_cm.empty:
            st.altair_chart(apply_theme(
                alt.Chart(df_cm).mark_bar(color="#f4a261").encode(
                    x=alt.X("월:N", sort=list(df_cm["월"]), title=None,
                            axis=alt.Axis(labelAngle=-45)),
                    y=alt.Y("취소보험료:Q", title="원수보험료(원)", axis=alt.Axis(format=",.0f")),
                    tooltip=[alt.Tooltip("월:N"), alt.Tooltip("취소보험료:Q", format=",.0f")]
                ).properties(height=240, background=CHART_BG)
            ), use_container_width=True)
        else:
            st.info("데이터 없음")

    st.markdown('<div class="section-title">보험사별 / 채널별 취소 현황</div>', unsafe_allow_html=True)

    @st.cache_data(ttl=300)
    def get_cancel_by_insurer(d_from, d_to, mgr_f):
        df = session.sql(f"""
            SELECT
                COALESCE(ca.JOIN_INSURER_CODE, '미분류') AS "보험사",
                COUNT(*) AS "취소건수",
                SUM(cv.CONTRACT_AMOUNT) AS "취소보험료"
            FROM AJDCAR_PROD.PUBLIC.COUNSEL_APPLICATION ca
            LEFT JOIN AJDCAR_PROD.PUBLIC.COUNSEL_VEHICLE cv ON ca.COUNSEL_ID = cv.COUNSEL_ID
            LEFT JOIN AJDCAR_PROD.PUBLIC.MANAGER m ON ca.COUNSEL_MANAGER_ID = m.ID
            WHERE ca.COUNSEL_STATUS = 'JOIN_CANCELLED'
              AND ca.CREATED_AT::DATE BETWEEN '{d_from}' AND '{d_to}'
              AND (m.NAME IS NULL OR m.NAME NOT LIKE '%테스트%')
              {mgr_f}
            GROUP BY 1 ORDER BY 2 DESC NULLS LAST
        """).to_pandas()
        df.columns = ["보험사", "취소건수", "취소보험료"]
        return df

    @st.cache_data(ttl=300)
    def get_cancel_by_channel(d_from, d_to, mgr_f):
        df = session.sql(f"""
            SELECT
                {CH_EXPR} AS "채널",
                COUNT(*) AS "취소건수",
                SUM(cv.CONTRACT_AMOUNT) AS "취소보험료"
            FROM AJDCAR_PROD.PUBLIC.COUNSEL_APPLICATION ca
            LEFT JOIN AJDCAR_PROD.PUBLIC.COUNSEL_VEHICLE cv ON ca.COUNSEL_ID = cv.COUNSEL_ID
            LEFT JOIN AJDCAR_PROD.PUBLIC.MANAGER m ON ca.COUNSEL_MANAGER_ID = m.ID
            WHERE ca.COUNSEL_STATUS = 'JOIN_CANCELLED'
              AND ca.CREATED_AT::DATE BETWEEN '{d_from}' AND '{d_to}'
              AND (m.NAME IS NULL OR m.NAME NOT LIKE '%테스트%')
              {mgr_f}
            GROUP BY 1 ORDER BY 2 DESC
        """).to_pandas()
        df.columns = ["채널", "취소건수", "취소보험료"]
        return df

    df_ci = get_cancel_by_insurer(cancel_from, cancel_to, cancel_mgr_f)
    df_cc = get_cancel_by_channel(cancel_from, cancel_to, cancel_mgr_f)
    ct1, ct2 = st.columns(2)
    with ct1:
        st.caption("보험사별 취소")
        if not df_ci.empty:
            st.dataframe(df_ci, use_container_width=True, hide_index=True)
        else:
            st.info("데이터 없음")
    with ct2:
        st.caption("채널별 취소")
        if not df_cc.empty:
            st.dataframe(df_cc, use_container_width=True, hide_index=True)
        else:
            st.info("데이터 없음")

    st.markdown('<div class="section-title">취소건 상세 목록 (최대 500건)</div>', unsafe_allow_html=True)

    @st.cache_data(ttl=300)
    def get_cancel_detail(d_from, d_to, mgr_f):
        df = session.sql(f"""
            SELECT
                ca.COUNSEL_ID                              AS "상담ID",
                ca.CREATED_AT::DATE                        AS "생성일",
                m.NAME                                     AS "담당매니저",
                u.USER_NAME                                AS "딜러명",
                COALESCE(ca.JOIN_INSURER_CODE, '미분류')   AS "보험사",
                {CH_EXPR}                                  AS "채널",
                cv.CONTRACT_AMOUNT                         AS "원수보험료",
                ca.COUNSEL_STATUS                          AS "상태"
            FROM AJDCAR_PROD.PUBLIC.COUNSEL_APPLICATION ca
            LEFT JOIN AJDCAR_PROD.PUBLIC.COUNSEL_VEHICLE cv ON ca.COUNSEL_ID = cv.COUNSEL_ID
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

    with st.expander("취소건 상세 목록 보기"):
        df_cd = get_cancel_detail(cancel_from, cancel_to, cancel_mgr_f)
        if not df_cd.empty:
            st.dataframe(df_cd, use_container_width=True, hide_index=True)
            st.download_button("⬇ CSV 다운로드",
                               df_cd.to_csv(index=False, encoding="utf-8-sig"),
                               "cancel_detail.csv", "text/csv")
        else:
            st.info("데이터 없음")


# ═══════════════════════════════════════════════════════════════
# TAB 4 — 비활동 딜러 현황
# ═══════════════════════════════════════════════════════════════
with tab4:

    st.markdown("""
    <div class="criteria-box">
    📌 <b>비활동 딜러 4가지 분류 기준</b><br>
    • <b>유형1 — 미체결</b>: 정회원(IS_ASSOCIATE=0), 가입 후 60일 초과, 누적 체결 0건<br>
    • <b>유형2 — 1회 후 미활동</b>: 정회원, 누적 체결 1건, 직전 60일 내 체결 없음<br>
    • <b>유형3 — 2회↑ 후 미활동</b>: 정회원, 누적 체결 ≥2건, 직전 60일 내 체결 없음<br>
    • <b>유형4 — 준회원 미활동</b>: 준회원(IS_ASSOCIATE=1), 체결 ≥1건, 직전 60일 내 체결 없음<br>
    • 기준일: 선택한 월의 말일 / G속성: USERS.BUSINESS_TYPE + BUSINESS_SUB_TYPE
    </div>
    """, unsafe_allow_html=True)

    ina_cols = st.columns(2)
    with ina_cols[0]:
        ina_months = []
        _d2 = today.replace(day=1)
        for _ in range(12):
            ina_months.append(_d2.strftime("%Y-%m"))
            _d2 = (_d2 - timedelta(days=1)).replace(day=1)
        ina_base_month = st.selectbox("기준월 선택", ina_months, key="ina_base_month")
    with ina_cols[1]:
        ina_mgr = st.selectbox("담당매니저 필터", ["전체"] + MANAGER_LIST, key="ina_mgr")

    _iy, _im = int(ina_base_month[:4]), int(ina_base_month[5:7])
    _ild  = calendar.monthrange(_iy, _im)[1]
    ina_base_date = date(_iy, _im, _ild)
    ina_base_str  = ina_base_date.strftime("%Y-%m-%d")
    ina_ref_60    = (ina_base_date - timedelta(days=60)).strftime("%Y-%m-%d")
    ina_mgr_cond  = "" if ina_mgr == "전체" else f"AND m.NAME = '{ina_mgr}'"

    st.caption(f"기준일: {ina_base_str} / 직전 60일: {ina_ref_60} ~ {ina_base_str}")

    @st.cache_data(ttl=600)
    def get_inactive_summary(base_str, ref_60, mgr_cond):
        r = session.sql(f"""
            WITH cs AS (
                SELECT
                    u.ID               AS uid,
                    u.IS_ASSOCIATE,
                    u.CREATED_AT::DATE AS reg_date,
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
                SUM(CASE WHEN IS_ASSOCIATE=0 AND total_cnt=0
                              AND reg_date <= DATEADD('DAY',-60,'{base_str}') THEN 1 ELSE 0 END) AS cat1,
                SUM(CASE WHEN IS_ASSOCIATE=0 AND total_cnt=1  AND recent_act=0 THEN 1 ELSE 0 END) AS cat2,
                SUM(CASE WHEN IS_ASSOCIATE=0 AND total_cnt>=2 AND recent_act=0 THEN 1 ELSE 0 END) AS cat3,
                SUM(CASE WHEN IS_ASSOCIATE=1 AND total_cnt>=1 AND recent_act=0 THEN 1 ELSE 0 END) AS cat4
            FROM cs
        """).collect()
        return r[0]

    @st.cache_data(ttl=600)
    def get_inactive_raw(category, base_str, ref_60, mgr_cond):
        cond_map = {
            1: f"IS_ASSOCIATE=0 AND total_cnt=0 AND reg_date<=DATEADD('DAY',-60,'{base_str}')",
            2: "IS_ASSOCIATE=0 AND total_cnt=1 AND recent_act=0",
            3: "IS_ASSOCIATE=0 AND total_cnt>=2 AND recent_act=0",
            4: "IS_ASSOCIATE=1 AND total_cnt>=1 AND recent_act=0",
        }
        df = session.sql(f"""
            WITH cs AS (
                SELECT
                    u.USER_ID           AS login_id,
                    u.USER_NAME         AS dealer_name,
                    u.IS_ASSOCIATE,
                    u.CREATED_AT::DATE  AS reg_date,
                    m.NAME              AS manager_name,
                    {G_ATTR_EXPR}       AS g_attr,
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
                GROUP BY 1,2,3,4,5,6
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
            FROM cs WHERE {cond_map[category]}
            ORDER BY total_cnt DESC, reg_date
        """).to_pandas()
        df.columns = ["로그인ID","딜러명","담당매니저","G속성","준회원여부","가입일","총체결건수","마지막체결일"]
        return df

    @st.cache_data(ttl=600)
    def get_inactive_g_dist(base_str, ref_60, mgr_cond):
        df = session.sql(f"""
            WITH cs AS (
                SELECT
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
                GROUP BY 1,2,3
            )
            SELECT
                g_attr AS "G속성",
                SUM(CASE WHEN IS_ASSOCIATE=0 AND total_cnt=0
                              AND reg_date<=DATEADD('DAY',-60,'{base_str}') THEN 1 ELSE 0 END) AS "미체결",
                SUM(CASE WHEN IS_ASSOCIATE=0 AND total_cnt=1  AND recent_act=0 THEN 1 ELSE 0 END) AS "1회후미활동",
                SUM(CASE WHEN IS_ASSOCIATE=0 AND total_cnt>=2 AND recent_act=0 THEN 1 ELSE 0 END) AS "2회이상후미활동",
                SUM(CASE WHEN IS_ASSOCIATE=1 AND total_cnt>=1 AND recent_act=0 THEN 1 ELSE 0 END) AS "준회원미활동"
            FROM cs GROUP BY 1 ORDER BY 2 DESC
        """).to_pandas()
        df.columns = ["G속성","미체결","1회후미활동","2회이상후미활동","준회원미활동"]
        return df

    ina_sum = get_inactive_summary(ina_base_str, ina_ref_60, ina_mgr_cond)
    ina_cat_labels = [
        ("미체결 딜러",        "cat1", "정회원, 가입 60일↑, 체결 0건"),
        ("1회 체결 후 미활동", "cat2", "정회원, 총 1건, 직전 60일 없음"),
        ("2회↑ 체결 후 미활동","cat3", "정회원, 총 ≥2건, 직전 60일 없음"),
        ("준회원 미활동",       "cat4", "준회원, 체결 ≥1건, 직전 60일 없음"),
    ]

    ic1, ic2, ic3, ic4 = st.columns(4)
    for col, (lbl, key, desc) in zip([ic1,ic2,ic3,ic4], ina_cat_labels):
        cnt = ina_sum[key.upper()] or 0
        with col:
            st.markdown(kpi_card(lbl, f"{cnt:,}명", desc, "neutral"), unsafe_allow_html=True)

    st.markdown('<div class="section-title">G속성별 비활동 딜러 분포</div>', unsafe_allow_html=True)

    df_ig = get_inactive_g_dist(ina_base_str, ina_ref_60, ina_mgr_cond)
    if not df_ig.empty:
        df_melt = df_ig.melt("G속성", var_name="유형", value_name="딜러수")
        st.altair_chart(apply_theme(
            alt.Chart(df_melt).mark_bar().encode(
                x=alt.X("G속성:N", title="G속성"),
                y=alt.Y("딜러수:Q", title="딜러수"),
                color=alt.Color("유형:N", legend=alt.Legend(title="비활동 유형")),
                tooltip=[alt.Tooltip("G속성:N"), alt.Tooltip("유형:N"),
                         alt.Tooltip("딜러수:Q", format=",")]
            ).properties(height=300, background=CHART_BG)
        ), use_container_width=True)
        st.dataframe(df_ig, use_container_width=True, hide_index=True)
    else:
        st.info("데이터 없음")

    st.markdown('<div class="section-title">유형별 상세 딜러 목록</div>', unsafe_allow_html=True)
    for cat_num, (lbl, key, desc) in enumerate(ina_cat_labels, 1):
        cnt = ina_sum[key.upper()] or 0
        with st.expander(f"▶ 유형{cat_num}: {lbl} ({cnt:,}명)"):
            df_iraw = get_inactive_raw(cat_num, ina_base_str, ina_ref_60, ina_mgr_cond)
            if df_iraw.empty:
                st.info("해당 딜러 없음")
            else:
                st.dataframe(df_iraw, use_container_width=True, hide_index=True)
                st.download_button(
                    "⬇ CSV 다운로드",
                    df_iraw.to_csv(index=False, encoding="utf-8-sig"),
                    f"inactive_cat{cat_num}_{ina_base_month}.csv",
                    "text/csv", key=f"ina_dl_{cat_num}"
                )


# ═══════════════════════════════════════════════════════════════
# TAB 5 — 비견건수
# ═══════════════════════════════════════════════════════════════
with tab5:

    st.markdown("""
    <div class="criteria-box">
    📌 <b>비견건수 집계 기준</b><br>
    • <b>비견 견적</b>: COMPARISON_ESTIMATE 테이블 (counsel_vehicle.ID = comparison_estimate.COUNSEL_VEHICLE_ID)<br>
    • <b>비견 완료</b>: COUNSEL_STATUS = 'COMPARISON_COMPLETED'<br>
    • <b>비견→가입 전환</b>: COMPARISON_COMPLETED 후 JOIN_COMPLETED 전환 건<br>
    • 테스트 매니저 제외 / 삭제건 제외<br>
    • ERD 연결: counsel_application → counsel_vehicle → comparison_estimate → comparison_request_vehicle
    </div>
    """, unsafe_allow_html=True)

    cmp1, cmp2, cmp3 = st.columns(3)
    with cmp1: cmp_from = st.date_input("시작일", value=date(today.year, 1, 1), key="cmp_from")
    with cmp2: cmp_to   = st.date_input("종료일", value=today, key="cmp_to")
    with cmp3: cmp_mgr  = st.selectbox("담당매니저", ["전체"] + MANAGER_LIST, key="cmp_mgr")

    cmp_mgr_f = "" if cmp_mgr == "전체" else f"AND m.NAME = '{cmp_mgr}'"

    @st.cache_data(ttl=300)
    def get_cmp_kpi(d_from, d_to, mgr_f):
        # ERD 조인 체인:
        # counsel_application → counsel_vehicle
        #   → comparison_request_vehicle (counsel_vehicle_id)
        #   → comparison_request (request_id)
        #   → comparison_estimate (request_vehicle_id)
        r = session.sql(f"""
            SELECT
                COUNT(DISTINCT ca.COUNSEL_ID)                                            AS "전체상담건수",
                COUNT(DISTINCT cr.REQUEST_ID)                                            AS "비견요청건수",
                COUNT(DISTINCT ce.ESTIMATE_ID)                                           AS "비견견적건수",
                COUNT(DISTINCT CASE WHEN ca.COUNSEL_STATUS = 'COMPARISON_COMPLETED'
                                    THEN ca.COUNSEL_ID END)                              AS "비견완료건수",
                COUNT(DISTINCT CASE WHEN ca.COUNSEL_STATUS = 'JOIN_COMPLETED'
                                    THEN ca.COUNSEL_ID END)                              AS "가입완료건수"
            FROM AJDCAR_PROD.PUBLIC.COUNSEL_APPLICATION ca
            LEFT JOIN AJDCAR_PROD.PUBLIC.COUNSEL_VEHICLE cv
                ON ca.COUNSEL_ID = cv.COUNSEL_ID
                AND (cv.IS_DELETED = FALSE OR cv.IS_DELETED IS NULL)
            LEFT JOIN AJDCAR_PROD.PUBLIC.COMPARISON_REQUEST_VEHICLE crv
                ON cv.COUNSEL_VEHICLE_ID = crv.COUNSEL_VEHICLE_ID
            LEFT JOIN AJDCAR_PROD.PUBLIC.COMPARISON_REQUEST cr
                ON crv.REQUEST_ID = cr.REQUEST_ID
            LEFT JOIN AJDCAR_PROD.PUBLIC.COMPARISON_ESTIMATE ce
                ON crv.REQUEST_VEHICLE_ID = ce.REQUEST_VEHICLE_ID
            LEFT JOIN AJDCAR_PROD.PUBLIC.MANAGER m ON ca.COUNSEL_MANAGER_ID = m.ID
            WHERE ca.CREATED_AT::DATE BETWEEN '{d_from}' AND '{d_to}'
              AND (ca.IS_DELETED = FALSE OR ca.IS_DELETED IS NULL)
              AND (m.NAME IS NULL OR m.NAME NOT LIKE '%테스트%')
              {mgr_f}
        """).collect()
        return r[0]

    ck2 = get_cmp_kpi(cmp_from, cmp_to, cmp_mgr_f)
    total_ca   = ck2["전체상담건수"] or 0
    req_cnt    = ck2["비견요청건수"] or 0
    est_cnt    = ck2["비견견적건수"] or 0
    cmp_done   = ck2["비견완료건수"] or 0
    join_done  = ck2["가입완료건수"] or 0
    cmp_rate   = (cmp_done / total_ca * 100) if total_ca else 0
    join_rate  = (join_done / cmp_done * 100) if cmp_done else 0

    kc1, kc2, kc3, kc4, kc5 = st.columns(5)
    with kc1: st.markdown(kpi_card("전체 상담건수",   f"{total_ca:,}건"), unsafe_allow_html=True)
    with kc2: st.markdown(kpi_card("비견 요청건수",   f"{req_cnt:,}건"), unsafe_allow_html=True)
    with kc3: st.markdown(kpi_card("비견 견적건수",   f"{est_cnt:,}건"), unsafe_allow_html=True)
    with kc4: st.markdown(kpi_card("비견완료건수",    f"{cmp_done:,}건",
                                    f"상담 대비 {cmp_rate:.1f}%"), unsafe_allow_html=True)
    with kc5: st.markdown(kpi_card("비견→가입 전환율", f"{join_rate:.1f}%",
                                    f"비견완료 {cmp_done:,}건 중"), unsafe_allow_html=True)

    st.markdown('<div class="section-title">월별 비견건수 추이</div>', unsafe_allow_html=True)

    @st.cache_data(ttl=300)
    def get_cmp_monthly(d_from, d_to, mgr_f):
        df = session.sql(f"""
            SELECT
                TO_CHAR(ca.CREATED_AT, 'YYYY-MM')       AS "월",
                COUNT(DISTINCT ca.COUNSEL_ID)             AS "전체상담",
                COUNT(DISTINCT cr.REQUEST_ID)             AS "비견요청",
                COUNT(DISTINCT ce.ESTIMATE_ID)            AS "비견견적",
                COUNT(DISTINCT CASE WHEN ca.COUNSEL_STATUS = 'COMPARISON_COMPLETED'
                                    THEN ca.COUNSEL_ID END) AS "비견완료",
                COUNT(DISTINCT CASE WHEN ca.COUNSEL_STATUS = 'JOIN_COMPLETED'
                                    THEN ca.COUNSEL_ID END) AS "가입완료"
            FROM AJDCAR_PROD.PUBLIC.COUNSEL_APPLICATION ca
            LEFT JOIN AJDCAR_PROD.PUBLIC.COUNSEL_VEHICLE cv
                ON ca.COUNSEL_ID = cv.COUNSEL_ID
                AND (cv.IS_DELETED = FALSE OR cv.IS_DELETED IS NULL)
            LEFT JOIN AJDCAR_PROD.PUBLIC.COMPARISON_REQUEST_VEHICLE crv
                ON cv.COUNSEL_VEHICLE_ID = crv.COUNSEL_VEHICLE_ID
            LEFT JOIN AJDCAR_PROD.PUBLIC.COMPARISON_REQUEST cr
                ON crv.REQUEST_ID = cr.REQUEST_ID
            LEFT JOIN AJDCAR_PROD.PUBLIC.COMPARISON_ESTIMATE ce
                ON crv.REQUEST_VEHICLE_ID = ce.REQUEST_VEHICLE_ID
            LEFT JOIN AJDCAR_PROD.PUBLIC.MANAGER m ON ca.COUNSEL_MANAGER_ID = m.ID
            WHERE ca.CREATED_AT::DATE BETWEEN '{d_from}' AND '{d_to}'
              AND (ca.IS_DELETED = FALSE OR ca.IS_DELETED IS NULL)
              AND (m.NAME IS NULL OR m.NAME NOT LIKE '%테스트%')
              {mgr_f}
            GROUP BY 1 ORDER BY 1 DESC
        """).to_pandas()
        df.columns = ["월", "전체상담", "비견요청", "비견견적", "비견완료", "가입완료"]
        return df

    df_cmp_m = get_cmp_monthly(cmp_from, cmp_to, cmp_mgr_f)
    if not df_cmp_m.empty:
        df_melt2 = df_cmp_m.melt("월", var_name="구분", value_name="건수")
        order_cmp = list(df_cmp_m["월"])
        st.altair_chart(apply_theme(
            alt.Chart(df_melt2).mark_line(point=True).encode(
                x=alt.X("월:N", sort=order_cmp, title="월", axis=alt.Axis(labelAngle=-45)),
                y=alt.Y("건수:Q", title="건수"),
                color=alt.Color("구분:N", legend=alt.Legend(title="구분")),
                tooltip=[alt.Tooltip("월:N"), alt.Tooltip("구분:N"),
                         alt.Tooltip("건수:Q", format=",")]
            ).properties(height=300, background=CHART_BG)
        ), use_container_width=True)
        st.dataframe(df_cmp_m, use_container_width=True, hide_index=True)
    else:
        st.info("데이터 없음")

    st.markdown('<div class="section-title">매니저별 비견 현황</div>', unsafe_allow_html=True)

    @st.cache_data(ttl=300)
    def get_cmp_by_mgr(d_from, d_to):
        df = session.sql(f"""
            SELECT
                COALESCE(m.NAME, '미배정') AS "담당매니저",
                COUNT(DISTINCT ca.COUNSEL_ID)             AS "전체상담",
                COUNT(DISTINCT cr.REQUEST_ID)             AS "비견요청",
                COUNT(DISTINCT ce.ESTIMATE_ID)            AS "비견견적",
                COUNT(DISTINCT CASE WHEN ca.COUNSEL_STATUS = 'COMPARISON_COMPLETED'
                                    THEN ca.COUNSEL_ID END) AS "비견완료",
                COUNT(DISTINCT CASE WHEN ca.COUNSEL_STATUS = 'JOIN_COMPLETED'
                                    THEN ca.COUNSEL_ID END) AS "가입완료",
                ROUND(
                    COUNT(DISTINCT CASE WHEN ca.COUNSEL_STATUS = 'COMPARISON_COMPLETED'
                                        THEN ca.COUNSEL_ID END)
                    / NULLIF(COUNT(DISTINCT ca.COUNSEL_ID), 0) * 100, 1
                ) AS "비견완료율(%)"
            FROM AJDCAR_PROD.PUBLIC.COUNSEL_APPLICATION ca
            LEFT JOIN AJDCAR_PROD.PUBLIC.COUNSEL_VEHICLE cv
                ON ca.COUNSEL_ID = cv.COUNSEL_ID
                AND (cv.IS_DELETED = FALSE OR cv.IS_DELETED IS NULL)
            LEFT JOIN AJDCAR_PROD.PUBLIC.COMPARISON_REQUEST_VEHICLE crv
                ON cv.COUNSEL_VEHICLE_ID = crv.COUNSEL_VEHICLE_ID
            LEFT JOIN AJDCAR_PROD.PUBLIC.COMPARISON_REQUEST cr
                ON crv.REQUEST_ID = cr.REQUEST_ID
            LEFT JOIN AJDCAR_PROD.PUBLIC.COMPARISON_ESTIMATE ce
                ON crv.REQUEST_VEHICLE_ID = ce.REQUEST_VEHICLE_ID
            LEFT JOIN AJDCAR_PROD.PUBLIC.MANAGER m ON ca.COUNSEL_MANAGER_ID = m.ID
            WHERE ca.CREATED_AT::DATE BETWEEN '{d_from}' AND '{d_to}'
              AND (ca.IS_DELETED = FALSE OR ca.IS_DELETED IS NULL)
              AND (m.NAME IS NULL OR m.NAME NOT LIKE '%테스트%')
            GROUP BY 1 ORDER BY 4 DESC
        """).to_pandas()
        df.columns = ["담당매니저","전체상담","비견요청","비견견적","비견완료","가입완료","비견완료율(%)"]
        return df

    df_cmp_mgr = get_cmp_by_mgr(cmp_from, cmp_to)
    if not df_cmp_mgr.empty:
        st.dataframe(df_cmp_mgr, use_container_width=True, hide_index=True)
    else:
        st.info("데이터 없음")

    st.markdown('<div class="section-title">비견 요청 차량 현황</div>', unsafe_allow_html=True)

    @st.cache_data(ttl=300)
    def get_cmp_vehicle(d_from, d_to, mgr_f):
        df = session.sql(f"""
            SELECT
                TO_CHAR(ca.CREATED_AT, 'YYYY-MM')      AS "월",
                COUNT(DISTINCT crv.COUNSEL_VEHICLE_ID)  AS "비견요청차량수",
                COUNT(DISTINCT ce.ESTIMATE_ID)          AS "비견견적수",
                COUNT(DISTINCT ca.COUNSEL_ID)           AS "상담건수"
            FROM AJDCAR_PROD.PUBLIC.COUNSEL_APPLICATION ca
            LEFT JOIN AJDCAR_PROD.PUBLIC.COUNSEL_VEHICLE cv
                ON ca.COUNSEL_ID = cv.COUNSEL_ID
                AND (cv.IS_DELETED = FALSE OR cv.IS_DELETED IS NULL)
            LEFT JOIN AJDCAR_PROD.PUBLIC.COMPARISON_REQUEST_VEHICLE crv
                ON cv.COUNSEL_VEHICLE_ID = crv.COUNSEL_VEHICLE_ID
            LEFT JOIN AJDCAR_PROD.PUBLIC.COMPARISON_REQUEST cr
                ON crv.REQUEST_ID = cr.REQUEST_ID
            LEFT JOIN AJDCAR_PROD.PUBLIC.COMPARISON_ESTIMATE ce
                ON crv.REQUEST_VEHICLE_ID = ce.REQUEST_VEHICLE_ID
            LEFT JOIN AJDCAR_PROD.PUBLIC.MANAGER m ON ca.COUNSEL_MANAGER_ID = m.ID
            WHERE ca.CREATED_AT::DATE BETWEEN '{d_from}' AND '{d_to}'
              AND (ca.IS_DELETED = FALSE OR ca.IS_DELETED IS NULL)
              AND (m.NAME IS NULL OR m.NAME NOT LIKE '%테스트%')
              {mgr_f}
            GROUP BY 1 ORDER BY 1 DESC
        """).to_pandas()
        df.columns = ["월","비견요청차량수","비견견적수","상담건수"]
        return df

    try:
        df_crv = get_cmp_vehicle(cmp_from, cmp_to, cmp_mgr_f)
        if not df_crv.empty:
            st.dataframe(df_crv, use_container_width=True, hide_index=True)
        else:
            st.info("데이터 없음")
    except Exception as e:
        st.warning(f"비견 요청 차량 조회 오류 (테이블 스키마 확인 필요): {e}")

    st.markdown('<div class="section-title">상태 이력 기반 비견 전환 분석 (counsel_status_log)</div>',
                unsafe_allow_html=True)

    STATUS_KO = {
        "ACCUMULATE_PENDING":       "누적 대기",
        "CALL_TRANSFER_ATTEMPTED":  "콜 전달 시도",
        "COMPARISON_COMPLETED":     "비견 완료",
        "COMPARISON_IN_PROGRESS":   "비견 진행중",
        "COUNSEL_CLOSED":           "상담 종료",
        "COUNSEL_REQUEST":          "상담 요청",
        "CUSTOMER_EXCLUDED":        "고객 제외",
        "JOIN_CANCELLED":           "가입 취소",
        "JOIN_COMPLETED":           "가입 완료",
        "PROSPECT_COUNSEL":         "잠재 상담",
    }

    @st.cache_data(ttl=300)
    def get_status_log(d_from, d_to):
        df = session.sql(f"""
            SELECT
                csl.NEW_COUNSEL_STATUS AS "상태",
                TO_CHAR(csl.CREATED_AT, 'YYYY-MM') AS "월",
                COUNT(*) AS "건수"
            FROM AJDCAR_PROD.PUBLIC.COUNSEL_STATUS_LOG csl
            WHERE csl.CREATED_AT::DATE BETWEEN '{d_from}' AND '{d_to}'
            GROUP BY 1, 2 ORDER BY 2 DESC, 3 DESC
        """).to_pandas()
        df.columns = ["상태", "월", "건수"]
        df["상태"] = df["상태"].map(lambda x: STATUS_KO.get(x, x))
        return df

    try:
        df_sl = get_status_log(cmp_from, cmp_to)
        if not df_sl.empty:
            pv_sl = df_sl.pivot_table(
                index="상태", columns="월", values="건수", aggfunc="sum", fill_value=0
            ).reset_index()
            m_sl = sorted([c for c in pv_sl.columns if c != "상태"], reverse=True)
            pv_sl = pv_sl[["상태"] + m_sl]
            st.dataframe(pv_sl, use_container_width=True, hide_index=True)
        else:
            st.info("데이터 없음")
    except Exception as e:
        st.warning(f"상태 이력 조회 오류 (테이블 스키마 확인 필요): {e}")
