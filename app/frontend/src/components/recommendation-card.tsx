"use client";

import { useState } from "react";
import { ChevronDown, Sparkles, Sprout } from "lucide-react";
import { cn } from "@/lib/utils";
import type {
  Confidence,
  RecommendResponse,
  RecommendationItem,
} from "@/lib/types";
import { PctChangeChart } from "./pct-chart";
import { PracticeImage } from "./practice-image";

const CONF_COPY: Record<Confidence, string> = {
  high: "High confidence — well supported by field evidence here.",
  medium: "Medium confidence — reasonable evidence for this objective.",
  low: "Limited evidence for this objective, so treat the ranking as directional, not exact.",
};

const CONTEXT_FIELDS: { key: string; label: string; unit?: string; digits?: number }[] = [
  { key: "Rainfall", label: "Rainfall", unit: "mm", digits: 0 },
  { key: "temp_mean_annual", label: "Mean temp", unit: "°C", digits: 1 },
  { key: "Altitude_r", label: "Altitude", unit: "m", digits: 0 },
  { key: "slope", label: "Slope", unit: "%", digits: 1 },
  { key: "soil_clay", label: "Clay", unit: "%", digits: 0 },
  { key: "soil_ph", label: "Soil pH", digits: 1 },
  { key: "soil_soc", label: "Soil organic C", digits: 1 },
  { key: "lgp_days", label: "Growing period", unit: "days", digits: 0 },
];

function fmt(v: number | string | null | undefined, digits = 1): string {
  if (v == null) return "—";
  const n = typeof v === "number" ? v : Number(v);
  if (Number.isNaN(n)) return String(v);
  return n.toFixed(digits);
}

function PracticeHeroCard({
  item,
  zone,
  rank,
  featured,
}: {
  item: RecommendationItem;
  zone?: string;
  rank: number;
  featured?: boolean;
}) {
  return (
    <article
      className={cn(
        "overflow-hidden rounded-2xl border border-edge bg-elevated shadow-soft",
        featured && "ring-1 ring-leaf/15"
      )}
    >
      <div className="relative">
        <PracticeImage practice={item.practice} priority={featured} />
        <div className="absolute bottom-0 left-0 right-0 p-4 sm:p-5">
          <div className="flex items-end justify-between gap-3">
            <div className="min-w-0">
              {rank === 1 ? (
                <p className="mb-1 inline-flex items-center gap-1.5 rounded-full bg-white/90 px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-wider text-leaf-deep backdrop-blur">
                  <Sparkles className="h-3 w-3" />
                  Top match
                </p>
              ) : (
                <p className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-white/80">
                  #{rank} option
                </p>
              )}
              <h3 className="font-display text-2xl leading-tight tracking-tight text-white drop-shadow-sm sm:text-[1.65rem]">
                {item.practice}
              </h3>
            </div>
          </div>
        </div>
      </div>
      <div className="space-y-2 border-t border-edge/80 px-4 py-4 sm:px-5">
        <p className="flex items-start gap-2 text-[15px] leading-relaxed text-ink">
          <Sprout className="mt-0.5 h-4 w-4 shrink-0 text-leaf" aria-hidden />
          {item.effect}
        </p>
        {zone && rank === 1 && (
          <p className="text-xs text-mute">
            Context: <span className="font-medium text-ink">{zone}</span>
          </p>
        )}
      </div>
    </article>
  );
}

function CompactCard({ item, rank }: { item: RecommendationItem; rank: number }) {
  return (
    <article className="flex items-start gap-3 rounded-2xl border border-edge bg-elevated/80 p-3.5 shadow-sm">
      <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-leaf/12 text-[13px] font-semibold text-leaf-deep dark:text-leaf-bright">
        {rank}
      </span>
      <div className="min-w-0 flex-1">
        <h3 className="font-display text-lg leading-snug tracking-tight text-ink">
          {item.practice}
        </h3>
        <p className="mt-0.5 text-sm text-mute">{item.effect}</p>
      </div>
    </article>
  );
}

