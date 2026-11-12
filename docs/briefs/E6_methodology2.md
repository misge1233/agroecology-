# E6: Methodology 2, LLM evidence reasoning (with the E5.1 follow-up first) (12 Nov 2026)

**Binding:** `docs/roadmap/AE+_enhancement_roadmap.md` sections 9 to 11 and Appendix B; `docs/decisions/enhancement_v2.md`; `docs/decisions/evidence_fusion.md` (numbers come from evidence, never from the LLM); the harness of E4 with the E5 scorings; CLAUDE.md; the E5 report and review in `progress.md`; this brief.

**Purpose.** Part 0 runs one pre-registered follow-up of Methodology 1 (E5.1). Parts 1 to 6 build Methodology 2: an engine that ranks the candidate practices of a query by asking a language model to reason over the same evidence Methodology 1 learns from, presented as short evidence cards, with passages and graph facts in the richer variants. It is scored on the same queries, folds and masks as every other method, so E7 can compare the two methodologies and decide the production design.

**Owner decisions (12 Nov 2026).** (1) Evidence cards from **all sources, including Habtamu's database**, may be sent to the OpenAI API (the owner confirmed with the data holder); record this in `docs/decisions/enhancement_v2.md` as an addendum with the date and in the M2 model card. (2) Models: the serving model `gpt-4o-mini` for every variant, plus **one stronger model** on the owner's key for the full variant only (Part 5).

**Ground rules:** as E1 to E5, plus:

- **The LLM never produces a number shown to anyone.** It ranks and cites card ids; every effect estimate and interval is computed by code from the cited cards (doctrine 1, numeric guard).
- **Masked like everything else.** Cards, passages and graph facts for a query come only from data that the fold's `Mask` allows. A test proves a held-out study's card can never reach a prompt.
- **Every paid call is cached, counted and capped.** A dry run prints the token and cost estimate per variant and model; a `--budget-usd` cap stops the run before it is exceeded; reruns of cached prompts cost nothing.
- **Pre-registration.** The variants, models, prompts and the E5.1 change are fixed in this brief before any result; results are reported whatever they are.
- Long runs: one variant per process (the E5 native crash).
- Commit messages, if the owner asks for any, are short and plain with no attribution lines.
- Report as an **E6 block in `progress.md`** (with E5.1 as its first section), then stop. The owner commits.

---

## Part 0: E5.1, one pre-registered follow-up of Methodology 1

Fixed now, before any run: two changes, evaluated once.

1. **Stacker candidates.** The inner-fold selection chooses among: ridge, rank averaging over four components (E5), rank averaging over ranker, regressor and prior (matched studies left out), and ranker-weighted rank averaging with ranker weight 2 or 3 over the same three components. The inner selection score is the mean of inner top-1 hit and inner C-index (both ranks, not RMSE). The served choice follows the E5 majority-of-folds rule.
2. **Group-conditional conformal.** The 80% quantile is taken per objective group (Mondrian conformal) when the group has at least 30 inner residuals, else the pooled quantile.

Run `m1_v2_e51` on the ET set, both splits, 5 x 5, one variant per process. Report it beside `m1_v2` (E5), `m0_current+prior` and `practice_prior` with full coverage, common subset and paired bootstrap differences, plus calibration per objective group. Label it in every table as **"E5.1, post-hoc, pre-registered 12 Nov 2026"**. Whatever the result, no further Methodology 1 variants are run before E7. If E5.1 improves the full-coverage spatial top-1 or C-index over E5 with a paired interval excluding zero, rebuild `model/artifacts/m1_v2/` with it (keep the E5 artifact as `m1_v2_e5/`); otherwise keep E5.

## Part 1: evidence cards (`model/m2/cards.py`)

- A **card** is one pooled contrast per `(group, site, practice_id, outcome_id, crop, comparator_class)` from the rows a fold allows, with: `card_id` (stable short hash), practice name, outcome name and what "better" means in words, oriented effect as a rounded percent change (`exp(y) - 1`), number of rows, a precision class (high, medium, low from `var_lrr` or the weight), site context in words and numbers (belt name, rainfall mm, altitude m, slope %, soil clay and sand %, aridity), country, year, quality flag, short citation and DOI. Rendered by a fixed template, about 60 to 80 tokens. Card metadata carries `doi`, `study_ids`, `practice_id`, `outcome_id`, `objective_group`, coordinates.
- **Selection per query** (structured, not embedding search): for each candidate, cards of the same practice and outcome first, then the same practice and objective group, ordered by context distance in the standardised space of `m1/matched.py`; up to 6 per candidate; if a candidate has fewer than 2, add up to 2 cards of practices sharing its main component, flagged "related practice". A total cap of 48 cards per prompt; candidates are never dropped, only their card count shrinks.
- All selection passes through `mask.filter_rows` first. A test builds a fold with a canary study and asserts its cards are never selected.

## Part 2: knowledge context

- **Passages** (variants `rag` and `graph`): the masked `TieredRetriever` over Tier 1, Tier 2 and the guidelines with a query built from the practice, the objective and the context in words; at most 2 passages per candidate, at most 8 per prompt, each trimmed to 120 tokens, with its tier and citation.
- **Graph facts** (variant `graph`): from the masked graph view, per candidate: its components, the challenges it addresses, the catalogue entry's suitable land use and agroecology text, the scale and limitations fields; at most 60 tokens per candidate.

## Part 3: prompt, output and scoring (`model/m2/prompt.py`, `engine.py`)

