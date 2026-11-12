"""The build-robustness fixes of the E3 review (11 Nov 2026): the WhiteboxTools wrapper fails
loudly, AWC is computed in float32 blocks, downloads ride out an outage, groups run in worker
processes with their peak memory recorded, the disk pre-flight warns, and elevation and slope
are accepted within a documented statistical tolerance."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from pipelines.geodata import core, download, qa, refresh, release
from pipelines.geodata.core import load_catalog
from pipelines.geodata.grid import Grid
from pipelines.geodata.layers import soil
from pipelines.geodata.layers import terrain as tr


# ------------------------------------------------------------------ 1. WhiteboxTools wrapper
def test_run_wbt_raises_with_exit_code_and_missing_output(tmp_path):
    """A 'binary' that cannot run the tool (python itself, which rejects the flags) must raise
    WhiteboxError naming the exit code and the missing output, with the captured message."""
    fake = SimpleNamespace(exe_path=str(Path(sys.executable).parent), exe_name=Path(sys.executable).name)
    with pytest.raises(tr.WhiteboxError) as ei:
        tr.run_wbt(fake, "FillDepressions", tmp_path, ("filled.tif",), dem="dem.tif", output="filled.tif")
    msg = str(ei.value)
    assert "exit code" in msg and "filled.tif missing" in msg and ei.value.tool == "FillDepressions"


def test_run_wbt_detects_an_error_line_even_with_exit_code_zero(tmp_path, monkeypatch):
    done = {}

    def fake_run(args, **kw):
        done["args"] = args
        return SimpleNamespace(returncode=0, stdout="Reading data...\nError: unsupported TIFF layout\n", stderr="")

    monkeypatch.setattr(tr.subprocess, "run", fake_run)
    monkeypatch.setattr(tr, "_wbt_exe_of", lambda wbt: Path(sys.executable))
    with pytest.raises(tr.WhiteboxError, match="unsupported TIFF layout"):
        tr.run_wbt(None, "D8Pointer", tmp_path, ("pointer.tif",), dem="filled.tif", output="pointer.tif")
    assert "--run=D8Pointer" in done["args"] and "--dem=filled.tif" in done["args"] and "-v=true" in done["args"]


def test_wbt_input_is_striped_uncompressed_classic_tiff(tmp_path):
    import rasterio

    g = Grid(38.0, 9.0, 1 / 1200, 700, 530)
    z = np.random.default_rng(0).random(g.shape, dtype="float32") * 100
    z[0, 0] = np.nan
    tr._write_plain(tmp_path / "dem.tif", z, g, tr.WBT_NODATA)
    with rasterio.open(tmp_path / "dem.tif") as s:
        assert not s.profile["tiled"] and s.profile.get("compress") is None
        assert s.block_shapes[0][0] == tr.WBT_ROWS_PER_STRIP and s.nodata == tr.WBT_NODATA
        assert s.read(1)[0, 0] == tr.WBT_NODATA and s.read(1)[1, 1] == z[1, 1]
    big = Grid(0.0, 0.0, 1 / 1200, 40000, 30000)
    with pytest.raises(core.GeodataError, match="4 GB"):
        tr._write_plain(tmp_path / "big.tif", np.zeros((1, 1), "float32"), big, tr.WBT_NODATA)


@pytest.mark.skipif(tr.whitebox_exe() is None, reason="WhiteboxTools binary not installed")
def test_d8_on_a_plane_through_the_subprocess_runner(tmp_path):
    g = Grid(38.0, 9.0, 1 / 1200, 6, 8)
    z = (9.0 * 1000 - np.arange(8)[:, None] * 5 + np.linspace(0, 0.01, 6)[None, :]).astype("float32")
    acc = tr.d8_upstream_area(z, g, workdir=tmp_path)
    _, area, _ = tr.cell_geometry(g)
    assert acc[0].max() == pytest.approx(area[0], rel=1e-5) and np.nanmax(acc) >= 7 * area.mean()
    assert not list(tmp_path.glob("*.tif"))  # inputs and outputs cleaned


# ------------------------------------------------------------------ 2. memory
def test_awc_blockwise_float32_matches_whole_array():
    rng = np.random.default_rng(1)
    sand = rng.uniform(5, 90, (37, 11)).astype("float32")
    clay = np.clip(rng.uniform(5, 60, (37, 11)), 0, 95 - sand).astype("float32")
    soc = rng.uniform(1, 60, (37, 11)).astype("float32")
    bd = rng.uniform(0.9, 1.7, (37, 11)).astype("float32")
    sand[3, 3] = soil.ND
    bd[4, 4] = 0
    a = soil.awc_layer(sand, clay, soc, bd, rows=5)
    b = soil.awc_layer(sand, clay, soc, bd, rows=10_000)
    assert a.dtype == np.float32 and np.array_equal(a, b)
    assert a[3, 3] == soil.ND and a[4, 4] == soil.ND and 20 < np.median(a[a > 0]) < 250


def test_peak_memory_is_reported():
    m = core.peak_memory_mb()
    assert m["peak_rss_mb"] is not None and m["peak_rss_mb"] > 10


def test_group_runs_in_a_worker_process_and_reports_memory(tmp_path, monkeypatch):
    """The real refresh entry point, groups=vegetation (pending, no network): a worker process is
    spawned, its sidecar and result file come back, the run fails on the required layers only."""
    monkeypatch.setenv("GEODATA_CACHE", str(tmp_path / "cache"))
    rc = refresh.main(["--country", "ET", "--release", "2026.1", "--geodata-root", str(tmp_path / "geo"),
                       "--legacy-dir", str(tmp_path / "nolegacy"), "--groups", "vegetation", "--skip-download"])
    assert rc == 1  # the required layers were not built (only vegetation ran)
    res = json.loads((tmp_path / "cache" / "_work" / "ET" / "_group_vegetation.json").read_text(encoding="utf-8"))
    assert res["group"] == "vegetation" and res["peak_rss_mb"] > 10 and res["entries"]["ndvi_trend"] == "pending"
    staging = tmp_path / "geo" / "ET" / ".2026.1.partial"
    sc = json.loads((staging / "ndvi_trend.layer.json").read_text(encoding="utf-8"))
    assert sc["status"] == "pending"
    rep = json.loads((staging / "qa_report.json").read_text(encoding="utf-8"))
    assert "aez_belt" in rep["required_failed"]


# ------------------------------------------------------------------ 3. network
class _Resp:
    def __init__(self, body=b"abc"):
        self.status_code, self.headers, self._body = 200, {"Content-Length": str(len(body))}, body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def iter_content(self, n):
        yield self._body

    def raise_for_status(self):
        pass


def test_download_rides_out_a_dns_outage(tmp_path, monkeypatch):
    import requests

    calls, sleeps = [], []
    errors = [requests.exceptions.ConnectionError("getaddrinfo failed"),
              requests.exceptions.ConnectionError("getaddrinfo failed"), None]

    def fake_get(url, **kw):
        calls.append(url)
        e = errors.pop(0)
        if e:
            raise e
        return _Resp()

    monkeypatch.setattr(requests, "get", fake_get)
    monkeypatch.setattr(download.time, "sleep", lambda s: sleeps.append(s))
    dl = download.Downloader(root=tmp_path, retries=1)  # a single ordinary retry: outages must not consume it
    p = dl.fetch("src", "https://x/y.tif", "y.tif")
    assert p.read_bytes() == b"abc" and len(calls) == 3 and sleeps == [5.0, 10.0]


def test_download_gives_up_after_the_outage_budget(tmp_path, monkeypatch):
    import requests

    def fake_get(url, **kw):
        raise requests.exceptions.ConnectionError("getaddrinfo failed")

    monkeypatch.setattr(requests, "get", fake_get)
    waited = []
    monkeypatch.setattr(download.time, "sleep", lambda s: waited.append(s))
    dl = download.Downloader(root=tmp_path, outage_budget_s=60)
    with pytest.raises(requests.exceptions.ConnectionError):
        dl.fetch("src", "https://x/y.tif", "y.tif")
    assert sum(waited) <= 60 and waited == [5.0, 10.0, 20.0]
    assert not (tmp_path / "src" / "y.tif").exists()


def test_polite_gap_between_requests_to_one_source(tmp_path, monkeypatch):
    import requests

    monkeypatch.setattr(requests, "get", lambda url, **kw: _Resp())
    sleeps = []
    monkeypatch.setattr(download.time, "sleep", lambda s: sleeps.append(s))
    dl = download.Downloader(root=tmp_path, polite_s=1.0)
    dl.fetch("src", "https://x/a.tif", "a.tif")
    dl.fetch("src", "https://x/b.tif", "b.tif")
    assert sleeps and 0 < sleeps[0] <= 1.0


# ------------------------------------------------------------------ 4. disk
def test_disk_status_flags_low_and_short_drives(monkeypatch, tmp_path):
    monkeypatch.setattr(core.shutil, "disk_usage", lambda p: SimpleNamespace(free=12e9, total=1000e9))
    st = core.disk_status([tmp_path], needed_mb=20_000)
    (drive,) = st["drives"]
    assert st["drives"][drive]["free_gb"] == 12.0 and st["low"] == [drive] and st["short"] == [drive]
    monkeypatch.setattr(core.shutil, "disk_usage", lambda p: SimpleNamespace(free=40e9, total=1000e9))
    st = core.disk_status([tmp_path, tmp_path / "sub"], needed_mb=20_000)
    assert len(st["drives"]) == 1 and st["low"] == [] and st["short"] == []


# ------------------------------------------------------------------ 5. legacy tolerance
def test_elevation_and_slope_accepted_within_tolerance_others_strict(tmp_path):
    cat = load_catalog()
    elev, slope, rain = cat.layers["elevation"], cat.layers["slope"], cat.layers["precip_annual"]
    assert elev.raw["legacy_tolerance"] == {"median_abs": 0.1, "p99_abs": 10}
    assert slope.raw["legacy_tolerance"] == {"median_abs": 0.05, "p99_abs": 5}
    assert "legacy_tolerance" not in rain.raw
    rng = np.random.default_rng(2)
    old = rng.uniform(500, 3000, (200, 200)).astype("float32")
    new = old + rng.normal(0, 0.02, old.shape).astype("float32")  # median ~0.013 m, p99 ~0.05 m
    new[:3, :3] += 4.0  # a few cells shifted by metres, still under p99 10 m
    old[0, 100:110] = -9999.0  # cells the new build fills
    r = qa.compare_arrays(new, old, elev)
    assert not r["equal"] and r["within_tolerance"] is True and r["accepted"] is True
    assert r["abs_diff"]["median"] < 0.1 and r["abs_diff"]["p99"] < 10 and r["newly_valid"] == 10
    assert r["tolerance_checks"] == {"median_abs": True, "p99_abs": True}
    worse = new + 0.5
    r2 = qa.compare_arrays(worse, old, elev)
    assert r2["within_tolerance"] is False and r2["accepted"] is False
    r3 = qa.compare_arrays(new, old, rain)  # no tolerance: strict
    assert r3["within_tolerance"] is None and r3["accepted"] is False
    s = qa.summarise({}, {"elevation": r, "precip_annual": r3, "slope": qa.compare_arrays(old, old, slope)}, cat, {})
    assert s["legacy_layers_differing"] == ["precip_annual"] and s["legacy_layers_within_tolerance"] == ["elevation"]


def test_manifest_and_diff_carry_the_tolerance_numbers(tmp_path):
    from .conftest import write_tif

    cat = load_catalog()
    g = Grid(38.7, 9.05, 0.00225, 8, 6)
    old = np.full(g.shape, 1000.0, "float32")
    new = old + 0.02
    (tmp_path / "old").mkdir()
    (tmp_path / "new").mkdir()
    write_tif(tmp_path / "old" / "elevation.tif", old, g, -9999.0)
    write_tif(tmp_path / "new" / "elevation.tif", new, g, -9999.0)
    lc = qa.compare_arrays(new, old, cat.layers["elevation"])
    cfg = SimpleNamespace(code="ET")
    entries = {"elevation": {"status": "built", "file": "elevation.tif", "data_sha256": "a"}}
    m = release.manifest_body(cfg, "2026.1", g, cat, entries,
                              {"status": "warn", "legacy_comparison": {"elevation": lc}, "layers": {}}, None, None,
                              "test", {})
    e = m["layers"]["elevation"]
    assert e["legacy_equal"] is False and e["legacy_within_tolerance"] is True
    assert e["legacy_tolerance"] == {"median_abs": 0.1, "p99_abs": 10} and e["legacy_abs_diff"]["p99"] < 0.1
    rows = release.diff_layers(tmp_path / "new", entries, tmp_path / "old",
                               {"elevation": {"status": "built", "file": "elevation.tif", "data_sha256": "b"}}, cat, None)
    assert rows[0]["change"] == "changed, within tolerance" and rows[0]["abs_diff_p99"] == pytest.approx(0.02, abs=1e-3)
    md = release.diff_markdown(rows, "ET/2026.1", "legacy")
    assert "within tolerance" in md and "Median / p99 abs diff" in md


# ------------------------------------------------------------------ E4 Part 0: the WhiteboxTools flake
def _fake_tif(path: Path) -> None:
    import rasterio

    g = Grid(38.0, 9.0, 1 / 1200, 3, 3)
    tr._write_plain(path, np.ones((3, 3), "float32"), g, tr.WBT_NODATA)


def test_run_wbt_retries_the_output_panic_exactly_once(tmp_path, monkeypatch, caplog):
    """The known panic is retried once, logged as a warning and recorded; the second run succeeds."""
    calls = []
    panic = "Finding pit cells: 100%\nthread 'main' panicked at fill_depressions.rs:368:23:\nError unwrapping 'output'\n"

    def fake_run(args, **kw):
        calls.append(args)
        if len(calls) == 1:
            return SimpleNamespace(returncode=101, stdout=panic, stderr="")
        _fake_tif(tmp_path / "filled.tif")
        return SimpleNamespace(returncode=0, stdout="Filling depressions: 100%\n", stderr="")

    monkeypatch.setattr(tr.subprocess, "run", fake_run)
    monkeypatch.setattr(tr, "_wbt_exe_of", lambda wbt: Path(sys.executable))
    monkeypatch.setattr(tr, "WBT_RETRIES", [])
    import logging

    with caplog.at_level(logging.WARNING, logger=tr.logger.name):
        tr.run_wbt(None, "FillDepressions", tmp_path, ("filled.tif",), dem="dem.tif", output="filled.tif")
    assert len(calls) == 2
    assert len(tr.WBT_RETRIES) == 1 and tr.WBT_RETRIES[0]["tool"] == "FillDepressions" and tr.WBT_RETRIES[0]["recovered"]
    assert any("retrying once" in r.getMessage() for r in caplog.records)
    assert tr.whitebox_tool_record()["retries"] == tr.WBT_RETRIES


def test_run_wbt_gives_up_after_one_retry_and_other_errors_fail_at_once(tmp_path, monkeypatch):
    calls = []
    panic = "thread 'main' panicked at x.rs:1:1:\nError unwrapping 'output'\n"

    def always_panic(args, **kw):
        calls.append(args)
        return SimpleNamespace(returncode=101, stdout=panic, stderr="")

    monkeypatch.setattr(tr.subprocess, "run", always_panic)
    monkeypatch.setattr(tr, "_wbt_exe_of", lambda wbt: Path(sys.executable))
    monkeypatch.setattr(tr, "WBT_RETRIES", [])
    with pytest.raises(tr.WhiteboxError):
        tr.run_wbt(None, "FillDepressions", tmp_path, ("filled.tif",), dem="dem.tif", output="filled.tif")
    assert len(calls) == 2 and tr.WBT_RETRIES[0]["recovered"] is False

    calls.clear()

    def other_error(args, **kw):
        calls.append(args)
        return SimpleNamespace(returncode=1, stdout="Error: unsupported TIFF layout\n", stderr="")

    monkeypatch.setattr(tr.subprocess, "run", other_error)
    monkeypatch.setattr(tr, "WBT_RETRIES", [])
    with pytest.raises(tr.WhiteboxError, match="unsupported TIFF layout"):
        tr.run_wbt(None, "D8Pointer", tmp_path, ("pointer.tif",), dem="filled.tif", output="pointer.tif")
    assert len(calls) == 1 and tr.WBT_RETRIES == []


def test_wbt_scratch_folder_is_under_the_cache_not_the_user_temp(tmp_path, monkeypatch):
    monkeypatch.setenv("GEODATA_CACHE", str(tmp_path / "cache"))
    wd, own = tr._workdir(None)
    assert own and wd.is_dir() and wd.parent == tmp_path / "cache" / "_work" / "wbt"
    tr._cleanup(wd, own, ())
    assert not wd.exists()
