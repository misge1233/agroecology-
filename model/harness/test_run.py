"""The runner end to end on a fixture store (E4 Part 5): prediction format, metrics,
config hashes, report and figures, determinism of two runs."""
from __future__ import annotations

import json

import pandas as pd

from model.harness import folds as hf
from model.harness import queries as hq
from model.harness import run as hr
from rag.test_mask_canary import Tax, fixture_store


def _prepare(tmp_path):
    store = fixture_store()
    queries, items = hq.build_queries(store, Tax(), aez_lookup={7: "Moist Dega"})
    harness = tmp_path / "harness"
    harness.mkdir()
    hq.write_queries(queries, items, harness)
    for split, name in (("spatial", hf.FOLDS_SPATIAL.name), ("study", hf.FOLDS_STUDY.name)):
        df, _ = hf.build_folds(queries, split)
        hf.write_folds(df, harness / name)
    return store, queries, items, harness


def test_runner_writes_predictions_metrics_config_and_report(tmp_path):
    store, queries, items, harness = _prepare(tmp_path)
    tax = Tax()
    tax.practices = pd.DataFrame([{"practice_id": p, "practice_family": "F"} for p in "ABC"])
    kw = dict(harness_dir=harness, out_dir=tmp_path / "runs", queries_override=queries, items_override=items,
              store_override=store, taxonomy_override=tax, report=False)
    run_a = hr.run(["random", "practice_prior", "nearest_studies"], ["spatial", "study"], reps=2, query_set="ET",
                   run_id="t1", **kw)
    preds = pd.read_parquet(run_a / "predictions.parquet")
    assert list(preds.columns) == hr.PREDICTION_COLUMNS
    assert set(preds["method"]) == {"random", "practice_prior", "nearest_studies"} and set(preds["split"]) == {"spatial", "study"}
    # every held-out query of every rep has a row per candidate for every method
    n_cands = queries.set_index("query_id")["n_practices"]
    per = preds.groupby(["method", "split", "rep", "query_id"]).size()
    assert (per.reset_index(level=3)["query_id"].map(n_cands).to_numpy() == per.to_numpy()).all()
    assert per.reset_index().groupby(["method", "split", "rep"])["query_id"].nunique().eq(len(queries)).all()
    metrics = json.loads((run_a / "metrics.json").read_text(encoding="utf-8"))
    assert set(metrics["aggregate"]) == {"random", "practice_prior", "nearest_studies"}
    agg = metrics["aggregate"]["practice_prior"]["study"]
    assert agg["n_queries"]["mean"] == len(queries) and 0 <= agg["c_index"]["mean"] <= 1
    assert "objective_group" in metrics["breakdowns"] and metrics["random_expectation"]["c_index"] == 0.5
    config = json.loads((run_a / "config.json").read_text(encoding="utf-8"))
    assert config["run_id"] == "t1" and config["query_hash"] == hq.query_hash(queries)
    assert set(config["fold_files"]) == {"spatial", "study"} and config["methods"]["nearest_studies"]["k"] == 10
    assert config["release"] == "ET/2026.1"
    # the random engine gives no numbers; the prior does, with intervals
    rnd = preds[preds["method"] == "random"]
    assert rnd["est_lrr"].isna().all() and not rnd["abstain"].any()
    prior = preds[(preds["method"] == "practice_prior") & ~preds["abstain"]]
    assert prior["est_lrr"].notna().all() and (prior["lo"] <= prior["est_lrr"]).all()
    # determinism: a second run gives identical metrics to the third decimal
    run_b = hr.run(["random", "practice_prior", "nearest_studies"], ["spatial", "study"], reps=2, query_set="ET",
                   run_id="t2", **kw)
    assert hr.compare_runs(run_a, run_b) == []
    pa = pd.read_parquet(run_a / "predictions.parquet").drop(columns="run_id")
    pb = pd.read_parquet(run_b / "predictions.parquet").drop(columns="run_id")
    pd.testing.assert_frame_equal(pa, pb)
    # the report and its figures
    from model.harness.report import write_report

    pq = pd.read_parquet(run_a / "per_query.parquet")
    path = write_report(run_a, metrics, config, pd.read_parquet(run_a / "predictions.parquet"), items, queries, pq,
                        reports_dir=tmp_path / "reports")
    text = path.read_text(encoding="utf-8")
    assert "How to read this" in text and "## Headline, full coverage (spatial split)" in text and "n < 20" in text
    assert "## Common subset (spatial split" in text and "## Paired differences" in text
    abstaining = [m for m, a in preds.groupby("method")["abstain"].any().items() if a]
    for m in abstaining:  # every abstaining method has its full-coverage variant in the report
        assert f"{m}+prior" in text
    assert set(json.loads((run_a / "metrics.json").read_text(encoding="utf-8"))["full_coverage"]["methods"]) >= {"random", "practice_prior"}
    figs = tmp_path / "reports" / "figures" / "t1"
    assert (figs / "coverage_accuracy_spatial.png").exists() and (figs / "calibration_study.png").exists()
    assert "figures/t1/coverage_accuracy_spatial.png" in text
    assert "index_hash" in text and "practice_prior" in text


def test_query_set_selection_and_empty_set():
    q = pd.DataFrame({"query_id": ["a", "b", "c"], "query_set": ["ET", "global", "legacy_68"],
                      "post_2024": [True, False, False], "legacy": [False, False, True]})
    assert hr.select_queries(q, "ET")["query_id"].tolist() == ["a"]
    assert hr.select_queries(q, "all")["query_id"].tolist() == ["a", "b"]
    assert hr.select_queries(q, "post_2024")["query_id"].tolist() == ["a"]
    assert hr.select_queries(q, "legacy_68")["query_id"].tolist() == ["c"]
