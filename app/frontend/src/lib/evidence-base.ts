/** Presentation helpers for the Tier-1 evidence base (Phase P6b-i).
 *
 * The backend's /explain response carries, per recommended practice, how many
 * studies and field observations stand behind it and where they were
 * measured. These helpers turn that into display strings.
 *
 * Counts and provenance ONLY. Effect magnitudes belong to the model: the
 * knowledge graph's dataset aggregates are deliberately absent from the API
 * payload, and nothing here invents one.
 */
import type { EvidenceBaseEntry, EvidenceBaseStudy } from "./types";

/** Studies behind a practice that contribute at least one corpus passage. */
export function studiesInCorpus(entry: EvidenceBaseEntry): number {
  const counts = entry.corpus_status ?? {};
  return (counts.full_text ?? 0) + (counts.abstract ?? 0);
}

/** Practice → entry pairs in a stable display order (most-evidenced first). */
export function evidenceBaseEntries(
  base?: Record<string, EvidenceBaseEntry>
): [string, EvidenceBaseEntry][] {
  return Object.entries(base ?? {}).sort(
    (a, b) => b[1].n_studies - a[1].n_studies || a[0].localeCompare(b[0])
  );
}

/** One tooltip line per study: provenance plus how retrievable it is. */
export function studyLine(study: EvidenceBaseStudy): string {
  // The year attaches to the title without a separator: "… erosion (2019)".
  const head =
    [study.era_code, study.title ?? "Untitled study"].filter(Boolean).join(" · ") +
    (study.year != null ? ` (${study.year})` : "");
  const suffix =
    study.corpus_status === "full_text"
      ? "full text"
      : study.corpus_status === "abstract"
        ? "abstract only"
        : "not in the corpus";
  return `${head} — ${suffix}`;
}

/** The whole study list as a tooltip, or undefined when there is none. */
export function studiesTooltip(entry: EvidenceBaseEntry): string | undefined {
  const lines = (entry.studies ?? []).map(studyLine);
  return lines.length > 0 ? lines.join("\n") : undefined;
}

/** The same sentence the backend puts in the prompt and the fallback text. */
export function evidenceBaseSentence(
  practice: string,
  entry: EvidenceBaseEntry
): string {
  const studies = `${entry.n_studies} ${entry.n_studies === 1 ? "study" : "studies"}`;
  const obs = `${entry.n_obs} field ${
    entry.n_obs === 1 ? "observation" : "observations"
  }`;
  const belts =
    entry.aez_belts?.length > 0 ? ` in ${entry.aez_belts.join(", ")}` : "";
  const inCorpus = studiesInCorpus(entry);
  const corpus = `; ${inCorpus} of the studies ${
    inCorpus === 1 ? "is" : "are"
  } in the retrievable corpus`;
  return `${practice}: backed by ${studies} / ${obs}${belts}${corpus}.`;
}
