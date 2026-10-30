"""advise(): the three modes end to end with fakes; the chat integration (P9)."""
from __future__ import annotations

import json
from typing import Any

import pytest

from app.config import Settings
from app.i18n import t
from app.services import advisory_service as adv
from app.services import evidence_service as ev
from app.services import explain_service as es


@pytest.fixture(autouse=True)
def _hermetic(monkeypatch: pytest.MonkeyPatch) -> None:
    """Never touch the real graph store, the Chroma index or the network."""
    monkeypatch.setattr(es, "get_graph_query", lambda: None)
    monkeypatch.setattr(es, "get_guidance_retriever", lambda: None)
from tests.test_evidence_service import ECWM, INDICATORS, POOL, FakeGraphQuery, FakeGuidance, model, passages, summary

NO_EVIDENCE = ValueError("No field evidence in the dataset for challenge 'X' with objective 'Y'. Choose a different objective for this challenge.")
UNSUPPORTED = ValueError("The objective 'yield' is not supported for challenge 'Livestock production and management'. Supported objectives: biomass yield.")


def _settings(**kw: Any) -> Settings:
    return Settings(_env_file=None, openai_api_key="", **kw)


def _advise(gq, recommend, guidance=None, **kw):
    return adv.advise(8.38, 39.37, ECWM, "soil loss", top_n=3, graph_query=gq, guidance_retriever=guidance,
                      recommend_fn=recommend, context_fn=lambda la, lo: {"aez_belt": "Dry Kolla", "Rainfall": 700, "slope": 3},
                      pool_fn=lambda fam: POOL, indicators=INDICATORS, settings=_settings(), **kw)


def test_model_led_returns_the_engine_payload_unchanged_and_no_candidates():
    payload = model(["Mulch", "Physical SWC Measures", "Deficit Irrigation"])
    gq = FakeGraphQuery({("Mulch", "soil loss"): summary(4, {"Dry Kolla": 12})})
    out = _advise(gq, lambda **kw: payload, guidance=FakeGuidance(passages()))
    assert out["mode"] == ev.MODEL_LED
    assert out["model"] is payload and out["knowledge_candidates"] == []
    assert out["reasons"][0]["key"] == "mode.reason.strong_evidence"
    assert out["context"]["aez_belt"] == "Dry Kolla"


def test_hybrid_keeps_the_ranking_and_adds_cited_candidates():
    payload = model(["Mulch", "Physical SWC Measures"])
    gq = FakeGraphQuery({("Mulch", "soil loss"): summary(1, {"Wet Dega": 2}), ("Mulch", "yield"): summary(5, {"Dry Kolla": 20})})
    out = _advise(gq, lambda **kw: payload, guidance=FakeGuidance(passages()))
    assert out["mode"] == ev.HYBRID and out["model"] is payload
    assert out["knowledge_candidates"] and all(c["citations"] for c in out["knowledge_candidates"])
    assert out["knowledge_candidates"][0]["key"] == "Mulch"
    assert out["funnel"]["guidance"]["retrieved"] == 5


def test_no_evidence_error_is_knowledge_led_not_an_exception():
    def boom(**kw):
        raise NO_EVIDENCE
    gq = FakeGraphQuery({("Mulch", "yield"): summary(5, {"Dry Kolla": 20})})
    out = _advise(gq, boom, guidance=FakeGuidance(passages()))
    assert out["mode"] == ev.KNOWLEDGE_LED and out["model"] is None
    assert out["reasons"][0] == {"key": "mode.reason.engine_no_evidence", "params": {}}
    assert out["context"]["aez_belt"] == "Dry Kolla"  # resolved without the model payload
    assert out["knowledge_candidates"][0]["key"] == "Mulch"


def test_unsupported_pair_is_knowledge_led_and_other_errors_propagate():
    def unsupported(**kw):
        raise UNSUPPORTED
    assert _advise(FakeGraphQuery({}), unsupported)["reasons"][0]["key"] == "mode.reason.engine_unsupported"

    def other(**kw):
        raise ValueError("unknown indicator: magic beans")
    with pytest.raises(ValueError):
        _advise(FakeGraphQuery({}), other)


def test_knowledge_led_without_any_candidate_says_so():
    def boom(**kw):
        raise NO_EVIDENCE
    out = _advise(FakeGraphQuery({}), boom, guidance=None)
    assert out["mode"] == ev.KNOWLEDGE_LED and out["knowledge_candidates"] == []
    assert out["reasons"][-1]["key"] == "mode.reason.no_candidates"
    text = adv.knowledge_led_text(out, ECWM, "soil loss", "en")
    assert text == t("en", "mode.knowledge_led.none", challenge=ECWM, objective="soil loss")


