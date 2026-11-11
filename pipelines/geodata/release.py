"""Release folder, manifest, VRT, README and diffs (brief E3 A1, A3).

A release lives in ``geodata/<CC>/<release>/`` and is **immutable**: it is built in
``geodata/<CC>/.<release>.partial/`` and renamed into place only after
``manifest.json`` is written; an existing release id is refused. The staging folder
keeps the per-layer sidecars, so a failed run resumes where it stopped.
"""
from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

import numpy as np

from .core import GEODATA_ROOT, Catalog, data_sha256, read_band, utc_now
from .grid import Grid

RELEASE_RE = re.compile(r"^\d{4}\.\d+$")
GDAL_TYPES = {"uint8": "Byte", "int16": "Int16", "uint16": "UInt16", "int32": "Int32", "float32": "Float32",
              "float64": "Float64"}


class ReleaseExists(RuntimeError):
    """The release id is taken (releases are immutable)."""


def release_dir(country: str, release: str, root: Path = GEODATA_ROOT) -> Path:
    return root / country / release


def staging_dir(country: str, release: str, root: Path = GEODATA_ROOT) -> Path:
    return root / country / f".{release}.partial"


def release_id(country: str, release: str) -> str:
    """``ET/2026.1``: what ``GEODATA_RELEASE`` and ``ctx_release`` carry."""
    return f"{country}/{release}"


def _key(rid: str) -> tuple[int, int]:
    y, n = rid.split(".")
    return int(y), int(n)


def list_releases(country: str, root: Path = GEODATA_ROOT) -> list[str]:
    """Published release ids of a country, oldest first."""
    d = root / country
    if not d.exists():
        return []
    ids = [p.name for p in d.iterdir() if p.is_dir() and RELEASE_RE.match(p.name) and (p / "manifest.json").exists()]
    return sorted(ids, key=_key)


def previous_release(country: str, release: str, root: Path = GEODATA_ROOT) -> str | None:
    """The newest published release older than ``release``."""
    older = [r for r in list_releases(country, root) if _key(r) < _key(release)]
    return older[-1] if older else None


def check_new(country: str, release: str, root: Path = GEODATA_ROOT) -> None:
    """Refuse a malformed or already published release id."""
    if not RELEASE_RE.match(release):
        raise ValueError(f"release id {release!r} must look like 2026.1")
    if (release_dir(country, release, root) / "manifest.json").exists() or release_dir(country, release, root).exists():
        raise ReleaseExists(f"{release_dir(country, release, root)} exists: releases are immutable, "
                            f"choose a new id (e.g. {release.split('.')[0]}.{int(release.split('.')[1]) + 1})")


def load_manifest(path: Path) -> dict[str, Any]:
    return json.loads((path / "manifest.json").read_text(encoding="utf-8"))


# ------------------------------------------------------------ VRT
def write_vrt(folder: Path, entries: dict[str, dict[str, Any]], grid: Grid, order: list[str]) -> Path:
    """``stack.vrt``: one band per built layer, paths relative to the VRT."""
    from rasterio.crs import CRS

    t = grid.transform
    bands = []
    for i, lid in enumerate([x for x in order if entries.get(x, {}).get("status") == "built"], 1):
        e = entries[lid]
        bands.append(
            f'  <VRTRasterBand dataType="{GDAL_TYPES[e["dtype"]]}" band="{i}">\n'
            f"    <Description>{escape(lid)}</Description>\n"
            f"    <NoDataValue>{e['nodata']}</NoDataValue>\n"
            f"    <SimpleSource>\n"
            f'      <SourceFilename relativeToVRT="1">{escape(e["file"])}</SourceFilename>\n'
            f"      <SourceBand>1</SourceBand>\n"
            f'      <SrcRect xOff="0" yOff="0" xSize="{grid.ncols}" ySize="{grid.nrows}"/>\n'
            f'      <DstRect xOff="0" yOff="0" xSize="{grid.ncols}" ySize="{grid.nrows}"/>\n'
            f"    </SimpleSource>\n  </VRTRasterBand>")
    xml = (f'<VRTDataset rasterXSize="{grid.ncols}" rasterYSize="{grid.nrows}">\n'
           f"  <SRS>{escape(CRS.from_user_input(grid.crs).to_wkt())}</SRS>\n"
           f"  <GeoTransform>{t.c!r}, {t.a!r}, {t.b!r}, {t.f!r}, {t.d!r}, {t.e!r}</GeoTransform>\n"
           + "\n".join(bands) + "\n</VRTDataset>\n")
    p = folder / "stack.vrt"
    p.write_text(xml, encoding="utf-8")
    return p


