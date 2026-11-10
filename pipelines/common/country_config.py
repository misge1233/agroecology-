"""Country configuration: ``countries/<CC>.yaml`` -> :class:`CountryConfig` (roadmap 6.5).

Country is configuration (roadmap principle 5): nothing in the pipelines
hard-codes Ethiopia; it reads ``countries/ET.yaml``. Validation (fail fast):

* ``code`` is two upper-case letters and equals the file name;
* ``status`` is one of :data:`STATUSES`;
* ``bbox`` has ``lon_min < lon_max`` and ``lat_min < lat_max`` within WGS84;
* ``exposure`` thresholds are positive integers;
* when ``status: active``: ``grid`` and the three ``aez`` paths are set and the
  files exist (paths relative to the repository root), ``languages`` and
  ``evidence_sources`` are non-empty. Overlays with ``status: planned`` are not
  checked (their rasters are still to come).

Usage::

    from pipelines.common.country_config import load_country
    cfg = load_country("ET")
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
COUNTRIES_DIR = REPO_ROOT / "countries"
STATUSES = ("active", "draft", "planned", "retired")


class CountryConfigError(ValueError):
    """Raised when a country file is missing or invalid."""


@dataclass(frozen=True)
class BBox:
    """WGS84 bounding box."""

    lon_min: float
    lon_max: float
    lat_min: float
    lat_max: float

    def contains(self, lat: float, lon: float) -> bool:
        """True when ``(lat, lon)`` is inside the box (edges included)."""
        return self.lat_min <= lat <= self.lat_max and self.lon_min <= lon <= self.lon_max


@dataclass(frozen=True)
class Exposure:
    """Thresholds of the challenge/objective exposure rule (roadmap 5.4)."""

    min_rows: int = 30
    min_studies: int = 5
    min_docs: int = 3


@dataclass(frozen=True)
class AEZ:
    """Agro-ecological zone anchor raster, lookup and attributes."""

    anchor_raster: str | None = None
    lookup: str | None = None
    attributes: str | None = None


@dataclass(frozen=True)
class CountryConfig:
    """One validated country configuration."""

    code: str
    name: str
    status: str
    bbox: BBox
    grid: str | None
    aez: AEZ
    languages: tuple[str, ...]
    evidence_sources: tuple[str, ...]
    knowledge_sources: tuple[str, ...]
    exposure: Exposure
    overlays: dict[str, Any] = field(default_factory=dict)
    contact: str | None = None
    path: Path | None = None

    @property
    def active(self) -> bool:
        """True when the country is live in the product."""
        return self.status == "active"

    def resolve(self, rel: str | None, root: Path = REPO_ROOT) -> Path | None:
        """Absolute path of a repo-relative path in the config."""
        return None if rel is None else (root / rel)


def _num(d: dict, key: str, where: str) -> float:
    try:
        return float(d[key])
    except (KeyError, TypeError, ValueError) as exc:
        raise CountryConfigError(f"{where}: bbox.{key} missing or not a number") from exc


def parse_country(data: dict[str, Any], expected_code: str | None = None, root: Path = REPO_ROOT,
                  check_files: bool = True, path: Path | None = None) -> CountryConfig:
    """Validate a parsed YAML mapping and build a :class:`CountryConfig`."""
    where = str(path or expected_code or "country config")
    if not isinstance(data, dict):
        raise CountryConfigError(f"{where}: not a mapping")
    code = str(data.get("code", ""))
    if not re.fullmatch(r"[A-Z]{2}", code):
        raise CountryConfigError(f"{where}: code {code!r} is not ISO 3166-1 alpha-2")
    if expected_code and code != expected_code:
        raise CountryConfigError(f"{where}: code {code} does not match the file name {expected_code}")
    status = str(data.get("status", ""))
    if status not in STATUSES:
        raise CountryConfigError(f"{where}: status {status!r} not in {STATUSES}")
    b = data.get("bbox") or {}
    bbox = BBox(*(_num(b, k, where) for k in ("lon_min", "lon_max", "lat_min", "lat_max")))
    if not (-180 <= bbox.lon_min < bbox.lon_max <= 180):
        raise CountryConfigError(f"{where}: bbox longitudes out of order or range")
    if not (-90 <= bbox.lat_min < bbox.lat_max <= 90):
        raise CountryConfigError(f"{where}: bbox latitudes out of order or range")
    ex = data.get("exposure") or {}
    try:
        exposure = Exposure(int(ex.get("min_rows", 30)), int(ex.get("min_studies", 5)), int(ex.get("min_docs", 3)))
    except (TypeError, ValueError) as exc:
        raise CountryConfigError(f"{where}: exposure thresholds must be integers") from exc
    if min(exposure.min_rows, exposure.min_studies, exposure.min_docs) < 1:
        raise CountryConfigError(f"{where}: exposure thresholds must be >= 1")
    aez_d = data.get("aez") or {}
    aez = AEZ(aez_d.get("anchor_raster"), aez_d.get("lookup"), aez_d.get("attributes"))
    cfg = CountryConfig(
        code=code, name=str(data.get("name", code)), status=status, bbox=bbox, grid=data.get("grid"), aez=aez,
        languages=tuple(data.get("languages") or ()), evidence_sources=tuple(data.get("evidence_sources") or ()),
        knowledge_sources=tuple(data.get("knowledge_sources") or ()), exposure=exposure,
        overlays=dict(data.get("overlays") or {}), contact=data.get("contact"), path=path,
    )
    if status == "active":
        if not cfg.languages or not cfg.evidence_sources:
            raise CountryConfigError(f"{where}: an active country needs languages and evidence_sources")
        required = {"grid": cfg.grid, "aez.anchor_raster": aez.anchor_raster, "aez.lookup": aez.lookup,
                    "aez.attributes": aez.attributes}
        unset = [k for k, v in required.items() if not v]
        if unset:
            raise CountryConfigError(f"{where}: active country with unset paths {unset}")
        if check_files:
            missing = [f"{k}={v}" for k, v in required.items() if not (root / v).exists()]
            if missing:
                raise CountryConfigError(f"{where}: files missing for an active country: {missing}")
    return cfg


def load_country(code: str, countries_dir: Path = COUNTRIES_DIR, root: Path = REPO_ROOT,
                 check_files: bool = True) -> CountryConfig:
    """Read and validate ``countries/<code>.yaml``."""
    code = code.upper()
    path = countries_dir / f"{code}.yaml"
    if not path.exists():
        raise CountryConfigError(f"no country configuration {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return parse_country(data, expected_code=code, root=root, check_files=check_files, path=path)


def list_countries(countries_dir: Path = COUNTRIES_DIR) -> list[str]:
    """Codes of all ``countries/*.yaml`` files."""
    return sorted(p.stem for p in countries_dir.glob("*.yaml") if re.fullmatch(r"[A-Z]{2}", p.stem))
