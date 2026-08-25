import { useTarget } from "../lib/useTarget";
import { formatCompactWon, formatPercent } from "../lib/format";

export default function TargetPanel({ scopeKey, rangeKey, premiumSum, defaultTarget = 0 }) {
  const { target, setTarget, loaded } = useTarget(`${scopeKey}|${rangeKey}`, defaultTarget);

  const handleChange = (val) => {
    const num = Number(val.replace(/[^0-9]/g, "")) || 0;
    setTarget(num);
  };

  const rate = target > 0 ? (premiumSum / target) * 100 : 0;

  return (
    <div className="card">
      <div className="target-row">
        <span style={{ color: "var(--ink-muted)" }}>선택 기간 목표매출</span>
        <input
          type="text"
          inputMode="numeric"
          value={loaded ? target.toLocaleString("ko-KR") : ""}
          onChange={(e) => handleChange(e.target.value)}
          placeholder="목표 금액 입력"
        />
        <span style={{ color: "var(--ink-muted)" }}>원</span>
        <span className="chip" style={{ marginLeft: "auto" }}>브라우저에만 저장됨</span>
      </div>

      {target > 0 ? (
        <>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13 }}>
            <span>
              현재 실적 <b>{formatCompactWon(premiumSum)}</b>
            </span>
            <span style={{ fontWeight: 700, color: rate >= 100 ? "var(--good)" : "var(--accent-ink)" }}>
              {formatPercent(rate)} 달성
            </span>
          </div>
          <div className="progress-track">
            <div
              className={`progress-fill ${rate >= 100 ? "over" : ""}`}
              style={{ width: `${Math.min(100, rate)}%` }}
            />
          </div>
        </>
      ) : (
        <p className="section-note" style={{ margin: 0 }}>
          목표 금액을 입력하면 달성률이 실시간으로 계산됩니다.
        </p>
      )}
    </div>
  );
}
