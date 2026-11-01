"""Evidence fusion — the best evidence leads, every number has a source (U9).

Binding rules: ``docs/decisions/evidence_fusion.md`` (owner, 1 Nov 2026) and
CLAUDE.md doctrine §1 as amended that day.

For each ranked practice this module builds an **evidence bundle**:

* the field-trial **model** estimate for the user's pin (the engine's own
  ``pct_change`` / ``log_ratio``, never re-estimated) with its confidence and
  the out-of-fold residual SD of the indicator as its uncertainty;
* the **study evidence**: one row per study that measured this practice for
  this indicator — the graph's ``REPORTS_EFFECT`` aggregation of dataset rows
  (``effect = exp(mean_log_rr) − 1``), with the between-observation SD / √n
  computed from the same rows, the match level of the study's belts against
  the user's (zone → altitude group → moisture class), and provenance;

then decides **who leads** (model / study), whether the two **disagree**, the
**headline** (a provenance object, or a range when they disagree) and the
**conservative bound** used for ordering. No number here is produced by a
language model; every number is a model output, a computation over dataset
rows, or a count.

Collaborators (graph query, study statistics, model uncertainty) are
injectable so tests run on synthetic data without rasters or the model.
"""
from __future__ import annotations

import json
import logging
import math
import statistics
from functools import lru_cache
from typing import Any, Callable, Iterable

from app.config import get_settings
from app.services import evidence_service as ev
from app.services.numbers import number

logger = logging.getLogger(__name__)

LEAD_MODEL, LEAD_STUDY, LEAD_DOCUMENTED = "model", "study", "documented"
#: Study match levels, best first (decision §3: zone → belt group → context class).
MATCH_ZONE, MATCH_GROUP, MATCH_MOISTURE, MATCH_OTHER = "zone", "belt_group", "moisture", "other"
MATCH_ORDER: tuple[str, ...] = (MATCH_ZONE, MATCH_GROUP, MATCH_MOISTURE)
STRONG_CONFIDENCE = {"medium", "high"}

StudyStats = dict[tuple[str, str, str], dict[str, float]]


# ------------------------------------------------------------ data sources
def pct(log_rr: float) -> float:
    """Response ratio on the log scale → % change (``exp(x) − 1``)."""
    return (math.exp(float(log_rr)) - 1.0) * 100.0


@lru_cache(maxsize=1)
def _dataset_study_stats() -> tuple[StudyStats, dict[str, float]]:
    """Per (study, practice, indicator): n, mean and SD of log RR; pooled SD per indicator.

    Read from the engine's own dataset frame (wrap, never fork: the frame is
    the one ``recommend.py`` loaded). The graph stores the same rows' mean
    but not their spread, which the conservative bound needs.
    """
    from app.services import recommender_service as svc

    df = svc.dataset_frame()
    grouped = df.groupby(["Study_No_", "CSA_practices", "Indicator"])["log_response_ratio"]
    stats: StudyStats = {}
    for (study, practice, indicator), values in grouped:
        vals = [float(v) for v in values]
        stats[(str(study), str(practice), str(indicator))] = {
            "n": float(len(vals)),
            "mean": statistics.fmean(vals),
            "sd": statistics.stdev(vals) if len(vals) > 1 else 0.0,
        }
    pooled = {str(ind): float(v.std(ddof=1)) for ind, v in df.groupby("Indicator")["log_response_ratio"]}
    return stats, pooled


@lru_cache(maxsize=1)
def _model_rmse() -> dict[str, float]:
    """Out-of-fold residual SD (RMSE, log scale) per indicator from the P7 evaluation."""
    path = get_settings().backend_root.parents[1] / "model" / "artifacts" / "model_eval.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        best = next(r for r in payload["runs"] if r.get("label") == payload["best"])
        return {ind: float(v["rmse"]["mean"]) for ind, v in best["per_indicator"].items()}
    except Exception as exc:  # optional: fall back to the pooled SD
        logger.warning("Model RMSE unavailable (%s) — pooled study SD used as model uncertainty.", exc)
        return {}


