import { MOCK_MANAGERS } from "../lib/mockAssign";

export default function FilterBar({
  dateFrom,
  dateTo,
  onDateFrom,
  onDateTo,
  manager,
  onManager,
  bounds,
  onReset,
  scopeLabel,
}) {
  return (
    <div className="filter-bar">
      <div className="filter-field">
        <label>기간</label>
        <div className="row">
          <input
            type="date"
            value={dateFrom}
            min={bounds.min}
            max={dateTo}
            onChange={(e) => onDateFrom(e.target.value)}
          />
          <span className="sep">~</span>
          <input
            type="date"
            value={dateTo}
            min={dateFrom}
            max={bounds.max}
            onChange={(e) => onDateTo(e.target.value)}
          />
        </div>
      </div>

      <div className="filter-field">
        <label>매니저</label>
        <select value={manager} onChange={(e) => onManager(e.target.value)}>
          <option value="ALL">전체 (관리자 보기)</option>
          {MOCK_MANAGERS.map((m) => (
            <option key={m} value={m}>
              {m}
            </option>
          ))}
        </select>
      </div>

      <button className="filter-reset" onClick={onReset}>
        필터 초기화
      </button>

      <div className="filter-scope">
        {manager === "ALL" ? (
          <>현재 <b>전체 매니저</b> 기준으로 보고 있습니다</>
        ) : (
          <>현재 <b>{manager}</b> 매니저 본인 기준으로 보고 있습니다</>
        )}
      </div>
    </div>
  );
}
