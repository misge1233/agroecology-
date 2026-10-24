#!/usr/bin/env python3
"""
evaluate.py  -  the model evaluation protocol (Phase P7).

Replaces the single ad-hoc ``GroupKFold(5)`` pass that ``train_model.py``
used to run with a protocol that is **deterministic, repeated, and honest
about what a ranking tool is for**:

* **Deterministic folds.** Fold membership is read from
  ``data/processed/cv_folds.csv`` (written by
  ``pipelines/dataset/assign_folds.py``), never recomputed with
  ``GroupKFold`` — whose numpy tie-breaking gave three different splits, three
  different baselines and two different winning models across three machines
  (P6a.1 review, 24 Oct 2026).
* **Repeated grouped CV.** Every number is reported as **mean +- sd across
  the 10 fold repetitions**, so a result can be read together with its
  fold-choice uncertainty instead of being quoted off one lucky split.
* **Ranking metrics as the headline.** The product ranks practices for one
  pin; R² on individual rows is a secondary statistic. Within each
  (study, indicator) cell comparing >= 3 distinct practices we report
  Spearman rho, top-1 hit rate (against its own chance level), top-half hit
  rate and pairwise concordance (C-index).
* **Reference rows that frame the R².** A random 5-fold split (the leakage
  ablation: rows of the same study on both sides) and three in-sample
  noise ceilings, so a grouped R² of ~0.2 can be read against both the
  leakage number and the maximum any model could reach.

Direction semantics are NOT redefined here: the sign convention comes from
``recommend.DIRECTION`` (imported; see :func:`direction_map`).

Usage:
    python model/evaluate.py                 # full protocol, writes model_eval.json
    python model/evaluate.py --quick         # 2 repetitions, 1 setting per model
    python model/evaluate.py --no-grid       # skip the hyper-parameter search

Requires: pandas, numpy, scikit-learn.
"""
from __future__ import annotations

import argparse
import ast
import json
import logging
import sys
from dataclasses import dataclass, field
from itertools import product
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.metrics import balanced_accuracy_score, mean_squared_error, r2_score, roc_auc_score

REPO_ROOT = Path(__file__).resolve().parents[1]
DATASET_PATH = REPO_ROOT / "data" / "processed" / "CSA_ERA_final_model_ready.csv"
FOLDS_PATH = REPO_ROOT / "data" / "processed" / "cv_folds.csv"
RECOMMEND_PY = REPO_ROOT / "app" / "backend" / "recommend.py"

if str(REPO_ROOT / "pipelines" / "dataset") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "pipelines" / "dataset"))
from assign_folds import load_folds  # noqa: E402  (the canonical fold reader)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------- contract
# These must stay exactly as train_model.py has always written them: the
# artefact they describe is loaded by app/backend/recommend.py.
CAT = ["CSA_practices", "practice_family", "Crop_group", "crop_type",
       "aez_belt", "Indicator", "land_cover"]
NUM = ["Rainfall", "Altitude_r", "temp_mean_annual", "precip_seasonality",
       "slope", "soil_clay"]
FEATURES = CAT + NUM
TARGET = "log_response_ratio"
GROUP = "Study_No_"

#: P7 item 4 — reported as an ablation only, never adopted: changing the
#: serving feature set is a separate decision because recommend.py would
#: have to supply these at prediction time.
EXTRA_NUM = ["lgp_days", "soil_ph", "soil_soc"]

PROTOCOL_NAME = "grouped-cv-10x5-deterministic"
MIN_PRACTICES_PER_CELL = 3
CONFIDENCE_THRESHOLDS = (0.10, 0.0)   # >= high, >= medium, else low


# ------------------------------------------------------- direction semantics
_DIRECTION: dict[str, int] | None = None
_DIRECTION_SOURCE = "unloaded"


def direction_map() -> dict[str, int]:
    """``recommend.DIRECTION`` — the single source of "which way is better".

    Imports the engine when its dependencies are installed; otherwise reads
    the same literal out of ``recommend.py`` with :mod:`ast`. Both paths read
    the one definition, so the values cannot drift (the mechanism mirrors
    ``rag/graph/indicator_map.py``).
    """
    global _DIRECTION, _DIRECTION_SOURCE
    if _DIRECTION is not None:
        return dict(_DIRECTION)
    backend = str(RECOMMEND_PY.parent)
    added = backend not in sys.path
    if added:
        sys.path.insert(0, backend)
    try:
        import recommend  # type: ignore[import-not-found]

        _DIRECTION, _DIRECTION_SOURCE = dict(recommend.DIRECTION), "import recommend"
    except Exception as exc:
        logger.debug("recommend import unavailable (%s); parsing source", exc)
        tree = ast.parse(RECOMMEND_PY.read_text(encoding="utf-8"), str(RECOMMEND_PY))
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "DIRECTION" for t in node.targets
            ):
                _DIRECTION = {str(k): int(v) for k, v in ast.literal_eval(node.value).items()}
                _DIRECTION_SOURCE = "ast parse of recommend.py"
                break
        else:  # pragma: no cover
            raise ValueError(f"no DIRECTION assignment found in {RECOMMEND_PY}")
    finally:
        if added and backend in sys.path:
            sys.path.remove(backend)
    return dict(_DIRECTION)


