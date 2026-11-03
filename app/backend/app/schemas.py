"""Pydantic v2 request/response schemas for the new lat/long contract."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.services import recommender_service as svc

# Enum literals sourced from the canonical engine.
PracticeFamily = Literal[
    "Crop production and management",
    "Livestock production and management",
    "Integrated soil fertility management",
    "Erosion control and water management",
    "Agro-forestry and forest management",
]
Indicator = Literal[
    "yield",
    "biomass yield",
    "income",
    "water use efficiency",
    "SOM content",
    "soil loss",
    "runoff",
]
Confidence = Literal["high", "medium", "low"]


# --------------------------------------------------------------------- requests
class RecommendRequest(BaseModel):
    lat: float = Field(..., description="Latitude within Ethiopia (3.3–14.9).")
    lon: float = Field(..., description="Longitude within Ethiopia (32.9–48.2).")
    practice_family: PracticeFamily
    indicator: Indicator
    crop_type: str | None = Field(default=None, max_length=200)
    top_n: int = Field(default=1, ge=1, le=10)

    @field_validator("crop_type")
    @classmethod
    def _blank_crop_is_none(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        return v or None

    @model_validator(mode="after")
    def _check_bounds(self) -> "RecommendRequest":
        lat_lo, lat_hi = svc.LAT_BOUNDS
        lon_lo, lon_hi = svc.LON_BOUNDS
        if not (lat_lo <= self.lat <= lat_hi):
            raise ValueError(
                f"lat {self.lat} is outside Ethiopia ({lat_lo}–{lat_hi})."
            )
        if not (lon_lo <= self.lon <= lon_hi):
            raise ValueError(
                f"lon {self.lon} is outside Ethiopia ({lon_lo}–{lon_hi})."
            )
        return self


class ExplainRequest(BaseModel):
    """Grounded explanation of a recommendation the engine already produced."""

    recommendation: dict[str, Any] = Field(
        ..., description="The two-tier /recommend payload (query/recommendations/details)."
    )
    question: str | None = Field(default=None, max_length=2000)
    k: int = Field(default=8, ge=1, le=20, description="Evidence chunks to retrieve.")
    #: UI language (U1). Selects the catalog for deterministic texts and adds a
    #: "Reply in …" line to the LLM prompt; numbers and the data contract stay English.
    language: Literal["en", "am", "om"] = "en"

    @field_validator("question")
    @classmethod
    def _blank_question_is_none(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        return v or None


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str


class ChatSlotsHint(BaseModel):
    """Structured values behind a quick-reply chip (U2, additive).

    The chat shows the chip's sentence in the UI language; the backend reads the
    canonical data-contract values from here instead of parsing translated text.
    """

    practice_family: PracticeFamily | None = None
    indicator: Indicator | None = None
    lat: float | None = None
    lon: float | None = None
    crop_type: str | None = Field(default=None, max_length=200)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    history: list[ChatMessage] = Field(default_factory=list)
    stream: bool = True
    top_n: int = Field(default=1, ge=1, le=10)
    # Most recent two-tier recommendation so follow-ups (why / thanks / how)
    # can reuse details without the LLM re-calling the tool.
    last_recommendation: dict[str, Any] | None = None
    #: UI language (U1) — see ExplainRequest.language.
    language: Literal["en", "am", "om"] = "en"
    # U2: structured slots behind a quick-reply chip (optional, additive).
    hint: ChatSlotsHint | None = None

    @field_validator("history")
    @classmethod
    def cap_history(cls, v: list[ChatMessage]) -> list[ChatMessage]:
        return v[-20:]


# -------------------------------------------------------------------- responses
class RecommendationItem(BaseModel):
    """Clean, short — the only thing shown by default in the UI."""

    practice: str
    effect: str


class RankedItem(BaseModel):
    practice: str
    pct_change: float
    log_ratio: float
    n_evidence: int


class RecommendQuery(BaseModel):
    lat: float
    lon: float
    practice_family: str
    indicator: str
    crop_type: str | None = None
    goal_direction: str


class RecommendDetails(BaseModel):
    """Revealed only when the user asks 'why / explain'."""

    context: dict[str, Any]
    crop_group: str | None = None
    confidence: Confidence
    ranked: list[RankedItem]
    n_candidates: int
    n_grounded: int | None = None
    ranking_scope: str | None = None
    note: str


class RecommendResponse(BaseModel):
    query: RecommendQuery
    recommendations: list[RecommendationItem]
    details: RecommendDetails


# ---------------------------------------------------------------- advisory (P9)
class AdviseRequest(RecommendRequest):
    """The /recommend request plus the UI language (for localised rationales)."""

    top_n: int = Field(default=3, ge=1, le=10)
    language: Literal["en", "am", "om"] = "en"


class ModeReason(BaseModel):
    """Why the advisory is in its mode — a catalog key plus parameters, never prose."""

    key: str
    params: dict[str, Any] = Field(default_factory=dict)


class CandidateEvidence(BaseModel):
    """Counts behind one ranked practice relative to the user's belt (counts only)."""

    practice: str
    n_studies: int
    n_obs: int
    n_obs_in_belt: int
    n_obs_in_zone: int
    aez_belts: list[str] = Field(default_factory=list)
    corpus_status: dict[str, int] = Field(default_factory=dict)
    belt_counts_exact: bool = True
    in_top3: bool = False


