"use client";

import {
  Layers,
  BookOpenCheck,
  BrainCircuit,
  MessagesSquare,
} from "lucide-react";
import { Section, Reveal, GlassCard } from "@/components/ui/section";

const TILES = [
  {
    icon: Layers,
    title: "Geospatial feature stack",
    body: "Eleven layers sampled at your pin — rainfall, temperature, seasonality, elevation, slope, soil clay/pH/SOC, land cover, LGP, and AEZ belt.",
    span: "md:col-span-2",
  },
  {
    icon: BookOpenCheck,
    title: "Evidence base",
    body: "Meta-analysis of agroecological field trials across Ethiopia — thousands of paired observations across hundreds of studies.",
    span: "",
  },
  {
    icon: BrainCircuit,
    title: "Ranking model",
    body: "A pooled RandomForest ranks practices by expected effect for your context. Confidence and evidence counts are disclosed on request.",
    span: "",
  },
  {
    icon: MessagesSquare,
    title: "Advisor interface",
    body: "Plain-language recommendations with optional explanation. The assistant does not invent statistics outside the model outputs.",
    span: "md:col-span-2",
  },
];

export function HomePowers() {
  return (
    <Section
      id="powers"
      eyebrow="System architecture"
      title="Science under the hood, clarity on the surface"
      subtitle="Four components work together so recommendations fit the land under a given coordinate — not a generic national average."
      className="bg-panel/40"
    >
      <div className="grid gap-4 md:grid-cols-3">
        {TILES.map((t, i) => (
          <Reveal key={t.title} delay={i * 0.05} className={t.span}>
            <GlassCard className="h-full p-6 sm:p-7">
              <t.icon className="mb-4 h-5 w-5 text-leaf" />
              <h3 className="font-display text-xl font-semibold tracking-tight text-ink">
                {t.title}
              </h3>
              <p className="mt-2 text-sm leading-relaxed text-mute">{t.body}</p>
            </GlassCard>
          </Reveal>
        ))}
      </div>
    </Section>
  );
}