def direction_source() -> str:
    """How the direction map was obtained (reported in the artefact)."""
    direction_map()
    return _DIRECTION_SOURCE


def align(values: np.ndarray, indicators: Sequence[str]) -> np.ndarray:
    """Multiply by +-1 so that **higher is always better**.

    ``soil loss`` and ``runoff`` are lower-is-better in
    ``recommend.DIRECTION``; aligning lets one ranking metric serve all seven
    indicators.
    """
    directions = direction_map()
    return np.asarray(values, dtype=float) * np.array(
        [directions[i] for i in indicators], dtype=float
    )


# ------------------------------------------------------------------ encoding
def build_cat_maps(df: pd.DataFrame, cat: Sequence[str] = CAT) -> dict[str, dict[str, int]]:
    """Category -> {level: code}; identical to what train_model.py always did."""
    return {c: {v: i for i, v in enumerate(sorted(df[c].astype(str).unique()))}
            for c in cat}


def encode(df: pd.DataFrame, cmaps: dict[str, dict[str, int]],
           features: Sequence[str] = FEATURES,
           cat: Sequence[str] = CAT) -> pd.DataFrame:
    """Ordinal-encode the categoricals, pass the numerics through as float."""
    X = pd.DataFrame(index=df.index)
    for c in features:
        if c in cat:
            X[c] = df[c].astype(str).map(cmaps[c]).fillna(-1).astype(int)
        else:
            X[c] = df[c].astype(float)
    return X[list(features)]


# -------------------------------------------------------------------- models
@dataclass(frozen=True)
class ModelSpec:
    """One model configuration in the protocol."""

    family: str
    params: dict[str, Any]

    @property
    def label(self) -> str:
        if not self.params:
            return self.family
        inner = ",".join(f"{k}={v}" for k, v in sorted(self.params.items()))
        return f"{self.family}({inner})"


def make_model(spec: ModelSpec, cat_mask: list[bool]):
    """Instantiate a model from its spec. ``random_state`` is always fixed."""
    if spec.family == "RandomForest":
        return RandomForestRegressor(n_jobs=-1, random_state=0, **spec.params)
    if spec.family == "HistGBM":
        return HistGradientBoostingRegressor(
            categorical_features=cat_mask, l2_regularization=1.0,
            random_state=0, **spec.params,
        )
    raise ValueError(f"unknown model family: {spec.family}")


#: The defaults train_model.py has always used — the protocol's reference point.
DEFAULT_SPECS: tuple[ModelSpec, ...] = (
    ModelSpec("RandomForest", {"n_estimators": 150, "min_samples_leaf": 3}),
    ModelSpec("HistGBM", {"learning_rate": 0.06, "max_iter": 400, "min_samples_leaf": 20}),
)

#: P7 item 3 — the small honest grid.
GRID_SPECS: tuple[ModelSpec, ...] = tuple(
    ModelSpec("RandomForest", {"n_estimators": n, "min_samples_leaf": leaf})
    for leaf, n in product((3, 5, 10), (150, 400))
) + tuple(
    ModelSpec("HistGBM", {"learning_rate": lr, "max_iter": it, "min_samples_leaf": leaf})
    for lr, it, leaf in product((0.03, 0.06), (400, 800), (20, 50))
)


# ------------------------------------------------------------------- metrics
def spearman(a: Sequence[float], b: Sequence[float]) -> float:
    """Spearman rho with average ranks for ties (no scipy dependency).

    Returns ``nan`` when either side is constant, which is the honest answer
    for a cell where every practice scored the same.
    """
    ra, rb = _average_ranks(a), _average_ranks(b)
    if np.std(ra) == 0 or np.std(rb) == 0:
        return float("nan")
    return float(np.corrcoef(ra, rb)[0, 1])


def _average_ranks(values: Sequence[float]) -> np.ndarray:
    """Ranks 1..n, ties sharing their average rank."""
    arr = np.asarray(values, dtype=float)
    order = np.argsort(arr, kind="stable")
    ranks = np.empty(len(arr), dtype=float)
    ranks[order] = np.arange(1, len(arr) + 1, dtype=float)
    # average the ranks inside each tie group
    for value in np.unique(arr):
        tied = arr == value
        if tied.sum() > 1:
            ranks[tied] = ranks[tied].mean()
    return ranks


def concordance(truth: Sequence[float], pred: Sequence[float]) -> tuple[int, int]:
    """(concordant pairs, comparable pairs) for the C-index."""
    t, p = np.asarray(truth, float), np.asarray(pred, float)
    concordant = comparable = 0
    for i in range(len(t)):
        for j in range(i + 1, len(t)):
            if t[i] == t[j]:
                continue
            comparable += 1
            if (t[i] - t[j]) * (p[i] - p[j]) > 0:
                concordant += 1
            elif p[i] == p[j]:
                concordant += 0.5          # a tie in the prediction is half credit
    return concordant, comparable


