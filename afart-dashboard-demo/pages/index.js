import { useEffect, useMemo, useState } from "react";
import Head from "next/head";
import {
  loadRawRows,
  toClientRows,
  toGiftRows,
  toPendingRows,
  toCancelledRows,
  toRenewalRows,
} from "../lib/data";
import { unpackRows } from "../lib/pack";
import { aggregate, filterRows, filterGiftRows, filterListRows } from "../lib/aggregate";
import {
  formatWon,
  formatCompactWon,
  formatCount,
  formatPercent,
  formatDateLabel,
} from "../lib/format";
import PeriodChart from "../components/PeriodChart";
import FilterBar from "../components/FilterBar";
import TargetPanel from "../components/TargetPanel";
import IncentivePanel from "../components/IncentivePanel";
import MockBadge from "../components/MockBadge";
import SalesRawList from "../components/SalesRawList";
import MonthTargetCard from "../components/MonthTargetCard";
import { GROUPS } from "../lib/groups";
import { generateAppSignups, AFFILIATION_OPTIONS } from "../lib/mockData";

const COMPANY_MONTHLY_TARGET = 1_000_000_000; // 원수보험료 기준 월 목표 10억원 (직접 전달받은 값)

export async function getStaticProps() {
  const raw = loadRawRows();
  // [date, premium, insurer, joinType, channel, dealerKey, dealerName, managerName, group, hasComparison, prospectToCompDays, compToJoinDays][]
  const packedRows = toClientRows(raw);
  const giftRows = toGiftRows(raw);
  const pendingRows = toPendingRows(raw);
  const cancelledRows = toCancelledRows(raw);
  const renewalRows = toRenewalRows(raw);
  const dateMin = packedRows.reduce((m, r) => (m === "" || r[0] < m ? r[0] : m), "");
  const dateMax = packedRows.reduce((m, r) => (m === "" || r[0] > m ? r[0] : m), "");
  const managers = [...new Set(raw.map((r) => r.managerName).filter(Boolean))].sort();
  return {
    props: {
      packedRows,
      giftRows,
      pendingRows,
      cancelledRows,
      renewalRows,
      managers,
      bounds: { min: dateMin, max: dateMax },
    },
  };
}

// "YYYY-MM-DD" 두 날짜 사이의 일수 (due - today).
function daysUntilFull(dueDateStr, todayStr) {
  const due = new Date(dueDateStr + "T00:00:00Z");
  const today = new Date(todayStr + "T00:00:00Z");
  return Math.round((due - today) / 86400000);
}

// "YYYY-MM-DD"에서 n일 전 날짜를 돌려준다.
function daysAgoDate(dateStr, n) {
  const d = new Date(dateStr + "T00:00:00Z");
  d.setUTCDate(d.getUTCDate() - n);
  return d.toISOString().slice(0, 10);
}

// "YYYY-MM-DD" 기준으로 n개월 전 달의 1일을 돌려준다 (n=6, 기준일이 8월이면 3월 1일).
function monthsAgoStart(dateStr, n) {
  const [y, m] = dateStr.slice(0, 7).split("-").map(Number);
  const total = y * 12 + (m - 1) - (n - 1);
  const yy = Math.floor(total / 12);
  const mm = (total % 12) + 1;
  return `${yy}-${String(mm).padStart(2, "0")}-01`;
}

// dateStr과 같은 "일"을 바로 전달에서 찾아 돌려준다 (전달에 그 일자가 없으면 전달 말일로 캡).
// 예: 2026-08-24 -> 2026-07-24, 2026-03-31 -> 2026-02-28
function sameDayLastMonth(dateStr) {
  const d = new Date(dateStr + "T00:00:00Z");
  const day = d.getUTCDate();
  const prevMonthFirst = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() - 1, 1));
  const prevMonthLastDay = new Date(
    Date.UTC(prevMonthFirst.getUTCFullYear(), prevMonthFirst.getUTCMonth() + 1, 0)
  ).getUTCDate();
  const cappedDay = Math.min(day, prevMonthLastDay);
  return `${prevMonthFirst.getUTCFullYear()}-${String(prevMonthFirst.getUTCMonth() + 1).padStart(2, "0")}-${String(
    cappedDay
  ).padStart(2, "0")}`;
}

function diffPct(curr, prev) {
  if (!prev) return null;
  return ((curr - prev) / prev) * 100;
}

function deltaLabel(pct) {
  if (pct == null) return "비교 불가 (직전 동기간 데이터 없음)";
  const arrow = pct >= 0 ? "▲" : "▼";
  return `${arrow} ${Math.abs(pct).toFixed(1)}%`;
}

const PERIOD_TABS = [
  { key: "daily", label: "일별" },
  { key: "weekly", label: "주별" },
  { key: "monthly", label: "월별" },
];

