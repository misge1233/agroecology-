"""Data-dependent acceptance tests (brief Part E). Skipped when the raw files are absent.

* B1/B2 reconciliation: the legacy rules applied to the loaded frames reproduce the
  7,250 ERA and 1,414 CSA rows of the frozen dataset exactly.
* B3: Habtamu row counts and the `.grist` cross-check.
* C5: the catalogue parses to 30 entries with a name and a category.
"""
from __future__ import annotations

import pytest

from pipelines.evidence import load_csa, load_era, load_habtamu, parse_catalogue, reconcile

pytestmark = pytest.mark.data

need_era = pytest.mark.skipif(not load_era.RAW_PATH.exists(), reason="ERA raw CSV absent")
need_csa = pytest.mark.skipif(not (load_csa.RAW_PATH.exists() and load_csa.REFS_PATH.exists()),
                              reason="CSA workbook or references absent")
need_final = pytest.mark.skipif(not reconcile.FINAL_PATH.exists(), reason="frozen dataset absent")
need_hab = pytest.mark.skipif(not load_habtamu.RAW_PATH.exists(), reason="Habtamu export absent (partner data)")
need_cat = pytest.mark.skipif(not parse_catalogue.RAW_PATH.exists(), reason="catalogue docx absent (partner data)")


@need_era
@need_final
def test_era_reconciliation_exact():
    df, log, raw = load_era.load()
    assert len(df) == len(raw) == 14_792 and df["study_id"].nunique() == 306
    res = reconcile.reconcile(df, "ERA")
    assert res.n_expected == res.n_reproduced == 7_250
    assert res.only_in_store == 0 and res.only_in_frozen == 0
    assert res.max_abs_lrr_diff <= 1e-9
    assert res.exact


@need_csa
@need_final
def test_csa_reconciliation_exact():
    df, log, raw = load_csa.load()
    assert len(df) == len(raw) == 3_344
    res = reconcile.reconcile(df, "CSA")
    assert res.n_expected == res.n_reproduced == 1_414
    assert res.only_in_store == 0 and res.only_in_frozen == 0
    assert res.exact


@need_hab
def test_habtamu_counts():
    df, log, raw = load_habtamu.load()
    assert len(df) == len(raw) == 1_617                     # no silent drops
    assert int(df["lrr"].notna().sum()) == 1_312
    assert int(df["var_lrr"].notna().sum()) == 643          # 646 in the profile minus 3 rows with SD = 0
    assert log.parsing["var_lrr_null_sd_zero"] == 3
    et = df["country"] == "ET"
    assert int(et.sum()) == 158 and int((et & df["lrr"].notna()).sum()) == 129
    grist = load_habtamu.grist_row_count()
    if grist is not None:
        assert grist == 1_617


@need_cat
def test_catalogue_has_30_entries():
    entries = parse_catalogue.parse()
    parse_catalogue.check(entries)                          # 30, consecutive, name and category
    assert len(entries) == 30
    assert all(e.key_problems for e in entries)
    assert sum(len(e.photo_captions) for e in entries) > 0
