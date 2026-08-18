"use client";

import {
  Wheat,
  Beef,
  Sprout,
  Waves,
  Trees,
  TrendingUp,
  Leaf,
  Droplets,
  Mountain,
  CircleDollarSign,
  Gauge,
} from "lucide-react";
import { useMetadata } from "@/components/metadata-provider";
import { Section, Reveal, GlassCard } from "@/components/ui/section";
import { Chip } from "@/components/ui/motion";

const FAMILY_META: Record<
  string,
  { icon: typeof Wheat; blurb: string }
> = {
  "Crop production and management": {
    icon: Wheat,
    blurb: "Varieties, planting, residue, and in-field crop management.",
  },
  "Livestock production and management": {
    icon: Beef,
    blurb: "Feed, fodder, and herd practices that fit local systems.",
  },
  "Integrated soil fertility management": {
    icon: Sprout,
    blurb: "Organic and mineral fertility for lasting soil health.",
  },
  "Erosion control and water management": {
    icon: Waves,
    blurb: "Bunds, mulch, harvesting — hold soil and water on-farm.",
  },
  "Agro-forestry and forest management": {
    icon: Trees,
    blurb: "Trees with crops and landscapes that buffer climate risk.",
  },
};

const OBJ_ICONS: Record<string, typeof TrendingUp> = {
  yield: TrendingUp,
  "biomass yield": Leaf,
  income: CircleDollarSign,
  "water use efficiency": Droplets,
  "SOM content": Sprout,
  "soil loss": Mountain,
  runoff: Gauge,
};

const DEFAULT_FAMILIES = Object.keys(FAMILY_META);

export function HomeFamilies() {
  const { meta } = useMetadata();
  const families = meta?.practice_families?.length
    ? meta.practice_families
    : DEFAULT_FAMILIES;
  const indicators = meta?.indicators ?? [];

  return (
    <>
      <Section
        id="families"
        eyebrow="Practice families"
        title="Five challenge areas"
        subtitle="Select the challenge domain — ranking is performed within that family for the sampled location."
      >
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {families.map((f, i) => {
            const m = FAMILY_META[f] ?? {
              icon: Sprout,
              blurb: "Evidence-backed practices for this challenge.",
            };
            const Icon = m.icon;
            return (
              <Reveal key={f} delay={i * 0.04}>
                <GlassCard className="h-full p-5 sm:p-6">
                  <Icon className="mb-3 h-5 w-5 text-leaf" />
                  <h3 className="font-display text-lg font-semibold leading-snug tracking-tight text-ink">
                    {f}
                  </h3>
                  <p className="mt-2 text-sm text-mute">{m.blurb}</p>
                </GlassCard>
              </Reveal>
            );
          })}
        </div>
      </Section>

      <Section
        id="objectives"
        eyebrow="Objectives"
        title="Seven outcomes you can optimize"
        subtitle="Interface labels are human-readable; the model receives the precise indicator keys."
        className="pt-0"
      >
        <Reveal>
          <div className="flex flex-wrap gap-2.5">
            {(indicators.length
              ? indicators
              : [
                  { key: "yield", label: "Increase crop yield", direction: "increase" as const },
                  { key: "biomass yield", label: "Increase biomass / fodder", direction: "increase" as const },
                  { key: "income", label: "Increase income", direction: "increase" as const },
                  { key: "water use efficiency", label: "Improve water-use efficiency", direction: "increase" as const },
                  { key: "SOM content", label: "Improve soil organic matter", direction: "increase" as const },
                  { key: "soil loss", label: "Reduce soil loss / erosion", direction: "reduce" as const },
                  { key: "runoff", label: "Reduce runoff", direction: "reduce" as const },
                ]
            ).map((ind) => {
              const Icon = OBJ_ICONS[ind.key] ?? TargetFallback;
              return (
                <Chip key={ind.key} className="gap-2 px-4 py-2.5 text-sm text-ink">
                  <Icon className="h-3.5 w-3.5 text-leaf" />
                  {ind.label}
                </Chip>
              );
            })}
          </div>
        </Reveal>
      </Section>
    </>
  );
}

function TargetFallback(props: React.ComponentProps<typeof TrendingUp>) {
  return <TrendingUp {...props} />;
}
