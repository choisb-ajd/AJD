import { useTarget } from "../lib/useTarget";
import { formatCompactWon, formatPercent } from "../lib/format";

// KPI 카드 자리에 들어가는 압축판 — TargetPanel과 같은 로컬 저장소를 쓰지만
// "선택 기간"이 아니라 상단 날짜 필터와 무관하게 항상 "이번달" 기준으로 고정된다.
export default function MonthTargetCard({ scopeKey, monthKey, premiumSum, defaultTarget = 0 }) {
  const { target, setTarget, loaded } = useTarget(`month:${scopeKey}|${monthKey}`, defaultTarget);

  const handleChange = (val) => {
    const num = Number(val.replace(/[^0-9]/g, "")) || 0;
    setTarget(num);
  };

  const rate = target > 0 ? (premiumSum / target) * 100 : 0;

  return (
    <div className="kpi-card">
      <div className="label">이번달 목표 매출</div>
      <input
        type="text"
        inputMode="numeric"
        className="kpi-target-input"
        value={loaded ? target.toLocaleString("ko-KR") : ""}
        onChange={(e) => handleChange(e.target.value)}
        placeholder="목표 금액 입력"
      />
      {target > 0 ? (
        <>
          <div className="kpi-target-rate">
            <span>{formatCompactWon(premiumSum)}</span>
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
        <div className="kpi-target-rate" style={{ color: "var(--ink-faint)" }}>
          목표 입력 시 달성률 표시
        </div>
      )}
    </div>
  );
}
