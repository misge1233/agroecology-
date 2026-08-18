"use client";

import { AnimatePresence, motion } from "framer-motion";
import { MapPinned, Navigation } from "lucide-react";
import type { IndicatorMeta, Metadata } from "@/lib/types";
import {
  indicatorLabelForFamily,
  shortFamilyName,
  type ChatSetupStage,
  type ChatSetupState,
} from "@/lib/chat-flow";
import {
  ChallengePicker,
  ObjectivePicker,
  SetupProgressSteps,
  SetupStagePanel,
} from "./setup-pickers";
import { cn } from "@/lib/utils";

const STAGE_LABEL: Record<ChatSetupStage, string> = {
  challenge: "Challenge",
  objective: "Objective",
  location: "Location",
  complete: "Ready",
};

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
  onPickObjective: (ind: IndicatorMeta) => void;
  onChangeChallenge: () => void;
  onOpenMap: () => void;
  onUseLocation: () => void;
}) {
  if (setup.stage === "complete") return null;

  const steps: ChatSetupStage[] = ["challenge", "objective", "location"];

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 6 }}
      className="flex justify-start pl-10"
    >
      <div className="w-full max-w-[min(100%,36rem)] space-y-3 rounded-[1.35rem] border border-edge/70 bg-elevated/60 p-4 shadow-soft backdrop-blur-sm">
        <SetupProgressSteps
          steps={steps}
          stepLabels={STAGE_LABEL}
          active={setup.stage}
          completed={{
            challenge: !!setup.family,
            objective: !!setup.indicatorKey,
          }}
        />

        {setup.family && setup.stage !== "challenge" && (
          <p className="text-[13px] text-mute">
            Challenge:{" "}
            <span className="font-medium text-ink">{shortFamilyName(setup.family)}</span>
            {setup.indicatorKey && setup.stage === "location" ? (
              <>
                {" "}
                · Objective:{" "}
                <span className="font-medium text-ink">
                  {indicatorLabelForFamily(
                    setup.family,
                    meta.indicators.find((i) => i.key === setup.indicatorKey) ?? {
                      key: setup.indicatorKey,
                      label: setup.indicatorKey,
                      direction: "increase",
                    }
                  )}
                </span>
              </>
            ) : null}
          </p>
        )}

        <AnimatePresence mode="wait">
          {setup.stage === "challenge" && (
            <SetupStagePanel key="challenge" title="Choose your challenge">
              <ChallengePicker
                meta={meta}
                selectedFamily={setup.family}
                onSelect={onPickChallenge}
              />
            </SetupStagePanel>
          )}

          {setup.stage === "objective" && setup.family && (
            <SetupStagePanel key="objective" title="Pick your objective">
              <ObjectivePicker
                meta={meta}
                family={setup.family}
                selectedKey={setup.indicatorKey}
                onSelect={onPickObjective}
                onChangeChallenge={onChangeChallenge}
              />
            </SetupStagePanel>
          )}

          {setup.stage === "location" && (
            <SetupStagePanel key="location" title="Set your farm location">
              <p className="mb-1 text-[13px] leading-relaxed text-mute">
                Drop a pin inside Ethiopia, use GPS, or type coordinates in the box below.
              </p>
              <div className="flex flex-wrap gap-2">
                <ActionChip onClick={onOpenMap} icon={MapPinned}>
                  Open map
                </ActionChip>
                <ActionChip onClick={onUseLocation} icon={Navigation}>
                  Use my location
                </ActionChip>
              </div>
            </SetupStagePanel>
          )}
        </AnimatePresence>
      </div>
    </motion.div>
  );
}

function ActionChip({
  children,
  onClick,
  icon: Icon,
}: {
  children: React.ReactNode;
  onClick: () => void;
  icon: typeof MapPinned;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-2 rounded-xl border border-edge bg-elevated px-4 py-2.5 text-[13px] font-semibold text-ink shadow-sm transition hover:border-leaf/40 hover:bg-leaf/5"
      )}
    >
      <Icon className="h-4 w-4 text-leaf" />
      {children}
    </button>
  );
}