def test_no_graph_degrades_to_model_led_with_a_reason():
    payload = model(["Mulch"])
    out = _advise(None, lambda **kw: payload)
    assert out["mode"] == ev.MODEL_LED and out["reasons"] == [{"key": "mode.reason.graph_unavailable", "params": {}}]


def test_hybrid_note_and_knowledge_led_text_carry_counts_only():
    payload = model(["Mulch"])
    gq = FakeGraphQuery({("Mulch", "soil loss"): summary(1, {"Wet Dega": 2}), ("Mulch", "yield"): summary(5, {"Dry Kolla": 20})})
    out = _advise(gq, lambda **kw: payload, guidance=FakeGuidance(passages()))
    note = adv.hybrid_note(out, "en")
    n = len(out["knowledge_candidates"])
    assert note.startswith(" Field-trial evidence for this request is thin") and f"{n} documented" in note
    assert adv.hybrid_note({"mode": ev.MODEL_LED, "knowledge_candidates": [{}]}, "en") == ""
    text = adv.knowledge_led_text(out, ECWM, "soil loss", "en")
    assert text.startswith("There is no field-trial evidence for **" + ECWM) and "- **Mulch** — " in text
    assert "%" not in text  # never an effect
    assert all(ev.rationale_numbers_are_counts(c) for c in out["knowledge_candidates"])


def test_reasons_render_in_the_three_languages():
    reason = {"key": "mode.reason.strong_evidence", "params": {"practice": "Mulch", "n_studies": 4, "n_obs": 12}}
    for lang in ("en", "am", "om"):
        text = adv.reason_text(reason, lang)
        assert "Mulch" in text and "4" in text and "12" in text


@pytest.mark.asyncio
async def test_chat_emits_the_advisory_event_and_keeps_the_model_led_narrative_byte_identical(monkeypatch):
    from app.config import get_settings
    from app.services import chat_service as cs
    from app.services import slot_extraction as se

    monkeypatch.setattr(get_settings(), "openai_api_key", "")
    payload = model(["Mulch", "Physical SWC Measures"])
    gq = FakeGraphQuery({("Mulch", "soil loss"): summary(4, {"Dry Kolla": 12})})
    monkeypatch.setattr(cs, "_advise_from_slots", lambda slots, top_n, language: adv.advise(
        8.38, 39.37, ECWM, "soil loss", top_n=top_n, language=language, graph_query=gq,
        recommend_fn=lambda **kw: payload, context_fn=lambda la, lo: payload["details"]["context"],
        pool_fn=lambda fam: POOL, indicators=INDICATORS, settings=_settings()))
    events = []
    async for chunk in cs.stream_chat("My farm is at 8.38, 39.37 and I want to reduce erosion.", [], None, 3, "en"):
        events.append(json.loads(chunk[len("data: "):]))
    types = [e["type"] for e in events]
    assert types[:3] == ["slots", "advisory", "recommendation"] and types[-1] == "done"
    assert events[1]["data"]["mode"] == ev.MODEL_LED and events[1]["data"]["knowledge_candidates"] == []
    narrative = "".join(e.get("text", "") for e in events if e["type"] == "token")
    assert narrative == se.evidence_summary(payload, "en")  # byte-identical to pre-P9


@pytest.mark.asyncio
async def test_chat_knowledge_led_answers_with_documented_practices(monkeypatch):
    from app.config import get_settings
    from app.services import chat_service as cs

    monkeypatch.setattr(get_settings(), "openai_api_key", "")
    gq = FakeGraphQuery({("Mulch", "yield"): summary(5, {"Dry Kolla": 20})})

    def boom(**kw):
        raise NO_EVIDENCE
    monkeypatch.setattr(cs, "_advise_from_slots", lambda slots, top_n, language: adv.advise(
        8.38, 39.37, ECWM, "soil loss", top_n=top_n, language=language, graph_query=gq, recommend_fn=boom,
        context_fn=lambda la, lo: {"aez_belt": "Dry Kolla"}, pool_fn=lambda fam: POOL, indicators=INDICATORS,
        guidance_retriever=FakeGuidance(passages()), settings=_settings()))
    out = await cs.run_chat("My farm is at 8.38, 39.37 and I want to reduce erosion.", [], None, 3, "en")
    assert out["recommendation"] is None and out["error"] is None
    assert out["advisory"]["mode"] == ev.KNOWLEDGE_LED and out["advisory"]["knowledge_candidates"]
    assert "no field-trial evidence" in out["reply"].lower() and "**Mulch**" in out["reply"]
