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

/**
 * Visualises the ranked pct_change — shown ONLY inside the "Why this?" view.
 * Colours come from the CVD-checked chart tokens; the highlighted practice
 * takes the primary token. Bars fade with thin evidence (n_evidence).
 */
export function PctChangeChart({
  ranked,
  direction,
  nameOf,
  highlight,
  changeLabel,
  obsOf,
}: {
  ranked: RankedItem[];
  direction: string;
  /** Localised display name for a practice. */
  nameOf: (practice: string) => string;
  /** Practice to emphasise (the card's own). */
  highlight?: string;
  /** Tooltip series label, e.g. "change". */
  changeLabel: string;
  /** Tooltip observations label, e.g. (17) → "17 field observations". */
  obsOf: (n: number) => string;
}) {
  const data = ranked.map((r) => {
    const name = nameOf(r.practice);
    return {
      name: name.length > 24 ? name.slice(0, 22) + "…" : name,
      full: name,
      practice: r.practice,
      pct: r.pct_change,
      n: r.n_evidence,
      good: isBeneficial(r.pct_change, direction),
    };
  });

  return (
    <div className="h-56 w-full rounded-card border border-border bg-surface p-3" aria-hidden>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} layout="vertical" margin={{ top: 4, right: 16, left: 8, bottom: 4 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" horizontal={false} />
          <XAxis type="number" tick={{ fill: "var(--muted)", fontSize: 11 }} unit="%" />
          <YAxis type="category" dataKey="name" width={130} tick={{ fill: "var(--text)", fontSize: 11 }} />
          <Tooltip
            cursor={{ fill: "var(--surface-2)" }}
            contentStyle={{
              background: "var(--surface)",
              border: "1px solid var(--border)",
              borderRadius: 8,
              fontSize: 12,
              color: "var(--text)",
            }}
            formatter={(value, _n, item) => {
              const v = typeof value === "number" ? value : Number(value);
              const n = (item?.payload as { n?: number })?.n ?? 0;
              return [`${v.toFixed(1)}% · ${obsOf(n)}`, changeLabel];
            }}
            labelFormatter={(_, payload) => {
              const p = payload?.[0]?.payload as { full?: string } | undefined;
              return p?.full || "";
            }}
          />
          <Bar dataKey="pct" radius={[0, 6, 6, 0]} maxBarSize={22}>
            {data.map((d) => (
              <Cell
                key={d.practice}
                fill={
                  d.practice === highlight
                    ? "var(--primary)"
                    : d.good
                      ? "var(--chart-3)"
                      : "var(--chart-5)"
                }
                fillOpacity={d.n >= 5 ? 1 : d.n >= 1 ? 0.72 : 0.48}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
