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

/** One cited study behind an explanation (deduped per era_code). */
export interface ExplainCitation {
  era_code: string | null;
  doi: string | null;
  title: string | null;
  year: number | null;
  journal: string | null;
  practice: string | null;
  snippet: string;
  /** How many retrieved passages this study contributed. */
  n_passages: number;
}

export interface ExplainResponse {
  explanation: string;
  citations: ExplainCitation[];
  grounded: boolean;
  llm_used: boolean;
}

export interface ExplainRequestPayload {
  recommendation: RecommendResponse;
  question?: string | null;
  k?: number;
}

export interface ChatRequestPayload {
  message: string;
  history: ChatMessage[];
  last_recommendation?: RecommendResponse | null;
  stream?: boolean;
  top_n?: number;
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
}

export interface ChatStreamEvent {
  type: "recommendation" | "token" | "done" | "error" | "slots";
  text?: string;
  data?: RecommendResponse | ChatSlotsEvent;
  message?: string;
}
