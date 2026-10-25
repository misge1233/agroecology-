#!/usr/bin/env python3
"""Normalize a WOCAT export into ``rag/corpus/wocat/technologies.jsonl``.

The export format is **not known yet** — the owner is requesting a research
data export through the Alliance Bioversity-CIAT / WOCAT partnership, and it
may arrive as JSON, NDJSON or CSV with any key spelling. So this module is
built the same way ``fetch_gardian.py`` was for the GARDIAN corpus:

* ``--inspect`` prints the real shape of whatever file arrives — record
  count, top-level keys with fill rates, and one sample record — so the
  adapter can be written against the data instead of against a guess;
* an **adapter interface** (:class:`Adapter`) converts raw records to the
  normalized dicts of ``rag.ingest.wocat.schema``. Two adapters ship now:
  :class:`PassThroughAdapter` (records already in normalized shape — the
  P6a fixtures) and :class:`KeyProbeAdapter` (probes a list of candidate key
  spellings per field, the GARDIAN-style fallback);
* registering a new adapter for the real export is a small, isolated change.

Nothing here fetches anything. Bulk or automated fetching of wocat.net is
forbidden by the project's data-access decision; records come from the
export or from the hand-built fixtures in ``fixtures/``.

Usage (run as a module from the repo root — this is a package)::

    python -m rag.ingest.wocat.normalize_wocat --inspect <export>
    python -m rag.ingest.wocat.normalize_wocat --input rag/ingest/wocat/fixtures
    python -m rag.ingest.wocat.normalize_wocat --input <export> --adapter key_probe
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from .schema import WocatApproach, WocatTechnology, parse_record

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_INPUT = Path(__file__).resolve().parent / "fixtures"
OUTPUT_DIR = REPO_ROOT / "rag" / "corpus" / "wocat"
TECHNOLOGIES_PATH = OUTPUT_DIR / "technologies.jsonl"
APPROACHES_PATH = OUTPUT_DIR / "approaches.jsonl"


# --------------------------------------------------------------- loading
def load_raw(path: Path) -> list[dict[str, Any]]:
    """Read raw records from a file or a directory of files.

    Understands ``.json`` (object or list), ``.jsonl``/``.ndjson`` and
    ``.csv``. Unknown suffixes are skipped with a warning.
    """
    if path.is_dir():
        records: list[dict[str, Any]] = []
        for child in sorted(path.iterdir()):
            if child.is_file():
                records.extend(load_raw(child))
        return records

    suffix = path.suffix.lower()
    if suffix in (".jsonl", ".ndjson"):
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    if suffix == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            return payload
        for key in ("results", "records", "data", "technologies", "items"):
            if isinstance(payload.get(key), list):
                return payload[key]
        return [payload]
    if suffix == ".csv":
        with open(path, encoding="utf-8-sig", newline="") as fh:
            return list(csv.DictReader(fh))
    logger.warning("skipping unsupported file: %s", path)
    return []


def inspect(records: list[dict[str, Any]], sample: int = 1) -> dict[str, Any]:
    """Describe the real shape of an export: keys, fill rates, a sample.

    Printed by ``--inspect`` before any adapter is written, so the adapter is
    built against the data rather than against an assumption.
    """
    keys: Counter[str] = Counter()
    filled: Counter[str] = Counter()
    types: dict[str, Counter[str]] = {}
    for record in records:
        for key, value in record.items():
            keys[key] += 1
            if value not in (None, "", [], {}):
                filled[key] += 1
            types.setdefault(key, Counter())[type(value).__name__] += 1
    return {
        "n_records": len(records),
        "keys": {
            key: {
                "present": n,
                "non_empty": filled[key],
                "types": dict(types[key].most_common()),
            }
            for key, n in keys.most_common()
        },
        "sample": records[:sample],
    }


# -------------------------------------------------------------- adapters
class Adapter:
    """Raw export record -> dict accepted by ``schema.parse_record``."""

    name = "base"

    def adapt(self, record: dict[str, Any]) -> dict[str, Any] | None:
        """Return a normalized dict, or None to skip the record."""
        raise NotImplementedError


class PassThroughAdapter(Adapter):
    """For records already written in the normalized shape (the fixtures)."""

    name = "pass_through"

    def adapt(self, record: dict[str, Any]) -> dict[str, Any] | None:
        if not record.get("wocat_id"):
            logger.warning("record without wocat_id — skipped")
            return None
        return dict(record)


#: Candidate key spellings, most specific first. Extend when the real export
#: arrives and ``--inspect`` shows what it actually calls things.
KEY_CANDIDATES: dict[str, tuple[str, ...]] = {
    "wocat_id": ("wocat_id", "id", "identifier", "code", "technology_id", "pk"),
    "title": ("title", "name", "technology_name", "qg_name"),
    "country": ("country", "countries", "qg_location_country"),
    "region": ("region", "state", "province", "region_state_province"),
    "url": ("url", "link", "permalink", "web_url"),
    "compiler": ("compiler", "compilers", "author", "contributor"),
    "licence": ("licence", "license", "rights"),
    "short_description": ("short_description", "summary", "abstract", "description"),
    "slm_groups": ("slm_groups", "slm_group", "groups", "qg_slm_group"),
    "measures": ("measures", "slm_measures", "measure_codes", "qg_measures"),
    "degradation": ("degradation", "degradation_types", "land_degradation"),
    "land_use": ("land_use", "land_use_types", "landuse"),
    "water_supply": ("water_supply", "watersupply"),
    "rainfall_mm": ("rainfall_mm", "annual_rainfall_mm", "mean_annual_rainfall"),
    "context": ("context", "context_classes", "natural_environment"),
    "landform": ("landform", "landforms"),
    "activities": ("activities", "implementation_activities"),
    "costs": ("costs", "inputs_and_costs"),
    "impacts": ("impacts", "on_site_impacts", "impact_ratings"),
    "cost_benefit": ("cost_benefit", "cost_benefit_analysis", "benefits_vs_costs"),
    "adoption": ("adoption", "adoption_spread"),
    "strengths": ("strengths", "advantages"),
    "weaknesses": ("weaknesses", "disadvantages", "risks"),
    "references": ("references", "publications", "links"),
    "linked_approaches": ("linked_approaches", "approaches", "related_approaches"),
    "record_type": ("record_type", "type", "object_type"),
}


class KeyProbeAdapter(Adapter):
    """Probe :data:`KEY_CANDIDATES` case-insensitively for each field.

    The same defensive pattern ``fetch_gardian.py`` uses: it does not assume
    the export's key spellings, it tries the plausible ones and reports what
    it could not find.
    """

    name = "key_probe"

    def adapt(self, record: dict[str, Any]) -> dict[str, Any] | None:
        lowered = {str(k).lower(): v for k, v in record.items()}
        out: dict[str, Any] = {}
        for field, candidates in KEY_CANDIDATES.items():
            for candidate in candidates:
                value = lowered.get(candidate.lower())
                if value not in (None, "", [], {}):
                    out[field] = value
                    break
        if not out.get("wocat_id"):
            logger.warning("no id key found in record with keys %s", sorted(record))
            return None
        out.setdefault("title", str(out["wocat_id"]))
        out.setdefault("record_type", "technology")
        out.setdefault("provenance", "wocat_export")
        return out


ADAPTERS: dict[str, type[Adapter]] = {
    PassThroughAdapter.name: PassThroughAdapter,
    KeyProbeAdapter.name: KeyProbeAdapter,
}


# ------------------------------------------------------------ normalizing
def normalize(
    records: Iterable[dict[str, Any]], adapter: Adapter
) -> tuple[list[WocatTechnology], list[WocatApproach], list[str]]:
    """Adapt and validate every record. Returns (technologies, approaches, errors)."""
    technologies: list[WocatTechnology] = []
    approaches: list[WocatApproach] = []
    errors: list[str] = []
    for raw in records:
        try:
            adapted = adapter.adapt(raw)
        except Exception as exc:
            errors.append(f"adapter {adapter.name} failed: {exc}")
            continue
        if adapted is None:
            continue
        try:
            parsed = parse_record(adapted)
        except Exception as exc:
            errors.append(f"{adapted.get('wocat_id', '?')}: {exc}")
            continue
        if isinstance(parsed, WocatApproach):
            approaches.append(parsed)
        else:
            technologies.append(parsed)
    return technologies, approaches, errors


def write_jsonl(records: list[Any], path: Path) -> Path:
    """Write validated records as .jsonl, sorted by id for stable output."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for record in sorted(records, key=lambda r: r.wocat_id):
            fh.write(
                json.dumps(record.model_dump(mode="json"), sort_keys=True,
                           ensure_ascii=False)
                + "\n"
            )
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT,
                        help="export file or directory (default: the fixtures)")
    parser.add_argument("--adapter", choices=sorted(ADAPTERS), default="pass_through")
    parser.add_argument("--inspect", action="store_true",
                        help="print the export's real key shape and exit")
    parser.add_argument("--out-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--sample", type=int, default=1)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if not args.input.exists():
        logger.error("input not found: %s", args.input)
        return 2
    raw = load_raw(args.input)
    if args.inspect:
        print(json.dumps(inspect(raw, args.sample), indent=2, ensure_ascii=False,
                         default=str))
        return 0

    technologies, approaches, errors = normalize(raw, ADAPTERS[args.adapter]())
    for error in errors:
        logger.error("%s", error)

    tech_path = write_jsonl(technologies, args.out_dir / TECHNOLOGIES_PATH.name)
    approach_path = write_jsonl(approaches, args.out_dir / APPROACHES_PATH.name)
    logger.info("%d technologies -> %s", len(technologies), tech_path)
    logger.info("%d approaches   -> %s", len(approaches), approach_path)
    synthetic = [t.wocat_id for t in technologies if t.synthetic]
    if synthetic:
        logger.warning(
            "%d SYNTHETIC record(s) in the output (%s) — test scaffolding, "
            "never cite these", len(synthetic), ", ".join(synthetic)
        )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
