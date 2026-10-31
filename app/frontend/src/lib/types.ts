/** Shared API types matching the FastAPI schemas (AgroAdvisor-ET contract). */

export type Direction = "increase" | "reduce";
export type Confidence = "high" | "medium" | "low";

export interface IndicatorMeta {
  key: string;
  label: string;
  direction: Direction;
}

export interface ModelMeta {
  name: string;
  cv_r2?: number | null;
  note: string;
}

export interface Bounds {
  lat: [number, number];
  lon: [number, number];
}

export interface Metadata {
  practice_families: string[];
  indicators: IndicatorMeta[];
  /** Indicator keys with evidence for each practice family (model-derived). */
  indicators_by_family?: Record<string, string[]>;
  /** Practice names eligible for ranking within each practice_family. */
  practices_by_family?: Record<string, string[]>;
  crop_types: string[];
  bounds: Bounds;
  model: ModelMeta;
  /** True when the RAG index is built — gates the Evidence panel. */
  rag_ready?: boolean;
  /** True when the knowledge graph is built — gates the evidence-base line. */
  graph_ready?: boolean;
  /** Server voice is configured (U6); actual model access comes from GET /speech/status. */
  speech_ready?: boolean;
  /** Languages the API answers in (U1, additive). */
  languages?: string[];
  /** Evidence-base counts for the trust strip (U1, additive). */
  evidence?: EvidenceCounts | null;
}

/** The clean, default-view item (practice + one-line effect). */
export interface RecommendationItem {
  practice: string;
  effect: string;
}

/** Detail-view rows (shown only on "Why this?"). */
export interface RankedItem {
  practice: string;
  pct_change: number;
  log_ratio: number;
  n_evidence: number;
}

export interface RecommendQuery {
  lat: number;
  lon: number;
  practice_family: string;
  indicator: string;
  crop_type?: string | null;
  goal_direction: string;
}

export interface RecommendDetails {
  context: Record<string, number | string | null>;
  crop_group: string | null;
  confidence: Confidence;
  ranked: RankedItem[];
  n_candidates: number;
  n_grounded?: number;
  ranking_scope?: string;
  note: string;
}

export interface RecommendResponse {
  query: RecommendQuery;
  recommendations: RecommendationItem[];
  details: RecommendDetails;
}

export interface RecommendRequest {
  lat: number;
  lon: number;
  practice_family: string;
  indicator: string;
  crop_type?: string | null;
  top_n?: number;
}

/** One cited source behind an explanation (deduped per study/document).
 * tier "evidence" = ERA study (era_code links to training rows);
 * tier "guidance" = GARDIAN implementation-guidance document (url links out).
 */
export interface ExplainCitation {
  era_code: string | null;
  /** Defaults to "evidence" on the backend; optional for old payloads. */
  tier?: "evidence" | "guidance" | "practice";
  /** P9: the marker this source carries in the explanation — "3", "G1", "W2". */
  ref?: string | null;
  /** Source link for guidance documents (null for most ERA studies). */
  url?: string | null;
  doi: string | null;
  title: string | null;
  year: number | null;
  journal: string | null;
  practice: string | null;
  snippet: string;
  /** How many retrieved passages this study contributed. */
  n_passages: number;
}

/** One study behind a practice — provenance only, never an effect size. */
export interface EvidenceBaseStudy {
  era_code: string | null;
  title: string | null;
  year: number | null;
  doi: string | null;
  /** "full_text" | "abstract" | "none" — how much of it is retrievable. */
  corpus_status: string | null;
}

/** How much field evidence stands behind one recommended practice.
 *
 * Counts and provenance ONLY. Effect magnitudes stay with the model: the
 * knowledge graph's dataset aggregates are deliberately not exposed, because
 * a dataset-wide average can contradict the model's prediction for this pin.
 */
export interface EvidenceBaseEntry {
  n_studies: number;
  n_obs: number;
  aez_belts: string[];
  crop_groups: string[];
  /** counts keyed by full_text / abstract / none */
  corpus_status: Record<string, number>;
  studies: EvidenceBaseStudy[];
}

export interface ExplainResponse {
  explanation: string;
  citations: ExplainCitation[];
  grounded: boolean;
  llm_used: boolean;
  /** practice -> evidence base; empty when the knowledge graph is not built. */
  evidence_base?: Record<string, EvidenceBaseEntry>;
}

export interface ExplainRequestPayload {
  recommendation: RecommendResponse;
  question?: string | null;
  k?: number;
  language?: ApiLanguage;
}

/** Structured values behind a quick-reply chip (U2, additive on ChatRequest). */
export interface ChatSlotsHint {
  practice_family?: string | null;
  indicator?: string | null;
  lat?: number | null;
  lon?: number | null;
  crop_type?: string | null;
}