class EvidenceSufficiency(BaseModel):
    user_belt: str | None = None
    user_zone: str | None = None
    thresholds: dict[str, int] = Field(default_factory=dict)
    candidates: list[CandidateEvidence] = Field(default_factory=list)
    graph_available: bool = True


class KnowledgeCitation(BaseModel):
    """Provenance of one source behind a knowledge candidate (no effect numbers)."""

    tier: str = "guidance"
    ref: str | None = None
    era_code: str | None = None
    # Dataset study id for evidence rows that are not in the ERA corpus (P9).
    study_no: str | int | None = None
    title: str | None = None
    year: int | None = None
    doi: str | None = None
    url: str | None = None
    snippet: str | None = None
    indicator: str | None = None
    practice: str | None = None
    wocat_id: str | int | None = None
    country: str | None = None
    licence: str | None = None
    chunk_id: str | None = None
    # U9 (C2/C3): full reference for a dataset study, and the original link of a guidance PDF.
    reference: str | None = None
    reference_truncated: bool | None = None
    compilation: bool | None = None
    source_url: str | None = None


class CandidateSupport(BaseModel):
    n_sources: int
    n_documents: int
    n_guidance_documents: int = 0
    n_studies: int = 0
    n_passages: int = 0
    other_objectives: dict[str, int] = Field(default_factory=dict)


class KnowledgeCandidate(BaseModel):
    """A documented practice proposed with provenance — never with an effect."""

    key: str
    component: str | None = None
    label: str
    practices: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    support: CandidateSupport
    record: dict[str, Any] | None = None
    citations: list[KnowledgeCitation] = Field(default_factory=list)
    rationale: dict[str, Any] = Field(default_factory=dict)
    rationale_text: str


class NumberValue(BaseModel):
    """A number on the wire with its provenance (U9, decision §5)."""

    value: float
    unit: str | None = None
    source: Literal["model", "study", "passage", "context", "count"]
    ref: str | None = None
    #: The value as shown (shared rounding rule, ``app/services/numbers.py``).
    display: str


class Headline(NumberValue):
    """The headline effect of a practice; a range when model and studies disagree."""

    range: list[NumberValue] | None = None


class ModelEvidence(NumberValue):
    confidence: str
    n_obs: int
    n_studies: int
    n_obs_in_zone: int
    se_log: float


class StudyLead(NumberValue):
    """The leading study evidence: median of the best-matched studies' effects."""

    refs: list[str]
    match: str
    n_studies: int
    n_obs: int
    log: float
    se_log: float


