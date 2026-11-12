# E5: Methodology 1 v2, the evidence model (11 Nov 2026)

**Binding:** `docs/roadmap/AE+_enhancement_roadmap.md` sections 7, 8, 11 and Appendix B; `docs/decisions/enhancement_v2.md`; `docs/decisions/evidence_fusion.md`; the harness of E4 (`model/harness/README.md`), used as is; CLAUDE.md; the E1 to E4 reports and reviews in `progress.md`; this brief.

**Purpose.** Build Methodology 1 v2: an evidence model that ranks every candidate practice for every query, gives an effect estimate with a calibrated 80% interval, says which evidence led, and is measured on the E4 harness against the four baselines. It replaces the current model's two weaknesses: it learns the product question directly (which practice is better here) and it answers all queries instead of abstaining on 46% of them. Retrieval stays the explanation layer of Methodology 1; it is not scored for ranking in this phase.

**Ground rules:** as E1 to E4 (production grade, additive, deterministic, masked, nothing silently dropped, tests for every module). Plus:

- **Nested, never leaky.** Anything learned from data (hyperparameters, stacker weights, conformal quantiles, feature selection) is learned inside the outer training fold only, with inner folds built by the same study-grouped rule. The harness Mask governs every fit.
- **One engine, full coverage.** `m1_v2` answers every query of the ET set; when a component cannot answer, the next one in a fixed fallback chain does, and `lead_source` says which.
- **The frozen artifact contract is untouched.** `csa_model.joblib`, `recommend.py` and the serving path keep working; M1 v2 is a new artifact behind a flag.
- Commit messages, if the owner asks for any, are short and plain with no attribution lines.
- Report as an **E5 block in `progress.md`**, then stop. The owner commits.

**Do not regress:** the E4 baseline runs (`et_baselines_a` metrics reproduce), the P7 protocol, all test suites, the running app.

---

## Part 0: harness additions (do first)

1. **Fair comparison across abstention.** E4 counts a query as abstained when a method abstains on any candidate, so methods are scored on different subsets. Add two scorings to `model/metrics.py` and the report, and use them as the headline from now on:
   - **full coverage**: every method is scored on all queries of the set; where it abstains, its ranking is filled by `practice_prior` and the method is labelled `<method>+prior`;
   - **common subset**: for any set of methods compared in a run, the metrics on the queries all of them answered, with the subset size.
   The per-method "answered" metrics stay as a secondary table.
2. **Paired significance.** For two methods on the same queries, report the paired bootstrap 95% interval of the difference in top-1 hit, C-index and NDCG@3 (query-level resampling, 1,000 draws, seeded). A method "beats" another only when that interval excludes zero on the spatial split.
3. **Retrieval baseline on the new index.** Rerun `rag/eval/eval_retrieval.py` (and the chat evaluation if it uses the index) on the E4 index, record the numbers as the new retrieval baseline in `rag/eval/` with the index hash, and note the change from the August 2026 figures.
4. Run `practice_prior`, `nearest_studies`, `m0_current` once more under the new scorings so the E5 tables have reference rows (`et_baselines_c`).

## Part 1: training data and features (`model/m1/data.py`)

- **Rows:** store rows eligible for the harness (reviewed direction, computable `lrr`, practice and outcome ids, not a duplicate, not an unchecked geocode) after `mask.filter_rows`. Country-precision rows enter with missing context and a `ctx_missing` flag; an ablation excludes them.
- **Target:** oriented effect `y = direction x lrr` (benefit is positive for every outcome), so one model serves every objective.
- **Features:** the release `ctx_*` layers (27), the belt as one categorical attribute, Köppen class, crop group, practice id (target-encoded within folds with counts), practice components (multi-hot over the component layer), practice family, outcome id, objective group, duration, source, quality flag, location precision. No feature may be computed from the query's own rows.
- **Weights:** two schemes, both kept for the ablation: inverse variance (capped as in the store) and the store's quality-default `weight`.
- **Feature selection:** grouped permutation importance on inner folds; features that do not improve the inner ranking metrics are dropped in a documented, deterministic order (expected candidates: `soil_depth_bedrock`, `koppen_class` duplicates of belt information, `travel_time` for non-economic outcomes). The kept set is reported per outer fold and must be stable in at least 4 of 5 folds to be used in serving.

## Part 2: components (`model/m1/`)

