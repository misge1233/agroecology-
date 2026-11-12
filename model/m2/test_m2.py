"""Methodology 2 (E6): masking canaries for cards, passages and graph facts, the budget cap,
the cache, validation and retry, the numeric guard, scoring and card selection."""
from __future__ import annotations

import json
import math

import httpx
import numpy as np
import pytest

from model.engines.base import RankRequest
from model.harness.mask import Mask
from model.m1.matched import dersimonian_laird
from model.m1.test_m1 import COMPONENTS, OUTCOME_GROUP, synthetic_store
from model.m2 import cards as mc
from model.m2 import prompt as pm
from model.m2.client import BudgetExceeded, ChatClient, Ledger
from model.m2.engine import M2Engine
from model.m2.knowledge import GraphFacts, PassageSource, n_tokens
from rag.graph.query import GraphQuery
from rag.graph.schema import EdgeType, NodeType, add_edge, add_node, new_graph, node_id
from rag.test_mask_canary import TOKEN, _chunk, build_fixture_index

NAMES = {"A": "Mulching", "B": "Mulch with manure", "C": "Stone bund", "D": "Bund with trees", "X": "Mulch variant"}
MAPS = dict(outcome_group=OUTCOME_GROUP, practice_name=NAMES, outcome_name={"YIELD": "Crop yield", "SOIL_LOSS": "Soil loss"},
            outcome_direction={"YIELD": 1, "SOIL_LOSS": -1}, components_of=COMPONENTS, belt_name_of={6: "Wet Dega", 7: "Moist Dega"})
PRICES = {"test-model": {"input": 1.0, "output": 2.0}, "text-embedding-3-small": {"input": 0.02, "output": 0.0}}
CTX = {"ctx_precip_annual": 900.0, "ctx_elevation": 1600.0, "ctx_aez_belt": 6, "release": "ET/2026.1"}


def _req(cands=("A", "B", "C"), mask=None, qid="q1"):
    return RankRequest(query_id=qid, context=dict(CTX), challenge_ids=[], outcome_id="YIELD", candidates=list(cands),
                       crop="maize", user_attrs={}, mask=mask or Mask.empty(), direction=1, objective_group="productivity")


