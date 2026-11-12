"""Evidence cards and their per-query selection (E6 Part 1).

A **card** is one pooled contrast per ``(group, site, practice_id, outcome_id, crop,
comparator_class)`` from the rows a fold's :class:`~model.harness.mask.Mask` allows: the
same cell as the harness queries and the pooled items of Methodology 1
(:func:`model.m1.data.pooled_items`, reused here). It is rendered by one fixed template
(about 60 to 80 tokens): a stable short id, the practice and outcome names with what
"better" means, the oriented effect as a rounded percent change ``exp(y) - 1``, the number
of rows, a precision class, the site context in words and numbers, country, year, quality
flag, a short citation and the DOI. Card metadata keeps ``doi``, ``study_ids``,
``practice_id``, ``outcome_id``, ``objective_group`` and the coordinates.

**Selection per query** (structured, not embedding search): for each candidate, cards of
the same practice and outcome first, then the same practice and objective group, each
ordered by context distance in the standardised space of :mod:`model.m1.matched`; at most
``per_candidate`` (4); a candidate with fewer than 2 gets up to 2 cards of practices
sharing its main component, flagged "related practice". A total cap (32) shrinks the
largest candidate blocks first; candidates are never dropped.

Every card comes from ``mask.filter_rows`` (through :func:`model.m1.data.training_rows`),
so a held-out study can never reach a prompt (``test_m2`` canary).

**Precision class**: from the pooled variance ``v`` of the cell (``v < 0.01`` high,
``v < 0.05`` medium, else low); without a variance, ``medium`` for quality ``High`` rows
and ``low`` otherwise.
"""
from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass, field
from typing import Any, Mapping

import numpy as np
import pandas as pd

from model.harness import queries as hq
from model.harness.mask import Mask
from model.m1 import data as md
from model.m1.matched import MatchedStudies

PER_CANDIDATE = 4
MAX_CARDS = 32
MIN_OWN = 2
MAX_RELATED = 2


@dataclass
class Card:
    card_id: str
    practice_id: str
    outcome_id: str
    objective_group: str
    y: float
    var: float
    n_rows: int
    precision: str
    doi: str | None
    study_ids: list[str]
    lat: float | None
    lon: float | None
    text: str = ""
    related: bool = False
    meta: dict[str, Any] = field(default_factory=dict)


# ----------------------------------------------------------------- formatting helpers
def card_id_of(key: tuple[Any, ...], length: int = 6) -> str:
    return "c" + hashlib.sha256("\x1f".join(str(k) for k in key).encode("utf-8")).hexdigest()[:length]


def precision_class(var: float, quality: Any) -> str:
    if var is not None and np.isfinite(var):
        return "high" if var < 0.01 else "medium" if var < 0.05 else "low"
    return "medium" if str(quality) == "High" else "low"


def pct_change(y: float) -> str:
    """The oriented effect as a rounded percent change (``exp(y) - 1``); + means better."""
    p = (math.exp(float(y)) - 1.0) * 100.0
    r = int(round(p)) if abs(p) < 1000 else int(round(p, -2))
    return f"{r:+d}%"


def short_citation(citation: Any, year: Any) -> str:
    """First author's surname and the year (``Temesgen 2009``) from any of the store's formats."""
    c = str(citation or "").strip()
    name = re.split(r"[,_(]|\s", c, maxsplit=1)[0].strip() if c else ""
    y = ""
    yr = _num(year)
    if yr is not None:
        y = str(int(yr))
    else:
        m = re.search(r"(19|20)\d\d", c)
        y = m.group(0) if m else ""
    return " ".join(p for p in (name, y) if p) or "unknown source"


def _num(v: Any) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _str(v: Any) -> str | None:
    """A non-empty string or ``None`` (``pd.NA``, ``nan`` and blanks become ``None``)."""
    return v.strip() if isinstance(v, str) and v.strip() else None


def context_words(ctx: Mapping[str, Any], belt_name: str | None) -> str:
    """Belt, rainfall, altitude, slope, clay, sand and aridity in words (missing parts left out)."""
    parts = [belt_name] if belt_name else []
    for key, alt, fmt in (("ctx_precip_annual", "Rainfall", "{:.0f} mm rain"), ("ctx_elevation", "Altitude_r", "{:.0f} m"),
                          ("ctx_slope", "slope", "slope {:.0f}%"), ("ctx_soil_clay", "soil_clay", "clay {:.0f}%"),
                          ("ctx_soil_sand", None, "sand {:.0f}%"), ("ctx_aridity_index", None, "aridity {:.2f}")):
        v = _num(ctx.get(key))
        if v is None and alt:
            v = _num(ctx.get(alt))
        if v is not None:
            parts.append(fmt.format(v))
    return ", ".join(parts) if parts else "context not reported"


