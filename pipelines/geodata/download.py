#!/usr/bin/env python3
"""Resumable, checksum-verified downloads into ``pipelines/geodata/cache/<source>/`` (brief E3 A1).

Every file a release reads is recorded in ``cache/<source>/downloads.json``:
URL, bytes, SHA-256, UTC download date, and ``absent`` for tiles the server does
not have (ocean tiles answer 404). On reuse the file is re-hashed and compared
with the record, so a corrupted or truncated cache is detected, never used.
A partial download resumes from its ``.part`` file with an HTTP Range request.
Files dropped by hand (``manual: true`` sources) are hashed and recorded on first
use. ``GEODATA_CACHE`` moves the cache to another drive.

CLI::

    python pipelines/geodata/download.py --list                 # sources and cache status
    python pipelines/geodata/download.py --check                # HEAD every source URL (no body)
    python pipelines/geodata/download.py --source worldclim_tavg_30s   # fetch one file source
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    __package__ = "pipelines.geodata"

from .core import (ManualDownloadRequired, MissingInput, cache_root, load_catalog,  # noqa: E402
                   sha256_file, utc_now)

logger = logging.getLogger("geodata.download")

USER_AGENT = "AgroEcoAdvisor-geodata/1.0 (+https://github.com/; research pipeline)"
RECORDS = "downloads.json"
OUTAGE_BUDGET_S = 15 * 60.0  # a short internet outage (DNS, connection refused/reset) must not fail a file
POLITE_S = 1.0  # gap between bulk requests to one server (CHIRPS answers 429 when hammered)


def is_outage(exc: BaseException) -> bool:
    """True for DNS and connection-level failures (no HTTP answer at all), which deserve a long retry."""
    import requests

    if isinstance(exc, (requests.exceptions.ConnectionError, requests.exceptions.Timeout)):
        return True
    return isinstance(exc, (ConnectionError, TimeoutError, OSError)) and not isinstance(exc, (FileNotFoundError,
                                                                                               PermissionError))


class Downloader:
    """Download and verify cached source files."""

    def __init__(self, root: Path | None = None, offline: bool = False, retries: int = 6, timeout: int = 300,
                 outage_budget_s: float = OUTAGE_BUDGET_S, polite_s: float = POLITE_S):
        self.root = Path(root) if root else cache_root()
        self.offline = offline
        self.retries = retries
        self.timeout = timeout
        self.outage_budget_s = outage_budget_s  # DNS/connection errors: keep retrying this long per file
        self.polite_s = polite_s  # minimum gap between two requests to the same source (bulk tiles, CHIRPS)
        self._records: dict[str, dict[str, Any]] = {}
        self._verified: set[str] = set()
        self._last: dict[str, float] = {}

    # ------------------------------------------------------------ records
    def folder(self, source: str) -> Path:
        p = self.root / source
        p.mkdir(parents=True, exist_ok=True)
        return p

    def records(self, source: str) -> dict[str, Any]:
        if source not in self._records:
            f = self.root / source / RECORDS
            self._records[source] = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
        return self._records[source]

    def _save(self, source: str) -> None:
        f = self.folder(source) / RECORDS
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.records(source), indent=1, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(tmp, f)

    def record(self, source: str, name: str, **fields: Any) -> dict[str, Any]:
        rec = self.records(source).setdefault(name, {})
        rec.update(fields)
        self._save(source)
        return rec

    def input_entry(self, source: str, name: str) -> dict[str, Any]:
        """The manifest ``inputs`` entry of a cached file."""
        rec = self.records(source).get(name, {})
        return {"source": source, "file": name, "url": rec.get("url"), "sha256": rec.get("sha256"),
                "bytes": rec.get("bytes"), "downloaded_utc": rec.get("downloaded_utc"),
                "manual": rec.get("manual", False)}

    # ------------------------------------------------------------ fetch
    def path(self, source: str, name: str) -> Path:
        return self.root / source / name

    def is_absent(self, source: str, name: str) -> bool:
        return self.records(source).get(name, {}).get("status") == "absent"

    def cached(self, source: str, name: str) -> bool:
        """True when the file is in the cache (not verified)."""
        return self.path(source, name).exists()

    def verify(self, source: str, name: str) -> bool:
        """Re-hash a cached file and compare with its record (records it when unrecorded)."""
        p = self.path(source, name)
        key = f"{source}/{name}"
        if key in self._verified:
            return True
        rec = self.records(source).get(name)
        digest = sha256_file(p)
        if rec and rec.get("sha256") and rec["sha256"] != digest:
            logger.warning("checksum mismatch for %s (recorded %s, now %s)", p, rec["sha256"][:12], digest[:12])
            return False
        if not rec or not rec.get("sha256"):
            self.record(source, name, sha256=digest, bytes=p.stat().st_size, status="ok", manual=True,
                        downloaded_utc=utc_now(), url=(rec or {}).get("url"))
        self._verified.add(key)
        return True

    def fetch(self, source: str, url: str, name: str, manual: bool = False, approx_mb: float | None = None,
              throttle_s: float = 0.0, absent_ok: bool = False, landing: str | None = None) -> Path | None:
        """Return the verified cached path of ``url`` (downloading it when allowed).

        ``absent_ok``: a 404 is recorded as ``absent`` and ``None`` is returned (tiles).
        """
        p = self.path(source, name)
        if p.exists():
            if self.verify(source, name):
                return p
            p.unlink()
        if self.is_absent(source, name):
            return None
        if self.offline:
            raise MissingInput(f"{p} is not cached (--skip-download)")
        if manual:
            raise ManualDownloadRequired(url, p, approx_mb, landing)
        return self._download(source, url, name, throttle_s, absent_ok)

    def _download(self, source: str, url: str, name: str, throttle_s: float, absent_ok: bool) -> Path | None:
        import requests

        p = self.path(source, name)
        self.folder(source)
        part = p.with_name(p.name + ".part")
        wait = self._last.get(source, 0.0) + max(throttle_s, self.polite_s) - time.time()
        if wait > 0:
            time.sleep(wait)
        outage_waited, outage_tries = 0.0, 0
        attempt = 0
        while attempt < self.retries:
            have = part.stat().st_size if part.exists() else 0
            headers = {"User-Agent": USER_AGENT}
            if have:
                headers["Range"] = f"bytes={have}-"
            try:
                with requests.get(url, stream=True, timeout=self.timeout, headers=headers) as r:
                    self._last[source] = time.time()
                    if r.status_code == 404 and absent_ok:
                        self.record(source, name, url=url, status="absent", checked_utc=utc_now())
                        return None
                    if r.status_code in (429, 500, 502, 503, 504):
                        delay = float(r.headers.get("Retry-After") or 0) or min(60.0, 2.0 * 2 ** attempt)
                        logger.info("  %s answered %s; retrying in %.0f s", url, r.status_code, delay)
                        time.sleep(delay)
                        continue
                    if r.status_code == 200 and have:
                        have = 0  # server ignored the Range header: start again
                        part.unlink(missing_ok=True)
                    if r.status_code not in (200, 206):
                        r.raise_for_status()
                    total = r.headers.get("Content-Length")
                    total = int(total) + have if total else None
                    with open(part, "ab" if have else "wb") as f:
                        for chunk in r.iter_content(1 << 20):
                            f.write(chunk)
                if total is not None and part.stat().st_size != total:
                    raise IOError(f"incomplete download ({part.stat().st_size} of {total} bytes)")
                os.replace(part, p)
                digest = sha256_file(p)
                self.record(source, name, url=url, sha256=digest, bytes=p.stat().st_size, status="ok",
                            downloaded_utc=utc_now(), manual=False)
                self._verified.add(f"{source}/{name}")
                logger.info("  downloaded %s (%.1f MB)", name, p.stat().st_size / 1e6)
                return p
            except Exception as exc:  # noqa: BLE001  (network errors: retry, keep the .part)
                if is_outage(exc):
                    # no HTTP answer at all (DNS, refused, reset, timeout): an outage, not this file's
                    # fault; back off up to the outage budget before giving up on it
                    delay = min(120.0, 5.0 * 2 ** outage_tries)
                    if outage_waited + delay > self.outage_budget_s:
                        logger.error("  %s: still unreachable after %.0f min: %s", url, outage_waited / 60, exc)
                        raise
                    logger.warning("  %s unreachable (%s); retrying in %.0f s (%.0f of %.0f min used)", url,
                                   type(exc).__name__, delay, outage_waited / 60, self.outage_budget_s / 60)
                    time.sleep(delay)
                    outage_waited += delay
                    outage_tries += 1
                    continue  # does not consume an ordinary retry
                if attempt == self.retries - 1:
                    raise
                delay = min(60.0, 2.0 * 2 ** attempt)
                logger.info("  %s: %s; retrying in %.0f s", url, exc, delay)
                time.sleep(delay)
            attempt += 1
        raise IOError(f"could not download {url}")

    def prune(self, source: str, names: list[str]) -> int:
        """Delete cached files after their derived products are cached (records stay); returns bytes freed."""
        freed = 0
        for n in names:
            p = self.path(source, n)
            if p.exists():
                freed += p.stat().st_size
                p.unlink()
                self.record(source, n, pruned_utc=utc_now())
        return freed


# ------------------------------------------------------------------ CLI
def _file_sources(catalog) -> dict[str, dict[str, Any]]:
    return {k: v for k, v in catalog.sources.items() if v.get("kind") == "file" and v.get("url")}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Geodata download cache")
    ap.add_argument("--list", action="store_true", help="list sources and what the cache holds")
    ap.add_argument("--check", action="store_true", help="HEAD every source URL (status and size, no body)")
    ap.add_argument("--source", help="download one single-file source (also manual ones)")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    cat = load_catalog()
    dl = Downloader()
    if a.list:
        for sid, s in cat.sources.items():
            folder = dl.root / sid
            files = [p for p in folder.glob("*") if p.is_file() and p.name != RECORDS] if folder.exists() else []
            mb = sum(p.stat().st_size for p in files) / 1e6
            print(f"{sid:26s} {s.get('kind'):13s} manual={bool(s.get('manual'))!s:5s} cached={len(files):4d} files "
                  f"{mb:9.1f} MB  (~{s.get('approx_mb', '?')} MB expected)")
        return 0
    if a.check:
        import requests

        for sid, s in cat.sources.items():
            url = s.get("url") or s.get("url_template", "")
            if not url.startswith("http"):
                print(f"{sid:26s} local/none  {s.get('path') or s.get('reason') or ''}")
                continue
            if "{" in url:
                print(f"{sid:26s} template    {url}")
                continue
            try:
                r = requests.head(url, allow_redirects=True, timeout=60, headers={"User-Agent": USER_AGENT})
                size = r.headers.get("Content-Length")
                print(f"{sid:26s} HTTP {r.status_code}  {int(size) / 1e6 if size else float('nan'):9.1f} MB  {url}")
            except Exception as exc:  # noqa: BLE001
                print(f"{sid:26s} ERROR {exc}")
        return 0
    if a.source:
        s = _file_sources(cat).get(a.source)
        if not s:
            ap.error(f"{a.source} is not a single-file source: {sorted(_file_sources(cat))}")
        name = s.get("filename") or s["url"].rsplit("/", 1)[-1]
        p = dl.fetch(a.source, s["url"], name, manual=False)
        print(f"cached {p}")
        return 0
    ap.error("use --list, --check or --source ID")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
