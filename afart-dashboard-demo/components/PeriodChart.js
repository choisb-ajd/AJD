import {
  ResponsiveContainer,
  ComposedChart,
  Bar,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from "recharts";
import { formatCompactWon, formatCount } from "../lib/format";

function ChartTooltip({ active, payload, label, single, valueLabel, valueFormatter }) {
  if (!active || !payload || !payload.length) return null;
  const p = payload[0]?.payload;
  return (
    <div
      style={{
        background: "var(--surface)",
        border: "1px solid var(--border)",
        borderRadius: 8,
        padding: "8px 12px",
        fontSize: 12,
        boxShadow: "var(--shadow)",
      }}
    >
      <div style={{ fontWeight: 600, marginBottom: 4 }}>{label}</div>
      {single ? (
        <div>
          {valueLabel} · {valueFormatter(p.premiumSum)}
        </div>
      ) : (
        <>
          <div>원수보험료 · {formatCompactWon(p.premiumSum)}</div>
          <div style={{ color: "var(--ink-muted)" }}>체결건수 · {formatCount(p.count)}</div>
        </>
      )}
    </div>
  );
}

// mode="premium"(기본) — 막대(원수보험료)+선(체결건수), 툴팁에 둘 다 표시.
// mode="count" — 막대 하나만, 툴팁에도 valueLabel 한 줄만 표시 (예: 앱 가입현황).
export default function PeriodChart({ data, mode = "premium", valueLabel = "건수", valueFormatter = formatCount }) {
  const single = mode === "count";
  return (
    <div style={{ width: "100%", height: 220 }}>
      <ResponsiveContainer>
        <ComposedChart data={data} margin={{ top: 8, right: 8, left: 8, bottom: 0 }}>
          <CartesianGrid stroke="var(--border)" vertical={false} />
          <XAxis
            dataKey="label"
            tick={{ fontSize: 11, fill: "var(--ink-muted)" }}
            axisLine={{ stroke: "var(--border)" }}
            tickLine={false}
          />
          <YAxis
            yAxisId="premium"
            tickFormatter={single ? (v) => formatCount(v) : (v) => formatCompactWon(v)}
            tick={{ fontSize: 10, fill: "var(--ink-faint)" }}
            axisLine={false}
            tickLine={false}
            width={64}
          />
          {!single && <YAxis yAxisId="count" orientation="right" hide />}
          <Tooltip
            content={<ChartTooltip single={single} valueLabel={valueLabel} valueFormatter={valueFormatter} />}
            cursor={{ fill: "rgba(36,82,217,0.06)" }}
          />
          <Bar yAxisId="premium" dataKey="premiumSum" fill="var(--accent)" radius={[3, 3, 0, 0]} maxBarSize={28} />
          {!single && (
            <Line yAxisId="count" type="monotone" dataKey="count" stroke="var(--warn)" strokeWidth={2} dot={false} />
          )}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
