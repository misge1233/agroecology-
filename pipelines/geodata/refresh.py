#!/usr/bin/env python3
"""Build an immutable geodata release from public sources (brief E3 A3).

    python pipelines/geodata/refresh.py --country ET --release 2026.1 [--layers a,b] [--dry-run]
                                        [--groups a,b] [--skip-download] [--prune-downloads]
                                        [--rebuild] [--in-process] [-v]

Steps: read ``countries/<CC>.yaml`` and ``sources.yaml``; download (or verify the
cache); build each layer group onto the country grid; QA every layer and compare the
11 legacy layers with the current stack; write ``geodata/<CC>/<release>/`` with
``<layer>.tif`` (COG, LZW, overviews), ``stack.vrt``, ``manifest.json``,
``qa_report.json``, ``README.md``, ``diff_vs_<previous>.md`` (when a previous release
exists) and ``diff_vs_legacy.md`` (against ``geodata/layers``). Exit code 1 when a
required layer is missing or fails QA; the staging folder
``geodata/<CC>/.<release>.partial/`` is kept and a rerun resumes from it.

``--layers`` builds only the named layers and carries the others from the previous
release (an annual refresh of land cover and recent climate). ``--dry-run`` prints
the plan (sources, URLs, cache state, sizes) and downloads nothing.

Each layer group runs in its own worker process (``--_group``), so the memory of one
group is freed before the next and its peak is logged; ``--in-process`` keeps everything
in one process (tests, debugging). ``--groups a,b`` reruns only those groups and takes
the rest from the staging folder. A pre-flight check warns when a drive is below 15 GB
or has less than the estimated remaining need.
"""
from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    __package__ = "pipelines.geodata"

from pipelines.common.country_config import load_country  # noqa: E402

from . import qa, release  # noqa: E402
from .core import (GEODATA_ROOT, LEGACY_LAYERS_DIR, REPO_ROOT, BuildContext, LayerUnavailable,  # noqa: E402
                   ManualDownloadRequired, MissingInput, cache_root, disk_status, git_commit, load_catalog,
                   peak_memory_mb, read_band)
from .download import Downloader  # noqa: E402
from .grid import grid_for_country  # noqa: E402
from .layers import GROUPS, aez, landcover, terrain  # noqa: E402

logger = logging.getLogger("geodata")


# ------------------------------------------------------------------ plan
def _tile_plan(dl: Downloader, source: str, names: list[str]) -> tuple[int, int, int]:
    cached = sum(dl.cached(source, n) for n in names)
    absent = sum(dl.is_absent(source, n) for n in names)
    return len(names), cached, absent