# --------------------------------------------------------------- matching
def match_level(study_belts: Iterable[str], user_belt: str | None) -> str:
    """How close a study's belts are to the user's: zone, altitude group, moisture or other."""
    user = ev.parse_belt(user_belt)
    if user is None:
        return MATCH_OTHER
    parsed = [p for p in (ev.parse_belt(b) for b in study_belts) if p]
    if any(p == user for p in parsed):
        return MATCH_ZONE
    if any(p[1] == user[1] for p in parsed):
        return MATCH_GROUP
    if any(p[0] == user[0] for p in parsed):
        return MATCH_MOISTURE
    return MATCH_OTHER


def study_rows(
    graph_query: Any,
    practice: str,
    indicator: str,
    user_belt: str | None,
    stats: StudyStats,
    pooled_sd: float,
) -> list[dict[str, Any]]:
    """Study evidence for one (practice, indicator), best-matched and largest first."""
    if graph_query is None:
        return []
    try:
        summary = graph_query.evidence_summary(practice, indicator)
    except Exception as exc:
        logger.warning("evidence_summary failed for %r (%s)", practice, exc)
        return []
    rows: list[dict[str, Any]] = []
    for st in summary.get("studies") or []:
        mean = st.get("mean_log_rr")
        n_obs = int(st.get("n_obs") or 0)
        if mean is None or n_obs <= 0:
            continue
        study_no = str(st.get("study_no"))
        row_stats = stats.get((study_no, practice, indicator)) or {}
        sd = float(row_stats.get("sd") or 0.0)
        se = sd / math.sqrt(n_obs) if n_obs > 1 and sd > 0 else pooled_sd
        obs_by_belt = {str(b): int(n) for b, n in (st.get("obs_by_belt") or {}).items()}
        belts = list(obs_by_belt) or list(st.get("aez_belts") or [])
        ref = f"study:{study_no}"
        rows.append({
            "ref": ref,
            "study_no": study_no,
            "era_code": st.get("era_code"),
            "title": st.get("title"),
            "year": st.get("year"),
            "doi": st.get("doi"),
            "data_source": st.get("data_source"),
            "n_obs": n_obs,
            "mean_log_rr": float(mean),
            "se_log": float(se),
            "effect": number(pct(float(mean)), "%", "study", ref),
            "share_positive": st.get("share_positive"),
            "aez_belts": belts,
            "obs_by_belt": obs_by_belt,
            "match": match_level(belts, user_belt),
        })
    rank = {m: i for i, m in enumerate((*MATCH_ORDER, MATCH_OTHER))}
    rows.sort(key=lambda r: (rank[r["match"]], -r["n_obs"], r["study_no"]))
    return rows


# --------------------------------------------------------------- decision
def _study_headline(lead: list[dict[str, Any]]) -> tuple[float, float]:
    """Median of the leading studies' mean log RR, and its standard error.

    SE of a mean of m study means: ``sqrt(Σ se_i²) / m`` (the median is
    summarised with the same SE — a documented approximation).
    """
    log_med = statistics.median(r["mean_log_rr"] for r in lead)
    se = math.sqrt(sum(r["se_log"] ** 2 for r in lead)) / len(lead)
    return float(log_med), float(se)