# ------------------------------------------------------------ diff
def legacy_entries(legacy_dir: Path, catalog: Catalog) -> dict[str, dict[str, Any]]:
    """Pseudo-manifest entries of the unversioned stack (``geodata/layers``), for diffing."""
    out = {}
    for lid in catalog.legacy_ids():
        p = legacy_dir / f"{lid}.tif"
        if p.exists():
            arr = read_band(p)[0]
            out[lid] = {"status": "built", "file": p.name, "data_sha256": data_sha256(arr)}
    return out


def diff_layers(new_dir: Path, new_entries: dict[str, dict[str, Any]], old_dir: Path,
                old_entries: dict[str, dict[str, Any]], catalog: Catalog, mask: np.ndarray | None) -> list[dict[str, Any]]:
    """Per layer: identical, changed (with mean and quantile shifts over the mask), added, removed, not built."""
    rows = []
    for lid in list(dict.fromkeys([*new_entries, *old_entries])):
        n, o = new_entries.get(lid), old_entries.get(lid)
        nb, ob = bool(n and n.get("status") == "built"), bool(o and o.get("status") == "built")
        row: dict[str, Any] = {"layer": lid}
        if nb and not ob:
            row["change"] = "added"
        elif ob and not nb:
            row["change"] = "removed" if not n else f"not built ({n.get('status')})"
        elif not nb and not ob:
            row["change"] = f"not built ({(n or o or {}).get('status')})"
        elif n.get("data_sha256") == o.get("data_sha256"):
            row["change"] = "identical"
        else:
            row["change"] = "changed"
            spec = catalog.layers.get(lid)
            a, b = read_band(new_dir / n["file"])[0], read_band(old_dir / o["file"])[0]
            inside = mask if mask is not None and mask.shape == a.shape else np.ones(a.shape, bool)
            if spec is not None:
                from .core import nodata_mask

                va = a[inside & ~nodata_mask(a, spec.nodata)]
                vb = b[inside & ~nodata_mask(b, spec.nodata)]
                if spec.categorical:
                    both = inside & ~nodata_mask(a, spec.nodata) & ~nodata_mask(b, spec.nodata)
                    row["share_of_cells_changed"] = float((a[both] != b[both]).mean()) if both.any() else None
                elif va.size and vb.size:
                    qs = (5, 50, 95)
                    qa, qb = np.percentile(va, qs), np.percentile(vb, qs)
                    row["mean_shift"] = float(va.mean() - vb.mean())
                    row["quantile_shift"] = {f"p{q}": float(x - y) for q, x, y in zip(qs, qa, qb)}
                    na, nb = nodata_mask(a, spec.nodata), nodata_mask(b, spec.nodata)
                    both = inside & ~na & ~nb
                    row["newly_valid"] = int((inside & ~na & nb).sum())
                    if both.any():
                        dd = np.abs(a[both].astype("float64") - b[both])
                        q50, q99 = np.percentile(dd, [50, 99])
                        row.update(max_abs_diff=float(dd.max()), abs_diff_median=float(q50), abs_diff_p99=float(q99))
                        tol = spec.raw.get("legacy_tolerance") if isinstance(spec.raw, dict) else None
                        if tol:
                            ok = (q50 <= float(tol.get("median_abs", np.inf))) and (q99 <= float(tol.get("p99_abs", np.inf)))
                            row["within_tolerance"] = bool(ok)
                            row["change"] = "changed, within tolerance" if ok else "changed, beyond tolerance"
                        del dd
        rows.append(row)
    return rows


