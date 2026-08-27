// 이 raw pull에는 없는 값들(앱가입 로그, 상태 전환 이력)을 시연 목적으로 생성한 샘플 데이터.
// 전부 "샘플" 배지가 붙은 영역에서만 쓰인다 — 실제 서비스는 users / counsel_status_log 테이블 필요.

// "소속" 선택지 — 실제로는 로그인한 사용자가 센터상담사 권한(manager → manager_permission → permission →
// permission_scope_mapping → permission_scope 체인)을 가졌을 때만 노출해야 하지만, 이 데모엔 로그인이
// 없어 항상 노출한다. 선택값 자체도 raw pull에 없는 데이터라 필터링에는 연결되지 않는다.
export const AFFILIATION_OPTIONS = ["파이낸셜", "인슈어런스", "파트너스"];

function seededRand(seed) {
  let h = 0;
  for (let i = 0; i < seed.length; i++) h = (h * 31 + seed.charCodeAt(i)) >>> 0;
  return () => {
    h = (h * 1664525 + 1013904223) >>> 0;
    return h / 4294967296;
  };
}

export function generateAppSignups(dateFrom, dateTo) {
  const out = [];
  const start = new Date(dateFrom + "T00:00:00Z");
  const end = new Date(dateTo + "T00:00:00Z");
  const days = Math.min(90, Math.round((end - start) / 86400000) + 1);
  const rand = seededRand(dateFrom + dateTo);
  for (let i = 0; i < days; i++) {
    const d = new Date(end);
    d.setUTCDate(end.getUTCDate() - (days - 1 - i));
    const key = d.toISOString().slice(0, 10);
    const weekday = d.getUTCDay();
    const base = weekday === 0 || weekday === 6 ? 2 : 6;
    out.push({ date: key, count: base + Math.floor(rand() * 6) });
  }
  return out;
}

// 인센티브 요율 — 배치도 문서 06번 섹션의 스켈레톤을 그대로 옮긴 샘플 정책 (실제 정책 미확정)
export const INCENTIVE_TIERS = [
  { min: 0, max: 10_000_000, rate: 0.0, label: "0 ~ 1천만원" },
  { min: 10_000_000, max: 30_000_000, rate: 0.02, label: "1천만 ~ 3천만원" },
  { min: 30_000_000, max: 60_000_000, rate: 0.035, label: "3천만 ~ 6천만원" },
  { min: 60_000_000, max: Infinity, rate: 0.05, label: "6천만원 이상" },
];

export function calcIncentive(premiumSum) {
  let incentive = 0;
  const breakdown = [];
  for (const tier of INCENTIVE_TIERS) {
    const upper = Math.min(premiumSum, tier.max);
    const lower = tier.min;
    if (upper > lower) {
      const amt = (upper - lower) * tier.rate;
      incentive += amt;
      breakdown.push({ ...tier, taxed: upper - lower, amount: amt });
    }
  }
  return { incentive, breakdown };
}
