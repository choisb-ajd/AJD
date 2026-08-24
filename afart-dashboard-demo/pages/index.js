import { useMemo, useState } from "react";
import Head from "next/head";
import { loadRawRows, aggregate } from "../lib/data";
import { formatWon, formatCompactWon, formatCount, formatDateLabel } from "../lib/format";
import PeriodChart from "../components/PeriodChart";

export async function getStaticProps() {
  const rows = loadRawRows();
  const data = aggregate(rows);
  return { props: { data } };
}

const PERIOD_TABS = [
  { key: "daily", label: "일별" },
  { key: "weekly", label: "주별" },
  { key: "monthly", label: "월별" },
];

export default function Home({ data }) {
  const [period, setPeriod] = useState("monthly");
  const [dealerSort, setDealerSort] = useState("premiumSum");

  const periodRows = useMemo(() => {
    const rows = data.periods[period];
    const chartSlice = period === "daily" ? rows.slice(-30) : rows;
    return { table: [...rows].reverse(), chart: chartSlice };
  }, [data, period]);

  const dealerTop = useMemo(() => {
    const sorted = [...data.dealerRank].sort((a, b) => b[dealerSort] - a[dealerSort]);
    return sorted.slice(0, 15);
  }, [data, dealerSort]);
  const dealerRest = data.dealerRank.length - dealerTop.length;
  const dealerRestSum = data.dealerRank
    .slice(15)
    .reduce((s, d) => s + d.premiumSum, 0);
  const dealerRestCount = data.dealerRank
    .slice(15)
    .reduce((s, d) => s + d.count, 0);

  return (
    <>
      <Head>
        <title>AFART 실적 대시보드 (예시)</title>
      </Head>

      <div className="topbar">
        <div className="logo">
          오토<span>AFART</span>
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

      <div className="demo-banner">
        <b>예시 페이지입니다.</b> raw 쿼리 데이터(2026-01-02 ~ 2026-08-24, {formatCount(data.totals.count)})만으로
        만든 프로토타입이라, 실제 배치도 문서에서 다룬 항목 중 아래는 이 예시에 없습니다.
        <ul>
          <li>이 raw 데이터에는 담당 <b>매니저</b> 컬럼이 없어서, 매니저별 실적 대신 <b>딜러별 실적</b>으로 대체했습니다.</li>
          <li>이미 체결 확정된 건만 담겨 있어 지급대기·가입취소 리스트, 비견(비교견적완료) 퍼널은 표현할 수 없습니다.</li>
          <li>G1~G5 그룹, 목표매출 달성률, 인센티브 계산은 정책·마스터데이터가 없어 제외했습니다.</li>
        </ul>
      </div>

      <div className="page">
        <div className="page-head">
          <div>
            <h1>실적 대시보드</h1>
            <p className="sub">체결(지급대기·가입완료) 기준 원수 데이터 예시</p>
          </div>
          <span className="range-chip">
            {data.totals.dateMin} ~ {data.totals.dateMax}
          </span>
        </div>

        <div className="kpi-row">
          <div className="kpi-card">
            <div className="label">체결건수 합계</div>
            <div className="value">{data.totals.count.toLocaleString("ko-KR")}<span className="unit">건</span></div>
          </div>
          <div className="kpi-card">
            <div className="label">원수보험료 합계</div>
            <div className="value">{formatCompactWon(data.totals.premiumSum)}</div>
          </div>
          <div className="kpi-card">
            <div className="label">건당 평균 보험료</div>
            <div className="value">{formatCompactWon(data.totals.avgPremium)}</div>
          </div>
          <div className="kpi-card">
            <div className="label">활동 딜러 수</div>
            <div className="value">{data.totals.dealerCount.toLocaleString("ko-KR")}<span className="unit">명</span></div>
          </div>
        </div>

        <section className="section">
          <div className="section-head">
            <h2>기간별 실적</h2>
            <div className="toggle-group">
              {PERIOD_TABS.map((t) => (
                <button
                  key={t.key}
                  className={period === t.key ? "active" : ""}
                  onClick={() => setPeriod(t.key)}
                >
                  {t.label}
                </button>
              ))}
            </div>
          </div>
          <p className="section-note">
            숫자로 확인하는 실적표가 기본이고, 막대(원수보험료)·선(체결건수) 그래프는 추세 파악용 보조 지표입니다.
          </p>
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
            <h2>가입 보험사 × 가입유형(CM/TM)별 원수보험료</h2>
          </div>
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>보험사</th>
                  {data.insurerPivot.types.map((t) => (
                    <th key={t}>{t}</th>
                  ))}
                  <th>합계</th>
                </tr>
              </thead>
              <tbody>
                {data.insurerPivot.rows.map((row) => (
                  <tr key={row.insurer}>
                    <td>{row.insurer}</td>
                    {data.insurerPivot.types.map((t) => (
                      <td key={t}>{formatWon(row.byType[t])}</td>
                    ))}
                    <td style={{ fontWeight: 600 }}>{formatWon(row.total)}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr>
                  <td>합계</td>
                  {data.insurerPivot.types.map((t) => (
                    <td key={t}>{formatWon(data.insurerPivot.typeTotals[t])}</td>
                  ))}
                  <td>{formatWon(data.insurerPivot.grandTotal)}</td>
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
                  <button
                    className={dealerSort === "premiumSum" ? "active" : ""}
                    onClick={() => setDealerSort("premiumSum")}
                  >
                    보험료순
                  </button>
                  <button
                    className={dealerSort === "count" ? "active" : ""}
                    onClick={() => setDealerSort("count")}
                  >
                    건수순
                  </button>
                </div>
              </div>
              <p className="section-note">
                실제 서비스에서는 상담담당 매니저 기준으로 집계하고, 이 예시에서는 매니저 컬럼이 없어 딜러 기준으로 대체했습니다.
              </p>
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
                    {data.byChannel.map((c) => (
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
            <h2>주유권 발송 대상 리스트</h2>
            <span className="chip gift">가입완료 + 주유권 선택 고객</span>
          </div>
          <p className="section-note">
            {data.gift.summary
              .map((g) => `${g.giftName} ${g.count}건`)
              .join(" · ")}
            {" · 총 "}
            {formatCount(data.gift.list.length)}
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
                {data.gift.list.map((g, i) => (
                  <tr key={i}>
                    <td>{g.contractDate}</td>
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
          <h3>이 예시에서 다루지 못한 항목 (배치도 문서 참고)</h3>
          <ul>
            <li>매니저별 실적 집계 — 상담담당자(counsel_manager_id) 컬럼이 이 raw 데이터엔 없음</li>
            <li>G1~G5 그룹별 배정 회원수 — 딜러유형(business_type) 정보 없음</li>
            <li>지급대기 / 가입취소 전환 리스트, 하루 갱신 건 — 상태 이력(counsel_status_log) 필요</li>
            <li>비견(비교견적완료) 퍼널, 비견비 체결율 — 상태 전환 타임라인 필요</li>
            <li>월별 목표매출 대비 달성률, 실시간 매니저 랭킹 — 목표값 테이블 필요</li>
            <li>이번달 예상 인센티브 계산 — 인센티브 요율 정책 확정 필요</li>
          </ul>
        </div>
      </div>

      <footer className="foot">
        AFART 실적 대시보드 예시 · raw_query.csv 기반 정적 빌드 · 실제 서비스는 DB 실시간 조회로 대체 필요
      </footer>
    </>
  );
}
