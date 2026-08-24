// 딜러유형(business_type) 기준 실제 그룹 배정.
// 배치도 문서의 G1~G5는 신차딜러를 수입/국산(business_sub_type)으로 더 나누지만,
// 이 raw pull엔 sub_type이 없어 신차딜러는 하나로 묶는다.
export const GROUPS = [
  { code: "NEW", label: "신차딜러 (수입/국산 미구분)" },
  { code: "USED", label: "중고차딜러" },
  { code: "AGENT", label: "보험설계사" },
  { code: "AGENCY", label: "에이전시" },
  { code: "ETC", label: "미분류" },
];

const MAP = {
  NEW_CAR_DEALER: "NEW",
  USED_CAR_DEALER: "USED",
  INSURANCE_AGENT: "AGENT",
  AGENCY: "AGENCY",
};

export function groupOf(dealerType) {
  const code = MAP[dealerType] || "ETC";
  return GROUPS.find((g) => g.code === code);
}