class StudyEvidence(BaseModel):
    """One study's measured effect for this practice and objective (dataset rows, never an LLM)."""

    ref: str
    study_no: str
    era_code: str | None = None
    title: str | None = None
    year: int | str | None = None
    doi: str | None = None
    data_source: str | None = None
    n_obs: int
    mean_log_rr: float
    se_log: float
    effect: NumberValue
    share_positive: float | None = None
    aez_belts: list[str] = Field(default_factory=list)
    obs_by_belt: dict[str, int] = Field(default_factory=dict)
    match: str


class PracticeEvidence(BaseModel):
    """The evidence bundle of one shown practice (U9, docs/decisions/evidence_fusion.md)."""

    practice: str
    lead_source: Literal["model", "study", "documented"]
    match: str
    headline: Headline
    disagreement: bool = False
    caution: bool = False
    model: ModelEvidence
    study: StudyLead | None = None
    studies: list[StudyEvidence] = Field(default_factory=list)
    conservative_bound: float
    matches_constraints: list[str] = Field(default_factory=list)
    replaces_crop: bool = False
    constraint_pick: bool = False


class AdviseResponse(BaseModel):
    mode: Literal["model-led", "hybrid", "knowledge-led"]
    reasons: list[ModeReason] = Field(default_factory=list)
    #: The engine's /recommend payload — items unchanged, restricted to the shown
    #: practices in the fused order (U9) — or null when the engine cannot rank.
    model: RecommendResponse | None = None
    #: U9: one evidence bundle per shown practice, in display order.
    practices: list[PracticeEvidence] = Field(default_factory=list)
    #: U9: "conservative" | "model" (ADVISORY_ORDERING) and the fusion knobs.
    ordering: str = "conservative"
    fusion: dict[str, Any] = Field(default_factory=dict)
    #: U9 (A6): soil constraints the request carried ("acidic_soil", ...).
    constraints: list[str] = Field(default_factory=list)
    knowledge_candidates: list[KnowledgeCandidate] = Field(default_factory=list)
    evidence_sufficiency: EvidenceSufficiency
    #: Resolved context (also when there is no model payload).
    context: dict[str, Any] = Field(default_factory=dict)
    language: Literal["en", "am", "om"] = "en"


class ContextResponse(BaseModel):
    lat: float
    lon: float
    aez_belt: str | None = None
    context: dict[str, Any]


class IndicatorMeta(BaseModel):
    key: str
    label: str
    direction: Literal["increase", "reduce"]


class BoundsMeta(BaseModel):
    lat: list[float]
    lon: list[float]


class ModelMeta(BaseModel):
    name: str
    cv_r2: float | None = None
    note: str


class EvidenceCounts(BaseModel):
    """Size of the field-evidence base behind the model — counts only (U1)."""

    n_observations: int
    n_studies: int
    n_practices: int
    n_belts: int
    #: belts in the agro-ecological belt system (from the AEZ lookup), not only
    #: those with observations — the figure the home page shows.
    n_belts_total: int
    n_crop_types: int


class NearestPlaceResponse(BaseModel):
    """GET /geocode/nearest — the gazetteer town a pin is in or near (U9, D10)."""

    found: bool
    name: str | None = None
    distance_km: float | None = None


class GeocodeResponse(BaseModel):
    """GET /geocode — an Ethiopian place name resolved by the offline gazetteer (U1)."""

    query: str
    found: bool
    name: str | None = None
    lat: float | None = None
    lon: float | None = None
    source: str | None = None


class MetadataResponse(BaseModel):
    practice_families: list[str]
    indicators: list[IndicatorMeta]
    indicators_by_family: dict[str, list[str]]
    practices_by_family: dict[str, list[str]]
    crop_types: list[str]
    # Additive: crop types with field observations per practice family.
    crop_types_by_family: dict[str, list[str]] = {}
    bounds: BoundsMeta
    model: ModelMeta
    rag_ready: bool
    #: True when rag/graph/store/graph.json exists — gates the evidence-base
    #: line in the UI's Evidence panel.
    graph_ready: bool = False
    #: True when server-side voice (POST /speech/transcribe, /speech/synthesize) is configured (U6).
    speech_ready: bool = False
    #: U9: evidence-fusion settings (ordering, k, disagreement and caution thresholds).
    fusion: dict[str, Any] = Field(default_factory=dict)
    #: UI languages the API can answer in (U1): en, am, om.
    languages: list[str] = Field(default_factory=lambda: ["en", "am", "om"])
    # Additive (U1): headline evidence counts for the UI trust strip.
    evidence: EvidenceCounts | None = None
    # Additive (P9): the evidence-tiered advisory's thresholds and sources.
    advisory: dict[str, Any] | None = None


