// 이 raw pull에는 없는 값들(앱가입 로그, 상태 전환 이력)을 시연 목적으로 생성한 샘플 데이터.
// 전부 "샘플" 배지가 붙은 영역에서만 쓰인다 — 실제 서비스는 users / counsel_status_log 테이블 필요.

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

export const RENEWAL_TODAY_SAMPLE = [
  { customerName: "예시고객A", phone: "010-****-1023", insurer: "현대해상", dueDate: "2026-08-24", dealerName: "샘플딜러1" },
  { customerName: "예시고객B", phone: "010-****-5591", insurer: "DB손해보험", dueDate: "2026-08-24", dealerName: "샘플딜러2" },
  { customerName: "예시고객C", phone: "010-****-2280", insurer: "KB손해보험", dueDate: "2026-08-24", dealerName: "샘플딜러1" },
  { customerName: "예시고객D", phone: "010-****-7714", insurer: "삼성화재", dueDate: "2026-08-24", dealerName: "샘플딜러3" },
];

export const ACCUMULATE_PENDING_SAMPLE = [
  { customerName: "예시고객E", phone: "010-****-3312", premium: 812400, transitionAt: "2026-08-23 14:02", managerName: "이선" },
  { customerName: "예시고객F", phone: "010-****-8890", premium: 654200, transitionAt: "2026-08-23 11:47", managerName: "김미희" },
  { customerName: "예시고객G", phone: "010-****-1156", premium: 921300, transitionAt: "2026-08-22 16:20", managerName: "정혜령" },
  { customerName: "예시고객H", phone: "010-****-4470", premium: 733100, transitionAt: "2026-08-22 10:05", managerName: "최현정" },
  { customerName: "예시고객I", phone: "010-****-9902", premium: 588900, transitionAt: "2026-08-21 09:41", managerName: "박순미" },
];

export const JOIN_CANCELLED_SAMPLE = [
  { customerName: "예시고객J", phone: "010-****-6631", premium: 512000, transitionAt: "2026-08-23 17:10", reason: "고객 변심", managerName: "송민선" },
  { customerName: "예시고객K", phone: "010-****-2247", premium: 674500, transitionAt: "2026-08-22 13:55", reason: "타사 재가입", managerName: "신영란" },
  { customerName: "예시고객L", phone: "010-****-8813", premium: 399000, transitionAt: "2026-08-20 15:30", reason: "서류 미비", managerName: "진서연" },
];

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