def ranking_metrics(df: pd.DataFrame, pred: np.ndarray,
                    min_practices: int = MIN_PRACTICES_PER_CELL) -> dict[str, Any]:
    """Ranking skill inside (study, indicator) cells.

    A cell is one study's comparison of several practices for one indicator —
    exactly the comparison the product makes. Rows are averaged per practice
    first, so a practice measured twice does not count twice. Observed and
    predicted values are direction-aligned, so "higher is better" everywhere.

    ``top1_chance`` is the mean of 1/n_practices over the scored cells: the
    hit rate a coin would reach on these same cells.
    """
    aligned_truth = align(df[TARGET].to_numpy(), df["Indicator"].tolist())
    aligned_pred = align(np.asarray(pred, float), df["Indicator"].tolist())
    work = pd.DataFrame({
        "study": df[GROUP].to_numpy(),
        "indicator": df["Indicator"].to_numpy(),
        "practice": df["CSA_practices"].to_numpy(),
        "truth": aligned_truth,
        "pred": aligned_pred,
    })
    cell_means = work.groupby(["study", "indicator", "practice"], sort=True).mean().reset_index()

    rhos: list[float] = []
    top1: list[float] = []
    tophalf: list[float] = []
    chance: list[float] = []
    concordant = comparable = 0
    n_cells = 0
    for (_study, _indicator), cell in cell_means.groupby(["study", "indicator"], sort=True):
        n = len(cell)
        if n < min_practices:
            continue
        n_cells += 1
        truth = cell["truth"].to_numpy()
        pred_cell = cell["pred"].to_numpy()
        rho = spearman(truth, pred_cell)
        if not np.isnan(rho):
            rhos.append(rho)
        # top-1: is the predicted best also an observed best?
        best_pred = int(np.argmax(pred_cell))
        top1.append(float(truth[best_pred] == truth.max()))
        # top-half: is the predicted best in the observed upper half by rank?
        observed_rank = _average_ranks(truth)[best_pred]          # 1 = worst
        tophalf.append(float(observed_rank > n / 2))
        chance.append(1.0 / n)
        c, m = concordance(truth, pred_cell)
        concordant += c
        comparable += m

    def mean_or_nan(values: list[float]) -> float:
        return float(np.mean(values)) if values else float("nan")

    return {
        "n_cells": n_cells,
        "n_cells_with_rho": len(rhos),
        "spearman_mean": mean_or_nan(rhos),
        "spearman_median": float(np.median(rhos)) if rhos else float("nan"),
        "top1_hit_rate": mean_or_nan(top1),
        "top1_chance": mean_or_nan(chance),
        "tophalf_hit_rate": mean_or_nan(tophalf),
        "c_index": (concordant / comparable) if comparable else float("nan"),
        "n_comparable_pairs": comparable,
    }


def direction_metrics(df: pd.DataFrame, pred: np.ndarray) -> dict[str, Any]:
    """Can the model tell a beneficial practice from a harmful one?

    "Beneficial" is the sign of the direction-aligned log response ratio.
    The base rate is reported alongside, because on this evidence base a
    constant "always beneficial" guess already scores ~0.73 accuracy — only
    balanced accuracy and AUC say whether the model beats that.
    """
    truth = align(df[TARGET].to_numpy(), df["Indicator"].tolist()) > 0
    score = align(np.asarray(pred, float), df["Indicator"].tolist())
    base_rate = float(truth.mean())
    out: dict[str, Any] = {"base_rate_beneficial": base_rate, "n": int(len(truth))}
    if truth.all() or not truth.any():     # degenerate, e.g. a tiny test set
        out.update(balanced_accuracy=float("nan"), roc_auc=float("nan"),
                   accuracy=float("nan"))
        return out
    out["balanced_accuracy"] = float(balanced_accuracy_score(truth, score > 0))
    out["roc_auc"] = float(roc_auc_score(truth, score))
    out["accuracy"] = float((truth == (score > 0)).mean())
    return out


def regression_metrics(df: pd.DataFrame, y: np.ndarray, pred: np.ndarray) -> dict[str, Any]:
    """R² and RMSE overall, per indicator and per source."""
    indicators = df["Indicator"].to_numpy()
    sources = df["source"].to_numpy()
    return {
        "r2": float(r2_score(y, pred)),
        "rmse": float(mean_squared_error(y, pred) ** 0.5),
        "per_indicator": {
            str(i): {"n": int((indicators == i).sum()),
                     "r2": float(r2_score(y[indicators == i], pred[indicators == i])),
                     "rmse": float(mean_squared_error(y[indicators == i],
                                                      pred[indicators == i]) ** 0.5)}
            for i in sorted(set(indicators))
        },
        "per_source": {
            str(s): {"n": int((sources == s).sum()),
                     "r2": float(r2_score(y[sources == s], pred[sources == s]))}
            for s in sorted(set(sources))
        },
    }


