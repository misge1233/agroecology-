"use client";

import { MapPinned, Navigation } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import type { Metadata } from "@/lib/types";
import { type ChatSetupStage, type ChatSetupState } from "@/lib/chat-flow";
import { familyShort, indicatorLabel } from "@/i18n/glossary";
import type { Locale } from "@/i18n/routing";
import { ChallengeCards } from "./advisor/challenge-step";
import { ObjectiveChips } from "./advisor/objective-step";
import { Button } from "./ui/button";
import { Card } from "./ui/card";
import { Stepper } from "./ui/stepper";

/** Guided set-up inside the chat: challenge → objective → location. */
export function ChatQuickReplies({
  meta,
  setup,
  onPickChallenge,
  onPickObjective,
  onChangeChallenge,
  onOpenMap,
  onUseLocation,
}: {
  meta: Metadata;
  setup: ChatSetupState;
  onPickChallenge: (family: string) => void;
  onPickObjective: (indicatorKey: string) => void;
  onChangeChallenge: () => void;
  onOpenMap: () => void;
  onUseLocation: () => void;
}) {
  const t = useTranslations("chat");
  const ta = useTranslations("a11y");
  const locale = useLocale() as Locale;
  if (setup.stage === "complete") return null;

  const order: ChatSetupStage[] = ["challenge", "objective", "location"];
  const steps = order.map((key) => ({
    key,
    label: t(`stage.${key}`),
    reachable: false,
    complete:
      key === "challenge" ? !!setup.family : key === "objective" ? !!setup.indicatorKey : setup.hasLocation,
  }));

  return (
    <div className="rise-in sm:pl-11">
      <Card className="space-y-4 p-4">
        <Stepper
          steps={steps}
          current={setup.stage}
          onSelect={() => undefined}
          label={ta("stepper")}
          currentLabel={ta("currentStep")}
          completedLabel={ta("completedStep")}
        />

        {setup.family && setup.stage !== "challenge" ? (
          <p className="text-sm text-muted">
            {t("stage.challenge")}: <span className="font-medium text-text">{familyShort(setup.family, locale)}</span>
            {setup.indicatorKey && setup.stage === "location" ? (
              <>
                {" · "}
                {t("stage.objective")}:{" "}
                <span className="font-medium text-text">{indicatorLabel(setup.indicatorKey, locale)}</span>
              </>
            ) : null}
          </p>
        ) : null}

        {setup.stage === "challenge" ? (
          <div className="space-y-3">
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-muted">{t("quick.chooseChallenge")}</p>
            <ChallengeCards families={meta.practice_families} selected={setup.family} onSelect={onPickChallenge} />
          </div>
        ) : null}

        {setup.stage === "objective" && setup.family ? (
          <div className="space-y-3">
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-muted">{t("quick.pickObjective")}</p>
            <ObjectiveChips meta={meta} family={setup.family} selected={setup.indicatorKey} onSelect={onPickObjective} />
            <Button variant="link" size="sm" onClick={onChangeChallenge}>
              {t("quick.changeChallenge")}
            </Button>
          </div>
        ) : null}

        {setup.stage === "location" ? (
          <div className="space-y-3">
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-muted">{t("quick.setLocation")}</p>
            <p className="text-sm text-muted">{t("quick.locationHelp")}</p>
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" onClick={onOpenMap}>
                <MapPinned className="h-4 w-4 text-primary" aria-hidden />
                {t("quick.openMap")}
              </Button>
              <Button variant="outline" onClick={onUseLocation}>
                <Navigation className="h-4 w-4 text-primary" aria-hidden />
                {t("useMyLocation")}
              </Button>
            </div>
          </div>
        ) : null}
      </Card>
    </div>
  );
}
