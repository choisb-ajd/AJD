import { INCENTIVE_TIERS, calcIncentive } from "../lib/mockData";
import { formatWon, formatCompactWon, formatPercent } from "../lib/format";

export default function IncentivePanel({ premiumSum }) {
  const { incentive, breakdown } = calcIncentive(premiumSum);

  return (
    <div className="card">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 10 }}>
        <span style={{ fontSize: 13, color: "var(--ink-muted)" }}>이번달 원수보험료 기준 예상 인센티브</span>
        <span style={{ fontSize: 22, fontWeight: 700 }}>{formatWon(incentive)}</span>
      </div>
      <div className="table-wrap">
        <table className="data">
          <thead>
            <tr>
              <th>구간</th>
              <th>요율</th>
              <th>해당 구간 실적</th>
              <th>구간 인센티브</th>
            </tr>
          </thead>
          <tbody>
            {INCENTIVE_TIERS.map((tier) => {
              const applied = breakdown.find((b) => b.label === tier.label);
              return (
                <tr key={tier.label} style={{ opacity: applied ? 1 : 0.4 }}>
                  <td>{tier.label}</td>
                  <td>{formatPercent(tier.rate * 100, 1)}</td>
                  <td>{applied ? formatCompactWon(applied.taxed) : "-"}</td>
                  <td>{applied ? formatWon(applied.amount) : "-"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="mock-note">
        요율은 배치도 문서의 인센티브 스켈레톤을 그대로 옮긴 샘플 값입니다. 실제 구간·요율은 정책 확정 후 「설정 &gt; 인센티브 요율 관리」에서 관리합니다.
      </p>
    </div>
  );
}
