"""Queries: the units every method is evaluated on (E4 Part 1).

A **query** is one cell of the evidence store keyed by
``(group, site, outcome_id, crop, comparator_class)``:

* ``group``: the normalised DOI when the store has one, else the source ``study_id``
  (:func:`model.harness.mask.group_key`), so a paper extracted by two sources is one
  group;
* ``site``: the coordinate pair rounded to 3 decimals (about 100 m), or the site name
  when coordinates are missing (``unknown`` when both are missing);
* ``comparator_class``: :data:`COMPARATOR_CLASSES`, derived from the free-text
  ``comparator`` by :func:`comparator_class` (rules in its docstring).

Rows qualify when ``lrr`` is computable, ``direction_reviewed`` is true, ``practice_id``
and ``outcome_id`` are set, the row is not an ``extra.dup_of`` repeat and ``loc_method``
is not ``geocoded_llm_unchecked`` (:func:`eligible_rows`).

**Ground truth** (:func:`pool_effects`): within a query the rows of one practice are
pooled to one observed effect, the inverse-variance mean of ``lrr`` when ``var_lrr``
exists for all of them, else the mean weighted by the store ``weight``; the effect is
oriented by the outcome ``direction`` so that higher is better. Queries need at least
:data:`MIN_PRACTICES_PAIRWISE` (2) practices for the pairwise metrics and
:data:`MIN_PRACTICES_LIST` (3) for the list metrics.

**Inputs a method receives** (the ``context`` column, JSON): for site and district
precision the ``ctx_*`` layers of release ``ET/2026.1`` written by ``add_context.py``
(plus the same values under the legacy feature names the serving model uses, through
``pipelines.geodata.extract.TRAINING_CONTEXT``), for country precision and for
non-Ethiopian rows the reported context fields; the challenge ids the outcome belongs
to; the candidate practice ids in a random order fixed by the seed; the crop. Nothing
else from the query's rows.

**Query sets**: ``ET`` (headline), ``global`` (non-ET), ``post_2024`` (flag: studies
published in 2024 or later), ``legacy_68`` (the (study, indicator) cells of the P7
protocol built from the frozen dataset by :func:`legacy_queries`, for continuity).

Outputs (``data/evidence/harness/``): ``queries.parquet`` (one row per query),
``query_items.parquet`` (one row per query x practice: the ground truth),
``queries_card.md`` and ``queries_summary.json``. The parquet files hold
partner-derived rows and are git-ignored; the card and summary are in git.

Usage::

    python -m model.harness.queries [--seed 0] [--store-dir data/evidence]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import random
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from model.harness import HARNESS_DIR, RELEASE, REPO_ROOT
from model.harness.mask import group_key

if str(REPO_ROOT / "pipelines" / "dataset") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "pipelines" / "dataset"))

logger = logging.getLogger(__name__)

QUERIES_PARQUET = HARNESS_DIR / "queries.parquet"
ITEMS_PARQUET = HARNESS_DIR / "query_items.parquet"
CARD = HARNESS_DIR / "queries_card.md"
SUMMARY = HARNESS_DIR / "queries_summary.json"
LEGACY_DATASET = REPO_ROOT / "data" / "processed" / "CSA_ERA_final_model_ready.csv"

COMPARATOR_CLASSES = ("no_practice", "farmer_practice", "conventional_tillage", "mineral_fertilizer_only", "other")
MIN_PRACTICES_PAIRWISE = 2
MIN_PRACTICES_LIST = 3
POST_CUTOFF_YEAR = 2024
EXCLUDED_LOC_METHOD = "geocoded_llm_unchecked"
HOME_COUNTRY = "ET"

QUERY_COLUMNS = ["query_id", "query_set", "post_2024", "legacy", "group", "site", "outcome_id", "objective_group",
                 "direction", "crop", "comparator_class", "comparator_null", "n_practices", "n_rows", "n_studies",
                 "country", "loc_precision", "sources", "year", "challenge_ids", "candidates", "context", "ctx_source",
                 "belt", "lat", "lon", "legacy_indicator"]
ITEM_COLUMNS = ["query_id", "practice_id", "y", "lrr_pooled", "var_pooled", "n_rows", "n_studies", "pooling",
                "practice_family", "practice_label", "rows_json"]

#: Legacy (serving) feature name -> store ``ctx_<layer>`` column.
LEGACY_CONTEXT = {"Rainfall": "ctx_precip_annual", "Altitude_r": "ctx_elevation", "temp_mean_annual": "ctx_temp_mean_annual",
                  "precip_seasonality": "ctx_precip_seasonality", "slope": "ctx_slope", "soil_clay": "ctx_soil_clay",
                  "land_cover": "ctx_land_cover", "aez_belt": "ctx_aez_belt", "lgp_days": "ctx_lgp_days",
                  "soil_ph": "ctx_soil_ph", "soil_soc": "ctx_soil_soc"}
#: Reported context -> legacy feature name (country precision and non-Ethiopian rows).
REPORTED_CONTEXT = {"ctx_reported_rain_mm": "Rainfall", "ctx_reported_altitude_m": "Altitude_r",
                    "ctx_reported_slope_pct": "slope"}


# ------------------------------------------------------------ comparator classes
_RE_FARMER = re.compile(r"\b(farmer|farmers|local practice|traditional|indigenous|local)\b", re.I)
_RE_TILLAGE = re.compile(r"\b(conventional\s*till|conventional\s*tillage|ct|tillage|plough|plow|ploughing|cultivat)\w*", re.I)
_RE_FERT = re.compile(r"\b(npk|nps|n\s*p\s*k|urea|dap|tsp|mineral|inorganic|chemical|recommended\s*(dose|rate|fert\w*)|"
                      r"100\s*%?\s*rf|rf|rdf|fertili[sz]er\s*only|\d+\s*kg\s*n)\b", re.I)
_RE_NONE = re.compile(r"\b(control|no\b|non[- ]?|without|zero|untreated|unamended|unfertili[sz]ed|nil|bare|none|"
                      r"absolute|check|[npk]0(?:[npk]0)*|fym0|0\s*kg|0\s*t|t0|t1)\b|^\s*0\s*$|(?<![\w.])0(?![\w.%])", re.I)


def comparator_class(text: Any) -> str:
    """Normalise a free-text comparator to one of :data:`COMPARATOR_CLASSES`.

    Rules, in order (the first that fires wins):

    1. ``farmer_practice``: farmer/farmers' practice, local or traditional practice;
    2. ``conventional_tillage``: conventional tillage/till, ``CT``, plough/plow, tillage;
    3. ``mineral_fertilizer_only``: NPK/NPS/urea/DAP/TSP, mineral, inorganic or chemical
       fertiliser, recommended dose/rate, ``RF``/``RDF``;
    4. ``no_practice``: control, no/none/without/zero/untreated/unamended/nil/bare/check,
       a lone ``0`` (``N0P0``, ``FYM0 NP0``, ``control 0``, ``T0``, ``T1``);
    5. otherwise ``other``; a missing comparator is ``other`` as well (reported separately).

    Rule 4 comes after 3 so that ``N0P0`` (no fertiliser) is ``no_practice`` while
    ``100 % RF`` is ``mineral_fertilizer_only``; ``control`` alone is ``no_practice``.
    """
    if text is None or (isinstance(text, float) and np.isnan(text)) or not str(text).strip():
        return "other"
    s = " ".join(str(text).split())
    if _RE_FARMER.search(s):
        return "farmer_practice"
    if _RE_TILLAGE.search(s):
        return "conventional_tillage"
    if _RE_FERT.search(s) and not re.search(r"\b(n0|p0|k0|0\s*kg|fym0)\b", s, re.I):
        return "mineral_fertilizer_only"
    if _RE_NONE.search(s):
        return "no_practice"
    return "other"


# ------------------------------------------------------------ eligibility and keys
def dup_of_series(df: pd.DataFrame) -> pd.Series:
    def _d(x: Any) -> Any:
        if not isinstance(x, str) or not x:
            return None
        try:
            return json.loads(x).get("dup_of")
        except (TypeError, ValueError):
            return None
    return pd.Series([_d(x) for x in df["extra"]], index=df.index, dtype=object)


def eligible_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Store rows that may form queries (rule in the module docstring)."""
    ok = (df["lrr"].notna() & (df["direction_reviewed"] == True) & df["practice_id"].notna()  # noqa: E712
          & df["outcome_id"].notna() & df["direction"].notna() & dup_of_series(df).isna()
          & (df["loc_method"] != EXCLUDED_LOC_METHOD))
    return df[ok.fillna(False)]


