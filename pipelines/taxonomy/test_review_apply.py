"""Review appliers (brief E2 A1, A2): every decision type on fixture sheets; unaccepted rows untouched."""
from __future__ import annotations

import pandas as pd
import pytest

from pipelines.taxonomy import review_apply as ra
from pipelines.taxonomy import taxonomy_io as tio


def _outcome(oid, d="1", g="other", status="seed"):
    return {"outcome_id": oid, "name_en": oid.lower(), "direction": d, "unit_class": "other", "objective_group": g,
            "legacy_indicator": "", "status": status, "notes": ""}


def _alias(alias, oid, source="CSA", id_col="outcome_id"):
    return {"alias": alias, "source": source, id_col: oid, "method": "keyword", "confidence": "0.80",
            "accepted": "", "reviewer": "", "date": "", "notes": ""}


@pytest.fixture
def root(tmp_path):
    (tmp_path / "review").mkdir()
    tio.write_csv(pd.DataFrame([_outcome("A_OK"), _outcome("B_FLIP"), _outcome("C_EXCL"), _outcome("D_CTX"),
                                _outcome("E_TYPO"), _outcome("INFILTRATION_RATE", g="water"),
                                _outcome("F_UNTICKED"), _outcome("TREE_HEIGHT")]),
                  tmp_path / "outcomes.csv", tio.OUTCOME_COLUMNS)
    tio.write_csv(pd.DataFrame([_alias("a", "A_OK"), _alias("e1", "E_TYPO"), _alias("e2", "E_TYPO"),
                                _alias("f", "F_UNTICKED")]),
                  tmp_path / "outcome_aliases.csv", tio.alias_columns("outcome_id"))
    sheet = pd.DataFrame([
        {"outcome_id": "A_OK", "proposed_decision": "accept", "proposed_direction": "1", "proposed_group": "climate",
         "merge_into": "", "note": "", "accepted": "yes", "reviewer": "MT", "date": "2026-11-11"},
        {"outcome_id": "B_FLIP", "proposed_decision": "flip", "proposed_direction": "-1", "proposed_group": "water",
         "merge_into": "", "note": "", "accepted": "YES", "reviewer": "MT", "date": "2026-11-11"},
        {"outcome_id": "C_EXCL", "proposed_decision": "exclude", "proposed_direction": "", "proposed_group": "",
         "merge_into": "", "note": "descriptor", "accepted": "yes", "reviewer": "MT", "date": ""},
        {"outcome_id": "D_CTX", "proposed_decision": "context_dependent", "proposed_direction": "",
         "proposed_group": "soil_health", "merge_into": "", "note": "depends on pH", "accepted": "yes",
         "reviewer": "MT", "date": ""},
        {"outcome_id": "E_TYPO", "proposed_decision": "merge_into", "proposed_direction": "1", "proposed_group": "water",
         "merge_into": "INFILTRATION_RATE", "note": "typo", "accepted": "yes", "reviewer": "MT", "date": ""},
        {"outcome_id": "F_UNTICKED", "proposed_decision": "flip", "proposed_direction": "-1", "proposed_group": "water",
         "merge_into": "", "note": "", "accepted": "", "reviewer": "", "date": ""},
        {"outcome_id": "MEAN_TREE_HEIGHT_DIFFERENCXE", "proposed_decision": "accept", "proposed_direction": "1",
         "proposed_group": "productivity", "merge_into": "", "note": "renamed", "accepted": "yes", "reviewer": "MT",
         "date": ""},
    ])
    sheet.to_csv(tmp_path / "review" / "outcomes_direction_review.csv", index=False)
    return tmp_path


