"""The Methodology 2 harness engine (E6 Parts 3 and 4).

:meth:`M2Engine.fit` prepares the fold's masked evidence (cards from ``mask.filter_rows``,
the masked graph view; passages are retrieved with the mask at rank time).
:meth:`M2Engine.rank` builds the prompt of a query, asks the model (through the cached,
capped :class:`~model.m2.client.ChatClient`), validates the answer (one retry with the
validation error appended; a second failure abstains the query, counted) and scores it:

* ``score`` from the rank position (best = number of candidates);
* ``est_lrr`` and the 80 % interval computed by code from the cited cards **of that
  practice** (random-effects pooling with the distance decay of :mod:`model.m1.matched`),
  null when none is cited; the model's ``reason`` text is never read by code;
* ``effect_class = unknown`` abstains that candidate;
* ``lead_source = llm_evidence``; ``citations`` = the study ids of the cited cards.

Variants (pre-registered): ``m2_zero`` (context, objective and candidate names only),
``m2_cards`` (plus evidence cards), ``m2_rag`` (plus passages), ``m2_graph`` (plus graph
facts). ``mode="collect"`` builds and records prompts without calling (dry run, prefetch).
"""
from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass, field
from typing import Any, Mapping

import numpy as np
import pandas as pd

from model.engines.base import Z80, RankedItem, RankRequest, abstain_all
from model.harness.mask import Mask
from model.m1.matched import dersimonian_laird
from model.m2 import prompt as pm
from model.m2.cards import Card, CardStore, _num, context_words
from model.m2.knowledge import GraphFacts, PassageSource, passage_query

VARIANTS = ("m2_zero", "m2_cards", "m2_rag", "m2_graph", "m2_names", "m2_swap")
#: E7 Part A validity variants (no evidence, like m2_zero): ``m2_names`` hides the site context and
#: the crop ("not given"); ``m2_swap`` shows the context of the most dissimilar query of the same
#: objective group (``context_override``) with the query's own crop
NO_EVIDENCE = ("m2_zero", "m2_names", "m2_swap")
NOT_GIVEN = "not given"
SERVING_MODEL = "gpt-4o-mini"
LEAD = "llm_evidence"


def method_name(variant: str, model: str) -> str:
    return variant if model == SERVING_MODEL else f"{variant}__{model}"


@dataclass
class Built:
    """One query's prompt and everything needed to score its answer."""

    query_id: str
    candidates: list[str]           # in prompt order
    user: str
    schema: dict[str, Any]
    shown: dict[str, list[Card]]    # cards per candidate as shown (related flag set)
    passages: list[dict[str, Any]] = field(default_factory=list)
    facts: dict[str, str] = field(default_factory=dict)

    @property
    def card_ids(self) -> set[str]:
        return {c.card_id for v in self.shown.values() for c in v}

    def messages(self) -> list[dict[str, str]]:
        return pm.messages(self.user)