def site_key(lat: Any, lon: Any, site_name: Any) -> str:
    if pd.notna(lat) and pd.notna(lon):
        return f"{float(lat):.3f},{float(lon):.3f}"
    if isinstance(site_name, str) and site_name.strip():
        return " ".join(site_name.split())
    return "unknown"


def query_id_of(group: str, site: str, outcome_id: str, crop: str, comparator: str) -> str:
    """Deterministic id of a query key (first 12 hex digits of its SHA-256)."""
    key = "\x1f".join([group, site, outcome_id, crop, comparator])
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]


# ------------------------------------------------------------ ground truth
def pool_effects(lrr: np.ndarray, var: np.ndarray, weight: np.ndarray) -> tuple[float, float, str]:
    """``(pooled lrr, pooled variance or nan, method)``: inverse-variance when every row has a
    positive ``var_lrr``, else the store-weighted mean."""
    lrr = np.asarray(lrr, float)
    var = np.asarray(var, float)
    if len(lrr) and np.all(np.isfinite(var)) and np.all(var > 0):
        w = 1.0 / var
        return float(np.sum(w * lrr) / np.sum(w)), float(1.0 / np.sum(w)), "inverse_variance"
    w = np.asarray(weight, float)
    w = np.where(np.isfinite(w) & (w > 0), w, 1.0)
    return float(np.sum(w * lrr) / np.sum(w)), float("nan"), "weighted_mean"


