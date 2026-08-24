// fs를 쓰지 않는 순수 유틸이라 클라이언트 번들에도 안전하게 포함된다.
// lib/data.js가 만드는 [date, premium, insurer, joinType, channel, dealerKey, dealerName, managerName, group] 배열을
// 다시 객체 배열로 복원한다.
export function unpackRows(packed) {
  return packed.map(
    ([date, premium, insurer, joinType, channel, dealerKey, dealerName, managerName, group]) => ({
      date,
      premium,
      insurer,
      joinType,
      channel,
      dealerKey,
      dealerName,
      managerName,
      group,
    })
  );
}
