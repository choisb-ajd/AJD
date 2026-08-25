import { useEffect, useState } from "react";

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

// 브라우저 로컬 저장소에만 남는 목표 금액 — TargetPanel(선택 기간)과
// MonthTargetCard(이번달 KPI 카드)가 같은 스토리지를 storeKey만 다르게 써서 공유한다.
export function useTarget(storeKey, defaultTarget = 0) {
  const [targets, setTargets] = useState({});
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    setTargets(loadTargets());
    setLoaded(true);
  }, []);

  const target = targets[storeKey] ?? defaultTarget;

  const setTarget = (num) => {
    const next = { ...targets, [storeKey]: num };
    setTargets(next);
    saveTargets(next);
  };

  return { target, setTarget, loaded };
}
