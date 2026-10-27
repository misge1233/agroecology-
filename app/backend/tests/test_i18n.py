"""Backend language plumbing (Phase U1).

Three guarantees:

1. **English is byte-identical to the pre-U1 texts.** Every deterministic
   string the API produces (clarifications, social replies, errors, the
   evidence narrative, explanation fallbacks, the evidence-base sentence, the
   no-passages text) was snapshotted BEFORE the refactor into
   ``fixtures/en_texts_pre_u1.json``; the same inputs must reproduce it now.
2. **Amharic really is Amharic** (Ethiopic script present) and Afaan Oromoo
   really differs from English.
3. **The LLM prompts carry the "Reply in …" instruction** and nothing else
   about them changed.

Runs without rasters, chromadb, or the network.
"""
from __future__ import annotations

import json
import re
from itertools import product
from pathlib import Path
from typing import Any

import pytest

from app import i18n
from app.config import Settings
from app.schemas import ChatRequest, ExplainRequest, MetadataResponse
from app.services import chat_service as cs
from app.services import explain_service as es
from app.services import slot_extraction as se

FIXTURE = Path(__file__).parent / "fixtures" / "en_texts_pre_u1.json"
ETHIOPIC = re.compile(r"[ሀ-፿]")


# ------------------------------------------------------------ inputs (same as the snapshot script)
def _slots(fam, ind, loc, place) -> se.ChatSlots:
    s = se.ChatSlots(practice_family=fam, indicator=ind, lat=loc and loc[0],
                     lon=loc and loc[1], place_name=place)
    missing = []
    if not s.practice_family:
        missing.append("challenge")
    if not s.indicator:
        missing.append("objective")
    if s.lat is None or s.lon is None:
        missing.append("location")
    s.missing = missing
    return s


REC = {
    "query": {"goal_direction": "reduce", "indicator": "soil loss", "crop_type": None},
    "details": {"context": {"aez_belt": "Moist Dega", "Rainfall": 812.5, "slope": 8.0,
                            "soil_clay": 31.2}, "confidence": "low"},
    "recommendations": [{"practice": "Mulch", "effect": "x"},
                        {"practice": "Water Harvesting", "effect": "y"}],
}
RREC = {"query": {"indicator": "soil loss"},
        "recommendations": [{"practice": "Mulching", "effect": "~42% decrease in soil loss"},
                            {"practice": "Soil bunds", "effect": "~35% decrease in soil loss"}]}
CHUNKS = [{"era_code": "NN0123", "title": "Mulching effects on erosion", "year": 2019,
           "text": "t", "for_practice": "Mulching"},
          {"era_code": "NN0456", "title": None, "year": 2015, "text": "t",
           "for_practice": "Soil bunds"}]
EB = {"n_studies": 3, "n_obs": 17, "aez_belts": ["Dry Dega", "Moist Weyna Dega"],
      "corpus_status": {"full_text": 1, "abstract": 1, "none": 1}}


class NoRetriever:
    def retrieve_for_recommendation(self, rec: dict[str, Any], k: int = 8):
        return []


