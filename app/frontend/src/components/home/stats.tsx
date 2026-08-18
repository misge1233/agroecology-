"use client";

import { useMetadata } from "@/components/metadata-provider";
import { Reveal } from "@/components/ui/section";
import { StatCounter } from "@/components/ui/motion";

const FALLBACK = [
  { value: 8664, label: "Field observations", suffix: "" },
  { value: 337, label: "Studies in the evidence base", suffix: "" },
  { value: 15, label: "Agro-ecological belts", suffix: "" },
  { value: 11, label: "Geospatial layers", suffix: "" },
  { value: 5, label: "Practice families", suffix: "" },
  { value: 7, label: "Objectives", suffix: "" },
];

export function HomeStats() {
  const { meta } = useMetadata();
  const stats = [
    FALLBACK[0],
    FALLBACK[1],
    FALLBACK[2],
    FALLBACK[3],
    {
      value: meta?.practice_families?.length ?? 5,
      label: "Practice families",
      suffix: "",
    },
    {
      value: meta?.indicators?.length ?? 7,
      label: "Objectives",
      suffix: "",
    },
  ];

  return (
    <section className="border-y border-edge bg-elevated">
      <div className="mx-auto max-w-7xl px-4 py-10 sm:px-6 sm:py-12">
        <Reveal>
          <p className="eyebrow mb-8 text-center">
            Nationwide coverage · ~250&nbsp;m resolution
          </p>
        </Reveal>
        <div className="grid grid-cols-2 gap-x-6 gap-y-8 md:grid-cols-3 lg:grid-cols-6 lg:divide-x lg:divide-edge/80">
          {stats.map((s, i) => (
            <Reveal key={s.label} delay={i * 0.04}>
              <StatCounter
                value={s.value}
                label={s.label}
                suffix={s.suffix}
                className="text-center lg:px-3"
              />
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}