# ------------------------------------------------------------- oof machinery
def baseline_oof(df: pd.DataFrame, test_mask: np.ndarray, oof: np.ndarray) -> None:
    """Mean-of-(practice, indicator) baseline, filled in place for one fold."""
    train = df.loc[~test_mask]
    cell_mean = train.groupby(["CSA_practices", "Indicator"])[TARGET].mean()
    grand = train[TARGET].mean()
    keys = zip(df.loc[test_mask, "CSA_practices"], df.loc[test_mask, "Indicator"])
    oof[test_mask] = [cell_mean.get(k, grand) for k in keys]


def fold_masks(df: pd.DataFrame, folds: dict[str, list[int]], rep: int,
               n_folds: int = 5) -> list[np.ndarray]:
    """Boolean test masks, one per fold, for one repetition."""
    assigned = df[GROUP].map(lambda s: folds[s][rep]).to_numpy()
    return [assigned == f for f in range(n_folds)]


def random_fold_masks(n_rows: int, rep: int, n_folds: int = 5) -> list[np.ndarray]:
    """Row-level random folds for the LEAKAGE ablation (study-blind broken).

    Deterministic per repetition via :class:`random.Random`, so the ablation
    is as reproducible as the grouped protocol it is contrasted with.
    """
    import random

    order = list(range(n_rows))
    random.Random(1000 + rep).shuffle(order)
    assigned = np.empty(n_rows, dtype=int)
    for position, row in enumerate(order):
        assigned[row] = position % n_folds
    return [assigned == f for f in range(n_folds)]


def out_of_fold(df: pd.DataFrame, X: pd.DataFrame, y: np.ndarray,
                masks: list[np.ndarray], spec: ModelSpec | None,
                cat_mask: list[bool]) -> np.ndarray:
    """Out-of-fold predictions for one repetition.

    ``spec=None`` runs the mean baseline instead of fitting a model.
    """
    oof = np.full(len(y), np.nan)
    for test_mask in masks:
        if not test_mask.any():
            continue
        if spec is None:
            baseline_oof(df, test_mask, oof)
            continue
        model = make_model(spec, cat_mask)
        model.fit(X.loc[~test_mask], y[~test_mask])
        oof[test_mask] = model.predict(X.loc[test_mask])
    if np.isnan(oof).any():  # pragma: no cover - guards a malformed fold file
        raise RuntimeError("fold assignment left rows without a prediction")
    return oof


# ------------------------------------------------------------ the protocol
@dataclass
class EvalRun:
    """Everything the protocol measured for one model specification."""

    label: str
    family: str
    params: dict[str, Any]
    per_rep: list[dict[str, Any]] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        """mean +- sd of every scalar metric across the repetitions."""
        return {
            "label": self.label,
            "family": self.family,
            "params": self.params,
            "n_reps": len(self.per_rep),
            **_aggregate(self.per_rep),
        }


def _aggregate(per_rep: list[dict[str, Any]]) -> dict[str, Any]:
    """Recursively mean/sd every numeric leaf across repetitions."""
    if not per_rep:
        return {}
    out: dict[str, Any] = {}
    for key, first in per_rep[0].items():
        values = [rep[key] for rep in per_rep if key in rep]
        if isinstance(first, dict):
            out[key] = _aggregate(values)
        elif isinstance(first, (int, float)) and not isinstance(first, bool):
            arr = np.array([float(v) for v in values], dtype=float)
            finite = arr[np.isfinite(arr)]
            out[key] = {
                "mean": float(finite.mean()) if finite.size else float("nan"),
                "sd": float(finite.std(ddof=1)) if finite.size > 1 else 0.0,
            }
        else:
            out[key] = first
    return out


def evaluate_spec(df: pd.DataFrame, X: pd.DataFrame, y: np.ndarray,
                  folds: dict[str, list[int]], spec: ModelSpec | None,
                  cat_mask: list[bool], n_reps: int, label: str | None = None,
                  masks_for_rep: Callable[[int], list[np.ndarray]] | None = None,
                  ) -> EvalRun:
    """Run one model specification over ``n_reps`` fold repetitions."""
    run = EvalRun(
        label=label or (spec.label if spec else "Baseline(practice x indicator mean)"),
        family=spec.family if spec else "Baseline",
        params=dict(spec.params) if spec else {},
    )
    for rep in range(n_reps):
        masks = masks_for_rep(rep) if masks_for_rep else fold_masks(df, folds, rep)
        oof = out_of_fold(df, X, y, masks, spec, cat_mask)
        run.per_rep.append({
            **regression_metrics(df, y, oof),
            "ranking": ranking_metrics(df, oof),
            "direction": direction_metrics(df, oof),
        })
        logger.info("  %-52s rep%-2d R2 %.3f", run.label, rep, run.per_rep[-1]["r2"])
    return run


