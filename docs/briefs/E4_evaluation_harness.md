# E4: evaluation harness, one protocol for every method (11 Nov 2026)

**Binding:** `docs/roadmap/AE+_enhancement_roadmap.md` sections 8 to 11 and Appendix B, `docs/decisions/enhancement_v2.md`, `docs/decisions/evidence_fusion.md`, `model/evaluate.py` (the P7 protocol, wrapped, never forked), CLAUDE.md, the E1 to E3 reports in `progress.md`, this brief. E4 starts after E3 is approved: it reads the `ctx_*` columns that `add_context.py` writes into the evidence store from release `ET/2026.1`.

**Purpose.** Build the single evaluation harness that will decide between Methodology 1 (evidence model plus retrieval), Methodology 2 (LLM evidence reasoning) and their hybrid, and that the manuscript will report. One query set, one set of deterministic folds, one masking mechanism, one metric library, one prediction format, one report generator. E4 also runs the baselines so E5 and E6 have numbers to beat. No new model is trained in this phase beyond refitting the current one inside the folds.

**Ground rules:** as E1 to E3 (production grade, additive, deterministic, nothing dropped silently, tests for every module), plus:

- **No leakage, by construction.** A held-out study is invisible to every method through every channel: training rows, retrieval chunks, graph edges, evidence cards, prompts. Masking is enforced in one place and tested with a canary.
- **Same queries for every method.** A method that cannot answer a query abstains; it never gets a different query set.
- **Reproducible to the third decimal.** Two runs on the same machine give identical metrics; fold files and configurations are hashed into every report.
- Commit messages, if the owner asks for any, are short and plain with no attribution lines.
- Report as an **E4 block in `progress.md`**, then stop. The owner commits.

**Do not regress:** `python model/evaluate.py` (the P7 protocol and its 68-cell numbers), all test suites, the running app.

---

## Part 0: carry-overs (do first)

1. `rag/graph/test_glossary_sync.py` fails on HEAD (`glossary.ts` against `practice_components.py`). Find which side is stale, fix it, and say which in the report.
2. `rag/ingest/ingest_guidelines.py` silently recorded 170 page errors when Pillow was missing. Pin `pillow` in `pipelines/requirements.txt` (the owner added a line; check it) and make the OCR step raise on the first rendering error that is not page-specific.
3. **Cross-source duplicates.** 40 DOIs occur in more than one source (ERA, CSA, HAB). Add `pipelines/evidence/dedupe.py`: identify rows that report the same contrast in two sources (same DOI, same practice id, same outcome id, means within 1% or LRR within 0.01), keep the row with the richer record (dispersion, coordinates) and flag the other `extra.dup_of`; report counts per source pair in the cards. The harness uses the DOI, not the source study id, as the grouping key (Part B).
4. **WhiteboxTools flake** (E3: FillDepressions panicked in 2 of 15 unit runs with "Error unwrapping 'output'"). Run WhiteboxTools work in a folder under `pipelines/geodata/cache/_work/` rather than the user temp folder (Windows Defender and the indexer lock fresh files there), and allow exactly one retry for that specific panic, logged as a warning and counted in the manifest. Any other WhiteboxTools error still fails at once. Run the geodata unit suite 20 times and report the pass count.
5. **`train_model.py` report path.** The report `docs/reports/model_evaluation_report.md` is written only by a full run that also writes the canonical artifacts; `--quick` and runs with `--artifacts` elsewhere write their report next to their artifacts.
6. Git-ignore `model/artifacts/release_check/` (reproducible).

## Part 1: queries (`model/harness/queries.py`)

**1.1 Definition.** A query is one cell of the evidence store keyed by `(group, site, outcome_id, crop, comparator_class)`, where `group` is the normalised DOI when present and the source `study_id` otherwise; `site` is the rounded coordinate pair (3 decimals) or the site name when coordinates are missing; `comparator_class` is a small normalised vocabulary (`no_practice`, `farmer_practice`, `conventional_tillage`, `mineral_fertilizer_only`, `other`) derived from `comparator` text by rules (document them; report counts with and without the comparator key). Rows qualify when `lrr` is computable, `direction_reviewed` is true, `practice_id` and `outcome_id` are set, the row is not a `dup_of`, and `loc_method` is not `geocoded_llm_unchecked`.

