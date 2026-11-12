#!/usr/bin/env python3
"""Build the unified evidence store (brief B4).

Runs the three loaders (ERA, CSA, Habtamu), the catalogue parser, the taxonomy
proposal (rules only; reviewed rows are never overwritten), applies the
taxonomies (``practice_id``, ``practice_family``, ``practice_components``,
``outcome_id``, ``direction``), computes ``weight``, validates against the
frozen schema and writes:

* ``data/evidence/evidence_rows.parquet`` + ``evidence_rows.csv`` + ``store_manifest.json``
  (the rows are git-ignored: partner data);
* ``data/evidence/cards/{ERA,CSA,HAB}.md``;
* ``data/evidence/README.md``;
* a one-screen summary on stdout.

Weights: ``1 / var_lrr`` where a variance exists, capped at its 99th percentile;
otherwise ``factor(quality_flag) x median(capped inverse variance)`` with
factors High 1.0, Medium 0.8, NR 0.8, Low 0.5 (NR is treated like Medium: the
source did not rate the study, which is not evidence of low quality).

Usage::

    python pipelines/evidence/build_evidence_store.py [--dry-run] [--skip-hab] [--no-propose]
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipelines.evidence import (  # noqa: E402
    common, crop_lookup, load_csa, load_era, load_habtamu, parse_catalogue, reconcile, schema,
)
from pipelines.taxonomy import propose_mappings  # noqa: E402
from pipelines.taxonomy import taxonomy_io as tio  # noqa: E402

logger = logging.getLogger(__name__)

QUALITY_FACTOR = {"High": 1.0, "Medium": 0.8, "NR": 0.8, "Low": 0.5}
INV_VAR_CAP_QUANTILE = 0.99
README_PATH = common.EVIDENCE_DIR / "README.md"


# ------------------------------------------------------------------- weights
def compute_weights(df: pd.DataFrame) -> tuple[pd.Series, dict]:
    """Inverse-variance weights with a quality-based default; returns ``(weights, params)``."""
    var = pd.to_numeric(df["var_lrr"], errors="coerce")
    inv = 1.0 / var.where(var > 0)
    cap = float(inv.quantile(INV_VAR_CAP_QUANTILE)) if inv.notna().any() else 1.0
    capped = inv.clip(upper=cap)
    med = float(capped.median()) if capped.notna().any() else 1.0
    default = df["quality_flag"].map(QUALITY_FACTOR).fillna(QUALITY_FACTOR["NR"]) * med
    w = capped.where(capped.notna(), default).astype("float64")
    params = {"method": "inverse variance, capped at the 99th percentile; default = factor(quality) x median",
              "cap": cap, "median_inverse_variance": med, "quality_factor": QUALITY_FACTOR,
              "n_inverse_variance": int(capped.notna().sum()), "n_default": int(capped.isna().sum())}
    return w, params


# ----------------------------------------------------------------- taxonomy
def apply_taxonomy(df: pd.DataFrame, tax: tio.Taxonomy, source: str) -> pd.DataFrame:
    """Fill practice and outcome ids, family, components and reviewed direction."""
    out = df.copy()
    pl, ol = tax.practice_lookup(), tax.outcome_lookup()
    prac = tax.practices.set_index("practice_id")
    dirs = tax.outcome_directions()
    out["practice_id"] = common.omap(out["practice_raw"], lambda p: pl.get((source, p)))
    out["practice_family"] = common.omap(out["practice_id"], lambda p: prac["practice_family"].get(p) if p else None)
    out["practice_components"] = common.omap(
        out["practice_id"], lambda p: (prac["components"].get(p) or None) if p else None)
    out["outcome_id"] = common.omap(out["_outcome_key"], lambda o: ol.get((source, o)))
    out["direction"] = pd.array([dirs.get(o) if o else None for o in out["outcome_id"]], dtype="Int64")
    out["direction_reviewed"] = out["direction"].notna()
    return out


# -------------------------------------------------------------------- cards
def geocoding_section(h: pd.DataFrame) -> str:
    """HAB card section: review-sheet coverage and what the store holds now."""
    from pipelines.evidence import geocode_sites

    lines = []
    if geocode_sites.REVIEW_CSV.exists():
        sheet = pd.read_csv(geocode_sites.REVIEW_CSV, dtype=str, keep_default_na=False)
        cov = geocode_sites.coverage(sheet)
        lines += [
            f"Review sheet `{geocode_sites.REVIEW_CSV.relative_to(common.REPO_ROOT).as_posix()}`: "
            f"{len(sheet)} studies, every row with a quote ({cov['with_quote']}), quote found verbatim in the "
            f"source text for {cov['quote_verified']}. Accepted by a reviewer: "
            f"{int((sheet['accepted'].str.lower() == 'yes').sum())}.", "",
            "| Scope | Studies | Site | District | Country | Site or district |", "|---|---:|---:|---:|---:|---:|",
        ]
        for name, key in (("All studies", "all"), ("Ethiopian studies", "ET_studies"), ("Ethiopian DOIs", "ET_dois")):
            c = cov[key]
            bp = c["by_precision"]
            lines.append(f"| {name} | {c['n']} | {bp.get('site', 0)} | {bp.get('district', 0)} | "
                         f"{bp.get('country', 0)} | {c['site_or_district']} ({c['share']:.0%}) |")
        lines.append("")
    else:
        lines.append("No geocoding review sheet yet (`python pipelines/evidence/geocode_sites.py --llm`).")
    lines.append("Store rows by `loc_method`: " + ", ".join(
        f"{k} {v:,}" for k, v in h["loc_method"].value_counts().items()) + ". Rows with "
        "`geocoded_llm_unchecked` stay out of training (E3/E5 filter) until a reviewer accepts them.")
    return "\n".join(lines)



def _mapping_section(df: pd.DataFrame) -> str:
    n = max(len(df), 1)
    lines = ["| Field | Rows mapped | Share |", "|---|---:|---:|"]
    for c in ("practice_id", "outcome_id", "direction"):
        k = int(df[c].notna().sum())
        lines.append(f"| `{c}`{' (reviewed)' if c == 'direction' else ''} | {k:,} | {k / n:.1%} |")
    return "\n".join(lines)


def write_card(source: str, df: pd.DataFrame, log: common.RuleLog, rows_read: int, inputs: list[str],
               licence: str, provenance: list[str], sections: dict[str, str], dry_run: bool) -> str:
    """Render and (unless dry run) write ``cards/<source>.md``."""
    cov = common.coverage(df, ["doi", "year", "country", "lat", "site_name", "practice_id", "outcome_id",
                               "direction", "crop", "crop_group", "unit", "mean_with", "mean_without", "sd_with",
                               "n_with", "lrr", "var_lrr", "duration_years", "ctx_reported_rain_mm",
                               "ctx_reported_altitude_m", "ctx_reported_soil", "ctx_reported_aez", "evidence_text"])
    sections = {"Taxonomy mapping (rules, not yet human-accepted)": _mapping_section(df), **sections}
    text = common.render_card(source, {"ERA": "ERA Ethiopia", "CSA": "Adimassu et al. CSA compilation",
                                       "HAB": "Habtamu Sewnet extraction database"}[source],
                              inputs, rows_read, len(df), log, cov, licence, provenance, sections)
    if not dry_run:
        common.write_text(common.CARDS_DIR / f"{source}.md", text)
    return text


# ------------------------------------------------------------------ summary
def summary(df: pd.DataFrame, outcomes: pd.DataFrame) -> str:
    """One-screen summary of the store."""
    grp = df["outcome_id"].map(dict(zip(outcomes["outcome_id"], outcomes["objective_group"])))
    lines = [f"Evidence store: {len(df):,} rows, {df['study_id'].nunique():,} studies, schema {schema.SCHEMA_VERSION}"]

    def block(title: str, s: pd.Series, top: int = 12) -> None:
        vc = s.fillna("(unmapped)").value_counts()
        shown = ", ".join(f"{k} {v:,}" for k, v in vc.head(top).items())
        more = f", +{len(vc) - top} more" if len(vc) > top else ""
        lines.append(f"  {title}: {shown}{more}")

    block("per source", df["source"])
    block("per country", df["country"], top=8)
    block("per family", df["practice_family"])
    block("per objective group", grp)
    lines.append(f"  with coordinates: {df['lat'].notna().mean():.1%}   with var_lrr: {df['var_lrr'].notna().mean():.1%}"
                 f"   with lrr: {df['lrr'].notna().mean():.1%}   reviewed direction: {df['direction_reviewed'].mean():.1%}")
    return "\n".join(lines)


def write_readme(manifest: dict, summary_text: str, dry_run: bool) -> str:
    """``data/evidence/README.md``: what the store is, how to rebuild it, what the cards say."""
    rows = manifest.get("rows_per_source", {})
    text = f"""# data/evidence: the unified evidence store

