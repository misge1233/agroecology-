# Model card: Methodology 1 v2 (`m1_v2`)

Built 2026-11-12T01:07:26+00:00 by `model/m1/train.py` from the evidence store (17,326 eligible rows, 561 study groups, 414 training queries) with release `ET/2026.1` context; git `3644d5929787bd3c1e9d47c688c0be8f541406d5+dirty`. Serves behind `ADVISOR_ENGINE=m1_v2` (default `legacy`: the frozen `csa_model.joblib` path is unchanged).

## What it does

Ranks every candidate practice for a site, a challenge and an objective (any canonical outcome in the registry) and gives an effect estimate on the oriented log response ratio scale with a conformal 80 % interval. Four components feed one combination rule: an effect regressor (HistGradientBoosting on the oriented effect), a within-study ranker (LightGBM lambdarank on the training queries), context-matched studies (DerSimonian-Laird pooling of the nearest training sites) and a shrunken practice prior (empirical Bayes toward component, family and grand means). The prior answers every candidate, so the engine never abstains; `lead_source` names the component with the largest contribution (model, matched_studies, prior = model-led, study-led, documented).

## Data

Store rows with a reviewed direction, a computable `lrr`, practice and outcome ids, not a duplicate, not an unchecked geocode; weights `inverse_variance`. Country-precision rows enter with the reported context and a `ctx_missing` flag. Nothing is learned from a query's own rows; in evaluation every learned quantity was fitted inside the outer training fold (nested inner folds).

## Features

80 active features: the release context layers, belt and Köppen class as categorical attributes, land cover, crop group, practice family, outcome id, objective group, source, quality flag, location precision, duration, the practice components (multi-hot) and the practice target encoding with counts (out-of-fold on the training rows).

Features stable in at least 4 of 5 outer folds (spatial split, repetition 0; `feature_stability.json`): 80, served exactly (`features.json`).

## Components and combination

- regressor: `{'learning_rate': 0.05, 'max_iter': 300, 'min_samples_leaf': 50}`
- ranker: {'kind': 'ranker:lambdarank', 'n_queries': 414, 'n_items': 1179}
- matched studies: k = 20, decay power 1.0, k_min = 3
- prior: kappa 2.84, sigma2 0.454, tau2 0.1599
- stacker: `rank_avg`, fixed to the choice made inside the majority of the outer folds of the evaluation (`per_fold_choices.json`: rank averaging in 8 of 10 fits, all 5 spatial folds)
- conformal: 80 % quantile 0.808 on 3295 inner out-of-fold items

## Evaluation (E4 harness, ET set, full coverage, mean across 5 x 5 folds)

| split | top-1 hit | chance | C-index | NDCG@3 | 80 % coverage | width |
|---|---:|---:|---:|---:|---:|---:|
| spatial | 0.519 | 0.396 | 0.603 | 0.830 | 0.82 | 1.30 |
| study | 0.546 | 0.396 | 0.618 | 0.844 | 0.80 | 1.27 |

## Limitations

- Evidence is thin for many practice x outcome cells: the prior leads there, and its interval is a shrinkage interval, not a prediction interval.
- Context outside Ethiopia and country-precision sites carry only the reported rainfall, altitude and slope.
- The ranker and regressor learn from the same 800-odd studies; a new practice with no rows is placed by its components and family only.
- Numbers shown to users must carry their provenance (`lead_source`, citations) as every other source does.

## Intended use

Ranking and effect estimates behind the advisory when `ADVISOR_ENGINE=m1_v2`; not a substitute for the study-level evidence and guidance that the fusion layer shows beside it.
