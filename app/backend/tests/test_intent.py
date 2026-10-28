"""U2 — language-aware intent parsing: protocol sentences, chip hints, LLM pass.

Fixtures in all three languages. The LLM call is monkeypatched (no network);
English must never reach it.
"""
from __future__ import annotations

import pytest

from app.config import Settings
from app.i18n import LANGUAGES, t, term
from app.services import chat_service, intent_llm
from app.services import slot_extraction as se

EROSION = "Erosion control and water management"
SOIL = "Integrated soil fertility management"

AM_FREE_TEXT = "በደብረ ብርሃን አቅራቢያ ባለው ተዳፋት እርሻዬ ላይ የአፈር መሸርሸርን መቀነስ እፈልጋለሁ"
OM_FREE_TEXT = "Dirree gadee koo Dabra Birhaan bira jiru irratti dhiqama biyyee hir'isuu barbaada"


# ------------------------------------------------------------ protocol sentences
@pytest.mark.parametrize("lang", LANGUAGES)
def test_challenge_protocol_parses_in_every_language(lang):
    msg = t(lang, "protocol.challenge", family=term(lang, "family", EROSION))
    slots = se.extract_slots(msg)
    assert slots.practice_family == EROSION
    assert slots.source == "protocol"
    assert slots.confidence["practice_family"] == "high"


@pytest.mark.parametrize("lang", LANGUAGES)
def test_objective_protocol_parses_in_every_language(lang):
    # The UI sends the objective label; the translated label contains the noun.
    objective = {
        "en": "reduce soil loss / erosion",
        "am": "የአፈር መሸርሸርን መቀነስ",
        "om": "Dhiqama biyyee hir'isuu",
    }[lang]
    msg = t(lang, "protocol.objective", objective=objective)
    slots = se.extract_slots(msg)
    assert slots.indicator == "soil loss"
    assert slots.source == "protocol"


def test_yield_is_not_mistaken_for_biomass_yield_in_amharic():
    msg = t("am", "protocol.objective", objective="የሰብል ምርትን መጨመር")
    assert se.extract_slots(msg).indicator == "yield"
    msg = t("am", "protocol.objective", objective="ባዮማስ / መኖን መጨመር")
    assert se.extract_slots(msg).indicator == "biomass yield"


@pytest.mark.parametrize("lang", LANGUAGES)
def test_combined_map_message_parses_in_every_language(lang):
    """applyMapAndContinue joins farm-at + challenge note + objective note."""
    bits = [
        t(lang, "protocol.farm_at", lat="8.3800", lon="39.3700"),
        t(lang, "protocol.challenge_note", family=term(lang, "family", EROSION)),
        t(lang, "protocol.objective_note", objective=term(lang, "indicator", "soil loss")),
    ]
    slots = se.extract_slots(" ".join(bits))
    assert (slots.lat, slots.lon) == (8.38, 39.37)
    assert slots.practice_family == EROSION
    assert slots.indicator == "soil loss"
    assert slots.is_complete


def test_free_text_after_coordinates_is_not_truncated_by_the_protocol_parser():
    """'…at 8.38, 39.37 and I want…' must keep lon = 39.37 (the sentence-stop
    lookahead once let the numeric group backtrack to '39' + '.37')."""
    slots = se.extract_slots("My farm is at 8.38, 39.37 and I want to reduce erosion.")
    assert (slots.lat, slots.lon) == (8.38, 39.37)
    assert slots.indicator == "soil loss" and slots.is_complete


def test_protocol_templates_are_anchored_to_sentence_starts():
    """Free text that merely contains the English template words is not a chip."""
    slots = se.extract_slots("I think my challenge is the steep slope near my house")
    assert slots.source != "protocol"


# ------------------------------------------------------------ chip hints
def test_hint_sets_slots_without_parsing_the_text():
    slots = se.extract_slots(
        "ፈተናዬ የአፈር ለምነት ነው።",  # display sentence; the hint is the truth
        hint={"practice_family": SOIL, "indicator": "SOM content", "lat": 8.38, "lon": 39.37},
    )
    assert slots.practice_family == SOIL
    assert slots.indicator == "SOM content"
    assert (slots.lat, slots.lon) == (8.38, 39.37)
    assert slots.source == "hint"
    assert slots.is_complete


def test_hint_rejects_values_outside_the_contract():
    slots = se.extract_slots("hello", hint={"practice_family": "Bogus", "indicator": "nope", "lat": 60, "lon": 10})
    assert slots.practice_family is None and slots.indicator is None and slots.lat is None
    assert slots.source is None


def test_hint_beats_conflicting_text():
    slots = se.extract_slots("My challenge is livestock.", hint={"practice_family": EROSION})
    assert slots.practice_family == EROSION


