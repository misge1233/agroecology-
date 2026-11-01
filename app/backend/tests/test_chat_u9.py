"""Chat in U9: register switching (en/am/om), soil constraints, the chat eval set.

No key, no rasters, no model: synthetic payloads and a fake graph.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pytest

from app.config import Settings
from app.services import advisory_service as adv
from app.services import chat_service as cs
from app.services import fusion_service as fu
from app.services.slot_extraction import constraints_from_text, extract_slots

ISFM = "Integrated soil fertility management"
CHAT_EVAL = Path(__file__).resolve().parents[3] / "rag" / "eval" / "chat_eval.jsonl"


class Graph:
    def __init__(self, studies: dict[str, list[dict[str, Any]]] | None = None) -> None:
        self.studies = studies or {}

    def evidence_summary(self, practice: str, indicator: str) -> dict[str, Any]:
        st = self.studies.get(practice, [])
        return {"practice": practice, "indicator": indicator, "found": bool(st), "studies": st,
                "n_studies": len(st), "n_obs": sum(s["n_obs"] for s in st), "aez_belts": [],
                "obs_by_belt": {}, "belt_counts_exact": True, "corpus_status": {}, "crop_groups": []}

    def related_practices(self, practice: str, k: int = 5) -> list[dict[str, Any]]:
        return []

    def similar_context_technologies(self, *a: Any, **kw: Any) -> list[dict[str, Any]]:
        return []


def study(no: str, pct: float, n: int, belt: str = "Moist Weyna Dega") -> dict[str, Any]:
    return {"study_no": no, "era_code": f"E{no}", "title": f"Liming trial {no}", "year": 2016, "doi": None,
            "mean_log_rr": math.log(1 + pct / 100), "n_obs": n, "share_positive": 1.0, "obs_by_belt": {belt: n}}


def payload(items: list[tuple[str, float]], indicator: str = "yield", direction: str = "increase",
            crop: str | None = "Teff") -> dict[str, Any]:
    return {
        "query": {"lat": 11.59, "lon": 37.39, "practice_family": ISFM, "indicator": indicator,
                  "crop_type": crop, "goal_direction": direction},
        "recommendations": [{"practice": p, "effect": f"~{abs(v):.0f}% increase in {indicator}"} for p, v in items],
        "details": {"context": {"aez_belt": "Moist Weyna Dega", "Rainfall": 1340.0, "slope": 4.0},
                    "confidence": "medium",
                    "ranked": [{"practice": p, "pct_change": v, "log_ratio": round(math.log(1 + v / 100), 4),
                                "n_evidence": 6} for p, v in items]},
    }


def settings() -> Settings:
    return Settings(_env_file=None, openai_api_key="")


@pytest.fixture(autouse=True)
def hermetic(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import get_settings
    from app.services import explain_service as es

    monkeypatch.setattr(get_settings(), "openai_api_key", "")
    monkeypatch.setattr(es, "get_graph_query", lambda: Graph({"pH Control": [study("1", 35, 4)]}))
    monkeypatch.setattr(fu, "_dataset_study_stats", lambda: ({}, {"yield": 0.4, "soil loss": 0.6}))
    monkeypatch.setattr(fu, "_model_rmse", lambda: {"yield": 0.3, "soil loss": 0.5})


# ------------------------------------------------------------- registers
@pytest.mark.parametrize("message", [
    "Why?", "How do you know?", "What is the evidence?", "Which study says that?", "Show me the sources",
    "ለምን?", "ማስረጃው ምንድን ነው?", "ምንጩ የትኛው ነው?",
    "Maaliif?", "Ragaan isaa maali?", "Maddi isaa eessa?",
])
def test_evidence_intents_are_recognised_in_three_languages(message: str) -> None:
    assert cs.is_evidence_request(message)


@pytest.mark.parametrize("message", ["My farm is near Bahir Dar", "Thanks!", "I want more yield", "Qonni koo Adaamaa jira"])
def test_ordinary_messages_stay_in_the_plain_register(message: str) -> None:
    assert not cs.is_evidence_request(message)


@pytest.mark.asyncio
@pytest.mark.parametrize(("language", "question", "label"), [
    ("en", "Why this one?", "Model estimate for your area"),
    ("am", "ለምን?", "ለአካባቢዎ የሞዴል ግምት"),
    ("om", "Maaliif?", "Tilmaama moodeelaa naannoo keessaniif"),
])
async def test_asking_why_switches_chat_to_the_labelled_cited_register(language: str, question: str, label: str) -> None:
    last = payload([("pH Control", 30.0)])
    events = []
    async for chunk in cs.stream_chat(question, [], last, 3, language):
        events.append(json.loads(chunk[len("data: "):]))
    text = "".join(e.get("text", "") for e in events if e["type"] == "token")
    assert label in text and "[1]" in text
    assert not [e for e in events if e["type"] in ("recommendation", "advisory")]  # no re-scoring


def test_the_plain_register_has_no_markers_and_the_evidence_register_has_them() -> None:
    rec = payload([("pH Control", 30.0)])
    bundles = cs._bundles_for(rec)
    plain = cs.chat_summary(bundles, rec, "en")
    labelled = cs.evidence_register(rec, "en", bundles)
    assert "[" not in plain and "Reported in study [1]" in labelled


# ------------------------------------------------- A6: soil constraints
def test_soil_constraints_are_parsed_in_three_languages() -> None:
    assert constraints_from_text("my soil is acidic") == ["acidic_soil"]
    assert constraints_from_text("the pH is low and the field is waterlogged") == ["acidic_soil", "waterlogging"]
    assert constraints_from_text("አፈሬ አሲዳማ ነው") == ["acidic_soil"]
    assert constraints_from_text("biyyeen koo asiidii dha") == ["acidic_soil"]
    assert constraints_from_text("saline soil near the lake") == ["salinity"]


def _advise(items: list[tuple[str, float]], constraints: list[str], top_n: int = 2, crop: str | None = "Teff") -> dict[str, Any]:
    p = payload(items, crop=crop)
    return adv.advise(11.59, 37.39, ISFM, "yield", crop_type=crop, top_n=top_n, graph_query=Graph({"pH Control": [study("1", 35, 4)]}),
                      recommend_fn=lambda **kw: p, context_fn=lambda la, lo: p["details"]["context"],
                      pool_fn=lambda fam: [i[0] for i in items], indicators=["yield"], settings=settings(),
                      stats_fn=lambda: ({}, {"yield": 0.4}), rmse_fn=lambda: {"yield": 0.3}, constraints=constraints)


def test_a_named_constraint_brings_its_practice_in_and_flags_it() -> None:
    out = _advise([("Organic Fertilizer", 60.0), ("Inorganic Fertilizer", 55.0), ("pH Control", 30.0)], ["acidic_soil"])
    shown = [b["practice"] for b in out["practices"]]
    assert shown[-1] == "pH Control" and out["practices"][-1]["constraint_pick"] is True
    assert out["practices"][-1]["matches_constraints"] == ["acidic_soil"]
    assert [r["practice"] for r in out["model"]["details"]["ranked"]] == shown  # payload follows the bundles
    text = cs.chat_summary(out["practices"], out["model"], "en")
    assert "It targets acidic soil directly." in text and "Added because it addresses the soil problem" in text


def test_a_practice_that_replaces_the_named_crop_is_flagged() -> None:
    out = _advise([("Drought Tolerant Crops", 40.0), ("Improved Varieties", 20.0)], [], top_n=2)
    flags = {b["practice"]: b["replaces_crop"] for b in out["practices"]}
    assert flags == {"Drought Tolerant Crops": True, "Improved Varieties": False}
    assert "instead of Teff" in cs.chat_summary(out["practices"], out["model"], "en")


def test_large_gains_carry_a_caution_in_plain_language() -> None:
    out = _advise([("Organic Fertilizer", 95.0)], [], top_n=1)
    assert out["practices"][0]["caution"] is True
    assert "Gains this large are uncommon" in cs.chat_summary(out["practices"], out["model"], "en")


# ----------------------------------------------------------- chat eval set
def _eval_cases() -> list[dict[str, Any]]:
    return [json.loads(line) for line in CHAT_EVAL.read_text(encoding="utf-8").splitlines() if line.strip()]


@pytest.mark.parametrize("case", _eval_cases(), ids=lambda c: c["id"])
def test_chat_eval_set_request_understanding(case: dict[str, Any]) -> None:
    slots = extract_slots(case["message"])
    exp = case["expect"]
    assert slots.practice_family == exp["practice_family"]
    assert slots.indicator == exp["indicator"]
    assert slots.crop_type == exp["crop_type"]
    assert slots.place_name == exp["place_name"]
    assert slots.constraints == exp["constraints"]
    comp = exp["constraint_component"]
    assert comp in adv.CONSTRAINT_COMPONENTS[exp["constraints"][0]]
    assert exp["never_lead_with_component"] in adv.REPLACES_CROP_COMPONENTS


def test_confidence_vocabulary_matches_the_advisor_glossary():
    """D5: chat names confidence exactly like the Advisor card (glossary.ts CONFIDENCE)."""
    import re
    from pathlib import Path

    from app.i18n import t

    glossary = (Path(__file__).resolve().parents[2] / "frontend" / "src" / "i18n" / "glossary.ts").read_text(encoding="utf-8")
    block = glossary[glossary.index("export const CONFIDENCE:"):glossary.index("export const CONFIDENCE_MEANING")]
    for level in ("high", "medium", "low"):
        row = re.search(rf'{level}: \{{ en: "([^"]+)", am: "([^"]+)", om: "([^"]+)" \}}', block)
        assert row, level
        for lang, label in zip(("en", "am", "om"), row.groups()):
            assert t(lang, f"fusion.confidence.{level}").lower() == label.lower(), (lang, level)


def test_reason_text_uses_the_display_name_in_the_reply_language():
    """D11: no English practice name inside an Amharic or Oromo sentence."""
    from app.services.advisory_service import reason_text
    from app.services.practice_names import practice_name

    reason = {"key": "mode.reason.thin_evidence",
              "params": {"practice": "Mulch", "n_studies": 1, "n_obs": 4, "min_studies": 3, "min_obs": 20}}
    for lang in ("am", "om"):
        text = reason_text(reason, lang)
        assert practice_name("Mulch", lang) in text
        assert "Mulch" not in text or practice_name("Mulch", lang) == "Mulch"
    assert reason["params"]["practice"] == "Mulch"  # the contract is untouched


def test_chat_answers_are_prose_not_lists():
    """1 Nov 2026: chat answers read as conversation: no bullets, headings or menus."""
    import re

    from app.services import chat_service as cs

    rec = {"query": {"indicator": "soil loss", "crop_type": None}, "details": {"context": {"aez_belt": "Dry Kolla"}}}
    bundle = {
        "practice": "Mulch", "lead_source": "study", "match": "belt_group", "disagreement": False, "caution": False,
        "headline": {"value": -71.0, "unit": "%", "source": "study", "ref": "S1", "display": "71"},
        "model": {"value": -60.0, "unit": "%", "source": "model", "ref": None, "display": "60",
                  "confidence": "low", "n_obs": 12, "n_studies": 2, "n_obs_in_zone": 0, "se_log": 0.4},
        "study": {"value": -71.0, "unit": "%", "source": "study", "ref": "S1", "display": "71",
                  "refs": ["S1"], "match": "belt_group", "n_studies": 1, "n_obs": 9},
        "studies": [{"ref": "S1", "study_no": "CSA_18", "era_code": None, "title": "Mulch trial", "year": 2000,
                     "doi": None, "data_source": "csa", "n_obs": 9, "mean_log_rr": -1.2, "se_log": 0.3,
                     "effect": {"value": -71.0, "unit": "%", "source": "study", "ref": "S1", "display": "71"},
                     "share_positive": 0.0, "aez_belts": ["Dry Kolla"], "obs_by_belt": {"Dry Kolla": 9},
                     "match": "belt_group"}],
        "conservative_bound": -40.0,
    }
    for lang in ("en", "am", "om"):
        for text in (cs.chat_summary([bundle], rec, lang), cs.evidence_register(rec, lang, [bundle])):
            assert not re.search(r"(?m)^\s*([-*•]|\d+\.)\s", text), text
            assert not re.search(r"(?m)^#{1,6}\s", text), text
            assert "፦:" not in text and "::" not in text


def test_the_ai_writer_is_told_to_talk_not_list():
    from app.services import chat_service as cs

    rec = {"query": {"indicator": "yield"}, "recommendations": [], "details": {}}
    for facts in ("Mulch: about 50% more yield.", None):
        prompt = cs.narrative_system_instruction(rec, "en", facts=facts)
        assert cs.CONVERSATION_STYLE in prompt
