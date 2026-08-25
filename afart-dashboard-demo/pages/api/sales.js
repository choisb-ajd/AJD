import { loadRawRows, toSalesRows } from "../../lib/data";

// 매출 로우 데이터 리스트 데모용 서버 라우트. 기간 파라미터로 걸러서 필요한 컬럼만 내려준다.
let cachedRows = null;
function getRows() {
  if (!cachedRows) cachedRows = loadRawRows();
  return cachedRows;
}

const MAX_RESULTS = 1000;

export default function handler(req, res) {
  const { from = "", to = "" } = req.query;
  if (!from || !to) {
    return res.status(400).json({ error: "from, to 파라미터가 필요합니다." });
  }

  const rows = toSalesRows(getRows(), { dateFrom: from, dateTo: to });
  const truncated = rows.length > MAX_RESULTS;
  res.status(200).json({
    results: truncated ? rows.slice(0, MAX_RESULTS) : rows,
    total: rows.length,
    truncated,
  });
}