**1.2 Ground truth.** Within a query, rows of the same practice are pooled to one observed effect: inverse-variance mean of `lrr` where `var_lrr` exists for all of them, else the weighted mean with the store `weight`. The effect is oriented by `direction` (higher is better after orientation). Queries need at least 2 practices for the pairwise metrics and at least 3 for the list metrics; both counts are reported.

**1.3 Inputs a method receives.** The query context (`ctx_*` from release `ET/2026.1` for site and district precision; the reported context fields for country precision), the challenge ids that the outcome belongs to (from `challenges.csv`), the objective `outcome_id`, the candidate practice ids (the practices observed in the query, in a random order fixed by seed), and the crop. Nothing else from the query's rows.

**1.4 Query sets.** `ET` (headline), `global` (non-ET, secondary, mainly Habtamu), `post_2024` (studies published in 2024 or later, the memorisation check for Methodology 2), and `legacy_68` (the 68 cells of the P7 protocol, for continuity). Expected from the 10 Nov store (the report gives the actual): about 362 Ethiopian queries with at least 2 practices and 199 with at least 3 (against 68 today), by objective group roughly productivity 170, economics 80, soil health 37, water 40, livestock 31. `queries.parquet` and `queries_card.md` (counts per objective, challenge, belt, source, precision) are written under `data/evidence/harness/`.

## Part 2: folds (`model/harness/folds.py`)

- **Study-grouped:** every query of one `group` is in one fold.
- **Spatial blocks:** queries are assigned to blocks of 1 degree by 1 degree (about 110 km) from their coordinates (country-precision queries form their own block per country); whole blocks are held out. Blocks are assigned to 5 folds by a greedy balance on query count, with 5 repetitions under different seeds (5 x 5).
- A group that spans two blocks takes the block of most of its queries; the report lists such groups.
- Fold files `data/evidence/harness/folds_spatial.csv` and `folds_study.csv` with a manifest (`seed`, `n_reps`, `n_folds`, sha256 of the query file). Reading folds goes through one function, as `assign_folds.load_folds` does today.

## Part 3: masking (`model/harness/mask.py`)

A `Mask` object built from the held-out groups of a fold holds the set of DOIs, study ids and `era_code`s to hide. It is passed to every engine and enforced by:

- **training rows:** `mask.filter_rows(df)`;
- **retrieval:** a metadata filter in `rag/retrieve.py` (`where` clause on `doi`, `era_code`, `study_id`) applied to Tier 1, Tier 2 and the guidelines collection; chunks without study metadata are never masked and are reported;
- **graph:** `rag/graph/query.py` functions accept a mask and drop `REPORTS_EFFECT` edges and `Study` nodes of masked groups;
- **evidence cards (E6):** the card builder takes the mask.

**Tier 1 re-index.** Re-index Tier 1 now with the open-access Habtamu papers added in E2, so every chunk carries `doi`, `study_ids` (list) and `source`; the evaluation baseline is defined on this index. Record the index hash in every report.

**Canary test (mandatory).** For a random held-out group, insert a synthetic chunk containing a unique token and its DOI into a temporary collection, run retrieval with the fold's mask for a query built from that token, and assert the chunk never appears; the same for a graph edge and a training row. Run it for every fold in CI on a fixture index.

## Part 4: engine interface and baselines (`model/engines/`)

```python
@dataclass
class RankRequest:
    query_id: str; context: dict; challenge_ids: list[str]; outcome_id: str
    candidates: list[str]; crop: str | None; user_attrs: dict; mask: Mask

@dataclass
class RankedItem:
    practice_id: str; score: float; est_lrr: float | None; lo: float | None; hi: float | None
    abstain: bool; lead_source: str; citations: list[str]

class Engine(Protocol):
    name: str
    def fit(self, train_rows: pd.DataFrame, mask: Mask) -> None: ...
    def rank(self, req: RankRequest) -> list[RankedItem]: ...
```