def noise_ceilings(df: pd.DataFrame, y: np.ndarray) -> dict[str, Any]:
    """In-sample R² of group means — the most any model could explain.

    None of these is achievable out of sample; they say how much of the
    target is study effect and how much is irreducible replicate noise.
    """
    def cell_r2(keys: list[str]) -> float:
        fitted = df.groupby(keys)[TARGET].transform("mean").to_numpy()
        return float(r2_score(y, fitted))

    return {
        "study_practice_indicator_means": cell_r2([GROUP, "CSA_practices", "Indicator"]),
        "study_indicator_means": cell_r2([GROUP, "Indicator"]),
        "practice_indicator_means": cell_r2(["CSA_practices", "Indicator"]),
    }


CONFIDENCE_K_SD = 1.0   # the lower end of mean - k*sd must clear a threshold


def confidence_flags(per_indicator: dict[str, Any],
                     k_sd: float = CONFIDENCE_K_SD) -> dict[str, str]:
    """Per-indicator confidence from the LOWER END of the repeated-CV band.

    Thresholds are unchanged (>=0.10 high, >=0 medium, else low), but the
    value tested is ``mean - k_sd * sd`` of the per-indicator grouped R²
    across the repetitions, not the mean alone: a flag is granted only when
    the whole ±1 sd band clears the cut-off (reviewer decision, 24 Oct 2026,
    after `yield` cleared 0.10 by 0.0004 on the mean). With no sd available
    (single split) the mean is used, as before.
    """
    high, medium = CONFIDENCE_THRESHOLDS
    flags: dict[str, str] = {}
    for indicator, stats in per_indicator.items():
        r2 = stats["r2"]
        if isinstance(r2, dict):
            lower = r2["mean"] - k_sd * float(r2.get("sd") or 0.0)
        else:
            lower = float(r2)
        flags[indicator] = "high" if lower >= high else ("medium" if lower >= medium else "low")
    return flags


def run_protocol(dataset_path: Path = DATASET_PATH, folds_path: Path = FOLDS_PATH,
                 n_reps: int | None = None, grid: bool = True,
                 ablations: bool = True, quick: bool = False) -> dict[str, Any]:
    """Run the whole protocol and return the ``model_eval.json`` payload."""
    df = pd.read_csv(dataset_path)
    folds = load_folds(folds_path)
    missing = set(df[GROUP]) - set(folds)
    if missing:
        raise ValueError(
            f"{len(missing)} studies have no fold assignment (e.g. {sorted(missing)[:3]}) "
            "— re-run pipelines/dataset/assign_folds.py"
        )
    available_reps = len(next(iter(folds.values())))
    n_reps = min(n_reps or (2 if quick else available_reps), available_reps)

    cmaps = build_cat_maps(df)
    X = encode(df, cmaps)
    y = df[TARGET].to_numpy(dtype=float)
    cat_mask = [c in CAT for c in FEATURES]

    specs = list(DEFAULT_SPECS)
    if grid and not quick:
        specs = [s for s in GRID_SPECS]
        for default in DEFAULT_SPECS:          # make sure the incumbents are in
            if default not in specs:
                specs.append(default)
    elif quick:
        specs = [DEFAULT_SPECS[0]]

    logger.info("protocol: %d repetitions x 5 folds, %d model settings",
                n_reps, len(specs))

    runs: list[EvalRun] = [
        evaluate_spec(df, X, y, folds, None, cat_mask, n_reps)      # baseline
    ]
    for spec in specs:
        runs.append(evaluate_spec(df, X, y, folds, spec, cat_mask, n_reps))

    model_runs = [r for r in runs if r.family != "Baseline"]
    best = max(model_runs, key=lambda r: (r.summary()["r2"]["mean"],
                                          -_complexity(r), r.label))
    # ties -> simpler model: _complexity is negated above so the smaller wins

    payload: dict[str, Any] = {
        "protocol": PROTOCOL_NAME,
        "fold_file": str(folds_path.relative_to(REPO_ROOT))
        if folds_path.is_relative_to(REPO_ROOT) else str(folds_path),
        "n_reps": n_reps,
        "n_folds": 5,
        "n_rows": int(len(df)),
        "n_groups": int(df[GROUP].nunique()),
        "features": FEATURES,
        "direction_source": direction_source(),
        "min_practices_per_cell": MIN_PRACTICES_PER_CELL,
        "runs": [r.summary() for r in runs],
        "best": best.label,
        "noise_ceiling": noise_ceilings(df, y),
    }

    if ablations:
        logger.info("leakage ablation: random 5-fold with %s", best.label)
        spec = ModelSpec(best.family, best.params)
        leakage = evaluate_spec(
            df, X, y, folds, spec, cat_mask, n_reps,
            label=f"{best.label} [random 5-fold = LEAKAGE]",
            masks_for_rep=lambda rep: random_fold_masks(len(df), rep),
        )
        payload["leakage_ablation"] = leakage.summary()

        logger.info("feature ablation: + %s", ", ".join(EXTRA_NUM))
        extra_features = FEATURES + EXTRA_NUM
        X_extra = encode(df, cmaps, features=extra_features)
        extra_mask = [c in CAT for c in extra_features]
        extra = evaluate_spec(
            df, X_extra, y, folds, spec, extra_mask, n_reps,
            label=f"{best.label} + {'+'.join(EXTRA_NUM)}",
        )
        payload["feature_ablation"] = {
            "added_features": EXTRA_NUM,
            "adopted": False,
            "note": "report only — adopting these would change the serving "
                    "feature contract recommend.py depends on",
            **extra.summary(),
        }
        gain = extra.summary()["r2"]["mean"] - best.summary()["r2"]["mean"]
        sd = best.summary()["r2"]["sd"]
        payload["feature_ablation"]["r2_gain"] = gain
        payload["feature_ablation"]["exceeds_one_sd"] = bool(abs(gain) > sd > 0)

    payload["indicator_confidence"] = confidence_flags(best.summary()["per_indicator"])
    return payload


