"""Backend ↔ frontend vocabulary sync (U2).

Two catalogs describe the same words: the backend's ``app/i18n`` (used in API
texts and to read translated quick-reply sentences) and the frontend's
``messages/*.json`` + ``src/i18n/glossary.ts`` (used for display). They must
not drift: a chip the UI sends in Amharic must be parseable by the backend.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.i18n import LANGUAGES, catalog
from app.services.recommender_service import INDICATORS, PRACTICE_FAMILIES

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
MESSAGES = FRONTEND / "messages"
GLOSSARY = FRONTEND / "src" / "i18n" / "glossary.ts"

pytestmark = pytest.mark.skipif(not MESSAGES.exists(), reason="frontend not checked out")

PROTOCOL_KEYS = {
    "farm_at": "farmAt",
    "challenge": "challenge",
    "objective": "objective",
    "challenge_note": "challengeNote",
    "objective_note": "objectiveNote",
}


def _ts_table(name: str) -> dict[str, dict[str, str]]:
    source = GLOSSARY.read_text(encoding="utf-8")
    m = re.search(rf"export const {name}[^=]*=\s*\{{(.*?)\n\}};", source, re.S)
    assert m, name
    out: dict[str, dict[str, str]] = {}
    for mm in re.finditer(r'^[ ]{2}"?([^"\n:]+?)"?: \{(.*?)\n?[ ]*\},?$', m.group(1), re.M | re.S):
        out[mm.group(1)] = dict(re.findall(r'\b(en|am|om): "((?:[^"\\]|\\.)*)"', mm.group(2)))
    return out


@pytest.mark.parametrize("lang", LANGUAGES)
def test_protocol_sentences_match_the_ui_catalog(lang):
    ui = json.loads((MESSAGES / f"{lang}.json").read_text(encoding="utf-8"))["chat"]["protocol"]
    for backend_key, ui_key in PROTOCOL_KEYS.items():
        assert catalog(lang)[f"protocol.{backend_key}"] == ui[ui_key], (lang, backend_key)


@pytest.mark.parametrize("lang", ["am", "om"])
def test_family_indicator_and_belt_terms_match_the_glossary(lang):
    families = _ts_table("FAMILIES")
    nouns = _ts_table("INDICATOR_NOUNS")
    labels = _ts_table("INDICATORS")
    belts = _ts_table("AEZ_BELTS")
    for fam in PRACTICE_FAMILIES:
        assert catalog(lang)[f"family.{fam}"] == families[fam][lang], (lang, fam)
    for ind in INDICATORS:
        assert catalog(lang)[f"indicator.{ind}"] == nouns[ind][lang], (lang, ind)
        assert catalog(lang)[f"indicator_label.{ind}"] == labels[ind][lang], (lang, ind)
    for belt, tri in belts.items():
        assert catalog(lang)[f"aez.{belt}"] == tri[lang], (lang, belt)


def test_translated_protocol_sentences_are_not_english():
    for lang in ("am", "om"):
        ui = json.loads((MESSAGES / f"{lang}.json").read_text(encoding="utf-8"))["chat"]["protocol"]
        en = json.loads((MESSAGES / "en.json").read_text(encoding="utf-8"))["chat"]["protocol"]
        assert all(ui[k] != en[k] for k in PROTOCOL_KEYS.values()), lang
