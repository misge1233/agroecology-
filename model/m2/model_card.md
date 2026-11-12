# Model card: Methodology 2, LLM evidence reasoning (`m2_*`)

Built in phase E6 (12 Nov 2026) by `model/m2/`. Evaluation only: Methodology 2 lives in the
harness and has no serving path; serving waits for the E7 decision. Results are in
`model/reports/eval_2026-11-12_m2.md` and the E6 block of `progress.md`.

## What it does

For one harness query (a site's context, one objective outcome with its direction, the crop and
the candidate practices) a language model ranks every candidate and, for each, gives an effect
class (`large_benefit`, `benefit`, `neutral`, `harm`, `unknown`), a confidence and the ids of the
evidence cards it relies on. **The model never produces a number shown to anyone**
(doctrine 1): the harness score is the rank position, and the effect estimate with its 80 %
interval is computed by code from the cited cards of that practice (random-effects pooling with
the context-distance decay of `model/m1/matched.py`); without a cited card of the practice the
estimate is null. The free-text `reason` is logged for audit and never read by code.
`effect_class = unknown` abstains the candidate; two invalid answers abstain the query.

## Variants (pre-registered in the E6 brief)

| variant | evidence in the prompt |
|---|---|
| `m2_zero` | context, objective and candidate names only (what the model already knows) |
| `m2_cards` | plus evidence cards |
| `m2_rag` | plus retrieved passages (Tier 1, Tier 2, guidelines) |
| `m2_graph` | plus graph facts (the full Methodology 2 of the roadmap) |

## Data sent to the API, and the owner's decision

The owner decided on 12 Nov 2026, after confirming with the data holder, that evidence cards from
**all sources, including Habtamu's database**, may be sent to the OpenAI API (recorded as an
addendum to `docs/decisions/enhancement_v2.md`). Per query the request holds:

- the query context in words and numbers (belt, rainfall, altitude, slope, clay, sand, aridity,
  temperature, growing period), the objective and its direction, the crop, candidate ids and names;
- up to 4 evidence cards per candidate and 32 per prompt. A card is one pooled contrast per study
  cell (study, site, practice, outcome, crop, comparator class): the oriented effect as a rounded
  percent change, rows, a precision class, the site context, country, year, quality flag, a short
  citation (first author and year) and the DOI. Cards are built only from rows the fold's mask
  allows: a held-out study can never reach a prompt (canary tests in `model/m2/test_m2.py`);
- up to 2 passages per candidate and 4 per prompt, trimmed to 120 tokens, with tier and citation
  (masked retrieval);
- graph facts per candidate (components, challenges addressed, the catalogue entry's land use,
  suitable belts, scale and limitations), at most 60 tokens, from the masked graph view.

No partner file is sent whole. Query embeddings for retrieval (`text-embedding-3-small`) are sent
for the query text only.

## Models and settings

- `gpt-4o-mini` for every variant (the serving model), temperature 0, seed 0, structured output
  (strict JSON schema with the candidate ids as an enum; card ids free text so invented ids stay
  measurable).
- **Owner decision (12 Nov 2026): Methodology 2 is evaluated with deployable, low-cost models
  only.** `gpt-4.1-mini` is the stronger model of E6, run on `m2_zero` and `m2_graph` (the
  reviewer's addition: does the evidence effect seen with `gpt-4o-mini` hold with a stronger
  model?), same prompts, temperature 0, seed 0. Frontier models (`gpt-4.1`, `o3`, `gpt-5` class)
  are out of scope for cost. The project key lists `gpt-4o-mini`, `gpt-4.1-mini` and
  `text-embedding-3-small` only.
- The exact model id returned by the API, the system fingerprint, the date, usage and latency are
  stored with every cached answer.

## Prompt

`model/m2/prompt.py`, version `m2-p1`; its hash goes into every run's `config.json`. A fixed
system message (role, six rules: rank every candidate once, judge from the evidence and prefer
similar contexts, say `unknown` rather than guess, cite only shown card ids, confidence 0 to 1,
reason at most 30 words with no numbers) and a user message with the context, objective, crop,
candidates, cards by candidate, passages and graph facts. One retry with the validation error
appended.

## Cost controls

Every answer is cached in `model/m2/cache/` (git-ignored) by model, prompt version and request
hash; reruns cost nothing. Every paid request is written to `model/m2/cache/ledger.jsonl`; a
`--budget-usd` cap (100 USD for the phase) refuses a request whose worst-case cost would exceed
the cap before sending it. `python -m model.m2.run --dry-run` prints calls, tokens and the
estimated cost per variant and model from `model/m2/prices.yaml` (the owner checks the prices).

## Limitations

- The model may know published studies from its training data: `m2_zero` measures that, and the
  `post_2024` queries are reported with their size, not interpreted.
- Card-derived intervals pool few cards and are not calibrated (reported, not fixed in E6).
- Answers are deterministic only as far as the API is (temperature 0 and a seed); the stability
  check measures repeat and order effects.
- The evaluation uses the spatial split, repetition 0 only (owner's minimal design): the
  uncertainty reported is across the 375 queries, not across fold assignments.

## Intended use

Research comparison with Methodology 1 in E7. Not a serving component.