# ------------------------------------------------------------ context
def context_of(rows: pd.DataFrame, aez_lookup: dict[int, str]) -> tuple[dict[str, Any], str]:
    """The context a method receives for a query: release layers or reported fields."""
    first = rows.iloc[0]
    ctx_cols = [c for c in rows.columns if c.startswith("ctx_") and not c.startswith("ctx_reported_")
                and c != "ctx_release"]
    if pd.notna(first.get("ctx_release")) and pd.notna(first.get("ctx_precip_annual")):
        ctx: dict[str, Any] = {}
        for c in ctx_cols:
            v = first[c]
            ctx[c] = None if pd.isna(v) else (int(v) if c in ("ctx_land_cover", "ctx_aez_belt", "ctx_koppen_class")
                                               else round(float(v), 4))
        for feat, col in LEGACY_CONTEXT.items():
            v = first.get(col)
            if pd.isna(v):
                ctx[feat] = None
            elif feat == "land_cover":
                ctx[feat] = int(v)
            elif feat == "aez_belt":
                ctx[feat] = aez_lookup.get(int(v))
            else:
                ctx[feat] = round(float(v), 3)
        ctx["release"] = str(first["ctx_release"])
        return ctx, "release"
    ctx = {}
    for col, feat in REPORTED_CONTEXT.items():
        v = first.get(col)
        ctx[feat] = None if pd.isna(v) else round(float(v), 3)
    for col in ("ctx_reported_soil", "ctx_reported_aez"):
        v = first.get(col)
        ctx[col] = None if pd.isna(v) else str(v)
    ctx["aez_belt"] = None
    return ctx, "reported"


