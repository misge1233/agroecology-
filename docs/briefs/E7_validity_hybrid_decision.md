# E7: validity of the LLM result, the hybrid, and the methodology decision (12 Nov 2026)

**Binding:** `docs/roadmap/AE+_enhancement_roadmap.md` sections 10 and 11; `docs/decisions/enhancement_v2.md` (with the 12 Nov addendum); `docs/decisions/evidence_fusion.md`; the harness (E4) with the E5 scorings; the E5 and E6 reports and reviews in `progress.md`; this brief.

**Why this phase is shaped this way.** E6 found that `gpt-4.1-mini` given **no evidence** (only the context, the objective, the crop and the candidate names) ranks better than every evidence-based method, by +0.104 top-1 and +0.055 C-index over M1 v2 on the spatial repetition-0 folds, and that adding evidence makes it worse. Before this result can shape the product or the manuscript, three explanations must be told apart, because they have opposite consequences:

1. **Real, location-aware agronomic knowledge**: the model uses the farm context well. Then a hybrid that lets it reorder evidence-backed candidates may help users.
2. **Generic knowledge or trial-design structure**: the model ranks practices the same way everywhere (for example "combined inputs beat single inputs", which trials are often designed to show). Then it is a strong generic prior, useful only where local evidence is thin, and it cannot carry the claim of location-specific advice.
3. **Recall of the published studies** (the test queries come from studies the model may have read): then its score overstates what it can do for a new farm, and it must not be trusted for ranking until a fresh test set shows otherwise.

All tests, hybrid variants and decision branches below are **pre-registered on 12 Nov 2026**, before any of them runs. Results are reported whatever they are.

**Ground rules:** as E1 to E6 (production grade, additive, masked, cached and capped LLM calls, one variant per process for long runs, no tuning against outer folds, short plain commit messages with no attribution lines if the owner asks for any). Budget cap for the phase: 20 USD. Models: `gpt-4o-mini` and `gpt-4.1-mini` (owner decision of 12 Nov). Report as an **E7 block in `progress.md`**, then stop. The owner commits.

---

## Part A: validity tests (both models unless stated; all 375 ET queries unless stated)

`m2_zero` uses no evidence, so its predictions do not depend on the folds; it is reused from E6 and not re-called.

- **A1. Fair reference.** Compare `m2_zero` with M1 v2, `m0_current+prior` and `practice_prior` using, for each query, those methods' metrics averaged over all 5 spatial repetitions (not repetition 0 only). Paired bootstrap as before.
- **A2. Names only** (`m2_names`): the candidate names and the objective only; no site context, no crop. If it matches `m2_zero`, the model is not using the context.
- **A3. Context swap** (`m2_swap`): each query receives the context of the most dissimilar query of the same objective group (largest standardised context distance; deterministic). Report the metrics and the Kendall tau between the `m2_swap` and `m2_zero` rankings of the same query. If the metrics do not fall and the rankings barely change, the context is not driving the ranking.
- **A4. Heuristic baselines, no LLM:** `component_count` (more practice components first, ties broken by the practice prior) and `input_intensity` (a fixed, documented ordering of practice families and components by input level, written before the run from the taxonomy only). If either comes close to `m2_zero`, the model's advantage is largely trial-design structure.
- **A5. Recall probes** (`gpt-4.1-mini` only, 80 queries stratified by objective group and source, one query per study group):
  - *identification*: given exactly the `m2_zero` prompt content, ask the model to name the published study (first author, year, journal) or say unknown; score a match on first-author surname and year within one;
  - *title lift*: ask the `m2_zero` question again with the study's title and DOI added; the difference in top-1 hit between "with title" and "without title" on the same 80 queries measures how much study-specific recall the model can access.
  Report the identification rate and the title lift with bootstrap intervals.
- **A6. Fresh test set (data work, parallel, not blocking).** Add a loader path and a query set `fresh_2024plus` for Ethiopian multi-practice trials published after June 2024 (after the knowledge cutoff of both models), in the Habtamu database format, from `data/raw/fresh_2024plus/` when the owner provides it. If at least 30 queries are available before Part C, run Part A1 and the hybrid on them; otherwise report that the set is pending.

## Part B: hybrid candidates (pre-registered)