def plan(cfg: Any, catalog: Any, grid: Any, grid_src: str, wanted: list[str], dl: Downloader) -> dict[str, Any]:
    """What a run would do: per group, layers and sources with URL, cache state and size."""
    out: dict[str, Any] = {"country": cfg.code, "status": cfg.status, "grid": grid.definition(),
                           "grid_source": grid_src, "cache": str(dl.root), "groups": [], "to_download_mb": 0.0,
                           "manual": [], "notes": []}
    seen: set[str] = set()
    for gname, mod in GROUPS.items():
        lids = [l for l in wanted if catalog.layers[l].group == gname]
        if not lids:
            continue
        gp: dict[str, Any] = {"group": gname, "layers": [], "sources": []}
        for lid in lids:
            spec = catalog.layers[lid]
            note = ""
            if gname == "aez" and not aez.has_anchor(cfg):
                note = "no national anchor: belt attribute unavailable; Koppen class and GAEZ zones will stand in"
            elif gname == "vegetation":
                note = "pending: " + catalog.source("modis_ndvi")["reason"]
            elif gname == "overlays":
                rasters = ((cfg.overlays or {}).get("omo_gibe") or {}).get("rasters") or {}
                from .layers.overlays import KEYS, find_raster

                key = KEYS.get(lid)
                if not rasters:
                    note = "no overlay configured for this country: pending"
                elif key and find_raster(rasters.get(key)) is None:
                    note = f"pending: no GeoTIFF at {rasters.get(key)!r}"
            gp["layers"].append({"id": lid, "required": spec.required, "legacy": spec.legacy, "unit": spec.unit,
                                 "resampling": spec.resampling, "note": note})
        for lid in lids:
            if gname == "aez" and not aez.has_anchor(cfg):
                continue  # the belt source is Ethiopia's shapefile: nothing to read for this country
            for sid in catalog.layers[lid].sources:
                if sid in seen:
                    continue
                seen.add(sid)
                s = catalog.source(sid)
                item: dict[str, Any] = {"source": sid, "kind": s.get("kind"), "manual": bool(s.get("manual")),
                                        "licence": s.get("licence")}
                if s.get("kind") == "tiles":
                    if sid == "glo30_dem":
                        names = [terrain.tile_name(la, lo) + ".tif" for la, lo in terrain.tiles_for(grid)]
                    else:
                        names = [landcover.tile_name(la, lo) + ".tif" for la, lo in landcover.tiles_for(grid)]
                    n, cached, absent = _tile_plan(dl, sid, names)
                    todo = n - cached - absent
                    mb = todo * float(s.get("approx_mb_per_tile", 0))
                    note = "ocean tiles answer 404 and are recorded as absent"
                    if sid == "glo30_dem" and terrain.stage1_cached(cache_root() / "_work" / cfg.code):
                        mb, note = 0.0, ("the 90 m tile-pass intermediates are cached (cache/_work): the tiles "
                                         "are not fetched again")
                    item.update(url=s.get("url_template"), files=n, cached=cached, known_absent=absent,
                                approx_mb=round(mb), note=note)
                elif s.get("kind") == "file_template":
                    from .layers.climate_chirps import file_names

                    yrs = tuple(int(y) for y in catalog.settings.get("chirps_years", (1991, 2020)))
                    names = [n for _, _, n in file_names(yrs)]
                    n, cached, absent = _tile_plan(dl, sid, names)
                    mb = float(s.get("approx_mb", 0)) * (n - cached) / max(n, 1)
                    item.update(url=s.get("url_template"), files=n, cached=cached, approx_mb=round(mb))
                elif s.get("kind") == "stream":
                    item.update(url=s.get("url") or s.get("url_template"), approx_mb=s.get("approx_mb"),
                                note="streamed through /vsicurl/ and cached as grid-aligned clips")
                elif s.get("kind") == "file":
                    name = s.get("filename") or (s.get("url") or "").rsplit("/", 1)[-1]
                    if "{" in (s.get("url_template") or ""):
                        name = f"(WCS clip of the padded country box)"
                    cached = dl.cached(sid, name) if "{" not in name and "(" not in name else False
                    clips = (dl.root / sid / "clips")
                    if not cached and clips.exists() and any(clips.glob(f"*__{cfg.code}_*.tif")):
                        cached = "clips"
                    item.update(url=s.get("url") or s.get("url_template"), file=name, cached=cached,
                                approx_mb=0 if cached else s.get("approx_mb"))
                    if s.get("manual") and not cached:
                        out["manual"].append({"source": sid, "url": s.get("url"), "landing_page": s.get("landing_page"),
                                              "save_as": str(dl.root / sid / name), "approx_mb": s.get("approx_mb")})
                elif s.get("kind") == "local":
                    p = REPO_ROOT / s["path"]
                    item.update(path=s["path"], exists=p.exists(), approx_mb=0)
                else:
                    item.update(note=s.get("reason"), approx_mb=0)
                out["to_download_mb"] += float(item.get("approx_mb") or 0)
                gp["sources"].append(item)
        out["groups"].append(gp)
    out["to_download_mb"] = round(out["to_download_mb"])
    return out


def print_plan(p: dict[str, Any], release_id: str) -> None:
    g = p["grid"]
    print(f"PLAN {release_id}  ({p['country']}, status {p['status']})  -- dry run, nothing is downloaded or written")
    print(f"grid: {g['ncols']} x {g['nrows']} cells, {g['res_deg']} deg, lon {g['xmin']}..{g['xmax']}, "
          f"lat {g['ymin']}..{g['ymax']}  ({p['grid_source']})")
    print(f"cache: {p['cache']}")
    for gp in p["groups"]:
        print(f"\n[{gp['group']}]")
        for l in gp["layers"]:
            flag = "required" if l["required"] else "optional"
            leg = ", legacy" if l["legacy"] else ""
            print(f"  layer {l['id']:26s} {flag}{leg}; {l['unit']}; {l['resampling']}"
                  + (f"\n        -> {l['note']}" if l["note"] else ""))
        for s in gp["sources"]:
            extra = ""
            if "files" in s:
                extra = f"{s['files']} files, {s['cached']} cached" + (
                    f", {s['known_absent']} known absent" if s.get("known_absent") else "")
            elif "cached" in s:
                extra = f"cached: {s['cached']}"
            elif "exists" in s:
                extra = f"exists: {s['exists']}"
            mb = f"~{s['approx_mb']:,} MB to fetch" if isinstance(s.get("approx_mb"), (int, float)) and s.get("approx_mb") else ""
            print(f"  source {s['source']:24s} {s['kind']}{' (MANUAL)' if s['manual'] else ''}; {extra} {mb}")
            if s.get("url") or s.get("path"):
                print(f"        {s.get('url') or s.get('path')}")
            if s.get("note"):
                print(f"        note: {s['note']}")
    print(f"\nto download: ~{p['to_download_mb']:,} MB (before --prune-downloads)")
    for m in p["manual"]:
        print(f"MANUAL: {m['source']}: download {m['url']}"
              + (f" (landing page {m['landing_page']})" if m.get("landing_page") else "")
              + f" (~{m['approx_mb']} MB) and save it as {m['save_as']}")


