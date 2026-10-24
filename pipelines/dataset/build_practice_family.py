#!/usr/bin/env python3
"""
build_practice_family.py
Assign every practice in the merged dataset to one of the FIVE expert categories
from the AICCRA/Adimassu paper (paper_long.txt):
  CPM  Crop production and management
  LPM  Livestock production and management
  ISFM Integrated Soil Fertility Management
  ECWM Erosion control and water management
  FAF  Forestry and agroforestry

Method:
- CSA-source practices (the 20 CSA_catago categories) use an explicit lookup
  built directly from the paper's category listings.
- ERA-source practices (81, many are 'A-B-C' combinations) are classified by
  keyword tokens; when a combined practice matches several categories, the paper
  notes such overlaps, so we resolve to ONE family by a documented priority:
      FAF > LPM > ISFM > ECWM > CPM
  (distinctive whole-system practices first; ISFM is the dominant ERA soil-fertility
   theme; ECWM for water/erosion; CPM as the base crop-management default).

Pipeline position:  merged -> (this script) -> final
  in   data/processed/CSA_ERA_merged_model_ready.csv
  out  data/processed/CSA_ERA_final_model_ready.csv
  and, with --sync-copies (default), byte-identical copies back to the merged
  file and to app/backend/dataset/. See docs/reports/merged_dataset_notes.md.

The dataset's COLUMN NAMES are a frozen data contract and are never changed;
this script only (re)computes the VALUES of `practice_family`.

Usage:
    python pipelines/dataset/build_practice_family.py
    python pipelines/dataset/build_practice_family.py --dataset X.csv --out Y.csv
    python pipelines/dataset/build_practice_family.py --no-sync-copies

Requires: pandas.
"""
from __future__ import annotations

import argparse
import hashlib
import shutil
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
MERGED_PATH = REPO_ROOT / "data" / "processed" / "CSA_ERA_merged_model_ready.csv"
FINAL_PATH = REPO_ROOT / "data" / "processed" / "CSA_ERA_final_model_ready.csv"
BACKEND_PATH = REPO_ROOT / "app" / "backend" / "dataset" / "CSA_ERA_final_model_ready.csv"

# full category names (replace abbreviations)
CPM = "Crop production and management"
LPM = "Livestock production and management"
ISFM = "Integrated soil fertility management"
ECWM = "Erosion control and water management"
FAF = "Agro-forestry and forest management"

# --- explicit map for the 20 CSA_catago categories (from paper category lists) ---
CSA_MAP = {
 "Physical SWC measures": ECWM,
 "Animal feed management": LPM,
 "In-situ water harvesting": ECWM,
 "ISFM": ISFM,
 "Intercropping": CPM,
 "Exclosure": FAF,
 "organic amedements": ISFM,
 "Deficit irrigation": ECWM,
 "Conservation tillage": CPM,
 "agronomic/biological SWCP": ECWM,
 "furrow irrigation": ECWM,
 "drip irrigation": ECWM,
 "Physical + biological SWC practices": ECWM,
 "grazing management": LPM,
 "Biological SWC practices": ECWM,
 "weeding": CPM,
 "IWM": ECWM,                       # integrated water/watershed management
 "overhead irrigation with mulching": ECWM,
 "furrow irrigation_alternate": ECWM,
 "Drought tolerrant crops": CPM,
}

# --- keyword sets for ERA practices (searched as substrings, lowercased) ---
# ERRATUM (23 Oct 2026): LPM previously carried the bare token "supplement",
# intended for feed supplementation. It also matches "Supplemental Irrigation",
# and because LPM outranks ECWM in PRIORITY it sent all 311 rows of
# "Supplemental Irrigation" and its two combinations to LPM, contradicting
# docs/decisions/practice_family_mapping.md (irrigation -> ECWM). Replaced by
# "supplementation" and "feed supplement", which cannot match an irrigation
# label. Audit of all 49 multi-keyword ERA names found this to be the only
# false match. See the erratum in practice_family_mapping.md.
KW = {
 "FAF": ["agroforest", "parkland", "multistrata", "alley crop", "alleycropping", "afforest", "reforest",
         "exclosure", "silvopast", "silvo-past", "prosopis", "woodlot", "fmnr",
         "natural regeneration", "pruning", "fodder tree", "tree", "shrub"],
 "LPM": ["feed", "forage", "fodder", "grazing", "livestock", "animal", "breed",
         "supplementation", "feed supplement", "silage", "destock", "dairy", "pasture", "herd"],
 "ISFM": ["fertilizer", "inorganic", "organic", "biochar", "compost", "vermicompost",
          "manure", "lime", "liming", "gypsum", "ph control", "nutrient", "bio fertil",
          "bioslurry", "green manure", "residue incorporation", "microdose", "micro-dose",
          "amendment", "inoculant", "soil fertility", "integrated soil"],
 "ECWM": ["irrigation", "water harvest", "bund", "terrace", "fanya", "tied ridge",
          "tie-ridge", "tie ridge", "ridge", "mulch", "runoff", "check dam", "shallow well",
          "water storage", "spate", "drip", "furrow", "sprinkler", "deficit", "grass strip",
          "trench", "waterway", "sub-soil", "sub soil", "soil and water", "moisture",
          "half moon", "percolation", "contour", "broad bed", "bbf", "bbm", "pond", "diversion"],
 "CPM": ["variet", "cultivar", "intercrop", "rotation", "tillage", "minimum till", "zero till",
         "weed", "pest", "ipm", "planting date", "sowing", "seed", "cover crop", "fallow",
         "drought tolerant", "conservation agri", "advisory", "insurance", "diversif",
         "residue", "relay", "push-pull", "botanical", "striga"],
}
PRIORITY = ["FAF", "LPM", "ISFM", "ECWM", "CPM"]
FULL = {"CPM": CPM, "LPM": LPM, "ISFM": ISFM, "ECWM": ECWM, "FAF": FAF}


