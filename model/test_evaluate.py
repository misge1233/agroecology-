"""Unit tests for the P7 evaluation protocol.

Every metric is checked against a synthetic dataset whose answer is known by
construction: a perfect ranker must score rho = 1 and top-1 = 1, a reversed
one rho = -1 and top-1 = 0. The artefact-compatibility test loads a bundle
the way ``app/backend/recommend.py`` does and pushes one row through it, so
the serving contract cannot be broken silently — and it needs no rasters.

Run from the repo root:
    python -m pytest model/test_evaluate.py -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

MODEL_DIR = Path(__file__).resolve().parent
REPO_ROOT = MODEL_DIR.parents[0]
for _p in (str(MODEL_DIR), str(REPO_ROOT / "pipelines" / "dataset")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import evaluate as ev  # noqa: E402
import train_model as tm  # noqa: E402
from assign_folds import build_folds, write_folds  # noqa: E402


# --------------------------------------------------------------- fixtures
def make_df(n_studies: int = 12, practices: int = 4) -> pd.DataFrame:
    """A synthetic model-ready frame with the frozen column names.

    ``log_response_ratio`` is a clean function of the practice index, so a
    model can learn it and the ranking inside every (study, indicator) cell
    is known in advance.
    """
    rows = []
    for s in range(n_studies):
        for p in range(practices):
            for indicator in ("yield", "soil loss"):
                effect = (p + 1) * 0.1
                # soil loss is lower-is-better: store it with the opposite sign
                value = effect if indicator == "yield" else -effect
                rows.append({
                    "source": "ERA" if s % 2 else "CSA",
                    "Study_No_": f"ERA_S{s:03d}",
                    "CSA_practices": f"P{p}",
                    "practice_family": "Erosion control and water management",
                    "Crop_group": "Cereal",
                    "crop_type": "maize",
                    "Rainfall": 800.0 + s,
                    "Altitude_r": 2000.0,
                    "slope": 5.0,
                    "temp_mean_annual": 19.0,
                    "precip_seasonality": 70.0,
                    "lgp_days": 180.0,
                    "soil_clay": 30.0,
                    "soil_ph": 6.1,
                    "soil_soc": 1.2,
                    "land_cover": 40,
                    "aez_belt": "Dry Dega",
                    "Indicator": indicator,
                    "response_ratio": 1.0,
                    "log_response_ratio": value,
                })
    return pd.DataFrame(rows)


@pytest.fixture
def df() -> pd.DataFrame:
    return make_df()


@pytest.fixture
def folds_file(df, tmp_path) -> Path:
    sizes = df.groupby(ev.GROUP).size().to_dict()
    return write_folds(build_folds(sizes, n_folds=3, n_reps=2),
                       tmp_path / "cv_folds.csv", n_reps=2)


# ------------------------------------------------------------- direction
def test_direction_map_comes_from_recommend():
    directions = ev.direction_map()
    assert directions["yield"] == 1
    assert directions["soil loss"] == -1 and directions["runoff"] == -1
    assert "recommend" in ev.direction_source()


def test_align_flips_only_the_lower_is_better_indicators():
    values = np.array([0.5, 0.5])
    aligned = ev.align(values, ["yield", "soil loss"])
    assert aligned.tolist() == [0.5, -0.5]


# --------------------------------------------------------------- spearman
def test_spearman_on_known_sequences():
    assert ev.spearman([1, 2, 3, 4], [1, 2, 3, 4]) == pytest.approx(1.0)
    assert ev.spearman([1, 2, 3, 4], [4, 3, 2, 1]) == pytest.approx(-1.0)
    # monotone but non-linear -> still exactly 1 (that is the point of rho)
    assert ev.spearman([1, 2, 3, 4], [1, 10, 100, 1000]) == pytest.approx(1.0)


def test_spearman_is_nan_when_a_side_is_constant():
    assert np.isnan(ev.spearman([1, 2, 3], [5, 5, 5]))


def test_average_ranks_share_ties():
    assert ev._average_ranks([10, 20, 20, 30]).tolist() == [1.0, 2.5, 2.5, 4.0]


# ------------------------------------------------------------ concordance
def test_concordance_counts_pairs():
    assert ev.concordance([1, 2, 3], [1, 2, 3]) == (3, 3)
    assert ev.concordance([1, 2, 3], [3, 2, 1]) == (0, 3)
    # ties in the truth are not comparable; ties in the prediction score half
    assert ev.concordance([1, 1, 2], [5, 5, 9]) == (2, 2)
    assert ev.concordance([1, 2], [7, 7]) == (0.5, 1)


# -------------------------------------------------------- ranking metrics
def test_perfect_ranker_scores_one(df):
    """Predicting the truth exactly must give rho = 1 and top-1 = 1."""
    metrics = ev.ranking_metrics(df, df[ev.TARGET].to_numpy())
    assert metrics["n_cells"] == df.groupby([ev.GROUP, "Indicator"]).ngroups
    assert metrics["spearman_mean"] == pytest.approx(1.0)
    assert metrics["top1_hit_rate"] == pytest.approx(1.0)
    assert metrics["tophalf_hit_rate"] == pytest.approx(1.0)
    assert metrics["c_index"] == pytest.approx(1.0)


def test_reversed_ranker_scores_minus_one(df):
    metrics = ev.ranking_metrics(df, -df[ev.TARGET].to_numpy())
    assert metrics["spearman_mean"] == pytest.approx(-1.0)
    assert metrics["top1_hit_rate"] == pytest.approx(0.0)
    assert metrics["c_index"] == pytest.approx(0.0)


def test_top1_chance_is_one_over_the_cell_size(df):
    """Four practices per cell -> a coin flip lands the best 1 time in 4."""
    metrics = ev.ranking_metrics(df, df[ev.TARGET].to_numpy())
    assert metrics["top1_chance"] == pytest.approx(0.25)


def test_cells_below_the_minimum_are_skipped(df):
    small = df[df.CSA_practices.isin(["P0", "P1"])]          # 2 practices/cell
    assert ev.ranking_metrics(small, small[ev.TARGET].to_numpy())["n_cells"] == 0


def test_repeated_rows_for_one_practice_are_averaged_not_double_counted(df):
    doubled = pd.concat([df, df], ignore_index=True)
    once = ev.ranking_metrics(df, df[ev.TARGET].to_numpy())
    twice = ev.ranking_metrics(doubled, doubled[ev.TARGET].to_numpy())
    assert twice["n_cells"] == once["n_cells"]
    assert twice["n_comparable_pairs"] == once["n_comparable_pairs"]


def test_ranking_uses_direction_alignment(df):
    """Un-aligned, 'soil loss' cells would score -1 and halve the mean."""
    metrics = ev.ranking_metrics(df, df[ev.TARGET].to_numpy())
    soil_only = df[df.Indicator == "soil loss"]
    assert ev.ranking_metrics(soil_only,
                              soil_only[ev.TARGET].to_numpy())["spearman_mean"] \
        == pytest.approx(1.0)
    assert metrics["spearman_mean"] == pytest.approx(1.0)


# ------------------------------------------------------ direction metrics
def test_direction_metrics_on_a_perfect_and_an_inverted_predictor(df):
    """Needs both classes, so half the practices are made harmful here."""
    mixed = df.copy()
    harmful = mixed.CSA_practices.isin(["P0", "P1"])
    mixed.loc[harmful, ev.TARGET] = -mixed.loc[harmful, ev.TARGET]

    perfect = ev.direction_metrics(mixed, mixed[ev.TARGET].to_numpy())
    assert perfect["balanced_accuracy"] == pytest.approx(1.0)
    assert perfect["roc_auc"] == pytest.approx(1.0)
    assert perfect["base_rate_beneficial"] == pytest.approx(0.5)

    inverted = ev.direction_metrics(mixed, -mixed[ev.TARGET].to_numpy())
    assert inverted["roc_auc"] == pytest.approx(0.0)
    assert inverted["balanced_accuracy"] == pytest.approx(0.0)


def test_direction_metrics_degrade_gracefully_when_one_class_is_absent(df):
    """All-beneficial truth has no negatives: report nan, do not crash."""
    out = ev.direction_metrics(df, df[ev.TARGET].to_numpy())
    assert out["base_rate_beneficial"] == 1.0
    assert np.isnan(out["balanced_accuracy"])
    assert np.isnan(out["roc_auc"])


# --------------------------------------------------------------- protocol
def test_fold_masks_cover_every_row_exactly_once(df, folds_file):
    from assign_folds import load_folds

    folds = load_folds(folds_file)
    masks = ev.fold_masks(df, folds, rep=0, n_folds=3)
    stacked = np.vstack(masks)
    assert stacked.sum(axis=0).tolist() == [1] * len(df)


def test_grouped_folds_never_split_a_study(df, folds_file):
    from assign_folds import load_folds

    folds = load_folds(folds_file)
    for mask in ev.fold_masks(df, folds, rep=0, n_folds=3):
        studies_in = set(df.loc[mask, ev.GROUP])
        studies_out = set(df.loc[~mask, ev.GROUP])
        assert not (studies_in & studies_out)


def test_random_fold_masks_are_deterministic_and_complete(df):
    a = ev.random_fold_masks(len(df), rep=0)
    b = ev.random_fold_masks(len(df), rep=0)
    assert all((x == y).all() for x, y in zip(a, b))
    assert np.vstack(a).sum(axis=0).tolist() == [1] * len(df)
    # a different repetition gives a different split
    c = ev.random_fold_masks(len(df), rep=1)
    assert not all((x == y).all() for x, y in zip(a, c))


def test_noise_ceilings_are_ordered_as_expected(df):
    y = df[ev.TARGET].to_numpy()
    ceilings = ev.noise_ceilings(df, y)
    # the finest grouping explains at least as much as the coarser ones
    assert ceilings["study_practice_indicator_means"] >= ceilings["practice_indicator_means"]


def test_confidence_flags_use_the_documented_thresholds():
    # no sd (single split): the mean is tested, exactly as before
    per_indicator = {
        "yield": {"r2": {"mean": 0.25}},
        "income": {"r2": {"mean": 0.05}},
        "runoff": {"r2": {"mean": -0.3}},
        "edge": {"r2": {"mean": 0.10}},
    }
    assert ev.confidence_flags(per_indicator) == {
        "yield": "high", "income": "medium", "runoff": "low", "edge": "high",
    }


def test_confidence_flags_require_the_lower_band_to_clear_the_threshold():
    # with an sd, mean - 1 sd is tested: a coin-flip margin no longer grants a flag
    per_indicator = {
        "yield": {"r2": {"mean": 0.1004, "sd": 0.0264}},      # P7: cleared 0.10 by 0.0004
        "biomass yield": {"r2": {"mean": 0.078, "sd": 0.044}},
        "soil loss": {"r2": {"mean": -0.0012, "sd": 0.0503}},
        "solid": {"r2": {"mean": 0.20, "sd": 0.05}},
        "zero_sd": {"r2": {"mean": 0.10, "sd": 0.0}},
    }
    assert ev.confidence_flags(per_indicator) == {
        "yield": "medium", "biomass yield": "medium", "soil loss": "low",
        "solid": "high", "zero_sd": "high",
    }
    assert ev.confidence_flags(per_indicator, k_sd=0.0)["yield"] == "high"


def test_aggregate_reports_mean_and_sd():
    out = ev._aggregate([{"r2": 0.2, "sub": {"x": 1.0}}, {"r2": 0.4, "sub": {"x": 3.0}}])
    assert out["r2"]["mean"] == pytest.approx(0.3)
    assert out["r2"]["sd"] == pytest.approx(0.1414, abs=1e-3)
    assert out["sub"]["x"]["mean"] == pytest.approx(2.0)


def test_run_protocol_end_to_end_on_synthetic_data(df, folds_file, tmp_path):
    dataset = tmp_path / "ds.csv"
    df.to_csv(dataset, index=False)
    payload = ev.run_protocol(dataset, folds_file, n_reps=2, grid=False,
                              ablations=False)
    assert payload["protocol"] == ev.PROTOCOL_NAME
    assert payload["n_reps"] == 2
    assert payload["best"] in [r["label"] for r in payload["runs"]]
    assert set(payload["indicator_confidence"]) == {"yield", "soil loss"}
    for run in payload["runs"]:
        assert "mean" in run["r2"] and "sd" in run["r2"]
        assert run["ranking"]["n_cells"]["mean"] > 0


def test_protocol_rejects_a_fold_file_missing_studies(df, tmp_path):
    dataset = tmp_path / "ds.csv"
    df.to_csv(dataset, index=False)
    partial = write_folds({"ERA_S000": [0, 0]}, tmp_path / "partial.csv", n_reps=2)
    with pytest.raises(ValueError, match="no fold assignment"):
        ev.run_protocol(dataset, partial, n_reps=2, grid=False, ablations=False)


def test_model_specs_cover_the_briefed_grid():
    rf = [s for s in ev.GRID_SPECS if s.family == "RandomForest"]
    hgb = [s for s in ev.GRID_SPECS if s.family == "HistGBM"]
    assert {s.params["min_samples_leaf"] for s in rf} == {3, 5, 10}
    assert {s.params["n_estimators"] for s in rf} == {150, 400}
    assert {s.params["learning_rate"] for s in hgb} == {0.03, 0.06}
    assert {s.params["max_iter"] for s in hgb} == {400, 800}
    assert {s.params["min_samples_leaf"] for s in hgb} == {20, 50}
    assert len(ev.GRID_SPECS) == 6 + 8


# ----------------------------------------------- serving-artefact contract
def test_artefact_keys_and_one_prediction(df, folds_file, tmp_path):
    """Build the artefact and use it exactly as recommend.py does."""
    import joblib

    dataset = tmp_path / "ds.csv"
    df.to_csv(dataset, index=False)
    art = tmp_path / "art"
    assert tm.main(["--dataset", str(dataset), "--folds", str(folds_file),
                    "--artifacts", str(art), "--no-copy", "--no-report", "--quick",
                    "--no-ablations"]) == 0

    bundle = joblib.load(art / "csa_model.joblib")
    # the exact keys app/backend/recommend.py reads
    for key in ("model", "cat_maps", "features", "cat", "num", "cat_mask",
                "target", "model_name", "indicator_confidence"):
        assert key in bundle, key

    model = bundle["model"]
    cmaps = bundle["cat_maps"]
    feat = bundle["features"]
    cat = bundle["cat"]
    row = df.iloc[0].to_dict()
    encoded = {}
    for c in feat:                                   # recommend.py's own loop
        if c in cat:
            encoded[c] = cmaps[c].get(str(row.get(c)), -1)
        else:
            encoded[c] = float(row.get(c))
    prediction = model.predict(pd.DataFrame([encoded])[feat])
    assert prediction.shape == (1,) and np.isfinite(prediction[0])


def test_model_metrics_keeps_its_published_shape(df, folds_file, tmp_path):
    dataset = tmp_path / "ds.csv"
    df.to_csv(dataset, index=False)
    art = tmp_path / "art"
    tm.main(["--dataset", str(dataset), "--folds", str(folds_file),
             "--artifacts", str(art), "--no-copy", "--no-report", "--quick", "--no-ablations"])
    metrics = json.loads((art / "model_metrics.json").read_text(encoding="utf-8"))

    # keys the backend and the frontend read, with their original shapes
    assert isinstance(metrics["model"], str)
    assert isinstance(metrics["cv_r2"], float)
    for indicator, pair in metrics["per_indicator"].items():
        assert isinstance(pair, list) and len(pair) == 2      # [n, r2]
        assert isinstance(pair[0], int)
    assert set(metrics["indicator_confidence"]) == {"yield", "soil loss"}
    assert metrics["features"] == ev.FEATURES
    # P7 additions
    assert metrics["protocol"] == ev.PROTOCOL_NAME
    assert "cv_r2_sd" in metrics and "ranking_metrics" in metrics
    assert metrics["fold_file"]


def test_reuse_eval_does_not_rerun_the_protocol(df, folds_file, tmp_path):
    dataset = tmp_path / "ds.csv"
    df.to_csv(dataset, index=False)
    art = tmp_path / "art"
    tm.main(["--dataset", str(dataset), "--folds", str(folds_file),
             "--artifacts", str(art), "--no-copy", "--no-report", "--quick", "--no-ablations"])
    payload = json.loads((art / "model_eval.json").read_text(encoding="utf-8"))
    payload["best"] = payload["runs"][-1]["label"]
    marker = "SENTINEL-NOT-RECOMPUTED"
    payload["protocol"] = marker
    (art / "model_eval.json").write_text(json.dumps(payload), encoding="utf-8")

    tm.main(["--dataset", str(dataset), "--folds", str(folds_file),
             "--artifacts", str(art), "--no-copy", "--no-report", "--reuse-eval"])
    metrics = json.loads((art / "model_metrics.json").read_text(encoding="utf-8"))
    assert metrics["protocol"] == marker        # it read the file, did not re-run


def test_train_model_reexports_the_shared_contract():
    """train_model.py must not define a second copy of these."""
    assert tm.FEATURES is ev.FEATURES
    assert tm.CAT is ev.CAT and tm.NUM is ev.NUM
    assert tm.build_cat_maps is ev.build_cat_maps