One table of with/without contrasts from every field-evidence source, in one
frozen schema with provenance (schema version {schema.SCHEMA_VERSION}, roadmap
Appendix A; `pipelines/evidence/schema.py`). Every later phase reads this store;
no engine reads a raw file.

| File | In git | What it is |
|---|---|---|
| `evidence_rows.parquet` | no (partner data) | the store (pyarrow, zstd) |
| `evidence_rows.csv` | no (partner data) | CSV mirror for inspection |
| `store_manifest.json` | yes | schema version, rows per source, build time, git commit, SHA-256 of every input, weight parameters, validation report, reconciliation results |
| `cards/ERA.md`, `cards/CSA.md`, `cards/HAB.md` | yes | one data card per source |
| `registry_ET.json` | yes | challenges and objectives for Ethiopia with exposure flags (`build_registry.py`) |
| `review/geocoding_review.csv`, `.html` | yes | E2: one row per Habtamu study (site, coordinates, precision, method, confidence, quote) and a Leaflet map for the reviewer |
| `review/habtamu_papers_missing.csv` | yes | E2: Habtamu papers with a DOI but no open-access full text (landing URL for the owner) |
| `hab_geocoding.csv` | yes | E2: geocoding applied to the store (`geocode_sites.py --apply-geocoding`) |

