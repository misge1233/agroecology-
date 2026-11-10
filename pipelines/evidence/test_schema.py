"""Tests for the evidence schema (brief A2): valid frame, each violation type, round trip."""
from __future__ import annotations

import json
import math

import numpy as np
import pandas as pd
import pytest

from pipelines.evidence import schema


def valid_frame() -> pd.DataFrame:
    """Three schema-valid rows from two sources."""
    rows = []
    for i, (src, sid, mw, mo, sd, n, oid, d) in enumerate([
        ("ERA", "ERA_X1", 120.0, 100.0, 10.0, 4, "YIELD", 1),
        ("ERA", "ERA_X1", 80.0, 100.0, None, None, "SOIL_LOSS", -1),
        ("HAB", "HAB_Y_2020", 0.0, 5.0, None, None, "NEW_OUTCOME", None),
    ]):
        lrr = math.log(mw / mo) if mw > 0 and mo > 0 else None
        var = (sd * sd / (n * mw * mw) + sd * sd / (n * mo * mo)) if sd and n else None
        rows.append({
            "row_id": f"{src}:{sid}:{sum(1 for r in rows if r['study_id'] == sid) + 1}",
            "source": src, "study_id": sid, "doi": None, "citation": "Someone (2020).", "year": 2020,
            "country": "ET", "lat": 9.0, "lon": 38.0, "loc_precision": "site", "loc_method": "reported",
            "site_name": "Site", "practice_id": "MULCH", "practice_raw": "Mulch", "practice_components": "Mulch",
            "practice_family": "Erosion control and water management", "comparator": "bare",
            "crop_group": "Cereal", "crop": "Maize", "outcome_id": oid, "outcome_raw": oid.lower(),
            "direction": d, "unit": "kg/ha", "mean_with": mw, "mean_without": mo,
            "sd_with": sd, "sd_without": sd, "se_with": None, "se_without": None,
            "n_with": n, "n_without": n, "lrr": lrr, "var_lrr": var, "weight": 1.0 / var if var else 0.8,
            "duration_years": 1.0, "study_design": None, "replication": None, "scale": None,
            "quality_flag": "NR", "ctx_reported_rain_mm": 900.0, "ctx_reported_altitude_m": 1800.0,
            "ctx_reported_soil": "clay", "ctx_reported_aez": "Moist Weyna Dega", "ctx_release": None,
            "evidence_text": None, "extraction_locator": "Table 2", "licence": "test",
            "hlpe_principle": None, "mfl_domain": None, "extra": json.dumps({"k": 1}),
            "direction_reviewed": d is not None, "ctx_reported_slope_pct": 12.0,
        })
    return schema.coerce(pd.DataFrame(rows))


DIRECTIONS = {"YIELD": 1, "SOIL_LOSS": -1, "NEW_OUTCOME": None}


def test_valid_frame_passes():
    rep = schema.validate(valid_frame(), outcome_directions=DIRECTIONS)
    assert rep.ok and rep.n_errors == 0 and rep.n_rows == 3


def test_columns_in_appendix_order():
    cols = list(schema.EVIDENCE_COLUMNS)
    assert cols[:3] == ["row_id", "source", "study_id"]
    assert {"hlpe_principle", "mfl_domain", "extra", "direction_reviewed"} <= set(cols)
    assert schema.SCHEMA_VERSION == "1.1"


@pytest.mark.parametrize("mutate, check", [
    (lambda d: d.drop(columns=["licence"]), "missing_column"),
    (lambda d: d.assign(bogus=1), "unknown_column"),
    (lambda d: d.assign(source=["ERA", "XXX", "HAB"]), "enum:source"),
    (lambda d: d.assign(loc_precision=["site", "planet", "site"]), "enum:loc_precision"),
    (lambda d: d.assign(loc_method=["reported", "guess", "reported"]), "enum:loc_method"),
    (lambda d: d.assign(quality_flag=["NR", "Great", "NR"]), "enum:quality_flag"),
    (lambda d: d.assign(direction=pd.array([1, 2, pd.NA], dtype="Int64")), "enum:direction"),
    (lambda d: d.assign(row_id=["ERA:ERA_X1:1", "ERA:ERA_X1:1", "HAB:HAB_Y_2020:1"]), "row_id_duplicate"),
    (lambda d: d.assign(row_id=["ERA-ERA_X1-1", "ERA:ERA_X1:2", "HAB:HAB_Y_2020:1"]), "row_id_pattern"),
    (lambda d: d.assign(row_id=["CSA:ERA_X1:1", "ERA:ERA_X1:2", "HAB:HAB_Y_2020:1"]), "row_id_mismatch"),
    (lambda d: d.assign(lrr=[0.5, d["lrr"][1], None]), "lrr_mismatch"),
    (lambda d: d.assign(lrr=[d["lrr"][0], d["lrr"][1], 0.1]), "lrr_without_positive_means"),
    (lambda d: d.assign(var_lrr=[d["var_lrr"][0], 0.01, None]), "var_lrr_without_sd_n"),
    (lambda d: d.assign(weight=[1.0, 0.0, 1.0]), "weight_not_positive"),
    (lambda d: d.assign(extra=["[1]", None, None]), "extra_not_json_object"),
    (lambda d: d.assign(direction_reviewed=[True, True, True]), "direction_review_state"),
    (lambda d: d.assign(direction=pd.array([-1, -1, pd.NA], dtype="Int64")), "direction_vs_taxonomy"),
    (lambda d: d.assign(outcome_id=["YIELD", "SOIL_LOSS", "UNKNOWN"]), "outcome_id_not_in_taxonomy"),
    (lambda d: d.assign(citation=["a", None, "c"]), "null:citation"),
    (lambda d: d.assign(year=["2020", 2020, 2020]), "dtype:year"),
])
def test_each_violation_is_counted(mutate, check):
    df = mutate(valid_frame())
    rep = schema.validate(df, strict=False, outcome_directions=DIRECTIONS)
    assert check in rep.errors, rep.summary()
    with pytest.raises(schema.SchemaError):
        schema.validate(df, strict=True, outcome_directions=DIRECTIONS)


def test_round_trip(tmp_path):
    df = valid_frame()
    src = tmp_path / "input.csv"
    src.write_text("x\n", encoding="utf-8")
    manifest = schema.write_store(df, tmp_path, input_files=[src], extra_manifest={"note": "t"})
    assert (tmp_path / schema.STORE_PARQUET).exists() and (tmp_path / schema.STORE_CSV).exists()
    assert manifest["rows_per_source"] == {"ERA": 2, "HAB": 1}
    assert manifest["schema_version"] == "1.1" and manifest["note"] == "t"
    assert len(next(iter(manifest["input_files"].values()))) == 64
    back = schema.read_store(tmp_path)
    assert list(back.columns) == list(df.columns)
    pd.testing.assert_frame_equal(back.reset_index(drop=True), df.reset_index(drop=True))
    assert schema.validate(back, outcome_directions=DIRECTIONS).ok


def test_read_store_missing_is_clear(tmp_path):
    with pytest.raises(FileNotFoundError, match="build_evidence_store"):
        schema.read_store(tmp_path)


def test_ctx_prefix_columns_allowed():
    df = valid_frame().assign(ctx_lgp_days=np.array([200.0, 210.0, 220.0]))
    assert schema.validate(df, outcome_directions=DIRECTIONS).ok
