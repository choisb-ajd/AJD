import { useMemo, useState } from "react";
import Head from "next/head";
import {
  loadRawRows,
  toClientRows,
  toGiftRows,
  toPendingRows,
  toCancelledHistoryRows,
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
import SearchPanel from "../components/SearchPanel";
import TargetPanel from "../components/TargetPanel";
import IncentivePanel from "../components/IncentivePanel";
import MockBadge from "../components/MockBadge";
import { GROUPS } from "../lib/groups";
import { generateAppSignups, RENEWAL_TODAY_SAMPLE } from "../lib/mockData";

const COMPANY_MONTHLY_TARGET = 1_000_000_000; // 원수보험료 기준 월 목표 10억원 (직접 전달받은 값)

export async function getStaticProps() {
  const raw = loadRawRows();
  // [date, premium, insurer, joinType, channel, dealerKey, dealerName, managerName, group, hasComparison, prospectToCompDays, compToJoinDays][]
  const packedRows = toClientRows(raw);
  const giftRows = toGiftRows(raw);
  const pendingRows = toPendingRows(raw);
  const cancelledRows = toCancelledHistoryRows(raw);
  const dateMin = packedRows.reduce((m, r) => (m === "" || r[0] < m ? r[0] : m), "");
  const dateMax = packedRows.reduce((m, r) => (m === "" || r[0] > m ? r[0] : m), "");
  const managers = [...new Set(raw.map((r) => r.managerName).filter(Boolean))].sort();
  return {
    props: {
      packedRows,
      giftRows,
      pendingRows,
      cancelledRows,
      managers,
      bounds: { min: dateMin, max: dateMax },
    },
  };
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
  const [period, setPeriod] = useState("monthly");
  const [dealerSort, setDealerSort] = useState("premiumSum");

  const resetFilters = () => {
    setDateFrom(defaultDateFrom);
    setDateTo(defaultDateTo);
    setManager("ALL");
  };

  // 날짜만 적용 (매니저 랭킹처럼 전체 매니저를 비교할 때 사용)
  const rangeRows = useMemo(() => filterRows(rows, { dateFrom, dateTo }), [rows, dateFrom, dateTo]);
  // 날짜 + 매니저 둘 다 적용 (관리자=전체 / 매니저=본인 화면 대부분이 이걸 씀)
  const scopeRows = useMemo(() => filterRows(rangeRows, { manager }), [rangeRows, manager]);

  const agg = useMemo(() => aggregate(scopeRows), [scopeRows]);
  const aggAll = useMemo(() => aggregate(rangeRows), [rangeRows]);

  const periodRows = useMemo(() => {
    const list = agg.periods[period];
    const chartSlice = period === "daily" ? list.slice(-30) : list;
    return { table: [...list].reverse(), chart: chartSlice };
  }, [agg, period]);

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

  const renewalsInRange = RENEWAL_TODAY_SAMPLE.filter((r) => r.dueDate >= dateFrom && r.dueDate <= dateTo);

  return (
    <>
      <Head>
        <title>다이렉트 대시보드 for AFART</title>
      </Head>

      <div className="topbar">
        <div className="logo">
          다이렉트 대시보드 for <span>AFART</span>
        </div>
        <nav>
          <a className="active">실적 대시보드</a>
          <a>회원별 고객 관리</a>
          <a>회원 관리</a>
          <a>출금 관리</a>
          <a>고객 상담</a>
          <a>비교 견적</a>
          <a>설정</a>
        </nav>
      </div>

      <FilterBar
        dateFrom={dateFrom}
        dateTo={dateTo}
        onDateFrom={setDateFrom}
        onDateTo={setDateTo}
        manager={manager}
        onManager={setManager}
        managers={managers}
        bounds={bounds}
        onReset={resetFilters}
      />

      <div className="demo-banner">
        <b>예시 페이지입니다.</b> raw 쿼리 데이터(원본 {formatCount(rows.length)}, 현재 필터 {formatCount(scopeRows.length)})로
        만든 프로토타입입니다. 매니저·딜러유형·상태이력·지급대기/가입취소는 실제 데이터를 그대로 씁니다. <MockBadge /> 표시가 붙은
        영역만 이 raw 데이터에 없는 값이라 시연을 위해 만든 샘플입니다.
        <ul>
          <li>앱가입현황, 하루 갱신 건, 인센티브 요율은 이 raw pull에 아예 없는 값이라 샘플로 대체했습니다.</li>
          <li>신차딜러는 business_sub_type(수입/국산)이 없어 하나로 묶었습니다 — 원래 배치도의 G1/G2 세분화는 불가합니다.</li>
          <li>비견 퍼널의 "전환율"은 이 raw pull이 이미 성사된 건만 담고 있어, 손실 건을 포함한 진짜 전환율이 아니라 "체결 건 중 비교견적을 거친 비율"입니다.</li>
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
            <div className="value">
              {agg.totals.count.toLocaleString("ko-KR")}
              <span className="unit">건</span>
            </div>
          </div>
          <div className="kpi-card">
            <div className="label">원수보험료 합계</div>
            <div className="value">{formatCompactWon(agg.totals.premiumSum)}</div>
          </div>
          <div className="kpi-card">
            <div className="label">건당 평균 보험료</div>
            <div className="value">{formatCompactWon(agg.totals.avgPremium)}</div>
          </div>
          <div className="kpi-card">
            <div className="label">{manager === "ALL" ? "활동 딜러 수" : "담당 딜러 수"}</div>
            <div className="value">
              {agg.totals.dealerCount.toLocaleString("ko-KR")}
              <span className="unit">명</span>
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
            <div className="toggle-group">
              {PERIOD_TABS.map((t) => (
                <button key={t.key} className={period === t.key ? "active" : ""} onClick={() => setPeriod(t.key)}>
                  {t.label}
                </button>
              ))}
            </div>
          </div>
          <p className="section-note">숫자로 확인하는 실적표가 기본이고, 막대(원수보험료)·선(체결건수) 그래프는 추세 파악용 보조 지표입니다.</p>
          <div className="card">
            <PeriodChart
              data={periodRows.chart.map((r) => ({
                label: formatDateLabel(r.label ?? r.key),
                premiumSum: r.premiumSum,
                count: r.count,
              }))}
            />
          </div>
          <div className="table-wrap" style={{ marginTop: 12 }}>
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
                {periodRows.table.map((r) => (
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
        </section>

        <section className="section">
          <div className="section-head">
            <h2>매니저별 실적 랭킹</h2>
          </div>
          <p className="section-note">
            counsel_manager 기준 실제 데이터입니다. 선택한 기간의 전체 매니저를 비교하며, 필터에서 매니저를 고르면 해당 행이 강조됩니다.
          </p>
          <div className="card">
            {aggAll.managerRank.map((m, i) => (
              <div key={m.managerName} className={`rank-row ${m.managerName === manager ? "selected" : ""}`}>
                <span className={`rank-badge ${i < 3 ? "top" : ""}`}>{i + 1}</span>
                <span className="name">{m.managerName}</span>
                <span className="num">담당딜러 {m.dealerCount}</span>
                <span className="num">{formatCount(m.count)}</span>
                <span className="num" style={{ fontWeight: 700, color: "var(--accent-ink)" }}>
                  {formatWon(m.premiumSum)}
                </span>
              </div>
            ))}
          </div>
        </section>

        <section className="section">
          <div className="section-head">
            <h2>비견(비교견적완료) 퍼널{manager !== "ALL" ? ` — ${manager}` : ""}</h2>
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

        <div className="grid-2">
          <section className="section">
            <div className="section-head">
              <h2>선택 기간 목표매출 달성률</h2>
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
              <h2>선택 기간 예상 인센티브</h2>
              <MockBadge>샘플 요율</MockBadge>
            </div>
            <IncentivePanel premiumSum={agg.totals.premiumSum} />
          </section>
        </div>

        <section className="section">
          <div className="section-head">
            <h2>딜러유형별 배정 회원수{manager !== "ALL" ? ` — ${manager}` : ""}</h2>
          </div>
          <p className="section-note">business_type 실제 데이터입니다. 신차딜러는 business_sub_type이 없어 수입/국산으로 나누지 못합니다.</p>
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
                        <td>{formatCount(d.count)}</td>
                        <td>{formatWon(d.premiumSum)}</td>
                      </tr>
                    ))}
                  </tbody>
                  {dealerRest > 0 && (
                    <tfoot>
                      <tr>
                        <td>그 외 {dealerRest}명</td>
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
                <h2>영업채널별 실적</h2>
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
            </div>
          </div>
        </section>

        <section className="section">
          <div className="section-head">
            <h2>하루 갱신 건 집계</h2>
            <MockBadge />
          </div>
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>만기일</th>
                  <th>고객명</th>
                  <th>연락처</th>
                  <th>기존 보험사</th>
                  <th>담당 딜러</th>
                </tr>
              </thead>
              <tbody>
                {renewalsInRange.length === 0 && (
                  <tr>
                    <td colSpan={5} style={{ textAlign: "center", color: "var(--ink-faint)" }}>
                      선택한 기간엔 갱신 예정 건이 없습니다.
                    </td>
                  </tr>
                )}
                {renewalsInRange.map((r, i) => (
                  <tr key={i}>
                    <td>{r.dueDate}</td>
                    <td style={{ textAlign: "left" }}>{r.customerName}</td>
                    <td>{r.phone}</td>
                    <td>{r.insurer}</td>
                    <td>{r.dealerName}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <div className="grid-2">
          <section className="section">
            <div className="section-head">
              <h2>'지급대기' 전환 고객 리스트</h2>
            </div>
            <p className="section-note">현재상태 = ACCUMULATE_PENDING 실제 데이터입니다.</p>
            <div className="table-wrap">
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
                  {pending.length === 0 && (
                    <tr>
                      <td colSpan={5} style={{ textAlign: "center", color: "var(--ink-faint)" }}>
                        해당 조건에 지급대기 건이 없습니다.
                      </td>
                    </tr>
                  )}
                  {pending.map((r, i) => (
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
              <h2>'가입취소' 이력이 있는 건</h2>
            </div>
            <p className="section-note">
              이 raw pull은 최종 성사 건만 담고 있어 현재 가입취소 상태인 건은 없습니다. 대신 이력상 가입취소 후 재가입으로 마무리된
              실제 사례입니다.
            </p>
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>가입취소일시</th>
                    <th>고객명</th>
                    <th>연락처</th>
                    <th>재가입일시</th>
                    <th>매니저</th>
                  </tr>
                </thead>
                <tbody>
                  {cancelled.length === 0 && (
                    <tr>
                      <td colSpan={5} style={{ textAlign: "center", color: "var(--ink-faint)" }}>
                        해당 조건에 가입취소 이력이 없습니다.
                      </td>
                    </tr>
                  )}
                  {cancelled.map((r, i) => (
                    <tr key={i}>
                      <td>{r.cancelledAt}</td>
                      <td style={{ textAlign: "left" }}>{r.customerName}</td>
                      <td>{r.phone}</td>
                      <td>{r.recoveredAt}</td>
                      <td>{r.managerName}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </div>

        <section className="section">
          <div className="section-head">
            <h2>주유권 발송 대상 리스트</h2>
            <span className="chip gift">가입완료 + 주유권 선택 고객</span>
          </div>
          <p className="section-note">
            {gift.summary.map((g) => `${g.giftName} ${g.count}건`).join(" · ") || "해당 기간에 주유권 발송 대상이 없습니다."}
            {gift.summary.length > 0 && ` · 총 ${formatCount(gift.list.length)}`}
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

        <section className="section">
          <div className="section-head">
            <h2>상세검색 — 고객 검색</h2>
          </div>
          <p className="section-note">
            주민번호+이름 / 핸드폰번호+이름 / 차량번호·차대번호로 고객을 찾는 검색 기능 데모입니다. 필터와 무관하게 전체 raw 데이터에서 검색합니다.
          </p>
          <SearchPanel />
        </section>

        <div className="scope-out">
          <h3>실제 서비스 전환 시 필요한 것</h3>
          <ul>
            <li><MockBadge /> 표시가 붙은 섹션(앱가입현황, 하루 갱신 건, 인센티브 요율)은 실제 데이터 소스가 생기기 전까지 샘플입니다</li>
            <li>매니저별 목표매출은 전사 목표(10억)만 반영했고, 개별 목표는 입력 UI만 만들어뒀습니다 — 값 저장은 브라우저 로컬에만 됩니다</li>
            <li>주민번호 검색은 이 raw 데이터에 원천적으로 없어, 실제 서비스에서도 암호화된 customer_rrn 처리 방식을 먼저 정해야 함</li>
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