**2.1 Effect regressor** (`regressor.py`). Gradient boosting on `y` with the features above (sklearn `HistGradientBoostingRegressor` by default; LightGBM allowed if it installs cleanly on the owner's machine with numpy 2.4.6, decision recorded). Hyperparameters by a small grid on inner folds, scored by the inner ranking metrics, not RMSE.

**2.2 Within-study ranker** (`ranker.py`). Learns which practice is better at the same site, from the training queries (cells with at least two practices). Primary: LightGBM `LGBMRanker` (lambdarank) with queries as groups and graded relevance from the observed oriented effects (rank within the query). Fallback if LightGBM is unavailable: a symmetric pairwise classifier (HistGBM on `[x_i - x_j, context]` with both orders of every pair, label `y_i > y_j`, pairs with `|y_i - y_j| < 0.02` dropped). Features exclude site identifiers so the ranker cannot memorise sites. Report how many training queries and pairs each fold has.

**2.3 Context-matched studies** (`matched.py`). The E4 `nearest_studies` engine improved: k and the distance weights tuned on inner folds; pooling by a random-effects model (DerSimonian and Laird) per practice and outcome, which also gives an interval; abstains below `k_min` groups (tuned, default 3).

**2.4 Shrunken practice prior** (`prior.py`). Empirical-Bayes estimate per (practice, objective group) shrunk toward its component mean, then its family mean, with a random-effects interval. This is the last link of the fallback chain and answers every candidate.

**2.5 Stacker and fallback chain** (`stack.py`). For each candidate: the stacker combines the available component scores (regressor estimate, ranker score, matched estimate and its precision, prior) with weights learned on inner out-of-fold predictions (a small ridge model on standardised scores, or a rank-averaging rule if the ridge does not beat it on inner folds; decision recorded). When a component is missing for a candidate, the stacker uses the trained sub-model for the available components. `lead_source` is the component with the largest weighted contribution: `model` (regressor or ranker), `matched_studies` or `prior`, mapping to the fusion labels `model-led`, `study-led`, `documented`.

**2.6 Calibrated intervals** (`conformal.py`). Normalised split-conformal on grouped inner folds: residuals of the effect estimate divided by a difficulty score (the matched-studies spread and the distance to the nearest training site), the 80% quantile taken on inner out-of-fold predictions, applied to the outer fold. Target: 80% coverage between 0.75 and 0.85 on held-out queries, with the width reported.

**2.7 Engine** (`model/engines/m1_v2.py`). Implements the E4 `Engine` protocol, registered in `model/engines/__init__.py`. `rank()` returns every candidate with `score`, `est_lrr`, `lo`, `hi`, `abstain = False`, `lead_source`, and `citations` = the study ids that contributed (matched studies and, for the regressor, the top contributing training groups by context distance; no text).

## Part 3: evaluation

Runs on the E4 harness, ET set, both splits, 5 x 5, plus the all set:

- **Headline:** `m1_v2` against `practice_prior`, `nearest_studies+prior`, `m0_current+prior` under full coverage and on the common subset; paired bootstrap differences.
- **Components:** each component alone (with the prior fallback) to show what each adds.
- **Ablations:** belt removed; context reduced to the 11 legacy layers; Habtamu rows removed; country-precision rows removed; weights inverse-variance against quality default; ranker removed; matched studies removed; stacker against rank averaging.
- **Calibration:** 80% coverage and width, overall and per objective group; the calibration plot.
- **Breakdowns** as in E4 (objective group, challenge, belt, source, precision), with the `n < 20` rule.
- **Continuity:** `m1_v2` restricted to `legacy_68` with the P7 folds, beside `m0_current`.

**Success criterion for the phase** (stated now, before any result): on the ET set, spatial split, full coverage, `m1_v2` beats `practice_prior` and `m0_current+prior` on top-1 hit and C-index (paired bootstrap interval of the difference excludes zero), and its 80% intervals cover 75 to 85% of held-out effects. If it does not, the report says so plainly, shows which component carries what, and proposes the smallest change worth testing; no tuning against the outer folds.

## Part 4: artifact and serving adapter (no default switch)

- `model/m1/train.py --release ET/2026.1` fits the final engine on all eligible rows with the selected configuration and writes `model/artifacts/m1_v2/` (model files, feature list, conformal quantiles, component weights, `model_card.md`, `config.json` with the store, release, query and fold hashes). Git-ignore the binary files; keep the card and config in git.
- Backend: an `ADVISOR_ENGINE` setting (`legacy` default, `m1_v2` optional). With `m1_v2` the recommender service ranks through the new engine for any challenge and objective in the registry, maps `lead_source` to the existing fusion labels, and returns the interval as additive response fields. The default path and every existing test are unchanged; new tests cover the `m1_v2` path on a fixture artifact.
- No UI change in this phase.

## Part 5: report

`model/reports/eval_<date>_m1v2.md` from the harness, `model/artifacts/m1_v2/model_card.md` (data, features, components, metrics with intervals, limitations, intended use), and the E5 block in `progress.md` with: the headline table (full coverage and common subset, both splits), the paired differences, component and ablation tables, calibration, the selected features, timings, decisions, and open items for E6 (Methodology 2) and E7 (comparison and fusion v2).

## Acceptance

1. Part 0 in place: full-coverage and common-subset scorings, paired bootstrap differences, the new retrieval baseline recorded, `et_baselines_c` run.
2. `m1_v2` answers 100% of ET queries, with `lead_source` on every item.
3. Every learned quantity is fitted inside the outer training fold (a test fits on a fold with a canary study and shows the canary never influences the stacker, conformal quantile or selected features).
4. Headline, component, ablation, calibration and continuity tables reported for both splits; two runs identical to the third decimal.
5. The success criterion is evaluated and reported plainly, whatever the result.
6. `model/artifacts/m1_v2/` built with a model card; the backend serves it behind `ADVISOR_ENGINE=m1_v2` with tests; the default path unchanged.
7. All tests pass; nothing committed.