def diff_markdown(rows: list[dict[str, Any]], new_id: str, old_id: str) -> str:
    lines = [f"# Diff: {new_id} versus {old_id}", "",
             "Per layer: identical or changed by data checksum (SHA-256 of the pixel values); for changed "
             "layers the mean and quantile shift over the country mask (new minus old), the median and p99 of "
             "the absolute cell difference, and the cells valid now but nodata before (newly filled). A layer "
             "with a `legacy_tolerance` in `sources.yaml` (elevation, slope) is accepted when its median and "
             "p99 absolute difference are within it; every other legacy layer must be equal.", "",
             "| Layer | Change | Mean shift | p5 / p50 / p95 shift | Max abs diff | Cells changed (classes) "
             "| Median / p99 abs diff | Newly valid cells |",
             "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        q = r.get("quantile_shift")
        qs = " / ".join(f"{v:+.4g}" for v in q.values()) if q else ""
        ms = f"{r['mean_shift']:+.4g}" if r.get("mean_shift") is not None else ""
        mx = f"{r['max_abs_diff']:.4g}" if r.get("max_abs_diff") is not None else ""
        sc = f"{100 * r['share_of_cells_changed']:.3f}%" if r.get("share_of_cells_changed") is not None else ""
        md = (f"{r['abs_diff_median']:.4g} / {r['abs_diff_p99']:.4g}" if r.get("abs_diff_median") is not None else "")
        nv = f"{r['newly_valid']:,}" if r.get("newly_valid") is not None else ""
        lines.append(f"| `{r['layer']}` | {r['change']} | {ms} | {qs} | {mx} | {sc} | {md} | {nv} |")
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------ README
def readme_markdown(manifest: dict[str, Any], order: list[str]) -> str:
    """The auto-generated layer table of a release."""
    e = manifest["layers"]
    lines = [f"# Geodata release {manifest['release_id']}", "",
             f"Built {manifest['created_utc']} by `pipelines/geodata/refresh.py` (git {manifest.get('git_commit')}). "
             f"Grid: {manifest['grid']['ncols']} x {manifest['grid']['nrows']} cells of {manifest['grid']['res_deg']} "
             f"degrees ({manifest['grid']['crs']}), hash `{manifest['grid_hash'][:12]}`. "
             f"`sources.yaml` hash `{manifest['sources_yaml_sha256'][:12]}`. QA: **{manifest['qa_status']}**.", "",
             "**Immutable.** Never edit this folder; a rebuild writes a new release id. Large files are "
             "git-ignored; `manifest.json`, `qa_report.json`, this README and the diffs are in git.", "",
             "| Layer | Status | Source | Version | Unit | Resampling | Cadence | Required | Size | QA |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for lid in order:
        x = e.get(lid)
        if not x:
            continue
        size = f"{x['bytes'] / 1e6:.1f} MB" if x.get("bytes") else ""
        lines.append(f"| `{lid}` | {x['status']} | {x.get('source_name', '')} | {x.get('version') or ''} | "
                     f"{x.get('unit', '')} | {x.get('resampling', '')} | {x.get('update_cadence', '')} | "
                     f"{'yes' if x.get('required') else 'no'} | {size} | {x.get('qa_status', '')} |")
    not_built = [(lid, x) for lid, x in e.items() if x["status"] != "built"]
    if not_built:
        lines += ["", "## Not built", ""] + [f"- `{lid}` ({x['status']}): {x.get('reason')}" for lid, x in not_built]
    lines += ["", "## Licences", ""]
    for lic in sorted({str(x.get("licence")) for x in e.values() if x.get("licence")}):
        lines.append(f"- {lic}")
    lines += ["", "Read it with `pipelines.geodata.extract.ContextExtractor(\"geodata/"
              f"{manifest['release_id']}\")` or point the backend at it with `GEODATA_RELEASE={manifest['release_id']}`."]
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------ publish
def carry_layer(prev_dir: Path, lid: str, staging: Path, prev_id: str) -> dict[str, Any]:
    """Copy a built layer of the previous release into the staging folder (``--layers`` refresh)."""
    m = load_manifest(prev_dir)
    entry = dict(m["layers"][lid])
    if entry.get("status") == "built":
        shutil.copy2(prev_dir / entry["file"], staging / entry["file"])
    entry["carried_from"] = prev_id
    (staging / f"{lid}.layer.json").write_text(json.dumps(entry, indent=2, default=str) + "\n", encoding="utf-8")
    return entry


def publish(staging: Path, final: Path) -> None:
    """Rename the staging folder into place (the last step of a release)."""
    if final.exists():
        raise ReleaseExists(f"{final} appeared during the build")
    for p in staging.glob("*.layer.json"):
        p.unlink()
    for p in staging.glob("*.tmp.tif"):
        p.unlink()
    os.replace(staging, final)


def manifest_body(country: Any, release: str, grid: Grid, catalog: Catalog, entries: dict[str, dict[str, Any]],
                  qa: dict[str, Any], previous: str | None, commit: str | None, grid_source: str,
                  args: dict[str, Any]) -> dict[str, Any]:
    layers = {}
    for lid in catalog.layers:
        if lid in entries:
            x = dict(entries[lid])
            r = qa["layers"].get(lid)
            if r:
                x["qa_status"] = r["status"]
                x["qa"] = {c["check"]: c["status"] for c in r["checks"]}
            lc = qa["legacy_comparison"].get(lid)
            if lc:
                x["legacy_equal"] = lc.get("equal")
                if lc.get("within_tolerance") is not None:
                    x["legacy_within_tolerance"] = lc["within_tolerance"]
                    x["legacy_tolerance"] = lc.get("tolerance_spec")
                if lc.get("abs_diff"):
                    x["legacy_abs_diff"] = lc["abs_diff"]
                    x["legacy_newly_valid_cells"] = lc.get("newly_valid")
                    x["legacy_newly_nodata_cells"] = lc.get("newly_nodata")
            layers[lid] = x
    return {"release_id": release_id(country.code, release), "country": country.code, "release": release,
            "created_utc": utc_now(), "git_commit": commit, "pipeline": "pipelines/geodata/refresh.py",
            "grid": grid.definition(), "grid_hash": grid.hash(), "grid_source": grid_source,
            "sources_yaml_sha256": catalog.sha256, "previous_release": previous, "qa_status": qa["status"],
            "args": args, "layers": layers}
