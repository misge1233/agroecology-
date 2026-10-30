"use client";

import { useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { usePathname, useRouter } from "@/i18n/navigation";
import { sanitizeIndicatorForFamily } from "@/lib/chat-flow";
import { useMetadata } from "@/components/metadata-provider";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Stepper, type StepperStep } from "@/components/ui/stepper";
import { PageHeader } from "@/components/shell/page-header";
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
import { SummaryRail } from "./summary-rail";
import { useZone } from "./use-zone";

export function AdvisorSkeleton() {
  return (
    <div className="container-page py-8" aria-busy>
      <Skeleton className="h-8 w-48" />
      <Skeleton className="mt-3 h-4 w-96 max-w-full" />
      <Skeleton className="mt-6 h-10 w-full" />
      <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,1fr)_18rem]">
        <Skeleton className="h-96 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    </div>
  );
}

/** Only the step area while /metadata loads — the page header is already on screen. */
function StepSkeleton() {
  return (
    <div aria-busy className="space-y-4">
      <Skeleton className="h-7 w-64 max-w-full" />
      <Skeleton className="h-4 w-80 max-w-full" />
      <Skeleton className="h-64 w-full sm:h-80" />
      <Skeleton className="h-10 w-full" />
    </div>
  );
}

/**
 * The four-step Advisor. The URL is the single source of truth for the
 * request (`?lat&lon&family&indicator&crop&top`), so a result can be shared
 * and survives reload; only "which step is open" lives in React state.
 */
export function AdvisorFlow() {
  const t = useTranslations("advisor");
  const ta = useTranslations("a11y");
  const ts = useTranslations("status");
  const tc = useTranslations("common");
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

  // A complete request in the URL scores straight away (POST /recommend runs in
  // parallel with /metadata); the input steps need the metadata lists first.
  // The title, subtitle and stepper never wait for metadata (they are the
  // page's LCP text and are server-rendered).
  const metaGate = !meta && step !== "results";
  const families = meta?.practice_families ?? [];
  const hasLocation = params.lat != null && params.lon != null;
  const steps: StepperStep[] = STEP_ORDER.map((key) => ({
    key,
    label: t(`steps.${key}`),
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

  return (
    <>
    <PageHeader title={t("title")} description={t("subtitle")} compact />
    <div className="container-page py-8 lg:py-10 print:p-0">
      <Stepper
        steps={steps}
        current={step}
        onSelect={(key) => setStepOverride(key as StepKey)}
        label={ta("stepper")}
        currentLabel={ta("currentStep")}
        completedLabel={ta("completedStep")}
        className="no-print"
      />
      <p className="no-print sr-only" aria-live="polite">
        {t("stepOf", { current: stepIndex + 1, total: STEP_ORDER.length })}
      </p>

      <div className="mt-8 grid gap-8 lg:grid-cols-[minmax(0,1fr)_20rem] print:mt-0 print:block">
        <div className="min-w-0">
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
              onChange={(lat, lon) => update({ lat, lon })}
              onNext={() => setStepOverride(params.family ? (params.indicator ? "crop" : "objective") : "challenge")}
            />
          ) : step === "challenge" && meta ? (
            <ChallengeStep
              families={families}
              selected={params.family}
              onSelect={(family) => update({ family }, "objective")}
            />
          ) : step === "objective" && params.family && meta ? (
            <ObjectiveStep
              meta={meta}
              family={params.family}
              selected={params.indicator}
              onSelect={(indicator) => update({ indicator }, "crop")}
            />
          ) : step === "crop" && meta ? (
            <CropStep
              cropTypes={meta.crop_types}
              value={params.crop}
              onChange={(crop) => update({ crop })}
              onSubmit={() => setStepOverride("results")}
            />
          ) : step === "results" ? (
            <Results
              params={params}
              onTopN={(topN) => update({ topN })}
              onReset={() => {
                router.replace(pathname, { scroll: false });
                setStepOverride("location");
              }}
            />
          ) : (
            <AdvisorSkeleton />
          )}
          {step !== "location" && step !== "results" ? (
            <div className="no-print mt-6">
              <Button variant="ghost" onClick={() => setStepOverride(STEP_ORDER[Math.max(0, stepIndex - 1)])}>
                {tc("back")}
              </Button>
            </div>
          ) : null}
        </div>

        <SummaryRail
          lat={params.lat}
          lon={params.lon}
          belt={zone.belt}
          family={params.family}
          indicator={params.indicator}
          crop={params.crop}
          onEdit={(key) => setStepOverride(key)}
          onReset={() => {
            router.replace(pathname, { scroll: false });
            setStepOverride("location");
          }}
          // Phones: an all-empty summary is noise above step 1, so it appears once something is set.
          className={`no-print order-first lg:order-none ${hasLocation || params.family ? "" : "hidden lg:block"}`}
        />
      </div>
    </div>
    </>
  );
}
