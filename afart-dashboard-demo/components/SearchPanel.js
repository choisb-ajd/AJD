import { useEffect, useState } from "react";

export default function SearchPanel() {
  const [rrnPrefix, setRrnPrefix] = useState("");
  const [phone, setPhone] = useState("");
  const [phoneName, setPhoneName] = useState("");
  const [vin, setVin] = useState("");
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const hasQuery = phone.trim() || phoneName.trim() || vin.trim();
    if (!hasQuery) {
      setResults([]);
      return;
    }
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      setLoading(true);
      try {
        const params = new URLSearchParams();
        if (vin.trim()) params.set("vin", vin.trim());
        if (phone.trim()) params.set("phone", phone.trim());
        if (phoneName.trim()) params.set("name", phoneName.trim());
        const res = await fetch(`/api/search?${params.toString()}`, { signal: controller.signal });
        const data = await res.json();
        setResults(data.results || []);
      } catch (e) {
        if (e.name !== "AbortError") setResults([]);
      } finally {
        setLoading(false);
      }
    }, 300);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [phone, phoneName, vin]);

  const hasQuery = phone.trim() || phoneName.trim() || vin.trim();

  return (
    <div className="card">
      <div className="search-grid">
        <div className="field">
          <label>주민번호 앞자리 + 이름</label>
          <input
            type="text"
            placeholder="예: 900101"
            value={rrnPrefix}
            onChange={(e) => setRrnPrefix(e.target.value)}
            disabled
          />
          <span className="hint">이 raw 데이터엔 주민번호가 없어 비활성화 — 실제로는 customer.customer_rrn 필요</span>
        </div>
        <div className="field">
          <label>핸드폰번호 + 이름</label>
          <input type="text" placeholder="010-****-1234" value={phone} onChange={(e) => setPhone(e.target.value)} />
          <input
            type="text"
            placeholder="고객명 (예: 김*수)"
            value={phoneName}
            onChange={(e) => setPhoneName(e.target.value)}
            style={{ marginTop: 4 }}
          />
        </div>
        <div className="field">
          <label>차량번호 / 차대번호</label>
          <input type="text" placeholder="VIN 일부 입력" value={vin} onChange={(e) => setVin(e.target.value)} />
          <span className="hint">이 raw pull은 차량번호·차대번호가 한 컬럼(vin)으로 합쳐져 있음</span>
        </div>
      </div>

      {loading && <p className="section-note">검색 중…</p>}

      {!loading && results.length > 0 && (
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>체결일</th>
                <th>고객명</th>
                <th>연락처</th>
                <th>차량번호/차대번호</th>
                <th>딜러</th>
              </tr>
            </thead>
            <tbody>
              {results.map((r, i) => (
                <tr key={i}>
                  <td>{r.date}</td>
                  <td style={{ textAlign: "left" }}>{r.customerName}</td>
                  <td>{r.phone}</td>
                  <td>{r.vin || "-"}</td>
                  <td>{r.dealerName}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {!loading && hasQuery && results.length === 0 && <p className="section-note">검색 결과가 없습니다.</p>}
    </div>
  );
}