class FakeClient:
    """Answers from a function of the messages; counts calls (no network)."""

    model = "fake"
    reasoning = False

    def __init__(self, answer):
        self.answer = answer
        self.calls: list[list[dict[str, str]]] = []
        self.stats = {}

    def params(self):
        return {"temperature": 0}

    def chat(self, messages, schema=None, repeat=None):
        self.calls.append(messages)
        content = self.answer(messages, len(self.calls))
        parsed = json.loads(content) if isinstance(content, str) else content
        return {"content": json.dumps(parsed), "parsed": parsed, "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                "latency_s": 0.1, "cost_usd": 0.0, "from_cache": False, "model": "fake"}


def _ids_in(messages):
    import re

    return re.findall(r"\[(c[0-9a-f]{6,})\]", messages[1]["content"])


def _answer(ranking, cls="benefit", cards=None, reason="evidence from similar sites"):
    return {"ranking": ranking, "items": [{"id": p, "effect_class": cls if not isinstance(cls, dict) else cls[p], "confidence": 0.7,
                                           "card_ids": (cards or {}).get(p, []), "reason": reason} for p in ranking]}


# ----------------------------------------------------------------- cards
def test_cards_never_show_a_masked_canary_study():
    store = synthetic_store(canary=True)
    mask = Mask.from_groups(["10.1/canary", "10.1/g03"], store)
    cs = mc.CardStore(**MAPS).fit(store, mask)
    assert cs.cards and not any(c.doi == "10.1/canary" or "ERA_CANARY" in c.study_ids for c in cs.cards)
    eng = M2Engine("m2_cards", FakeClient(lambda m, n: _answer(["X", "A"])), **MAPS, mode="collect")
    eng.fit(store, mask)
    eng.rank(_req(("X", "A"), mask))
    text = eng.collected[0]["messages"][1]["content"]
    assert "canary" not in text and "+14741%" not in text
    # unmasked, the canary card is selectable for its practice (so the test can tell)
    open_ = mc.CardStore(**MAPS).fit(store, Mask.from_groups(["10.1/g03"], store))
    sel = open_.select(CTX, ["X"], "YIELD", "productivity")
    assert any(c.doi == "10.1/canary" for c in sel["X"])


def test_card_template_selection_limits_and_related_flag():
    store = synthetic_store()
    cs = mc.CardStore(**MAPS).fit(store, Mask.empty())
    c = cs.cards[0]
    assert c.card_id.startswith("c") and len(c.card_id) == 7 and n_tokens(c.text) <= 100
    assert "higher is better" in c.text and "(+ = better)" in c.text and "Moist Dega" in c.text or "Wet Dega" in c.text
    assert len({k.card_id for k in cs.cards}) == len(cs.cards)  # stable unique ids
    sel = cs.select(CTX, ["A", "B", "C", "D", "X"], "YIELD", "productivity")
    assert all(len(sel[p]) == mc.PER_CANDIDATE for p in "ABCD")
    assert sel["X"] and all(k.related and "RELATED PRACTICE" in k.text and k.practice_id != "X" for k in sel["X"])
    assert all(k.practice_id == "A" and k.outcome_id == "YIELD" for k in sel["A"])
    capped = cs.select(CTX, ["A", "B", "C", "D", "X"], "YIELD", "productivity", per_candidate=4, max_cards=9)
    assert sum(len(v) for v in capped.values()) == 9 and all(capped[p] for p in "ABCDX")  # shrunk, never dropped
    # ordering by context distance: the first card of A is at least as near as the last
    d = cs.space._distances(CTX, np.array([cs.cards.index(next(x for x in cs.cards if x.card_id == k.card_id)) for k in sel["A"]]))
    assert d[0] <= d[-1]
    assert mc.pct_change(math.log(1.5)) == "+50%" and mc.short_citation("Temesgen, M., Hoogmoed (2009). T", 2009) == "Temesgen 2009"
    assert mc.short_citation("Roschewitz_2005_001", None) == "Roschewitz 2005" and mc.precision_class(float("nan"), "High") == "medium"


# ----------------------------------------------------------------- passages and graph facts
def test_passages_never_return_a_masked_canary_chunk(tmp_path):
    chunks = [_chunk("canary", f"mulching crop yield {TOKEN} Ethiopia", era_code="S03", doi="10.1/canary", study_ids=["ERA_S03"]),
              _chunk("open1", "mulching crop yield Ethiopia rainfall", era_code="S01", doi="10.1/open"),
              _chunk("open2", f"stone bund crop yield {TOKEN}", era_code="S02", doi="10.1/open2")]
    r = build_fixture_index(tmp_path, chunks)
    src = PassageSource(r)
    store = synthetic_store(canary=True)
    mask = Mask(groups=frozenset({"10.1/canary"}), dois=frozenset({"10.1/canary"}), study_ids=frozenset({"ERA_S03"}),
                era_codes=frozenset({"S03"}))
    q = {"A": f"Mulching crop yield {TOKEN}", "C": f"Stone bund crop yield {TOKEN}"}
    hits = src.for_candidates(q, mask)
    assert hits and not any(h["chunk_id"] == "canary" for h in hits) and len(hits) <= 4
    assert any(h["chunk_id"] == "canary" for h in PassageSource(r).for_candidates(q, Mask.empty()))
    # through the engine: the prompt of the masked fold never carries the canary chunk
    eng = M2Engine("m2_rag", FakeClient(lambda m, n: _answer(["A", "C"])), **MAPS, passages=src, mode="collect")
    eng.fit(store, Mask.from_groups(["10.1/canary"], store))
    eng.rank(_req(("A", "C"), mask))
    assert "[canary]" not in eng.collected[0]["messages"][1]["content"] and "PASSAGES:" in eng.collected[0]["messages"][1]["content"]


def _graph():
    g = new_graph()
    add_node(g, NodeType.PRACTICE, "Mulching", label="Mulching", practice_id="A", practice_family="F1")
    add_node(g, NodeType.PRACTICE_COMPONENT, "Mulch", label="Mulch")
    add_edge(g, node_id(NodeType.PRACTICE, "Mulching"), EdgeType.COMPOSED_OF, node_id(NodeType.PRACTICE_COMPONENT, "Mulch"), "era_rows")
    add_node(g, NodeType.CHALLENGE, "LOW_YIELD", label="Low yield", name_en="Low crop productivity")
    add_edge(g, node_id(NodeType.PRACTICE, "Mulching"), EdgeType.ADDRESSES_PROBLEM, node_id(NodeType.CHALLENGE, "LOW_YIELD"), "era_rows")
    add_node(g, NodeType.INDICATOR, "yield", label="yield")
    add_node(g, NodeType.STUDY, "ERA_CANARY", label="ERA_CANARY", doi="10.1/canary", era_code="CANARY", title=f"Canary {TOKEN}")
    add_edge(g, node_id(NodeType.STUDY, "ERA_CANARY"), EdgeType.REPORTS_EFFECT, node_id(NodeType.PRACTICE, "Mulching"),
             "era_rows", key_suffix="yield", indicator="yield", n_obs=3)
    return GraphQuery(g)


def test_graph_facts_come_from_the_masked_view():
    store = synthetic_store(canary=True)
    mask = Mask.from_groups(["10.1/canary"], store)
    gf = GraphFacts(_graph()).fit(mask)
    assert not gf.view.graph.has_node(node_id(NodeType.STUDY, "ERA_CANARY"))  # the masked view
    facts = gf.facts(["A", "Z"])
    assert "components: Mulch" in facts["A"] and "Low crop productivity" in facts["A"] and facts["Z"] == ""
    assert n_tokens(facts["A"]) <= 61
    eng = M2Engine("m2_graph", FakeClient(lambda m, n: _answer(["A"])), **MAPS, passages=PassageSource(_NoPassages()),
                   graph=GraphFacts(_graph()), mode="collect")
    eng.fit(store, mask)
    eng.rank(_req(("A", "C"), mask))
    text = eng.collected[0]["messages"][1]["content"]
    assert "GRAPH FACTS:" in text and TOKEN not in text and "canary" not in text.lower()


class _NoPassages:
    unmaskable: dict = {}

    def retrieve(self, q, k=2, mask=None):
        return []


# ----------------------------------------------------------------- client: budget, cache, ledger
def _transport(counter):
    def handler(request: httpx.Request) -> httpx.Response:
        counter.append(json.loads(request.content))
        body = {"model": "test-model-2026", "system_fingerprint": "fp", "usage": {"prompt_tokens": 100, "completion_tokens": 50},
                "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(_answer(["A", "B"]))}}]}
        return httpx.Response(200, json=body)

    return httpx.MockTransport(handler)


def test_budget_cap_stops_before_sending_and_cache_reruns_free(tmp_path):
    sent: list = []
    ledger = Ledger(tmp_path / "ledger.jsonl")
    cl = ChatClient("test-model", budget_usd=1.0, cache_dir=tmp_path, ledger=ledger, prices=PRICES, api_key="k",
                    transport=_transport(sent))
    msgs = pm.messages("FARM CONTEXT: x")
    rec = cl.chat(msgs, pm.response_schema(["A", "B"]))
    assert len(sent) == 1 and rec["parsed"]["ranking"] == ["A", "B"] and not rec["from_cache"]
    assert sent[0]["temperature"] == 0 and sent[0]["seed"] == 0 and sent[0]["response_format"]["type"] == "json_schema"
    assert ledger.total() == pytest.approx((100 * 1.0 + 50 * 2.0) / 1e6)
    again = cl.chat(msgs, pm.response_schema(["A", "B"]))
    assert len(sent) == 1 and again["from_cache"] and again["parsed"] == rec["parsed"] and cl.stats["cache_hits"] == 1
    assert len(sent) == 1 and cl.chat(msgs, pm.response_schema(["A", "B"]), repeat="r1") and len(sent) == 2  # own key
    # a ledger near the cap: the next request is refused and nothing is sent
    ledger.settle(0.0, {"cost_usd": 0.999999, "kind": "test"})
    with pytest.raises(BudgetExceeded):
        cl.chat(pm.messages("FARM CONTEXT: y"), pm.response_schema(["A", "B"]))
    assert len(sent) == 2 and ledger._reserved == 0.0
    off = ChatClient("test-model", cache_dir=tmp_path, ledger=ledger, prices=PRICES, offline=True)
    assert off.chat(msgs, pm.response_schema(["A", "B"]))["from_cache"]
    with pytest.raises(LookupError):
        off.chat(pm.messages("never asked"), None)


def test_reasoning_models_get_no_temperature():
    cl = ChatClient("o3", prices={"o3": {"input": 2, "output": 8, "reasoning": True}}, api_key="k")
    assert "temperature" not in cl.params() and "seed" not in cl.params() and cl.reasoning


# ----------------------------------------------------------------- engine: validation, scoring, guard
def test_validation_retry_and_abstention():
    store = synthetic_store()

    def bad_then_good(messages, n):
        return _answer(["A", "B"]) if n == 1 else _answer(["B", "A", "C"])  # first answer misses C

    eng = M2Engine("m2_cards", FakeClient(bad_then_good), **MAPS)
    eng.fit(store, Mask.empty())
    items = eng.rank(_req())
    assert len(eng.client.calls) == 2 and "invalid" in eng.client.calls[1][-1]["content"]
    assert [i.practice_id for i in items] == ["A", "B", "C"] and max(items, key=lambda i: i.score).practice_id == "B"
    assert eng.log[-1]["valid"] and len(eng.log[-1]["attempts"]) == 2

    def invented(messages, n):
        return _answer(["A", "B", "C"], cards={"A": ["cdeadbeef"]})

    eng2 = M2Engine("m2_cards", FakeClient(invented), **MAPS)
    eng2.fit(store, Mask.empty())
    items = eng2.rank(_req())
    assert all(i.abstain for i in items) and eng2.n_abstained_invalid == 1 and eng2.log[-1]["attempts"][0]["invented_ids"] == 1
    with pytest.raises(pm.InvalidAnswer):
        pm.validate({"ranking": ["A", "A"], "items": []}, ["A", "B"], set())


def test_numeric_guard_and_estimates_from_cited_cards_only():
    """Numbers in the model's reason never reach est_lrr, lo, hi or any field; estimates are
    the random-effects pooling of the cited cards of that practice (related cards excluded)."""
    store = synthetic_store()
    captured = {}

    def answer(messages, n):
        ids = _ids_in(messages)
        captured["ids"] = ids
        eng_cards = {c.card_id: c for c in eng.cards.cards}
        a_ids = [i for i in ids if i in eng_cards and eng_cards[i].practice_id == "A"][:2]
        x_rel = [i for i in ids if i in eng_cards and eng_cards[i].practice_id != "X" and i not in a_ids][:1]
        return _answer(["A", "X", "C"], cls={"A": "large_benefit", "X": "benefit", "C": "unknown"},
                       cards={"A": a_ids, "X": x_rel}, reason="raises yield by 47 percent to 3.2 t/ha (0.385 lrr)")

    eng = M2Engine("m2_cards", FakeClient(answer), **MAPS)
    eng.fit(store, Mask.empty())
    items = {i.practice_id: i for i in eng.rank(_req(("A", "X", "C")))}
    cards = {c.card_id: c for c in eng.cards.cards}
    cited = [cards[i] for i in eng.log[-1]["items"]["A"]["card_ids"]]
    assert len(cited) == 2
    idx = np.array([eng.cards.cards.index(c) for c in cited])
    d = eng.cards.space._distances(CTX, idx)
    v = np.array([c.var if np.isfinite(c.var) and c.var > 0 else eng.cards.space.default_var for c in cited])
    est, se, _ = dersimonian_laird(np.array([c.y for c in cited]), v, 1 / (1 + d ** 2))
    a = items["A"]
    assert a.est_lrr == pytest.approx(est) and a.lo == pytest.approx(est - 1.2815515655446004 * se)
    assert items["X"].est_lrr is None and items["X"].citations  # only a related card: cited, no estimate
    assert items["C"].abstain and items["C"].est_lrr is None  # unknown abstains the candidate
    for it in items.values():
        for val in (it.est_lrr, it.lo, it.hi, it.score):
            assert val is None or not any(math.isclose(val, x, rel_tol=1e-9) for x in (47.0, 0.47, 3.2, 0.385))
        assert "47" not in " ".join(it.citations) and it.lead_source == "llm_evidence"


def test_cached_reruns_give_identical_predictions(tmp_path):
    store = synthetic_store()
    sent: list = []

    def handler(request):
        body = json.loads(request.content)
        cands = body["response_format"]["json_schema"]["schema"]["properties"]["ranking"]["items"]["enum"]
        sent.append(1)
        return httpx.Response(200, json={"model": "test-model", "usage": {"prompt_tokens": 10, "completion_tokens": 10},
                                         "choices": [{"message": {"content": json.dumps(_answer(sorted(cands)))}}]})

    ledger = Ledger(tmp_path / "l.jsonl")
    outs = []
    for offline in (False, True):
        cl = ChatClient("test-model", cache_dir=tmp_path, ledger=ledger, prices=PRICES, api_key="k",
                        transport=httpx.MockTransport(handler), offline=offline)
        eng = M2Engine("m2_cards", cl, **MAPS)
        eng.fit(store, Mask.from_groups(["10.1/g01"], store))
        outs.append([(i.practice_id, i.score, i.est_lrr, i.lo, i.hi, i.abstain, tuple(i.citations)) for i in eng.rank(_req())])
    assert outs[0] == outs[1] and len(sent) == 1


def test_zero_variant_shows_no_evidence_and_shuffle_changes_order():
    store = synthetic_store()
    eng = M2Engine("m2_zero", FakeClient(lambda m, n: _answer(["A", "B"])), **MAPS, mode="collect")
    eng.fit(store, Mask.empty())
    eng.rank(_req(("A", "B")))
    text = eng.collected[0]["messages"][1]["content"]
    assert "EVIDENCE CARDS" not in text and "PASSAGES" not in text and "Mulching" in text and "Wet Dega" in text
    sh = M2Engine("m2_zero", FakeClient(lambda m, n: _answer(["A", "B"])), **MAPS, mode="collect", shuffle_seed=1)
    sh.fit(store, Mask.empty())
    b = sh.build(_req(("A", "B")))
    assert b.candidates == ["B", "A"]
    assert pm.PROMPT_VERSION == "m2-p1" and len(pm.prompt_hash()) == 64


# ----------------------------------------------------------------- report measures
def test_kendall_tau_and_citation_validity():
    from model.m2.report import citation_validity, kendall_tau

    assert kendall_tau(["A", "B", "C"], ["A", "B", "C"]) == 1.0 and kendall_tau(["A", "B", "C"], ["C", "B", "A"]) == -1.0
    assert kendall_tau(["A", "B", "C"], ["B", "A", "C"]) == pytest.approx(1 / 3)
    entries = [{"valid": True, "prompt_card_ids": ["c1", "c2", "c3"],
                "card_practice": {"c1": {"practice_id": "A", "related_for": []}, "c2": {"practice_id": "B", "related_for": []},
                                  "c3": {"practice_id": "A", "related_for": ["X"]}},
                "items": {"A": {"card_ids": ["c1", "c2"]}, "B": {"card_ids": []}, "X": {"card_ids": ["c3"]}},
                "attempts": [{"invented_ids": 2}, {"invented_ids": 0}]}]
    c = citation_validity(entries)
    assert c["items"] == 3 and c["items_with_citation"] == pytest.approx(2 / 3) and c["cited_ids"] == 3
    assert c["cited_matching"] == pytest.approx(2 / 3) and c["cited_outside_prompt"] == 0 and c["invented_in_first_answers"] == 2


def test_ledger_sums_every_process_file_and_skips_an_unfinished_line(tmp_path):
    a = Ledger(tmp_path / "ledger.jsonl")
    a.settle(0.0, {"cost_usd": 0.25})
    (tmp_path / "ledger.99999.jsonl").write_text('{"cost_usd": 0.5}\n{"cost_usd": 0.', encoding="utf-8")  # another process mid-write
    assert a.own.name.startswith("ledger.") and a.total() == pytest.approx(0.75)
    with pytest.raises(BudgetExceeded):
        a.reserve(0.3, budget=1.0)


def test_passage_cache_replays_the_stored_order(tmp_path):
    class Flip:
        unmaskable: dict = {}

        def __init__(self):
            self.n = 0

        def retrieve(self, q, k=2, mask=None):
            self.n += 1
            hits = [{"chunk_id": "a", "text": "x", "tier": "evidence"}, {"chunk_id": "b", "text": "y", "tier": "guidelines"}]
            return hits if self.n % 2 else hits[::-1]  # a tie that flips between calls

    r = Flip()
    first = PassageSource(r, cache_dir=tmp_path).for_candidates({"A": "q"}, Mask.empty())
    again = PassageSource(r, cache_dir=tmp_path).for_candidates({"A": "q"}, Mask.empty())
    assert [h["chunk_id"] for h in first] == [h["chunk_id"] for h in again] == ["a", "b"] and r.n == 1
