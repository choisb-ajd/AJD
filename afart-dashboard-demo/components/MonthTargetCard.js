import { useEffect, useState } from "react";
import { useTarget } from "../lib/useTarget";
import { formatCompactWon, formatPercent } from "../lib/format";

// KPI 카드 자리에 들어가는 압축판 — TargetPanel과 같은 로컬 저장소를 쓰지만
// "선택 기간"이 아니라 상단 날짜 필터와 무관하게 항상 "이번달" 기준으로 고정된다.
// 목표 금액 변경은 관리자 권한(isAdmin)에서만 가능하다 — 입력값은 저장 버튼을 눌러야 반영된다.
export default function MonthTargetCard({ scopeKey, monthKey, premiumSum, defaultTarget = 0, isAdmin }) {
  const { target, setTarget, loaded } = useTarget(`month:${scopeKey}|${monthKey}`, defaultTarget);
  const [draft, setDraft] = useState(target);

  // 소속/매니저 전환으로 scopeKey가 바뀌어 다른 저장값을 불러왔을 때만 입력창을 그 값으로 되돌린다.
  useEffect(() => {
    setDraft(target);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scopeKey, monthKey, loaded]);

  const handleChange = (val) => {
    const num = Number(val.replace(/[^0-9]/g, "")) || 0;
    setDraft(num);
  };

  const dirty = loaded && draft !== target;

  const handleSave = () => {
    if (!isAdmin || !dirty) return;
    setTarget(draft);
  };

  const rate = target > 0 ? (premiumSum / target) * 100 : 0;

  return (
    <div className="kpi-card">
      <div className="label">이번달 목표 매출</div>
      <div className="kpi-target-row">
        <input
          type="text"
          inputMode="numeric"
          className="kpi-target-input"
          value={loaded ? draft.toLocaleString("ko-KR") : ""}
          onChange={(e) => handleChange(e.target.value)}
          placeholder="목표 금액 입력"
          disabled={!isAdmin}
        />
        {isAdmin && (
          <button type="button" className="btn-primary kpi-target-save" onClick={handleSave} disabled={!dirty}>
            저장
          </button>
        )}
      </div>
      {!isAdmin && (
        <div className="kpi-target-rate" style={{ marginBottom: 6 }}>
          목표 매출 변경은 관리자만 가능합니다
        </div>
      )}
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
