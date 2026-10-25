"""Normalized WOCAT record shapes (pydantic v2).

One model per WOCAT record type:

* :class:`WocatTechnology` — a documented SLM Technology (QT 2019);
* :class:`WocatApproach`   — the Approach a Technology is implemented under.

The models are deliberately strict about the controlled vocabularies and
permissive about everything else: SLM groups, SLM measure codes, degradation
codes, context classes and impact-variable names are normalized against
``rag.graph.wocat_taxonomy`` and **dropped with a warning** if they are not
members of the questionnaire's vocabulary, while free text, costs and
activities pass through as given. That way a malformed export degrades to a
smaller valid record instead of poisoning the graph with invented codes.

Every record carries its provenance and licence. WOCAT data are
**CC BY-NC-SA 4.0**: attribution to WOCAT and the named compiler, a link to
the original record, and share-alike on anything derived from it.
"""
from __future__ import annotations

import logging
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from rag.graph import wocat_taxonomy as wt
from rag.graph.schema import CONTEXT_CLASS_KINDS

logger = logging.getLogger(__name__)

DEFAULT_LICENCE = "CC BY-NC-SA 4.0"

#: Where a record came from; mirrors the graph's edge provenance values.
Provenance = Literal["wocat_fixture", "wocat_export"]


class Activity(BaseModel):
    """One establishment or maintenance activity (QT §4.3 / §4.5)."""

    model_config = ConfigDict(extra="allow")

    description: str
    timing: str | None = None
    phase: Literal["establishment", "maintenance"] = "establishment"


class Costs(BaseModel):
    """Inputs and costs (QT §4.2, §4.4, §4.6)."""

    model_config = ConfigDict(extra="allow")

    currency: str | None = None
    usd_exchange_rate: float | None = None
    area_unit: str | None = None
    per_hectare: bool | None = None
    establishment_total: float | None = None
    maintenance_total: float | None = None
    comments: str | None = None


class CostBenefit(BaseModel):
    """Benefits vs costs, short and long term (QT §6.4)."""

    model_config = ConfigDict(extra="allow")

    establishment_short_term: str | None = None
    establishment_long_term: str | None = None
    maintenance_short_term: str | None = None
    maintenance_long_term: str | None = None

    @field_validator(
        "establishment_short_term", "establishment_long_term",
        "maintenance_short_term", "maintenance_long_term", mode="before",
    )
    @classmethod
    def _known_class(cls, value: Any) -> Any:
        if value in (None, ""):
            return None
        text = str(value).strip().lower()
        if text not in wt.COST_BENEFIT_CLASSES:
            logger.warning("unknown QT §6.4 cost-benefit class %r — dropped", value)
            return None
        return text


class Adoption(BaseModel):
    """Adoption and spontaneous adoption bands (QT §6.5)."""

    model_config = ConfigDict(extra="allow")

    share_of_land_users: str | None = None
    share_spontaneous: str | None = None
    comments: str | None = None

    @field_validator("share_of_land_users", mode="before")
    @classmethod
    def _adoption(cls, value: Any) -> Any:
        if value in (None, ""):
            return None
        band = wt.normalize_adoption_band(str(value))
        if band is None:
            logger.warning("unknown QT §6.5 adoption band %r — dropped", value)
        return band

    @field_validator("share_spontaneous", mode="before")
    @classmethod
    def _spontaneous(cls, value: Any) -> Any:
        if value in (None, ""):
            return None
        band = wt.normalize_spontaneous_band(str(value))
        if band is None:
            logger.warning("unknown QT §6.5 spontaneous band %r — dropped", value)
        return band


class Reference(BaseModel):
    """A publication or link the record cites (QT §7.2 / §7.3)."""

    model_config = ConfigDict(extra="allow")

    title: str
    url: str | None = None


class WocatRecord(BaseModel):
    """Fields shared by Technologies and Approaches."""

    model_config = ConfigDict(extra="allow")

    wocat_id: str
    record_type: Literal["technology", "approach"]
    title: str
    country: str | None = None
    region: str | None = None
    url: str | None = None
    compiler: str | None = None
    licence: str = DEFAULT_LICENCE
    provenance: Provenance = "wocat_export"
    short_description: str | None = None
    #: True only for records that are NOT real WOCAT data — test scaffolding.
    #: Synthetic records must never be cited in user-facing output.
    synthetic: bool = False

    @field_validator("wocat_id", mode="before")
    @classmethod
    def _as_str(cls, value: Any) -> str:
        return str(value).strip()


class WocatApproach(WocatRecord):
    """A documented SLM Approach."""

    record_type: Literal["approach"] = "approach"
    aims: str | None = None
    approach_type: str | None = None
    year_initiated: int | None = None
    year_terminated: int | None = None
    linked_technologies: list[str] = Field(default_factory=list)