class ExplainCitation(BaseModel):
    """Provenance of one cited source.

    Tier "evidence" (default): an ERA study — era_code links to training
    rows. Tier "guidance": a GARDIAN implementation-guidance document
    (era_code is None, url links to the source). Deduped per study/document:
    retrieval may surface several chunks of the same source; ``n_passages``
    says how many, ``snippet`` comes from the highest-ranked one.
    """

    era_code: str | None = None
    tier: str = "evidence"
    url: str | None = None
    doi: str | None = None
    title: str | None = None
    year: int | None = None
    journal: str | None = None
    # U9 (C2/C3): full reference for a dataset study, and the original link of a guidance PDF.
    reference: str | None = None
    reference_truncated: bool | None = None
    compilation: bool | None = None
    source_url: str | None = None
    practice: str | None = None
    snippet: str
    #: Retrieved passages from this source; 0 for a study cited for its measured
    #: effect only (U9 evidence fusion: no passage retrieved).
    n_passages: int = Field(default=1, ge=0)
    #: P9: the marker this source carries in the explanation — "3", "G1", "W2".
    ref: str | None = None
    #: U9: dataset study id ("ERA_123", "CSA_18") and data source, for study-effect citations.
    study_no: str | None = None
    data_source: str | None = None


class EvidenceBaseStudy(BaseModel):
    """One study behind a practice — provenance only, no effect numbers."""

    era_code: str | None = None
    title: str | None = None
    year: int | None = None
    doi: str | None = None
    corpus_status: str | None = None


class EvidenceBaseEntry(BaseModel):
    """How much field evidence stands behind one recommended practice.

    Counts and provenance ONLY. Effect magnitudes stay with the model
    (CLAUDE.md doctrine 1): the knowledge graph's ``mean_log_rr`` /
    ``median_log_rr`` aggregates are deliberately not exposed here, because a
    dataset-wide aggregate can contradict the model's prediction for the
    user's specific pin.
    """

    n_studies: int
    n_obs: int
    aez_belts: list[str] = Field(default_factory=list)
    crop_groups: list[str] = Field(default_factory=list)
    #: counts keyed by full_text / abstract / none
    corpus_status: dict[str, int] = Field(default_factory=dict)
    studies: list[EvidenceBaseStudy] = Field(default_factory=list)


class ExplainResponse(BaseModel):
    #: The evidence register: labelled and cited; every number passed guard v2.
    explanation: str
    #: The plain register: one plain-language sentence per practice, no markers (U9).
    summary: str = ""
    #: Provenance of every number in ``explanation`` (U9).
    numbers: list[NumberValue] = Field(default_factory=list)
    #: Sentences guard v2 removed for an unsourced number (U9).
    removed_sentences: int = 0
    #: Synthesised implementation steps per practice, each cited [Gn] and guarded (U9, C1).
    howto: dict[str, list[str]] = Field(default_factory=dict)
    citations: list[ExplainCitation]
    grounded: bool
    llm_used: bool
    #: practice -> evidence base; empty when the knowledge graph is not built.
    evidence_base: dict[str, EvidenceBaseEntry] = Field(default_factory=dict)


class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    version: str


class ModelListItem(BaseModel):
    key: str
    label: str
    description: str
    features: list[str]


# ------------------------------------------------------------------- error env
class ErrorDetail(BaseModel):
    code: str
    message: str
    details: Any = None


class ErrorEnvelope(BaseModel):
    error: ErrorDetail