Baselines in this phase:

- `random` (seeded; its expected metrics are also computed analytically and must agree);
- `practice_prior`: mean oriented LRR per practice and outcome group in the training rows (with a family fallback);
- `nearest_studies`: inverse-variance pooled LRR of the k nearest training queries in standardised context space (k = 10; the context vector is the release layers used by the current model plus the new ones; distance weights documented);
- `m0_current`: the current HistGBM refitted per fold on the training rows through the existing `train_model` / `evaluate` code paths (wrap, never fork), restricted to the 7 legacy indicators where its features exist; it abstains on other outcomes.

## Part 5: metrics and reports (`model/metrics.py`, `model/harness/report.py`)

- Implement roadmap Appendix B exactly: top-1 hit with chance, top-half hit, C-index (ties count half), NDCG@3, median Spearman, RMSE and sign accuracy of LRR, 80% interval coverage and width, abstention rate and conditional accuracy. Unit tests with hand-computed fixtures for every metric.
- Uncertainty: mean and sd across the 5 x 5 repetitions, plus a query-level bootstrap 95% interval (1,000 resamples, seeded).
- Breakdowns: per objective group, per challenge, per belt (as an attribute only), per source, per location precision, ET versus global, and `post_2024`. Any cell with fewer than 20 queries is shown as "n < 20" and never as a number.
- **Prediction format:** one parquet per run `model/harness/runs/<run_id>/predictions.parquet` with `run_id, method, split, fold, rep, query_id, practice_id, score, est_lrr, lo, hi, abstain, lead_source, citations`; `metrics.json`; `config.json` (method parameters, fold and query hashes, index hash, release id, git commit).
- **Report:** `model/reports/eval_<date>_<run_id>.md` with the headline table (methods by metrics, spatial and study splits), the breakdowns, a coverage-accuracy curve and a calibration plot (PNG, matplotlib), and a short "how to read this" paragraph in plain words. The same numbers go to `metrics.json` so the Methodology page can render them later.
- CLI: `python -m model.harness.run --methods random,practice_prior,nearest_studies,m0_current --split spatial,study --reps 5`.

## Part 6: continuity with P7

Run `m0_current` on `legacy_68` with the P7 grouped folds and confirm the P7 ranking metrics (top-1 52%, C-index 0.70, median Spearman 0.51) within one sd. If they differ, explain why before going further.

**Release switch check (E3 carry-over).** With the full P7 protocol (10 x 5), compare the current model on the legacy stack and on release `ET/2026.1` (`train_model.py --release ET/2026.1`, artifacts outside the canonical folder). The backend switch to `GEODATA_RELEASE=ET/2026.1` is recommended in the report only if every ranking metric moves by less than one sd; otherwise the report explains which feature moved and why.

---

## Acceptance

1. Part 0 done: glossary test green with the stale side named; OCR fails loudly; cross-source duplicates flagged with counts; the geodata unit suite passes 20 of 20 runs (retries reported); `train_model.py` no longer overwrites the canonical report from quick or redirected runs; `release_check/` ignored.
2. `queries.parquet` and the query card written; counts reported for every query set and objective group, with and without the comparator key.
3. Deterministic folds: two builds give identical files (hash match); spatial blocks and study groups never split across folds.
4. Masking canary passes for every fold on the fixture index and on the real index for one fold; chunks without study metadata are counted and listed.
5. Tier 1 re-indexed with the Habtamu papers; index hash recorded.
6. Baselines run end to end on both splits; report and `metrics.json` produced; two runs give identical metrics to the third decimal.
7. `m0_current` reproduces the P7 numbers on `legacy_68` within one sd; the full-protocol release switch check is reported with a clear recommendation.
8. All tests pass; nothing committed.
