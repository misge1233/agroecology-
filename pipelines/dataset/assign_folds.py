#!/usr/bin/env python3
"""
assign_folds.py  -  deterministic grouped cross-validation folds (Phase P7).

Writes ``data/processed/cv_folds.csv``: one row per study
(``Study_No_``) and ten repetition columns ``fold_rep00`` … ``fold_rep09``,
each holding that study's fold index (0-4) for that repetition.

WHY THIS FILE EXISTS
--------------------
``sklearn.model_selection.GroupKFold`` orders groups by size using
``np.argsort``. **298 of the 337 studies share their row count with at least
one other study**, so fold membership is decided by numpy's tie-breaking,
which differs between numpy versions and CPU code paths. Three environments
produced three different fold assignments, three different baseline R²
values, and even a different winning model family (P6a.1 review, 24 Oct
2026). Persisting the folds removes that hazard: every machine evaluates on
exactly the same split, and the split is reproducible from this script alone.

THE RULE
--------
Repetition 0 is fully deterministic with no randomness at all:

1. order the studies by (row count **descending**, ``Study_No_``
   **ascending**) — the string sort breaks every size tie;
2. walk that order and assign each study to the fold that currently holds the
   **fewest rows** (ties → lowest fold index).

Repetitions 1-9 apply the same greedy assignment after a seeded
``random.Random(rep)`` shuffle — but the shuffle is **local**: the studies
are first ordered by size as above, then shuffled only *within consecutive
blocks of ``SHUFFLE_BLOCK`` (4) studies*, so a study can swap places with
its size-neighbours but the order stays approximately largest-first.

That detail is a deliberate refinement of the P7 brief, and it is measured.
Feeding the greedy assigner a **fully** shuffled order destroys its balance:
a 539-row study arriving last lands entirely in one fold, and over the ten
repetitions the worst fold deviated **21.5%** from the mean row count — far
outside the 5% the brief requires, and itself a source of the between-fold
variance this phase exists to remove. Shuffling only *within size ties*
balances perfectly but pins the 39 uniquely sized studies — including the
five largest — to the same fold in every repetition, which would understate
the uncertainty. Block shuffling gives both: **worst deviation 0.05%**,
only one study pinned across all ten repetitions, ~250 of 337 studies
change fold between any two repetitions, and every one of the five largest
studies moves.

Everything is pure Python: no numpy sort is involved anywhere, so the output
cannot drift with numpy's version.

Usage:
    python pipelines/dataset/assign_folds.py
    python pipelines/dataset/assign_folds.py --n-folds 5 --n-reps 10

Requires: pandas (only to read the dataset).
"""
from __future__ import annotations

import argparse
import csv
import random
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DATASET_PATH = REPO_ROOT / "data" / "processed" / "CSA_ERA_final_model_ready.csv"
FOLDS_PATH = REPO_ROOT / "data" / "processed" / "cv_folds.csv"

GROUP = "Study_No_"
N_FOLDS = 5
N_REPS = 10
#: Studies are shuffled only within consecutive blocks of this many, after
#: the size-descending sort — see the module docstring for why.
SHUFFLE_BLOCK = 4


