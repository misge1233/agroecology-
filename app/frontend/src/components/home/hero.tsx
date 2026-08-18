"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { motion, useReducedMotion } from "framer-motion";
import { ArrowRight, MapPin } from "lucide-react";
import { Button } from "@/components/ui/button";

const PROMPTS = [
  "How do I cut soil erosion at 8.38, 39.37?",
  "Best practice to raise maize yield in the highlands?",
  "Reduce runoff with water management near 7.68, 36.83",
  "Increase soil organic matter for teff at 9.03, 38.74",
];

const SOURCES = [
  "WorldClim",
  "SoilGrids",
  "Copernicus DEM",
  "ESA WorldCover",
  "CSA field evidence",
];

export function HomeHero() {
  const router = useRouter();
  const reduce = useReducedMotion();
  const [promptIdx, setPromptIdx] = useState(0);
  const [typed, setTyped] = useState("");
  const [ask, setAsk] = useState("");

  useEffect(() => {
    if (reduce) {
      setTyped(PROMPTS[0]);
      return;
    }
    const full = PROMPTS[promptIdx];
    let i = 0;
    setTyped("");
    let holdId = 0;
    const typeId = window.setInterval(() => {
      i += 1;
      setTyped(full.slice(0, i));
      if (i >= full.length) {
        window.clearInterval(typeId);
        holdId = window.setTimeout(() => {
          setPromptIdx((p) => (p + 1) % PROMPTS.length);
        }, 2200);
      }
    }, 28);
    return () => {
      window.clearInterval(typeId);
      if (holdId) window.clearTimeout(holdId);
    };
  }, [promptIdx, reduce]);

  function goChat(text?: string) {
    const msg = (text ?? ask).trim();
    if (msg) {
      sessionStorage.setItem("agro-seed-message", msg);
    }
    router.push("/chat");
  }

  return (
    <section className="relative overflow-hidden pb-12 pt-12 sm:pb-16 sm:pt-16">
      <div className="mx-auto max-w-7xl px-4 sm:px-6">
        <div className="mx-auto max-w-4xl text-center">
          <motion.p
            initial={reduce ? false : { opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="eyebrow mb-5"
          >
            Evidence · Geospatial context · Transparent ranking
          </motion.p>
          <motion.h1
            initial={reduce ? false : { opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.04, duration: 0.65, ease: [0.22, 1, 0.36, 1] }}
            className="font-display text-[clamp(2.75rem,6.5vw,4.75rem)] font-semibold leading-[0.98] tracking-tight text-ink"
          >
            Agroecology AI
          </motion.h1>
          <motion.p
            initial={reduce ? false : { opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
            className="mx-auto mt-5 max-w-2xl text-lg leading-relaxed text-body sm:text-xl"
          >
            Evidence-ranked climate-smart practices for Ethiopian farms —
            grounded in field trials and local geospatial context.
          </motion.p>

          <motion.div
            initial={reduce ? false : { opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.16 }}
            className="mt-8 flex flex-wrap items-center justify-center gap-3"
          >
            <Button href="/chat" variant="primary" size="lg">
              Request recommendation
              <ArrowRight className="h-4 w-4" />
            </Button>
            <Button href="/dashboard" variant="secondary" size="lg">
              Open analyst view
            </Button>
          </motion.div>
        </div>

        <motion.div
          initial={reduce ? false : { opacity: 0, y: 28 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.22, duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
          className="relative mx-auto mt-12 max-w-3xl"
        >
          <div className="relative overflow-hidden rounded-[1.5rem] bg-aurora-panel p-5 shadow-lift sm:rounded-[1.75rem] sm:p-7 md:p-8">
            <div className="pointer-events-none absolute inset-0 opacity-30">
              <div className="absolute -left-16 top-0 h-56 w-56 rounded-full bg-indigo-400/20 blur-3xl" />
              <div className="absolute bottom-0 right-0 h-64 w-64 rounded-full bg-cyan-500/15 blur-3xl" />
            </div>

            <form
              className="relative z-10"
              onSubmit={(e) => {
                e.preventDefault();
                goChat(ask || typed);
              }}
            >
              <p className="mb-3 text-[11px] font-semibold uppercase tracking-[0.14em] text-white/55">
                Location-aware query
              </p>
              <div className="rounded-2xl border border-white/15 bg-white/[0.97] p-3.5 shadow-lift sm:p-4">
                <div className="flex items-start gap-2.5">
                  <MapPin
                    className="mt-2.5 h-4 w-4 shrink-0 text-leaf"
                    aria-hidden
                  />
                  <label className="sr-only" htmlFor="hero-ask">
                    Ask Agroecology AI
                  </label>
                  <input
                    id="hero-ask"
                    value={ask}
                    onChange={(e) => setAsk(e.target.value)}
                    placeholder={typed || "Ask a farm question…"}
                    className="min-h-11 flex-1 bg-transparent py-2 text-[15px] text-ink outline-none placeholder:text-mute/75"
                  />
                  <Button type="submit" variant="primary" size="sm" className="mt-0.5 shrink-0">
                    Ask
                  </Button>
                </div>
                <div className="mt-3 flex flex-wrap gap-1.5 border-t border-edge/70 pt-3">
                  {SOURCES.map((s) => (
                    <span
                      key={s}
                      className="rounded-md border border-edge/80 bg-panel/60 px-2.5 py-1 text-[11px] font-medium text-body"
                    >
                      {s}
                    </span>
                  ))}
                </div>
              </div>
            </form>
          </div>
        </motion.div>
      </div>
    </section>
  );
}
