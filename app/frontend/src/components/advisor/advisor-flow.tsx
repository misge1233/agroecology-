"use client";

import { useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Compass, RotateCcw } from "lucide-react";
import { useFormatter, useLocale, useTranslations } from "next-intl";
import { usePathname, useRouter } from "@/i18n/navigation";
import { aezName, familyShort, indicatorLabel } from "@/i18n/glossary";
import type { Locale } from "@/i18n/routing";
import { sanitizeIndicatorForFamily } from "@/lib/chat-flow";
import { useMetadata } from "@/components/metadata-provider";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Stepper, type StepperStep } from "@/components/ui/stepper";
import {
  STEP_ORDER,
  autoStep,
  isComplete,
  parseParams,
  toSearch,
  type AdvisorParams,
  type StepKey,
} from "./advisor-state";
import { ChallengeStep } from "./challenge-step";
import { CropStep } from "./crop-step";
import { LocationStep } from "./location-step";
import { ObjectiveStep } from "./objective-step";
import { Results } from "./results";
import { StepPanel } from "./step-layout";
import { ContourLines } from "@/components/shell/contour-lines";
import { useZone } from "./use-zone";

/** Whole-page placeholder (Suspense fallback): header band, stepper, step panel. */
export function AdvisorSkeleton() {
  return (
    <div aria-busy>
      <div className="border-b border-border bg-primary-soft">
        <div className="container-page py-8 sm:py-10">
          <Skeleton className="h-9 w-48" />
          <Skeleton className="mt-3 h-5 w-96 max-w-full" />
          <Skeleton className="mt-8 h-10 w-full" />
        </div>
      </div>
      <div className="bg-surface-2">
        <div className="container-page py-8 sm:py-10">
          <Skeleton className="h-[32rem] w-full rounded-panel" />
        </div>
      </div>
    </div>
  );
}

/** Only the step area while /metadata loads; the page header is already on screen. */
function StepSkeleton() {
  return (
    <StepPanel>
      <div aria-busy className="space-y-4">
        <Skeleton className="h-4 w-24" />
        <Skeleton className="h-8 w-72 max-w-full" />
        <Skeleton className="h-5 w-96 max-w-full" />
        <Skeleton className="mt-4 h-80 w-full sm:h-[28rem]" />
      </div>
    </StepPanel>
  );
}

/**
 * The four-step Advisor. The URL is the single source of truth for the
 * request (`?lat&lon&family&indicator&crop&top`), so a result can be shared
 * and survives reload; only "which step is open" lives in React state.
 * U5: one white header band (title, start over, stepper with the chosen
 * values) over a solid tinted work area; input steps sit in one white panel.
 */