class M2Engine:
    def __init__(self, variant: str, client: Any, outcome_group: Mapping[str, str], practice_name: Mapping[str, str],
                 outcome_name: Mapping[str, str], outcome_direction: Mapping[str, int],
                 components_of: Mapping[str, list[str]], belt_name_of: Mapping[int, str] | None = None,
                 passages: PassageSource | None = None, graph: GraphFacts | None = None, mode: str = "call",
                 shuffle_seed: int | None = None, repeat: str | None = None, name: str | None = None,
                 context_override: Mapping[str, Mapping[str, Any]] | None = None) -> None:
        if variant not in VARIANTS:
            raise KeyError(f"unknown M2 variant {variant!r}; known: {VARIANTS}")
        self.variant = variant
        self.client = client
        self.model = getattr(client, "model", SERVING_MODEL)
        self.name = name or method_name(variant, self.model)
        self.outcome_group = dict(outcome_group)
        self.practice_name = dict(practice_name)
        self.outcome_name = dict(outcome_name)
        self.cards = CardStore(outcome_group, practice_name, outcome_name, outcome_direction, components_of, belt_name_of)
        self.use_cards = variant not in NO_EVIDENCE
        if variant == "m2_swap" and context_override is None:
            raise ValueError("m2_swap needs the swapped contexts (context_override)")
        self.context_override = {str(k): dict(v) for k, v in (context_override or {}).items()}
        self.use_passages = variant in ("m2_rag", "m2_graph")
        self.use_graph = variant == "m2_graph"
        if self.use_passages and passages is None:
            raise ValueError(f"{variant} needs a PassageSource")
        if self.use_graph and graph is None:
            raise ValueError(f"{variant} needs GraphFacts")
        self.passages = passages
        self.graph = graph
        self.mode = mode
        self.shuffle_seed = shuffle_seed
        self.repeat = repeat
        self.mask = Mask.empty()
        self.fold_tag: dict[str, Any] = {}
        self.collected: list[dict[str, Any]] = []
        self.log: list[dict[str, Any]] = []
        self.n_abstained_invalid = 0

    # ------------------------------------------------------------ fit
    def fit(self, train_rows: pd.DataFrame, mask: Mask) -> None:
        self.mask = mask
        import hashlib

        self.fold_tag = {"mask_hash": hashlib.sha256(mask.to_json().encode("utf-8")).hexdigest()[:12]}
        if self.use_cards:
            self.cards.fit(train_rows, mask)
        if self.use_graph:
            assert self.graph is not None
            self.graph.fit(mask)

    @property
    def unmaskable(self) -> dict[str, int]:
        return self.passages.unmaskable if self.passages is not None else {}

    # ------------------------------------------------------------ prompt
    def context_text(self, ctx: Mapping[str, Any]) -> str:
        words = context_words(ctx, self.cards.belt_name(ctx))
        extra = []
        t = _num(ctx.get("ctx_temp_mean_annual", ctx.get("temp_mean_annual")))
        if t is not None:
            extra.append(f"mean temperature {t:.0f} C")
        g = _num(ctx.get("ctx_lgp_days", ctx.get("lgp_days")))
        if g is not None:
            extra.append(f"growing period {g:.0f} days")
        return ", ".join([words] + extra)

    def build(self, req: RankRequest) -> Built:
        cands = list(req.candidates)
        if self.shuffle_seed is not None:
            random.Random(f"{self.shuffle_seed}:{req.query_id}").shuffle(cands)
            if cands == list(req.candidates) and len(cands) > 1:  # a shuffle always changes the order
                cands = cands[1:] + cands[:1]
        group = req.objective_group or self.outcome_group.get(req.outcome_id, "other")
        better = self.cards.better_words(req.outcome_id)
        objective = self.outcome_name.get(req.outcome_id, req.outcome_id)
        crop = req.crop
        if self.variant == "m2_names":
            ctx_text, crop = NOT_GIVEN, NOT_GIVEN
        elif self.variant == "m2_swap":
            # a query without a partner (a single-query objective group) keeps its own context
            ctx_text = self.context_text(self.context_override.get(req.query_id, req.context))
        else:
            ctx_text = self.context_text(req.context)
        shown: dict[str, list[Card]] = {c: [] for c in cands}
        if self.use_cards:
            shown = self.cards.select(req.context, cands, req.outcome_id, group)
        passages: list[dict[str, Any]] = []
        if self.use_passages:
            assert self.passages is not None
            words = context_words(req.context, self.cards.belt_name(req.context))
            qs = {c: passage_query(self.practice_name.get(c, c), objective, better, words) for c in cands}
            passages = self.passages.for_candidates(qs, req.mask)
        facts: dict[str, str] = self.graph.facts(cands) if self.use_graph and self.graph is not None else {}
        user = pm.user_message(ctx_text, objective, better, crop,
                               [(c, self.practice_name.get(c, c)) for c in cands],
                               cards={c: [k.text for k in shown[c]] for c in cands} if self.use_cards else None,
                               passages=passages if self.use_passages else None,
                               facts=facts if self.use_graph else None)
        return Built(req.query_id, cands, user, pm.response_schema(cands), shown, passages, facts)

    # ------------------------------------------------------------ rank
    def rank(self, req: RankRequest) -> list[RankedItem]:
        b = self.build(req)
        if self.mode == "collect":
            self.collected.append({"query_id": req.query_id, "messages": b.messages(), "schema": b.schema,
                                   "n_cards": len(b.card_ids), "n_passages": len(b.passages), **self.fold_tag})
            return abstain_all(req, LEAD)
        entry: dict[str, Any] = {"query_id": req.query_id, "method": self.name, "variant": self.variant, "model": self.model,
                                 "repeat": self.repeat, "shuffle_seed": self.shuffle_seed, **self.fold_tag,
                                 "candidates": b.candidates, "n_cards": len(b.card_ids), "n_passages": len(b.passages),
                                 "attempts": [], "prompt_card_ids": sorted(b.card_ids),
                                 "card_practice": self._card_practice(b), "passage_ids": [p["chunk_id"] for p in b.passages]}
        msgs = b.messages()
        answer = None
        for attempt in range(2):
            rec = self.client.chat(msgs, b.schema, repeat=self.repeat)
            parsed = rec.get("parsed")
            invented = self._invented(parsed, b.card_ids)
            entry["attempts"].append({"usage": rec.get("usage"), "latency_s": rec.get("latency_s"), "cost_usd": rec.get("cost_usd", 0.0),
                                      "from_cache": rec.get("from_cache", False), "model": rec.get("model"),
                                      "invented_ids": invented, "content": rec.get("content")})
            try:
                answer = pm.validate(parsed, b.candidates, b.card_ids)
                break
            except pm.InvalidAnswer as err:
                entry["attempts"][-1]["error"] = str(err)
                msgs = pm.messages(b.user, str(err), rec.get("content"))
        if answer is None:
            self.n_abstained_invalid += 1
            entry["valid"] = False
            self.log.append(entry)
            return abstain_all(req, LEAD)
        entry["valid"] = True
        items = self.score(req, b, answer)
        entry["items"] = {i.practice_id: {"rank": answer["ranking"].index(i.practice_id),
                                          "effect_class": answer["items"][i.practice_id]["effect_class"],
                                          "confidence": answer["items"][i.practice_id].get("confidence"),
                                          "card_ids": list(answer["items"][i.practice_id].get("card_ids") or []),
                                          "reason": answer["items"][i.practice_id].get("reason")} for i in items}
        self.log.append(entry)
        return items

    @staticmethod
    def _card_practice(b: Built) -> dict[str, dict[str, Any]]:
        """Per shown card: its practice and the candidates it was shown under as a related practice."""
        out: dict[str, dict[str, Any]] = {}
        for cand, cards in b.shown.items():
            for c in cards:
                e = out.setdefault(c.card_id, {"practice_id": c.practice_id, "related_for": []})
                if c.related:
                    e["related_for"].append(cand)
        return out

    @staticmethod
    def _invented(parsed: Any, shown: set[str]) -> int:
        if not isinstance(parsed, dict):
            return 0
        n = 0
        for it in parsed.get("items") or []:
            if isinstance(it, dict):
                n += sum(1 for c in it.get("card_ids") or [] if c not in shown)
        return n

    # ------------------------------------------------------------ scoring (code, never the model's numbers)
    def score(self, req: RankRequest, b: Built, answer: dict[str, Any]) -> list[RankedItem]:
        n = len(b.candidates)
        pos = {pid: i for i, pid in enumerate(answer["ranking"])}
        shown_by_id = {c.card_id: c for v in b.shown.values() for c in v}
        out = []
        for pid in req.candidates:  # request order, as every engine
            it = answer["items"][pid]
            cited = [shown_by_id[c] for c in it.get("card_ids") or [] if c in shown_by_id]
            # own evidence = cited cards of this practice (a card can also be shown as "related"
            # under another candidate that shares the component; it stays own evidence here)
            own = [c for c in cited if c.practice_id == pid]
            est, lo, hi = self.estimate(req.context, own)
            out.append(RankedItem(pid, float(n - pos[pid]), est, lo, hi, it["effect_class"] == "unknown", LEAD,
                                  sorted({s for c in cited for s in c.study_ids})))
        return out

    def estimate(self, context: Mapping[str, Any], cards: list[Card]) -> tuple[float | None, float | None, float | None]:
        """Random-effects pooled oriented effect of the cited cards with the matched-studies
        distance decay ``1 / (1 + d^2)``; ``(None, None, None)`` without cards."""
        if not cards:
            return None, None, None
        y = np.array([c.y for c in cards], float)
        default_var = self.cards.space.default_var if self.cards.space is not None else 1.0
        v = np.array([c.var if np.isfinite(c.var) and c.var > 0 else default_var for c in cards], float)
        decay = np.ones(len(cards))
        if self.cards.space is not None and not self.cards.items.empty:
            idx = {c.card_id: i for i, c in enumerate(self.cards.cards)}
            sel = np.array([idx[c.card_id] for c in cards])
            d = self.cards.space._distances(dict(context), sel)
            decay = np.where(np.isfinite(d), 1.0 / (1.0 + d ** 2), 1.0)
        est, se, _ = dersimonian_laird(y, v, decay)
        if not (math.isfinite(est) and math.isfinite(se)):
            return None, None, None
        return float(est), float(est - Z80 * se), float(est + Z80 * se)

    # ------------------------------------------------------------ harness
    def params(self) -> dict[str, Any]:
        from model.m2.cards import MAX_CARDS, PER_CANDIDATE
        from model.m2.knowledge import FACT_TOKENS, MAX_PASSAGES, PASSAGE_TOKENS, PASSAGES_PER_CANDIDATE

        return {"variant": self.variant, "model": self.model, "prompt_version": pm.PROMPT_VERSION, "prompt_hash": pm.prompt_hash(),
                "sampling": self.client.params() if hasattr(self.client, "params") else None,
                "reasoning_model": getattr(self.client, "reasoning", None),
                "limits": {"cards_per_candidate": PER_CANDIDATE, "cards_per_prompt": MAX_CARDS,
                           "passages_per_candidate": PASSAGES_PER_CANDIDATE, "passages_per_prompt": MAX_PASSAGES,
                           "passage_tokens": PASSAGE_TOKENS, "fact_tokens": FACT_TOKENS},
                "evidence": {"cards": self.use_cards, "passages": self.use_passages, "graph": self.use_graph},
                "context": ("hidden (not given), crop hidden" if self.variant == "m2_names" else
                            "swapped: most dissimilar query of the same objective group" if self.variant == "m2_swap" else "own"),
                "shuffle_seed": self.shuffle_seed, "repeat": self.repeat,
                "abstained_invalid": self.n_abstained_invalid,
                "client_stats": dict(getattr(self.client, "stats", {}))}


def log_lines(entries: list[dict[str, Any]]) -> str:
    return "".join(json.dumps(e, default=str) + "\n" for e in entries)