def _complexity(run: EvalRun) -> int:
    """Rough size of a fitted model, for breaking ties toward the simpler one."""
    params = run.params
    return int(params.get("n_estimators", 0)) + int(params.get("max_iter", 0))


# ------------------------------------------------------------------ report
def _ms(stat: dict[str, Any] | None, places: int = 3, pct: bool = False) -> str:
    """Render a {mean, sd} pair as ``mean ± sd`` (or ``—`` when absent)."""
    if not isinstance(stat, dict) or "mean" not in stat:
        return "—"
    mean, sd = stat["mean"], stat.get("sd", 0.0)
    if not np.isfinite(mean):
        return "—"
    if pct:
        return f"{mean:.1%} ± {sd:.1%}" if sd else f"{mean:.1%}"
    return f"{mean:.{places}f} ± {sd:.{places}f}"


def threshold_margins(per_indicator: dict[str, Any],
                      within_sd: float = 0.25) -> list[dict[str, Any]]:
    """Indicators whose mean R² lands within ``within_sd`` of a flag cut-off.

    Repeated CV stops a flag flipping with fold luck, but it cannot decide
    one that sits ON the threshold — that is a policy question about where
    the cut-offs are, and the report says so rather than presenting a coin
    flip as a finding.
    """
    out: list[dict[str, Any]] = []
    for indicator, stats in sorted(per_indicator.items()):
        r2 = stats["r2"]["mean"] if isinstance(stats.get("r2"), dict) else stats["r2"]
        sd = stats["r2"].get("sd", 0.0) if isinstance(stats.get("r2"), dict) else 0.0
        if not sd:
            continue
        for threshold in CONFIDENCE_THRESHOLDS:
            margin = r2 - threshold
            if abs(margin) <= within_sd * sd:
                out.append({"indicator": indicator, "r2": r2, "sd": sd,
                            "threshold": threshold, "margin": margin,
                            "margin_in_sd": abs(margin) / sd})
                break
    return out


