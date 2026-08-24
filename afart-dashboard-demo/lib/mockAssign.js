// raw_query.csv에는 담당 매니저 / 딜러유형 컬럼이 없습니다.
// "매니저별 실적", "G1~G5 그룹별 배정" 기능이 실제로 동작하는 모습을 보여주기 위해
// 딜러ID를 해시해서 가상의 매니저/그룹을 결정적으로(같은 딜러=항상 같은 매니저) 배정합니다.
// 실제 서비스에서는 counsel_application.counsel_manager_id, users.business_type으로 대체됩니다.

export const MOCK_MANAGERS = [
  "강수현",
  "김경선",
  "김미희",
  "박순미",
  "송민선",
  "신영란",
  "이선",
  "이선이",
  "정혜령",
  "진서연",
  "최현정",
];

export const GROUPS = [
  { code: "G1", label: "G1 · 수입차딜러" },
  { code: "G2", label: "G2 · 국산차딜러" },
  { code: "G3", label: "G3 · 중고차딜러" },
  { code: "G4", label: "G4 · 보험설계사" },
  { code: "G5", label: "G5 · 에이전시" },
];

function hashStr(s) {
  let h = 0;
  for (let i = 0; i < s.length; i++) {
    h = (h * 31 + s.charCodeAt(i)) >>> 0;
  }
  return h;
}

export function assignManager(key) {
  return MOCK_MANAGERS[hashStr("m:" + key) % MOCK_MANAGERS.length];
}

export function assignGroup(key) {
  return GROUPS[hashStr("g:" + key) % GROUPS.length];
}