# ------------------------------------------------------------------ run
CHILD_FLAG = "--_group"
GROUP_RESULT = "_group_{}.json"
LAYER_MB_ESTIMATE = 110.0  # a 6,800 x 5,156 float32 COG, LZW, with overviews
TERRAIN_TEMP_MB = 4096.0  # the 90 m DEM, filled DEM, pointer and accumulation rasters of WhiteboxTools


@dataclass
class Session:
    """Everything ``run`` and a group worker share: the catalogue, grid, folders and the build context."""

    cfg: Any
    catalog: Any
    grid: Any
    grid_src: str
    wanted: list[str]
    rid: str
    dl: Downloader
    root: Path
    staging: Path
    work: Path
    ctx: BuildContext
    prev: str | None


def _open(args: argparse.Namespace) -> Session:
    cc = args.country.upper()
    cfg = load_country(cc, check_files=False)
    catalog = load_catalog()
    grid, grid_src = grid_for_country(cfg)
    wanted = [l for l in catalog.layers if not args.layers or l in args.layers]
    unknown = sorted(set(args.layers or []) - set(catalog.layers))
    if unknown:
        raise SystemExit(f"unknown layers {unknown}; known: {sorted(catalog.layers)}")
    rid = release.release_id(cc, args.release)
    dl = Downloader(offline=args.skip_download)
    root = Path(args.geodata_root)
    staging = release.staging_dir(cc, args.release, root)
    work = cache_root() / "_work" / cc
    ctx = BuildContext(country=cfg, grid=grid, catalog=catalog, downloader=dl, staging=staging, work=work,
                       prune=args.prune_downloads, rebuild=args.rebuild)
    prev = release.previous_release(cc, args.release, root)
    return Session(cfg, catalog, grid, grid_src, wanted, rid, dl, root, staging, work, ctx, prev)