export interface ChatRequestPayload {
  message: string;
  history: ChatMessage[];
  last_recommendation?: RecommendResponse | null;
  stream?: boolean;
  top_n?: number;
  language?: ApiLanguage;
  hint?: ChatSlotsHint | null;
}

export interface ContextResponse {
  lat: number;
  lon: number;
  aez_belt: string | null;
  context: Record<string, number | string | null>;
}

export interface ChatMessage {
  role: "user" | "assistant" | "system";
  content: string;
}

export interface ChatSlotsEvent {
  practice_family?: string | null;
  indicator?: string | null;
  lat?: number | null;
  lon?: number | null;
  place_name?: string | null;
  crop_type?: string | null;
  missing?: string[];
  inferred?: string[];
  confidence?: Record<string, string>;
  is_followup?: boolean;
  wants_advice?: boolean;
  geocode_source?: string | null;
  /** "rules" | "protocol" | "hint" | "llm" — where the decisive values came from (U2). */
  source?: string | null;
  llm_used?: boolean;
}

export interface ChatStreamEvent {
  type: "recommendation" | "token" | "done" | "error" | "slots" | "advisory";
  text?: string;
  data?: RecommendResponse | ChatSlotsEvent | AdvisoryEvent;
  message?: string;
}

// ------------------------------------------------------------ advisory (P9)
export type AdvisoryMode = "model-led" | "hybrid" | "knowledge-led";

/** Why the advisory is in its mode: a catalog key + params, rendered by the UI. */
export interface ModeReason {
  key: string;
  params: Record<string, string | number>;
}

export interface CandidateEvidence {
  practice: string;
  n_studies: number;
  n_obs: number;
  n_obs_in_belt: number;
  n_obs_in_zone: number;
  aez_belts: string[];
  corpus_status: Record<string, number>;
  belt_counts_exact: boolean;
  in_top3: boolean;
}

export interface EvidenceSufficiency {
  user_belt: string | null;
  user_zone: string | null;
  thresholds: Record<string, number>;
  candidates: CandidateEvidence[];
  graph_available: boolean;
}

export interface KnowledgeCitation {
  tier: "evidence" | "guidance" | "practice";
  ref?: string | null;
  era_code?: string | null;
  /** Dataset study id when the study is not in the ERA corpus (no code, no title). */
  study_no?: string | number | null;
  title?: string | null;
  year?: number | null;
  doi?: string | null;
  url?: string | null;
  snippet?: string | null;
  indicator?: string | null;
  practice?: string | null;
  wocat_id?: string | number | null;
  country?: string | null;
  licence?: string | null;
}

export type KnowledgeSource = "evidence_other_objectives" | "documented_in_guidance" | "documented_practice_record";

/** A documented practice proposed with provenance — never with an effect number. */
export interface KnowledgeCandidate {
  key: string;
  component: string | null;
  label: string;
  practices: string[];
  sources: KnowledgeSource[];
  support: {
    n_sources: number;
    n_documents: number;
    n_guidance_documents: number;
    n_studies: number;
    n_passages: number;
    other_objectives: Record<string, number>;
  };
  record?: { wocat_id?: string | number; country?: string | null; shared_context?: string[] } | null;
  citations: KnowledgeCitation[];
  rationale: { key: string; params: Record<string, string | number> };
  rationale_text: string;
}

/** The parts of an advisory that are not the model payload (chat SSE `advisory` event). */
export interface AdvisoryEvent {
  mode: AdvisoryMode;
  reasons: ModeReason[];
  knowledge_candidates: KnowledgeCandidate[];
  evidence_sufficiency: EvidenceSufficiency;
  context: Record<string, number | string | null>;
  /** Chat only: the resolved slots, so a knowledge-led turn can deep-link to the Advisor. */
  query?: Omit<RecommendQuery, "goal_direction"> | null;
}

/** POST /advise */
export interface AdviseResponse extends AdvisoryEvent {
  /** The unchanged /recommend payload, or null in knowledge-led mode. */
  model: RecommendResponse | null;
  language: ApiLanguage;
}

/** Headline size of the evidence base — counts only, never an effect (U1). */
export interface EvidenceCounts {
  n_observations: number;
  n_studies: number;
  n_practices: number;
  n_belts: number;
  n_crop_types: number;
}

/** UI languages the API can answer in (U1). */
export type ApiLanguage = "en" | "am" | "om";

/** GET /geocode — a place name resolved by the offline gazetteer (U1). */
export interface GeocodeResponse {
  query: string;
  found: boolean;
  name: string | null;
  lat: number | null;
  lon: number | null;
  source: string | null;
}
