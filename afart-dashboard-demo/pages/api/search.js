import { loadRawRows } from "../../lib/data";

// 상세검색 데모용 서버 라우트.
// 이 raw pull엔 주민번호가 없어 rrn 파라미터는 항상 빈 결과를 돌려준다 — 프론트에서도 입력을 막아뒀다.
let cachedRows = null;
function getRows() {
  if (!cachedRows) cachedRows = loadRawRows();
  return cachedRows;
}

export default function handler(req, res) {
  const { phone = "", name = "", vin = "" } = req.query;
  const phoneQ = String(phone).trim();
  const nameQ = String(name).trim();
  const vinQ = String(vin).trim();

  if (!phoneQ && !nameQ && !vinQ) {
    return res.status(200).json({ results: [] });
  }

  const rows = getRows();
  const results = [];
  for (const r of rows) {
    if (!r.contractDate) continue;
    let match;
    if (vinQ) {
      match = r.vin && r.vin.includes(vinQ);
    } else {
      const phoneOk = !phoneQ || (r.phone || "").includes(phoneQ);
      const nameOk = !nameQ || (r.customerName || "").includes(nameQ);
      match = phoneOk && nameOk;
    }
    if (match) {
      results.push({
        date: r.contractDate,
        customerName: r.customerName,
        phone: r.phone,
        vin: r.vin,
        dealerName: r.dealerName,
      });
      if (results.length >= 20) break;
    }
  }

  res.status(200).json({ results });
}