def test_outcome_review_every_decision(root):
    res = ra.apply_outcome_review(root / "review" / "outcomes_direction_review.csv", root)
    assert res.n_rows_in_sheet == 7 and res.n_accepted == 6
    assert dict(res.applied) == {"accept": 2, "flip": 1, "exclude": 1, "context_dependent": 1, "merge_into": 1}
    tax = tio.Taxonomy.load(root)
    o = tax.outcomes.set_index("outcome_id")
    assert (o.loc["A_OK", "status"], o.loc["A_OK", "objective_group"]) == ("reviewed", "climate")
    assert (o.loc["B_FLIP", "direction"], o.loc["B_FLIP", "status"]) == ("-1", "reviewed")
    assert (o.loc["C_EXCL", "status"], o.loc["C_EXCL", "direction"]) == ("excluded", "")
    assert o.loc["D_CTX", "status"] == "context_dependent" and "depends on pH" in o.loc["D_CTX", "notes"]
    assert o.loc["E_TYPO", "status"] == "merged"
    assert o.loc["F_UNTICKED", "status"] == "seed" and o.loc["F_UNTICKED", "direction"] == "1"  # untouched
    assert o.loc["TREE_HEIGHT", "status"] == "reviewed"            # sheet's old id followed the rename
    assert "MT" in o.loc["A_OK", "notes"]
    al = tax.outcome_aliases.set_index("alias")
    assert al.loc["e1", "outcome_id"] == al.loc["e2", "outcome_id"] == "INFILTRATION_RATE"
    assert "moved from E_TYPO" in al.loc["e1", "notes"] and al.loc["e1", "reviewer"] == "MT"
    d = tax.outcome_directions()
    assert d["A_OK"] == 1 and d["B_FLIP"] == -1
    assert d["C_EXCL"] is None and d["D_CTX"] is None and d["E_TYPO"] is None and d["F_UNTICKED"] is None


def test_applied_rows_survive_reseeding(root):
    ra.apply_outcome_review(root / "review" / "outcomes_direction_review.csv", root)
    old = tio.read_csv(root / "outcomes.csv", tio.OUTCOME_COLUMNS)
    fresh = pd.DataFrame([_outcome("C_EXCL"), _outcome("A_OK", d="-1")])  # rules would say otherwise
    merged = tio.merge_by_key(fresh, old, ["outcome_id"], tio.protect_taxonomy_row).set_index("outcome_id")
    assert merged.loc["C_EXCL", "status"] == "excluded" and merged.loc["A_OK", "direction"] == "1"


def test_no_accepted_rows_changes_nothing(root):
    sheet = root / "review" / "outcomes_direction_review.csv"
    s = pd.read_csv(sheet, dtype=str, keep_default_na=False).assign(accepted="")
    s.to_csv(sheet, index=False)
    before = (root / "outcomes.csv").read_text(encoding="utf-8")
    res = ra.apply_outcome_review(sheet, root)
    assert res.n_accepted == 0 and not res.applied
    assert (root / "outcomes.csv").read_text(encoding="utf-8") == before


def test_bad_rows_are_skipped(root):
    sheet = root / "review" / "outcomes_direction_review.csv"
    pd.DataFrame([{"outcome_id": "A_OK", "proposed_decision": "accept", "proposed_direction": "2",
                   "proposed_group": "nowhere", "merge_into": "", "note": "", "accepted": "yes", "reviewer": "x",
                   "date": ""},
                  {"outcome_id": "NOPE", "proposed_decision": "accept", "proposed_direction": "1",
                   "proposed_group": "water", "merge_into": "", "note": "", "accepted": "yes", "reviewer": "x",
                   "date": ""}]).to_csv(sheet, index=False)
    res = ra.apply_outcome_review(sheet, root)
    assert len(res.skipped) == 2 and not res.applied


def _practice(pid, name, status="seed", cat=""):
    return {"practice_id": pid, "name_en": name, "practice_family": "Erosion control and water management",
            "components": "", "era_codes": "", "catalogue_ids": cat, "wocat_group": "", "wocat_measure": "",
            "status": status, "notes": ""}


