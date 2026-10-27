/** Presentation helpers for the Tier-1 evidence base (Phase P6b-i, localised in U1).
 *
 * The backend's /explain response carries, per recommended practice, how many
 * studies and field observations stand behind it and where they were
 * measured. These helpers turn that into display strings using the message
 * catalog (ICU plurals), so the English sentence stays word-for-word identical
 * to the backend's own and the other languages come from the same keys.
 *
 * Counts and provenance ONLY. Effect magnitudes belong to the model: the
 * knowledge graph's dataset aggregates are deliberately absent from the API
 * payload, and nothing here invents one.
 */
import type { EvidenceBaseEntry, EvidenceBaseStudy } from "./types";

/** `useTranslations("evidence.evidenceBase")` or a `createTranslator` equivalent. */
export type EvidenceBaseTranslator = (
  key: "sentence" | "studies" | "observations" | "inBelts" | "verb",
  values?: Record<string, string | number>
) => string;

/** Labels for the per-study tooltip lines (from `evidence.*`). */
export interface StudyLabels {
  untitled: string;
  fullText: string;
  abstractOnly: string;
  notInCorpus: string;
}

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
export function studyLine(study: EvidenceBaseStudy, labels: StudyLabels): string {
  // The year attaches to the title without a separator: "… erosion (2019)".
  const head =
    [study.era_code, study.title ?? labels.untitled].filter(Boolean).join(" · ") +
    (study.year != null ? ` (${study.year})` : "");
  const suffix =
    study.corpus_status === "full_text"
      ? labels.fullText
      : study.corpus_status === "abstract"
        ? labels.abstractOnly
        : labels.notInCorpus;
  return `${head} — ${suffix}`;
}

/** The whole study list as a tooltip, or undefined when there is none. */
export function studiesTooltip(entry: EvidenceBaseEntry, labels: StudyLabels): string | undefined {
  const lines = (entry.studies ?? []).map((s) => studyLine(s, labels));
  return lines.length > 0 ? lines.join("\n") : undefined;
}

/** The same sentence the backend puts in the prompt and the fallback text.
 *
 * @param nameOf localises the practice / belt names (identity for English).
 */
export function evidenceBaseSentence(
  practice: string,
  entry: EvidenceBaseEntry,
  t: EvidenceBaseTranslator,
  nameOf: { practice?: (p: string) => string; belt?: (b: string) => string } = {}
): string {
  const inCorpus = studiesInCorpus(entry);
  const belts =
    entry.aez_belts?.length > 0
      ? t("inBelts", { belts: entry.aez_belts.map(nameOf.belt ?? ((b) => b)).join(", ") })
      : "";
  return t("sentence", {
    practice: (nameOf.practice ?? ((p) => p))(practice),
    studies: t("studies", { n: entry.n_studies }),
    observations: t("observations", { n: entry.n_obs }),
    belts,
    inCorpus,
    verb: t("verb", { n: inCorpus }),
  });
}
