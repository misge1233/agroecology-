"use client";

import { ArrowDown, ArrowUp } from "lucide-react";
import { cn } from "@/lib/utils";
import type { IndicatorMeta } from "@/lib/types";

export function IndicatorPicker({
  indicators,
  value,
  onChange,
  variant = "chips",
}: {
  indicators: IndicatorMeta[];
  value?: string | null;
  onChange: (key: string) => void;
  variant?: "chips" | "select";
}) {
  if (variant === "select") {
    return (
      <label className="block text-sm 2xl:text-base">
        <span className="mb-1.5 block text-[13px] font-medium text-ink 2xl:text-[15px]">
          Goal indicator
        </span>
        <select
          className="w-full rounded-2xl border border-edge bg-elevated px-3.5 py-2.5 text-sm text-ink outline-none transition focus:border-ink/20 focus:ring-4 focus:ring-ink/5 2xl:px-4 2xl:py-3 2xl:text-base"
          value={value || ""}
          onChange={(e) => onChange(e.target.value)}
        >
          <option value="" disabled>
            Select indicator…
          </option>
          {indicators.map((ind) => (
            <option key={ind.key} value={ind.key}>
              {ind.label}
            </option>
          ))}
        </select>
      </label>
    );
  }

  return (
    <div className="flex flex-wrap justify-center gap-2 2xl:gap-3" role="listbox" aria-label="Indicators">
      {indicators.map((ind) => {
        const active = value === ind.key;
        const Icon = ind.direction === "increase" ? ArrowUp : ArrowDown;
        return (
          <button
            key={ind.key}
            type="button"
            role="option"
            aria-selected={active}
            onClick={() => onChange(ind.key)}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-lg border px-3.5 py-2 text-[13px] font-medium transition 2xl:px-4 2xl:py-2.5 2xl:text-[15px]",
              active
                ? "border-leaf bg-leaf text-white"
                : "border-edge bg-elevated text-mute shadow-sm hover:border-leaf/25 hover:text-ink"
            )}
          >
            <Icon className="h-3 w-3 opacity-70 2xl:h-3.5 2xl:w-3.5" aria-hidden />
            {ind.label}
          </button>
        );
      })}
    </div>
  );
}

export function ContextChips({
  slots,
  onClear,
}: {
  slots: Record<string, string | number | null | undefined>;
  onClear?: (key: string) => void;
}) {
  const entries = Object.entries(slots).filter(
    ([, v]) => v !== null && v !== undefined && v !== ""
  );
  if (!entries.length) return null;

  return (
    <div className="flex flex-wrap gap-1.5" aria-label="Understood parameters">
      {entries.map(([k, v]) => (
        <span
          key={k}
          className="inline-flex items-center gap-1 rounded-full border border-edge bg-elevated/90 px-2.5 py-1 text-[11px] text-ink shadow-sm"
        >
          <span className="text-mute">{k.replace(/_/g, " ")}:</span>
          <span className="font-medium">{String(v)}</span>
          {onClear && (
            <button
              type="button"
              className="ml-0.5 text-mute hover:text-ink"
              aria-label={`Clear ${k}`}
              onClick={() => onClear(k)}
            >
              ×
            </button>
          )}
        </span>
      ))}
    </div>
  );
}

export function SuggestionChips({
  items,
  onPick,
}: {
  items: string[];
  onPick: (item: string) => void;
}) {
  if (!items.length) return null;
  return (
    <div className="flex flex-wrap justify-center gap-2 2xl:gap-3">
      {items.map((item) => (
        <button
          key={item}
          type="button"
          onClick={() => onPick(item)}
          className="rounded-xl border border-edge bg-elevated px-3.5 py-2 text-left text-[12.5px] text-body shadow-sm transition hover:border-leaf/30 hover:text-ink 2xl:px-4 2xl:py-2.5 2xl:text-[14.5px]"
        >
          {item}
        </button>
      ))}
    </div>
  );
}