# ----------------------------------------------------------------- the store of one fold
class CardStore:
    """Every card a fold allows, with the matched-studies distance space for selection."""

    def __init__(self, outcome_group: Mapping[str, str], practice_name: Mapping[str, str],
                 outcome_name: Mapping[str, str], outcome_direction: Mapping[str, int],
                 components_of: Mapping[str, list[str]], belt_name_of: Mapping[int, str] | None = None) -> None:
        self.outcome_group = dict(outcome_group)
        self.practice_name = dict(practice_name)
        self.outcome_name = dict(outcome_name)
        self.outcome_direction = dict(outcome_direction)
        self.components_of = {k: list(v) for k, v in components_of.items()}
        self.belt_name_of = dict(belt_name_of or {})
        self.cards: list[Card] = []
        self.items = pd.DataFrame()
        self.space: MatchedStudies | None = None
        self.mask = Mask.empty()

    def fit(self, store: pd.DataFrame, mask: Mask) -> "CardStore":
        """Cards from the eligible rows the mask allows (the M1 training rows, all sources)."""
        self.mask = mask
        rows = md.training_rows(store, mask, md.DataConfig(), self.outcome_group)
        self.cards, self.items = [], pd.DataFrame()
        if rows.empty:
            return self
        items = md.pooled_items(rows)
        # every study id of each cell (pooled_items keeps the first row's), same cell keys
        r = rows.assign(crop_key=rows["crop"].map(lambda c: " ".join(str(c).split()).lower() if isinstance(c, str) and c.strip() else ""),
                        comp=rows["comparator"].map(hq.comparator_class))
        keys = ["group", "site", "outcome_id", "crop_key", "comp", "practice_id"]
        sids = {("\x1f".join(str(k) for k in key[:5]), key[5]): sorted({str(s) for s in g["study_id"]})
                for key, g in r.groupby(keys, sort=True)}
        self.space = MatchedStudies().fit(rows, items)
        ids_seen: dict[str, tuple] = {}
        for it in items.itertuples():
            first = rows.loc[it.row_index]
            group, site, outcome, crop_key, comp = it.qkey.split("\x1f")
            key = (group, site, it.practice_id, outcome, crop_key, comp)
            cid = card_id_of(key)
            n = 6
            while cid in ids_seen and ids_seen[cid] != key:  # a collision lengthens the id (never seen in the store)
                n += 2
                cid = card_id_of(key, n)
            ids_seen[cid] = key
            card = Card(card_id=cid, practice_id=str(it.practice_id), outcome_id=str(outcome),
                        objective_group=str(it.objective_group), y=float(it.y),
                        var=float(it.var) if it.var is not None and np.isfinite(it.var) else float("nan"),
                        n_rows=int(it.n_rows), precision=precision_class(it.var, first.get("quality_flag")),
                        doi=first["doi"] if isinstance(first.get("doi"), str) and first["doi"].strip() else None,
                        study_ids=sids.get((it.qkey, it.practice_id), [str(it.study_id)]),
                        lat=_num(first.get("lat")), lon=_num(first.get("lon")),
                        meta={"group": group, "site": site, "crop": crop_key, "comparator_class": comp,
                              "country": _str(first.get("country")), "year": _num(first.get("year")),
                              "quality_flag": _str(first.get("quality_flag")), "source": _str(first.get("source")),
                              "citation": short_citation(first.get("citation"), first.get("year")),
                              "context": self._row_context(first)})
            card.text = self.render(card)
            self.cards.append(card)
        self.items = items.assign(card_index=range(len(items)))
        return self

    @staticmethod
    def _row_context(row: pd.Series) -> dict[str, Any]:
        ctx = {k: _num(v) for k, v in row.items() if isinstance(k, str) and k.startswith("ctx_")
               and k not in ("ctx_release",) and not k.startswith("ctx_reported_")}
        for col, feat in (("ctx_reported_rain_mm", "Rainfall"), ("ctx_reported_altitude_m", "Altitude_r"),
                          ("ctx_reported_slope_pct", "slope")):
            v = _num(row.get(col))
            if v is not None:
                ctx[feat] = v
        if isinstance(row.get("ctx_reported_aez"), str) and row["ctx_reported_aez"].strip():
            ctx["reported_aez"] = row["ctx_reported_aez"].strip()
        return ctx

    def belt_name(self, ctx: Mapping[str, Any]) -> str | None:
        code = ctx.get("ctx_aez_belt")
        if code is not None and _num(code) is not None and int(float(code)) in self.belt_name_of:
            return self.belt_name_of[int(float(code))]
        for k in ("aez_belt", "reported_aez"):
            if isinstance(ctx.get(k), str) and ctx[k].strip():
                return ctx[k].strip()
        return None

    def better_words(self, outcome_id: str) -> str:
        return "lower is better" if int(self.outcome_direction.get(outcome_id, 1)) < 0 else "higher is better"

    def render(self, card: Card, related: bool = False) -> str:
        """The fixed card template (about 60 to 80 tokens)."""
        m = card.meta
        ctx = m.get("context") or {}
        year = f" {int(m['year'])}" if m.get("year") else ""
        crop = f", {m['crop']}" if m.get("crop") else ""
        doi = f", doi:{card.doi}" if card.doi else ""
        flag = f" RELATED PRACTICE ({self.practice_name.get(card.practice_id, card.practice_id)})" if related else ""
        return (f"[{card.card_id}]{flag} {self.practice_name.get(card.practice_id, card.practice_id)} vs "
                f"{m.get('comparator_class') or 'control'}{crop} | {self.outcome_name.get(card.outcome_id, card.outcome_id)} "
                f"({self.better_words(card.outcome_id)}): {pct_change(card.y)} (+ = better) | {card.n_rows} rows, "
                f"precision {card.precision} | {context_words(ctx, self.belt_name(ctx))} | {m.get('country') or '?'}{year}, "
                f"quality {m.get('quality_flag') or 'NR'} | {m.get('citation')}{doi}")

    # ------------------------------------------------------------ selection
    def _ordered(self, sel: np.ndarray, context: Mapping[str, Any]) -> list[int]:
        """Card indices ordered by context distance (stable; ties and unknown distances by card id)."""
        if len(sel) == 0:
            return []
        assert self.space is not None
        d = self.space._distances(dict(context), sel)
        order = sorted(range(len(sel)), key=lambda i: (d[i] if np.isfinite(d[i]) else math.inf, self.cards[sel[i]].card_id))
        return [int(sel[i]) for i in order]

    def select(self, context: Mapping[str, Any], candidates: list[str], outcome_id: str, objective_group: str,
               per_candidate: int = PER_CANDIDATE, max_cards: int = MAX_CARDS) -> dict[str, list[Card]]:
        """Cards per candidate (in candidate order); related-practice cards carry ``related=True``."""
        out: dict[str, list[Card]] = {c: [] for c in candidates}
        if self.items.empty:
            return out
        it = self.items
        prac, outc, grp = it["practice_id"].to_numpy(), it["outcome_id"].to_numpy(), it["objective_group"].to_numpy()
        for cand in candidates:
            same = np.flatnonzero((prac == cand) & (outc == outcome_id))
            near = np.flatnonzero((prac == cand) & (outc != outcome_id) & (grp == objective_group))
            chosen = (self._ordered(same, context) + self._ordered(near, context))[:per_candidate]
            cards = [self.cards[i] for i in chosen]
            if len(cards) < MIN_OWN:
                main = (self.components_of.get(cand) or [None])[0]
                if main:
                    shares = np.array([main in self.components_of.get(str(p), []) for p in prac])
                    rel_same = np.flatnonzero(shares & (prac != cand) & (outc == outcome_id))
                    rel_near = np.flatnonzero(shares & (prac != cand) & (outc != outcome_id) & (grp == objective_group))
                    rel = (self._ordered(rel_same, context) + self._ordered(rel_near, context))[:MAX_RELATED]
                    for i in rel:
                        c = self.cards[i]
                        cards.append(Card(**{**c.__dict__, "related": True, "text": self.render(c, related=True)}))
            out[cand] = cards
        # total cap: shrink the largest block (the last candidate among equals) one card at a time
        while sum(len(v) for v in out.values()) > max_cards:
            biggest = max(range(len(candidates)), key=lambda i: (len(out[candidates[i]]), i))
            out[candidates[biggest]].pop()
        return out

    def by_id(self) -> dict[str, Card]:
        return {c.card_id: c for c in self.cards}
