"use client";

import { AnimatePresence, motion } from "framer-motion";
import {
  ArrowDown,
  ArrowUp,
  Beef,
  Check,
  Sprout,
  Trees,
  Waves,
  Wheat,
} from "lucide-react";
import type { IndicatorMeta, Metadata } from "@/lib/types";
import {
  indicatorLabelForFamily,
  indicatorsForFamily,
  shortFamilyName,
} from "@/lib/chat-flow";
import { cn } from "@/lib/utils";

export const FAMILY_ICONS: Record<string, typeof Wheat> = {
  "Crop production and management": Wheat,
  "Livestock production and management": Beef,
  "Integrated soil fertility management": Sprout,
  "Erosion control and water management": Waves,
  "Agro-forestry and forest management": Trees,
};

export function SetupProgressSteps<T extends string>({
  steps,
  stepLabels,
  active,
  completed,
}: {
  steps: T[];
  stepLabels: Record<T, string>;
  active: T;
  completed: Partial<Record<T, boolean>>;
}) {
  const stepIndex = steps.indexOf(active);
  return (
    <div className="flex flex-wrap items-center gap-2">
      {steps.map((s, i) => {
        const done = completed[s] || i < stepIndex;
        const isActive = active === s;
        return (
          <span
            key={s}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wider",
              isActive
                ? "bg-leaf text-white shadow-sm"
                : done
                  ? "bg-leaf/12 text-leaf-deep dark:text-leaf-bright"
                  : "bg-panel/80 text-mute"
            )}
          >
            {done && !isActive ? <Check className="h-3 w-3" aria-hidden /> : null}
            {i + 1}. {stepLabels[s]}
          </span>
        );
      })}
    </div>
  );
}

export function ChallengePicker({
  meta,
  selectedFamily,
  onSelect,
  className,
}: {
  meta: Metadata;
  selectedFamily?: string | null;
  onSelect: (family: string) => void;
  className?: string;
}) {
  return (
    <div className={cn("grid gap-2 sm:grid-cols-2", className)}>
      {meta.practice_families.map((f) => {
        const Icon = FAMILY_ICONS[f] ?? Sprout;
        const selected = selectedFamily === f;
        return (
          <button
            key={f}
            type="button"
            onClick={() => onSelect(f)}
            className={cn(
              "group flex items-start gap-3 rounded-2xl border px-3.5 py-3 text-left transition",
              selected
                ? "border-leaf/50 bg-leaf/10 shadow-sm ring-1 ring-leaf/20"
                : "border-edge/80 bg-elevated/90 hover:border-leaf/35 hover:bg-leaf/5"
            )}
          >
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-leaf/12 text-leaf-deep transition group-hover:scale-105 dark:text-leaf-bright">
              <Icon className="h-4 w-4" aria-hidden />
            </span>
            <span>
              <span className="block text-[13px] font-semibold leading-snug text-ink">
                {shortFamilyName(f)}
              </span>
              <span className="mt-0.5 block text-[11px] leading-relaxed text-mute">
                Evidence-ranked practices in this area
              </span>
            </span>
          </button>
        );
      })}
    </div>
  );
}

export function ObjectivePicker({
  meta,
  family,
  selectedKey,
  onSelect,
  onChangeChallenge,
}: {
  meta: Metadata;
  family: string;
  selectedKey?: string | null;
  onSelect: (ind: IndicatorMeta) => void;
  onChangeChallenge?: () => void;
}) {
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-2">
        {indicatorsForFamily(meta, family).map((ind) => {
          const selected = selectedKey === ind.key;
          return (
            <ObjectiveChip
              key={ind.key}
              ind={ind}
              label={indicatorLabelForFamily(family, ind)}
              selected={selected}
              onClick={() => onSelect(ind)}
            />
          );
        })}
      </div>
      {onChangeChallenge ? (
        <button
          type="button"
          className="text-[12px] font-medium text-mute underline-offset-2 hover:text-ink hover:underline"
          onClick={onChangeChallenge}
        >
          Change challenge
        </button>
      ) : null}
    </div>
  );
}

export function ObjectiveChip({
  ind,
  label,
  onClick,
  selected,
}: {
  ind: IndicatorMeta;
  label: string;
  onClick: () => void;
  selected?: boolean;
}) {
  const Icon = ind.direction === "increase" ? ArrowUp : ArrowDown;
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-2 rounded-full border px-3.5 py-2.5 text-left text-[12.5px] font-medium shadow-sm transition",
        selected
          ? "border-leaf/50 bg-leaf/10 text-ink ring-1 ring-leaf/20"
          : "border-edge/90 bg-elevated text-ink hover:border-leaf/40 hover:bg-leaf/5 hover:shadow-md"
      )}
    >
      <span className="flex h-7 w-7 items-center justify-center rounded-full bg-leaf/12 text-leaf-deep dark:text-leaf-bright">
        <Icon className="h-3.5 w-3.5" aria-hidden />
      </span>
      {label}
    </button>
  );
}

export function SetupStagePanel({
  title,
  children,
  id,
}: {
  title: string;
  children: React.ReactNode;
  id?: string;
}) {
  return (
    <motion.div
      id={id}
      initial={{ opacity: 0, x: 12 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -12 }}
      transition={{ duration: 0.25, ease: [0.22, 1, 0.36, 1] }}
      className="space-y-3"
    >
      <p className="text-[11px] font-medium uppercase tracking-widest text-mute">
        {title}
      </p>
      {children}
    </motion.div>
  );
}

export function SetupSummaryLine({
  family,
  indicatorKey,
  meta,
  locationLabel,
}: {
  family: string | null;
  indicatorKey: string | null;
  meta: Metadata;
  locationLabel?: string | null;
}) {
  if (!family && !indicatorKey && !locationLabel) return null;
  const ind =
    indicatorKey &&
    meta.indicators.find((i) => i.key === indicatorKey);
  return (
    <p className="text-[13px] text-mute">
      {locationLabel ? (
        <>
          Location: <span className="font-medium text-ink">{locationLabel}</span>
          {" · "}
        </>
      ) : null}
      {family ? (
        <>
          Challenge:{" "}
          <span className="font-medium text-ink">{shortFamilyName(family)}</span>
        </>
      ) : null}
      {family && ind ? (
        <>
          {" "}
          · Objective:{" "}
          <span className="font-medium text-ink">
            {indicatorLabelForFamily(family, ind)}
          </span>
        </>
      ) : null}
    </p>
  );
}