def compute_all(language: str) -> dict[str, str]:
    """Every snapshotted text, recomputed for ``language``."""
    out: dict[str, str] = {}
    for fam, ind, loc, place in product(
        [None, "Erosion control and water management", "Crop production and management"],
        [None, "soil loss"], [None, (8.38, 39.37)], [None, "Debre Birhan"],
    ):
        out[f"clarify|{fam}|{ind}|{bool(loc)}|{place}"] = se.clarification_message(
            _slots(fam, ind, loc, place), language)
    out["summary|full"] = se.evidence_summary(REC, language)
    rec2 = {**REC, "query": {**REC["query"], "crop_type": "maize"},
            "details": {**REC["details"], "confidence": "high"},
            "recommendations": [{"practice": "Mulch", "effect": "x"}]}
    out["summary|crop_single_high"] = se.evidence_summary(rec2, language)
    out["summary|empty"] = se.evidence_summary({"recommendations": [], "details": {}}, language)
    out["summary|empty_note"] = se.evidence_summary(
        {"recommendations": [], "details": {"note": "custom note"}}, language)
    out["summary|nozone"] = se.evidence_summary(
        {"query": {}, "details": {"context": {}}, "recommendations": [{"practice": "Mulch"}]},
        language)
    out["social|prior"] = cs._social_reply(True, language)
    out["social|none"] = cs._social_reply(False, language)
    out["error|rate"] = cs._error_message(Exception("429 rate limit"), language)
    out["error|generic"] = cs._error_message(Exception("boom"), language)
    out["error|passthru"] = cs._error_message(Exception("Point is outside Ethiopia"), language)
    out["fallback|two"] = es.build_fallback_text(RREC, CHUNKS, None, language)
    out["fallback|none"] = es.build_fallback_text(
        {"query": {"indicator": "soil loss"}, "recommendations": []}, CHUNKS, None, language)
    out["fallback|noind"] = es.build_fallback_text(
        {"query": {}, "recommendations": []}, [], None, language)
    out["eb|plural"] = es.evidence_base_sentence("Mulching", EB, language)
    out["eb|singular"] = es.evidence_base_sentence(
        "P", {"n_studies": 1, "n_obs": 1, "aez_belts": [],
              "corpus_status": {"full_text": 1, "abstract": 0, "none": 0}}, language)
    out["fallback|eb"] = es.build_fallback_text(RREC, CHUNKS, {"Mulching": EB}, language)
    out["explain|nochunks"] = es.explain(RREC, retriever=NoRetriever(), language=language)[
        "explanation"]
    return out