def format_report(payload: dict[str, Any]) -> str:
    """Render ``model_eval.json`` as the paper-ready markdown report."""
    runs = payload["runs"]
    best = next(r for r in runs if r["label"] == payload["best"])
    baseline = next(r for r in runs if r["family"] == "Baseline")
    ceiling = payload["noise_ceiling"]
    leakage = payload.get("leakage_ablation")
    ablation = payload.get("feature_ablation")
    L: list[str] = []

    L.append("# Model evaluation — AgroAdvisor-ET response-ratio model")
    L.append("")
    L.append("**Generated by `model/evaluate.py`; every number in this file comes "
             "from `model/artifacts/model_eval.json`. Do not edit by hand.**")
    L.append("")
    L.append(f"- Protocol: `{payload['protocol']}` — "
             f"{payload['n_reps']} repetitions x {payload['n_folds']} grouped folds")
    L.append(f"- Folds: `{payload['fold_file']}` (deterministic, pure-Python; "
             "see `pipelines/dataset/assign_folds.py`)")
    L.append(f"- Data: {payload['n_rows']:,} rows, {payload['n_groups']} studies, "
             f"grouped by `Study_No_`")
    L.append(f"- Direction semantics: `recommend.DIRECTION` "
             f"({payload['direction_source']})")
    L.append("- Every figure below is **mean ± sd across the repetitions**. The sd "
             "is the fold-choice uncertainty, which is exactly what a single "
             "`GroupKFold` pass hides.")
    L.append("")

    L.append("## 1. Protocol comparison — what the R² means")
    L.append("")
    L.append("| protocol | R² | reading |")
    L.append("|---|---:|---|")
    L.append(f"| **Grouped CV by study (primary, honest)** | **{_ms(best['r2'])}** | "
             "no study appears on both sides; this is what a new pin gets |")
    if leakage:
        L.append(f"| Random 5-fold (leakage ablation) | {_ms(leakage['r2'])} | "
                 "rows of the same study in train and test — **not skill** |")
    L.append(f"| Ceiling: (study, practice, indicator) means, in sample | "
             f"{ceiling['study_practice_indicator_means']:.3f} | an oracle knowing "
             "the exact cell; the rest is replicate noise |")
    L.append(f"| Ceiling: (study, indicator) means, in sample | "
             f"{ceiling['study_indicator_means']:.3f} | the study (site/season) "
             "effect alone |")
    L.append(f"| Ceiling: (practice, indicator) means, in sample | "
             f"{ceiling['practice_indicator_means']:.3f} | practice effect with no "
             "study information |")
    L.append("")
    gap = ceiling["study_practice_indicator_means"]
    L.append(f"Reading: the random-split figure is leakage, not skill. Even an "
             f"oracle that knows the exact (study, practice, indicator) cell reaches "
             f"only {gap:.2f}, so ~{1 - gap:.0%} of the target is within-cell "
             f"replicate noise that nothing can predict. A study-blind R² near "
             f"{best['r2']['mean']:.2f} should be read against that ceiling, not "
             f"against 1.0.")
    L.append("")

    L.append("## 2. Model comparison (grouped CV)")
    L.append("")
    L.append("| model | R² | RMSE | Spearman rho | top-1 | C-index |")
    L.append("|---|---:|---:|---:|---:|---:|")
    for run in sorted(runs, key=lambda r: -r["r2"]["mean"]):
        rank = run["ranking"]
        mark = " **← selected**" if run["label"] == payload["best"] else ""
        L.append(f"| `{run['label']}`{mark} | {_ms(run['r2'])} | {_ms(run['rmse'])} "
                 f"| {_ms(rank['spearman_mean'], 2)} "
                 f"| {_ms(rank['top1_hit_rate'], pct=True)} "
                 f"| {_ms(rank['c_index'], 2)} |")
    L.append("")
    L.append(f"Baseline (mean of practice x indicator): R² {_ms(baseline['r2'])}. "
             f"Selection rule: highest mean grouped R²; ties go to the simpler model.")
    L.append("")

    L.append("## 3. Ranking skill of the selected model")
    L.append("")
    rank = best["ranking"]
    L.append("This is the headline: the product ranks practices for one pin, so "
             "ranking skill matters more than row-level R². Scored inside "
             f"(study, indicator) cells comparing >= {payload['min_practices_per_cell']} "
             "distinct practices, after direction alignment.")
    L.append("")
    L.append("| metric | value | chance / reference |")
    L.append("|---|---:|---|")
    L.append(f"| cells scored | {rank['n_cells']['mean']:.0f} | of "
             f"{payload['n_groups']} studies x 7 indicators |")
    L.append(f"| Spearman rho (mean over cells) | {_ms(rank['spearman_mean'], 2)} | "
             "0 = no ordering skill |")
    L.append(f"| Spearman rho (median over cells) | {_ms(rank['spearman_median'], 2)} | |")
    L.append(f"| top-1 hit rate | {_ms(rank['top1_hit_rate'], pct=True)} | "
             f"chance {rank['top1_chance']['mean']:.1%} |")
    L.append(f"| top-half hit rate | {_ms(rank['tophalf_hit_rate'], pct=True)} | "
             "chance ~50% |")
    L.append(f"| pairwise concordance (C-index) | {_ms(rank['c_index'], 2)} | "
             f"0.50 = coin flip, over {rank['n_comparable_pairs']['mean']:.0f} pairs |")
    L.append("")
    direction = best["direction"]
    L.append("**Direction (beneficial vs harmful), reported honestly:**")
    L.append("")
    L.append("| metric | value |")
    L.append("|---|---:|")
    L.append(f"| base rate of beneficial observations | "
             f"{direction['base_rate_beneficial']['mean']:.1%} |")
    L.append(f"| accuracy | {_ms(direction['accuracy'], pct=True)} |")
    L.append(f"| balanced accuracy | {_ms(direction['balanced_accuracy'], 3)} |")
    L.append(f"| ROC-AUC | {_ms(direction['roc_auc'], 3)} |")
    L.append("")
    L.append("Plain accuracy is near the base rate, so it says nothing on its own; "
             "balanced accuracy and AUC are the figures to quote.")
    L.append("")

    L.append("## 4. Per-indicator and per-source (selected model)")
    L.append("")
    L.append("| indicator | n | R² | RMSE | confidence |")
    L.append("|---|---:|---:|---:|---|")
    for indicator, stats in sorted(best["per_indicator"].items()):
        flag = payload["indicator_confidence"].get(indicator, "—")
        L.append(f"| {indicator} | {stats['n']['mean']:.0f} | {_ms(stats['r2'])} "
                 f"| {_ms(stats['rmse'])} | {flag} |")
    L.append("")
    L.append("| source | n | R² |")
    L.append("|---|---:|---:|")
    for source, stats in sorted(best["per_source"].items()):
        L.append(f"| {source} | {stats['n']['mean']:.0f} | {_ms(stats['r2'])} |")
    L.append("")
    L.append("Confidence flags are derived from the **lower end of the mean ± 1 sd "
             "band** of the per-indicator grouped R² across the repetitions "
             "(mean − sd >= 0.10 high, >= 0 medium, else low): a flag is granted "
             "only when the whole band clears the cut-off, so it neither flips "
             "with fold luck nor rests on a coin-flip margin.")
    L.append("")
    borderline = threshold_margins(best["per_indicator"])
    if borderline:
        L.append("> **Flags sitting on a threshold.** Repeated CV removes fold luck, "
                 "but it cannot decide a flag whose R² lands on the cut-off. For "
                 "these indicators the margin is a small fraction of their own sd, "
                 "so the flag is effectively undetermined and is a policy choice "
                 "about where the thresholds sit, not a measurement:")
        L.append(">")
        L.append("> | indicator | mean R² | sd | threshold | margin | margin / sd |")
        L.append("> |---|---:|---:|---:|---:|---:|")
        for item in borderline:
            L.append(f"> | {item['indicator']} | {item['r2']:.4f} | {item['sd']:.4f} "
                     f"| {item['threshold']:.2f} | {item['margin']:+.4f} "
                     f"| {item['margin_in_sd']:.2f} |")
        L.append("")

    L.append("## 5. Hyper-parameter grid")
    L.append("")
    L.append("| family | parameters | R² | Spearman rho | top-1 |")
    L.append("|---|---|---:|---:|---:|")
    for run in sorted(runs, key=lambda r: (r["family"], -r["r2"]["mean"])):
        if run["family"] == "Baseline":
            continue
        params = ", ".join(f"{k}={v}" for k, v in sorted(run["params"].items()))
        L.append(f"| {run['family']} | {params} | {_ms(run['r2'])} "
                 f"| {_ms(run['ranking']['spearman_mean'], 2)} "
                 f"| {_ms(run['ranking']['top1_hit_rate'], pct=True)} |")
    L.append("")

    if ablation:
        L.append("## 6. Feature ablation (report only — NOT adopted)")
        L.append("")
        L.append(f"Adding {', '.join(f'`{f}`' for f in ablation['added_features'])} "
                 "to the 13 serving features. These are present in the dataset and "
                 "in the raster stack but are explanation-only in `recommend.py`.")
        L.append("")
        L.append("| feature set | R² | Spearman rho |")
        L.append("|---|---:|---:|")
        L.append(f"| 13 features (current) | {_ms(best['r2'])} "
                 f"| {_ms(best['ranking']['spearman_mean'], 2)} |")
        L.append(f"| + {' + '.join(ablation['added_features'])} | "
                 f"{_ms(ablation['r2'])} "
                 f"| {_ms(ablation['ranking']['spearman_mean'], 2)} |")
        L.append("")
        verdict = ("exceeds one sd — worth a decision"
                   if ablation.get("exceeds_one_sd")
                   else "within one sd of the current feature set — no evidence of gain")
        L.append(f"Gain: **{ablation['r2_gain']:+.4f} R²** ({verdict}). "
                 "Not adopted: it would change the serving feature contract that "
                 "`recommend.py` depends on, which is a separate decision.")
        L.append("")

    L.append("## 7. Reproducing this")
    L.append("")
    L.append("```bash")
    L.append("python pipelines/dataset/assign_folds.py    # only if cv_folds.csv is missing")
    L.append("python model/train_model.py                 # full protocol + artefacts")
    L.append("python -m pytest model/test_evaluate.py pipelines/dataset/test_assign_folds.py -q")
    L.append("```")
    L.append("")
    L.append("The fold file is committed, so the split is identical on every "
             "machine. Model internals can still differ slightly between library "
             "versions; the sd columns show how much fold choice alone moves each "
             "figure.")
    L.append("")
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[2])
    parser.add_argument("--dataset", type=Path, default=DATASET_PATH)
    parser.add_argument("--folds", type=Path, default=FOLDS_PATH)
    parser.add_argument("--n-reps", type=int, default=None)
    parser.add_argument("--no-grid", dest="grid", action="store_false",
                        help="evaluate only the two default settings")
    parser.add_argument("--no-ablations", dest="ablations", action="store_false")
    parser.add_argument("--quick", action="store_true",
                        help="2 repetitions, 1 setting — for tests and smoke runs")
    parser.add_argument("--out", type=Path,
                        default=REPO_ROOT / "model" / "artifacts" / "model_eval.json")
    parser.add_argument("--report", type=Path,
                        default=REPO_ROOT / "docs" / "reports" / "model_evaluation_report.md",
                        help="markdown report generated from the payload")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    payload = run_protocol(args.dataset, args.folds, args.n_reps,
                           grid=args.grid, ablations=args.ablations, quick=args.quick)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    logger.info("wrote %s", args.out)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(format_report(payload), encoding="utf-8")
        logger.info("wrote %s", args.report)
    logger.info("best: %s", payload["best"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
