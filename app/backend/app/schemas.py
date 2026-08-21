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


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    history: list[ChatMessage] = Field(default_factory=list)
    stream: bool = True
    top_n: int = Field(default=1, ge=1, le=10)
    # Most recent two-tier recommendation so follow-ups (why / thanks / how)
    # can reuse details without the LLM re-calling the tool.
    last_recommendation: dict[str, Any] | None = None

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


class MetadataResponse(BaseModel):
    practice_families: list[str]
    indicators: list[IndicatorMeta]
    indicators_by_family: dict[str, list[str]]
    practices_by_family: dict[str, list[str]]
    crop_types: list[str]
    bounds: BoundsMeta
    model: ModelMeta
    rag_ready: bool


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
    practice: str | None = None
    snippet: str
    n_passages: int = Field(default=1, ge=1)


class ExplainResponse(BaseModel):
    explanation: str
    citations: list[ExplainCitation]
    grounded: bool
    llm_used: bool


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