@pytest.fixture(autouse=True)
def _hermetic(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(es, "get_settings", lambda: Settings(_env_file=None, openai_api_key=""))
    monkeypatch.setattr(es, "get_guidance_retriever", lambda: None)
    monkeypatch.setattr(es, "get_graph_query", lambda: None)


# --------------------------------------------------------------- 1. en byte-identical
def test_english_texts_are_byte_identical_to_the_pre_u1_snapshot():
    snapshot = json.loads(FIXTURE.read_text(encoding="utf-8"))
    now = compute_all("en")
    assert set(now) == set(snapshot)
    diffs = {k: (snapshot[k], now[k]) for k in snapshot if snapshot[k] != now[k]}
    assert diffs == {}, f"{len(diffs)} English text(s) changed: {list(diffs)[:5]}"
    assert len(snapshot) >= 40


def test_default_language_everywhere_is_english():
    """Calling without a language must equal calling with 'en'."""
    s = _slots(None, "soil loss", (8.0, 39.0), None)
    assert se.clarification_message(s) == se.clarification_message(s, "en")
    assert se.evidence_summary(REC) == se.evidence_summary(REC, "en")
    assert cs._social_reply(True) == cs._social_reply(True, "en")
    assert es.evidence_base_sentence("P", EB) == es.evidence_base_sentence("P", EB, "en")


# --------------------------------------------------------------- 2. am / om
@pytest.mark.parametrize("key", [
    "clarify|None|None|False|None", "clarify|None|soil loss|True|Debre Birhan",
    "summary|full", "summary|empty", "social|prior", "social|none", "error|rate",
    "error|generic", "fallback|two", "fallback|none", "eb|plural", "eb|singular",
    "explain|nochunks",
])
def test_amharic_texts_contain_ethiopic_script(key):
    text = compute_all("am")[key]
    assert ETHIOPIC.search(text), text


def test_amharic_keeps_western_digits_and_data_contract_terms():
    """Numbers must stay \\d for the guardrail; practice names stay English."""
    text = compute_all("am")["eb|plural"]
    assert "3" in text and "17" in text and "2" in text
    assert "Mulching" in text
    assert not re.search(r"[፩-፼]", text)        # no Ge'ez numerals


def test_afaan_oromoo_texts_are_latin_and_differ_from_english():
    en, om = compute_all("en"), compute_all("om")
    for key in ("clarify|None|None|False|None", "summary|full", "social|prior",
                "fallback|two", "eb|plural", "explain|nochunks"):
        assert om[key] != en[key], key
        assert not ETHIOPIC.search(om[key]), key
        assert "Mulch" in om[key] or "clarify" in key or "social" in key or "nochunks" in key


def test_passthrough_engine_errors_are_not_translated():
    """Engine validation errors are the data contract's own wording."""
    for lang in i18n.LANGUAGES:
        assert cs._error_message(Exception("Point is outside Ethiopia"), lang) == \
            "Point is outside Ethiopia"


def test_am_and_om_catalogs_cover_every_english_key():
    for lang in ("am", "om"):
        missing = set(i18n.en.STRINGS) - set(i18n.catalog(lang))
        assert missing == set(), f"{lang} is missing {sorted(missing)}"


def test_unknown_language_falls_back_to_english():
    assert i18n.normalize_language("fr") == "en"
    assert i18n.normalize_language(None) == "en"
    assert i18n.normalize_language("AM") == "am"
    assert i18n.t("fr", "social.no_prior") == i18n.t("en", "social.no_prior")


def test_glossary_terms_pass_unknown_values_through():
    assert i18n.term("am", "aez", "Brand New Belt") == "Brand New Belt"
    assert i18n.term("am", "aez", "Dry Dega") == "ደረቅ ደጋ"
    assert i18n.term("en", "indicator", "soil loss") == "soil loss"


# --------------------------------------------------------------- 3. prompts
@pytest.mark.parametrize("lang,expected", [
    ("en", "Reply in English."),
    ("am", "Reply in Amharic (አማርኛ)."),
    ("om", "Reply in Afaan Oromoo."),
])
def test_explain_prompt_carries_the_language_instruction(lang, expected):
    system = es._build_messages(RREC, None, CHUNKS, None, None, lang)[0]["content"]
    assert system.endswith(expected)
    # every other rule is untouched
    assert system.startswith(es.EXPLAIN_SYSTEM_PROMPT)
    assert system == es.EXPLAIN_SYSTEM_PROMPT + "\n" + expected


@pytest.mark.parametrize("lang,expected", [
    ("en", "Reply in English."), ("am", "Reply in Amharic (አማርኛ)."),
    ("om", "Reply in Afaan Oromoo."),
])
def test_chat_prompts_carry_the_language_instruction(lang, expected):
    narrative = cs.narrative_system_instruction(REC, lang)
    followup = cs.followup_system_instruction(REC, lang)
    assert narrative.endswith(expected) and followup.endswith(expected)
    assert narrative.startswith(cs.SYSTEM_PROMPT) and followup.startswith(cs.SYSTEM_PROMPT)
    assert "CRITICAL: A recommendation was ALREADY computed" in narrative
    assert "This is a FOLLOW-UP" in followup


def test_english_prompts_differ_from_pre_u1_only_by_the_language_line():
    """The only prompt change for `en` is the appended instruction."""
    system = es._build_messages(RREC, None, CHUNKS, None, None, "en")[0]["content"]
    assert system.removesuffix("\nReply in English.") == es.EXPLAIN_SYSTEM_PROMPT


# --------------------------------------------------------------- schema + metadata
def test_request_schemas_accept_only_the_three_languages():
    assert ChatRequest(message="hi").language == "en"
    assert ExplainRequest(recommendation={}).language == "en"
    assert ChatRequest(message="hi", language="am").language == "am"
    with pytest.raises(Exception):
        ChatRequest(message="hi", language="fr")
    with pytest.raises(Exception):
        ExplainRequest(recommendation={}, language="de")


def test_metadata_schema_lists_the_languages():
    assert MetadataResponse.model_fields["languages"].default_factory() == ["en", "am", "om"]
    assert list(i18n.LANGUAGES) == ["en", "am", "om"]
    assert i18n.LANGUAGE_NAMES["am"].startswith("Amharic")


@pytest.mark.asyncio
async def test_offline_chat_answers_in_the_requested_language(monkeypatch):
    """No API key: clarification + narrative come from the catalogs."""
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "openai_api_key", "")
    out = await cs.run_chat("hello there", [], None, 1, "am")
    assert ETHIOPIC.search(out["reply"]), out["reply"]
    out_en = await cs.run_chat("hello there", [], None, 1)
    assert out_en["reply"] == se.clarification_message(_slots(None, None, None, None), "en")
