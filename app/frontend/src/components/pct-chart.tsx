"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { isBeneficial } from "@/lib/utils";
import type { RankedItem } from "@/lib/types";

/** Visualises the ranked pct_change — shown ONLY inside the explanation view. */
export function PctChangeChart({
  ranked,
  direction,
}: {
  ranked: RankedItem[];
  direction: string;
}) {
  const data = ranked.map((r) => ({
    name: r.practice.length > 22 ? r.practice.slice(0, 20) + "…" : r.practice,
    full: r.practice,
    pct: r.pct_change,
    n: r.n_evidence,
    good: isBeneficial(r.pct_change, direction),
  }));

  return (
    <div className="h-56 w-full rounded-2xl border border-edge bg-elevated/90 p-4 shadow-soft">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          data={data}
          layout="vertical"
          margin={{ top: 4, right: 16, left: 8, bottom: 4 }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke="var(--edge)" horizontal={false} />
          <XAxis type="number" tick={{ fill: "var(--mute)", fontSize: 11 }} unit="%" />
          <YAxis
            type="category"
            dataKey="name"
            width={120}
            tick={{ fill: "var(--ink)", fontSize: 11 }}
          />
          <Tooltip
            contentStyle={{
              background: "var(--canvas)",
              border: "1px solid var(--edge)",
              borderRadius: 12,
              fontSize: 12,
            }}
            formatter={(value, _n, item) => {
              const v = typeof value === "number" ? value : Number(value);
              const n = (item?.payload as { n?: number })?.n ?? 0;
              return [`${v.toFixed(1)}% · ${n} obs.`, "Estimated change"];
            }}
            labelFormatter={(_, payload) => {
              const p = payload?.[0]?.payload as { full?: string } | undefined;
              return p?.full || "";
            }}
          />
          <Bar dataKey="pct" radius={[0, 6, 6, 0]} maxBarSize={22}>
            {data.map((d) => (
              <Cell
                key={d.full}
                fill={d.good ? "var(--chart-1)" : "var(--chart-6)"}
                fillOpacity={d.n >= 5 ? 1 : d.n >= 1 ? 0.72 : 0.48}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