export function AdvisorFlow() {
  const t = useTranslations("advisor");
  const tsum = useTranslations("advisor.summary");
  const ta = useTranslations("a11y");
  const ts = useTranslations("status");
  const locale = useLocale() as Locale;
  const format = useFormatter();
  const { meta, loading, error, refresh } = useMetadata();
  const router = useRouter();
  const pathname = usePathname();
  const sp = useSearchParams();
  const params = useMemo(() => parseParams(new URLSearchParams(sp.toString()), meta), [sp, meta]);
  const [stepOverride, setStepOverride] = useState<StepKey | null>(null);
  const step: StepKey = stepOverride ?? autoStep(params);
  const zone = useZone(params.lat, params.lon, meta?.bounds ?? null);

  function update(patch: Partial<AdvisorParams>, nextStep?: StepKey) {
    const next: AdvisorParams = { ...params, ...patch };
    if (meta && next.family && next.indicator) {
      next.indicator = sanitizeIndicatorForFamily(meta, next.family, next.indicator) || null;
    }
    if (!next.family) next.indicator = null;
    const qs = toSearch(next);
    router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    // Stay on the current step unless the caller moves on explicitly: a pin
    // dropped on step 1 must not jump to step 2 before the belt is shown and
    // "Next" is pressed (U2 E2E found the auto-advance).
    setStepOverride(nextStep ?? step);
  }

  function reset() {
    router.replace(pathname, { scroll: false });
    setStepOverride("location");
  }

  // A complete request in the URL scores straight away (POST /recommend runs in
  // parallel with /metadata); the input steps need the metadata lists first.
  // The title, subtitle and stepper never wait for metadata (they are the
  // page's LCP text and are server-rendered).
  const metaGate = !meta && step !== "results";
  const families = meta?.practice_families ?? [];
  const hasLocation = params.lat != null && params.lon != null;
  const anySet = hasLocation || !!params.family;
  const coords = (n: number) => format.number(n, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const values: Record<StepKey, string | null> = {
    location: zone.belt
      ? aezName(zone.belt, locale)
      : hasLocation
        ? `${coords(params.lat as number)}, ${coords(params.lon as number)}`
        : null,
    challenge: params.family ? familyShort(params.family, locale) : null,
    objective: params.indicator ? indicatorLabel(params.indicator, locale) : null,
    crop: params.crop ? params.crop : step === "results" ? tsum("anyCrop") : null,
    results: null,
  };
  const steps: StepperStep[] = STEP_ORDER.map((key) => ({
    key,
    label: t(`steps.${key}`),
    value: values[key],
    reachable:
      key === "location" ||
      (key === "challenge" && hasLocation) ||
      (key === "objective" && !!params.family) ||
      (key === "crop" && !!params.indicator) ||
      (key === "results" && isComplete(params)),
    complete:
      (key === "location" && hasLocation) ||
      (key === "challenge" && !!params.family) ||
      (key === "objective" && !!params.indicator) ||
      (key === "crop" && step === "results"),
  }));
  const stepIndex = STEP_ORDER.indexOf(step);
  const stepLabel = t("stepOf", { current: stepIndex + 1, total: STEP_ORDER.length });
  const back = () => setStepOverride(STEP_ORDER[Math.max(0, stepIndex - 1)]);

  return (
    <>
      <section className="no-print relative isolate overflow-hidden border-b border-border bg-primary-soft">
        <ContourLines />
        <div className="container-page pb-6 pt-8 sm:pt-10">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div className="flex min-w-0 items-center gap-4">
              <span className="hidden h-14 w-14 shrink-0 items-center justify-center rounded-card bg-primary text-primary-fg shadow-1 sm:flex">
                <Compass className="h-7 w-7" aria-hidden />
              </span>
              <div className="min-w-0">
                <h1 className="text-balance text-3xl">{t("title")}</h1>
                <p className="mt-1.5 max-w-2xl text-base text-muted">{t("subtitle")}</p>
              </div>
            </div>
            {anySet && step !== "results" ? (
              <Button variant="outline" size="sm" onClick={reset}>
                <RotateCcw className="h-4 w-4" aria-hidden />
                {tsum("startOver")}
              </Button>
            ) : null}
          </div>
          <Stepper
            steps={steps}
            current={step}
            onSelect={(key) => setStepOverride(key as StepKey)}
            label={ta("stepper")}
            currentLabel={ta("currentStep")}
            completedLabel={ta("completedStep")}
            className="mt-8"
          />
          <p className="sr-only" aria-live="polite">
            {stepLabel}
          </p>
        </div>
      </section>

      <div className="bg-surface-2 print:bg-transparent">
        <div className="container-page py-8 sm:py-10 print:p-0">
          {metaGate && !loading ? (
            <Alert variant="danger" title={ts("apiUnreachable")}>
              <p lang="en">{error}</p>
              <Button variant="outline" size="sm" className="mt-3" onClick={refresh}>
                {ts("retry")}
              </Button>
            </Alert>
          ) : metaGate ? (
            <StepSkeleton />
          ) : step === "location" && meta ? (
            <LocationStep
              lat={params.lat}
              lon={params.lon}
              bounds={meta.bounds}
              zone={zone}
              stepLabel={stepLabel}
              onChange={(lat, lon) => update({ lat, lon })}
              onNext={() => setStepOverride(params.family ? (params.indicator ? "crop" : "objective") : "challenge")}
            />
          ) : step === "challenge" && meta ? (
            <ChallengeStep
              families={families}
              selected={params.family}
              stepLabel={stepLabel}
              onBack={back}
              onSelect={(family) => update({ family }, "objective")}
            />
          ) : step === "objective" && params.family && meta ? (
            <ObjectiveStep
              meta={meta}
              family={params.family}
              selected={params.indicator}
              stepLabel={stepLabel}
              onBack={back}
              onSelect={(indicator) => update({ indicator }, "crop")}
            />
          ) : step === "crop" && meta ? (
            <CropStep
              cropTypes={meta.crop_types}
              value={params.crop}
              stepLabel={stepLabel}
              onBack={back}
              onChange={(crop) => update({ crop })}
              onSubmit={() => setStepOverride("results")}
            />
          ) : step === "results" ? (
            <Results params={params} onTopN={(topN) => update({ topN })} onReset={reset} />
          ) : (
            <StepSkeleton />
          )}
        </div>
      </div>
    </>
  );
}