export function RecommendationPanel({
  data,
  lead,
  variant = "default",
}: {
  data: RecommendResponse;
  lead?: string;
  /** hero: large image card for #1; stack compact cards for rest */
  variant?: "default" | "hero";
}) {
  const [showWhy, setShowWhy] = useState(false);
  const { query, recommendations, details } = data;
  const zone = details.context?.aez_belt as string | undefined;
  const [primary, ...rest] = recommendations;
  const challengeLabel = query.practice_family.replace(/ and management$/i, "");

  return (
    <div className={cn("space-y-3", variant === "hero" && "px-4 pb-4 sm:px-5 sm:pb-5")}>
      <p className="text-[12px] font-medium text-mute">
        Ranked within challenge:{" "}
        <span className="text-ink">{challengeLabel}</span>
        {details.n_grounded != null && details.n_candidates != null ? (
          <span className="font-normal">
            {" "}
            · {details.n_grounded} of {details.n_candidates} practices with evidence for
            your objective
          </span>
        ) : null}
      </p>
      {lead && (
        <p className="text-[15px] leading-relaxed text-ink">{lead}</p>
      )}

      <div className="space-y-3">
        {variant === "hero" && primary ? (
          <>
            <PracticeHeroCard
              item={primary}
              zone={zone}
              rank={1}
              featured
            />
            {rest.map((r, i) => (
              <CompactCard key={r.practice} item={r} rank={i + 2} />
            ))}
          </>
        ) : (
          recommendations.map((r, i) => (
            <CompactCard key={r.practice} item={r} rank={i + 1} />
          ))
        )}
      </div>

      <button
        type="button"
        onClick={() => setShowWhy((v) => !v)}
        aria-expanded={showWhy}
        className="inline-flex items-center gap-1 text-[13px] font-medium text-leaf-deep transition hover:opacity-80 dark:text-leaf-bright"
      >
        {showWhy ? "Hide details" : "Why this?"}
        <ChevronDown
          className={cn("h-4 w-4 transition-transform", showWhy && "rotate-180")}
        />
      </button>

      {showWhy && (
        <div className="space-y-4 rounded-2xl border border-edge bg-canvas/50 p-4">
          <div>
            <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-mute">
              Confidence
            </p>
            <p
              className={cn(
                "mt-1 text-sm",
                details.confidence === "low" ? "text-soil" : "text-ink"
              )}
            >
              <span className="font-semibold capitalize">{details.confidence}</span>
              {" — "}
              {CONF_COPY[details.confidence]}
            </p>
          </div>

          {zone && (
            <div>
              <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-mute">
                Local context ({zone})
              </p>
              <div className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1.5 sm:grid-cols-4">
                {CONTEXT_FIELDS.filter(
                  (f) => details.context?.[f.key] != null
                ).map((f) => (
                  <div key={f.key} className="text-sm">
                    <span className="block text-[11px] text-mute">{f.label}</span>
                    <span className="font-medium text-ink">
                      {fmt(details.context[f.key], f.digits)}
                      {f.unit ? ` ${f.unit}` : ""}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div>
            <p className="mb-2 text-[11px] font-medium uppercase tracking-[0.14em] text-mute">
              Estimated effect &amp; evidence
            </p>
            <PctChangeChart ranked={details.ranked} direction={query.goal_direction} />
            <ul className="mt-2 space-y-1">
              {details.ranked.map((r) => (
                <li key={r.practice} className="flex justify-between gap-3 text-[12px]">
                  <span className="truncate text-ink">{r.practice}</span>
                  <span className="shrink-0 text-mute">
                    {r.pct_change > 0 ? "+" : ""}
                    {r.pct_change.toFixed(1)}% · {r.n_evidence} field obs.
                  </span>
                </li>
              ))}
            </ul>
          </div>

          {details.ranking_scope ? (
            <p className="text-[11px] leading-relaxed text-mute">{details.ranking_scope}</p>
          ) : null}
          <p className="text-[11px] leading-relaxed text-mute">{details.note}</p>
        </div>
      )}

      <p className="text-[11px] italic text-mute">
        Estimates from limited field evidence — not guarantees.
      </p>
    </div>
  );
}
