"""Recapture the E2E /advise fixtures from the current backend (U9).

The Playwright suite mocks the API with captured answers
(``app/frontend/e2e/fixtures/advise-{model,hybrid,knowledge}[.am|.om].json``).
They must carry today's response shape (evidence bundles, ordering,
constraints), so this script calls POST /advise in-process at the demo pin
(8.38, 39.37, Dry Kolla) for the Erosion-control challenge:

- water use efficiency: model-led
- soil loss: hybrid
- income: knowledge-led

Run from ``app/backend``::

    python scripts/capture_advise_fixtures.py

Needs the raster stack and the model artifacts (like ``tests/test_api.py``).
The mode of each capture is checked; a mismatch aborts without writing.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

from fastapi.testclient import TestClient

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.main import app  # noqa: E402

FIXTURES = BACKEND.parent / "frontend" / "e2e" / "fixtures"
FAMILY = "Erosion control and water management"
CASES = {
    "model": ("water use efficiency", "model-led"),
    "hybrid": ("soil loss", "hybrid"),
    "knowledge": ("income", "knowledge-led"),
}
LANGS = {"en": "", "am": ".am", "om": ".om"}

logger = logging.getLogger("capture_advise_fixtures")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    captured: dict[Path, dict] = {}
    with TestClient(app) as client:
        for name, (indicator, mode) in CASES.items():
            for lang, suffix in LANGS.items():
                body = {
                    "lat": 8.38, "lon": 39.37, "practice_family": FAMILY,
                    "indicator": indicator, "crop_type": None, "top_n": 3, "language": lang,
                }
                r = client.post("/advise", json=body)
                if r.status_code != 200:
                    logger.error("%s/%s: HTTP %s %s", name, lang, r.status_code, r.text[:300])
                    return 1
                data = r.json()
                if data.get("mode") != mode:
                    logger.error("%s/%s: expected %s, got %s", name, lang, mode, data.get("mode"))
                    return 1
                captured[FIXTURES / f"advise-{name}{suffix}.json"] = data
                logger.info("%s/%s: %s, %d practices", name, lang, data["mode"], len(data.get("practices") or []))
    for path, data in captured.items():
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    logger.info("wrote %d fixtures to %s", len(captured), FIXTURES)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