Last build: {manifest.get('built_at', 'n/a')} (commit `{manifest.get('git_commit') or 'n/a'}`):
{', '.join(f'{k} {v:,}' for k, v in rows.items())} rows.

```
{summary_text}
```

## Rebuild

```bash
python -m pip install -r pipelines/requirements.txt        # once, in the backend venv
python pipelines/evidence/crop_lookup.py                   # only if data/taxonomy/crop_harmonisation.csv is missing
python pipelines/evidence/parse_catalogue.py               # catalogue docx -> data/taxonomy/catalogue_entries.*
python pipelines/evidence/build_evidence_store.py          # loaders + taxonomy rules + store + cards + this README
python pipelines/evidence/build_registry.py --country ET   # registry_ET.json (prints the change against the file on disk)
# E2: reviews, geocoding
python pipelines/taxonomy/propose_mappings.py --apply-outcome-review   # accepted rows of review/outcomes_direction_review.csv
python pipelines/taxonomy/propose_mappings.py --apply-review           # accepted Habtamu sheet rows and practice merges
python pipelines/evidence/fetch_habtamu_papers.py --email you@example.org
python pipelines/evidence/geocode_sites.py --llm                       # review sheet + map
python pipelines/evidence/geocode_sites.py --apply-geocoding           # writes hab_geocoding.csv, rebuilds store and registry
python -m pytest pipelines -q                              # unit tests (+ data tests when the raw files exist)
```

Every script takes `--dry-run` (compute and report, write nothing).

## Rules that matter when reading the store

