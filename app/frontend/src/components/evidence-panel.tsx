"use client";

import { useEffect, useRef, useState } from "react";
import { BookOpen, ChevronDown, ExternalLink, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { postExplain } from "@/lib/api";
import type { ExplainCitation, ExplainResponse, RecommendResponse } from "@/lib/types";
import { useMetadata } from "./metadata-provider";

/** Evidence-on-demand for a recommendation card (Phase P2c; two-tier P5a).
 *
 * Hidden entirely until /metadata reports rag_ready. On first open it lazily
 * POSTs the recommendation to /explain and caches the result: a grounded
 * explanation plus one chip per cited source. Tier "evidence" chips are ERA
 * studies (era_code · title · year, linking to the DOI); tier "guidance"
 * chips are GARDIAN implementation documents — visually distinct (accent
 * ring + "Guidance" badge, own section) and linking to the source URL.
 */

type FetchState =
  | { status: "idle" | "loading" }
  | { status: "ready"; result: ExplainResponse }
  | { status: "error"; message: string };

function StudyChip({ citation }: { citation: ExplainCitation }) {
  const isGuidance = citation.tier === "guidance";
  const label = [
    citation.era_code,
    citation.title || (isGuidance ? "Untitled document" : "Untitled study"),
    citation.year != null ? String(citation.year) : null,
  ]
    .filter(Boolean)
    .join(" · ");
  const href = isGuidance
    ? citation.url ?? (citation.doi ? `https://doi.org/${citation.doi}` : null)
    : citation.doi
      ? `https://doi.org/${citation.doi}`
      : null;
  const body = (
    <>
      {isGuidance && (
        <span className="shrink-0 rounded-full bg-accent/15 px-1.5 py-px text-[9px] font-semibold uppercase tracking-wider text-accent">
          Guidance
        </span>
      )}
      <span className="max-w-[16rem] truncate sm:max-w-[22rem]">{label}</span>
      {citation.n_passages > 1 && (
        <span className="shrink-0 text-mute">×{citation.n_passages}</span>
      )}
      {href && <ExternalLink className="h-3 w-3 shrink-0 text-mute" aria-hidden />}
    </>
  );
  const className = cn(
    "inline-flex max-w-full items-center gap-1.5 rounded-full border bg-elevated px-2.5 py-1 text-[11px] text-ink",
    isGuidance ? "border-accent/40" : "border-edge"
  );
  if (!href) {
    return (
      <li className={className} title={citation.snippet}>
        {body}
      </li>
    );
  }
  return (
    <li className="max-w-full">
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        title={citation.snippet}
        className={cn(
          className,
          "transition",
          isGuidance
            ? "hover:border-accent hover:text-accent"
            : "hover:border-leaf/40 hover:text-leaf-deep dark:hover:text-leaf-bright"
        )}
      >
        {body}
      </a>
    </li>
  );
}

export function EvidencePanel({ data }: { data: RecommendResponse }) {
  const { meta } = useMetadata();
  const [open, setOpen] = useState(false);
  const [state, setState] = useState<FetchState>({ status: "idle" });
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  // Evidence is only offered when the backend has a built RAG index.
  if (!meta?.rag_ready) return null;

  const load = () => {
    setState({ status: "loading" });
    postExplain(data)
      .then((result) => {
        if (mounted.current) setState({ status: "ready", result });
      })
      .catch((e: Error) => {
        if (mounted.current)
          setState({ status: "error", message: e.message || "Evidence unavailable" });
      });
  };

  const toggle = () => {
    setOpen((v) => !v);
    if (state.status === "idle") load();
  };

  return (
    <div>
      <button
        type="button"
        onClick={toggle}
        aria-expanded={open}
        className="inline-flex items-center gap-1 text-[13px] font-medium text-leaf-deep transition hover:opacity-80 dark:text-leaf-bright"
      >
        <BookOpen className="h-3.5 w-3.5" aria-hidden />
        Evidence
        <ChevronDown className={cn("h-4 w-4 transition-transform", open && "rotate-180")} />
      </button>

      {open && (
        <div className="mt-2 space-y-3 rounded-2xl border border-edge bg-canvas/50 p-4">
          {state.status === "loading" && (
            <p className="flex items-center gap-2 text-sm text-mute">
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
              Retrieving evidence from the source studies…
            </p>
          )}

          {state.status === "error" && (
            <div className="space-y-2">
              <p className="text-sm text-soil">{state.message}</p>
              <button
                type="button"
                onClick={load}
                className="text-[13px] font-medium text-leaf-deep hover:opacity-80 dark:text-leaf-bright"
              >
                Try again
              </button>
            </div>
          )}

          {state.status === "ready" && (
            <>
              <div className="flex flex-wrap items-center gap-1.5">
                <span
                  className={cn(
                    "rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider",
                    state.result.grounded
                      ? "bg-leaf/12 text-leaf-deep dark:text-leaf-bright"
                      : "bg-soil/10 text-soil"
                  )}
                >
                  {state.result.grounded ? "Grounded in literature" : "No evidence retrieved"}
                </span>
                <span className="rounded-full bg-canvas px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider text-mute ring-1 ring-edge">
                  {state.result.llm_used ? "AI summary" : "Deterministic summary"}
                </span>
              </div>

              <p className="whitespace-pre-line text-sm leading-relaxed text-ink">
                {state.result.explanation}
              </p>

              {(() => {
                const evidence = state.result.citations.filter(
                  (c) => c.tier !== "guidance"
                );
                const guidance = state.result.citations.filter(
                  (c) => c.tier === "guidance"
                );
                return (
                  <>
                    {evidence.length > 0 && (
                      <div>
                        <p className="mb-1.5 text-[11px] font-medium uppercase tracking-[0.14em] text-mute">
                          Source studies ({evidence.length})
                        </p>
                        <ul className="flex flex-wrap gap-1.5">
                          {evidence.map((c, i) => (
                            <StudyChip key={c.era_code ?? c.doi ?? c.title ?? i} citation={c} />
                          ))}
                        </ul>
                      </div>
                    )}
                    {guidance.length > 0 && (
                      <div>
                        <p className="mb-1.5 text-[11px] font-medium uppercase tracking-[0.14em] text-mute">
                          Implementation guidance ({guidance.length})
                        </p>
                        <ul className="flex flex-wrap gap-1.5">
                          {guidance.map((c, i) => (
                            <StudyChip key={c.url ?? c.doi ?? c.title ?? i} citation={c} />
                          ))}
                        </ul>
                      </div>
                    )}
                  </>
                );
              })()}
            </>
          )}
        </div>
      )}
    </div>
  );
}