def classify_era(name) -> tuple[str, bool | None]:
    """ERA practice label -> (practice_family, was_multi_keyword).

    ``was_multi_keyword`` is True when several families matched and PRIORITY
    resolved it, False for a single clean hit, and None when NO keyword matched
    (the CPM default, reported for review).
    """
    s = str(name).lower()
    hits = {fam for fam, kws in KW.items() if any(k in s for k in kws)}
    for fam in PRIORITY:
        if fam in hits:
            return FULL[fam], (len(hits) > 1)   # (family full name, was_multi)
    return CPM, None                            # default (no keyword) -> review


def classify(source, practice) -> str:
    """Family for one row, dispatching on the row's `source` (CSA / ERA)."""
    if source == "CSA":
        return CSA_MAP.get(str(practice).strip(), CPM)
    return classify_era(practice)[0]


def detect_line_terminator(path: Path) -> str:
    r"""Line terminator already used by ``path`` ('\r\n' or '\n').

    The repo's canonical CSVs are CRLF (written by pandas on Windows). Writing
    LF here would rewrite all 8,665 lines and bury the real diff, so the input
    file's convention is preserved.
    """
    if not path.exists():
        return "\r\n"
    with open(path, "rb") as fh:
        head = fh.read(65536)
    return "\r\n" if b"\r\n" in head else "\n"


def md5(path: Path) -> str:
    """Checksum, used to prove the three dataset copies stay identical."""
    return hashlib.md5(path.read_bytes()).hexdigest()


def assign_families(m: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    """Add/replace `practice_family`, placed right after `CSA_practices`."""
    fam = []
    default_hits: dict[str, int] = {}
    for src, pr in zip(m.source, m.CSA_practices):
        if src == "CSA":
            fam.append(CSA_MAP.get(str(pr).strip(), CPM))
        else:
            f, multi = classify_era(pr)
            fam.append(f)
            if multi is None:
                default_hits[pr] = default_hits.get(pr, 0) + 1
    m["practice_family"] = fam
    # place practice_family right after CSA_practices
    cols = list(m.columns)
    cols.remove("practice_family")
    i = cols.index("CSA_practices") + 1
    return m[cols[:i] + ["practice_family"] + cols[i:]], default_hits


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--dataset", type=Path, default=MERGED_PATH,
                        help="merged model-ready csv to read")
    parser.add_argument("--out", type=Path, default=FINAL_PATH,
                        help="final model-ready csv to write")
    parser.add_argument("--sync-copies", action=argparse.BooleanOptionalAction,
                        default=True,
                        help="also write byte-identical copies back to the merged "
                             "file and to app/backend/dataset/ (default: on)")
    args = parser.parse_args(argv)

    before = pd.read_csv(args.dataset)
    had_family = "practice_family" in before.columns
    m, default_hits = assign_families(before.copy())

    terminator = detect_line_terminator(args.dataset)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    m.to_csv(args.out, index=False, lineterminator=terminator)
    print("saved", args.out, m.shape, "missing", int(m.isna().sum().sum()))

    if had_family:
        changed = (before["practice_family"].values != m["practice_family"].values).sum()
        print(f"\npractice_family values changed: {int(changed)} of {len(m)} rows")
        if changed:
            moves = pd.crosstab(
                before.loc[before["practice_family"].values != m["practice_family"].values,
                           "practice_family"],
                m.loc[before["practice_family"].values != m["practice_family"].values,
                      "practice_family"],
            )
            print("from (rows) -> to (cols):\n", moves)

    print("\npractice_family distribution:\n", m.practice_family.value_counts())
    print("\npractice_family x source:\n", pd.crosstab(m.practice_family, m.source))
    if default_hits:
        print("\nERA practices that hit NO keyword (defaulted to CPM) -- review:")
        for k, v in sorted(default_hits.items(), key=lambda x: -x[1]):
            print(f"  {v:5d}  {k}")
    else:
        print("\nAll ERA practices matched at least one keyword.")

    if args.sync_copies:
        for target in (args.dataset, BACKEND_PATH):
            if target.resolve() == args.out.resolve():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(args.out, target)
        print("\nsynced copies (md5 must match):")
        for path in {args.out, args.dataset, BACKEND_PATH}:
            print(f"  {md5(path)}  {path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