- **Row** = one with/without contrast. `row_id = <source>:<study_id>:<n>`.
- **`lrr`** is always `ln(mean_with / mean_without)` when both means are positive, else null;
  a mean is never flipped. **`direction`** comes from the outcome taxonomy and is null
  (`direction_reviewed = false`) until a human has reviewed the outcome; such rows are
  excluded from any ranking use. Only the 7 legacy indicators are reviewed today
  (their direction is `recommend.DIRECTION`).
- **`var_lrr`** is the delta-method variance, only when both SDs and both Ns exist.
- **`weight`** = inverse variance (capped at the 99th percentile) or a default of
  `factor(quality_flag) x median inverse variance` (factors in the manifest).
- **Nothing is dropped**: the loaders keep every source row. Rows that the legacy model
  excluded (other outcomes, non-positive means, ratios above 20, duplicates) are in the store;
  exact repeats carry `extra.dup_of`. The legacy rules are applied only by the
  reconciliation (`pipelines/evidence/reconcile.py`), which reproduces the 7,250 ERA and
  1,414 CSA rows of `data/processed/CSA_ERA_final_model_ready.csv`.
- **Schema 1.1 (E2)**: the taxonomy gains the `climate` objective group and the outcome statuses
  `excluded`, `context_dependent` and `merged`; their rows keep their `outcome_id` but carry
  `direction = null` and never count.
- **Location (E2)**: Habtamu rows geocoded from the papers carry `loc_method =
  geocoded_llm_unchecked` until a reviewer accepts the row in `review/geocoding_review.csv`
  (`geocoded_llm_checked`); unchecked rows stay out of training (E3/E5 filter).
- `practice_components` is a `;`-joined list; `extra` is a JSON object; `ctx_reported_slope_pct`
  is an extra `ctx_` column (validated by prefix).
- Taxonomy ids come from rule mappings in `data/taxonomy/*_aliases.csv` with `accepted` empty:
  proposals, not decisions. See `data/taxonomy/README.md`.

## What each card says

