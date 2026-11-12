"""E3 (brief C2): the backend reads context from a geodata release when GEODATA_RELEASE is set.

The adapter is exercised on a manifest that points at the current stack's files, so the
test runs wherever the raster stack is present: with the same rasters, the release path
must return exactly what ``recommend.extract_context`` returns, plus ``release`` and
``extended``. Without GEODATA_RELEASE the engine is untouched and /metadata says so.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.config import get_settings
from app.services import recommender_service as svc

LAYERS = get_settings().resolved_layers_dir
NAMES = list(svc._engine.STACK) + ["aez_belt"]
POINTS = [(9.03, 38.74), (13.49, 39.47), (7.06, 38.48), (11.79, 41.0), (8.25, 34.58), (7.67, 36.83)]

needs_stack = pytest.mark.skipif(not all((LAYERS / f"{n}.tif").exists() for n in NAMES), reason="raster stack absent")


def test_default_mode_reads_layers_dir():
    if svc._GEODATA_RELEASE:
        pytest.skip("GEODATA_RELEASE is set in this environment")
    info = svc.geodata_info()
    assert info["release"] is None and info["source"] == "layers_dir"
    assert svc._engine.extract_context is svc._LEGACY_EXTRACT_CONTEXT


@needs_stack
def test_release_adapter_matches_the_engine(tmp_path, monkeypatch):
    rel = tmp_path / "ET" / "test.1"
    rel.mkdir(parents=True)
    layers = {n: {"status": "built", "file": str((LAYERS / f"{n}.tif").resolve()),
                  "kind": "categorical" if n in ("aez_belt", "land_cover") else "continuous"} for n in NAMES}
    (rel / "manifest.json").write_text(json.dumps({"release_id": "ET/test.1", "layers": layers}), encoding="utf-8")
    legacy = svc._LEGACY_EXTRACT_CONTEXT
    expected = {p: legacy(*p) for p in POINTS}
    monkeypatch.setattr(svc, "_GEODATA_RELEASE", "ET/test.1")
    monkeypatch.setattr(svc, "_GEODATA_RELEASE_DIR", rel)
    try:
        svc._install_release_adapter()
        for p in POINTS:
            got = svc.extract_context(*p)
            assert got.pop("release") == "ET/test.1" and got.pop("extended") == {}
            assert got == expected[p]
        info = svc.geodata_info()
        assert info["release"] == "ET/test.1" and info["source"] == "release"
        assert str(rel / "manifest.json") in [str(x) for x in svc._required_paths()]
    finally:
        svc._engine.extract_context = legacy
        svc._EXTRACTOR = None  # a direct reset: monkeypatch here would restore the test extractor at teardown (E5 fix)


def test_wrong_release_fails_fast(tmp_path, monkeypatch):
    monkeypatch.setattr(svc, "_GEODATA_RELEASE", "ET/missing.1")
    monkeypatch.setattr(svc, "_GEODATA_RELEASE_DIR", tmp_path / "nope")
    legacy = svc._engine.extract_context
    with pytest.raises(RuntimeError, match="GEODATA_RELEASE=ET/missing.1"):
        svc._install_release_adapter()
    assert svc._engine.extract_context is legacy
    svc._EXTRACTOR = None


def test_settings_resolve_release_dir(monkeypatch):
    from app.config import Settings

    s = Settings(geodata_release="ET/2026.1")
    assert s.resolved_geodata_release_dir == (s.backend_root / "../../geodata").resolve() / "ET/2026.1"
    assert Settings(geodata_release="").resolved_geodata_release_dir is None
    assert isinstance(s.resolved_geodata_dir, Path)