def load_aez_lookup() -> dict[int, str]:
    from pipelines.geodata.extract import load_aez_lookup

    return load_aez_lookup()


def challenge_index(challenges: pd.DataFrame) -> dict[str, list[str]]:
    """outcome_id -> challenge ids whose ``outcome_ids`` list it."""
    out: dict[str, list[str]] = {}
    for r in challenges.itertuples():
        for oid in str(r.outcome_ids).split(";"):
            oid = oid.strip()
            if oid:
                out.setdefault(oid, []).append(r.challenge_id)
    return {k: sorted(v) for k, v in out.items()}


def dataset_labels(store: pd.DataFrame) -> dict[str, str]:
    """practice_id -> frozen ``CSA_practices`` label (from the ERA/CSA rows, the dataset's sources).

    Two ids carry two spellings (``CROP_ROTATION``: ``Crop Rotation``/``rotation``); the
    most frequent label is used.
    """
    rows = store[store["source"].isin(["ERA", "CSA"]) & store["practice_id"].notna()]
    out: dict[str, str] = {}
    for pid, g in rows.groupby("practice_id"):
        out[str(pid)] = str(g["practice_raw"].value_counts().index[0])
    return out


# ------------------------------------------------------------ builders
def build_queries(store: pd.DataFrame, taxonomy: Any, seed: int = 0, use_comparator: bool = True,
                  aez_lookup: dict[int, str] | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Queries and their ground-truth items from the store (``ET`` and ``global`` sets)."""
    rows = eligible_rows(store).copy()
    aez = aez_lookup if aez_lookup is not None else load_aez_lookup()
    outcomes = taxonomy.outcomes.set_index("outcome_id")
    challenge_of = challenge_index(taxonomy.challenges)
    labels = dataset_labels(store)
    family_of = {str(r.practice_id): str(r.practice_family) for r in taxonomy.practices.itertuples()}

    rows["group"] = [group_key(d, s) for d, s in zip(rows["doi"], rows["study_id"])]
    rows["site"] = [site_key(a, b, n) for a, b, n in zip(rows["lat"], rows["lon"], rows["site_name"])]
    rows["crop_key"] = rows["crop"].map(lambda c: " ".join(str(c).split()).lower() if isinstance(c, str) and c.strip() else "")
    rows["comparator_class"] = rows["comparator"].map(comparator_class) if use_comparator else "all"

    queries: list[dict[str, Any]] = []
    items: list[dict[str, Any]] = []
    keys = ["group", "site", "outcome_id", "crop_key", "comparator_class"]
    for (group, site, outcome_id, crop_key, comp), q in rows.groupby(keys, sort=True):
        if q["practice_id"].nunique() < MIN_PRACTICES_PAIRWISE:
            continue
        direction = int(q["direction"].iloc[0])
        qid = query_id_of(group, site, outcome_id, crop_key, comp)
        if not use_comparator:
            qid = "nc" + qid[2:]
        practices = sorted(q["practice_id"].unique())
        for pid in practices:
            p = q[q["practice_id"] == pid]
            pooled, var, method = pool_effects(p["lrr"].to_numpy(), p["var_lrr"].to_numpy(), p["weight"].to_numpy())
            items.append({"query_id": qid, "practice_id": pid, "y": pooled * direction, "lrr_pooled": pooled,
                          "var_pooled": var, "n_rows": int(len(p)), "n_studies": int(p["study_id"].nunique()),
                          "pooling": method, "practice_family": family_of.get(pid) or (p["practice_family"].dropna().iloc[0]
                                                                                       if p["practice_family"].notna().any() else None),
                          "practice_label": labels.get(pid), "rows_json": None})
        rng = random.Random(f"{seed}:{qid}")
        cands = list(practices)
        rng.shuffle(cands)
        ctx, ctx_source = context_of(q, aez)
        country = str(q["country"].iloc[0]) if pd.notna(q["country"].iloc[0]) else "unknown"
        year = q["year"].dropna()
        year_v = int(year.iloc[0]) if len(year) else None
        belt_code = q["ctx_aez_belt"].iloc[0] if "ctx_aez_belt" in q.columns else None
        queries.append({
            "query_id": qid, "query_set": "ET" if country == HOME_COUNTRY else "global",
            "post_2024": bool(year_v is not None and year_v >= POST_CUTOFF_YEAR), "legacy": False,
            "group": group, "site": site, "outcome_id": outcome_id,
            "objective_group": str(outcomes.loc[outcome_id, "objective_group"]) if outcome_id in outcomes.index else "other",
            "direction": direction, "crop": crop_key or None, "comparator_class": comp,
            "comparator_null": bool((q["comparator"].isna() | (q["comparator"].astype(str).str.strip() == "")).all()),
            "n_practices": len(practices), "n_rows": int(len(q)), "n_studies": int(q["study_id"].nunique()),
            "country": country, "loc_precision": str(q["loc_precision"].iloc[0]),
            "sources": ";".join(sorted(q["source"].unique())), "year": year_v,
            "challenge_ids": ";".join(challenge_of.get(outcome_id, [])), "candidates": ";".join(cands),
            "context": json.dumps(ctx, sort_keys=True), "ctx_source": ctx_source,
            "belt": aez.get(int(belt_code)) if pd.notna(belt_code) else None,
            "lat": float(q["lat"].iloc[0]) if pd.notna(q["lat"].iloc[0]) else None,
            "lon": float(q["lon"].iloc[0]) if pd.notna(q["lon"].iloc[0]) else None,
            "legacy_indicator": (str(outcomes.loc[outcome_id, "legacy_indicator"]) or None)
            if outcome_id in outcomes.index and str(outcomes.loc[outcome_id, "legacy_indicator"]).strip() else None,
        })
    qdf = pd.DataFrame(queries, columns=QUERY_COLUMNS)
    idf = pd.DataFrame(items, columns=ITEM_COLUMNS)
    return qdf, idf


def legacy_queries(dataset: pd.DataFrame, taxonomy: Any, seed: int = 0,
                   min_practices: int = MIN_PRACTICES_LIST,
                   label_to_id: dict[str, str] | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """The P7 cells: ``(Study_No_, Indicator)`` with >= 3 distinct practices in the frozen dataset.

    Ground truth is the mean ``log_response_ratio`` per practice, oriented by
    ``recommend.DIRECTION`` (exactly ``evaluate.ranking_metrics``). The context carries
    the dataset's own feature values and, per item, the dataset row indices
    (``rows_json``) so ``m0_current`` can score the very rows the P7 protocol scored.
    ``label_to_id`` maps frozen ``CSA_practices`` labels to canonical practice ids (from
    the store); a label without an id keeps the label as its id.
    """
    import evaluate as ev  # model/evaluate.py (the P7 protocol)

    directions = ev.direction_map()
    outcome_of = {str(r.legacy_indicator): str(r.outcome_id) for r in taxonomy.outcomes.itertuples()
                  if str(r.legacy_indicator).strip()}
    objective_of = {str(r.outcome_id): str(r.objective_group) for r in taxonomy.outcomes.itertuples()}
    challenge_of = challenge_index(taxonomy.challenges)
    label_to_id = dict(label_to_id or {})
    queries, items = [], []
    for (study, indicator), cell in dataset.groupby([ev.GROUP, "Indicator"], sort=True):
        practices = sorted(cell["CSA_practices"].unique())
        if len(practices) < min_practices:
            continue
        d = directions[indicator]
        outcome_id = outcome_of.get(indicator, indicator)
        qid = "legacy" + query_id_of(str(study), "", indicator, "", "legacy")[6:]
        first = cell.iloc[0]
        ctx = {k: (None if pd.isna(first[k]) else (int(first[k]) if k == "land_cover" else
                                                     (str(first[k]) if k == "aez_belt" else round(float(first[k]), 3))))
               for k in ("Rainfall", "Altitude_r", "temp_mean_annual", "precip_seasonality", "slope", "soil_clay",
                         "land_cover", "aez_belt", "lgp_days", "soil_ph", "soil_soc")}
        ctx["legacy_rows"] = True
        for pr in practices:
            p = cell[cell["CSA_practices"] == pr]
            items.append({"query_id": qid, "practice_id": label_to_id.get(pr, pr), "y": float(p[ev.TARGET].mean()) * d,
                          "lrr_pooled": float(p[ev.TARGET].mean()), "var_pooled": float("nan"), "n_rows": int(len(p)),
                          "n_studies": 1, "pooling": "mean", "practice_family": str(p["practice_family"].iloc[0]),
                          "practice_label": pr, "rows_json": json.dumps([int(i) for i in p.index])})
        rng = random.Random(f"{seed}:{qid}")
        cands = [label_to_id.get(pr, pr) for pr in practices]
        rng.shuffle(cands)
        queries.append({
            "query_id": qid, "query_set": "legacy_68", "post_2024": False, "legacy": True, "group": str(study),
            "site": site_key(first["latitude"], first["longitude"], None), "outcome_id": outcome_id,
            "objective_group": objective_of.get(outcome_id, "other"), "direction": d, "crop": None,
            "comparator_class": "legacy", "comparator_null": False, "n_practices": len(practices),
            "n_rows": int(len(cell)), "n_studies": 1,
            "country": HOME_COUNTRY, "loc_precision": "site", "sources": str(first["source"]), "year": None,
            "challenge_ids": ";".join(challenge_of.get(outcome_id, [])), "candidates": ";".join(cands),
            "context": json.dumps(ctx, sort_keys=True), "ctx_source": "legacy_dataset", "belt": str(first["aez_belt"]),
            "lat": float(first["latitude"]), "lon": float(first["longitude"]), "legacy_indicator": indicator,
        })
    return pd.DataFrame(queries, columns=QUERY_COLUMNS), pd.DataFrame(items, columns=ITEM_COLUMNS)


# ------------------------------------------------------------ summaries, card, io
def counts(qdf: pd.DataFrame) -> dict[str, Any]:
    """Query counts per set and objective group at the pairwise and list thresholds."""
    out: dict[str, Any] = {}
    for name, sub in (("ET", qdf[qdf["query_set"] == "ET"]), ("global", qdf[qdf["query_set"] == "global"]),
                      ("post_2024", qdf[qdf["post_2024"]]), ("legacy_68", qdf[qdf["query_set"] == "legacy_68"])):
        pair, lst = sub[sub["n_practices"] >= MIN_PRACTICES_PAIRWISE], sub[sub["n_practices"] >= MIN_PRACTICES_LIST]
        out[name] = {"n_pairwise": int(len(pair)), "n_list": int(len(lst)),
                     "by_objective_pairwise": {k: int(v) for k, v in pair["objective_group"].value_counts().sort_index().items()},
                     "by_objective_list": {k: int(v) for k, v in lst["objective_group"].value_counts().sort_index().items()}}
    return out


def _table(series: pd.Series, head: tuple[str, str], top: int | None = None) -> list[str]:
    vc = series.value_counts(dropna=False)
    if top:
        vc = vc.head(top)
    L = [f"| {head[0]} | {head[1]} |", "|---|---:|"]
    for k, v in vc.items():
        L.append(f"| {k} | {int(v):,} |")
    return L


def card_markdown(qdf: pd.DataFrame, idf: pd.DataFrame, nc_counts: dict[str, Any], summary: dict[str, Any]) -> str:
    """``queries_card.md``: counts per set, objective, challenge, belt, source, precision, comparator."""
    L = ["# Harness queries (E4 Part 1)", "",
         f"Built from the evidence store ({summary['store_rows']:,} rows, {summary['eligible_rows']:,} eligible; "
         f"release `{RELEASE}` context) and the frozen dataset (legacy cells). One query = one "
         "`(group, site, outcome_id, crop, comparator_class)` cell; ground truth = pooled oriented `lrr` per practice. "
         f"Seed {summary['seed']}; query-key hash `{summary['query_hash'][:12]}`.", ""]
    L += ["| set | queries with >= 2 practices (pairwise) | >= 3 practices (list) | same, without the comparator key |",
          "|---|---:|---:|---|"]
    for name, c in summary["counts"].items():
        nc = nc_counts.get(name)
        L.append(f"| {name} | {c['n_pairwise']} | {c['n_list']} | "
                 + ("n/a (dataset cells)" if name == "legacy_68" else
                    (f"{nc['n_pairwise']} / {nc['n_list']}" if nc else "same (not keyed)")) + " |")
    L += ["", "## By objective group (ET, pairwise / list)", "", "| objective group | >= 2 | >= 3 | without comparator key >= 2 / >= 3 |",
          "|---|---:|---:|---|"]
    et = summary["counts"]["ET"]
    etnc = nc_counts.get("ET", {})
    for og in sorted(set(et["by_objective_pairwise"]) | set(etnc.get("by_objective_pairwise", {}))):
        L.append(f"| {og} | {et['by_objective_pairwise'].get(og, 0)} | {et['by_objective_list'].get(og, 0)} | "
                 f"{etnc.get('by_objective_pairwise', {}).get(og, 0)} / {etnc.get('by_objective_list', {}).get(og, 0)} |")
    main = qdf[~qdf["legacy"]]
    L += ["", "## Comparator classes (rows that form queries)", ""]
    L += _table(main["comparator_class"], ("comparator_class", "queries"))
    L += ["", f"Rows without any comparator text are classed `other`; {summary['queries_with_null_comparator']} of the "
              f"{int((~qdf['legacy']).sum())} ET/global queries are built only from such rows (the other `other` "
              "queries have comparator text that no rule matched).", ""]
    L += ["## Challenges (ET queries; a query counts in every challenge of its outcome)", ""]
    ch = Counter(c for s in main[main['query_set'] == 'ET']["challenge_ids"] for c in str(s).split(";") if c)
    L += ["| challenge | queries |", "|---|---:|"] + [f"| {k} | {v} |" for k, v in sorted(ch.items(), key=lambda kv: -kv[1])]
    L += ["", "## Belt (ET queries, attribute only)", ""] + _table(main[main["query_set"] == "ET"]["belt"].fillna("none"), ("belt", "queries"))
    L += ["", "## Sources, precision, context source", ""] + _table(main["sources"], ("sources", "queries"))
    L += [""] + _table(main["loc_precision"], ("loc_precision", "queries"))
    L += [""] + _table(main["ctx_source"], ("ctx_source", "queries"))
    L += ["", "## Ground-truth pooling", ""] + _table(idf[idf["query_id"].isin(main["query_id"])]["pooling"], ("pooling", "items"))
    L += ["", f"Items (query x practice): {len(idf):,}; practices per query: median "
              f"{main['n_practices'].median():.0f}, max {main['n_practices'].max()}; rows per query: median "
              f"{main['n_rows'].median():.0f}.", ""]
    return "\n".join(L) + "\n"


def query_hash(qdf: pd.DataFrame) -> str:
    """SHA-256 of the sorted query keys (the fold manifests record it)."""
    lines = sorted(f"{r.query_id}\t{r.group}\t{r.site}\t{r.outcome_id}\t{r.crop}\t{r.comparator_class}\t{r.candidates}"
                   for r in qdf.itertuples())
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def write_queries(qdf: pd.DataFrame, idf: pd.DataFrame, out_dir: Path = HARNESS_DIR) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    qdf.to_parquet(out_dir / QUERIES_PARQUET.name, engine="pyarrow", index=False)
    idf.to_parquet(out_dir / ITEMS_PARQUET.name, engine="pyarrow", index=False)


def load_queries(out_dir: Path = HARNESS_DIR) -> tuple[pd.DataFrame, pd.DataFrame]:
    """The query table and its items (built by this module's CLI)."""
    q, i = out_dir / QUERIES_PARQUET.name, out_dir / ITEMS_PARQUET.name
    if not q.exists():
        raise FileNotFoundError(f"{q} not found: python -m model.harness.queries")
    return pd.read_parquet(q, engine="pyarrow"), pd.read_parquet(i, engine="pyarrow")


def build_all(store: pd.DataFrame, taxonomy: Any, dataset: pd.DataFrame | None, seed: int = 0
              ) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any], dict[str, Any]]:
    """Every query set plus the summary (with and without the comparator key)."""
    qdf, idf = build_queries(store, taxonomy, seed=seed, use_comparator=True)
    nc_q, _ = build_queries(store, taxonomy, seed=seed, use_comparator=False)
    if dataset is not None:
        label_to_id = {label: pid for pid, label in dataset_labels(store).items()}
        # the two ids with a second spelling (CROP_ROTATION 'rotation', DEFICIT_IRRIGATION_ERA) map every spelling
        rows = store[store["source"].isin(["ERA", "CSA"]) & store["practice_id"].notna()]
        for label, pid in zip(rows["practice_raw"], rows["practice_id"]):
            label_to_id.setdefault(str(label), str(pid))
        lq, li = legacy_queries(dataset, taxonomy, seed=seed, label_to_id=label_to_id)
        qdf, idf = pd.concat([qdf, lq], ignore_index=True), pd.concat([idf, li], ignore_index=True)
    elig = eligible_rows(store)
    summary = {"seed": seed, "store_rows": int(len(store)), "eligible_rows": int(len(elig)), "release": RELEASE,
               "counts": counts(qdf), "counts_without_comparator_key": counts(nc_q), "query_hash": query_hash(qdf),
               "n_queries": int(len(qdf)), "n_items": int(len(idf)),
               "queries_with_null_comparator": int(qdf[~qdf["legacy"]]["comparator_null"].sum()),
               "comparator_classes": {k: int(v) for k, v in qdf[~qdf["legacy"]]["comparator_class"].value_counts().items()}}
    return qdf, idf, counts(nc_q), summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build the harness query set from the evidence store")
    ap.add_argument("--store-dir", type=Path, default=REPO_ROOT / "data" / "evidence")
    ap.add_argument("--out-dir", type=Path, default=HARNESS_DIR)
    ap.add_argument("--dataset", type=Path, default=LEGACY_DATASET, help="frozen dataset for the legacy_68 cells")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO if a.verbose else logging.WARNING, format="%(levelname)s %(message)s")
    from pipelines.evidence import schema
    from pipelines.taxonomy import taxonomy_io as tio

    store = schema.read_store(a.store_dir)
    dataset = pd.read_csv(a.dataset) if a.dataset and Path(a.dataset).exists() else None
    qdf, idf, nc, summary = build_all(store, tio.Taxonomy.load(), dataset, seed=a.seed)
    write_queries(qdf, idf, a.out_dir)
    (a.out_dir / CARD.name).write_text(card_markdown(qdf, idf, nc, summary), encoding="utf-8")
    (a.out_dir / SUMMARY.name).write_text(json.dumps(summary, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "comparator_classes"}, indent=1))
    print(f"wrote {a.out_dir / QUERIES_PARQUET.name}, {a.out_dir / ITEMS_PARQUET.name}, {a.out_dir / CARD.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