Rows read and kept, rows dropped per rule (zero for all three loaders), every parsing and
mapping rule with its row count, coverage of key fields, licence and provenance, the
taxonomy mapping coverage and, for ERA and CSA, the reconciliation table with the result.
The HAB card adds the `.grist` row-count cross-check and the Ethiopian counts.
"""
    if not dry_run:
        common.write_text(README_PATH, text)
    return text


# ---------------------------------------------------------------------- main
def build(dry_run: bool = False, skip_hab: bool = False, propose: bool = True) -> dict:
    """Run the whole build; returns the manifest (also when ``dry_run``)."""
    if not crop_lookup.LOOKUP_PATH.exists():
        logger.warning("crop lookup missing: deriving it from the frozen files")
        tab = crop_lookup.derive()
        if not dry_run:
            crop_lookup.LOOKUP_PATH.parent.mkdir(parents=True, exist_ok=True)
            tab.to_csv(crop_lookup.LOOKUP_PATH, index=False, lineterminator="\n", encoding="utf-8")
    crops = crop_lookup.load_lookup(missing_ok=True)

    era, era_log, era_raw = load_era.load(crops=crops)
    csa, csa_log, csa_raw = load_csa.load(crops=crops)
    frames = {"ERA": era, "CSA": csa}
    logs = {"ERA": (era_log, len(era_raw)), "CSA": (csa_log, len(csa_raw))}
    have_hab = not skip_hab and load_habtamu.RAW_PATH.exists()
    if have_hab:
        from pipelines.evidence import geocode_sites

        hab, hab_log, hab_raw = load_habtamu.load(crops=crops)
        hab = geocode_sites.apply_to_frame(hab, log=hab_log)  # E2: applied geocoding, if any
        from pipelines.evidence import load_fresh

        if load_fresh.available():  # E7 A6: the fresh_2024plus test set, same format, marked in `extra`
            fresh, fresh_log = load_fresh.load(crops=crops)
            if len(fresh):
                hab = pd.concat([hab, schema.coerce(fresh)], ignore_index=True)
            for k, v in fresh_log.parsing.items():
                hab_log.parse(f"fresh_2024plus {k}", v)
            for k, v in fresh_log.dropped.items():
                hab_log.drop(f"fresh_2024plus {k}", v)
        frames["HAB"] = hab
        logs["HAB"] = (hab_log, len(hab_raw))
    elif not skip_hab:
        logger.warning("Habtamu file missing (%s): store built without HAB", load_habtamu.RAW_PATH)

    if parse_catalogue.RAW_PATH.exists():
        entries = parse_catalogue.parse()
        parse_catalogue.check(entries)
        if not dry_run:
            parse_catalogue.write(entries)
        catalogue = [asdict(e) for e in entries]
    elif parse_catalogue.OUT_JSON.exists():
        catalogue = json.loads(parse_catalogue.OUT_JSON.read_text(encoding="utf-8"))
    else:
        logger.warning("catalogue missing: practices seeded without catalogue entries")
        catalogue = []

    if propose:
        tax, cov = propose_mappings.run(frames, catalogue, write=not dry_run)
    else:
        tax = tio.Taxonomy.load()
        cov = {"rows": propose_mappings.row_coverage(frames, tax, catalogue)}

    mapped = {src: apply_taxonomy(df, tax, src) for src, df in frames.items()}
    store = pd.concat([schema.coerce(m) for m in mapped.values()], ignore_index=True)
    store = store.drop(columns=[c for c in store.columns if c.startswith("_")])
    store["weight"], weight_params = compute_weights(store)
    store = schema.coerce(store)
    report = schema.validate(store, strict=True, outcome_directions=tax.outcome_directions())

    recon = {"ERA": reconcile.reconcile(era, "ERA"), "CSA": reconcile.reconcile(csa, "CSA")}
    grist = load_habtamu.grist_row_count() if have_hab else None

    by_src = {s: store[store["source"] == s] for s in frames}
    inputs = {"ERA": [load_era.RAW_PATH], "CSA": [load_csa.RAW_PATH, load_csa.REFS_PATH],
              "HAB": [load_habtamu.RAW_PATH]}
    common_inputs = [crop_lookup.LOOKUP_PATH, reconcile.FINAL_PATH, parse_catalogue.RAW_PATH,
                     tio.PRACTICES, tio.PRACTICE_ALIASES, tio.OUTCOMES, tio.OUTCOME_ALIASES, tio.CHALLENGES]

    rel = lambda p: Path(p).resolve().relative_to(common.REPO_ROOT).as_posix()  # noqa: E731
    sections: dict[str, dict[str, str]] = {
        "ERA": {"Reconciliation with the frozen dataset (brief B1)": recon["ERA"].markdown(),
                "Outcomes (top 15 by rows)": common.counts_table(by_src["ERA"]["outcome_id"], ("outcome_id", "Rows"), 15)},
        "CSA": {"Reconciliation with the frozen dataset (brief B2)": recon["CSA"].markdown(),
                "Outcomes (top 15 by rows)": common.counts_table(by_src["CSA"]["outcome_id"], ("outcome_id", "Rows"), 15)},
    }
    prov = {
        "ERA": ["ERA (Evidence for Resilient Agriculture) Ethiopia extract, Harvard Dataverse; terms of the Dataverse "
                "record apply (licence tag to be confirmed by the owner).",
                "`study_id = ERA_<Code>` equals the frozen `Study_No_`; `extraction_locator` = ERA `DataLoc`.",
                "All 14,792 rows kept, including the 59 outcome codes outside the 7 model indicators."],
        "CSA": ["Adimassu et al. compilation workbook (Ethiopian with/without studies), internal to the project.",
                "Citations from `data/processed/csa_study_references.json` (`build_csa_references.py`).",
                "No dispersion or sample size in the source."],
        "HAB": ["Habtamu Sewnet's extraction database (Grist), shared for this project only: unpublished partner "
                "data, git-ignored, never redistributed (`evidence_rows.*` are git-ignored).",
                f"Archival `.grist` cross-check (sqlite, read-only): MasterData has {grist} rows; CSV has "
                f"{logs['HAB'][1] if 'HAB' in logs else 'n/a'} rows." if have_hab else "HAB not loaded."],
    }
    if have_hab:
        h = by_src["HAB"]
        et = h["country"] == "ET"
        sections["HAB"] = {
            "Counts against the 10 Nov profile": "\n".join([
                "| Count | Expected (profile) | Actual |", "|---|---:|---:|",
                f"| rows | 1,617 | {len(h):,} |",
                f"| rows with a computable `lrr` | 1,312 | {int(h['lrr'].notna().sum()):,} |",
                f"| rows with `var_lrr` | 646 | {int(h['var_lrr'].notna().sum()):,} |",
                f"| Ethiopian rows | 158 | {int(et.sum()):,} |",
                f"| Ethiopian rows with `lrr` | 129 | {int((et & h['lrr'].notna()).sum()):,} |",
                f"| `.grist` MasterData rows | 1,617 | {grist} |",
                "",
                "`var_lrr` is 3 below the profile because 3 rows report SD = 0 for both arms (a zero variance "
                "is not usable as an inverse-variance weight; counted as `var_lrr_null_sd_zero`).",
            ]),
            "Geocoding (E2, roadmap 5.5)": geocoding_section(h),
            "Countries (top 15)": common.counts_table(h["country"], ("country", "Rows"), 15),
            "Outcomes mapped (top 15)": common.counts_table(h["outcome_id"], ("outcome_id", "Rows"), 15),
        }
    for src in frames:
        log, n_read = logs[src]
        lic = {"ERA": load_era.LICENCE, "CSA": load_csa.LICENCE, "HAB": load_habtamu.LICENCE}[src]
        write_card(src, by_src[src], log, n_read, [rel(p) for p in inputs[src] if Path(p).exists()],
                   lic, prov[src], sections.get(src, {}), dry_run)

    manifest_extra = {
        "weights": weight_params,
        "validation": report.to_dict(),
        "reconciliation": {k: {"exact": v.exact, "expected": v.n_expected, "reproduced": v.n_reproduced,
                               "only_in_store": v.only_in_store, "only_in_frozen": v.only_in_frozen,
                               "max_abs_lrr_diff": v.max_abs_lrr_diff} for k, v in recon.items()},
        "mapping_coverage_rows": cov["rows"],
        "habtamu_grist_rows": grist,
        "catalogue_entries": len(catalogue),
    }
    all_inputs = [p for src in frames for p in inputs[src]] + common_inputs
    if dry_run:
        manifest = {"schema_version": schema.SCHEMA_VERSION, "n_rows": len(store),
                    "rows_per_source": store["source"].value_counts().to_dict(), **manifest_extra}
    else:
        manifest = schema.write_store(store, common.EVIDENCE_DIR, input_files=all_inputs, extra_manifest=manifest_extra)
    text = summary(store, tax.outcomes)
    write_readme(manifest, text, dry_run)
    print(text)
    print(f"Validation: {report.summary()}")
    for k, v in recon.items():
        print(f"Reconciliation {k}: {'EXACT' if v.exact else 'RESIDUAL'} ({v.n_reproduced:,} of {v.n_expected:,}; "
              f"max |dlrr| {v.max_abs_lrr_diff:.1e})")
    propose_mappings.print_coverage(cov) if "review_rows" in cov else None
    if dry_run:
        print("(dry run: nothing written)")
    return manifest


def main(argv: list[str] | None = None) -> int:
    """CLI."""
    ap = argparse.ArgumentParser(description="Build the unified evidence store.")
    ap.add_argument("--dry-run", action="store_true", help="build and validate in memory, write nothing")
    ap.add_argument("--skip-hab", action="store_true", help="build without the Habtamu source")
    ap.add_argument("--no-propose", action="store_true", help="use the taxonomy files as they are (no rule refresh)")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    common.setup_logging(args.verbose)
    build(dry_run=args.dry_run, skip_hab=args.skip_hab, propose=not args.no_propose)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