def _load_sidecars(ctx: BuildContext, lids: list[str]) -> None:
    """Read every ``<layer>.layer.json`` in the staging folder into ``ctx.entries`` (resumed runs)."""
    for lid in lids:
        sc = ctx.sidecar(lid)
        if sc.exists():
            try:
                ctx.entries[lid] = json.loads(sc.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                sc.unlink()


def _set_mask(ctx: BuildContext) -> None:
    if ctx.mask is None and (ctx.staging / "aez_belt.tif").exists():
        ctx.mask = read_band(ctx.staging / "aez_belt.tif")[0] > 0


def _build_group(ctx: BuildContext, gname: str, lids: list[str]) -> None:
    """Build one layer group in this process; every failure becomes a layer status, never a crash."""
    mod = GROUPS[gname]
    logger.info("== %s: %s", gname, ", ".join(lids))
    try:
        mod.build(ctx, set(lids))
    except LayerUnavailable as exc:
        logger.warning("  %s unavailable: %s", gname, exc)
        for lid in lids:
            if lid not in ctx.entries:
                ctx.mark(lid, "pending", str(exc))
    except (ManualDownloadRequired, MissingInput) as exc:
        logger.error("  %s: %s", gname, exc)
        for lid in lids:
            if lid not in ctx.entries:
                ctx.mark(lid, "failed", str(exc))
    except Exception as exc:  # noqa: BLE001  one group's failure must not lose the others
        logger.error("  %s failed: %s\n%s", gname, exc, traceback.format_exc(limit=4))
        for lid in lids:
            if lid not in ctx.entries:
                ctx.mark(lid, "failed", f"{type(exc).__name__}: {exc}")
    for lid in lids:
        if lid not in ctx.entries:
            ctx.mark(lid, "failed", "the module produced no output")


def _child_argv(args: argparse.Namespace, gname: str) -> list[str]:
    argv = [sys.executable, "-m", "pipelines.geodata.refresh", "--country", args.country, "--release", args.release,
            "--legacy-dir", str(args.legacy_dir), "--geodata-root", str(args.geodata_root), CHILD_FLAG, gname]
    if args.layers:
        argv += ["--layers", ",".join(args.layers)]
    for flag in ("skip_download", "prune_downloads", "rebuild", "verbose"):
        if getattr(args, flag, False):
            argv.append("--" + flag.replace("_", "-"))
    return argv


def run_group_worker(args: argparse.Namespace) -> int:
    """``--_group NAME``: build one group in a fresh process and leave a result file for the parent.

    One process per group frees every array between groups (the E3 run hit a MemoryError
    in soil after terrain) and gives a true peak-memory figure per group.
    """
    gname = args.group_worker
    s = _open(args)
    s.staging.mkdir(parents=True, exist_ok=True)
    s.work.mkdir(parents=True, exist_ok=True)
    lids = [l for l in s.wanted if s.catalog.layers[l].group == gname]
    _set_mask(s.ctx)
    t0 = time.time()
    _build_group(s.ctx, gname, lids)
    res = {"group": gname, "timing_s": round(time.time() - t0, 1), **peak_memory_mb(),
           "entries": {lid: s.ctx.entries[lid].get("status") for lid in lids if lid in s.ctx.entries}}
    (s.work / GROUP_RESULT.format(gname)).write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")
    logger.info("   %s worker done in %.0f s, peak RSS %s MB, peak commit %s MB", gname, res["timing_s"],
                res["peak_rss_mb"], res["peak_commit_mb"])
    return 0


def _run_group(args: argparse.Namespace, s: Session, gname: str, lids: list[str]) -> dict[str, Any]:
    """Build a group in a subprocess (default) or in this process (``--in-process``); returns timing and memory."""
    t0 = time.time()
    if args.in_process:
        _build_group(s.ctx, gname, lids)
        res: dict[str, Any] = {"group": gname, **peak_memory_mb()}
    else:
        res_file = s.work / GROUP_RESULT.format(gname)
        res_file.unlink(missing_ok=True)
        logger.info("== %s: %s (worker process)", gname, ", ".join(lids))
        proc = subprocess.run(_child_argv(args, gname), cwd=str(REPO_ROOT))
        res = json.loads(res_file.read_text(encoding="utf-8")) if res_file.exists() else {"group": gname}
        _load_sidecars(s.ctx, lids)
        for lid in lids:
            if lid not in s.ctx.entries or (not res_file.exists() and s.ctx.entries[lid].get("status") != "built"):
                s.ctx.mark(lid, "failed", f"the {gname} worker process exited with code {proc.returncode} "
                                          "without a result (out of memory or killed?)")
        res["worker_returncode"] = proc.returncode
    res["timing_s"] = round(time.time() - t0, 1)
    logger.info("   %s done in %.0f s, peak RSS %s MB, peak commit %s MB", gname, res["timing_s"],
                res.get("peak_rss_mb"), res.get("peak_commit_mb"))
    return res


def _planned(s: Session, args: argparse.Namespace) -> list[str]:
    """The layers this run will build: ``wanted`` restricted to ``--groups``."""
    return [l for l in s.wanted if not args.groups or s.catalog.layers[l].group in args.groups]


def preflight_disk(s: Session, args: argparse.Namespace) -> dict[str, Any]:
    """Free space on the release and cache drives against an estimate of what is still to come."""
    p = plan(s.cfg, s.catalog, s.grid, s.grid_src, _planned(s, args), s.dl)
    unbuilt = [l for l in s.wanted if s.ctx.entries.get(l, {}).get("status") != "built"]
    terrain_pending = any(s.catalog.layers[l].group == "terrain" and l in unbuilt for l in s.wanted
                          if l in ("flow_accumulation", "twi", "slope_length_factor", "dist_to_stream_m"))
    needed = float(p["to_download_mb"]) + LAYER_MB_ESTIMATE * len(unbuilt) + (TERRAIN_TEMP_MB if terrain_pending else 0)
    st = disk_status([s.root, s.dl.root], needed)
    st["estimate"] = {"download_mb": p["to_download_mb"], "layers_to_write": len(unbuilt),
                      "terrain_temporaries_mb": TERRAIN_TEMP_MB if terrain_pending else 0}
    for drive, d in st["drives"].items():
        level = logging.WARNING if drive in st["low"] or drive in st["short"] else logging.INFO
        logger.log(level, "disk %s: %.1f GB free of %.1f GB; this run still needs about %.1f GB%s", drive,
                   d["free_gb"], d["total_gb"], needed / 1000,
                   " -- LOW (below %.0f GB); use --prune-downloads or GEODATA_CACHE on another drive"
                   % st["warn_below_gb"] if drive in st["low"] else
                   (" -- NOT ENOUGH" if drive in st["short"] else ""))
    return st


def run(args: argparse.Namespace) -> int:
    t_start = time.time()
    if getattr(args, "group_worker", None):
        return run_group_worker(args)
    s = _open(args)
    cc, catalog, ctx, staging = s.cfg.code, s.catalog, s.ctx, s.staging
    if args.dry_run:
        print_plan(plan(s.cfg, catalog, s.grid, s.grid_src, _planned(s, args), s.dl), s.rid)
        st = disk_status([s.root, s.dl.root], 0)
        for drive, d in st["drives"].items():
            print(f"disk {drive}: {d['free_gb']:.1f} GB free" + ("  (LOW: below %.0f GB)" % st["warn_below_gb"]
                                                                if drive in st["low"] else ""))
        return 0
    if not s.cfg.active:
        raise SystemExit(f"{cc} is {s.cfg.status}: only --dry-run is allowed for a country that is not active")
    release.check_new(cc, args.release, s.root)
    staging.mkdir(parents=True, exist_ok=True)
    s.work.mkdir(parents=True, exist_ok=True)
    groups_to_run = list(GROUPS) if not args.groups else [g for g in GROUPS if g in args.groups]
    if args.layers:
        if not s.prev:
            raise SystemExit("--layers needs a previous release to carry the other layers from")
        prev_dir = release.release_dir(cc, s.prev, s.root)
        for lid in catalog.layers:
            if lid not in args.layers and not ctx.done(lid):
                ctx.entries[lid] = release.carry_layer(prev_dir, lid, staging, release.release_id(cc, s.prev))
    _load_sidecars(ctx, s.wanted)  # resumed run: what an earlier run built or recorded
    _set_mask(ctx)
    disk = preflight_disk(s, args)
    timings: dict[str, float] = {}
    memory: dict[str, Any] = {}
    for gname in GROUPS:
        lids = [l for l in s.wanted if catalog.layers[l].group == gname]
        if not lids or gname not in groups_to_run:
            continue
        res = _run_group(args, s, gname, lids)
        timings[gname] = res["timing_s"]
        memory[gname] = {k: res.get(k) for k in ("peak_rss_mb", "peak_commit_mb", "worker_returncode")}
        if gname == "aez":
            _set_mask(ctx)

    # ---- QA
    t0 = time.time()
    reports = {}
    for lid, e in ctx.entries.items():
        if e.get("status") == "built":
            reports[lid] = qa.check_layer(staging / e["file"], catalog.layers[lid], s.grid, ctx.mask)
    legacy_dir = Path(args.legacy_dir)
    legacy_cmp = {}
    if legacy_dir.exists():
        legacy_cmp = qa.compare_legacy(staging, legacy_dir, catalog, ctx.mask,
                                       [l for l in catalog.legacy_ids() if ctx.entries.get(l, {}).get("status") == "built"])
    summary = qa.summarise(reports, legacy_cmp, catalog, ctx.entries)
    timings["qa"] = round(time.time() - t0, 1)
    (staging / "qa_report.json").write_text(json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8")
    _print_summary(catalog, ctx.entries, reports, legacy_cmp)
    if summary["required_failed"]:
        logger.error("required layers failed: %s; staging kept in %s (rerun resumes)", summary["required_failed"], staging)
        return 1

    # ---- release files
    order = list(catalog.layers)
    rid = s.rid
    if s.prev:
        prev_dir = release.release_dir(cc, s.prev, s.root)
        rows = release.diff_layers(staging, ctx.entries, prev_dir, release.load_manifest(prev_dir)["layers"],
                                   catalog, ctx.mask)
        (staging / f"diff_vs_{s.prev}.md").write_text(release.diff_markdown(rows, rid, release.release_id(cc, s.prev)),
                                                      encoding="utf-8")
    if legacy_dir.exists():
        rows = release.diff_layers(staging, {k: v for k, v in ctx.entries.items() if catalog.layers[k].legacy},
                                   legacy_dir, release.legacy_entries(legacy_dir, catalog), catalog, ctx.mask)
        (staging / "diff_vs_legacy.md").write_text(release.diff_markdown(rows, rid, f"legacy stack {legacy_dir.name}/"),
                                                   encoding="utf-8")
    release.write_vrt(staging, ctx.entries, s.grid, order)
    timings["total"] = round(time.time() - t_start, 1)
    manifest = release.manifest_body(s.cfg, args.release, s.grid, catalog, ctx.entries, summary, s.prev, git_commit(),
                                     s.grid_src, {"layers": args.layers, "groups": args.groups,
                                                  "skip_download": args.skip_download,
                                                  "prune_downloads": args.prune_downloads,
                                                  "in_process": args.in_process})
    manifest["timings_s"] = timings
    manifest["peak_memory_mb"] = memory
    manifest["disk_preflight"] = disk
    manifest["release_bytes"] = sum(int(e.get("bytes") or 0) for e in ctx.entries.values())
    (staging / "README.md").write_text(release.readme_markdown(manifest, order), encoding="utf-8")
    (staging / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str) + "\n", encoding="utf-8")
    final = release.release_dir(cc, args.release, s.root)
    release.publish(staging, final)
    logger.info("published %s (%.1f GB, QA %s, %.0f min)", final, manifest["release_bytes"] / 1e9, summary["status"],
                timings["total"] / 60)
    print(f"\nRELEASE {rid}: {final}  QA {summary['status']}")
    return 0


def _print_summary(catalog: Any, entries: dict[str, Any], reports: dict[str, Any], legacy: dict[str, Any]) -> None:
    print(f"\n{'layer':26s} {'status':16s} {'QA':5s} {'legacy':10s} size")
    for lid in catalog.layers:
        e = entries.get(lid)
        if not e:
            continue
        r = reports.get(lid, {})
        lc = legacy.get(lid)
        if lc is None:
            leg = ""
        elif lc.get("equal"):
            leg = "equal"
        elif lc.get("within_tolerance"):
            leg = "within tol"
        else:
            leg = f"DIFF {lc.get('cells_differing')}"
        size = f"{e['bytes'] / 1e6:.1f} MB" if e.get("bytes") else (e.get("reason") or "")[:70]
        print(f"{lid:26s} {e['status']:16s} {r.get('status', ''):5s} {leg:10s} {size}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build a geodata release (brief E3)")
    ap.add_argument("--country", required=True)
    ap.add_argument("--release", default="2026.1")
    ap.add_argument("--layers", type=lambda s: [x.strip() for x in s.split(",") if x.strip()],
                    help="comma-separated layer ids to build; the others are carried from the previous release")
    ap.add_argument("--groups", type=lambda s: [x.strip() for x in s.split(",") if x.strip()],
                    help=f"only run these layer groups ({', '.join(GROUPS)}); the others are taken from the "
                         "staging folder of an earlier run (resume)")
    ap.add_argument("--dry-run", action="store_true", help="print the plan; download and write nothing")
    ap.add_argument("--skip-download", action="store_true", help="use the cache only")
    ap.add_argument("--prune-downloads", action="store_true",
                    help="delete large raw downloads once their derived clips/intermediates are cached")
    ap.add_argument("--rebuild", action="store_true", help="ignore layers already built in the staging folder")
    ap.add_argument("--in-process", action="store_true",
                    help="build every group in this process instead of one worker process per group")
    ap.add_argument("--legacy-dir", default=str(LEGACY_LAYERS_DIR), help="current stack to compare the legacy 11 with")
    ap.add_argument("--geodata-root", default=str(GEODATA_ROOT), help="where releases live (default: geodata/)")
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument(CHILD_FLAG, dest="group_worker", help=argparse.SUPPRESS)  # internal: one group, worker process
    a = ap.parse_args(argv)
    unknown = sorted(set(a.groups or []) - set(GROUPS))
    if unknown:
        ap.error(f"unknown groups {unknown}; known: {list(GROUPS)}")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    if not a.verbose:
        logging.getLogger("rasterio").setLevel(logging.WARNING)
    return run(a)


if __name__ == "__main__":
    raise SystemExit(main())
