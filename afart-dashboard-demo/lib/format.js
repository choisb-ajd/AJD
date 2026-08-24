export function formatWon(n) {
  if (n == null || Number.isNaN(n)) return "-";
  return Math.round(n).toLocaleString("ko-KR") + "원";
}

export function formatCompactWon(n) {
  if (n == null || Number.isNaN(n)) return "-";
  const eok = 100000000;
  const man = 10000;
  if (Math.abs(n) >= eok) {
    return (n / eok).toFixed(1).replace(/\.0$/, "") + "억원";
  }
  if (Math.abs(n) >= man) {
    return Math.round(n / man).toLocaleString("ko-KR") + "만원";
  }
  return formatWon(n);
}

export function formatCount(n) {
  if (n == null || Number.isNaN(n)) return "-";
  return n.toLocaleString("ko-KR") + "건";
}

export function formatPercent(n, digits = 1) {
  if (n == null || Number.isNaN(n)) return "-";
  return n.toFixed(digits) + "%";
}

export function formatDateLabel(key) {
  // YYYY-MM-DD -> MM/DD
  if (/^\d{4}-\d{2}-\d{2}$/.test(key)) {
    const [, m, d] = key.split("-");
    return `${m}/${d}`;
  }
  // YYYY-MM -> YYYY년 MM월
  if (/^\d{4}-\d{2}$/.test(key)) {
    const [y, m] = key.split("-");
    return `${y}년 ${Number(m)}월`;
  }
  return key;
}
