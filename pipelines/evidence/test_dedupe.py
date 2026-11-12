"""Cross-source duplicate flagging (E4 Part 0.3): rule, richness, determinism, card counts."""
from __future__ import annotations

import json

import pandas as pd

from pipelines.evidence import dedupe, schema


def _row(row_id, source, lrr=None, mw=None, mo=None, var=None, lat=None, extra=None, doi="10.1/x",
         practice="MULCH", outcome="YIELD"):
    return {"row_id": row_id, "source": source, "study_id": row_id.split(":")[1], "doi": doi, "citation": "c",
            "loc_precision": "site", "loc_method": "reported", "practice_id": practice, "practice_raw": "m",
            "outcome_id": outcome, "outcome_raw": "y", "direction": 1, "direction_reviewed": True,
            "mean_with": mw, "mean_without": mo, "lrr": lrr, "var_lrr": var, "lat": lat, "lon": lat,
            "weight": 1.0, "quality_flag": "NR", "licence": "l", "extra": json.dumps(extra) if extra else None}


def _store(rows):
    return schema.coerce(pd.DataFrame(rows))


def test_same_contrast_rules():
    a = pd.Series({"lrr": 0.300, "mean_with": 10.0, "mean_without": 8.0})
    assert dedupe.same_contrast(a, pd.Series({"lrr": 0.305, "mean_with": None, "mean_without": None})) == "lrr"
    assert dedupe.same_contrast(a, pd.Series({"lrr": None, "mean_with": 10.05, "mean_without": 7.95})) == "means"
    assert dedupe.same_contrast(a, pd.Series({"lrr": 0.35, "mean_with": 10.5, "mean_without": 8.0})) is None


def test_richer_row_is_kept_and_only_other_sources_are_flagged():
    df = _store([
        _row("ERA:ERA_A:1", "ERA", lrr=0.30, mw=10, mo=8, lat=9.0),              # poorer than the HAB row
        _row("HAB:HAB_A_001:1", "HAB", lrr=0.301, mw=10, mo=8, var=0.01, lat=9.0),  # richest: kept
        _row("CSA:CSA_1:1", "CSA", lrr=0.30, mw=10, mo=8),                         # flagged too
        _row("CSA:CSA_1:2", "CSA", lrr=0.30, mw=10, mo=8),                         # same source as the above: never a pair
        _row("CSA:CSA_1:3", "CSA", lrr=0.80, mw=18, mo=8),                         # a different contrast
    ])
    pairs = dedupe.find_duplicates(df)
    assert set(pairs["row_id"]) == {"ERA:ERA_A:1", "CSA:CSA_1:1", "CSA:CSA_1:2"}
    assert set(pairs["dup_of"]) == {"HAB:HAB_A_001:1"}
    out = dedupe.apply_duplicates(df, pairs)
    flagged = dedupe.dup_of_series(out)
    assert flagged["ERA:ERA_A:1" == out["row_id"]].iloc[0] == "HAB:HAB_A_001:1"
    assert flagged[out["row_id"] == "CSA:CSA_1:3"].iloc[0] is None
    assert json.loads(out.loc[out["row_id"] == "CSA:CSA_1:1", "extra"].iloc[0])["dup_rule"] == "cross_source"
    s = dedupe.summarise(out, pairs)
    assert s["flagged_rows"] == 3 and s["flagged_by_pair_kept_over_dropped"] == {"HAB>CSA": 2, "HAB>ERA": 1}
    assert s["dois_in_more_than_one_source"] == 1
    assert "HAB>CSA" in dedupe.card_markdown(s, pairs)


def test_existing_dup_of_rows_are_left_alone_and_ties_go_to_era():
    df = _store([
        _row("CSA:CSA_1:1", "CSA", lrr=0.30, mw=10, mo=8, extra={"dup_of": "CSA:CSA_1:0"}),  # loader flag kept
        _row("CSA:CSA_1:2", "CSA", lrr=0.30, mw=10, mo=8),
        _row("ERA:ERA_A:1", "ERA", lrr=0.30, mw=10, mo=8),
    ])
    pairs = dedupe.find_duplicates(df)
    assert pairs["row_id"].tolist() == ["CSA:CSA_1:2"] and pairs["dup_of"].tolist() == ["ERA:ERA_A:1"]
    out = dedupe.apply_duplicates(df, pairs)
    assert dedupe.dup_of(out.loc[out["row_id"] == "CSA:CSA_1:1", "extra"].iloc[0]) == "CSA:CSA_1:0"


def test_determinism_and_no_pairs_without_shared_doi():
    df = _store([_row("ERA:ERA_A:1", "ERA", lrr=0.3, doi="10.1/a"), _row("CSA:CSA_1:1", "CSA", lrr=0.3, doi="10.1/b"),
                 _row("HAB:HAB_B_001:1", "HAB", lrr=0.3, doi=None)])
    assert dedupe.find_duplicates(df).empty
    big = _store([_row(f"ERA:ERA_A:{i}", "ERA", lrr=0.3 + i * 0.1) for i in range(5)]
                 + [_row(f"CSA:CSA_1:{i}", "CSA", lrr=0.3 + i * 0.1) for i in range(5)])
    a, b = dedupe.find_duplicates(big), dedupe.find_duplicates(big.sample(frac=1, random_state=3))
    pd.testing.assert_frame_equal(a.sort_values("row_id").reset_index(drop=True),
                                  b.sort_values("row_id").reset_index(drop=True))
    assert len(a) == 5 and (a["source"] == "CSA").all()
