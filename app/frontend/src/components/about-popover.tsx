"use client";

import { useEffect, useRef, useState } from "react";
import { Info } from "lucide-react";

export function AboutPopover() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onDoc(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="rounded-full p-2.5 text-mute transition hover:bg-panel hover:text-ink"
        aria-expanded={open}
        aria-haspopup="dialog"
        aria-label="About this model"
      >
        <Info className="h-4 w-4" />
      </button>
      {open && (
        <div
          role="dialog"
          aria-label="How it works"
          className="absolute right-0 top-full z-50 mt-2 w-80 rounded-3xl border border-edge bg-elevated p-5 shadow-lift"
        >
          <h2 className="font-display text-lg tracking-tight text-ink">
            How it works
          </h2>
          <p className="mt-2 text-sm leading-relaxed text-mute">
            AgroGuide reads the agro-ecological context under your map pin and ranks
            Climate-Smart Agriculture practices with a Random Forest trained on
            Ethiopian meta-analysis field evidence. Skill is modest, so trust the
            <em> ordering</em> more than the exact percentages. The assistant only
            interprets your words — every number comes from the model.
          </p>
        </div>
      )}
    </div>
  );
}
