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
    <div className="mx-auto max-w-content px-4 py-8 sm:px-6" aria-busy>
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
    if (nextStep) setStepOverride(nextStep);
  }

  // A complete request in the URL scores straight away (POST /recommend runs in
  // parallel with /metadata); the input steps need the metadata lists first.
  if (!meta && step !== "results") {
    if (loading) return <AdvisorSkeleton />;
    return (
      <div className="mx-auto max-w-content px-4 py-8 sm:px-6">
        <Alert variant="danger" title={ts("apiUnreachable")}>
          <p lang="en">{error}</p>
          <Button variant="outline" size="sm" className="mt-3" onClick={refresh}>
            {ts("retry")}
          </Button>
        </Alert>
      </div>
    );
  }

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
    <div className="mx-auto max-w-content px-4 py-6 sm:px-6 lg:py-8">
      <div className="mb-5">
        <h1 className="text-2xl sm:text-3xl">{t("title")}</h1>
        <p className="mt-1 max-w-2xl text-muted">{t("subtitle")}</p>
      </div>

      <Stepper
        steps={steps}
        current={step}
        onSelect={(key) => setStepOverride(key as StepKey)}
        label={ta("stepper")}
        currentLabel={ta("currentStep")}
        completedLabel={ta("completedStep")}
      />
      <p className="sr-only" aria-live="polite">
        {t("stepOf", { current: stepIndex + 1, total: STEP_ORDER.length })}
      </p>

      <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,1fr)_18rem]">
        <div className="min-w-0">
          {step === "location" && meta ? (
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
            <div className="mt-6">
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
          className="order-first lg:order-none"
        />
      </div>
    </div>
  );
}