class WocatTechnology(WocatRecord):
    """A documented SLM Technology, normalized against the QT vocabularies."""

    record_type: Literal["technology"] = "technology"

    slm_groups: list[str] = Field(default_factory=list)
    measures: list[str] = Field(default_factory=list)
    degradation: list[str] = Field(default_factory=list)
    land_use: list[str] = Field(default_factory=list)
    water_supply: str | None = None

    #: ContextClass kind -> QT labels, e.g. ``{"agroclimatic_zone": ["sub-humid"]}``.
    context: dict[str, list[str]] = Field(default_factory=dict)
    #: QT §5.2 landform: a real QT vocabulary kept as an attribute rather than
    #: a graph node (see rag/graph/README.md).
    landform: list[str] = Field(default_factory=list)
    rainfall_mm: float | None = None

    activities: list[Activity] = Field(default_factory=list)
    costs: Costs = Field(default_factory=Costs)
    #: QT §6.1 variable name -> rating key from ``IMPACT_RATING_KEYS``.
    impacts: dict[str, str] = Field(default_factory=dict)
    cost_benefit: CostBenefit = Field(default_factory=CostBenefit)
    adoption: Adoption = Field(default_factory=Adoption)

    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    references: list[Reference] = Field(default_factory=list)
    linked_approaches: list[str] = Field(default_factory=list)

    year_implemented: int | None = None

    # -------------------------------------------------------- normalization
    @field_validator("slm_groups", mode="before")
    @classmethod
    def _groups(cls, values: Any) -> list[str]:
        out: list[str] = []
        for raw in _as_list(values):
            group = wt.normalize_slm_group(raw)
            if group is None:
                logger.warning("unknown QT §3.5 SLM group %r — dropped", raw)
            elif group not in out:
                out.append(group)
        return out

    @field_validator("measures", mode="before")
    @classmethod
    def _measures(cls, values: Any) -> list[str]:
        out: list[str] = []
        for raw in _as_list(values):
            code = _measure_code(raw)
            if code is None:
                logger.warning("unknown QT §3.6 SLM measure %r — dropped", raw)
            elif code not in out:
                out.append(code)
        return sorted(out)

    @field_validator("degradation", mode="before")
    @classmethod
    def _degradation(cls, values: Any) -> list[str]:
        out: list[str] = []
        for raw in _as_list(values):
            code = _degradation_code(raw)
            if code is None:
                logger.warning("unknown QT §3.7 degradation type %r — dropped", raw)
            elif code not in out:
                out.append(code)
        return sorted(out)

    @field_validator("land_use", mode="before")
    @classmethod
    def _land_use(cls, values: Any) -> list[str]:
        out: list[str] = []
        for raw in _as_list(values):
            text = str(raw).strip()
            code = text.split(":")[0].strip()
            out.append(code if code in wt.LAND_USE_TYPES else text)
        return out

    @field_validator("water_supply", mode="before")
    @classmethod
    def _water_supply(cls, value: Any) -> str | None:
        if value in (None, ""):
            return None
        text = " ".join(str(value).strip().lower().replace("–", "-").split())
        if text not in wt.WATER_SUPPLY:
            logger.warning("unknown QT §3.4 water supply %r — kept verbatim", value)
        return text

    @field_validator("context", mode="before")
    @classmethod
    def _context(cls, values: Any) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for kind, raw_values in (values or {}).items():
            if kind not in CONTEXT_CLASS_KINDS:
                logger.warning("context kind %r is not a graph node kind — dropped", kind)
                continue
            normalized: list[str] = []
            for raw in _as_list(raw_values):
                value = wt.normalize_context_value(kind, raw)
                if value is None:
                    logger.warning("unknown %s value %r — dropped", kind, raw)
                elif value not in normalized:
                    normalized.append(value)
            if normalized:
                out[kind] = normalized
        return out

    @field_validator("landform", mode="before")
    @classmethod
    def _landform(cls, values: Any) -> list[str]:
        out: list[str] = []
        for raw in _as_list(values):
            value = wt.normalize_context_value("landform", raw)
            out.append(value if value is not None else str(raw).strip())
        return out

    @field_validator("impacts", mode="before")
    @classmethod
    def _impacts(cls, values: Any) -> dict[str, str]:
        out: dict[str, str] = {}
        for raw_name, raw_rating in (values or {}).items():
            name = wt.normalize_impact_name(str(raw_name))
            rating = wt.normalize_rating(str(raw_rating))
            if name is None:
                logger.warning("unknown QT §6.1 impact variable %r — dropped", raw_name)
                continue
            if rating is None:
                logger.warning(
                    "unknown rating %r for %r — dropped", raw_rating, raw_name
                )
                continue
            out[name] = rating
        return dict(sorted(out.items()))

    @field_validator("linked_approaches", "strengths", "weaknesses", mode="before")
    @classmethod
    def _string_list(cls, values: Any) -> list[str]:
        return [str(v).strip() for v in _as_list(values) if str(v).strip()]

    @model_validator(mode="after")
    def _licence_present(self) -> WocatTechnology:
        if not self.licence:
            raise ValueError(
                f"{self.wocat_id}: WOCAT records must carry their CC BY-NC-SA licence"
            )
        return self


# -------------------------------------------------------------- utilities
def _as_list(value: Any) -> list[Any]:
    """Accept a scalar, a list, or ``None`` and always return a list."""
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def _measure_code(raw: Any) -> str | None:
    """``"A 3.3: Full tillage"`` / ``"A3"`` -> ``"A3"``, else None."""
    text = str(raw).strip().upper().replace(" ", "")
    head = text.split(":")[0]
    head = head.split(".")[0]
    return head if head in wt.MEASURES_BY_CODE else None


def _degradation_code(raw: Any) -> str | None:
    """``"Wt: loss of topsoil"`` / ``"Wt"`` -> ``"Wt"``, else None."""
    text = str(raw).strip().replace(" ", "")
    head = text.split(":")[0]
    if head in wt.DEGRADATION_BY_CODE:
        return head
    # tolerate case differences, e.g. "WT" from a spreadsheet export
    for code in wt.DEGRADATION_BY_CODE:
        if code.lower() == head.lower():
            return code
    return None


def parse_record(payload: dict[str, Any]) -> WocatTechnology | WocatApproach:
    """Build the right model from a raw dict (dispatches on ``record_type``)."""
    record_type = str(payload.get("record_type", "technology")).lower()
    if record_type == "approach":
        return WocatApproach.model_validate(payload)
    return WocatTechnology.model_validate(payload)
