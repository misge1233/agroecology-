"""E7 Part D: ``ADVISOR_ENGINE=m3`` (the m3_gate decision) on a fixture M1 v2 artifact and a fake
LLM client: the language model orders thin-evidence requests only; numbers, intervals and
citations stay M1 v2's; timeouts, errors and abstentions fall back to the M1 v2 order; the call
is cached and its cost logged; the default engine is unchanged."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.config import Settings  # noqa: E402
from app.services import m1_service, m3_service, registry_service  # noqa: E402
from tests.test_m1_engine import CONTEXT, REGISTRY, artifact  # noqa: E402,F401


class FakeLLM:
    """Ranks the candidates in reverse alphabetical order; counts calls; optional delay/abstain/error."""

    model = "gpt-4.1-mini"
    reasoning = False

    def __init__(self, delay: float = 0.0, cls: str = "benefit", fail: bool = False) -> None:
        self.delay, self.cls, self.fail = delay, cls, fail
        self.calls = 0
        self.cache: dict[str, dict] = {}
        self.stats = {}

    def params(self):
        return {"temperature": 0}

    def chat(self, messages, schema=None, repeat=None):
        key = json.dumps(messages, sort_keys=True)
        if key in self.cache:
            return {**self.cache[key], "from_cache": True}
        self.calls += 1
        if self.fail:
            raise RuntimeError("network down")
        time.sleep(self.delay)
        cands = schema["schema"]["properties"]["ranking"]["items"]["enum"]
        ranking = sorted(cands, reverse=True)
        ans = {"ranking": ranking, "items": [{"id": c, "effect_class": self.cls, "confidence": 0.6, "card_ids": [],
                                             "reason": "general knowledge"} for c in ranking]}
        rec = {"content": json.dumps(ans), "parsed": ans, "usage": {"prompt_tokens": 500, "completion_tokens": 120},
               "latency_s": self.delay, "cost_usd": 0.0004, "from_cache": False, "model": self.model}
        self.cache[key] = rec
        return rec


@pytest.fixture
def m3(artifact, tmp_path, monkeypatch):  # noqa: F811
    gate = tmp_path / "m3_gate"
    gate.mkdir()
    (gate / "config.json").write_text(json.dumps({"threshold": 10**6, "llm_model": "gpt-4.1-mini", "timeout_s": 8.0,
                                                  "decision": "E7 Part C branch 2"}), encoding="utf-8")
    s = Settings(_env_file=None, openai_api_key="", advisor_engine="m3", m1_artifact_dir=str(artifact),
                 m3_artifact_dir=str(gate), m3_timeout_seconds=0.5)
    for mod in (m1_service, m3_service):
        monkeypatch.setattr(mod, "get_settings", lambda: s)
    monkeypatch.setattr(registry_service, "get_registry", lambda country: REGISTRY)
    monkeypatch.setattr(m1_service, "context_of", lambda lat, lon: dict(CONTEXT))
    m1_service.reset()
    m3_service.reset()
    yield s, gate
    m1_service.reset()
    m3_service.reset()


def _ranker(s, client):
    m3_service.reset()
    return m3_service.ranker(s, m1_engine=m1_service.load(s), client=client)


def test_thin_evidence_is_ordered_by_the_llm_and_numbers_stay_m1(m3):
    s, _ = m3
    llm = FakeLLM()
    _ranker(s, llm)
    out = m1_service.rank(9.0, 38.0, "LOW_CROP_PRODUCTIVITY", "YIELD", "maize", top_n=10, country="TT")
    assert out["engine"] == "m3" and out["ordering"]["source"] == "llm_order" and out["ordering"]["llm"]["outcome"] == "used"
    assert [i["practice_id"] for i in out["items"]] == ["D", "C", "B", "A"] and llm.calls == 1
    s1 = Settings(_env_file=None, openai_api_key="", advisor_engine="m1_v2", m1_artifact_dir=s.m1_artifact_dir)
    base = {i["practice_id"]: i for i in m1_service.rank(9.0, 38.0, "LOW_CROP_PRODUCTIVITY", "YIELD", "maize", top_n=10,
                                                         country="TT", settings=s1)["items"]}
    for it in out["items"]:  # every number, interval, lead label and citation is M1 v2's
        b = base[it["practice_id"]]
        assert (it["est_lrr"], it["lo"], it["hi"], it["lead_label"], it["citations"]) == \
               (b["est_lrr"], b["lo"], b["hi"], b["lead_label"], b["citations"])
    # the same request again: answered from the cache, no new call
    again = m1_service.rank(9.0, 38.0, "LOW_CROP_PRODUCTIVITY", "YIELD", "maize", top_n=10, country="TT")
    assert llm.calls == 1 and again["ordering"]["llm"]["from_cache"] and again["ordering"]["llm"]["cost_usd"] == 0
    assert out["ordering"]["llm"]["cost_usd"] == pytest.approx(0.0004)


@pytest.mark.parametrize("client,outcome", [(FakeLLM(delay=2.0), "timeout"), (FakeLLM(fail=True), "error:RuntimeError"),
                                            (FakeLLM(cls="unknown"), "abstained")])
def test_timeout_error_and_abstention_fall_back_to_the_m1_order(m3, client, outcome):
    s, _ = m3
    _ranker(s, client)
    out = m1_service.rank(9.0, 38.0, "LOW_CROP_PRODUCTIVITY", "YIELD", "maize", top_n=10, country="TT")
    s1 = Settings(_env_file=None, openai_api_key="", advisor_engine="m1_v2", m1_artifact_dir=s.m1_artifact_dir)
    base = m1_service.rank(9.0, 38.0, "LOW_CROP_PRODUCTIVITY", "YIELD", "maize", top_n=10, country="TT", settings=s1)
    assert out["ordering"]["source"] == "m1_v2" and out["ordering"]["llm"]["outcome"] == outcome
    assert [i["practice_id"] for i in out["items"]] == [i["practice_id"] for i in base["items"]]
    assert out["ordering"]["llm"]["latency_s"] < 1.5  # the timeout (0.5 s here) bounds the wait


def test_dense_evidence_keeps_the_m1_order_without_a_call(m3):
    s, gate = m3
    (gate / "config.json").write_text(json.dumps({"threshold": 0, "llm_model": "gpt-4.1-mini"}), encoding="utf-8")
    llm = FakeLLM()
    _ranker(s, llm)
    out = m1_service.rank(9.0, 38.0, "LOW_CROP_PRODUCTIVITY", "YIELD", "maize", top_n=10, country="TT")
    assert out["ordering"]["source"] == "m1_v2" and out["ordering"]["llm"] is None and llm.calls == 0


def test_advise_carries_engine_and_ordering_and_metadata_reports_the_gate(m3):
    from app.services import advisory_service as adv

    s, _ = m3
    _ranker(s, FakeLLM())
    items, ordering = adv._m1_ranking(9.0, 38.0, "F1", "yield", "maize", s)
    assert [i["practice_id"] for i in items] == ["X", "B", "A"] and ordering["source"] == "llm_order"
    info = {**m1_service.info(s), **m3_service.info(s)}
    assert info["engine"] == "m3" and info["gate_threshold"] == 10**6 and info["llm_model"] == "gpt-4.1-mini"


def test_missing_gate_config_fails_fast_and_legacy_is_untouched(tmp_path, monkeypatch, artifact):  # noqa: F811
    s = Settings(_env_file=None, openai_api_key="", advisor_engine="m3", m1_artifact_dir=str(artifact),
                 m3_artifact_dir=str(tmp_path / "none"))
    m3_service.reset()
    with pytest.raises(RuntimeError, match="write-config"):
        m3_service.warmup(s)
    legacy = Settings(_env_file=None, openai_api_key="")
    assert not m3_service.enabled(legacy) and m3_service.info(legacy) == {} and m1_service.engine_name(legacy) == "legacy"
    m3_service.warmup(legacy)  # nothing to load
    m3_service.reset()
