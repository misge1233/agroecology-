"""The one masking mechanism of the harness (E4 Part 3).

A :class:`Mask` is built from the held-out **groups** of a fold (a group is the
normalised DOI when the store has one, else the source ``study_id``; see
:func:`group_key`). It holds every identifier under which those groups can reach a
method: DOIs, store study ids (which are also the frozen dataset's ``Study_No_`` and
the graph's study labels) and corpus ``era_code``s (``ERA_<code>`` study ids map to
the ERA corpus code, Habtamu study ids are their own corpus code). It is passed to
every engine and is enforced by:

* training rows: :meth:`Mask.filter_rows` (store frames by ``study_id``/``doi``,
  dataset frames by ``Study_No_``);
* retrieval: ``rag.retrieve.RagRetriever.retrieve(..., mask=)`` (a Chroma ``where``
  filter on ``doi`` and ``era_code`` plus :meth:`Mask.blocks_chunk` on every hit, which
  also reads the ``study_ids`` list of the re-indexed Tier 1);
* graph: ``rag.graph.query.GraphQuery.masked(mask)`` drops the ``Study`` nodes (and so
  their ``REPORTS_EFFECT`` edges) of masked groups;
* evidence cards (E6): the card builder takes the mask.

Chunks without any study metadata (no ``doi``, no ``era_code``, no ``study_ids``) can
never be masked; :meth:`Mask.blocks_chunk` returns ``False`` for them and the retriever
counts them (``unmaskable``), as the brief requires.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

import pandas as pd

ERA_PREFIX = "ERA_"
HAB_PREFIX = "HAB_"


def group_key(doi: Any, study_id: Any) -> str:
    """The harness grouping key: the normalised DOI when present, else the study id."""
    if isinstance(doi, str) and doi.strip():
        return doi.strip().lower()
    return str(study_id)


def group_keys(df: pd.DataFrame) -> pd.Series:
    """:func:`group_key` for every row of a store frame."""
    return pd.Series([group_key(d, s) for d, s in zip(df["doi"], df["study_id"])], index=df.index, dtype=object)


def era_code_of(study_id: str) -> str | None:
    """Corpus ``era_code`` of a store study id (``ERA_AC0019`` -> ``AC0019``; Habtamu ids are their own code)."""
    if study_id.startswith(ERA_PREFIX):
        return study_id[len(ERA_PREFIX):].split(".")[0]  # ERA_JS0269.1 is a sub-study of the paper JS0269
    if study_id.startswith(HAB_PREFIX):
        return study_id
    return None


def chunk_study_ids(meta: Mapping[str, Any]) -> list[str]:
    """``study_ids`` of a chunk record or its Chroma metadata (list, ``;``-joined string or absent)."""
    v = meta.get("study_ids")
    if v is None or v == "":
        return []
    if isinstance(v, str):
        return [s for s in v.split(";") if s]
    return [str(s) for s in v]


@dataclass(frozen=True)
class Mask:
    """Identifiers to hide from every method for one fold."""

    groups: frozenset[str] = field(default_factory=frozenset)
    dois: frozenset[str] = field(default_factory=frozenset)
    study_ids: frozenset[str] = field(default_factory=frozenset)
    era_codes: frozenset[str] = field(default_factory=frozenset)

    # --------------------------------------------------------------- build
    @classmethod
    def empty(cls) -> "Mask":
        return cls()

    @classmethod
    def from_groups(cls, groups: Iterable[str], store: pd.DataFrame) -> "Mask":
        """Every DOI, study id and corpus code of the rows whose :func:`group_key` is in ``groups``."""
        wanted = frozenset(str(g) for g in groups)
        keys = group_keys(store)
        rows = store[keys.isin(wanted)]
        dois = {d.strip().lower() for d in rows["doi"].dropna() if str(d).strip()}
        sids = {str(s) for s in rows["study_id"]}
        # a group named by a study id (no DOI) is itself hidden; a DOI group hides its DOI
        dois |= {g for g in wanted if "/" in g}
        sids |= {g for g in wanted if "/" not in g}
        codes = {c for c in (era_code_of(s) for s in sids) if c}
        return cls(groups=wanted, dois=frozenset(dois), study_ids=frozenset(sids), era_codes=frozenset(codes))

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "Mask":
        return cls(frozenset(d.get("groups", ())), frozenset(d.get("dois", ())), frozenset(d.get("study_ids", ())),
                   frozenset(d.get("era_codes", ())))

    def to_dict(self) -> dict[str, list[str]]:
        return {"groups": sorted(self.groups), "dois": sorted(self.dois), "study_ids": sorted(self.study_ids),
                "era_codes": sorted(self.era_codes)}

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True)

    @property
    def is_empty(self) -> bool:
        return not (self.dois or self.study_ids or self.era_codes)

    # --------------------------------------------------------------- checks
    def blocks_study(self, study_id: Any) -> bool:
        return isinstance(study_id, str) and study_id in self.study_ids

    def blocks_doi(self, doi: Any) -> bool:
        return isinstance(doi, str) and doi.strip().lower() in self.dois

    def blocks_era_code(self, era_code: Any) -> bool:
        return isinstance(era_code, str) and era_code in self.era_codes

    def blocks_chunk(self, meta: Mapping[str, Any]) -> bool:
        """True when a chunk (record or Chroma metadata) belongs to a masked group."""
        if self.is_empty:
            return False
        if self.blocks_doi(meta.get("doi")) or self.blocks_era_code(meta.get("era_code")):
            return True
        return any(s in self.study_ids or (era_code_of(s) in self.era_codes if era_code_of(s) else False)
                   for s in chunk_study_ids(meta))

    @staticmethod
    def chunk_is_maskable(meta: Mapping[str, Any]) -> bool:
        """A chunk with no study metadata at all can never be masked (counted, never silently kept)."""
        return bool(meta.get("doi")) or bool(meta.get("era_code")) or bool(chunk_study_ids(meta))

    def blocks_graph_study(self, attrs: Mapping[str, Any]) -> bool:
        """True for a graph ``Study`` node of a masked group (label = store study id)."""
        if self.is_empty:
            return False
        label = attrs.get("label") or (attrs.get("id", "").split(":", 1)[1] if ":" in attrs.get("id", "") else "")
        return (self.blocks_study(label) or self.blocks_doi(attrs.get("doi"))
                or self.blocks_era_code(attrs.get("era_code")))

    # --------------------------------------------------------------- rows
    def filter_rows(self, df: pd.DataFrame) -> pd.DataFrame:
        """Rows of ``df`` that are not held out (store frames or the frozen dataset)."""
        if self.is_empty or df.empty:
            return df
        keep = pd.Series(True, index=df.index)
        if "study_id" in df.columns:
            keep &= ~df["study_id"].astype(str).isin(self.study_ids)
        if "Study_No_" in df.columns:
            keep &= ~df["Study_No_"].astype(str).isin(self.study_ids)
        if "doi" in df.columns:
            keep &= ~df["doi"].map(lambda d: isinstance(d, str) and d.strip().lower() in self.dois)
        if "group" in df.columns:
            keep &= ~df["group"].astype(str).isin(self.groups)
        return df[keep]

    def where_clause(self) -> dict[str, Any] | None:
        """Chroma ``where`` filter on the scalar metadata fields (``doi``, ``era_code``)."""
        parts = []
        if self.dois:
            parts.append({"doi": {"$nin": sorted(self.dois)}})
        if self.era_codes:
            parts.append({"era_code": {"$nin": sorted(self.era_codes)}})
        if not parts:
            return None
        return parts[0] if len(parts) == 1 else {"$and": parts}