def study_sizes(dataset_path: Path) -> dict[str, int]:
    """``Study_No_`` -> number of dataset rows, read without pandas."""
    counts: Counter[str] = Counter()
    with open(dataset_path, encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            counts[row[GROUP]] += 1
    return dict(counts)


def ordered_studies(sizes: dict[str, int], rep: int,
                    block: int = SHUFFLE_BLOCK) -> list[str]:
    """Study order for one repetition.

    Repetition 0 is the deterministic rule with no randomness at all
    (largest first, ``Study_No_`` breaking every size tie). Repetitions 1+
    shuffle that list with a seeded :class:`random.Random`, but only within
    consecutive blocks of ``block`` studies, so the order stays
    approximately largest-first and the greedy assignment stays balanced.
    Each repetition is reproducible on its own from ``rep`` alone.
    """
    studies = sorted(sizes, key=lambda s: (-sizes[s], s))
    if rep:
        rng = random.Random(rep)
        for start in range(0, len(studies), block):
            chunk = studies[start:start + block]
            rng.shuffle(chunk)
            studies[start:start + block] = chunk
    return studies


def greedy_assign(studies: list[str], sizes: dict[str, int],
                  n_folds: int = N_FOLDS) -> dict[str, int]:
    """Assign each study to the fold holding the fewest rows so far.

    Ties go to the lowest fold index, so the result depends only on the
    input order — never on dict ordering or a library's sort stability.
    """
    load = [0] * n_folds
    assignment: dict[str, int] = {}
    for study in studies:
        fold = min(range(n_folds), key=lambda f: (load[f], f))
        assignment[study] = fold
        load[fold] += sizes[study]
    return assignment


def build_folds(sizes: dict[str, int], n_folds: int = N_FOLDS,
                n_reps: int = N_REPS,
                block: int = SHUFFLE_BLOCK) -> dict[str, list[int]]:
    """``Study_No_`` -> [fold for rep0, fold for rep1, …]."""
    per_rep = [
        greedy_assign(ordered_studies(sizes, rep, block), sizes, n_folds)
        for rep in range(n_reps)
    ]
    return {study: [rep[study] for rep in per_rep] for study in sorted(sizes)}


def fold_row_counts(folds: dict[str, list[int]], sizes: dict[str, int],
                    rep: int, n_folds: int = N_FOLDS) -> list[int]:
    """Rows per fold for one repetition — used for the balance check."""
    load = [0] * n_folds
    for study, assignment in folds.items():
        load[assignment[rep]] += sizes[study]
    return load


def max_imbalance(counts: list[int]) -> float:
    """Largest relative deviation of a fold's row count from the mean."""
    mean = sum(counts) / len(counts)
    return max(abs(c - mean) for c in counts) / mean if mean else 0.0


def write_folds(folds: dict[str, list[int]], path: Path,
                n_reps: int = N_REPS) -> Path:
    """Write cv_folds.csv (LF line endings, sorted by Study_No_)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [GROUP] + [f"fold_rep{rep:02d}" for rep in range(n_reps)]
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(fieldnames)
        for study in sorted(folds):
            writer.writerow([study, *folds[study]])
    return path


def load_folds(path: Path = FOLDS_PATH) -> dict[str, list[int]]:
    """Read cv_folds.csv back as ``Study_No_`` -> [fold per repetition]."""
    if not path.exists():
        raise FileNotFoundError(
            f"fold file not found: {path} — run pipelines/dataset/assign_folds.py"
        )
    folds: dict[str, list[int]] = {}
    with open(path, encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        rep_columns = [c for c in (reader.fieldnames or []) if c.startswith("fold_rep")]
        for row in reader:
            folds[row[GROUP]] = [int(row[c]) for c in rep_columns]
    return folds


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[2])
    parser.add_argument("--dataset", type=Path, default=DATASET_PATH)
    parser.add_argument("--out", type=Path, default=FOLDS_PATH)
    parser.add_argument("--n-folds", type=int, default=N_FOLDS)
    parser.add_argument("--n-reps", type=int, default=N_REPS)
    parser.add_argument("--block", type=int, default=SHUFFLE_BLOCK,
                        help="shuffle studies only within blocks of this size")
    args = parser.parse_args(argv)

    sizes = study_sizes(args.dataset)
    folds = build_folds(sizes, args.n_folds, args.n_reps, args.block)
    path = write_folds(folds, args.out, args.n_reps)

    total = sum(sizes.values())
    print(f"{len(sizes)} studies, {total} rows -> {path}")
    print(f"{args.n_reps} repetitions x {args.n_folds} folds\n")
    print("rep  " + "  ".join(f"fold{f}" for f in range(args.n_folds)) + "   max dev")
    worst = 0.0
    for rep in range(args.n_reps):
        counts = fold_row_counts(folds, sizes, rep, args.n_folds)
        dev = max_imbalance(counts)
        worst = max(worst, dev)
        print(f"{rep:>3}  " + "  ".join(f"{c:5d}" for c in counts) + f"   {dev:6.2%}")
    print(f"\nworst fold-size deviation from the mean: {worst:.2%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
