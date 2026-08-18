"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Copy,
  Download,
  Loader2,
  MapPinned,
  MessageSquare,
  Sparkles,
} from "lucide-react";
import { postRecommend } from "@/lib/api";
import type { RecommendResponse } from "@/lib/types";
import {
  indicatorLabelForFamily,
  indicatorsForFamily,
  sanitizeIndicatorForFamily,
} from "@/lib/chat-flow";
import { useMetadata } from "./metadata-provider";
import { LocationPicker } from "./location-picker";
import { RecommendationPanel } from "./recommendation-card";
import { PctChangeChart } from "./pct-chart";
import { Button } from "./ui/button";
import { GlassCard } from "./ui/section";

export function DashboardPanel() {
  const { meta, loading: metaLoading, error: metaError } = useMetadata();
  const router = useRouter();

  const [lat, setLat] = useState<number | null>(null);
  const [lon, setLon] = useState<number | null>(null);
  const [family, setFamily] = useState("");
  const [indicator, setIndicator] = useState("");
  const [crop, setCrop] = useState("");
  const [topN, setTopN] = useState(1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<RecommendResponse | null>(null);
  const [copied, setCopied] = useState(false);

  const objectiveOptions = useMemo(() => {
    if (!meta || !family) return [];
    return indicatorsForFamily(meta, family);
  }, [meta, family]);

  const ready =
    lat != null && lon != null && !!family && !!indicator;

  const lead = useMemo(() => {
    if (!result) return "";
    const zone = result.details.context?.aez_belt as string | undefined;
    const cropBit = result.query.crop_type
      ? ` growing ${result.query.crop_type}`
      : "";
    const where = zone ? `your ${zone} area` : "your location";
    return `For ${where}${cropBit}, here are the top practices within ${result.query.practice_family.replace(/ and management$/i, "")} to ${result.query.goal_direction} ${result.query.indicator}, ranked by field evidence for your location.`;
  }, [result]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!ready) {
      setError("Set a location on the map and choose a challenge and objective.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const res = await postRecommend({
        lat: lat as number,
        lon: lon as number,
        practice_family: family,
        indicator,
        crop_type: crop.trim() || null,
        top_n: topN,
      });
      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed");
    } finally {
      setBusy(false);
    }
  }

  function explainInChat() {
    if (!result) return;
    const q = result.query;
    const cropBit = q.crop_type ? ` growing ${q.crop_type}` : "";
    const msg = `I'm at ${q.lat}, ${q.lon}${cropBit}. For "${q.practice_family}" with the goal to ${q.goal_direction} ${q.indicator}, you recommended ${result.recommendations
      .map((r) => r.practice)
      .join(", ")}. Why these, and how sure are you?`;
    sessionStorage.setItem("agro-seed-message", msg);
    router.push("/chat");
  }

  function exportCsv() {
    if (!result) return;
    const rows = [
      ["rank", "practice", "effect", "pct_change", "n_evidence", "confidence"],
      ...result.details.ranked.map((r, i) => [
        String(i + 1),
        r.practice,
        result.recommendations[i]?.effect ?? "",
        String(r.pct_change),
        String(r.n_evidence),
        result.details.confidence,
      ]),
    ];
    const csv = rows
      .map((row) =>
        row.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(",")
      )
      .join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `agroecology-ai-${result.query.lat}-${result.query.lon}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  async function copyResults() {
    if (!result) return;
    const lines = [
      lead,
      "",
      ...result.recommendations.map(
        (r, i) => `${i + 1}. ${r.practice} — ${r.effect}`
      ),
      "",
      `Confidence: ${result.details.confidence}`,
      `Zone: ${result.details.context?.aez_belt ?? "—"}`,
    ];
    await navigator.clipboard.writeText(lines.join("\n"));
    setCopied(true);
    setTimeout(() => setCopied(false), 1600);
  }

  if (metaLoading) {
    return (
      <div className="flex h-64 items-center justify-center text-mute">
        <Loader2 className="mr-2 h-5 w-5 animate-spin" /> Loading…
      </div>
    );
  }

  if (metaError || !meta) {
    return (
      <div className="mx-auto max-w-lg px-4 py-16 text-center">
        <p className="text-sm text-soil">
          Cannot reach the API: {metaError || "unknown error"}
        </p>
        <p className="mt-2 text-xs text-mute">
          Start the backend on port 8000, then refresh.
        </p>
      </div>
    );
  }

  const zone = result?.details.context?.aez_belt as string | undefined;

  const fieldClass =
    "w-full rounded-2xl border border-edge bg-canvas/60 px-3.5 py-2.5 text-sm outline-none transition focus-ring";

  return (
    <div className="mx-auto max-w-5xl px-4 py-8 sm:px-6 sm:py-10 lg:max-w-6xl">
      <div className="mb-8 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div className="max-w-2xl">
          <p className="eyebrow mb-2">Analyst view</p>
          <h1 className="font-display text-4xl font-semibold tracking-tight text-ink sm:text-[2.75rem]">
            Practice Recommender
          </h1>
          <p className="mt-2 text-[15px] leading-relaxed text-mute">
            Set a coordinate, select challenge and objective, then review ranked
            practices with local context, confidence, and export.
          </p>
        </div>
        <Button href="/chat" variant="secondary" size="sm">
          <Sparkles className="h-3.5 w-3.5" /> Ask advisor
        </Button>
      </div>

      <div className="space-y-8">
        <form
          onSubmit={onSubmit}
          className="overflow-hidden rounded-2xl border border-edge bg-elevated shadow-soft"
        >
          <div className="relative border-b border-edge bg-panel/45 px-5 py-4 sm:px-6">
            <span className="absolute inset-y-3 left-0 w-1 rounded-r-full bg-leaf" aria-hidden />
            <p className="eyebrow">Step 1 · Location</p>
            <h2 className="mt-1 font-display text-xl font-semibold tracking-tight text-ink">
              Where is the farm?
            </h2>
          </div>

          <div className="p-5 sm:p-6">
            <LocationPicker
              lat={lat}
              lon={lon}
              bounds={meta.bounds}
              mapClassName="h-64 overflow-hidden rounded-2xl border border-edge shadow-soft sm:h-72 lg:h-80"
              onChange={(la, lo) => {
                setLat(la);
                setLon(lo);
                setResult(null);
              }}
            />
          </div>

          <div className="space-y-5 border-t border-edge/80 px-5 py-5 sm:px-6 sm:py-6">
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-widest text-mute">
                Step 2 · Your goal
              </p>
              <p className="mt-1 text-sm text-mute">
                Choose the challenge area and the outcome you want to improve.
                Recommendations are ranked only among practices recorded for that
                challenge (practice family) in the evidence dataset.
              </p>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <label className="block text-sm sm:col-span-2 lg:col-span-1">
                <span className="mb-1.5 block text-[13px] font-medium text-ink">
                  What challenge would you like to solve?
                </span>
                <select
                  value={family}
                  onChange={(e) => {
                    const next = e.target.value;
                    setFamily(next);
                    setIndicator((prev) =>
                      sanitizeIndicatorForFamily(meta, next, prev)
                    );
                    setResult(null);
                  }}
                  className={fieldClass}
                >
                  <option value="" disabled>
                    Select a challenge…
                  </option>
                  {meta.practice_families.map((f) => (
                    <option key={f} value={f}>
                      {f}
                    </option>
                  ))}
                </select>
              </label>

              <label className="block text-sm sm:col-span-2 lg:col-span-1">
                <span className="mb-1.5 block text-[13px] font-medium text-ink">
                  What is your objective?
                </span>
                <select
                  value={indicator}
                  disabled={!family}
                  onChange={(e) => {
                    setIndicator(e.target.value);
                    setResult(null);
                  }}
                  className={fieldClass}
                  aria-describedby={
                    family ? "dashboard-objective-hint" : undefined
                  }
                >
                  <option value="" disabled>
                    {family
                      ? "Select an objective…"
                      : "Select a challenge first…"}
                  </option>
                  {objectiveOptions.map((ind) => (
                    <option key={ind.key} value={ind.key}>
                      {indicatorLabelForFamily(family, ind)}
                    </option>
                  ))}
                </select>
                {family ? (
                  <p
                    id="dashboard-objective-hint"
                    className="mt-1.5 text-[12px] text-mute"
                  >
                    {objectiveOptions.length} objective
                    {objectiveOptions.length === 1 ? "" : "s"} aligned with{" "}
                    {family.replace(/ and management$/i, "")} in the model
                    dataset.
                  </p>
                ) : null}
              </label>

              <label className="block text-sm">
                <span className="mb-1.5 block text-[13px] font-medium text-ink">
                  Crop <span className="font-normal text-mute">(optional)</span>
                </span>
                <input
                  value={crop}
                  onChange={(e) => setCrop(e.target.value)}
                  list="crop-options-dashboard"
                  placeholder="e.g. Maize, Teff, Coffee"
                  className={fieldClass}
                />
                <datalist id="crop-options-dashboard">
                  {meta.crop_types.map((c) => (
                    <option key={c} value={c} />
                  ))}
                </datalist>
              </label>

              <label className="block text-sm">
                <span className="mb-1.5 block text-[13px] font-medium text-ink">
                  How many practices?
                </span>
                <select
                  value={topN}
                  onChange={(e) => setTopN(Number(e.target.value))}
                  className={fieldClass}
                >
                  {[1, 2, 3, 4, 5].map((n) => (
                    <option key={n} value={n}>
                      Top {n}{n === 1 ? " (recommended)" : ""}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            {error && (
              <p className="text-sm text-soil" role="alert">
                {error}
              </p>
            )}

            <button
              type="submit"
              disabled={busy || !ready}
              className="flex w-full items-center justify-center gap-2 rounded-xl bg-leaf py-3.5 text-sm font-semibold text-white shadow-soft transition hover:bg-leaf-deep disabled:opacity-45 sm:max-w-md"
            >
              {busy ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" /> Finding practices…
                </>
              ) : (
                "Get recommendations"
              )}
            </button>
          </div>
        </form>

        <section aria-label="Results" className="space-y-5">
          <div className="flex items-end justify-between gap-3">
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-widest text-mute">
                Step 3 · Results
              </p>
              <h2 className="mt-1 font-display text-2xl tracking-tight text-ink">
                Recommendations &amp; context
              </h2>
            </div>
          </div>

          {!result && (
            <div className="flex min-h-[16rem] flex-col items-center justify-center rounded-2xl border border-dashed border-edge bg-elevated/50 px-6 py-12 text-center sm:min-h-[20rem]">
              <MapPinned className="mb-3 h-8 w-8 text-mute/60" aria-hidden />
              <p className="max-w-md text-sm leading-relaxed text-mute">
                Complete the map and form above, then run{" "}
                <span className="font-medium text-ink">Get recommendations</span>.
                Ranked practices, effect charts, and local geospatial context will
                show here.
              </p>
            </div>
          )}

          {result && (
            <>
              <GlassCard className="p-5 sm:p-6">
                <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
                  <h2 className="font-display text-2xl tracking-tight text-ink">
                    Recommended practices
                  </h2>
                  <div className="flex flex-wrap gap-2">
                    <Button
                      type="button"
                      variant="secondary"
                      size="sm"
                      onClick={copyResults}
                    >
                      <Copy className="h-3.5 w-3.5" />
                      {copied ? "Copied" : "Copy"}
                    </Button>
                    <Button
                      type="button"
                      variant="secondary"
                      size="sm"
                      onClick={exportCsv}
                    >
                      <Download className="h-3.5 w-3.5" />
                      CSV
                    </Button>
                    <Button
                      type="button"
                      variant="dark"
                      size="sm"
                      onClick={explainInChat}
                    >
                      <MessageSquare className="h-3.5 w-3.5" /> Explain in chat
                    </Button>
                  </div>
                </div>
                <RecommendationPanel
                  data={result}
                  lead={lead}
                  variant={topN === 1 ? "hero" : "default"}
                />
              </GlassCard>

              <div className="grid gap-5 lg:grid-cols-2">
                <GlassCard className="p-5 sm:p-6">
                  <h3 className="font-display text-xl tracking-tight text-ink">
                    Estimated effect
                  </h3>
                  <p className="mt-1 text-sm text-mute">
                    Ranked % change for your objective
                  </p>
                  <div className="mt-4">
                    <PctChangeChart
                      ranked={result.details.ranked}
                      direction={result.query.goal_direction}
                    />
                  </div>
                </GlassCard>

                <GlassCard className="p-5 sm:p-6">
                  <h3 className="font-display text-xl tracking-tight text-ink">
                    Local context
                    {zone ? ` · ${zone}` : ""}
                  </h3>
                  <p className="mt-1 text-sm text-mute">
                    Auto-sampled from the geospatial stack
                  </p>
                  <dl className="mt-4 grid grid-cols-2 gap-3">
                    {[
                      ["Rainfall", "Rainfall", "mm", 0],
                      ["temp_mean_annual", "Mean temp", "°C", 1],
                      ["Altitude_r", "Altitude", "m", 0],
                      ["slope", "Slope", "%", 1],
                      ["soil_clay", "Clay", "%", 0],
                      ["soil_ph", "Soil pH", "", 1],
                      ["soil_soc", "Soil organic C", "", 1],
                      ["lgp_days", "Growing period", "days", 0],
                    ].map(([key, label, unit, digits]) => {
                      const raw = result.details.context?.[key as string];
                      if (raw == null) return null;
                      const n = typeof raw === "number" ? raw : Number(raw);
                      const text = Number.isNaN(n)
                        ? String(raw)
                        : n.toFixed(digits as number);
                      return (
                        <div
                          key={key as string}
                          className="rounded-2xl border border-edge/70 bg-canvas/40 px-3 py-2.5"
                        >
                          <dt className="text-[11px] text-mute">{label as string}</dt>
                          <dd className="text-sm font-semibold text-ink">
                            {text}
                            {unit ? ` ${unit}` : ""}
                          </dd>
                        </div>
                      );
                    })}
                  </dl>
                  <p className="mt-4 text-xs text-mute">
                    Confidence:{" "}
                    <span className="font-semibold capitalize text-ink">
                      {result.details.confidence}
                    </span>
                    {" · "}
                    {result.details.ranked[0]?.n_evidence ?? 0} field obs. on
                    top practice
                  </p>
                </GlassCard>
              </div>
            </>
          )}
        </section>
      </div>
    </div>
  );
}