def fuse_practice(
    item: dict[str, Any],
    *,
    indicator: str,
    direction: int,
    confidence: str,
    user_belt: str | None,
    graph_query: Any,
    stats: StudyStats,
    pooled_sd: float,
    model_sd: float,
    settings: Any,
) -> dict[str, Any]:
    """The evidence bundle and lead decision for one ranked practice (decision §3–§4)."""
    practice = item["practice"]
    k = float(settings.confidence_k_sd)
    limits = ev.thresholds(settings)
    studies = study_rows(graph_query, practice, indicator, user_belt, stats, pooled_sd)
    user_zone = ev.zone_of(user_belt)
    # Observations measured in the user's moisture zone (exact per-belt counts;
    # a study without per-belt counts contributes nothing — never a guess).
    n_obs_in_zone = sum(
        n for st in studies for b, n in st["obs_by_belt"].items() if user_zone and ev.zone_of(b) == user_zone
    )

    model_log = float(item["log_ratio"])
    model = {
        **number(float(item["pct_change"]), "%", "model", "model"),
        "confidence": confidence,
        "n_obs": int(item.get("n_evidence") or 0),
        "n_studies": len(studies),
        "n_obs_in_zone": int(n_obs_in_zone),
        "se_log": model_sd,
    }

    lead_studies: list[dict[str, Any]] = []
    level = MATCH_OTHER
    for lv in MATCH_ORDER:
        lead_studies = [s for s in studies if s["match"] == lv]
        if lead_studies:
            level = lv
            break

    model_ok = confidence in STRONG_CONFIDENCE and n_obs_in_zone >= limits["min_obs_in_zone"]
    lead = LEAD_MODEL if model_ok or not lead_studies else LEAD_STUDY

    study_part: dict[str, Any] | None = None
    if lead_studies:
        log_med, se = _study_headline(lead_studies)
        refs = [s["ref"] for s in lead_studies]
        study_part = {
            **number(pct(log_med), "%", "study", refs[0] if len(refs) == 1 else ",".join(refs)),
            "refs": refs,
            "match": level,
            "n_studies": len(lead_studies),
            "n_obs": sum(s["n_obs"] for s in lead_studies),
            "log": log_med,
            "se_log": se,
        }

    disagreement = False
    if study_part is not None:
        m, s = model["value"], study_part["value"]
        opposite = (m > 0) != (s > 0) and abs(m) >= 1 and abs(s) >= 1
        disagreement = opposite or abs(m - s) > float(settings.evidence_disagree_pct)

    model_bound = direction * model_log - k * model_sd
    if lead == LEAD_MODEL:
        headline = {**{k_: model[k_] for k_ in ("value", "unit", "source", "ref", "display")}}
        bound = model_bound
    else:
        assert study_part is not None
        headline = {k_: study_part[k_] for k_ in ("value", "unit", "source", "ref", "display")}
        bound = direction * study_part["log"] - k * study_part["se_log"]
    if disagreement and study_part is not None:
        lo, hi = sorted((model["value"], study_part["value"]))
        headline = {**headline, "range": [number(lo, "%", "model" if lo == model["value"] else "study"),
                                          number(hi, "%", "model" if hi == model["value"] else "study")]}
        # The more cautious of the two bounds orders a contested practice.
        bound = min(model_bound, direction * study_part["log"] - k * study_part["se_log"])

    gain = direction * float(headline["value"])
    return {
        "practice": practice,
        "lead_source": lead,
        # Best match level among the studies (what a study-led headline speaks for).
        "match": level,
        "headline": headline,
        "disagreement": disagreement,
        "caution": direction > 0 and gain >= float(settings.headline_caution_pct),
        "model": model,
        "study": study_part,
        "studies": studies,
        "conservative_bound": bound,
    }


def fuse(
    model_payload: dict[str, Any],
    *,
    graph_query: Any,
    settings: Any = None,
    stats_fn: Callable[[], tuple[StudyStats, dict[str, float]]] | None = None,
    rmse_fn: Callable[[], dict[str, float]] | None = None,
) -> list[dict[str, Any]]:
    """Evidence bundles for every ranked practice of an engine payload, in engine order."""
    s = settings or get_settings()
    query = model_payload.get("query") or {}
    details = model_payload.get("details") or {}
    indicator = str(query.get("indicator"))
    direction = -1 if query.get("goal_direction") == "reduce" else 1
    confidence = str(details.get("confidence") or "low")
    user_belt = (details.get("context") or {}).get("aez_belt")
    try:
        stats, pooled = (stats_fn or _dataset_study_stats)()
    except Exception as exc:  # degrade: studies then use the pooled default below
        logger.warning("Study statistics unavailable (%s)", exc)
        stats, pooled = {}, {}
    pooled_sd = float(pooled.get(indicator) or 0.5)
    model_sd = float((rmse_fn or _model_rmse)().get(indicator) or pooled_sd)
    return [
        fuse_practice(
            item, indicator=indicator, direction=direction, confidence=confidence, user_belt=user_belt,
            graph_query=graph_query, stats=stats, pooled_sd=pooled_sd, model_sd=model_sd, settings=s,
        )
        for item in details.get("ranked") or []
    ]


