"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  Cell,
} from "recharts";
import { Section, Reveal, GlassCard } from "@/components/ui/section";

const SAMPLE_EFFECTS = [
  { practice: "Mulching", pct: -67 },
  { practice: "Water harvesting", pct: -52 },
  { practice: "Contour bunds", pct: -41 },
];

const FAMILY_DIST = [
  { name: "Crop", n: 42 },
  { name: "Livestock", n: 18 },
  { name: "Soil fertility", n: 28 },
  { name: "Erosion / water", n: 35 },
  { name: "Agro-forestry", n: 22 },
];

const CHARTS = ["var(--chart-1)", "var(--chart-2)", "var(--chart-3)", "var(--chart-4)", "var(--chart-5)"];

export function HomeDemo() {
  return (
    <Section
      id="demo"
      eyebrow="Illustrative results"
      title="How rankings are communicated"
      subtitle="Sample charts from the soil-loss pathway. Live recommendations use your exact coordinate and selected objective."
    >
      <div className="grid gap-4 lg:grid-cols-2">
        <Reveal>
          <GlassCard className="p-5 sm:p-6">
            <h3 className="font-display text-lg font-semibold tracking-tight text-ink">
              Sample effect on soil loss
            </h3>
            <p className="mt-1 text-sm text-mute">
              Negative % = stronger reduction (favorable for erosion objectives).
            </p>
            <div className="mt-4 h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={SAMPLE_EFFECTS}
                  layout="vertical"
                  margin={{ left: 8, right: 16, top: 8, bottom: 8 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--edge)" horizontal={false} />
                  <XAxis type="number" tick={{ fill: "var(--mute)", fontSize: 11 }} />
                  <YAxis
                    type="category"
                    dataKey="practice"
                    width={110}
                    tick={{ fill: "var(--ink)", fontSize: 12 }}
                  />
                  <Tooltip
                    contentStyle={{
                      borderRadius: 10,
                      border: "1px solid var(--edge)",
                      background: "var(--elevated)",
                      fontSize: 12,
                    }}
                  />
                  <Bar dataKey="pct" name="% change" radius={[0, 6, 6, 0]}>
                    {SAMPLE_EFFECTS.map((_, i) => (
                      <Cell key={i} fill={CHARTS[i]} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </GlassCard>
        </Reveal>

        <Reveal delay={0.06}>
          <GlassCard className="p-5 sm:p-6">
            <h3 className="font-display text-lg font-semibold tracking-tight text-ink">
              Practice-family coverage
            </h3>
            <p className="mt-1 text-sm text-mute">
              Relative evidence density across the five challenge areas.
            </p>
            <div className="mt-4 h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={FAMILY_DIST} margin={{ left: 0, right: 8, top: 8, bottom: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--edge)" vertical={false} />
                  <XAxis dataKey="name" tick={{ fill: "var(--mute)", fontSize: 11 }} />
                  <YAxis tick={{ fill: "var(--mute)", fontSize: 11 }} />
                  <Tooltip
                    contentStyle={{
                      borderRadius: 10,
                      border: "1px solid var(--edge)",
                      background: "var(--elevated)",
                      fontSize: 12,
                    }}
                  />
                  <Bar dataKey="n" name="Relative volume" radius={[6, 6, 0, 0]}>
                    {FAMILY_DIST.map((_, i) => (
                      <Cell key={i} fill={CHARTS[i % CHARTS.length]} fillOpacity={0.92} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </GlassCard>
        </Reveal>

        <Reveal delay={0.1} className="lg:col-span-2">
          <GlassCard className="p-6 sm:p-8">
            <h3 className="font-display text-xl font-semibold tracking-tight text-ink">
              Response ratio, explained
            </h3>
            <p className="mt-3 max-w-3xl text-sm leading-relaxed text-mute sm:text-base">
              The model estimates how a practice shifts an outcome relative to a
              baseline. By default we present a concise effect statement; percentages,
              evidence counts, and confidence are revealed when you ask why. This is a
              ranking instrument over pooled field evidence — not a field guarantee.
            </p>
          </GlassCard>
        </Reveal>
      </div>
    </Section>
  );
}