# ------------------------------------------------------------ LLM pass
def test_english_and_structured_input_never_need_the_llm():
    en = se.extract_slots("I want to reduce soil loss near Debre Birhan")
    assert intent_llm.needs_llm("I want to reduce soil loss near Debre Birhan", "en", en) is False
    hinted = se.extract_slots("x", hint={"practice_family": EROSION})
    assert intent_llm.needs_llm("x", "am", hinted) is False
    proto = se.extract_slots(t("am", "protocol.challenge", family=term("am", "family", EROSION)))
    assert intent_llm.needs_llm("…", "am", proto) is False
    free = se.extract_slots(AM_FREE_TEXT)
    assert intent_llm.needs_llm(AM_FREE_TEXT, "am", free) is True
    assert intent_llm.needs_llm("", "am", free) is False


@pytest.mark.parametrize("lang,text", [("am", AM_FREE_TEXT), ("om", OM_FREE_TEXT)])
async def test_llm_reading_fills_slots_and_geocodes_the_place(monkeypatch, lang, text):
    seen: dict = {}

    async def fake_call(messages, settings):
        seen["messages"] = messages
        return {
            "practice_family": EROSION,
            "indicator": "soil loss",
            "place_name": "Debre Birhan",
            "lat": None,
            "lon": None,
            "crop_type": None,
            "is_followup": False,
            "wants_advice": True,
        }

    monkeypatch.setattr(intent_llm, "call_openai_json", fake_call)
    settings = Settings(_env_file=None, openai_api_key="sk-test")
    slots = se.extract_slots(text)
    assert not slots.is_complete  # rules cannot read Ethiopic / Qubee free text
    slots = await intent_llm.enrich_with_llm(slots, text, lang, settings)
    assert slots.llm_used and slots.source == "llm"
    assert slots.practice_family == EROSION
    assert slots.indicator == "soil loss"
    assert slots.place_name == "Debre Birhan"
    assert abs(slots.lat - 9.6795) < 0.02 and slots.geocode_source == "gazetteer"
    assert slots.is_complete and slots.missing == []
    # The prompt names the language and the user text, and lists the enumerations.
    system, user = seen["messages"]
    assert user["content"] == text
    assert ("Amharic" if lang == "am" else "Afaan Oromoo") in system["content"]
    assert "soil loss" in system["content"] and EROSION in system["content"]


async def test_llm_output_is_validated_against_the_contract(monkeypatch):
    async def junk(messages, settings):
        return {
            "practice_family": "Terracing everywhere",
            "indicator": "profit",
            "lat": 51.5,
            "lon": -0.1,
            "crop_type": "Dragonfruit",
            "place_name": 42,
        }

    monkeypatch.setattr(intent_llm, "call_openai_json", junk)
    settings = Settings(_env_file=None, openai_api_key="sk-test")
    slots = await intent_llm.enrich_with_llm(se.extract_slots(AM_FREE_TEXT), AM_FREE_TEXT, "am", settings)
    assert slots.llm_used
    assert slots.practice_family is None and slots.indicator is None
    assert slots.lat is None and slots.crop_type is None
    assert slots.missing == ["challenge", "objective", "location"]


async def test_llm_failure_degrades_to_the_rules(monkeypatch):
    async def boom(messages, settings):
        raise RuntimeError("quota")

    monkeypatch.setattr(intent_llm, "call_openai_json", boom)
    settings = Settings(_env_file=None, openai_api_key="sk-test")
    slots = await intent_llm.enrich_with_llm(se.extract_slots(AM_FREE_TEXT), AM_FREE_TEXT, "am", settings)
    assert slots.llm_used is False and not slots.is_complete


def test_llm_prompt_crop_vocabulary_matches_the_dataset():
    crops = intent_llm.crop_type_vocabulary()
    assert len(crops) > 10 and "Maize" in crops
    assert intent_llm.validate({"crop_type": "maize"}, crops)["crop_type"] == "Maize"


# ------------------------------------------------------------ chat behaviour
async def test_no_key_steers_amharic_free_text_to_the_advisor(monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "openai_api_key", "")
    out = await chat_service.run_chat(AM_FREE_TEXT, [], language="am")
    assert out["recommendation"] is None
    assert t("am", "clarify.use_advisor") in out["reply"]
    assert t("am", "clarify.all_missing") in out["reply"]
    assert out["slots"]["llm_used"] is False


async def test_no_key_english_free_text_is_not_steered(monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "openai_api_key", "")
    out = await chat_service.run_chat("I want to reduce soil loss on my sloping field", [], language="en")
    assert t("en", "clarify.use_advisor") not in out["reply"]
    assert "location" in out["reply"].lower()


async def test_chip_hint_completes_the_request_without_a_key(monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "openai_api_key", "")
    msg = t("om", "protocol.farm_at", lat="8.3800", lon="39.3700")
    out = await chat_service.run_chat(
        msg, [], language="om", hint={"lat": 8.38, "lon": 39.37, "practice_family": EROSION, "indicator": "soil loss"}
    )
    assert out["recommendation"] is not None
    assert out["recommendation"]["query"]["indicator"] == "soil loss"
    assert out["slots"]["source"] == "hint"
    assert "dhiqama biyyee" in out["reply"].lower()  # Afaan Oromoo evidence summary
