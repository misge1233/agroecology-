"""Backfill proper titles / years / item-page links for Tier-2 guidance docs.

Problem (C2): GARDIAN records carry no title field, so ``fetch_gardian.py``
fell back to the first words of the PDF text (``title_source:
"content_head"``) — e.g. "Farming System 2 (2024) 100110Contents lists…" —
and the only link kept is the bitstream *download* URL
(``https://cgspace.cgiar.org/rest/bitstreams/<uuid>/retrieve``), not the
repository item page. No other metadata (year, DOI, country) survived.

This script resolves each guidance document's source repository record and
writes a NON-destructive sidecar, ``rag/corpus/guidance/doc_metadata.json``.
``manifest.jsonl``, ``chunks.jsonl`` and the Chroma index are never touched.

Resolution (DSpace 7 REST, public, read-only):
    GET {host}/server/api/core/bitstreams/{uuid}/bundle?embed=item
  -> the owning item's ``dc.title``, ``dcterms.issued``, ``handle``,
     ``dcterms.language``, ``cg.coverage.region`` / ``cg.coverage.country``.
Supported hosts: cgspace.cgiar.org (and any other DSpace 7 host in
``DSPACE_HOSTS``). Documents whose URL is not a DSpace bitstream (MEL
downloads, publisher PDFs, archive.org …) are left out of the sidecar — the
UI keeps their original chip.

Politeness: at most ``--rate`` (default 4) requests/s, 20 s timeout, up to
4 attempts with exponential backoff on network errors / 429 / 5xx. Every
response (including a definitive 404) is cached under
``rag/corpus/guidance/meta_cache/<uuid>.json`` so re-runs are resumable and
offline once the cache is warm.

Sidecar schema::

    {
      "_about": {...provenance, counts...},
      "documents": {
        "<doc_id>": {
          "doc_id", "title", "year", "handle_url", "source_url",
          "item_uuid", "authors", "language", "region", "retrieved_at"
        }, ...
      }
    }

``doc_id`` is the manifest id; chunks carry it inside ``chunk_id``
(``G_<doc_id>_<pos>``) and carry ``source_url`` as their ``url`` — the backend
helper (app/backend/app/services/source_meta.py) matches on either.

Usage:
    python rag/ingest/backfill_guidance_metadata.py            # full run
    python rag/ingest/backfill_guidance_metadata.py --limit 20 --dry-run
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("backfill_guidance_metadata")

REPO_ROOT = Path(__file__).resolve().parents[2]
GUIDANCE_DIR = REPO_ROOT / "rag" / "corpus" / "guidance"
USER_AGENT = ("AgroAdvisor-ET guidance-metadata backfill "
              "(CGIAR research use; python-urllib)")

# DSpace 7 hosts whose legacy /rest/bitstreams/<uuid>/retrieve links we can
# resolve -> item page base URL used for the handle link.
DSPACE_HOSTS: dict[str, str] = {
    "cgspace.cgiar.org": "https://cgspace.cgiar.org",
    "digitalarchive.worldfishcenter.org": "https://digitalarchive.worldfishcenter.org",
}
_BITSTREAM_RE = re.compile(
    r"^https?://(?P<host>[^/]+)/(?:rest|server/api/core)/bitstreams/"
    r"(?P<uuid>[0-9a-fA-F-]{36})(?:/(?:retrieve|content))?/?$"
)
_YEAR_RE = re.compile(r"\b(1[89]\d{2}|20\d{2})\b")
_LANG_RE = re.compile(r"^[a-z]{2}$")
# Common non-ISO language values in CGSpace records -> ISO 639-1.
_LANG_NAMES = {"english": "en", "french": "fr", "spanish": "es",
               "portuguese": "pt", "amharic": "am", "arabic": "ar"}


# ------------------------------------------------------------------- parsing
def parse_bitstream_url(url: str | None) -> tuple[str, str] | None:
    """(host, bitstream uuid) for a supported DSpace bitstream URL, else None."""
    if not url:
        return None
    m = _BITSTREAM_RE.match(url.strip())
    if not m or m.group("host").lower() not in DSPACE_HOSTS:
        return None
    return m.group("host").lower(), m.group("uuid").lower()


def _values(metadata: dict[str, Any], key: str) -> list[str]:
    """All string values of one DSpace metadata field ([] if absent)."""
    return [str(v.get("value")).strip() for v in metadata.get(key, [])
            if isinstance(v, dict) and v.get("value")]


def _first(metadata: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        vals = _values(metadata, key)
        if vals:
            return vals[0]
    return None


def normalise_language(raw: str | None) -> str | None:
    """ISO 639-1 code from a DSpace language value ('en', 'en_US', 'English')."""
    if not raw:
        return None
    s = raw.strip().lower().replace("-", "_")
    head = s.split("_", 1)[0]
    if _LANG_RE.match(head):
        return head
    return _LANG_NAMES.get(s)


def clean_title(raw: str | None) -> str | None:
    """Collapse whitespace; None for empty titles."""
    if not raw:
        return None
    title = re.sub(r"\s+", " ", raw).strip()
    return title or None


def item_record(item: dict[str, Any], host: str, source_url: str,
                doc_id: str, retrieved_at: str) -> dict[str, Any]:
    """Sidecar entry from a DSpace 7 item JSON object (pure — testable)."""
    md = item.get("metadata") or {}
    issued = _first(md, "dcterms.issued", "dc.date.issued")
    year_m = _YEAR_RE.search(issued or "")
    handle = item.get("handle")
    base = DSPACE_HOSTS.get(host, f"https://{host}")
    if handle:
        handle_url = f"{base}/handle/{handle}"
    elif item.get("uuid"):
        handle_url = f"{base}/items/{item['uuid']}"
    else:
        handle_url = None
    regions = _values(md, "cg.coverage.region")
    countries = _values(md, "cg.coverage.country")
    region = "; ".join(dict.fromkeys(regions + countries)) or None
    return {
        "doc_id": doc_id,
        "title": clean_title(_first(md, "dc.title")),
        "year": int(year_m.group(1)) if year_m else None,
        "handle_url": handle_url,
        "source_url": source_url,
        "item_uuid": item.get("uuid"),
        "authors": _values(md, "dc.contributor.author")[:10] or None,
        "language": normalise_language(_first(md, "dcterms.language",
                                              "dc.language.iso", "dc.language")),
        "region": region,
        "retrieved_at": retrieved_at,
    }


# ------------------------------------------------------------------- network
class PoliteClient:
    """Rate-limited, retrying, disk-cached JSON GET client."""

    def __init__(self, cache_dir: Path, rate: float, timeout: float = 20.0,
                 attempts: int = 4) -> None:
        self.cache_dir = cache_dir
        self.min_interval = 1.0 / rate if rate > 0 else 0.0
        self.timeout = timeout
        self.attempts = attempts
        self._last = 0.0
        self.n_requests = 0
        self.n_cache_hits = 0

    def _throttle(self) -> None:
        wait = self._last + self.min_interval - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()

    def get_item(self, host: str, uuid: str) -> dict[str, Any]:
        """Cached ``{"status": "ok"|"not_found"|"error", "item"?, "retrieved_at"}``.

        Only "ok" and "not_found" are cached (errors are retried next run).
        """
        cache_path = self.cache_dir / f"{uuid}.json"
        if cache_path.exists():
            self.n_cache_hits += 1
            return json.loads(cache_path.read_text(encoding="utf-8"))

        url = (f"https://{host}/server/api/core/bitstreams/{uuid}"
               "/bundle?embed=item")
        result: dict[str, Any] = {"status": "error", "host": host}
        for attempt in range(1, self.attempts + 1):
            self._throttle()
            self.n_requests += 1
            req = urllib.request.Request(
                url, headers={"User-Agent": USER_AGENT,
                              "Accept": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    payload = json.load(resp)
                item = (payload.get("_embedded") or {}).get("item")
                if not item:
                    result = {"status": "not_found", "host": host,
                              "reason": "bundle has no item"}
                else:
                    result = {"status": "ok", "host": host, "item": item}
                break
            except urllib.error.HTTPError as exc:
                if exc.code in (401, 403, 404, 410):
                    result = {"status": "not_found", "host": host,
                              "reason": f"HTTP {exc.code}"}
                    break
                log.warning("%s: HTTP %s (attempt %d)", uuid, exc.code, attempt)
            except (urllib.error.URLError, TimeoutError, OSError,
                    json.JSONDecodeError) as exc:
                log.warning("%s: %s (attempt %d)", uuid, exc, attempt)
            time.sleep(min(30.0, 2.0 ** attempt))

        result["retrieved_at"] = datetime.now(timezone.utc).isoformat(
            timespec="seconds")
        if result["status"] != "error":
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(result, ensure_ascii=False),
                                  encoding="utf-8")
        return result


# ---------------------------------------------------------------------- main
def load_manifest(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in
            path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--corpus", type=Path, default=GUIDANCE_DIR,
                    help="guidance corpus dir (manifest.jsonl)")
    ap.add_argument("--out", type=Path, default=None,
                    help="sidecar path (default <corpus>/doc_metadata.json)")
    ap.add_argument("--cache", type=Path, default=None,
                    help="response cache dir (default <corpus>/meta_cache)")
    ap.add_argument("--limit", type=int, default=0,
                    help="process only the first N manifest documents")
    ap.add_argument("--rate", type=float, default=4.0,
                    help="max requests per second (<= 4 please)")
    ap.add_argument("--dry-run", action="store_true",
                    help="resolve and report, but do not write the sidecar")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(message)s")

    corpus: Path = args.corpus
    out_path: Path = args.out or corpus / "doc_metadata.json"
    client = PoliteClient(args.cache or corpus / "meta_cache",
                          rate=min(args.rate, 4.0))
    manifest = load_manifest(corpus / "manifest.jsonl")
    if args.limit:
        manifest = manifest[: args.limit]

    documents: dict[str, dict[str, Any]] = {}
    n_unsupported = n_not_found = n_error = 0
    examples: list[tuple[str, str]] = []
    for i, rec in enumerate(manifest, 1):
        parsed = parse_bitstream_url(rec.get("url"))
        if not parsed:
            n_unsupported += 1
            continue
        host, uuid = parsed
        res = client.get_item(host, uuid)
        if res["status"] == "not_found":
            n_not_found += 1
            log.debug("%s: not found (%s)", rec["doc_id"], res.get("reason"))
            continue
        if res["status"] != "ok":
            n_error += 1
            continue
        entry = item_record(res["item"], host, rec["url"], rec["doc_id"],
                            res["retrieved_at"])
        documents[rec["doc_id"]] = entry
        if len(examples) < 8 and entry["title"]:
            examples.append((rec.get("title") or "", entry["title"]))
        if i % 100 == 0:
            log.info("  %d/%d processed (%d requests, %d cache hits)", i,
                     len(manifest), client.n_requests, client.n_cache_hits)

    n_title = sum(1 for d in documents.values() if d["title"])
    n_handle = sum(1 for d in documents.values()
                   if d["handle_url"] and "/handle/" in d["handle_url"])
    n_year = sum(1 for d in documents.values() if d["year"])
    counts = {
        "documents_in_manifest": len(manifest),
        "resolvable_dspace_urls": len(manifest) - n_unsupported,
        "resolved": len(documents),
        "with_title": n_title,
        "with_handle": n_handle,
        "with_year": n_year,
        "not_found": n_not_found,
        "errors_retry_next_run": n_error,
        "unsupported_url": n_unsupported,
    }
    log.info("Coverage: %s", json.dumps(counts))
    for before, after in examples:
        log.info("  BEFORE %r\n         AFTER  %r", before[:80], after[:100])

    if args.dry_run:
        log.info("--dry-run: sidecar NOT written (%s)", out_path)
        return 0
    sidecar = {
        "_about": {
            "description": ("Backfilled item-level metadata for Tier-2 "
                            "guidance documents (non-destructive sidecar; "
                            "chunks.jsonl / manifest.jsonl / index untouched)."),
            "generator": "rag/ingest/backfill_guidance_metadata.py",
            "source": "DSpace 7 REST API (bitstream -> bundle -> item)",
            "generated_at": datetime.now(timezone.utc).isoformat(
                timespec="seconds"),
            "keys": "manifest doc_id (chunk_id = G_<doc_id>_<pos>); "
                    "source_url = the chunks' url field",
            "counts": counts,
        },
        "documents": documents,
    }
    out_path.write_text(json.dumps(sidecar, ensure_ascii=False, indent=1),
                        encoding="utf-8")
    log.info("Wrote %d entries -> %s", len(documents), out_path)
    return 0 if n_error == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
