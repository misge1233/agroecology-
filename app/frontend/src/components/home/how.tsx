"use client";

import { MapPinned, Target, ListOrdered } from "lucide-react";
import { Section, Reveal, GlassCard } from "@/components/ui/section";

const STEPS = [
  {
    icon: MapPinned,
    title: "Set the location",
    body: "Drop a pin on the Ethiopia map or enter coordinates. Soil, climate, terrain, and agro-ecological zone are sampled automatically.",
  },
  {
    icon: Target,
    title: "Define challenge & objective",
    body: "Select a practice family and an outcome — yield, erosion, runoff, soil organic matter, and related indicators.",
  },
  {
    icon: ListOrdered,
    title: "Review ranked practices",
    body: "Practices are ranked by expected effect from pooled field evidence. Confidence and evidence counts are available on request.",
  },
];

export function HomeHow() {
  return (
    <Section
      id="how"
      eyebrow="Method"
      title="Three steps from pin to practice"
      subtitle="No manual climate tables — geospatial context is derived from the coordinate you provide."
    >
      <div className="grid gap-4 md:grid-cols-3">
        {STEPS.map((s, i) => (
          <Reveal key={s.title} delay={i * 0.06}>
            <GlassCard className="h-full p-6 sm:p-7">
              <div className="mb-5 flex items-center justify-between">
                <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-leaf/10 text-leaf-deep dark:text-leaf-bright">
                  <s.icon className="h-5 w-5" />
                </span>
                <span className="font-display text-2xl font-semibold text-ink/12">
                  0{i + 1}
                </span>
              </div>
              <h3 className="font-display text-xl font-semibold tracking-tight text-ink">
                {s.title}
              </h3>
              <p className="mt-2 text-sm leading-relaxed text-mute">{s.body}</p>
            </GlassCard>
          </Reveal>
        ))}
      </div>
    </Section>
  );
}