export default function Home({
  packedRows,
  giftRows,
  pendingRows,
  cancelledRows,
  renewalRows,
  managers,
  bounds,
}) {
  const rows = useMemo(() => unpackRows(packedRows), [packedRows]);
  // 기본 기간 = 이번 달 1일 ~ 오늘(=데이터상 최신일). bounds.min/max는 date input의 선택 가능 범위로만 쓴다.
  const defaultDateTo = bounds.max;
  const defaultDateFrom = `${defaultDateTo.slice(0, 7)}-01`;
  const [dateFrom, setDateFrom] = useState(defaultDateFrom);
  const [dateTo, setDateTo] = useState(defaultDateTo);
  const [manager, setManager] = useState("ALL");
  const [affiliation, setAffiliation] = useState(AFFILIATION_OPTIONS[0]);
  // 로그인이 없는 데모라 "지금 보고 있는 사람이 관리자인지 센터상담사인지"를 별도 토글로 흉내낸다.
  // 목표 매출 저장 버튼은 어떤 매니저의 데이터를 보고 있는지(manager)와 무관하게 이 값으로만 갈린다 —
  // 관리자는 매니저를 바꿔가며 각자의 목표를 설정할 수 있고, 센터상담사는 항상 읽기 전용이다.
  const [viewerRole, setViewerRole] = useState("ADMIN");
  const isViewerAdmin = viewerRole === "ADMIN";
  const [dealerSort, setDealerSort] = useState("premiumSum");
  const [giftShipDate, setGiftShipDate] = useState("");
  const [renewalDaysAhead, setRenewalDaysAhead] = useState(45);

  // 매니저 드롭다운은 소속 선택에 따라 재직중 + 센터상담사 권한을 가진 매니저만 나열된다.
  // 이 raw pull의 매니저는 전부 소속=파이낸셜로 확인되어(2026-08-27), 다른 소속을 고르면
  // 목록이 비게 된다 — 실제 서비스에서는 매니저마다 소속이 다양하게 채워져 있을 것이다.
  const managersInAffiliation = affiliation === "파이낸셜" ? managers : [];

  // 소속을 바꿔서 현재 선택된 매니저가 새 목록에 없으면 '전체'로 되돌린다.
  useEffect(() => {
    if (manager !== "ALL" && !managersInAffiliation.includes(manager)) {
      setManager("ALL");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [affiliation]);

  const resetFilters = () => {
    setDateFrom(defaultDateFrom);
    setDateTo(defaultDateTo);
    setManager("ALL");
    setAffiliation(AFFILIATION_OPTIONS[0]);
  };

  // 날짜만 적용 (매니저 랭킹처럼 전체 매니저를 비교할 때 사용)
  const rangeRows = useMemo(() => filterRows(rows, { dateFrom, dateTo }), [rows, dateFrom, dateTo]);
  // 날짜 + 매니저 둘 다 적용 (관리자=전체 / 매니저=본인 화면 대부분이 이걸 씀)
  const scopeRows = useMemo(() => filterRows(rangeRows, { manager }), [rangeRows, manager]);

  const agg = useMemo(() => aggregate(scopeRows), [scopeRows]);
  const aggAll = useMemo(() => aggregate(rangeRows), [rangeRows]);

  // 직전 동기간 비교용 — "이번달 1일" 기준점만 필요하다 (상단 날짜 필터와는 별개).
  const oneMonthStart = useMemo(() => monthsAgoStart(bounds.max, 1), [bounds.max]);

  // 직전 동기간 = 바로 전달의 같은 날짜 범위(이번달 1일~오늘 대비 지난달 1일~같은 일자).
  // 트렌드 탭(일/주/월)과 무관하게 항상 이번달 vs 지난달로 고정.
  const curCompareFrom = oneMonthStart; // 이번달 1일
  const curCompareTo = bounds.max; // 오늘
  const prevCompareFrom = useMemo(() => monthsAgoStart(bounds.max, 2), [bounds.max]); // 지난달 1일
  const prevCompareTo = useMemo(() => sameDayLastMonth(bounds.max), [bounds.max]); // 지난달 같은 일자

  const curCompareRows = useMemo(
    () => filterRows(rows, { dateFrom: curCompareFrom, dateTo: curCompareTo, manager }),
    [rows, curCompareFrom, curCompareTo, manager]
  );
  const prevCompareRows = useMemo(
    () => filterRows(rows, { dateFrom: prevCompareFrom, dateTo: prevCompareTo, manager }),
    [rows, prevCompareFrom, prevCompareTo, manager]
  );
  const curCompareAgg = useMemo(() => aggregate(curCompareRows), [curCompareRows]);
  const prevCompareAgg = useMemo(() => aggregate(prevCompareRows), [prevCompareRows]);
  const periodComparison = {
    prevFrom: prevCompareFrom,
    prevTo: prevCompareTo,
    premiumPct: diffPct(curCompareAgg.totals.premiumSum, prevCompareAgg.totals.premiumSum),
    countPct: diffPct(curCompareAgg.totals.count, prevCompareAgg.totals.count),
    incomplete: prevCompareFrom < bounds.min,
  };

  const periodRows = useMemo(() => {
    const build = (key) => {
      const list = agg.periods[key];
      const chartSlice = key === "daily" ? list.slice(-30) : list;
      return { table: [...list].reverse(), chart: chartSlice };
    };
    return { daily: build("daily"), weekly: build("weekly"), monthly: build("monthly") };
  }, [agg]);

  const dealerTop = useMemo(() => {
    return [...agg.dealerRank].sort((a, b) => b[dealerSort] - a[dealerSort]).slice(0, 15);
  }, [agg, dealerSort]);
  const dealerRest = agg.dealerRank.length - dealerTop.length;
  const dealerRestSum = agg.dealerRank.slice(15).reduce((s, d) => s + d.premiumSum, 0);
  const dealerRestCount = agg.dealerRank.slice(15).reduce((s, d) => s + d.count, 0);

  const appSignups = useMemo(() => generateAppSignups(dateFrom, dateTo), [dateFrom, dateTo]);
  const appSignupTotal = appSignups.reduce((s, d) => s + d.count, 0);

  const groupRows = GROUPS.map((g) => ({
    ...g,
    dealerCount: agg.groupDealerCount.get(g.code)?.size || 0,
  }));

  // 담당 딜러 수 — "딜러 전담 매니저"(users.manager_id) 기준. 상담을 처리한 매니저(managerName)와는
  // 다른 축이라 상단 기간 필터와 무관하게, 전체 = 배정 여부만(체결 이력 전체), 활동 = 오늘(bounds.max)로부터
  // 최근 60일 이내 체결(=체결일자) 실적이 있는 딜러만 센다.
  const activeSinceDate = useMemo(() => daysAgoDate(bounds.max, 60), [bounds.max]);
  const dealerCounts = useMemo(() => {
    const scope = manager === "ALL" ? rows : rows.filter((r) => r.dealerManagerName === manager);
    const total = new Set(scope.map((r) => r.dealerKey)).size;
    const active = new Set(scope.filter((r) => r.date >= activeSinceDate).map((r) => r.dealerKey)).size;
    return { total, active };
  }, [rows, manager, activeSinceDate]);

  const managerDealerCounts = useMemo(() => {
    const map = new Map();
    for (const r of rows) {
      if (!map.has(r.dealerManagerName)) map.set(r.dealerManagerName, { total: new Set(), active: new Set() });
      const entry = map.get(r.dealerManagerName);
      entry.total.add(r.dealerKey);
      if (r.date >= activeSinceDate) entry.active.add(r.dealerKey);
    }
    return map;
  }, [rows, activeSinceDate]);

  const gift = useMemo(
    () => filterGiftRows(giftRows, { dateFrom, dateTo, manager }),
    [giftRows, dateFrom, dateTo, manager]
  );
  const pending = useMemo(
    () => filterListRows(pendingRows, { dateFrom, dateTo, manager }),
    [pendingRows, dateFrom, dateTo, manager]
  );
  const cancelled = useMemo(
    () => filterListRows(cancelledRows, { dateFrom, dateTo, manager }),
    [cancelledRows, dateFrom, dateTo, manager]
  );

  // 갱신 관리 — 오늘(bounds.max) 기준으로 만기가 renewalDaysAhead일 이내로 도래한 건만, 가까운 순으로.
  const renewalUpcoming = useMemo(() => {
    return renewalRows
      .filter((r) => manager === "ALL" || r.managerName === manager)
      .map((r) => ({ ...r, daysLeft: daysUntilFull(r.dueDate, bounds.max) }))
      .filter((r) => r.daysLeft <= renewalDaysAhead)
      .sort((a, b) => a.daysLeft - b.daysLeft);
  }, [renewalRows, manager, bounds.max, renewalDaysAhead]);
  const pendingShown = pending.slice(0, 30);
  const topManagerPremium = aggAll.managerRank[0]?.premiumSum || 1;

  return (
    <>
      <Head>
        <title>다이렉트 대시보드 for AFART</title>
        <meta name="robots" content="noindex, nofollow, noarchive" />
      </Head>

      <div className="topbar">
        <div className="logo">
          다이렉트 대시보드 for <span>AFART</span>
        </div>
        <nav>
          <a className="active">실적 대시보드</a>
        </nav>
        <div className="role-toggle" style={{ marginLeft: "auto" }}>
          <span className="role-toggle-label">내 권한 (데모)</span>
          <button
            type="button"
            className={viewerRole === "ADMIN" ? "active" : ""}
            onClick={() => setViewerRole("ADMIN")}
          >
            관리자
          </button>
          <button
            type="button"
            className={viewerRole === "COUNSELOR" ? "active" : ""}
            onClick={() => setViewerRole("COUNSELOR")}
          >
            센터상담사
          </button>
        </div>
      </div>

      <FilterBar
        dateFrom={dateFrom}
        dateTo={dateTo}
        onDateFrom={setDateFrom}
        onDateTo={setDateTo}
        manager={manager}
        onManager={setManager}
        managers={managersInAffiliation}
        bounds={bounds}
        onReset={resetFilters}
        affiliation={affiliation}
        onAffiliation={setAffiliation}
        affiliationOptions={AFFILIATION_OPTIONS}
      />

      <div className="demo-banner">
        <b>예시 페이지입니다.</b> raw 쿼리 데이터(원본 {formatCount(rows.length)}, 현재 필터 {formatCount(scopeRows.length)})로
        만든 프로토타입입니다. 매니저·딜러유형·상태이력·지급대기/가입취소는 실제 데이터를 그대로 씁니다. <MockBadge /> 표시가 붙은
        영역만 이 raw 데이터에 없는 값이라 시연을 위해 만든 샘플입니다.
        <ul>
          <li>앱가입현황, 인센티브 요율은 이 raw pull에 아예 없는 값이라 샘플로 대체했습니다.</li>
          <li>신차딜러는 business_sub_type(수입/국산)이 없어 하나로 묶었습니다 — 원래 배치도의 G1/G2 세분화는 불가합니다.</li>
          <li>비견 퍼널의 "전환율"은 이 raw pull이 이미 성사된 건만 담고 있어, 손실 건을 포함한 진짜 전환율이 아니라 "체결 건 중 비교견적을 거친 비율"입니다.</li>
          <li>"소속"에 따라 매니저 드롭다운이 필터링됩니다(소속 + 재직중 + 센터상담사 권한을 만족하는 매니저만 노출). 이 raw pull의 매니저는 전부 소속=파이낸셜로 확인되어, 인슈어런스·파트너스를 고르면 매니저 목록이 비게 됩니다(실제 서비스에서는 매니저마다 소속이 다양합니다).</li>
          <li>우측 상단 "내 권한" 토글은 로그인이 없는 데모라 지금 보고 있는 사람이 관리자인지 센터상담사인지를 흉내낸 것입니다. 실제 서비스에서는 로그인한 계정의 권한으로 자동 판별됩니다.</li>
        </ul>
      </div>

      <div className="page">
        <div className="page-head">
          <div>
            <h1>실적 대시보드</h1>
            <p className="sub">체결(지급대기·가입완료) 기준 원수 데이터</p>
          </div>
          <span className="range-chip">
            {dateFrom} ~ {dateTo}
          </span>
        </div>

        <div className="kpi-row">
          <div className="kpi-card">
            <div className="label">체결건수 합계</div>
            <div className="kpi-split">
              <div className="kpi-split-row">
                <span className="kpi-split-label">가입완료</span>
                <span className="kpi-split-value">
                  {agg.totals.joinCompletedCount.toLocaleString("ko-KR")}
                  <span className="unit">건</span>
                </span>
              </div>
              <div className="kpi-split-row">
                <span className="kpi-split-label">지급대기</span>
                <span className="kpi-split-value">
                  {agg.totals.pendingCount.toLocaleString("ko-KR")}
                  <span className="unit">건</span>
                </span>
              </div>
            </div>
          </div>
          <div className="kpi-card">
            <div className="label">원수보험료 합계</div>
            <div className="value" style={{ fontSize: 19 }}>
              {formatWon(agg.totals.premiumSum)}
            </div>
          </div>
          <MonthTargetCard
            scopeKey={manager}
            monthKey={bounds.max.slice(0, 7)}
            premiumSum={curCompareAgg.totals.premiumSum}
            defaultTarget={manager === "ALL" ? COMPANY_MONTHLY_TARGET : 0}
            isAdmin={isViewerAdmin}
          />
          <div className="kpi-card">
            <div className="label">담당 딜러 수</div>
            <div className="kpi-split">
              <div className="kpi-split-row">
                <span className="kpi-split-label">전체</span>
                <span className="kpi-split-value">
                  {dealerCounts.total.toLocaleString("ko-KR")}
                  <span className="unit">명</span>
                </span>
              </div>
              <div className="kpi-split-row">
                <span className="kpi-split-label">활동(60일)</span>
                <span className="kpi-split-value">
                  {dealerCounts.active.toLocaleString("ko-KR")}
                  <span className="unit">명</span>
                </span>
              </div>
            </div>
          </div>
        </div>

        <section className="section">
          <div className="section-head">
            <h2>앱 가입현황</h2>
            <MockBadge />
          </div>
          <p className="section-note">raw 데이터엔 앱 회원가입 로그가 없어 선택한 기간 길이에 맞춰 생성한 샘플 추이입니다.</p>
          <div className="card">
            <div style={{ marginBottom: 10, fontSize: 13, color: "var(--ink-muted)" }}>
              선택 기간 신규가입 <b style={{ color: "var(--ink)" }}>{formatCount(appSignupTotal)}</b>
            </div>
            <PeriodChart
              mode="count"
              valueLabel="앱 가입 건수"
              data={appSignups.map((d) => ({
                label: formatDateLabel(d.date),
                premiumSum: d.count,
                count: d.count,
              }))}
            />
          </div>
        </section>

        <section className="section">
          <div className="section-head">
            <h2>기간별 실적{manager !== "ALL" ? ` — ${manager}` : ""}</h2>
          </div>
          <p className="section-note">
            숫자로 확인하는 실적표가 기본이고, 막대(원수보험료)·선(체결건수) 그래프는 추세 파악용 보조 지표입니다. 상단 날짜 필터에서
            고른 기간({dateFrom} ~ {dateTo}) 기준으로 집계됩니다 — 첫 화면 기본값은 이번달 1일~오늘입니다.
          </p>
          <div className="compare-row">
            <span className="compare-label">
              직전 동기간(지난달, {periodComparison.prevFrom} ~ {periodComparison.prevTo}) 대비 — 이번달 {curCompareFrom} ~{" "}
              {curCompareTo} 기준
            </span>
            <span className={`compare-value ${periodComparison.premiumPct != null && periodComparison.premiumPct < 0 ? "down" : "up"}`}>
              원수보험료 {deltaLabel(periodComparison.premiumPct)}
            </span>
            <span className={`compare-value ${periodComparison.countPct != null && periodComparison.countPct < 0 ? "down" : "up"}`}>
              체결건수 {deltaLabel(periodComparison.countPct)}
            </span>
            {periodComparison.incomplete && (
              <span style={{ color: "var(--ink-faint)" }}>
                ⚠ 데이터가 {bounds.min}부터 시작이라 지난달 실적이 비어 있어 증감률을 비교할 수 없습니다
              </span>
            )}
          </div>

          {PERIOD_TABS.map((t, i) => (
            <div key={t.key} className="period-block" style={{ marginTop: i === 0 ? 0 : 28 }}>
              <h3 className="period-block-title">{t.label}</h3>
              <div className="card">
                <PeriodChart
                  data={periodRows[t.key].chart.map((r) => ({
                    label: formatDateLabel(r.label ?? r.key),
                    premiumSum: r.premiumSum,
                    count: r.count,
                  }))}
                />
              </div>
              <div className="table-wrap table-scroll-6" style={{ marginTop: 12 }}>
                <table className="data">
                  <thead>
                    <tr>
                      <th>기간</th>
                      <th>체결건수</th>
                      <th>원수보험료 합계</th>
                      <th>건당 평균</th>
                    </tr>
                  </thead>
                  <tbody>
                    {periodRows[t.key].table.map((r) => (
                      <tr key={r.key}>
                        <td>{formatDateLabel(r.label ?? r.key)}</td>
                        <td>{formatCount(r.count)}</td>
                        <td>{formatWon(r.premiumSum)}</td>
                        <td>{formatWon(r.avgPremium)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ))}
        </section>

        <section className="section">
          <div className="section-head">
            <h2>매출 리스트</h2>
          </div>
          <p className="section-note">
            기간을 지정해서 원본에 가까운 건별 데이터를 확인합니다.
            상담(체결)매니저와 딜러 전담 매니저가 <span style={{ color: "var(--warn)", fontWeight: 600 }}>다른 행은 연한 주황</span>으로
            표시됩니다.
          </p>
          <SalesRawList initialFrom={dateFrom} initialTo={dateTo} bounds={bounds} />
        </section>

        <section className="section">
          <div className="section-head">
            <h2>가입취소 리스트</h2>
          </div>
          <p className="section-note">
            현재 상태가 실제로 가입취소(JOIN_CANCELLED)인 상담 건만 보여줍니다.
          </p>
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>가입취소일시</th>
                  <th>고객명</th>
                  <th>연락처</th>
                  <th>체결일</th>
                  <th>가입보험사</th>
                  <th>가입유형</th>
                  <th>보험료</th>
                  <th>매니저</th>
                  <th>딜러(회원)</th>
                </tr>
              </thead>
              <tbody>
                {cancelled.length === 0 && (
                  <tr>
                    <td colSpan={9} style={{ textAlign: "center", color: "var(--ink-faint)" }}>
                      해당 조건에 가입취소 건이 없습니다.
                    </td>
                  </tr>
                )}
                {cancelled.map((r, i) => (
                  <tr key={i}>
                    <td>{r.cancelledAt}</td>
                    <td style={{ textAlign: "left" }}>{r.customerName}</td>
                    <td>{r.phone}</td>
                    <td>{r.contractDate || "-"}</td>
                    <td>{r.insurer}</td>
                    <td>{r.joinType}</td>
                    <td>{formatWon(r.premium)}</td>
                    <td>{r.managerName}</td>
                    <td style={{ textAlign: "left" }}>
                      {r.dealerName} · {r.dealerManagerName}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="section">
          <div className="section-head">
            <h2>매니저별 실적 랭킹</h2>
          </div>
          <p className="section-note">
            counsel_manager 기준 실제 데이터입니다. 선택한 기간의 전체 매니저를 비교하며, 필터에서 매니저를 고르면 해당 행이 강조됩니다.
          </p>
          <div className="card">
            {aggAll.managerRank.map((m, i) => {
              const pct = Math.max(6, (m.premiumSum / topManagerPremium) * 100);
              const medal = i === 0 ? "🥇" : i === 1 ? "🥈" : i === 2 ? "🥉" : null;
              return (
                <div key={m.managerName} className={`rank-row ${m.managerName === manager ? "selected" : ""}`}>
                  <span className={`rank-badge ${i < 3 ? "top" : ""}`}>{medal || i + 1}</span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 8 }}>
                      <span className="name">{m.managerName}</span>
                      <span style={{ fontSize: 12, color: "var(--ink-muted)" }}>
                        배정 {managerDealerCounts.get(m.managerName)?.total.size || 0} · 활동{" "}
                        {managerDealerCounts.get(m.managerName)?.active.size || 0} · {formatCount(m.count)} ·{" "}
                        <b style={{ color: "var(--accent-ink)", fontSize: 13 }}>{formatWon(m.premiumSum)}</b>
                      </span>
                    </div>
                    <div className="race-track">
                      <div className="race-fill" style={{ width: `${pct}%` }} />
                      <span className="race-runner" style={{ left: `${pct}%` }}>
                        🏃💨
                      </span>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </section>

        <section className="section">
          <div className="section-head">
            <h2>개인별 목표 매출 달성률</h2>
          </div>
          <TargetPanel
            scopeKey={manager}
            rangeKey={`${dateFrom}~${dateTo}`}
            premiumSum={agg.totals.premiumSum}
            defaultTarget={manager === "ALL" ? COMPANY_MONTHLY_TARGET : 0}
          />
        </section>

        <section className="section">
          <div className="section-head">
            <h2>예상 인센티브</h2>
            <MockBadge>샘플 요율</MockBadge>
          </div>
          <IncentivePanel premiumSum={agg.totals.premiumSum} />
        </section>

        <section className="section">
          <div className="section-head">
            <h2>비교견적 추적{manager !== "ALL" ? ` — ${manager}` : ""}</h2>
          </div>
          <p className="section-note">
            상태전환이력을 파싱해 만든 실제 지표입니다. 다만 이 raw pull은 이미 성사된 건만 담고 있어, "비견 후 이탈"까지 포함한 진짜
            전환율은 계산할 수 없습니다 — 아래 비율은 체결 건 중 비교견적 단계를 거친 비중입니다.
          </p>
          <div className="kpi-row" style={{ gridTemplateColumns: "repeat(3, 1fr)" }}>
            <div className="kpi-card">
              <div className="label">비견 경유 체결 (전체 대비)</div>
              <div className="value">
                {formatCount(agg.funnel.comparisonCount)}
                <span className="unit">{formatPercent(agg.funnel.comparisonRate)}</span>
              </div>
            </div>
            <div className="kpi-card">
              <div className="label">가망상담 → 비견 평균 소요일</div>
              <div className="value">
                {agg.funnel.avgProspectToCompDays != null ? agg.funnel.avgProspectToCompDays.toFixed(1) : "-"}
                <span className="unit">일</span>
              </div>
            </div>
            <div className="kpi-card">
              <div className="label">비견 → 체결 평균 소요일</div>
              <div className="value">
                {agg.funnel.avgCompToJoinDays != null ? agg.funnel.avgCompToJoinDays.toFixed(1) : "-"}
                <span className="unit">일</span>
              </div>
            </div>
          </div>
        </section>

        <section className="section">
          <div className="section-head">
            <h2>가입 보험사 × 가입유형(CM/TM)별 원수보험료{manager !== "ALL" ? ` — ${manager}` : ""}</h2>
          </div>
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>보험사</th>
                  {agg.insurerPivot.types.map((t) => (
                    <th key={t}>{t}</th>
                  ))}
                  <th>합계</th>
                </tr>
              </thead>
              <tbody>
                {agg.insurerPivot.rows.map((row) => (
                  <tr key={row.insurer}>
                    <td>{row.insurer}</td>
                    {agg.insurerPivot.types.map((t) => (
                      <td key={t}>{formatWon(row.byType[t])}</td>
                    ))}
                    <td style={{ fontWeight: 600 }}>{formatWon(row.total)}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr>
                  <td>합계</td>
                  {agg.insurerPivot.types.map((t) => (
                    <td key={t}>{formatWon(agg.insurerPivot.typeTotals[t])}</td>
                  ))}
                  <td>{formatWon(agg.insurerPivot.grandTotal)}</td>
                </tr>
              </tfoot>
            </table>
          </div>
        </section>

        <section className="section">
          <div className="grid-2">
            <div>
              <div className="section-head">
                <h2>딜러별 실적 TOP 15</h2>
                <div className="toggle-group">
                  <button className={dealerSort === "premiumSum" ? "active" : ""} onClick={() => setDealerSort("premiumSum")}>
                    보험료순
                  </button>
                  <button className={dealerSort === "count" ? "active" : ""} onClick={() => setDealerSort("count")}>
                    건수순
                  </button>
                </div>
              </div>
              <div className="table-wrap">
                <table className="data">
                  <thead>
                    <tr>
                      <th>딜러</th>
                      <th>딜러유형</th>
                      <th>담당 매니저</th>
                      <th>체결건수</th>
                      <th>원수보험료</th>
                    </tr>
                  </thead>
                  <tbody>
                    {dealerTop.map((d, i) => (
                      <tr key={`${d.dealerName}-${i}`}>
                        <td>
                          <span className={`rank-badge ${i < 3 ? "top" : ""}`}>{i + 1}</span>
                          {d.dealerName}
                        </td>
                        <td>{GROUPS.find((g) => g.code === d.group)?.label ?? "-"}</td>
                        <td>{d.managerName}</td>
                        <td>{formatCount(d.count)}</td>
                        <td>{formatWon(d.premiumSum)}</td>
                      </tr>
                    ))}
                  </tbody>
                  {dealerRest > 0 && (
                    <tfoot>
                      <tr>
                        <td>그 외 {dealerRest}명</td>
                        <td>-</td>
                        <td>-</td>
                        <td>{formatCount(dealerRestCount)}</td>
                        <td>{formatWon(dealerRestSum)}</td>
                      </tr>
                    </tfoot>
                  )}
                </table>
              </div>
            </div>

            <div>
              <div className="section-head">
                <h2>유입채널별 실적</h2>
              </div>
              <div className="table-wrap">
                <table className="data">
                  <thead>
                    <tr>
                      <th>채널</th>
                      <th>체결건수</th>
                      <th>원수보험료</th>
                    </tr>
                  </thead>
                  <tbody>
                    {agg.byChannel.map((c) => (
                      <tr key={c.channel}>
                        <td>{c.channel}</td>
                        <td>{formatCount(c.count)}</td>
                        <td>{formatWon(c.premiumSum)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="section-head" style={{ marginTop: 24 }}>
                <h2>딜러유형별 배정 회원수{manager !== "ALL" ? ` — ${manager}` : ""}</h2>
              </div>
              <p className="section-note">
                business_type 실제 데이터입니다. 신차딜러는 business_sub_type이 없어 수입/국산으로 나누지 못합니다.
              </p>
              <div className="table-wrap">
                <table className="data">
                  <thead>
                    <tr>
                      <th>딜러유형</th>
                      <th>배정 회원수</th>
                    </tr>
                  </thead>
                  <tbody>
                    {groupRows.map((g) => (
                      <tr key={g.code}>
                        <td>{g.label}</td>
                        <td>{g.dealerCount.toLocaleString("ko-KR")}명</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </section>

        <section className="section">
          <div className="section-head">
            <h2>갱신 관리</h2>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10, fontSize: 13 }}>
            <span style={{ color: "var(--ink-muted)" }}>만기 도래</span>
            <input
              type="number"
              min={0}
              className="date-input"
              style={{ width: 70, textAlign: "right" }}
              value={renewalDaysAhead}
              onChange={(e) => setRenewalDaysAhead(Math.max(0, Number(e.target.value) || 0))}
            />
            <span style={{ color: "var(--ink-muted)" }}>일 전부터 표시 (오늘 = {bounds.max} 기준, 기본값 45일)</span>
          </div>
          <p className="section-note">만기일이 가까운 순으로 정렬됩니다. 이미 만기가 지난 건은 맨 위에 표시됩니다.</p>
          <div className={`table-wrap ${renewalUpcoming.length > 10 ? "table-scroll-sm" : ""}`}>
            <table className="data">
              <thead>
                <tr>
                  <th>만기일</th>
                  <th>고객명</th>
                  <th>연락처</th>
                  <th>기존 보험사</th>
                  <th>담당 딜러</th>
                  <th>체결 매니저</th>
                </tr>
              </thead>
              <tbody>
                {renewalUpcoming.length === 0 && (
                  <tr>
                    <td colSpan={6} style={{ textAlign: "center", color: "var(--ink-faint)" }}>
                      해당 조건에 갱신 예정 건이 없습니다.
                    </td>
                  </tr>
                )}
                {renewalUpcoming.map((r, i) => (
                  <tr key={i}>
                    <td>{r.dueDate}</td>
                    <td style={{ textAlign: "left" }}>{r.customerName}</td>
                    <td>{r.phone}</td>
                    <td>{r.insurer}</td>
                    <td>{r.dealerName}</td>
                    <td>{r.managerName}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="section">
          <div className="section-head">
            <h2>'지급대기' 전환 고객 리스트</h2>
          </div>
          <p className="section-note">
            현재상태 = ACCUMULATE_PENDING 실제 데이터입니다.
            {pending.length > 30 && ` 최근 30건만 표시하고 스크롤됩니다 (전체 ${formatCount(pending.length)}).`}
          </p>
          <div className="table-wrap table-scroll">
            <table className="data">
              <thead>
                <tr>
                  <th>전환일시</th>
                  <th>고객명</th>
                  <th>연락처</th>
                  <th>보험료</th>
                  <th>매니저</th>
                </tr>
              </thead>
              <tbody>
                {pendingShown.length === 0 && (
                  <tr>
                    <td colSpan={5} style={{ textAlign: "center", color: "var(--ink-faint)" }}>
                      해당 조건에 지급대기 건이 없습니다.
                    </td>
                  </tr>
                )}
                {pendingShown.map((r, i) => (
                  <tr key={i}>
                    <td>{r.transitionAt}</td>
                    <td style={{ textAlign: "left" }}>{r.customerName}</td>
                    <td>{r.phone}</td>
                    <td>{formatWon(r.premium)}</td>
                    <td>{r.managerName}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="section">
          <div className="section-head">
            <h2>주유권 발송 대상 리스트</h2>
            <div className="filter-field">
              <label>발송예정일자</label>
              <input type="date" value={giftShipDate} onChange={(e) => setGiftShipDate(e.target.value)} />
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span className="chip gift">가입완료 + 주유권 선택 고객</span>
              <button type="button" className="btn-primary">
                엑셀 다운로드
              </button>
            </div>
          </div>
          <p className="section-note">
            {gift.summary.map((g) => `${g.giftName} ${g.count}건`).join(" · ") || "해당 기간에 주유권 발송 대상이 없습니다."}
            {gift.summary.length > 0 && ` · 총 ${formatCount(gift.list.length)}`} — 위에서 고른 발송예정일자가 이 목록 전체에 일괄 적용됩니다.
          </p>
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>체결일</th>
                  <th>고객명</th>
                  <th>연락처</th>
                  <th>권종</th>
                  <th>담당 딜러</th>
                </tr>
              </thead>
              <tbody>
                {gift.list.map((g, i) => (
                  <tr key={i}>
                    <td>{g.date}</td>
                    <td style={{ textAlign: "left" }}>{g.customerName}</td>
                    <td>{g.phone}</td>
                    <td>{g.giftName}</td>
                    <td>{g.dealerName}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <div className="scope-out">
          <h3>실제 서비스 전환 시 필요한 것</h3>
          <ul>
            <li><MockBadge /> 표시가 붙은 섹션(앱가입현황, 인센티브 요율)은 실제 데이터 소스가 생기기 전까지 샘플입니다</li>
            <li>매니저별 목표매출은 전사 목표(10억)만 반영했고, 개별 목표는 입력 UI만 만들어뒀습니다 — 값 저장은 브라우저 로컬에만 됩니다</li>
            <li>상세검색(주민번호/핸드폰/차량번호)은 이 데모 범위에서 빼고 별도로 개발 요청 예정입니다</li>
            <li>자세한 데이터 매핑·조인 기준은 별도 공유된 배치도 문서를 참고</li>
          </ul>
        </div>
      </div>

      <footer className="foot">
        다이렉트 대시보드 for AFART · 예시 · raw_query.csv 기반 정적 빌드 + 브라우저 필터링
      </footer>
    </>
  );
}
