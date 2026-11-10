#!/usr/bin/env python3
"""Load Habtamu Sewnet's extraction database (Grist export) into the evidence schema.

Input ``data/raw/grist_habtamu/@HabtamuSewnet-MasterData.csv`` (1,617 rows,
47 columns; partner data, git-ignored, never redistributed). The ``.grist``
file next to it is the archival original; :func:`grist_row_count` opens it
read-only with ``sqlite3`` as a cross-check of the row count.

Every row is kept. Text numerics go through :func:`common.parse_quantity`;
each parsing decision is a counted rule in the data card. A range is never a
mean (``range_as_null``) but is a midpoint for reported context
(``range_midpoint``, range kept in ``extra``).

Usage::

    python pipelines/evidence/load_habtamu.py [--dry-run] [--input PATH]
"""
from __future__ import annotations

import argparse
import logging
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipelines.evidence import common, crop_lookup  # noqa: E402
from pipelines.evidence.common import RuleLog  # noqa: E402

logger = logging.getLogger(__name__)

SOURCE = "HAB"
RAW_DIR = common.DATA_DIR / "raw" / "grist_habtamu"
RAW_PATH = RAW_DIR / "@HabtamuSewnet-MasterData.csv"
GRIST_PATH = RAW_DIR / "@HabtamuSewnet.grist"
LICENCE = "partner-unpublished-no-redistribution"
CARD_PATH = common.CARDS_DIR / "HAB.md"

#: Country names as written in the sheet -> ISO 3166-1 alpha-2.
COUNTRY_ISO2 = {
    "argentina": "AR", "australia": "AU", "austria": "AT", "belgium": "BE", "benin": "BJ",
    "brazil": "BR", "burkina faso": "BF", "canada": "CA", "china": "CN", "colombia": "CO",
    "cuba": "CU", "democratic republic of congo": "CD", "denmark": "DK", "el salvador": "SV",
    "estonia": "EE", "ethiopia": "ET", "france": "FR", "germany": "DE", "greece": "GR",
    "guatemala": "GT", "honduras": "HN", "india": "IN", "indonesia": "ID", "iran": "IR",
    "israel": "IL", "italy": "IT", "japan": "JP", "kenya": "KE", "madagascar": "MG",
    "malawi": "MW", "malaysia": "MY", "mali": "ML", "morocco": "MA", "netherlands": "NL",
    "nicaragua": "NI", "nigeria": "NG", "pakistan": "PK", "poland": "PL", "portugal": "PT",
    "romania": "RO", "senegal": "SN", "slovenia": "SI", "south africa": "ZA", "south korea": "KR",
    "spain": "ES", "sri lanka": "LK", "sudan": "SD", "sweden": "SE", "switzerland": "CH",
    "tanzania": "TZ", "tunisia": "TN", "uganda": "UG", "uk": "GB", "united kingdom": "GB",
    "england": "GB", "usa": "US", "united states": "US", "zambia": "ZM", "zimbabwe": "ZW",
}

#: ``Quality_score`` -> ``quality_flag`` (brief B3). Anything else -> NR (counted).
QUALITY_MAP = {
    "high": "High", "medium": "Medium", "medium-high": "Medium", "moderate-high": "Medium",
    "moderate": "Medium", "low": "Low", "nr": "NR", "na": "NR", "": "NR",
}

WORD_NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
                "eight": 8, "nine": 9, "ten": 10, "single": 1}
DURATION_UNITS = [  # (regex, years per unit)
    (r"seasons?|growing seasons?|cropping seasons?|flowering seasons?", 0.5),
    (r"years?|yrs?|yr", 1.0),
    (r"months?", 1.0 / 12.0),
    (r"weeks?", 7.0 / 365.0),
    (r"days?", 1.0 / 365.0),
]

#: Generic climate/zone words; an Agroecological_Zone made only of these does not name a site.
GENERIC_ZONE_WORDS = {
    "mediterranean", "temperate", "tropical", "subtropical", "sub-tropical", "semi-arid", "semiarid",
    "arid", "humid", "sub-humid", "subhumid", "highland", "highlands", "lowland", "lowlands", "midland",
    "zone", "climate", "region", "dry", "wet", "moist", "cool", "warm", "hot", "continental", "oceanic",
    "savanna", "savannah", "agroecological", "agro-ecological", "mixed", "farming", "and", "of", "the",
    "with", "nr", "tropics", "subtropics", "plains", "plain", "forest", "rainfed", "irrigated",
}

