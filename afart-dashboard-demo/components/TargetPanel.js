import { useEffect, useState } from "react";
import { formatCompactWon, formatPercent } from "../lib/format";

const STORAGE_KEY = "afart-demo-targets-v1";

function loadTargets() {
  if (typeof window === "undefined") return {};
  try {
    return JSON.parse(window.localStorage.getItem(STORAGE_KEY) || "{}");
  } catch {
    return {};
  }
}

function saveTargets(obj) {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(obj));
  } catch {
    // 저장 실패해도 화면 동작에는 지장 없음 (프라이빗 브라우징 등)
  }
}

export default function TargetPanel({ scopeKey, rangeKey, premiumSum, defaultTarget = 0 }) {
  const [targets, setTargets] = useState({});
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    setTargets(loadTargets());
    setLoaded(true);
  }, []);

  const storeKey = `${scopeKey}|${rangeKey}`;
  const target = targets[storeKey] ?? defaultTarget;

  const handleChange = (val) => {
    const num = Number(val.replace(/[^0-9]/g, "")) || 0;
    const next = { ...targets, [storeKey]: num };
    setTargets(next);
    saveTargets(next);
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
