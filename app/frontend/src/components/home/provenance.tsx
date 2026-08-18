"use client";

import { Section, Reveal, GlassCard } from "@/components/ui/section";
import { Button } from "@/components/ui/button";
import { ArrowRight, ShieldCheck } from "lucide-react";

const SOURCES = [
  "WorldClim",
  "SoilGrids",
  "Copernicus DEM",
  "ESA WorldCover",
  "AICCRA / ERA evidence",
  "Ethiopian AEZ (Hurni et al.)",
  "Meta-analysis field trials",
  "~250 m geospatial stack",
];

export function HomeProvenance() {
  return (
    <>
      <Section
        id="data"
        eyebrow="Data provenance"
        title="Sources behind every recommendation"
        subtitle="Recommendations combine published field evidence with openly documented geospatial layers."
      >
        <Reveal>
          <div className="flex flex-wrap gap-2">
            {SOURCES.map((s) => (
              <span
                key={s}
                className="rounded-lg border border-edge bg-elevated px-3.5 py-2 text-sm font-medium text-body shadow-sm"
              >
                {s}
              </span>
            ))}
          </div>
        </Reveal>
      </Section>

      <Section
        id="honesty"
        eyebrow="Evidence honesty"
        title="Transparent ranking — not guarantees"
        subtitle="Clean recommendations by default; full justification when requested."
        className="pt-0"
      >
        <Reveal>
          <GlassCard className="flex flex-col gap-5 p-6 sm:flex-row sm:items-start sm:p-8">
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-leaf/10 text-leaf-deep dark:text-leaf-bright">
              <ShieldCheck className="h-6 w-6" />
            </div>
            <div className="flex-1">
              <p className="text-sm leading-relaxed text-mute sm:text-[15px]">
                The model is a pooled ranking tool over field evidence (grouped R²
                is modest by design). Confidence and evidence counts exist to
                justify on request — not to decorate the default answer. When
                evidence is thin, the system says so.
              </p>
            </div>
          </GlassCard>
        </Reveal>
      </Section>

      <section className="pb-20 sm:pb-24">
        <div className="mx-auto max-w-7xl px-4 sm:px-6">
          <Reveal>
            <div className="relative overflow-hidden rounded-[1.5rem] bg-ink px-8 py-12 text-center text-white sm:rounded-[1.75rem] sm:px-14 sm:py-16">
              <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(60%_50%_at_15%_20%,rgba(79,70,229,0.28),transparent_55%),radial-gradient(50%_40%_at_90%_80%,rgba(8,145,178,0.18),transparent_50%)]" />
              <div className="relative">
                <p className="eyebrow mb-4 text-white/50">Next step</p>
                <h2 className="font-display text-3xl font-semibold tracking-tight sm:text-4xl">
                  Ready for location-aware advice?
                </h2>
                <p className="mx-auto mt-3 max-w-xl text-sm text-white/65 sm:text-base">
                  Use the advisor for a guided recommendation, or the analyst view
                  for charts, context, and export.
                </p>
                <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
                  <Button
                    href="/chat"
                    variant="primary"
                    size="lg"
                    className="bg-white text-ink hover:bg-panel"
                  >
                    Open advisor
                    <ArrowRight className="h-4 w-4" />
                  </Button>
                  <Button
                    href="/dashboard"
                    variant="secondary"
                    size="lg"
                    className="border-white/20 bg-white/8 text-white hover:bg-white/14"
                  >
                    Open analyst view
                  </Button>
                </div>
              </div>
            </div>
          </Reveal>
        </div>
      </section>
    </>
  );
}
