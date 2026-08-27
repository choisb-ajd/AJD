import { useEffect, useState } from "react";
import { formatWon, formatCount } from "../lib/format";

export default function SalesRawList({ initialFrom, initialTo, bounds }) {
  const [from, setFrom] = useState(initialFrom);
  const [to, setTo] = useState(initialTo);
  const [rows, setRows] = useState([]);
  const [meta, setMeta] = useState({ total: 0, truncated: false });
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!from || !to || from > to) return;
    let cancelled = false;
    setLoading(true);
    fetch(`/api/sales?from=${from}&to=${to}`)
      .then((res) => res.json())
      .then((data) => {
        if (cancelled) return;
        setRows(data.results || []);
        setMeta({ total: data.total || 0, truncated: !!data.truncated });
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [from, to]);

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 14 }}>
        <input
          type="date"
          className="date-input"
          value={from}
          min={bounds.min}
          max={to}
          onChange={(e) => setFrom(e.target.value)}
        />
        <span style={{ color: "var(--ink-faint)", fontSize: 12 }}>~</span>
        <input
          type="date"
          className="date-input"
          value={to}
          min={from}
          max={bounds.max}
          onChange={(e) => setTo(e.target.value)}
        />
        <span style={{ fontSize: 12.5, color: "var(--ink-muted)" }}>
          {loading
            ? "조회 중…"
            : `${formatCount(meta.total)}${meta.truncated ? ` 중 최근 1,000건만 표시` : ""}`}
        </span>
      </div>

      <div className="table-wrap table-scroll-sm">
        <table className="data">
          <thead>
            <tr>
              <th>유입채널</th>
              <th>고객명</th>
              <th>차량(차대)번호</th>
              <th>만기일자</th>
              <th>보험료</th>
              <th>체결일</th>
              <th>상담(체결)매니저</th>
              <th>딜러이름</th>
              <th>딜러 전담 매니저</th>
            </tr>
          </thead>
          <tbody>
            {!loading && rows.length === 0 && (
              <tr>
                <td colSpan={9} style={{ textAlign: "center", color: "var(--ink-faint)" }}>
                  해당 기간에 데이터가 없습니다.
                </td>
              </tr>
            )}
            {rows.map((r, i) => {
              const mismatch = r.counselManagerName !== r.dealerManagerName;
              return (
                <tr key={i}>
                  <td>{r.channel}</td>
                  <td style={{ textAlign: "left" }}>{r.customerName}</td>
                  <td>{r.vin || "-"}</td>
                  <td>{r.expiryDate || "-"}</td>
                  <td>{formatWon(r.premium)}</td>
                  <td>{r.contractDate}</td>
                  <td className={mismatch ? "manager-mismatch" : ""}>{r.counselManagerName}</td>
                  <td>{r.dealerName}</td>
                  <td className={mismatch ? "manager-mismatch" : ""}>{r.dealerManagerName}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
