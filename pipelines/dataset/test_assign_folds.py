"""Unit tests for the deterministic CV fold assignment (Phase P7).

Pure Python, no pandas, no numpy, no dataset: every test builds its own toy
study sizes. These pin the properties the protocol depends on — if any of
them breaks, the published model numbers stop being reproducible.

Run from the repo root:
    python -m pytest pipelines/dataset/test_assign_folds.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PIPELINE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PIPELINE_DIR.parents[1]
if str(PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(PIPELINE_DIR))

from assign_folds import (  # noqa: E402
    FOLDS_PATH,
    N_FOLDS,
    N_REPS,
    SHUFFLE_BLOCK,
    build_folds,
    fold_row_counts,
    greedy_assign,
    load_folds,
    max_imbalance,
    ordered_studies,
    study_sizes,
    write_folds,
)

#: A toy set whose repetition-0 assignment can be worked out by hand.
TOY = {"S_big": 100, "S_mid": 60, "S_small": 40, "S_tiny": 10, "S_one": 1}


# ------------------------------------------------------------ the rule itself
def test_repetition_zero_orders_by_size_then_name():
    sizes = {"b": 10, "a": 10, "c": 50}
    assert ordered_studies(sizes, 0) == ["c", "a", "b"]


def test_repetition_zero_is_reproducible_by_hand():
    """Work the documented rule through on TOY and compare.

    Order (size desc): S_big 100, S_mid 60, S_small 40, S_tiny 10, S_one 1.
    Three folds, each time to the emptiest (ties -> lowest index):
      S_big   -> loads (0,0,0)       -> fold 0, loads (100, 0, 0)
      S_mid   -> emptiest is fold 1  -> fold 1, loads (100, 60, 0)
      S_small -> emptiest is fold 2  -> fold 2, loads (100, 60, 40)
      S_tiny  -> emptiest is fold 2  -> fold 2, loads (100, 60, 50)
      S_one   -> emptiest is fold 2  -> fold 2, loads (100, 60, 51)
    """
    assignment = greedy_assign(ordered_studies(TOY, 0), TOY, n_folds=3)
    assert assignment == {"S_big": 0, "S_mid": 1, "S_small": 2,
                          "S_tiny": 2, "S_one": 2}


def test_greedy_breaks_load_ties_on_the_lowest_fold_index():
    sizes = {"a": 5, "b": 5, "c": 5}
    assert greedy_assign(["a", "b", "c"], sizes, n_folds=3) == {"a": 0, "b": 1, "c": 2}


def test_shuffle_is_local_so_the_order_stays_roughly_largest_first():
    sizes = {f"s{i:03d}": 100 - i for i in range(100)}   # all distinct sizes
    order = ordered_studies(sizes, rep=3, block=SHUFFLE_BLOCK)
    assert sorted(order) == sorted(sizes)
    # no study can move further than one block away from its sorted position
    sorted_order = ordered_studies(sizes, 0)
    for position, study in enumerate(order):
        assert abs(sorted_order.index(study) - position) < SHUFFLE_BLOCK


# -------------------------------------------------------------- determinism
def test_build_folds_is_deterministic_across_runs():
    assert build_folds(TOY) == build_folds(TOY)


def test_each_repetition_is_reproducible_from_its_seed_alone():
    sizes = {f"s{i:03d}": (i % 7) + 1 for i in range(50)}
    first = build_folds(sizes, n_reps=4)
    second = build_folds(sizes, n_reps=4)
    assert first == second
    # and rebuilding only repetition 2 gives the same column
    only_three = build_folds(sizes, n_reps=3)
    for study in sizes:
        assert first[study][:3] == only_three[study]


def test_assignment_does_not_depend_on_dict_insertion_order():
    forward = build_folds(dict(TOY))
    backward = build_folds({k: TOY[k] for k in reversed(list(TOY))})
    assert forward == backward


# ---------------------------------------------------------------- structure
def test_every_study_has_exactly_one_fold_per_repetition():
    folds = build_folds(TOY, n_folds=3, n_reps=N_REPS)
    assert set(folds) == set(TOY)
    for assignments in folds.values():
        assert len(assignments) == N_REPS
        assert all(0 <= f < 3 for f in assignments)


def test_folds_partition_the_studies_in_every_repetition():
    sizes = {f"s{i:03d}": (i % 11) + 1 for i in range(120)}
    folds = build_folds(sizes)
    for rep in range(N_REPS):
        members = [[] for _ in range(N_FOLDS)]
        for study, assignments in folds.items():
            members[assignments[rep]].append(study)
        flat = [s for fold in members for s in fold]
        assert sorted(flat) == sorted(sizes)        # covers every study once


# ------------------------------------------------------------------ balance
def test_fold_sizes_are_balanced_within_five_percent():
    sizes = {f"s{i:03d}": (i % 23) + 1 for i in range(200)}
    folds = build_folds(sizes)
    for rep in range(N_REPS):
        counts = fold_row_counts(folds, sizes, rep)
        assert max_imbalance(counts) < 0.05, (rep, counts)


def test_balance_holds_on_the_real_study_size_distribution():
    """The real dataset is the hard case: one study has 539 rows."""
    dataset = REPO_ROOT / "data" / "processed" / "CSA_ERA_final_model_ready.csv"
    if not dataset.exists():                      # pragma: no cover
        pytest.skip("dataset not available")
    sizes = study_sizes(dataset)
    folds = build_folds(sizes)
    for rep in range(N_REPS):
        counts = fold_row_counts(folds, sizes, rep)
        assert max_imbalance(counts) < 0.05, (rep, counts)


def test_repetitions_actually_differ():
    """Otherwise the sd across repetitions would be meaningless."""
    sizes = {f"s{i:03d}": (i % 9) + 1 for i in range(150)}
    folds = build_folds(sizes)
    movers = sum(1 for s in sizes if folds[s][0] != folds[s][1])
    assert movers > len(sizes) * 0.1
    visits_several = sum(1 for s in sizes if len(set(folds[s])) > 1)
    assert visits_several > len(sizes) * 0.5


# ---------------------------------------------------------------- round trip
def test_write_and_load_round_trip(tmp_path):
    folds = build_folds(TOY, n_reps=4)
    path = write_folds(folds, tmp_path / "cv_folds.csv", n_reps=4)
    assert load_folds(path) == folds


def test_written_file_uses_lf_and_is_sorted(tmp_path):
    path = write_folds(build_folds(TOY, n_reps=2), tmp_path / "f.csv", n_reps=2)
    raw = path.read_bytes()
    assert b"\r\n" not in raw
    lines = raw.decode().strip().split("\n")
    assert lines[0] == "Study_No_,fold_rep00,fold_rep01"
    studies = [line.split(",")[0] for line in lines[1:]]
    assert studies == sorted(studies)


def test_load_folds_reports_a_missing_file_clearly(tmp_path):
    with pytest.raises(FileNotFoundError, match="assign_folds"):
        load_folds(tmp_path / "nope.csv")


# ------------------------------------------------------- the committed file
def test_committed_fold_file_matches_the_rule():
    """The checked-in cv_folds.csv must be exactly what the script produces."""
    dataset = REPO_ROOT / "data" / "processed" / "CSA_ERA_final_model_ready.csv"
    if not (FOLDS_PATH.exists() and dataset.exists()):   # pragma: no cover
        pytest.skip("fold file or dataset not available")
    assert load_folds(FOLDS_PATH) == build_folds(study_sizes(dataset))