Both reuse the fold-independent `m2_zero` scores from E6 (no new LLM calls) and the M1 v2 components; numbers, intervals and citations always come from M1 v2 (conformal) and its evidence; the LLM only influences the order.

- **B1. `m3_stack`:** the M1 v2 nested stacker with the `gpt-4.1-mini` `m2_zero` ranking as an additional component. The inner selection chooses among the E5 configuration (no LLM), rank averaging with the LLM at weight 1, and with the LLM at weight 2, scored by the mean of inner top-1 and C-index; served choice by the majority-of-folds rule.
- **B2. `m3_gate`:** for each query, use the M1 v2 ordering when evidence is dense, else the `m2_zero` ordering filled by M1 v2 where the LLM abstains. Density = the median number of distinct training groups per candidate behind M1 v2's estimate; the threshold is chosen on inner folds among 2, 3 and 5.

Evaluate both on the ET set, spatial and study splits, 5 x 5, full coverage, common subset, paired bootstrap against M1 v2, `m2_zero` and `m0_current+prior`, with calibration and breakdowns.

## Part C: the decision (pre-registered branches)

Read the Part A results in this order and apply the first branch that holds:

1. **Recall dominates:** identification rate above 25%, or a title lift whose interval excludes zero and exceeds +0.10 top-1. Then the LLM is not used for ranking; production ranking is **M1 v2**; the LLM keeps its roles in conversation and explanation; the hybrid is deferred until `fresh_2024plus` exists.
2. **Context not used:** `m2_names` within 0.02 top-1 and 0.02 C-index of `m2_zero`, or `m2_swap` metrics within the same margins with a mean Kendall tau above 0.8. Then the LLM is a **generic prior**: it may enter production only through `m3_gate` (thin-evidence queries), and only if `m3_gate` beats M1 v2 on the spatial split under full coverage with a paired interval excluding zero; otherwise M1 v2.
3. **Otherwise** (context used, no recall signal): production ranking is the best of `m3_stack`, `m3_gate` and M1 v2 on the spatial split under full coverage, a method counting as better only when its paired interval against the next excludes zero; ties go to M1 v2 (cheaper, deterministic, no external call).

In every branch the 80% intervals of the chosen design must cover 75 to 85% of held-out effects, and the report states which branch applied and why, in plain words.

**Doctrine.** If the decision lets the LLM influence the order of practices, the owner must approve a one-paragraph amendment to `docs/decisions/evidence_fusion.md` (the order may be informed by the language model's general agronomic knowledge; every number, interval and citation still comes from evidence; the Methodology page says so). Claude Code drafts the paragraph and does not apply it.

## Part D: serving the decision (behind flags, no default switch)

- If the decision is M1 v2: nothing new to serve beyond E5.
- If it is a hybrid: `ADVISOR_ENGINE=m3`; the LLM call is made once per (context cell, objective, candidate set) and cached; timeout 8 s with fallback to M1 v2 ordering; cost per request logged; tests with a fake client; the default path unchanged.
- In both cases, the `/advise` response gains additive fields that the UI phase (E8) will use: the engine used, the lead source per practice mapped to the fusion labels, and the 80% interval.

## Part E: the methodology comparison report (manuscript-ready)

`model/reports/methodology_comparison_<date>.md` and `metrics.json` with: the protocol in plain words; one headline table (baselines, M0, M1 v2, M2 variants with both models, the hybrids) under full coverage and on the common subset; the paired differences that matter; the validity tests; calibration; cost and latency; the decision branch and its reasons; limitations (no fresh set yet if pending, single repetition for M2, deployable models only). Figures as PNG. This document feeds the Methodology page in E8 and the manuscript.

## Acceptance

1. Part A run and reported; the A6 loader and query set in place (pending or run).
2. `m3_stack` and `m3_gate` evaluated with nested selection; a canary test shows no outer-fold leakage.
3. The decision branch applied exactly as written, with the reasons in plain words.
4. The chosen design calibrated (75 to 85% at 80%), or the report says so plainly.
5. Serving behind a flag if a hybrid is chosen; the doctrine paragraph drafted, not applied.
6. The methodology comparison report written; all runs reproduce from the cache; all tests pass; spend under 20 USD; nothing committed.