def order(bundles: list[dict[str, Any]], how: str) -> list[dict[str, Any]]:
    """``conservative``: by the bound, best first (stable); ``model``: unchanged."""
    if how != "conservative":
        return list(bundles)
    return sorted(bundles, key=lambda b: -b["conservative_bound"])


# ------------------------------------------------------------- registers (A5)
def _words(language: str, n: int, one: str, many: str) -> str:
    from app.i18n import t

    return t(language, one if n == 1 else many)


def _dir_word(value: float, language: str) -> str:
    from app.i18n import t

    return t(language, "fusion.dir.less" if value < 0 else "fusion.dir.more")


def _abs_display(value: float) -> str:
    from app.services.numbers import display_text

    return display_text(abs(value))


def summary_text(bundle: dict[str, Any], indicator: str, language: str, practice_name: str | None = None) -> str:
    """Plain-language register: one sentence, no labels or citation markers.

    Its only numbers are the bundle's headline values (guarded upstream).
    """
    from app.i18n import t, term

    name = practice_name or bundle["practice"]
    ind = term(language, "indicator", indicator)
    head = bundle["headline"]
    if bundle.get("disagreement") and head.get("range"):
        lo, hi = head["range"]
        text = t(language, "fusion.summary.varies", practice=name, lo=lo["display"], hi=hi["display"], indicator=ind)
    elif bundle["lead_source"] == LEAD_STUDY:
        text = t(language, "fusion.summary.study", practice=name, value=_abs_display(head["value"]),
                 dir=_dir_word(head["value"], language), indicator=ind,
                 where=t(language, f"fusion.where.{bundle['match']}"))
    else:
        text = t(language, "fusion.summary.model", practice=name, value=_abs_display(head["value"]),
                 dir=_dir_word(head["value"], language), indicator=ind)
    if bundle.get("caution"):
        text += t(language, "fusion.caution")
    return text


def evidence_lines(
    bundle: dict[str, Any], indicator: str, language: str, ref_of: Callable[[str], str] | None = None,
    max_studies: int = 3,
) -> list[str]:
    """Labelled register: "Model estimate for your area: …", "Reported in study [n]: …".

    ``ref_of`` maps a study ref (``study:<no>``) to its visible citation
    number in the answer's registry; by default the study number itself.
    """
    from app.i18n import t, term

    ind = term(language, "indicator", indicator)
    m = bundle["model"]
    lines = [t(
        language, "fusion.label.model", value=_abs_display(m["value"]), dir=_dir_word(m["value"], language),
        indicator=ind, confidence=t(language, f"fusion.confidence.{m['confidence']}"),
        n_studies=m["n_studies"], studies_word=_words(language, m["n_studies"], "kc.study", "kc.studies"),
        n_obs=m["n_obs"], obs_word=_words(language, m["n_obs"], "eb.observation", "eb.observations"),
    )]
    lead_refs = set((bundle.get("study") or {}).get("refs") or [])
    shown = [s for s in bundle["studies"] if s["ref"] in lead_refs] or bundle["studies"]
    for st in shown[:max_studies]:
        about = f" ({', '.join(str(x) for x in (st.get('title'), st.get('year')) if x)})" if st.get("title") else ""
        lines.append(t(
            language, "fusion.label.study", ref=(ref_of or (lambda r: r.split(':', 1)[1]))(st["ref"]), about=about,
            value=_abs_display(st["effect"]["value"]), dir=_dir_word(st["effect"]["value"], language), indicator=ind,
            n_obs=st["n_obs"], obs_word=_words(language, st["n_obs"], "eb.observation", "eb.observations"),
        ))
    if bundle.get("disagreement"):
        lines.append(t(language, "fusion.label.disagree"))
    return lines