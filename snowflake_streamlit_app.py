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

/* 탭바 높이만큼 콘텐츠 밀어내기 */
div[data-testid="stTabs"] > div:nth-child(2) {
    margin-top: 56px !important;
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
# ── 탭바 고정 JS 주입 ─────────────────────────────────────────────
st.markdown("""
<div id="tab-sticky-anchor"></div>
<script>
(function() {
    function applySticky() {
        var tl = document.querySelector('div[data-testid="stTabs"] div[role="tablist"]');
        if (!tl) return false;
        tl.style.setProperty('position','fixed','important');
        tl.style.setProperty('top','0','important');
        tl.style.setProperty('left','0','important');
        tl.style.setProperty('right','0','important');
        tl.style.setProperty('z-index','9999','important');
        tl.style.setProperty('background-color','#ffffff','important');
        tl.style.setProperty('padding','6px 2rem 4px','important');
        tl.style.setProperty('border-bottom','2px solid #e0e0e0','important');
        tl.style.setProperty('box-shadow','0 2px 6px rgba(0,0,0,0.10)','important');
        tl.style.setProperty('display','flex','important');
        tl.style.setProperty('flex-direction','row','important');
        tl.style.setProperty('align-items','center','important');
        tl.style.setProperty('min-height','44px','important');
        Array.from(tl.querySelectorAll('button, [role="tab"], p, span')).forEach(function(el){
            el.style.setProperty('color','#333333','important');
            el.style.setProperty('visibility','visible','important');
            el.style.setProperty('opacity','1','important');
        });
        return true;
    }
    var tries = 0;
    var iv = setInterval(function(){
        if (applySticky() || ++tries > 30) clearInterval(iv);
    }, 300);
})();
</script>
""", unsafe_allow_html=True)

# 탭 구성
# ════════════════════════════════════
tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs([
    "📊 영업현황",
    "🏢 보험사별 현황",
    "❌ 취소건 현황",
    "💤 비활동 딜러 현황",
    "🔍 비견건수",
    "📈 주요지표분석",
    "👤 매니저별 실적",
    "🤝 상조회(B2B)",
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

    # ── 탈퇴회원 추이 ────────────────────────────
    st.markdown('<div class="section-title">탈퇴회원 추이</div>', unsafe_allow_html=True)

    @st.cache_data(ttl=300)
    def get_withdrawal_data():
        # 날짜 컬럼 없이 IS_DELETED=TRUE로 집계; 가입월(CREATED_AT) 기준으로 추이 표시
        r = session.sql("""
            SELECT COUNT(*) AS total_del
            FROM AJDCAR_PROD.PUBLIC.USERS
            WHERE IS_DELETED = TRUE
              AND USER_NAME NOT LIKE '%테스트%'
        """).collect()
        df = session.sql("""
            SELECT
                TO_CHAR(CREATED_AT, 'YYYY-MM') AS "가입월",
                COUNT(*) AS "탈퇴수"
            FROM AJDCAR_PROD.PUBLIC.USERS
            WHERE IS_DELETED = TRUE
              AND USER_NAME NOT LIKE '%테스트%'
              AND CREATED_AT IS NOT NULL
            GROUP BY 1
            ORDER BY 1 DESC
            LIMIT 24
        """).to_pandas()
        df.columns = ["가입월", "탈퇴수"]
        return r[0], df

    wd_kpi, df_wd = get_withdrawal_data()
    total_del = wd_kpi["TOTAL_DEL"] or 0
    total_inc_del = (kpi_usr["TOTAL"] or 0) + total_del
    churn_rate = (total_del / total_inc_del * 100) if total_inc_del else 0

    wd1, wd2 = st.columns(2)
    with wd1:
        st.markdown(kpi_card("누적 탈퇴회원", f"{total_del:,}명"), unsafe_allow_html=True)
    with wd2:
        st.markdown(kpi_card("탈퇴율 (누적)", f"{churn_rate:.1f}%",
                             f"전체 가입(탈퇴 포함) {total_inc_del:,}명 기준"), unsafe_allow_html=True)

    if not df_wd.empty:
        st.caption("가입월 기준 탈퇴회원 분포 (탈퇴일자 컬럼 없음 — 가입 코호트별 탈퇴수)")
        wd_order = list(df_wd["가입월"])
        wd_bar = alt.Chart(df_wd).mark_bar(color="#e03131").encode(
            x=alt.X("가입월:N", sort=wd_order, title=None, axis=alt.Axis(labelAngle=-45)),
            y=alt.Y("탈퇴수:Q", title="탈퇴수"),
            tooltip=[alt.Tooltip("가입월:N"), alt.Tooltip("탈퇴수:Q", format=",")]
        )
        wd_lbl = alt.Chart(df_wd).mark_text(dy=-6, fontSize=10, color="#333333").encode(
            x=alt.X("가입월:N", sort=wd_order),
            y=alt.Y("탈퇴수:Q"),
            text=alt.Text("탈퇴수:Q", format=",")
        )
        st.altair_chart(apply_theme(
            (wd_bar + wd_lbl).properties(height=220, background=CHART_BG)
        ), use_container_width=True)
    else:
        st.info("데이터 없음")

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

    # ── 앱 가입월별 체결 전환 분석 (코호트) ─────────
    st.markdown('<div class="section-title">앱 가입월별 체결 전환 분석</div>', unsafe_allow_html=True)
    st.markdown("""
    <div class="criteria-box">
    📌 <b>분석 기준</b><br>
    • 선택한 월에 앱 가입한 딜러(USERS.CREATED_AT 기준)를 코호트로 설정<br>
    • 해당 딜러들의 상담건 중 COUNSEL_STATUS = 'JOIN_COMPLETED' 전환 현황 집계<br>
    • 전환율 = 체결 발생 딜러수 / 해당월 가입 딜러수
    </div>
    """, unsafe_allow_html=True)

    coh1, coh2, coh3 = st.columns(3)
    with coh1:
        cohort_months = []
        _cd = today.replace(day=1)
        for _ in range(24):
            cohort_months.append(_cd.strftime("%Y-%m"))
            _cd = (_cd - timedelta(days=1)).replace(day=1)
        sel_cohort = st.selectbox("앱 가입월 선택", cohort_months, key="sel_cohort")
    with coh2:
        coh_mgr = st.selectbox("담당매니저", ["전체"] + MANAGER_LIST, key="coh_mgr")
    with coh3:
        coh_g = st.selectbox("G속성", ["전체","G1(수입)","G2(국산)","G3(중고차)","G4(보험설계)","G5(에이전시)"], key="coh_g")

    coh_mgr_f = "" if coh_mgr == "전체" else f"AND m.NAME = '{coh_mgr}'"
    coh_g_f   = "" if coh_g  == "전체" else f"AND ({G_ATTR_EXPR}) = '{coh_g}'"

    @st.cache_data(ttl=300)
    def get_cohort_kpi(cohort_ym, mgr_f, g_f):
        r = session.sql(f"""
            WITH cohort AS (
                SELECT
                    u.ID,
                    u.USER_NAME,
                    u.CREATED_AT::DATE AS reg_date,
                    {G_ATTR_EXPR}      AS g_attr,
                    m.NAME             AS manager_name
                FROM AJDCAR_PROD.PUBLIC.USERS u
                LEFT JOIN AJDCAR_PROD.PUBLIC.MANAGER m ON u.MANAGER_ID = m.ID
                WHERE TO_CHAR(u.CREATED_AT, 'YYYY-MM') = '{cohort_ym}'
                  AND u.USER_NAME NOT LIKE '%테스트%'
                  AND (u.IS_DELETED = FALSE OR u.IS_DELETED IS NULL)
                  AND u.IS_ASSOCIATE = 0
                  {mgr_f} {g_f}
            ),
            joined AS (
                SELECT ca.USER_ID, COUNT(*) AS join_cnt
                FROM AJDCAR_PROD.PUBLIC.COUNSEL_APPLICATION ca
                WHERE ca.COUNSEL_STATUS = 'JOIN_COMPLETED'
                  AND (ca.IS_DELETED = FALSE OR ca.IS_DELETED IS NULL)
                  AND ca.USER_ID IN (SELECT ID FROM cohort)
                GROUP BY 1
            )
            SELECT
                COUNT(DISTINCT c.ID)                                     AS "코호트딜러수",
                COUNT(DISTINCT CASE WHEN j.join_cnt > 0 THEN c.ID END)  AS "체결전환딜러수",
                COALESCE(SUM(j.join_cnt), 0)                            AS "총체결건수",
                ROUND(COUNT(DISTINCT CASE WHEN j.join_cnt > 0 THEN c.ID END)
                      / NULLIF(COUNT(DISTINCT c.ID), 0) * 100, 1)       AS "전환율"
            FROM cohort c
            LEFT JOIN joined j ON c.ID = j.USER_ID
        """).collect()
        return r[0]

    @st.cache_data(ttl=300)
    def get_cohort_detail(cohort_ym, mgr_f, g_f):
        df = session.sql(f"""
            WITH cohort AS (
                SELECT
                    u.ID,
                    u.USER_ID          AS login_id,
                    u.USER_NAME,
                    u.CREATED_AT::DATE AS reg_date,
                    {G_ATTR_EXPR}      AS g_attr,
                    COALESCE(u.PRIMARY_AFFILIATION, '-') AS brand,
                    m.NAME             AS manager_name
                FROM AJDCAR_PROD.PUBLIC.USERS u
                LEFT JOIN AJDCAR_PROD.PUBLIC.MANAGER m ON u.MANAGER_ID = m.ID
                WHERE TO_CHAR(u.CREATED_AT, 'YYYY-MM') = '{cohort_ym}'
                  AND u.USER_NAME NOT LIKE '%테스트%'
                  AND (u.IS_DELETED = FALSE OR u.IS_DELETED IS NULL)
                  AND u.IS_ASSOCIATE = 0
                  {mgr_f} {g_f}
            ),
            joined AS (
                SELECT
                    ca.USER_ID,
                    COUNT(*)                        AS join_cnt,
                    MIN(ca.JOIN_COMPLETED_AT::DATE) AS first_join,
                    MAX(ca.JOIN_COMPLETED_AT::DATE) AS last_join,
                    SUM(cv.CONTRACT_AMOUNT)         AS total_premium
                FROM AJDCAR_PROD.PUBLIC.COUNSEL_APPLICATION ca
                LEFT JOIN AJDCAR_PROD.PUBLIC.COUNSEL_VEHICLE cv
                    ON ca.COUNSEL_ID = cv.COUNSEL_ID
                    AND (cv.IS_DELETED = FALSE OR cv.IS_DELETED IS NULL)
                WHERE ca.COUNSEL_STATUS = 'JOIN_COMPLETED'
                  AND (ca.IS_DELETED = FALSE OR ca.IS_DELETED IS NULL)
                  AND ca.USER_ID IN (SELECT ID FROM cohort)
                GROUP BY 1
            )
            SELECT
                c.login_id                               AS "회원ID",
                c.USER_NAME                              AS "딜러명",
                c.manager_name                           AS "담당매니저",
                c.g_attr                                 AS "G속성",
                c.brand                                  AS "브랜드",
                c.reg_date                               AS "앱가입일",
                COALESCE(j.join_cnt, 0)                 AS "체결건수",
                j.first_join                             AS "첫체결일",
                j.last_join                              AS "마지막체결일",
                COALESCE(j.total_premium, 0)            AS "누적원수보험료",
                CASE WHEN j.join_cnt > 0 THEN '전환'
                     ELSE '미전환' END                   AS "전환여부"
            FROM cohort c
            LEFT JOIN joined j ON c.ID = j.USER_ID
            ORDER BY j.join_cnt DESC NULLS LAST, c.reg_date
        """).to_pandas()
        df.columns = ["회원ID","딜러명","담당매니저","G속성","브랜드","앱가입일",
                      "체결건수","첫체결일","마지막체결일","누적원수보험료","전환여부"]
        return df

    @st.cache_data(ttl=300)
    def get_cohort_monthly_conv(cohort_ym, mgr_f, g_f):
        df = session.sql(f"""
            WITH cohort AS (
                SELECT u.ID
                FROM AJDCAR_PROD.PUBLIC.USERS u
                LEFT JOIN AJDCAR_PROD.PUBLIC.MANAGER m ON u.MANAGER_ID = m.ID
                WHERE TO_CHAR(u.CREATED_AT, 'YYYY-MM') = '{cohort_ym}'
                  AND u.USER_NAME NOT LIKE '%테스트%'
                  AND (u.IS_DELETED = FALSE OR u.IS_DELETED IS NULL)
                  AND u.IS_ASSOCIATE = 0
                  {mgr_f} {g_f}
            )
            SELECT
                TO_CHAR(ca.JOIN_COMPLETED_AT, 'YYYY-MM') AS "체결월",
                COUNT(DISTINCT ca.USER_ID)                AS "체결딜러수",
                COUNT(*)                                  AS "체결건수",
                SUM(cv.CONTRACT_AMOUNT)                   AS "원수보험료"
            FROM AJDCAR_PROD.PUBLIC.COUNSEL_APPLICATION ca
            LEFT JOIN AJDCAR_PROD.PUBLIC.COUNSEL_VEHICLE cv
                ON ca.COUNSEL_ID = cv.COUNSEL_ID
                AND (cv.IS_DELETED = FALSE OR cv.IS_DELETED IS NULL)
            WHERE ca.COUNSEL_STATUS = 'JOIN_COMPLETED'
              AND (ca.IS_DELETED = FALSE OR ca.IS_DELETED IS NULL)
              AND ca.USER_ID IN (SELECT ID FROM cohort)
              AND ca.JOIN_COMPLETED_AT IS NOT NULL
            GROUP BY 1 ORDER BY 1
        """).to_pandas()
        df.columns = ["체결월", "체결딜러수", "체결건수", "원수보험료"]
        return df

    try:
        coh_kpi = get_cohort_kpi(sel_cohort, coh_mgr_f, coh_g_f)

        ck1, ck2, ck3, ck4 = st.columns(4)
        with ck1:
            st.markdown(kpi_card("코호트 딜러수", f"{coh_kpi['코호트딜러수'] or 0:,}명",
                                 f"{sel_cohort} 앱 가입"), unsafe_allow_html=True)
        with ck2:
            st.markdown(kpi_card("체결 전환 딜러수", f"{coh_kpi['체결전환딜러수'] or 0:,}명"),
                        unsafe_allow_html=True)
        with ck3:
            st.markdown(kpi_card("전환율", f"{coh_kpi['전환율'] or 0:.1f}%",
                                 "체결 1건 이상 발생 기준"), unsafe_allow_html=True)
        with ck4:
            st.markdown(kpi_card("총 체결건수", f"{coh_kpi['총체결건수'] or 0:,}건"),
                        unsafe_allow_html=True)

        df_coh = get_cohort_detail(sel_cohort, coh_mgr_f, coh_g_f)

        if not df_coh.empty:
            # 체결건수 구간 분포
            BUCKET_MAP = lambda x: (
                "0건(미전환)" if x == 0 else
                "1건" if x == 1 else
                "2~5건" if x <= 5 else
                "6~10건" if x <= 10 else
                "11건 이상"
            )
            BUCKET_ORDER_C = ["0건(미전환)", "1건", "2~5건", "6~10건", "11건 이상"]
            df_coh["구간"] = df_coh["체결건수"].apply(BUCKET_MAP)
            df_bucket_c = df_coh.groupby("구간").size().reset_index(name="딜러수")

            cv1, cv2 = st.columns(2)
            with cv1:
                st.caption("체결건수 구간별 딜러수")
                st.altair_chart(apply_theme(
                    alt.Chart(df_bucket_c).mark_bar(color=BAR_MAIN).encode(
                        x=alt.X("구간:N", sort=BUCKET_ORDER_C, title=None),
                        y=alt.Y("딜러수:Q", title="딜러수"),
                        tooltip=[alt.Tooltip("구간:N"), alt.Tooltip("딜러수:Q", format=",")]
                    ).properties(height=220, background=CHART_BG)
                ), use_container_width=True)

            with cv2:
                st.caption("월별 체결 추이 (해당 코호트)")
                df_coh_m = get_cohort_monthly_conv(sel_cohort, coh_mgr_f, coh_g_f)
                if not df_coh_m.empty:
                    order_cm2 = list(df_coh_m["체결월"])
                    st.altair_chart(apply_theme(
                        alt.Chart(df_coh_m).mark_bar(color="#5ba85a").encode(
                            x=alt.X("체결월:N", sort=order_cm2, title=None,
                                    axis=alt.Axis(labelAngle=-45)),
                            y=alt.Y("체결건수:Q", title="체결건수"),
                            tooltip=[alt.Tooltip("체결월:N"),
                                     alt.Tooltip("체결딜러수:Q", format=",", title="체결딜러수"),
                                     alt.Tooltip("체결건수:Q", format=","),
                                     alt.Tooltip("원수보험료:Q", format=",")]
                        ).properties(height=220, background=CHART_BG)
                    ), use_container_width=True)

            # 상세 테이블
            st.caption(f"{sel_cohort} 가입 딜러 전체 목록 ({len(df_coh):,}명)")
            df_coh_disp = df_coh.drop(columns=["구간"]).copy()
            df_coh_disp["누적원수보험료"] = df_coh_disp["누적원수보험료"].apply(
                lambda x: f"{int(x):,}" if x else "-"
            )
            st.dataframe(df_coh_disp, use_container_width=True, hide_index=True, height=400)
            st.download_button(
                "⬇ CSV 다운로드",
                df_coh_disp.to_csv(index=False, encoding="utf-8-sig"),
                f"cohort_{sel_cohort}.csv", "text/csv", key="coh_dl"
            )

    except Exception as e:
        st.warning(f"코호트 분석 조회 오류: {e}")

    # ── 광고비 포인트 현황 ────────────────────────
    st.markdown('<div class="section-title">광고비 포인트 현황 (USERS.AD_POINT 기준)</div>',
                unsafe_allow_html=True)
    st.markdown("""
    <div class="criteria-box">
    📌 <b>집계 기준</b><br>
    • <code>USERS.AD_POINT</code>: 딜러별 현재 광고비 포인트 <b>잔액</b><br>
    • 거래 이력(적립/출금 추이)은 AD_POINT_TRANSACTIONS 테이블 적재 후 제공 예정<br>
    • 테스트 계정·탈퇴회원 제외
    </div>
    """, unsafe_allow_html=True)

    @st.cache_data(ttl=300)
    def get_adpoint_kpi():
        r = session.sql(f"""
            SELECT
                COUNT(*)                                        AS "전체딜러수",
                SUM(AD_POINT)                                   AS "포인트총합",
                COUNT(CASE WHEN AD_POINT > 0 THEN 1 END)       AS "포인트보유수",
                COUNT(CASE WHEN AD_POINT = 0 THEN 1 END)       AS "포인트없음",
                ROUND(AVG(CASE WHEN AD_POINT > 0 THEN AD_POINT END), 0) AS "보유자평균"
            FROM AJDCAR_PROD.PUBLIC.USERS
            WHERE {USER_FILTER}
        """).collect()
        return r[0]

    @st.cache_data(ttl=300)
    def get_adpoint_g():
        df = session.sql(f"""
            SELECT
                {G_ATTR_EXPR}                                   AS "G속성",
                COUNT(*)                                        AS "딜러수",
                SUM(u.AD_POINT)                                 AS "포인트합계",
                COUNT(CASE WHEN u.AD_POINT > 0 THEN 1 END)     AS "보유수",
                ROUND(AVG(CASE WHEN u.AD_POINT > 0
                               THEN u.AD_POINT END), 0)        AS "보유자평균"
            FROM AJDCAR_PROD.PUBLIC.USERS u
            WHERE {USER_FILTER}
            GROUP BY 1 ORDER BY 3 DESC
        """).to_pandas()
        df.columns = ["G속성", "딜러수", "포인트합계", "보유수", "보유자평균"]
        return df

    @st.cache_data(ttl=300)
    def get_adpoint_mgr():
        df = session.sql(f"""
            SELECT
                COALESCE(m.NAME, '미배정')                      AS "담당매니저",
                COUNT(*)                                        AS "딜러수",
                SUM(u.AD_POINT)                                 AS "포인트합계",
                COUNT(CASE WHEN u.AD_POINT > 0 THEN 1 END)     AS "보유수",
                ROUND(AVG(CASE WHEN u.AD_POINT > 0
                               THEN u.AD_POINT END), 0)        AS "보유자평균"
            FROM AJDCAR_PROD.PUBLIC.USERS u
            LEFT JOIN AJDCAR_PROD.PUBLIC.MANAGER m ON u.MANAGER_ID = m.ID
            WHERE {USER_FILTER}
            GROUP BY 1 ORDER BY 3 DESC
        """).to_pandas()
        df.columns = ["담당매니저", "딜러수", "포인트합계", "보유수", "보유자평균"]
        return df

    @st.cache_data(ttl=300)
    def get_adpoint_bucket():
        df = session.sql(f"""
            SELECT
                CASE
                    WHEN u.AD_POINT = 0                          THEN '0원'
                    WHEN u.AD_POINT < 100000                     THEN '1~10만원 미만'
                    WHEN u.AD_POINT < 500000                     THEN '10~50만원 미만'
                    WHEN u.AD_POINT < 1000000                    THEN '50~100만원 미만'
                    ELSE '100만원 이상'
                END                                             AS "구간",
                COUNT(*)                                        AS "딜러수",
                SUM(u.AD_POINT)                                 AS "포인트합계"
            FROM AJDCAR_PROD.PUBLIC.USERS u
            WHERE {USER_FILTER}
            GROUP BY 1
            ORDER BY MIN(u.AD_POINT)
        """).to_pandas()
        df.columns = ["구간", "딜러수", "포인트합계"]
        return df

    try:
        ap_kpi = get_adpoint_kpi()
        ap1, ap2, ap3, ap4, ap5 = st.columns(5)
        with ap1:
            st.markdown(kpi_card("총 포인트 잔액", fmt_won(ap_kpi["포인트총합"] or 0)), unsafe_allow_html=True)
        with ap2:
            st.markdown(kpi_card("포인트 보유 딜러", f"{ap_kpi['포인트보유수'] or 0:,}명"), unsafe_allow_html=True)
        with ap3:
            st.markdown(kpi_card("포인트 미보유 딜러", f"{ap_kpi['포인트없음'] or 0:,}명"), unsafe_allow_html=True)
        with ap4:
            total_d = ap_kpi["전체딜러수"] or 1
            보유율 = (ap_kpi["포인트보유수"] or 0) / total_d * 100
            st.markdown(kpi_card("포인트 보유율", f"{보유율:.1f}%"), unsafe_allow_html=True)
        with ap5:
            st.markdown(kpi_card("보유자 평균 잔액", fmt_won(ap_kpi["보유자평균"] or 0)), unsafe_allow_html=True)

        ap_c1, ap_c2 = st.columns(2)

        with ap_c1:
            st.caption("포인트 잔액 구간별 딜러수")
            df_bucket = get_adpoint_bucket()
            BUCKET_ORDER = ["0원", "1~10만원 미만", "10~50만원 미만", "50~100만원 미만", "100만원 이상"]
            if not df_bucket.empty:
                st.altair_chart(apply_theme(
                    alt.Chart(df_bucket).mark_bar(color=BAR_MAIN).encode(
                        x=alt.X("구간:N", sort=BUCKET_ORDER, title=None),
                        y=alt.Y("딜러수:Q", title="딜러수"),
                        tooltip=[alt.Tooltip("구간:N"),
                                 alt.Tooltip("딜러수:Q", format=","),
                                 alt.Tooltip("포인트합계:Q", format=",", title="합계(원)")]
                    ).properties(height=240, background=CHART_BG)
                ), use_container_width=True)

        with ap_c2:
            st.caption("G속성별 포인트 합계")
            df_apg = get_adpoint_g()
            G5 = ["G1(수입)", "G2(국산)", "G3(중고차)", "G4(보험설계)", "G5(에이전시)"]
            df_apg_f = df_apg[df_apg["G속성"].isin(G5)]
            if not df_apg_f.empty:
                st.altair_chart(apply_theme(
                    alt.Chart(df_apg_f).mark_bar(color="#f4a261").encode(
                        x=alt.X("G속성:N", sort=G5, title=None),
                        y=alt.Y("포인트합계:Q", title="포인트 합계(원)",
                                axis=alt.Axis(format=",.0f")),
                        tooltip=[alt.Tooltip("G속성:N"),
                                 alt.Tooltip("딜러수:Q", format=","),
                                 alt.Tooltip("포인트합계:Q", format=","),
                                 alt.Tooltip("보유수:Q", format=","),
                                 alt.Tooltip("보유자평균:Q", format=",")]
                    ).properties(height=240, background=CHART_BG)
                ), use_container_width=True)

        st.caption("매니저별 포인트 현황")
        df_apm = get_adpoint_mgr()
        if not df_apm.empty:
            df_apm_disp = df_apm.copy()
            df_apm_disp["포인트합계"] = df_apm_disp["포인트합계"].apply(lambda x: f"{int(x):,}")
            df_apm_disp["보유자평균"] = df_apm_disp["보유자평균"].apply(
                lambda x: f"{int(x):,}" if pd.notna(x) and x else "-"
            )
            st.dataframe(df_apm_disp, use_container_width=True, hide_index=True)

        st.caption("G속성별 포인트 현황 상세")
        df_apg_disp = get_adpoint_g().copy()
        df_apg_disp["포인트합계"] = df_apg_disp["포인트합계"].apply(lambda x: f"{int(x):,}")
        df_apg_disp["보유자평균"] = df_apg_disp["보유자평균"].apply(
            lambda x: f"{int(x):,}" if pd.notna(x) and x else "-"
        )
        st.dataframe(df_apg_disp, use_container_width=True, hide_index=True)

    except Exception as e:
        st.warning(f"광고비 포인트 조회 오류: {e}")


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

    bi1, bi2, bi3, bi4 = st.columns(4)
    with bi1: ins_from  = st.date_input("시작일", value=date(today.year, 1, 1), key="ins_from")
    with bi2: ins_to    = st.date_input("종료일", value=today, key="ins_to")
    with bi3: ins_mgr   = st.selectbox("담당매니저", ["전체"] + MANAGER_LIST, key="ins_mgr")
    with bi4: ins_sub   = st.selectbox("가입경로", ["전체", "CM", "TM", "오프라인"], key="ins_sub")

    ins_mgr_f = "" if ins_mgr == "전체" else f"AND m.NAME = '{ins_mgr}'"
    _sub_map  = {"CM": "CM", "TM": "TM", "오프라인": "OFFLINE"}
    ins_sub_f = "" if ins_sub == "전체" else f"AND ca.SUBSCRIPTION_TYPE = '{_sub_map[ins_sub]}'"

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
    def get_ins_trend(d_from, d_to, mgr_f, sub_f):
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
              {mgr_f} {sub_f}
            GROUP BY 1, 2 ORDER BY 1 DESC, 3 DESC NULLS LAST
        """).to_pandas()
        df.columns = ["월", "보험사", "원수보험료", "건수"]
        return df

    df_it = get_ins_trend(ins_from, ins_to, ins_mgr_f, ins_sub_f)
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
    def get_ins_pivot(sub_f):
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
              {sub_f}
            GROUP BY 1, 2, 3 ORDER BY 1 DESC, 2, 3
        """).to_pandas()
        df.columns = ["월", "보험사", "채널", "원수보험료", "건수"]
        return df

    df_ipv = get_ins_pivot(ins_sub_f)
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

    # ── 가입경로(CM/TM/오프라인)별 보험사 실적 ────
    st.markdown('<div class="section-title">가입경로(CM/TM/오프라인)별 보험사 실적</div>',
                unsafe_allow_html=True)

    SUB_LABEL = {"CM": "CM", "TM": "TM", "OFFLINE": "오프라인"}

    @st.cache_data(ttl=300)
    def get_sub_ins(d_from, d_to, mgr_f):
        df = session.sql(f"""
            SELECT
                CASE ca.SUBSCRIPTION_TYPE
                    WHEN 'CM'      THEN 'CM'
                    WHEN 'TM'      THEN 'TM'
                    WHEN 'OFFLINE' THEN '오프라인'
                    ELSE COALESCE(ca.SUBSCRIPTION_TYPE, '미분류')
                END                                        AS "가입경로",
                COALESCE(ca.JOIN_INSURER_CODE, '미분류')   AS "보험사",
                TO_CHAR(ca.JOIN_COMPLETED_AT, 'YYYY-MM')  AS "월",
                SUM(cv.CONTRACT_AMOUNT)                    AS "원수보험료",
                COUNT(*)                                   AS "건수"
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
            GROUP BY 1, 2, 3
            ORDER BY 1, 2, 3 DESC
        """).to_pandas()
        df.columns = ["가입경로", "보험사", "월", "원수보험료", "건수"]
        return df

    df_sub = get_sub_ins(ins_from, ins_to, ins_mgr_f)

    if not df_sub.empty:
        sub_metric = st.radio("지표", ["원수보험료", "건수"], horizontal=True, key="sub_metric")

        # ① 가입경로 × 보험사 합산 표
        st.caption("가입경로 × 보험사 합산")
        df_sub_agg = df_sub.groupby(["가입경로", "보험사"])[["원수보험료", "건수"]].sum().reset_index()
        pv_sub = df_sub_agg.pivot_table(
            index="보험사", columns="가입경로",
            values=sub_metric, aggfunc="sum", fill_value=0
        ).reset_index()
        sub_cols = [c for c in ["CM", "TM", "오프라인"] if c in pv_sub.columns]
        pv_sub["합계"] = pv_sub[sub_cols].sum(axis=1)
        pv_sub = pv_sub[["보험사"] + sub_cols + ["합계"]].sort_values("합계", ascending=False).reset_index(drop=True)
        fmt_sub = (lambda x: f"{int(x):,}") if sub_metric == "원수보험료" else (lambda x: f"{int(x):,}건")
        for c in sub_cols + ["합계"]:
            pv_sub[c] = pv_sub[c].apply(fmt_sub)
        st.dataframe(pv_sub, use_container_width=True, hide_index=True)

        # ② 차트: 가입경로별 보험사 누적 막대
        sc1, sc2 = st.columns(2)
        with sc1:
            st.caption(f"보험사별 가입경로 {sub_metric}")
            chart_sub = alt.Chart(df_sub_agg).mark_bar().encode(
                x=alt.X("보험사:N", sort="-y", title=None),
                y=alt.Y(f"{sub_metric}:Q", title=sub_metric,
                        axis=alt.Axis(format=",.0f" if sub_metric == "원수보험료" else ",")),
                color=alt.Color("가입경로:N",
                                scale=alt.Scale(domain=["CM","TM","오프라인"],
                                                range=["#4c78a8","#f4a261","#5ba85a"]),
                                legend=alt.Legend(title="가입경로")),
                tooltip=["보험사", "가입경로",
                         alt.Tooltip(f"{sub_metric}:Q", format=",")],
            ).properties(height=300, background=CHART_BG)
            st.altair_chart(apply_theme(chart_sub), use_container_width=True)

        with sc2:
            st.caption(f"월별 가입경로 {sub_metric} 추이")
            df_sub_m = df_sub.groupby(["월", "가입경로"])[sub_metric].sum().reset_index()
            order_sub_m = sorted(df_sub_m["월"].unique(), reverse=True)
            chart_sub_m = alt.Chart(df_sub_m).mark_line(point=True).encode(
                x=alt.X("월:N", sort=order_sub_m, title=None,
                        axis=alt.Axis(labelAngle=-45)),
                y=alt.Y(f"{sub_metric}:Q", title=sub_metric,
                        axis=alt.Axis(format=",.0f" if sub_metric == "원수보험료" else ",")),
                color=alt.Color("가입경로:N",
                                scale=alt.Scale(domain=["CM","TM","오프라인"],
                                                range=["#4c78a8","#f4a261","#5ba85a"]),
                                legend=alt.Legend(title="가입경로")),
                tooltip=["월", "가입경로",
                         alt.Tooltip(f"{sub_metric}:Q", format=",")],
            ).properties(height=300, background=CHART_BG)
            st.altair_chart(apply_theme(chart_sub_m), use_container_width=True)

        # ③ 월별 × 가입경로 × 보험사 상세 피벗
        st.caption("월별 × 가입경로 × 보험사 상세")
        pv_sub2 = df_sub.pivot_table(
            index=["월", "가입경로"], columns="보험사",
            values=sub_metric, aggfunc="sum", fill_value=0
        ).reset_index()
        ins_cols2 = [c for c in pv_sub2.columns if c not in ["월", "가입경로"]]
        pv_sub2["합계"] = pv_sub2[ins_cols2].sum(axis=1)
        pv_sub2 = pv_sub2.sort_values(["월", "가입경로"], ascending=[False, True]).reset_index(drop=True)
        for c in ins_cols2 + ["합계"]:
            pv_sub2[c] = pv_sub2[c].apply(fmt_sub)
        st.dataframe(pv_sub2, use_container_width=True, hide_index=True)
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


# ═══════════════════════════════════════════════════════════════
# TAB 6 — 주요지표분석
# ✅ Snowflake 연동: 매니저별 가입수, 월별 원수보험료, 가동딜러수, 딜러앱등록비중
# ❌ 정적 데이터 유지: 사전예약현황, 광고비, 오프팀·B2B, 브랜드별, 본인계약, 연령별
#    (해당 데이터는 Snowflake 스키마에 관련 테이블/컬럼 없음)
# ═══════════════════════════════════════════════════════════════
with tab6:

    # ── 1. 사전예약 딜러확보 현황 (정적 — 사전예약 테이블 없음) ─
    st.markdown('<div class="section-title">사전예약 딜러확보 현황</div>', unsafe_allow_html=True)
    st.caption("ℹ️ Snowflake에 사전예약 테이블 없음 — 스프레드시트 기준 정적 데이터")
    df_reserve = pd.DataFrame({
        "사전예약일자": ["2025-8월", "2025-7월", "2025-6월", "총계"],
        "G1(수입)": [5, 162, 183, 627],
        "G2(국산)": [15, 119, 8, 396],
        "G3(중고차)": [1, 13, None, 30],
        "G4(보험설계)": [8, 46, None, 191],
        "G5(에이전시)": [1, 5, 6, 75],
        "총계": [30, 345, 197, 1319],
    })
    st.dataframe(df_reserve, use_container_width=True, hide_index=True)
    col_r1, _ = st.columns(2)
    with col_r1:
        df_reserve_summary = pd.DataFrame({
            "구분": ["사전예약", "App가입"],
            "총원": [1319, 1643],
            "사전예약만": [235, None],
            "예약&App가입": [1084, 1084],
            "App가입만": [None, 559],
        })
        st.dataframe(df_reserve_summary, use_container_width=True, hide_index=True)

    # ── 2. 매니저별 App가입 회원수 ✅ Snowflake ────────────────
    st.markdown('<div class="section-title">매니저별 App가입 회원수</div>', unsafe_allow_html=True)

    @st.cache_data(ttl=300)
    def get_t6_mgr_users():
        df = session.sql(f"""
            SELECT COALESCE(m.NAME, '미배정') AS "담당매니저",
                   COUNT(*) AS "가입수"
            FROM AJDCAR_PROD.PUBLIC.USERS u
            LEFT JOIN AJDCAR_PROD.PUBLIC.MANAGER m ON u.MANAGER_ID = m.ID
            WHERE u.USER_NAME NOT LIKE '%테스트%'
              AND (u.IS_DELETED = FALSE OR u.IS_DELETED IS NULL)
              AND u.IS_ASSOCIATE = 0
            GROUP BY 1 ORDER BY 2 DESC
        """).to_pandas()
        df.columns = ["담당매니저", "가입수"]
        return df

    try:
        df_mgr_join = get_t6_mgr_users()
        mg1, mg2 = st.columns([1, 2])
        with mg1:
            st.dataframe(df_mgr_join, use_container_width=True, hide_index=True)
        with mg2:
            if not df_mgr_join.empty:
                st.altair_chart(apply_theme(
                    alt.Chart(df_mgr_join).mark_bar(color=BAR_MAIN).encode(
                        y=alt.Y("담당매니저:N", sort="-x", title=None),
                        x=alt.X("가입수:Q", title="가입수"),
                        tooltip=[alt.Tooltip("담당매니저:N"), alt.Tooltip("가입수:Q", format=",")]
                    ).properties(height=280, background=CHART_BG)
                ), use_container_width=True)
    except Exception as e:
        st.warning(f"매니저별 가입수 조회 오류: {e}")

    # ── 3. 광고비 출금액 (정적 — 광고비 테이블 없음) ───────────
    st.markdown('<div class="section-title">광고비 출금액 (월별)</div>', unsafe_allow_html=True)
    st.caption("ℹ️ Snowflake에 광고비 출금 테이블 없음 — 스프레드시트 기준 정적 데이터")
    df_adcost = pd.DataFrame({
        "월": ["2026-8월","2026-7월","2026-6월","2026-5월","2026-4월","2026-3월","2026-2월","2026-1월",
               "2025-12월","2025-11월","2025-10월","2025-9월","2025-8월","총계"],
        "출금요청액(원)": [3447070,54159510,46994870,42966100,46786770,43856860,31771990,39480770,
                         28650160,25356990,24131030,19551440,8230000,415383560],
        "비율": ["4.10%","5.64%","4.66%","5.27%","5.56%","5.07%","4.71%","6.50%","-","-","-","-","-","-"],
    })
    col_a1, col_a2 = st.columns([2, 3])
    with col_a1:
        st.dataframe(df_adcost, use_container_width=True, hide_index=True)
    with col_a2:
        chart_ad = df_adcost[df_adcost["월"] != "총계"].copy()
        bar_ad = alt.Chart(chart_ad).mark_bar(color=BAR_MAIN).encode(
            x=alt.X("월:N", sort=None, title="월", axis=alt.Axis(labelAngle=-45)),
            y=alt.Y("출금요청액(원):Q", title="출금액(원)", axis=alt.Axis(format=",.0f")),
            tooltip=["월", alt.Tooltip("출금요청액(원):Q", format=",.0f"), "비율"],
        ).properties(height=280, title="월별 광고비 출금액")
        st.altair_chart(apply_theme(bar_ad.properties(background=CHART_BG)), use_container_width=True)

    # ── 4. 월별 원수보험료 ✅ Snowflake ────────────────────────
    st.markdown('<div class="section-title">월별 원수보험료</div>', unsafe_allow_html=True)

    @st.cache_data(ttl=300)
    def get_t6_monthly_premium():
        df = session.sql("""
            SELECT
                TO_CHAR(ca.JOIN_COMPLETED_AT, 'YYYY-MM') AS "체결월",
                SUM(cv.CONTRACT_AMOUNT)                   AS "원수보험료(원)"
            FROM AJDCAR_PROD.PUBLIC.COUNSEL_APPLICATION ca
            LEFT JOIN AJDCAR_PROD.PUBLIC.COUNSEL_VEHICLE cv
                ON ca.COUNSEL_ID = cv.COUNSEL_ID
                AND (cv.IS_DELETED = FALSE OR cv.IS_DELETED IS NULL)
            WHERE ca.COUNSEL_STATUS = 'JOIN_COMPLETED'
              AND ca.JOIN_COMPLETED_AT IS NOT NULL
              AND (ca.IS_DELETED = FALSE OR ca.IS_DELETED IS NULL)
            GROUP BY 1 ORDER BY 1 DESC
            LIMIT 24
        """).to_pandas()
        df.columns = ["체결월", "원수보험료(원)"]
        return df

    try:
        df_premium = get_t6_monthly_premium()
        col_p1, col_p2 = st.columns([2, 3])
        with col_p1:
            st.dataframe(df_premium, use_container_width=True, hide_index=True)
        with col_p2:
            if not df_premium.empty:
                order_pr = list(df_premium["체결월"])
                bar_pr = alt.Chart(df_premium).mark_bar(color=BAR_MAIN).encode(
                    x=alt.X("체결월:N", sort=order_pr, title="체결월",
                            axis=alt.Axis(labelAngle=-45)),
                    y=alt.Y("원수보험료(원):Q", title="원수보험료(원)",
                            axis=alt.Axis(format=",.0f")),
                    tooltip=["체결월", alt.Tooltip("원수보험료(원):Q", format=",.0f")],
                ).properties(height=280, title="월별 원수보험료")
                st.altair_chart(apply_theme(bar_pr.properties(background=CHART_BG)),
                                use_container_width=True)
    except Exception as e:
        st.warning(f"월별 원수보험료 조회 오류: {e}")

    # ── 5. 오프팀·B2B 활동회원 비율 (정적 — 세부채널 컬럼 없음) ─
    st.markdown('<div class="section-title">오프팀·B2B 활동회원 비율</div>', unsafe_allow_html=True)
    st.caption("ℹ️ 오프팀/B2B 세부 채널 분류 컬럼이 Snowflake에 없음 — 스프레드시트 기준 정적 데이터")
    df_offb2b = pd.DataFrame({
        "인입채널": ["오프팀","오프팀(별도영업)","오프팀(상조-종료)","오프팀(상조)","오프팀(후속)",
                    "B2B(겟차)","B2B(예상훈)","B2B(차사)","B2B(RS컴퍼니)","P_맥모닝","총계"],
        "앱가입(명)": [187,17,33,78,62,32,1,9,10,20,1643],
        "활동(60일)": ["32","1","16","24","29","21","-","4","-","10","626"],
        "활동(90일)": ["41","1","17","26","34","25","-","5","1","13","749"],
        "체결수(90일)": ["134","10","69","118","96","98","-","50","1","39","2566"],
        "활동률": ["17%","6%","48%","31%","47%","66%","0%","44%","0%","50%","-"],
    })
    st.dataframe(df_offb2b, use_container_width=True, hide_index=True)

    # ── 6. 딜러 브랜드별 분포 ✅ Snowflake (PRIMARY_AFFILIATION 기준) ─
    st.markdown('<div class="section-title">딜러 브랜드별 앱가입·활동회원·계약건수 분포</div>',
                unsafe_allow_html=True)
    st.caption("USERS.PRIMARY_AFFILIATION(1차소속) 기준, 직전 90일 체결건수 포함")

    @st.cache_data(ttl=300)
    def get_t6_brand_dist():
        df = session.sql(f"""
            WITH deal90 AS (
                SELECT USER_ID, COUNT(*) AS cnt90
                FROM AJDCAR_PROD.PUBLIC.COUNSEL_APPLICATION
                WHERE COUNSEL_STATUS = 'JOIN_COMPLETED'
                  AND JOIN_COMPLETED_AT >= DATEADD('DAY', -90, CURRENT_DATE)
                  AND (IS_DELETED = FALSE OR IS_DELETED IS NULL)
                GROUP BY 1
            ),
            deal60 AS (
                SELECT USER_ID, COUNT(*) AS cnt60
                FROM AJDCAR_PROD.PUBLIC.COUNSEL_APPLICATION
                WHERE COUNSEL_STATUS = 'JOIN_COMPLETED'
                  AND JOIN_COMPLETED_AT >= DATEADD('DAY', -60, CURRENT_DATE)
                  AND (IS_DELETED = FALSE OR IS_DELETED IS NULL)
                GROUP BY 1
            )
            SELECT
                {G_ATTR_EXPR}                                      AS "G속성",
                COALESCE(u.PRIMARY_AFFILIATION, '미분류')          AS "브랜드(1차소속)",
                COUNT(DISTINCT u.ID)                               AS "앱가입(명)",
                COUNT(DISTINCT CASE WHEN d60.cnt60 > 0 THEN u.ID END) AS "활동(60일)",
                COUNT(DISTINCT CASE WHEN d90.cnt90 > 0 THEN u.ID END) AS "활동(90일)",
                COALESCE(SUM(d90.cnt90), 0)                        AS "체결수(90일)",
                ROUND(COALESCE(SUM(d90.cnt90), 0)
                      / NULLIF(COUNT(DISTINCT u.ID), 0), 2)        AS "건당평균"
            FROM AJDCAR_PROD.PUBLIC.USERS u
            LEFT JOIN deal60 d60 ON u.ID = d60.USER_ID
            LEFT JOIN deal90 d90 ON u.ID = d90.USER_ID
            WHERE {USER_FILTER}
            GROUP BY 1, 2
            ORDER BY 1, 3 DESC
        """).to_pandas()
        df.columns = ["G속성","브랜드(1차소속)","앱가입(명)","활동(60일)","활동(90일)","체결수(90일)","건당평균"]
        return df

    try:
        df_brand = get_t6_brand_dist()
        if not df_brand.empty:
            br1, br2 = st.columns([3, 2])
            with br1:
                st.dataframe(df_brand, use_container_width=True, hide_index=True)
            with br2:
                df_brand_top = df_brand[~df_brand["G속성"].str.contains("소계|합계|미분류", na=False)].copy()
                chart_br = alt.Chart(df_brand_top).mark_bar().encode(
                    x=alt.X("앱가입(명):Q", title="앱가입(명)"),
                    y=alt.Y("브랜드(1차소속):N", sort="-x", title=None),
                    color=alt.Color("G속성:N", legend=alt.Legend(title="G속성")),
                    tooltip=["G속성","브랜드(1차소속)",
                             alt.Tooltip("앱가입(명):Q", format=","),
                             alt.Tooltip("활동(90일):Q", format=","),
                             alt.Tooltip("체결수(90일):Q", format=","),
                             alt.Tooltip("건당평균:Q")],
                ).properties(height=400, title="브랜드별 앱가입 현황")
                st.altair_chart(apply_theme(chart_br.properties(background=CHART_BG)),
                                use_container_width=True)
        else:
            st.info("데이터 없음")
    except Exception as e:
        st.warning(f"브랜드별 분포 조회 오류: {e}")

    # ── 7. 가동 딜러수 (월별·G속성별) ✅ Snowflake ─────────────
    st.markdown('<div class="section-title">가동 딜러수 (월별·G속성별)</div>', unsafe_allow_html=True)

    @st.cache_data(ttl=300)
    def get_t6_active_dealer_g():
        df = session.sql(f"""
            SELECT
                TO_CHAR(ca.JOIN_COMPLETED_AT, 'YYYY-MM') AS "체결월",
                {G_ATTR_EXPR}                             AS "G속성",
                COUNT(DISTINCT ca.USER_ID)                AS "가동딜러수"
            FROM AJDCAR_PROD.PUBLIC.COUNSEL_APPLICATION ca
            LEFT JOIN AJDCAR_PROD.PUBLIC.USERS u ON ca.USER_ID = u.ID
            WHERE ca.COUNSEL_STATUS = 'JOIN_COMPLETED'
              AND ca.JOIN_COMPLETED_AT IS NOT NULL
              AND (ca.IS_DELETED = FALSE OR ca.IS_DELETED IS NULL)
              AND u.USER_NAME NOT LIKE '%테스트%'
            GROUP BY 1, 2
            ORDER BY 1 DESC
            LIMIT 300
        """).to_pandas()
        df.columns = ["체결월", "G속성", "가동딜러수"]
        return df

    try:
        df_adg = get_t6_active_dealer_g()
        if not df_adg.empty:
            G5_LIST = ["G1(수입)", "G2(국산)", "G3(중고차)", "G4(보험설계)", "G5(에이전시)"]
            df_adg_filt = df_adg[df_adg["G속성"].isin(G5_LIST)]
            pivot_adg = df_adg_filt.pivot_table(
                index="체결월", columns="G속성", values="가동딜러수",
                aggfunc="sum", fill_value=0
            ).reset_index()
            pivot_adg["총계"] = pivot_adg[[c for c in G5_LIST if c in pivot_adg.columns]].sum(axis=1)
            pivot_adg = pivot_adg.sort_values("체결월", ascending=False).reset_index(drop=True)
            col_d1, col_d2 = st.columns([2, 3])
            with col_d1:
                st.dataframe(pivot_adg, use_container_width=True, hide_index=True)
            with col_d2:
                df_melt_adg = df_adg_filt[df_adg_filt["G속성"].isin(G5_LIST)].copy()
                order_adg = sorted(df_melt_adg["체결월"].unique(), reverse=True)
                chart_dl = alt.Chart(df_melt_adg).mark_line(point=True).encode(
                    x=alt.X("체결월:N", sort=order_adg, title="체결월",
                            axis=alt.Axis(labelAngle=-45)),
                    y=alt.Y("가동딜러수:Q", title="가동딜러수"),
                    color=alt.Color("G속성:N", legend=alt.Legend(title="G속성")),
                    tooltip=["체결월", "G속성",
                             alt.Tooltip("가동딜러수:Q", format=",")],
                ).properties(height=280, title="월별 G속성별 가동딜러수")
                st.altair_chart(apply_theme(chart_dl.properties(background=CHART_BG)),
                                use_container_width=True)
        else:
            st.info("데이터 없음")
    except Exception as e:
        st.warning(f"가동딜러수 조회 오류: {e}")

    # ── 8. 딜러앱 등록 체결건 비중 ✅ Snowflake (CHANNEL_PATH 기준) ─
    st.markdown('<div class="section-title">계약체결건 중 딜러앱 등록 체결건 비중</div>',
                unsafe_allow_html=True)
    st.caption("ℹ️ COUNSEL_APPLICATION.CHANNEL_PATH = 'DEALER_APP' 기준으로 산출")

    @st.cache_data(ttl=300)
    def get_t6_app_ratio():
        df = session.sql("""
            SELECT
                TO_CHAR(ca.JOIN_COMPLETED_AT, 'YYYY-MM') AS "체결월",
                SUM(CASE WHEN ca.CHANNEL_PATH = 'DEALER_APP' THEN 1 ELSE 0 END)     AS "딜러앱등록",
                SUM(CASE WHEN COALESCE(ca.CHANNEL_PATH,'') != 'DEALER_APP' THEN 1 ELSE 0 END) AS "미등록",
                COUNT(*)                                                              AS "총체결건",
                ROUND(
                    SUM(CASE WHEN ca.CHANNEL_PATH = 'DEALER_APP' THEN 1 ELSE 0 END)
                    / NULLIF(COUNT(*), 0) * 100, 2
                ) AS "앱등록비중(%)"
            FROM AJDCAR_PROD.PUBLIC.COUNSEL_APPLICATION ca
            WHERE ca.COUNSEL_STATUS = 'JOIN_COMPLETED'
              AND ca.JOIN_COMPLETED_AT IS NOT NULL
              AND (ca.IS_DELETED = FALSE OR ca.IS_DELETED IS NULL)
            GROUP BY 1 ORDER BY 1 DESC
            LIMIT 24
        """).to_pandas()
        df.columns = ["체결월", "딜러앱등록", "미등록", "총체결건", "앱등록비중(%)"]
        return df

    try:
        df_app_r = get_t6_app_ratio()
        if not df_app_r.empty:
            ar1, ar2 = st.columns([2, 3])
            with ar1:
                st.dataframe(df_app_r, use_container_width=True, hide_index=True)
            with ar2:
                order_ar = list(df_app_r["체결월"])
                df_ar_melt = df_app_r[["체결월","딜러앱등록","미등록"]].melt(
                    "체결월", var_name="구분", value_name="건수"
                )
                chart_ar = alt.Chart(df_ar_melt).mark_bar().encode(
                    x=alt.X("체결월:N", sort=order_ar, title="체결월",
                            axis=alt.Axis(labelAngle=-45)),
                    y=alt.Y("건수:Q", title="체결건수"),
                    color=alt.Color("구분:N", legend=alt.Legend(title="구분")),
                    tooltip=["체결월", "구분", alt.Tooltip("건수:Q", format=",")]
                ).properties(height=280, title="딜러앱 등록 vs 미등록 체결건")
                st.altair_chart(apply_theme(chart_ar.properties(background=CHART_BG)),
                                use_container_width=True)
        else:
            st.info("데이터 없음")
    except Exception as e:
        st.warning(f"딜러앱 등록 비중 조회 오류: {e}")

    # ── 9. 본인계약 비중 (정적 — 본인혜택 컬럼 불명확) ─────────
    st.markdown('<div class="section-title">계약체결건 중 딜러 본인계약 비중</div>',
                unsafe_allow_html=True)
    st.caption("ℹ️ 본인혜택(본인계약) 여부 컬럼이 Snowflake 스키마에서 확인되지 않음 — 정적 데이터")
    df_self_ratio = pd.DataFrame({
        "체결월": ["26-08m","26-07m","26-06m","26-05m","26-04m","26-03m","26-02m","26-01m",
                  "25-12m","25-11m","25-10m","25-09m","25-08m","25-07m","25-06m","총계"],
        "총체결건": [65,811,931,767,820,856,671,632,686,557,426,486,374,254,55,8391],
        "본인혜택체결건": [5,45,60,52,61,59,38,35,37,43,49,33,36,5,0,558],
        "비본인체결건": [60,766,871,715,759,797,633,597,649,514,377,453,338,249,55,7833],
        "본인계약률": ["7.69%","5.55%","6.44%","6.78%","7.44%","6.89%","5.66%","-","-","-","-","-","-","-","-","-"],
    })
    st.dataframe(df_self_ratio, use_container_width=True, hide_index=True)

    # ── 10. 딜러그룹 및 연령별 분포·생산성 (정적 — 연령 컬럼 없음) ─
    st.markdown('<div class="section-title">딜러그룹 및 연령별 분포·생산성</div>',
                unsafe_allow_html=True)
    st.caption("ℹ️ USERS 테이블에 연령대 컬럼 없음 — 스프레드시트 기준 정적 데이터")
    df_age = pd.DataFrame({
        "G속성": ["G1(수입)","G1(수입)","G1(수입)","G1(수입)","G1(수입) 소계",
                  "G2(국산)","G2(국산)","G2(국산)","G2(국산)","G2(국산)","G2(국산) 소계",
                  "G3(중고차)","G3(중고차)","G3(중고차)","G3(중고차) 소계",
                  "G4(보험설계)","G4(보험설계)","G4(보험설계)","G4(보험설계)","G4(보험설계)","G4(보험설계) 소계",
                  "G5(에이전시)","G5(에이전시)","G5(에이전시)","G5(에이전시)","G5(에이전시)","G5(에이전시) 소계"],
        "연령대": ["20대","30대","40대","50대","합계",
                   "20대","30대","40대","50대","60대 이상","합계",
                   "20대","30대","40대","합계",
                   "20대","30대","40대","50대","60대 이상","합계",
                   "20대","30대","40대","50대","60대 이상","합계"],
        "딜러수": [21,117,83,16,237, 15,54,71,44,21,205, 1,3,3,7, 8,27,32,19,3,89, 3,14,15,4,1,37],
        "직전60일 생산성": [4.48,3.17,2.95,2.06,3.14, 2.27,3.63,2.65,2.80,1.90,2.83,
                           2.00,1.00,2.33,1.71, 1.88,2.07,2.28,2.11,1.67,2.12,
                           2.00,2.14,4.20,2.50,2.00,3.0],
    })
    col_age1, col_age2 = st.columns([2, 3])
    with col_age1:
        st.dataframe(df_age, use_container_width=True, hide_index=True)
    with col_age2:
        df_age_detail = df_age[~df_age["연령대"].str.contains("합계")].copy()
        chart_age = alt.Chart(df_age_detail).mark_bar().encode(
            x=alt.X("G속성:N", title="G속성"),
            y=alt.Y("딜러수:Q", title="딜러수"),
            color=alt.Color("연령대:N", legend=alt.Legend(title="연령대")),
            tooltip=["G속성","연령대",
                     alt.Tooltip("딜러수:Q", format=","),
                     alt.Tooltip("직전60일 생산성:Q")],
        ).properties(height=280, title="G속성·연령대별 딜러 분포")
        st.altair_chart(apply_theme(chart_age.properties(background=CHART_BG)),
                        use_container_width=True)

# ═══════════════════════════════════════════════════════════════
# TAB 7 — 매니저별 실적
# ═══════════════════════════════════════════════════════════════
with tab7:

    st.markdown("""
    <div class="criteria-box">
    📌 <b>집계 기준</b><br>
    • 영업채널: 갱신(RENEWAL), CS(INBOUND), 딜러앱(DEALER_APP), 기타<br>
    • 체결 기준: COUNSEL_STATUS = 'JOIN_COMPLETED'<br>
    • 테스트 매니저 제외 / 삭제건 제외
    </div>
    """, unsafe_allow_html=True)

    # ── 필터 ──────────────────────────────────────
    mf1, mf2, mf3, mf4 = st.columns(4)
    with mf1:
        mgr7_from = st.date_input("시작일", value=today.replace(day=1), key="mgr7_from")
    with mf2:
        mgr7_to = st.date_input("종료일", value=today, key="mgr7_to")
    with mf3:
        mgr7_metric = st.radio("지표", ["원수보험료", "체결건수"], horizontal=True, key="mgr7_metric")
    with mf4:
        mgr7_unit = st.radio("단위", ["월별", "일별"], horizontal=True, key="mgr7_unit")

    CH_LIST = ["갱신", "딜러앱", "CS", "기타"]

    # ── 데이터 로드 ───────────────────────────────
    @st.cache_data(ttl=300)
    def get_mgr_perf(d_from, d_to, unit):
        grp = (
            "TO_CHAR(ca.JOIN_COMPLETED_AT, 'YYYY-MM')"
            if unit == "월별"
            else "TO_CHAR(ca.JOIN_COMPLETED_AT, 'YYYY-MM-DD')"
        )
        df = session.sql(f"""
            SELECT
                {grp}                          AS "기간",
                COALESCE(m.NAME, '미배정')      AS "매니저",
                {CH_EXPR}                       AS "채널",
                SUM(cv.CONTRACT_AMOUNT)         AS "원수보험료",
                COUNT(*)                        AS "체결건수"
            FROM AJDCAR_PROD.PUBLIC.COUNSEL_APPLICATION ca
            LEFT JOIN AJDCAR_PROD.PUBLIC.COUNSEL_VEHICLE cv
                ON ca.COUNSEL_ID = cv.COUNSEL_ID
                AND (cv.IS_DELETED = FALSE OR cv.IS_DELETED IS NULL)
            LEFT JOIN AJDCAR_PROD.PUBLIC.MANAGER m ON ca.COUNSEL_MANAGER_ID = m.ID
            WHERE ca.COUNSEL_STATUS = 'JOIN_COMPLETED'
              AND ca.JOIN_COMPLETED_AT IS NOT NULL
              AND (ca.IS_DELETED = FALSE OR ca.IS_DELETED IS NULL)
              AND ca.JOIN_COMPLETED_AT::DATE BETWEEN '{d_from}' AND '{d_to}'
              AND (m.NAME IS NULL OR m.NAME NOT LIKE '%테스트%')
            GROUP BY 1, 2, 3
            ORDER BY 1 DESC, 2, 3
        """).to_pandas()
        df.columns = ["기간", "매니저", "채널", "원수보험료", "체결건수"]
        return df

    try:
        df_mgr = get_mgr_perf(mgr7_from, mgr7_to, mgr7_unit)
    except Exception as e:
        st.error(f"데이터 조회 오류: {e}")
        df_mgr = pd.DataFrame()

    if df_mgr.empty:
        st.info("데이터 없음")
    else:
        val_col = mgr7_metric  # "원수보험료" or "체결건수"

        # ── KPI 요약 (매니저별 합계) ──────────────
        st.markdown('<div class="section-title">매니저별 합계</div>', unsafe_allow_html=True)

        df_kpi = (
            df_mgr.groupby("매니저")[["원수보험료", "체결건수"]]
            .sum()
            .reset_index()
            .sort_values("원수보험료", ascending=False)
        )
        total_row = pd.DataFrame({
            "매니저": ["합계"],
            "원수보험료": [df_kpi["원수보험료"].sum()],
            "체결건수": [df_kpi["체결건수"].sum()],
        })
        df_kpi_disp = pd.concat([df_kpi, total_row], ignore_index=True)

        kpi_cols = st.columns(len(df_kpi))
        for col, (_, row) in zip(kpi_cols, df_kpi.iterrows()):
            with col:
                st.markdown(
                    kpi_card(
                        row["매니저"],
                        f"{int(row['체결건수']):,}건",
                        fmt_won(row["원수보험료"]),
                        "neutral",
                        small=True,
                    ),
                    unsafe_allow_html=True,
                )

        # ── 피벗 테이블: 기간 × 채널 (매니저별) ──
        st.markdown('<div class="section-title">기간 × 영업채널 피벗</div>', unsafe_allow_html=True)

        # 전체 합산 피벗 (매니저 통합)
        df_pv_all = df_mgr.groupby(["기간", "채널"])[val_col].sum().reset_index()
        pv_all = df_pv_all.pivot_table(
            index="기간", columns="채널", values=val_col, aggfunc="sum", fill_value=0
        ).reset_index()
        for ch in CH_LIST:
            if ch not in pv_all.columns:
                pv_all[ch] = 0
        pv_all["총계"] = pv_all[CH_LIST].sum(axis=1)
        pv_all = pv_all[["기간"] + CH_LIST + ["총계"]].sort_values("기간", ascending=False).reset_index(drop=True)

        if val_col == "원수보험료":
            fmt_fn = lambda x: f"{int(x):,}" if x else "-"
        else:
            fmt_fn = lambda x: f"{int(x):,}건" if x else "-"

        pv_disp = pv_all.copy()
        for c in CH_LIST + ["총계"]:
            pv_disp[c] = pv_disp[c].apply(fmt_fn)

        st.caption(f"전체 매니저 합산 — {val_col}")
        st.dataframe(pv_disp, use_container_width=True, hide_index=True)

        # ── 매니저별 피벗 (expander) ─────────────
        st.markdown('<div class="section-title">매니저별 상세 피벗</div>', unsafe_allow_html=True)
        mgr_list_7 = sorted(df_mgr["매니저"].unique())
        for mgr_name in mgr_list_7:
            df_m = df_mgr[df_mgr["매니저"] == mgr_name]
            df_pv_m = df_m.groupby(["기간", "채널"])[val_col].sum().reset_index()
            pv_m = df_pv_m.pivot_table(
                index="기간", columns="채널", values=val_col, aggfunc="sum", fill_value=0
            ).reset_index()
            for ch in CH_LIST:
                if ch not in pv_m.columns:
                    pv_m[ch] = 0
            pv_m["총계"] = pv_m[CH_LIST].sum(axis=1)
            pv_m = pv_m[["기간"] + CH_LIST + ["총계"]].sort_values("기간", ascending=False).reset_index(drop=True)

            total_sum = int(pv_m["총계"].sum())
            label_fmt = fmt_won(total_sum) if val_col == "원수보험료" else f"{total_sum:,}건"

            with st.expander(f"▶ {mgr_name}  ({label_fmt})"):
                pv_m_disp = pv_m.copy()
                for c in CH_LIST + ["총계"]:
                    pv_m_disp[c] = pv_m_disp[c].apply(fmt_fn)
                st.dataframe(pv_m_disp, use_container_width=True, hide_index=True)

        # ── 시각화 ───────────────────────────────
        st.markdown('<div class="section-title">시각화</div>', unsafe_allow_html=True)

        v1, v2 = st.columns(2)

        with v1:
            st.caption(f"매니저 × 영업채널별 {val_col} (전체 기간 합산)")
            df_vis1 = df_mgr.groupby(["매니저", "채널"])[val_col].sum().reset_index()
            mgr_order = (
                df_vis1.groupby("매니저")[val_col]
                .sum()
                .sort_values(ascending=False)
                .index.tolist()
            )
            ch_colors = {
                "갱신": "#4c78a8",
                "딜러앱": "#5ba85a",
                "CS": "#f4a261",
                "기타": "#aaaaaa",
            }
            chart_v1 = alt.Chart(df_vis1).mark_bar().encode(
                x=alt.X("매니저:N", sort=mgr_order, title=None),
                y=alt.Y(f"{val_col}:Q", title=val_col,
                        axis=alt.Axis(format=",.0f" if val_col == "원수보험료" else ",")),
                color=alt.Color("채널:N",
                                scale=alt.Scale(domain=CH_LIST,
                                                range=[ch_colors[c] for c in CH_LIST]),
                                legend=alt.Legend(title="채널")),
                tooltip=[
                    alt.Tooltip("매니저:N"),
                    alt.Tooltip("채널:N"),
                    alt.Tooltip(f"{val_col}:Q", format=","),
                ],
            ).properties(height=300, background=CHART_BG)
            st.altair_chart(apply_theme(chart_v1), use_container_width=True)

        with v2:
            st.caption(f"기간별 매니저 {val_col} 추이")
            df_vis2 = df_mgr.groupby(["기간", "매니저"])[val_col].sum().reset_index()
            period_order_7 = sorted(df_vis2["기간"].unique(), reverse=True)
            chart_v2 = alt.Chart(df_vis2).mark_line(point=True).encode(
                x=alt.X("기간:N", sort=period_order_7, title=None,
                        axis=alt.Axis(labelAngle=-45)),
                y=alt.Y(f"{val_col}:Q", title=val_col,
                        axis=alt.Axis(format=",.0f" if val_col == "원수보험료" else ",")),
                color=alt.Color("매니저:N", legend=alt.Legend(title="매니저")),
                tooltip=[
                    alt.Tooltip("기간:N"),
                    alt.Tooltip("매니저:N"),
                    alt.Tooltip(f"{val_col}:Q", format=","),
                ],
            ).properties(height=300, background=CHART_BG)
            st.altair_chart(apply_theme(chart_v2), use_container_width=True)

        # ── 원수보험료·건수 동시 표 (전체) ────────
        st.markdown('<div class="section-title">전체 상세 데이터 (원수보험료 + 체결건수)</div>',
                    unsafe_allow_html=True)

        df_both = df_mgr.groupby(["기간", "매니저", "채널"])[["원수보험료", "체결건수"]].sum().reset_index()
        df_both = df_both.sort_values(["기간", "매니저", "채널"], ascending=[False, True, True]).reset_index(drop=True)
        df_both["원수보험료"] = df_both["원수보험료"].apply(lambda x: f"{int(x):,}")
        df_both["체결건수"] = df_both["체결건수"].apply(lambda x: f"{int(x):,}건")
        st.dataframe(df_both, use_container_width=True, hide_index=True)

        st.download_button(
            "⬇ CSV 다운로드 (집계)",
            df_mgr.to_csv(index=False, encoding="utf-8-sig"),
            f"mgr_perf_{mgr7_from}_{mgr7_to}.csv",
            "text/csv",
            key="mgr7_dl",
        )

    # ── Raw 데이터 ─────────────────────────────────────────────
    st.markdown('<div class="section-title">가입완료 Raw 데이터</div>', unsafe_allow_html=True)
    st.markdown("""
    <div class="criteria-box">
    📌 <b>Raw 데이터 컬럼 안내</b><br>
    • <b>주유권</b>: Snowflake 미연동 — 추후 반영 예정<br>
    • <b>직전1년 본인혜택건수</b>: 추가 예정<br>
    • <b>갱신-직전60일 딜러계약건수</b>: 추가 예정<br>
    • <b>가입경로(CM/TM)</b>: CHANNEL_PATH 기준 (INBOUND→CS/TM, DEALER_APP→딜러앱)<br>
    • 차량번호·만기월·영업용여부는 COUNSEL_VEHICLE 테이블 기준
    </div>
    """, unsafe_allow_html=True)

    @st.cache_data(ttl=300)
    def get_raw_joined(d_from, d_to):
        df = session.sql(f"""
            SELECT
                /* 영업채널 */
                {CH_EXPR}                                                          AS "영업채널",

                /* 고객 정보 — CUSTOMER 테이블 JOIN */
                COALESCE(cust.CUSTOMER_NAME, '-')                                  AS "고객명",

                /* 차량번호 — counsel_vehicle.LICENSE_PLATE_NUMBER */
                COALESCE(cv.LICENSE_PLATE_NUMBER, '-')                             AS "차량번호",

                /* 보험료 */
                cv.CONTRACT_AMOUNT                                                 AS "보험료",

                /* 가입보험사 */
                COALESCE(ca.JOIN_INSURER_CODE, '-')                                AS "가입보험사",

                /* 가입경로: SUBSCRIPTION_TYPE → CM/TM/OFFLINE */
                CASE ca.SUBSCRIPTION_TYPE
                    WHEN 'CM'      THEN 'CM'
                    WHEN 'TM'      THEN 'TM'
                    WHEN 'OFFLINE' THEN '오프라인'
                    ELSE COALESCE(ca.SUBSCRIPTION_TYPE, '-')
                END                                                                AS "가입경로",

                /* 만기월 — counsel_application.INSURANCE_END_DT (새 보험 만기일) */
                COALESCE(TO_CHAR(ca.INSURANCE_END_DT, 'YYYY-MM'), '-')            AS "만기월",

                /* 영업용 여부 — counsel_application.VEHICLE_USAGE_CODE */
                CASE
                    WHEN ca.VEHICLE_USAGE_CODE IS NULL THEN '-'
                    WHEN ca.VEHICLE_USAGE_CODE IN ('COMMERCIAL','BUSINESS') THEN '영업용'
                    ELSE '비영업용'
                END                                                                AS "영업용여부",

                /* 체결 일자 / 월 */
                ca.JOIN_COMPLETED_AT::DATE                                         AS "체결일자",
                TO_CHAR(ca.JOIN_COMPLETED_AT, 'YYYY-MM')                          AS "체결월",

                /* 매니저 */
                COALESCE(m.NAME, '미배정')                                         AS "매니저",

                /* 주유권 — GIFT 테이블 JOIN (ca.GIFT_ID → gift.GIFT_NAME) */
                COALESCE(g.GIFT_NAME, '-')                                         AS "주유권",

                /* 회원 정보 */
                u.USER_NAME                                                        AS "회원명",
                u.USER_ID                                                          AS "회원ID",
                COALESCE(u.PRIMARY_AFFILIATION, '-')                              AS "브랜드",

                /* 추가 예정 */
                NULL                                                               AS "직전1년본인혜택건수",
                NULL                                                               AS "갱신_직전60일딜러계약건수"

            FROM AJDCAR_PROD.PUBLIC.COUNSEL_APPLICATION ca
            LEFT JOIN AJDCAR_PROD.PUBLIC.COUNSEL_VEHICLE cv
                ON ca.COUNSEL_ID = cv.COUNSEL_ID
                AND (cv.IS_DELETED = FALSE OR cv.IS_DELETED IS NULL)
            LEFT JOIN AJDCAR_PROD.PUBLIC.CUSTOMER cust
                ON ca.CUSTOMER_ID = cust.CUSTOMER_ID
                AND (cust.IS_DELETED = FALSE OR cust.IS_DELETED IS NULL)
            LEFT JOIN AJDCAR_PROD.PUBLIC.GIFT g
                ON ca.GIFT_ID = g.GIFT_ID
            LEFT JOIN AJDCAR_PROD.PUBLIC.USERS u
                ON ca.USER_ID = u.ID
            LEFT JOIN AJDCAR_PROD.PUBLIC.MANAGER m
                ON ca.COUNSEL_MANAGER_ID = m.ID
            WHERE ca.COUNSEL_STATUS = 'JOIN_COMPLETED'
              AND ca.JOIN_COMPLETED_AT IS NOT NULL
              AND (ca.IS_DELETED = FALSE OR ca.IS_DELETED IS NULL)
              AND ca.JOIN_COMPLETED_AT::DATE BETWEEN '{d_from}' AND '{d_to}'
              AND (m.NAME IS NULL OR m.NAME NOT LIKE '%테스트%')
            ORDER BY ca.JOIN_COMPLETED_AT DESC
        """).to_pandas()
        return df

    try:
        df_raw = get_raw_joined(mgr7_from, mgr7_to)

        # 컬럼 오류 발생 시 fallback: 존재하지 않는 컬럼은 '-' 로 채움
        col_order = [
            "영업채널","고객명","차량번호","보험료","가입보험사","가입경로",
            "만기월","영업용여부","체결일자","체결월","매니저",
            "주유권","회원명","회원ID","브랜드",
            "직전1년본인혜택건수","갱신_직전60일딜러계약건수",
        ]
        for c in col_order:
            if c not in df_raw.columns:
                df_raw[c] = "-"
        df_raw = df_raw[col_order]

        # 보험료 포맷
        df_raw_disp = df_raw.copy()
        df_raw_disp["보험료"] = df_raw_disp["보험료"].apply(
            lambda x: f"{int(x):,}" if pd.notna(x) and x else "-"
        )

        st.caption(f"총 {len(df_raw_disp):,}건 — {mgr7_from} ~ {mgr7_to}")
        st.dataframe(df_raw_disp, use_container_width=True, hide_index=True, height=500)

        st.download_button(
            "⬇ Raw 데이터 CSV 다운로드",
            df_raw.to_csv(index=False, encoding="utf-8-sig"),
            f"raw_joined_{mgr7_from}_{mgr7_to}.csv",
            "text/csv",
            key="mgr7_raw_dl",
        )
    except Exception as e:
        st.warning(f"Raw 데이터 조회 오류 (컬럼명 확인 필요): {e}")

# ═══════════════════════════════════════════════════════════════
# TAB 8 — 상조회(B2B) 실적
# ═══════════════════════════════════════════════════════════════
with tab8:
    st.subheader("🤝 상조회(B2B) 딜러 실적")

    st.markdown("""
    <div class="criteria-box">
    <b>대상 그룹</b><br>
    ① 현대 / 하계 &nbsp;&nbsp; ② 현대 / 우이 &nbsp;&nbsp; ③ BMW / 방배 &nbsp;&nbsp;
    ④ BMW / 자유로 &nbsp;&nbsp; ⑤ BMW / 남양주<br>
    <b>조건</b>: IS_ASSOCIATE=0, 테스트 계정 제외, 탈퇴회원 제외
    </div>
    """, unsafe_allow_html=True)

    # ── B2B 대상 필터 ──────────────────────────────────────────
    B2B_GROUPS = [
        ("현대", "하계"),
        ("현대", "우이"),
        ("BMW", "방배"),
        ("BMW", "자유로"),
        ("BMW", "남양주"),
    ]

    # BRAND_1(1차 소속) / BRANCH_NAME(2차 소속) 컬럼명은
    # 실제 Snowflake 스키마에 맞게 조정 필요
    # 현재 USERS 테이블 기준: BRAND (브랜드), BRANCH_NAME (지점명)
    b2b_where_parts = " OR ".join(
        f"(u.PRIMARY_AFFILIATION = '{b1}' AND u.SECONDARY_AFFILIATION = '{b2}')"
        for b1, b2 in B2B_GROUPS
    )
    B2B_WHERE = f"({b2b_where_parts})"

    @st.cache_data(ttl=300)
    def get_b2b_trend():
        """소속별 월별 체결건수 + 원수보험료 추이"""
        df = session.sql(f"""
            SELECT
                TO_CHAR(ca.JOIN_COMPLETED_AT, 'YYYY-MM')  AS YM,
                u.PRIMARY_AFFILIATION                      AS BRAND,
                u.SECONDARY_AFFILIATION                    AS BRANCH_NAME,
                COUNT(*)                                   AS CNT,
                SUM(cv.CONTRACT_AMOUNT)                    AS FEE
            FROM AJDCAR_PROD.PUBLIC.COUNSEL_APPLICATION ca
            LEFT JOIN AJDCAR_PROD.PUBLIC.COUNSEL_VEHICLE cv ON cv.COUNSEL_ID = ca.COUNSEL_ID
            LEFT JOIN AJDCAR_PROD.PUBLIC.USERS u ON u.ID = ca.USER_ID
            WHERE ca.COUNSEL_STATUS = 'JOIN_COMPLETED'
              AND ca.JOIN_COMPLETED_AT IS NOT NULL
              AND (ca.IS_DELETED = FALSE OR ca.IS_DELETED IS NULL)
              AND (cv.IS_DELETED = FALSE OR cv.IS_DELETED IS NULL)
              AND ({b2b_where_parts})
              AND u.IS_ASSOCIATE = 0
              AND u.USER_NAME NOT LIKE '%테스트%'
              AND (u.IS_DELETED = FALSE OR u.IS_DELETED IS NULL)
            GROUP BY 1, 2, 3
            ORDER BY 1, 2, 3
        """).to_pandas()
        df.rename(columns={
            "YM": "체결월", "BRAND": "브랜드", "BRANCH_NAME": "지점명",
            "CNT": "체결건수", "FEE": "원수보험료",
        }, inplace=True)
        df["소속"] = df["브랜드"] + " / " + df["지점명"]
        return df

    @st.cache_data(ttl=300)
    def get_b2b_list():
        df = session.sql(f"""
            WITH joined AS (
                SELECT
                    ca.USER_ID                                                         AS uid,
                    COUNT(*)                                                           AS cnt_total,
                    SUM(cv.CONTRACT_AMOUNT)                                            AS fee_total,
                    MIN(ca.JOIN_COMPLETED_AT::DATE)                                   AS dt_first,
                    MAX(ca.JOIN_COMPLETED_AT::DATE)                                   AS dt_last,
                    COUNT(CASE WHEN ca.JOIN_COMPLETED_AT::DATE
                               >= DATEADD('day', -60, CURRENT_DATE()) THEN 1 END)    AS cnt_60d
                FROM AJDCAR_PROD.PUBLIC.COUNSEL_APPLICATION ca
                LEFT JOIN AJDCAR_PROD.PUBLIC.COUNSEL_VEHICLE cv ON cv.COUNSEL_ID = ca.COUNSEL_ID
                WHERE ca.COUNSEL_STATUS = 'JOIN_COMPLETED'
                  AND ca.JOIN_COMPLETED_AT IS NOT NULL
                  AND (ca.IS_DELETED = FALSE OR ca.IS_DELETED IS NULL)
                GROUP BY ca.USER_ID
            )
            SELECT
                u.ID                           AS USER_PK,
                u.USER_ID                      AS LOGIN_ID,
                u.USER_NAME                    AS USER_NAME,
                u.PRIMARY_AFFILIATION          AS BRAND,
                u.SECONDARY_AFFILIATION        AS BRANCH_NAME,
                u.CREATED_AT::DATE             AS CREATED_DT,
                j.dt_first                     AS DT_FIRST,
                j.dt_last                      AS DT_LAST,
                COALESCE(j.cnt_total,  0)      AS CNT_TOTAL,
                COALESCE(j.fee_total,  0)      AS FEE_TOTAL,
                COALESCE(j.cnt_60d,    0)      AS CNT_60D
            FROM AJDCAR_PROD.PUBLIC.USERS u
            LEFT JOIN joined j ON j.uid = u.ID
            WHERE {B2B_WHERE}
              AND {USER_FILTER}
            ORDER BY u.PRIMARY_AFFILIATION, u.SECONDARY_AFFILIATION, u.USER_NAME
        """).to_pandas()
        df.rename(columns={
            "USER_PK":    "회원ID",
            "LOGIN_ID":   "로그인ID",
            "USER_NAME":  "딜러성명",
            "BRAND":      "브랜드",
            "BRANCH_NAME":"지점명",
            "CREATED_DT": "회원가입일",
            "DT_FIRST":   "최초계약완료일",
            "DT_LAST":    "최근계약완료일",
            "CNT_TOTAL":  "누적계약체결수",
            "FEE_TOTAL":  "누적총원수보험료",
            "CNT_60D":    "직전60일계약건수",
        }, inplace=True)
        return df

    try:
        df_b2b = get_b2b_list()
    except Exception as e:
        st.error(f"데이터 조회 오류: {e}")
        df_b2b = pd.DataFrame()

    if df_b2b.empty:
        st.info("조회된 데이터가 없습니다. 컬럼명(BRAND, BRANCH_NAME)을 확인해주세요.")
    else:
        # ── KPI 요약 카드 ──────────────────────────────────────
        st.markdown('<div class="section-title">전체 요약</div>', unsafe_allow_html=True)

        total_dealers   = len(df_b2b)
        active_dealers  = int((df_b2b["누적계약체결수"] > 0).sum())
        total_contracts = int(df_b2b["누적계약체결수"].sum())
        total_fee       = int(df_b2b["누적총원수보험료"].sum())
        active_60d      = int((df_b2b["직전60일계약건수"] > 0).sum())
        contracts_60d   = int(df_b2b["직전60일계약건수"].sum())

        k1, k2, k3, k4, k5, k6 = st.columns(6)
        def _kpi(col, label, value):
            col.markdown(
                f'<div class="kpi-card"><div class="kpi-label">{label}</div>'
                f'<div class="kpi-value">{value}</div></div>',
                unsafe_allow_html=True,
            )
        _kpi(k1, "총 딜러수",       f"{total_dealers:,}명")
        _kpi(k2, "체결 딜러수",     f"{active_dealers:,}명")
        _kpi(k3, "누적 체결건수",   f"{total_contracts:,}건")
        _kpi(k4, "누적 원수보험료", f"{total_fee:,.0f}원")
        _kpi(k5, "직전60일 활동 딜러", f"{active_60d:,}명")
        _kpi(k6, "직전60일 체결건수",  f"{contracts_60d:,}건")

        # ── 그룹별 요약 ────────────────────────────────────────
        st.markdown('<div class="section-title">그룹별 집계</div>', unsafe_allow_html=True)

        df_grp = (
            df_b2b
            .groupby(["브랜드", "지점명"], dropna=False)
            .agg(
                딜러수          = ("회원ID",          "count"),
                체결딜러수      = ("누적계약체결수",   lambda x: (x > 0).sum()),
                누적체결건수    = ("누적계약체결수",   "sum"),
                누적원수보험료  = ("누적총원수보험료", "sum"),
                직전60일건수    = ("직전60일계약건수", "sum"),
            )
            .reset_index()
            .sort_values(["브랜드", "지점명"])
        )
        df_grp["누적원수보험료"] = df_grp["누적원수보험료"].apply(lambda x: f"{int(x):,}")
        st.dataframe(df_grp, use_container_width=True, hide_index=True)

        # ── 차트: 지점별 누적 체결건수 ────────────────────────
        st.markdown('<div class="section-title">지점별 누적 체결건수</div>', unsafe_allow_html=True)

        df_chart = (
            df_b2b.groupby(["브랜드", "지점명"])["누적계약체결수"]
            .sum()
            .reset_index()
        )
        df_chart["지점"] = df_chart["브랜드"] + " / " + df_chart["지점명"]

        chart_bar = apply_theme(
            alt.Chart(df_chart)
            .mark_bar()
            .encode(
                x=alt.X("지점:N", sort="-y", title="지점"),
                y=alt.Y("누적계약체결수:Q", title="체결건수"),
                color=alt.Color("브랜드:N", legend=alt.Legend(title="브랜드")),
                tooltip=["지점:N", "누적계약체결수:Q"],
            )
        )
        st.altair_chart(chart_bar, use_container_width=True)

        # ── 월별 실적 추이 ─────────────────────────────────────
        st.markdown('<div class="section-title">소속별 월별 실적 추이</div>', unsafe_allow_html=True)

        try:
            df_trend = get_b2b_trend()
        except Exception as e:
            st.warning(f"추이 데이터 조회 오류: {e}")
            df_trend = pd.DataFrame()

        if not df_trend.empty:
            b8_metric = st.radio(
                "지표 선택", ["체결건수", "원수보험료"],
                horizontal=True, key="b8_metric"
            )
            y_col   = b8_metric
            y_fmt   = ",.0f" if b8_metric == "원수보험료" else ",.0f"
            y_title = f"{b8_metric}{'(원)' if b8_metric == '원수보험료' else '(건)'}"

            # 라인 차트: 소속별 월별 추이
            chart_trend = apply_theme(
                alt.Chart(df_trend)
                .mark_line(point=True, strokeWidth=2)
                .encode(
                    x=alt.X("체결월:N", title="체결월", axis=alt.Axis(labelAngle=-45)),
                    y=alt.Y(f"{y_col}:Q", title=y_title,
                            axis=alt.Axis(format=",.0f")),
                    color=alt.Color("소속:N", legend=alt.Legend(title="소속")),
                    tooltip=["체결월:N", "소속:N",
                             alt.Tooltip(f"{y_col}:Q", format=y_fmt)],
                )
            )
            st.altair_chart(chart_trend, use_container_width=True)

            # 묶음 막대 차트: 월별 × 소속
            st.markdown('<div class="chart-caption">월별 소속 비교 (묶음 막대)</div>', unsafe_allow_html=True)
            chart_grouped = apply_theme(
                alt.Chart(df_trend)
                .mark_bar()
                .encode(
                    x=alt.X("체결월:N", title="체결월", axis=alt.Axis(labelAngle=-45)),
                    y=alt.Y(f"{y_col}:Q", title=y_title,
                            axis=alt.Axis(format=",.0f")),
                    color=alt.Color("소속:N", legend=alt.Legend(title="소속")),
                    xOffset=alt.XOffset("소속:N"),
                    tooltip=["체결월:N", "소속:N",
                             alt.Tooltip(f"{y_col}:Q", format=y_fmt)],
                )
            )
            st.altair_chart(chart_grouped, use_container_width=True)

            # 피벗 테이블: 월 × 소속
            st.markdown('<div class="chart-caption">월별 소속 피벗</div>', unsafe_allow_html=True)
            df_pivot = df_trend.pivot_table(
                index="체결월", columns="소속", values=y_col,
                aggfunc="sum", fill_value=0
            ).reset_index()
            st.dataframe(df_pivot, use_container_width=True, hide_index=True)

        # ── 딜러 상세 테이블 ───────────────────────────────────
        st.markdown('<div class="section-title">딜러 상세 목록</div>', unsafe_allow_html=True)

        # 브랜드/지점 필터
        b8c1, b8c2, b8c3 = st.columns([2, 2, 4])
        with b8c1:
            brand_opts = ["전체"] + sorted(df_b2b["브랜드"].dropna().unique().tolist())
            b8_brand = st.selectbox("브랜드", brand_opts, key="b8_brand")
        with b8c2:
            if b8_brand == "전체":
                branch_opts = ["전체"] + sorted(df_b2b["지점명"].dropna().unique().tolist())
            else:
                branch_opts = ["전체"] + sorted(
                    df_b2b[df_b2b["브랜드"] == b8_brand]["지점명"].dropna().unique().tolist()
                )
            b8_branch = st.selectbox("지점", branch_opts, key="b8_branch")
        with b8c3:
            b8_only_active = st.checkbox("체결 실적 있는 딜러만", value=False, key="b8_active")

        df_disp = df_b2b.copy()
        if b8_brand  != "전체": df_disp = df_disp[df_disp["브랜드"] == b8_brand]
        if b8_branch != "전체": df_disp = df_disp[df_disp["지점명"] == b8_branch]
        if b8_only_active:      df_disp = df_disp[df_disp["누적계약체결수"] > 0]

        df_disp = df_disp.copy()
        df_disp["누적총원수보험료"] = df_disp["누적총원수보험료"].apply(
            lambda x: f"{int(x):,}" if pd.notna(x) else "-"
        )

        col_order = [
            "브랜드", "지점명", "딜러성명", "로그인ID", "회원ID",
            "회원가입일", "최초계약완료일", "최근계약완료일",
            "누적계약체결수", "누적총원수보험료", "직전60일계약건수",
        ]
        col_order = [c for c in col_order if c in df_disp.columns]

        st.caption(f"총 {len(df_disp):,}명")
        st.dataframe(df_disp[col_order], use_container_width=True, hide_index=True, height=500)

        st.download_button(
            "⬇ B2B 딜러 목록 CSV 다운로드",
            df_b2b.to_csv(index=False, encoding="utf-8-sig"),
            "b2b_dealer_list.csv",
            "text/csv",
            key="b8_dl",
        )
