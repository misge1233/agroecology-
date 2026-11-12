# model/harness: the evaluation harness (E4)

One protocol for every method (roadmap sections 11 and Appendix B, brief
`docs/briefs/E4_evaluation_harness.md`): one query set, deterministic folds, one masking
mechanism, one metric library, one prediction format, one report generator. The P7 protocol
(`model/evaluate.py`) is wrapped, never forked: `m0_current` refits the serving model through
its functions, the fold assigner of `pipelines/dataset/assign_folds.py` balances the harness
folds, and `legacy_68` reproduces the P7 cells.

## Run it

```bash
# from the repo root, backend venv
python -m model.harness.queries                 # queries.parquet, query_items.parquet, queries_card.md, queries_summary.json
python -m model.harness.folds                   # folds_spatial.csv, folds_study.csv, folds_manifest.json
python -m model.harness.folds --check           # rebuild in memory and compare hashes (determinism)
python -m model.harness.run --methods random,practice_prior,nearest_studies,m0_current --split spatial,study --reps 5
python -m model.harness.run --methods m0_current --split legacy --query-set legacy_68 --reps 10   # P7 continuity
python -m model.harness.run --compare model/harness/runs/<a> model/harness/runs/<b>              # identical to 3 decimals?
python -m model.harness.release_check --release ET/2026.1                                        # full-protocol switch check
```

Outputs: `data/evidence/harness/` (the query tables are git-ignored partner-derived rows;
the card, summary, fold files and manifest are in git), `model/harness/runs/<run_id>/`
(`predictions.parquet`, `per_query.parquet`, `metrics.json`, `config.json`, the PNG figures;
git-ignored) and `model/reports/eval_<date>_<run_id>.md` (in git).

## Pieces

| Module | What |
|---|---|
| `queries.py` | one query = one `(group, site, outcome_id, crop, comparator_class)` cell of the store; ground truth = pooled oriented `lrr` per practice; sets `ET`, `global`, `post_2024`, `legacy_68` |
| `folds.py` | study-grouped and spatial-block (1 degree) folds, 5 x 5, greedy balance, never a split group or block |
| `mask.py` | the `Mask` of a fold: DOIs, study ids, corpus codes; `filter_rows`, `blocks_chunk`, `where_clause`, `blocks_graph_study` |
| `run.py` | fit and rank per fold, write predictions, metrics, config, report |
| `report.py` | the markdown report with the headline tables, breakdowns and figures |
| `release_check.py` | the full P7 protocol on the legacy stack and on a geodata release |
| `../metrics.py` | Appendix B metrics, aggregation, bootstrap, breakdowns, curves |
| `../engines/` | `base.py` (RankRequest, RankedItem, Engine), `random_engine`, `practice_prior`, `nearest_studies`, `m0_current` |

Masking is enforced through the `Mask` object in: engine training rows (`mask.filter_rows`),
`rag.retrieve.RagRetriever.retrieve(..., mask=)` (Chroma `where` on `doi`/`era_code` plus
`blocks_chunk` on every hit, reading the `study_ids` of the re-indexed Tier 1), and
`rag.graph.query.GraphQuery.masked(mask)`. `rag/test_mask_canary.py` proves it for every fold on a
fixture index and (`-m data`) on the real index.

## Adding a method

Implement the `Engine` protocol (`fit(train_rows, mask)`, `rank(req) -> list[RankedItem]`), register
it in `model/engines/__init__.py:registry`, add its construction to `run.make_engine` if it needs
taxonomy maps, and add a unit test. The engine receives nothing from a query but its context,
challenge ids, outcome, candidates and crop; everything it learns comes from `train_rows` after
`mask.filter_rows`, and anything it retrieves must go through the masked retriever or graph view.

## E5 additions (11 Nov 2026)

- **Full coverage** is the headline: `run.py` adds `<method>+prior` for every method that abstains
  (`metrics.fill_abstentions`: the abstained queries take `practice_prior`'s ranking); `metrics.json`
  holds `full_coverage`, `common_subset` (queries every compared method answered in every repetition,
  with its size) and `paired` (query-level paired bootstrap 95 % intervals of the difference in
  top-1, C-index and NDCG@3; "beats" only when the interval excludes zero). The per-method answered
  tables stay as a secondary section of the report. `--rescore` re-scores old runs the same way.
- **Methodology 1 v2** is registered as `m1_v2` with its component and ablation variants
  (`m1_regressor`, `m1_ranker`, `m1_matched`, `m1_prior`, `m1_nobelt`, `m1_legacy11`, `m1_nohab`,
  `m1_nocountry`, `m1_wquality`, `m1_noranker`, `m1_nomatched`, `m1_rankavg`, `m1_ridge`, `m1_notune`);
  code in `model/m1/`, engine in `model/engines/m1_v2.py`, artifact by `python -m model.m1.train`.
- Retrieval baseline on the E4 index: `rag/eval/results/retrieval_baseline_e4index.md`.