#: Separators between principles in ``HLPE_principle`` / ``MFL_domain``.
_HLPE_SPLIT = re.compile(r"\s*(?:;|,|/|\band\b|&)\s*", re.I)


def _s(v) -> str | None:
    return common.clean_str(v)


def read_raw(path: Path = RAW_PATH) -> pd.DataFrame:
    """Read the Grist CSV export as text (no type inference)."""
    if not path.exists():
        raise FileNotFoundError(f"Habtamu input not found: {path}")
    return pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8")


def grist_row_count(path: Path = GRIST_PATH, table: str = "MasterData") -> int | None:
    """Row count of ``table`` in the archival ``.grist`` file (opened read-only), or ``None``."""
    if not path.exists():
        return None
    uri = "file:" + path.resolve().as_posix() + "?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    try:
        return int(con.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
    finally:
        con.close()


def map_country(raw: str | None) -> tuple[str | None, str | None]:
    """``(iso2, flag)``; multi-country values keep the first, flagged ``multi_country``."""
    s = _s(raw)
    if not s:
        return None, "country_missing"
    no_paren = re.sub(r"\s*\(.*?\)\s*", " ", s)
    parts = [p.strip() for p in re.split(r"[;,]", no_paren) if p.strip()]
    if not parts:
        return None, "country_unmapped"
    first = parts[0].lower()
    code = COUNTRY_ISO2.get(first)
    if code is None:
        return None, "country_unmapped"
    return code, ("multi_country_first_kept" if len(parts) > 1 else None)


def parse_duration(raw: str | None) -> tuple[float | None, str]:
    """Intervention duration in years (seasons at 0.5 year, ranges at the midpoint)."""
    s = _s(raw)
    if not s:
        return None, "duration_missing"
    low = s.lower()
    if low.startswith((">", "<", "at least", "more than", "over ", "up to")):
        return None, "duration_bound_set_null"
    for w, n in WORD_NUMBERS.items():
        low = re.sub(rf"\b{w}\b", str(n), low)
    low = low.replace("~", "").replace("≈", "")
    for unit_re, factor in DURATION_UNITS:
        m = re.search(rf"(\d+(?:\.\d+)?)\s*(?:(?:–|—|-|to)\s*(\d+(?:\.\d+)?)\s*)?(?:{unit_re})\b", low)
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            val = ((a + b) / 2.0 if b is not None else a) * factor
            return val, ("duration_range_midpoint" if b is not None else "duration_parsed")
    return None, "duration_unparsed_set_null"


def normalise_principles(raw: str | None) -> str | None:
    """``Recycling; Soil Health`` -> ``Recycling; Soil health`` (case and separators)."""
    s = _s(raw)
    if not s:
        return None
    parts = [p.strip() for p in _HLPE_SPLIT.split(s) if p and p.strip()]
    out: list[str] = []
    for p in parts:
        p = p[:1].upper() + p[1:].lower()
        if p not in out:
            out.append(p)
    return "; ".join(out) or None


def year_from(study_id: str, period: str | None) -> tuple[int | None, str]:
    """Publication year from the ``Study_ID`` suffix, else the last year of ``Study_period``."""
    m = re.search(r"_((?:19|20)\d{2})(?:_\d+|[a-z])?$", study_id)
    if m:
        return int(m.group(1)), "year_from_study_id_suffix"
    years = re.findall(r"(?:19|20)\d{2}", period or "")
    if years:
        return int(years[-1]), "year_from_study_period_last_year"
    return None, "year_missing"


def names_site(zone: str | None) -> bool:
    """True when ``Agroecological_Zone`` names a place rather than only a climate class."""
    s = _s(zone)
    if not s:
        return False
    words = re.findall(r"[A-Za-z][A-Za-z\-]+", s)
    return any(w.lower() not in GENERIC_ZONE_WORDS and w[0].isupper() for w in words)


def crop_from_system(system: str | None, crops: dict[str, str]) -> tuple[str | None, str | None, str]:
    """``(crop, crop_group, rule)`` when ``Cropping_system`` names known crops."""
    s = _s(system)
    if not s:
        return None, None, "crop_missing"
    low = s.lower()
    hits: list[tuple[int, str]] = []
    for name in sorted(crops, key=len, reverse=True):
        m = re.search(rf"\b{re.escape(name)}s?\b", low)
        if m and not any(name in h for _, h in hits):
            hits.append((m.start(), name))
    if not hits:
        return None, None, "crop_not_named"
    hits.sort()
    names = [n for _, n in hits]
    if len(names) == 1:
        return names[0].capitalize(), crops[names[0]], "crop_single_named"
    groups = {crops[n] for n in names}
    group = "Cereal-Legume" if {"Cereal", "Pulse"} <= groups else "Mixed cropping"
    return "-".join(n.capitalize() for n in names), group, "crop_multiple_named"


EXTRA_CROPS = {  # crop -> group, for crops absent from the Ethiopian lookup
    "rice": "Cereal", "corn": "Cereal", "almond": "Perennial-Cash", "olive": "Perennial-Cash",
    "grape": "Fruit", "vineyard": "Fruit", "sugarcane": "Perennial-Cash", "cotton": "Other",
    "cassava": "Root & tuber", "sunflower": "Oilseed", "rapeseed": "Oilseed", "oat": "Cereal",
    "rye": "Cereal", "millet": "Cereal", "cowpea": "Pulse", "pigeon pea": "Pulse",
    "groundnut": "Oilseed", "peanut": "Oilseed", "broccoli": "Vegetable", "beet": "Root & tuber",
    "lentil": "Pulse", "chickpea": "Pulse", "soybean": "Pulse", "cocoa": "Perennial-Cash",
    "tea": "Perennial-Cash", "apple": "Fruit", "mango": "Fruit", "citrus": "Fruit",
}
NOT_CROPS = {"mixed", "various", "cropland", "forest", "homestead", "plantation forest", "woodland",
             "bushland", "rangeland", "grazing land", "exclosure", "mixed crop-livestock", "mixed cereals"}


def known_crops(lookup: crop_lookup.CropLookup) -> dict[str, str]:
    """Crop name (lower case) -> group: harmonised ERA/CSA crops plus :data:`EXTRA_CROPS`."""
    out = {c: g for c, g in lookup.crops().items() if c not in NOT_CROPS and "-" not in c and " intercrop" not in c}
    for c, g in EXTRA_CROPS.items():
        out.setdefault(c, g)
    return out


def load(path: Path = RAW_PATH, crops: crop_lookup.CropLookup | None = None) -> tuple[pd.DataFrame, RuleLog, pd.DataFrame]:
    """Return ``(frame, rule_log, raw)`` for the Habtamu sheet."""
    raw = read_raw(path)
    lookup = crops if crops is not None else crop_lookup.load_lookup(missing_ok=True)
    crop_names = known_crops(lookup)
    log = RuleLog()
    rules: Counter = Counter()
    df = pd.DataFrame(index=raw.index)
    df["source"] = SOURCE
    sid_raw = raw["Study_ID"].str.strip()
    df["study_id"] = "HAB_" + sid_raw.map(common.slug)
    blank_sid = sid_raw == ""
    log.parse("study_id_blank_slugged_unknown", int(blank_sid.sum()))

    doi, non_doi = [], []
    for v in raw["DOI"]:
        d, o = common.normalise_doi(v)
        doi.append(d)
        non_doi.append(o)
    df["doi"] = doi
    log.parse("doi_normalised", sum(d is not None for d in doi))
    log.parse("doi_non_doi_identifier_to_extra", sum(o is not None for o in non_doi))
    df["citation"] = [s if s else "Unknown study" for s in sid_raw]
    years = [year_from(s, p) for s, p in zip(sid_raw, raw["Study_period"])]
    df["year"] = pd.array([y for y, _ in years], dtype="Int64")
    rules.update(r for _, r in years)

    countries = [map_country(c) for c in raw["Country"]]
    df["country"] = [c for c, _ in countries]
    rules.update(f for _, f in countries if f)
    unmapped = Counter(_s(c) or "(blank)" for c, (code, _) in zip(raw["Country"], countries) if code is None)
    multi = Counter(_s(c) for c, (_, f) in zip(raw["Country"], countries) if f == "multi_country_first_kept")

    df["lat"] = np.nan
    df["lon"] = np.nan
    site = [names_site(z) for z in raw["Agroecological_Zone"]]
    df["loc_precision"] = ["site" if s else "country" for s in site]
    df["loc_method"] = "none"
    log.parse("loc_site_named_no_coordinates", sum(site))
    log.parse("loc_country_only", len(site) - sum(site))
    df["site_name"] = common.omap(raw["Agroecological_Zone"], _s)

    df["practice_raw"] = [(_s(v) or "(blank)") for v in raw["Intervention_type"]]
    df["comparator"] = common.omap(raw["Comparator_description"], _s)
    df["outcome_raw"] = [(_s(v) or "(blank)") for v in raw["Outcome_name"]]
    df["_outcome_key"] = df["outcome_raw"]
    df["unit"] = common.omap(raw["Unit"], _s)

    def num(col: str, kind: str = "mean") -> list[float | None]:
        vals = []
        for v in raw[col]:
            p = common.parse_quantity(v, kind)
            rules[f"{col}:{p.rule}"] += 1
            vals.append(p.value)
        return vals

    for src, dst in (("Mean_with", "mean_with"), ("Mean_without", "mean_without"),
                     ("SD_with", "sd_with"), ("SD_without", "sd_without"),
                     ("SE_with", "se_with"), ("SE_without", "se_without"),
                     ("N_with", "n_with"), ("N_without", "n_without")):
        df[dst] = pd.to_numeric(pd.Series(num(src), index=raw.index), errors="coerce")
    for c in ("n_with", "n_without"):
        frac = df[c].notna() & (df[c] % 1 != 0)
        log.parse(f"{c}_not_integer_set_null", int(frac.sum()))
        df[c] = df[c].where(~frac & (df[c] > 0)).round().astype("Int64")

    durations = [parse_duration(v) for v in raw["Intervention_duration"]]
    df["duration_years"] = [d for d, _ in durations]
    rules.update(r for _, r in durations)
    df["study_design"] = common.omap(raw["Study_design"], _s)
    df["replication"] = common.omap(raw["Replication_level"], _s)
    df["scale"] = common.omap(raw["Scale_study"], _s)

    q_raw = raw["Quality_score"].str.strip()
    q_key = q_raw.str.lower().str.replace("–", "-", regex=False).str.replace("—", "-", regex=False)
    df["quality_flag"] = [QUALITY_MAP.get(k, "NR") for k in q_key]
    unparsed_q = ~q_key.isin(list(QUALITY_MAP))
    log.parse("quality_high", int((df["quality_flag"] == "High").sum()))
    log.parse("quality_medium_from_medium_moderate_or_medium_high", int((df["quality_flag"] == "Medium").sum()))
    log.parse("quality_nr_reported", int(((df["quality_flag"] == "NR") & ~unparsed_q).sum()))
    log.parse("quality_unparsed_value_set_nr (shifted cells such as years or scales; raw kept in extra)",
              int(unparsed_q.sum()))

    ctx = {}
    for src, dst in (("Precipitation", "ctx_reported_rain_mm"), ("Altitude", "ctx_reported_altitude_m")):
        vals, ranges = [], []
        for v in raw[src]:
            p = common.parse_quantity(v, kind="context")
            rules[f"{src}:{p.rule}"] += 1
            vals.append(p.value)
            ranges.append(f"{p.low:g}-{p.high:g}" if p.low is not None else None)
        df[dst] = vals
        ctx[src] = ranges
    slope_vals = []
    for v in raw["Slope_topography"]:
        s = _s(v)
        p = common.parse_quantity(s, kind="context") if s and "%" in s else None
        slope_vals.append(p.value if p else None)
    df["ctx_reported_slope_pct"] = slope_vals
    log.parse("slope_percent_parsed", sum(v is not None for v in slope_vals))
    df["ctx_reported_soil"] = common.omap(raw["Soil"], _s)
    df["ctx_reported_aez"] = common.omap(raw["Agroecological_Zone"], _s)
    df["ctx_release"] = None

    crop_hits = [crop_from_system(v, crop_names) for v in raw["Cropping_system"]]
    df["crop"] = [c for c, _, _ in crop_hits]
    df["crop_group"] = [g for _, g, _ in crop_hits]
    rules.update(r for _, _, r in crop_hits)

    df["evidence_text"] = common.omap(raw["Supporting Evidence"], _s)
    df["extraction_locator"] = common.omap(raw["Extraction Source (Location in PDF)"], _s)
    df["licence"] = LICENCE
    df["hlpe_principle"] = [normalise_principles(v) for v in raw["HLPE_principle"]]
    df["mfl_domain"] = [normalise_principles(v) for v in raw["MFL_domain"]]

    df["row_id"] = common.make_row_ids(SOURCE, df["study_id"])
    dup_of = common.mark_duplicates(raw, list(raw.columns), df["row_id"])
    log.parse("exact_duplicate_of_earlier_row_flagged_in_extra", int(dup_of.notna().sum()))

    stat_cols = ["p-value", "t-value", "F-value", "x2-value", "correlation-r", "R²",
                 "CI_lower_with", "CI_upper_with", "CI_lower_without", "CI_upper_without", "CV_with", "CV_without"]
    extras = []
    for i in raw.index:
        r = raw.loc[i]
        e = {c: _s(r[c]) for c in stat_cols}
        e.update({
            "Outcome_type(domain)": _s(r["Outcome_type(domain)"]),
            "Measurement_method": _s(r["Measurement_method"]),
            "Cropping_system": _s(r["Cropping_system"]),
            "Intervention_duration": _s(r["Intervention_duration"]),
            "Study_period": _s(r["Study_period"]),
            "Continent": _s(r["Continent"]),
            "Country_raw": _s(r["Country"]),
            "Climate_Koppen_Class": _s(r["Climate_Koppen_Class"]),
            "Slope_topography": _s(r["Slope_topography"]),
            "Precipitation_raw": _s(r["Precipitation"]),
            "Precipitation_range": ctx["Precipitation"][i],
            "Altitude_raw": _s(r["Altitude"]),
            "Altitude_range": ctx["Altitude"][i],
            "Quality_score_raw": _s(r["Quality_score"]) if unparsed_q[i] else None,
            "doi_raw": non_doi[i],
            "Study_ID_raw": _s(r["Study_ID"]),
            "dup_of": dup_of[i],
        })
        for col in ("Mean_with", "Mean_without"):
            p = common.parse_quantity(r[col])
            if p.rule == "range_as_null":
                e[f"{col}_range"] = f"{p.low:g}-{p.high:g}"
        extras.append(common.json_extra(e))
    df["extra"] = extras

    df["lrr"] = common.lrr_series(df["mean_with"], df["mean_without"])
    df["var_lrr"] = common.var_lrr_series(df)
    sd_zero = (df["sd_with"].notna() & df["sd_without"].notna() & df["n_with"].notna() & df["n_without"].notna()
               & df["lrr"].notna() & df["var_lrr"].isna())
    log.parse("lrr_computable_both_means_positive", int(df["lrr"].notna().sum()))
    log.parse("lrr_null_mean_missing_or_not_positive", int(df["lrr"].isna().sum()))
    log.parse("var_lrr_delta_method_sd_and_n", int(df["var_lrr"].notna().sum()))
    log.parse("var_lrr_null_sd_zero", int(sd_zero.sum()))
    for k in sorted(rules):
        log.parse(k, rules[k])
    log.drop("rows_dropped_by_loader", 0)
    if unmapped:
        log.note("Unmapped country values (row counts): " + ", ".join(f"{k} ({v})" for k, v in unmapped.most_common()))
    if multi:
        log.note("Multi-country values, first kept: " + ", ".join(f"{k} ({v})" for k, v in multi.most_common()))
    log.note("No coordinates in the source: `lat`/`lon` are null, `loc_method = none`. `loc_precision = site` "
             "when `Agroecological_Zone` contains a capitalised word that is not a generic climate term "
             "(the zone names a place); otherwise `country`. Geocoding is phase E2 (roadmap 5.5).")
    log.note("`var_lrr` uses the SDs as given; SEs are not converted to SDs for this source (brief B3: "
             "'sd_*, se_*, n_* as given'), so rows with SE and N but no SD have no variance yet.")
    log.note("`evidence_text` = `Supporting Evidence` and `extraction_locator` = `Extraction Source "
             "(Location in PDF)` as the brief specifies. In the sheet these two columns are partly "
             "inverted: the locator column often holds a topic label ('Organic amendment') and the "
             "evidence column a table reference or a p-value. Kept as given; flagged for Habtamu.")
    logger.info("HAB: %d rows read, %d kept", len(raw), len(df))
    return df, log, raw


def main(argv: list[str] | None = None) -> int:
    """CLI: load, cross-check with the .grist file and summarise."""
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--input", type=Path, default=RAW_PATH)
    ap.add_argument("--dry-run", action="store_true", help="load and report only (default for this loader)")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    common.setup_logging(args.verbose)
    df, log, _ = load(args.input)
    et = df["country"] == "ET"
    print(f"HAB rows: {len(df):,} (.grist MasterData: {grist_row_count()}); lrr {df.lrr.notna().sum():,}; "
          f"var_lrr {df.var_lrr.notna().sum():,}; Ethiopia {int(et.sum())} ({int((et & df.lrr.notna()).sum())} with lrr)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
