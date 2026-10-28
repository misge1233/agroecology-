"use client";

import { MapPinned, Navigation } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import type { Metadata } from "@/lib/types";
import { type ChatSetupStage, type ChatSetupState } from "@/lib/chat-flow";
import { familyShort, indicatorLabel } from "@/i18n/glossary";
import type { Locale } from "@/i18n/routing";
import { FAMILY_ICONS } from "./advisor/family-icons";
import { ObjectiveChips } from "./advisor/objective-step";
import { Button } from "./ui/button";
import { Card } from "./ui/card";
import { Chip } from "./ui/chip";
import { Stepper } from "./ui/stepper";

/**
 * Guided set-up inside the chat (U2): challenge → objective → location, every
 * option a chip. A chip sends a protocol sentence in the UI language plus a
 * structured hint, so the backend never has to parse translated text.
 */
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
    <div className="rise-in sm:pl-11" data-testid="quick-replies">
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
            <div role="group" aria-label={t("quick.chooseChallenge")} className="flex flex-wrap gap-2">
              {meta.practice_families.map((family) => {
                const Icon = FAMILY_ICONS[family] ?? FAMILY_ICONS["Crop production and management"];
                return (
                  <Chip
                    key={family}
                    selected={setup.family === family}
                    onClick={() => onPickChallenge(family)}
                    icon={<Icon className="h-4 w-4 text-primary" aria-hidden />}
                  >
                    {familyShort(family, locale)}
                  </Chip>
                );
              })}
            </div>
            <p className="text-xs text-muted">{t("quick.orType")}</p>
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
              <Chip onClick={onOpenMap} icon={<MapPinned className="h-4 w-4 text-primary" aria-hidden />}>
                {t("quick.openMap")}
              </Chip>
              <Chip onClick={onUseLocation} icon={<Navigation className="h-4 w-4 text-primary" aria-hidden />}>
                {t("useMyLocation")}
              </Chip>
            </div>
          </div>
        ) : null}
      </Card>
    </div>
  );
}
