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

// 갱신 관리 샘플 — 만기일은 원본 소스에서 "YY-MM-DD"(예: 26-08-27) 형식으로 내려온다고 전달받아 그 형식으로 저장한다.
// 기준일(2026-08-24)로부터 3/10/22/38/51/70일 후로 흩어놔서, 기본 45일 필터에서 일부는 걸리고 일부는 빠지는 걸 보여준다.
export const RENEWAL_SAMPLE = [
  { customerName: "예시고객A", phone: "010-****-1023", insurer: "현대해상", dueDate: "26-08-27", dealerName: "샘플딜러1", managerName: "이선" },
  { customerName: "예시고객B", phone: "010-****-5591", insurer: "DB손해보험", dueDate: "26-09-03", dealerName: "샘플딜러2", managerName: "김미희" },
  { customerName: "예시고객C", phone: "010-****-2280", insurer: "KB손해보험", dueDate: "26-09-15", dealerName: "샘플딜러1", managerName: "이선" },
  { customerName: "예시고객D", phone: "010-****-7714", insurer: "삼성화재", dueDate: "26-10-01", dealerName: "샘플딜러3", managerName: "최현정" },
  { customerName: "예시고객E", phone: "010-****-4402", insurer: "한화손해보험", dueDate: "26-10-14", dealerName: "샘플딜러2", managerName: "김미희" },
  { customerName: "예시고객F", phone: "010-****-9931", insurer: "흥국화재", dueDate: "26-11-02", dealerName: "샘플딜러4", managerName: "정혜령" },
];

// "YY-MM-DD" -> Date(UTC). 2자리 연도는 20YY로 해석한다.
export function parseShortDate(s) {
  const [yy, mm, dd] = s.split("-").map(Number);
  return new Date(Date.UTC(2000 + yy, mm - 1, dd));
}

export function shortDateToFull(s) {
  const [yy, mm, dd] = s.split("-");
  return `20${yy}-${mm}-${dd}`;
}

export function daysUntil(dueDateStr, todayStr) {
  const due = parseShortDate(dueDateStr);
  const today = new Date(todayStr + "T00:00:00Z");
  return Math.round((due - today) / 86400000);
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