- **Prompt.** A fixed system message: the role (agronomist ranking practices for a specific farm context from the evidence given), the rules (rank every candidate id exactly once; judge from the cards and passages; prefer evidence from similar contexts; say `unknown` rather than guess; never invent card ids; no numbers in the reason). The user message: the context in words and numbers, the objective and its direction, the crop, the candidate ids with names, then the cards grouped by candidate, then passages and graph facts when the variant includes them. Prompt text and a version number live in one file; the version and its hash go into every run's `config.json`.
- **Output.** JSON with a schema enforced through the API's structured output when the model supports it, else JSON mode plus validation: `{"ranking": [ids], "items": [{"id", "effect_class": "large_benefit|benefit|neutral|harm|unknown", "confidence": 0..1, "card_ids": [...], "reason": "<= 30 words"}]}`. Validation: the ranking is a permutation of the candidates; every cited card id was in the prompt. One retry with the validation error appended; a second failure makes the query abstained (counted).
- **Scoring for the harness.** `score` from the rank position; `est_lrr` and the 80% interval computed by code from the cited cards of that practice (random-effects pooling as in `m1/matched.py`), null when no card is cited; `effect_class = unknown` makes that candidate abstained; `lead_source = llm_evidence`; `citations` = the study ids of the cited cards.
- **Determinism.** Temperature 0 where the model supports it (reasoning models do not; record that), a fixed seed parameter when available, the exact model id and the API date recorded.

## Part 4: variants (pre-registered)

| variant | evidence in the prompt |
|---|---|
| `m2_zero` | context, objective, candidate names only (what the model already knows) |
| `m2_cards` | plus evidence cards |
| `m2_rag` | plus passages |
| `m2_graph` | plus graph facts (the full Methodology 2 of the roadmap) |

All four with `gpt-4o-mini`. The stronger model (Part 5) runs `m2_graph` only.

## Part 5: runs, budget and the stronger model

- **Minimal sufficient design (owner request, 12 Nov 2026: smallest evaluation that still decides).** Methodology 2 trains nothing, so repetitions only change which other studies are masked; the uncertainty that matters is across queries, and every one of the 375 ET queries is kept. Therefore: **spatial split, repetition 0 only, all 375 ET queries, one call per query per variant** (about 375 calls per variant instead of 2,250); no study split for M2; the global set (39 queries) once for `m2_graph` with `gpt-4o-mini`. Every comparison with M1 v2 and the baselines uses their predictions on the same repetition-0 spatial folds, paired query by query.
- Prompt size: at most 4 cards per candidate, 32 per prompt, 4 passages per prompt (about 3,000 input tokens).
- **Dry run first:** `python -m model.m2.run --dry-run` builds every prompt, counts tokens (`tiktoken`), and prints calls, input and output tokens and the estimated cost per variant and model from a price table in `model/m2/prices.yaml` (the owner checks the prices). Expected order of magnitude: about 1,700 `gpt-4o-mini` calls in total (four variants, the global set and the stability check) and 375 calls for the stronger model.
- **Stronger model:** list the models available on the key (`GET /v1/models`), propose the strongest general model available, print its estimated cost for `m2_graph`, and **wait for the owner's go** before the paid run. Default cap `--budget-usd 100` for the whole phase.
- Cache: `model/m2/cache/` (git-ignored), keyed by model, prompt version and prompt hash.

## Part 6: evaluation and checks

- **Headline:** the four variants and the stronger model against `m1_v2` (the version kept after Part 0), `m0_current+prior` and `practice_prior`, full coverage and common subset, paired bootstrap differences, all on the spatial split, repetition 0, the same 375 queries.
- **Memorisation and evidence use:** `m2_zero` against `m2_cards`; `post_2024` reported with its size and not interpreted.
- **Stability:** on 40 fixed queries (spatial, repetition 0), `m2_graph` with `gpt-4o-mini`: 2 repeated calls bypassing the cache (top-1 agreement and Kendall tau between repeats) and 2 shuffled candidate orders (same measures).
- **Citation validity:** share of cited card ids whose practice equals the ranked item (or is flagged related); share of items with at least one citation; any cited id not in the prompt (must be 0).
- **Numeric guard:** a test that no number from the model's `reason` text reaches `est_lrr`, `lo`, `hi` or any response field.
- **Cost and latency:** per variant and model, per query: tokens, USD, median and p95 latency.
- **Calibration** of the card-derived intervals (expected weak; reported, not fixed in E6).

No serving change in E6: the engine lives in the harness. Serving waits for the E7 decision.

## Report

`model/reports/eval_<date>_m2.md`, `model/m2/model_card.md` (data sent to the API and the owner's decision, models, prompts, limits), and the E6 block in `progress.md`: E5.1 first, then the M2 headline, the variant ladder, the stronger model, stability, citation validity, cost, and the open items for E7.

## Acceptance

1. E5.1 run once with the two pre-registered changes, labelled post-hoc, reported against E5; the artifact rebuilt only under the stated rule.
2. Cards, passages and graph facts are masked (canary test); the dry run gives the token and cost estimate; the budget cap works (test).
3. All four `gpt-4o-mini` variants on the spatial split, repetition 0, all 375 ET queries; the stronger model on `m2_graph` after the owner's go; full coverage, common subset and paired differences against the other methods on the same folds reported.
4. Stability, citation validity, numeric guard and cost tables reported; 0 cited ids outside the prompt.
5. Two runs from the cache give identical predictions.
6. All tests pass; nothing committed.
