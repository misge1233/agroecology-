"""Reviewed backend translations must not change silently (U2 item 4).

Twin of app/frontend/src/i18n/review-status.test.ts for the ``backend`` rows
of ``app/frontend/messages/review-status.json``.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from app.i18n import catalog

STATUS = Path(__file__).resolve().parents[2] / "frontend" / "messages" / "review-status.json"


def _fingerprint(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def _entries():
    if not STATUS.exists():
        return []
    data = json.loads(STATUS.read_text(encoding="utf-8"))
    out = []
    for full_key, langs in data.items():
        source, _, key = full_key.partition("::")
        if source != "backend":
            continue
        for lang, entry in langs.items():
            out.append((key, lang, entry["sha1"]))
    return out


@pytest.mark.parametrize("key,lang,sha1", _entries() or [pytest.param(None, None, None, id="no-reviewed-backend-strings")])
def test_reviewed_backend_strings_keep_their_fingerprint(key, lang, sha1):
    if key is None:
        pytest.skip("no reviewed backend strings yet")
    current = catalog(lang).get(key)
    assert current is not None, f"{key} missing from the {lang} catalog"
    assert _fingerprint(current) == sha1, (
        f"{key} ({lang}) was reviewed but changed — re-import review.csv or set it back to machine-draft"
    )