def test_alias_reviews_and_merges(tmp_path):
    (tmp_path / "review").mkdir()
    tio.write_csv(pd.DataFrame([_practice("MULCH", "Mulch"), _practice("D_ERA", "Deficit Irrigation"),
                                _practice("D_CSA", "Deficit irrigation"), _practice("BENCH", "Bench", cat="CAT_01"),
                                _practice("PHYS", "Physical SWC measures")]),
                  tmp_path / "practices.csv", tio.PRACTICE_COLUMNS)
    tio.write_csv(pd.DataFrame([_alias("Deficit irrigation", "D_CSA", "CSA", "practice_id")]),
                  tmp_path / "practice_aliases.csv", tio.alias_columns("practice_id"))
    tio.write_csv(pd.DataFrame([_outcome("YIELD")]), tmp_path / "outcomes.csv", tio.OUTCOME_COLUMNS)
    tio.write_csv(pd.DataFrame(columns=tio.alias_columns("outcome_id")), tmp_path / "outcome_aliases.csv",
                  tio.alias_columns("outcome_id"))
    cols = tio.review_columns("practice_id")
    rows = [
        {"raw_label": "Straw mulch", "n_rows": "3", "accepted": "yes", "practice_id": "MULCH", "reviewer": "HS",
         "date": "2026-11-11", "llm_suggestion": "MULCH"},
        {"raw_label": "Cover crops", "n_rows": "9", "accepted": "yes", "practice_id": "NEW:COVER_CROPS",
         "reviewer": "HS", "date": "2026-11-11", "llm_suggestion": "NEW"},
        {"raw_label": "Organic farming", "n_rows": "49", "accepted": "", "practice_id": "", "reviewer": "",
         "date": "", "llm_suggestion": "NEW"},
        {"raw_label": "Mystery", "n_rows": "1", "accepted": "yes", "practice_id": "UNKNOWN", "reviewer": "HS",
         "date": "", "llm_suggestion": ""},
    ]
    pd.DataFrame(rows).reindex(columns=cols).fillna("").to_csv(tmp_path / "review" / "HAB_practices_review.csv",
                                                               index=False)
    pd.DataFrame(columns=tio.review_columns("outcome_id")).to_csv(tmp_path / "review" / "HAB_outcomes_review.csv",
                                                                   index=False)
    pd.DataFrame([
        {"practice_id_a": "D_CSA", "practice_id_b": "D_ERA", "relation": "same_practice", "reason": "",
         "accepted": "yes", "reviewer": "MT", "date": ""},
        {"practice_id_a": "BENCH", "practice_id_b": "PHYS", "relation": "narrower_than", "reason": "",
         "accepted": "yes", "reviewer": "MT", "date": ""},
    ]).to_csv(tmp_path / "review" / "practice_merges.csv", index=False)

    res = ra.apply_alias_reviews(tmp_path)
    assert res.applied["HAB_practices:alias"] == 2 and res.applied["HAB_practices:new_id"] == 1
    assert len(res.skipped) == 1 and "UNKNOWN" in res.skipped[0]
    merges = ra.apply_practice_merges(tmp_path)
    assert dict(merges.applied) == {"same_practice": 1, "narrower_than": 1}
    tax = tio.Taxonomy.load(tmp_path)
    look = tax.practice_lookup()
    assert look[("HAB", "Straw mulch")] == "MULCH" and look[("HAB", "Cover crops")] == "COVER_CROPS"
    assert ("HAB", "Organic farming") not in look
    assert look[("CSA", "Deficit irrigation")] == "D_ERA"                 # alias moved by the merge
    p = tax.practices.set_index("practice_id")
    assert p.loc["COVER_CROPS", "status"] == "reviewed" and p.loc["D_CSA", "status"] == "merged"
    assert "parent: PHYS" in p.loc["BENCH", "notes"]
    al = tax.practice_aliases.set_index("alias")
    assert al.loc["Straw mulch", "method"] == "llm" and al.loc["Cover crops", "method"] == "manual"


def test_drop_renamed_seed_rows():
    df = pd.DataFrame([_outcome("MEAN_TREE_HEIGHT_DIFFERENCXE"), _outcome("TREE_HEIGHT")])
    out = ra.drop_renamed_seed_rows(df, {"MEAN_TREE_HEIGHT_DIFFERENCXE": "TREE_HEIGHT"})
    assert list(out["outcome_id"]) == ["TREE_HEIGHT"]
