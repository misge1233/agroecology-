/**
 * One citation registry per page / answer (U9, B4).
 *
 * The explanation, the documented practices and the print sheet each come
 * with their own per-response numbering from the backend, so `[G1]` could mean
 * two different documents on one page. The registry assigns ONE visible label
 * per source, keyed by the source's identity (ERA code, dataset study id, URL,
 * WOCAT id, DOI, title — the backend's `citation_identity` order), numbered per
 * tier: studies `1, 2, …`, guidance `G1, G2, …`, practice records `W1, W2, …`.
 * Sources registered first keep their label as more arrive (stable keys).
 */
export type CitationTier = "evidence" | "guidance" | "practice";

export interface Citable {
  tier?: CitationTier | string | null;
  ref?: string | null;
  era_code?: string | null;
  study_no?: string | number | null;
  url?: string | null;
  wocat_id?: string | number | null;
  doi?: string | null;
  title?: string | null;
}

const PREFIX: Record<CitationTier, string> = { evidence: "", guidance: "G", practice: "W" };

function tierOf(c: Citable): CitationTier {
  return c.tier === "guidance" || c.tier === "practice" ? c.tier : "evidence";
}

/** What makes a source the same source across lists (mirrors the backend). */
export function citationIdentity(c: Citable): string | null {
  for (const key of ["era_code", "study_no", "url", "wocat_id", "doi", "title"] as const) {
    const v = c[key];
    if (v != null && String(v).trim() !== "") return `${tierOf(c)}|${key}:${String(v).trim()}`;
  }
  return null;
}

/**
 * One entry per source, first occurrence kept (order preserved). Two rows can
 * be the same source, e.g. two PDFs of one CGSpace item that share its handle
 * page; a list shows it once. Rows without an identity are kept as they are.
 */
export function uniqueSources<T extends Citable>(list: T[]): T[] {
  const seen = new Set<string>();
  return list.filter((c) => {
    const id = citationIdentity(c);
    if (id == null) return true;
    if (seen.has(id)) return false;
    seen.add(id);
    return true;
  });
}

/** A stable React key for a source in a list (its identity, else its position). */
export function sourceKey(c: Citable, index: number): string {
  return citationIdentity(c) ?? `row-${index}`;
}

export class CitationRegistry {
  private labels = new Map<string, string>();
  private counters: Record<CitationTier, number> = { evidence: 0, guidance: 0, practice: 0 };

  /** Register (or look up) a source; returns its visible label, or null when it has no identity. */
  register(c: Citable): string | null {
    const id = citationIdentity(c);
    if (!id) return null;
    const known = this.labels.get(id);
    if (known) return known;
    const tier = tierOf(c);
    this.counters[tier] += 1;
    const label = `${PREFIX[tier]}${this.counters[tier]}`;
    this.labels.set(id, label);
    return label;
  }

  label(c: Citable): string | null {
    const id = citationIdentity(c);
    return id ? (this.labels.get(id) ?? null) : null;
  }

  get size(): number {
    return this.labels.size;
  }
}

/** Build a registry from lists in priority order (first list keeps the lowest numbers). */
export function buildRegistry(...lists: Citable[][]): CitationRegistry {
  const reg = new CitationRegistry();
  for (const list of lists) for (const c of list) reg.register(c);
  return reg;
}

const MARKER = /\[([GW]?\d+)[a-z]?\]/g;

/**
 * Rewrite the markers of one response (`[3]`, `[G1]`, `[1a]`) to the page's
 * registry labels, using that response's own citation list (`ref` → source).
 * A marker whose source is unknown is left as written.
 */
export function relabelMarkers(text: string, citations: Citable[], registry: CitationRegistry): string {
  const byRef = new Map<string, Citable>();
  for (const c of citations) if (c.ref) byRef.set(String(c.ref), c);
  return text.replace(MARKER, (whole, ref: string) => {
    const c = byRef.get(ref);
    const label = c ? (registry.label(c) ?? registry.register(c)) : null;
    return label ? `[${label}]` : whole;
  });
}
