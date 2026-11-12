# E7.1: structure-aware Methodology 1 and the nested-query diagnostic (12 Nov 2026)

**Binding:** the E7 report and review in `progress.md`; `docs/briefs/E5_methodology1_v2.md` (the nested fitting rules); the harness (E4) with the E5 scorings; CLAUDE.md; this brief. Everything below is **pre-registered on 12 Nov 2026**, before any of it runs.

**Why.** E7 showed that the no-evidence LLM ranks practices the same way for every farm, and that a one-line rule with no LLM, "the practice with the most components first", does as well (+0.095 top-1 over M1 v2) and at least as well as the LLM gate. Field trials compare a combined treatment with its parts, and the combination usually gives the larger effect. That is real evidence about effects, but M1 v2 does not exploit it, and the benchmark rewards it whether or not a method knows anything about the farm. This phase (1) teaches M1 the structure of the candidate set from the evidence, instead of hard-coding the rule or calling an LLM, and (2) measures every method separately on questions where that structure cannot help.

**Owner decision (12 Nov 2026).** The evidence fusion amendment drafted in E7 is **not approved**: the language model stays out of ranking. Its gain is matched by a transparent rule, it does not use the farm context, and it would add an external dependency to every thin-evidence request. The `m3` code stays in the repository behind its flag for research; the draft stays in `docs/decisions/` marked "not approved, 12 Nov 2026". The language model keeps its roles in conversation and explanation.

**Ground rules:** as E5 to E7 (nested fitting, masking, one variant per process, determinism, short plain commit messages with no attribution lines if the owner asks for any). No LLM calls in this phase. Report as an **E7.1 block in `progress.md`**, then stop. The owner commits.

---

## Part A: the nested-query diagnostic (existing predictions, no new fits)

- **Definition.** A query is **nested** when the component set of at least one candidate strictly contains the component set of another candidate in the same query (for example "fertiliser + manure" with "manure"); otherwise it is **non-nested** (the candidates are alternatives, for example stone bund against soil bund). Components come from the taxonomy (`practice_components`), never from the query rows.
- Report the number of nested and non-nested ET queries, and for each subset the full-coverage metrics (top-1 with chance, C-index, NDCG@3) of every method already run: `practice_prior`, `nearest_studies+prior`, `m0_current+prior`, M1 v2 (E5), M1 v2 E5.1, `component_count`, `input_intensity`, `m2_zero` (both models, repetition-0 rows and the 5 x 5 replication), `m3_stack`, `m3_gate`. Paired differences against M1 v2 per subset. Label the section "diagnostic".
- Also report, per objective group, the share of nested queries and the `component_count` top-1, with the `n < 20` rule. The economics group matters most: a combined practice usually raises yield but may not raise the margin.

## Part B: structure-aware M1 (`m1_v2s`), one variant, evaluated once

Additions to M1 v2, all computed from the candidate set and the taxonomy, never from the query's outcomes:

- per candidate: number of components; whether it strictly contains another candidate (and how many); whether another candidate strictly contains it; its rank by component count within the set (ties averaged); its family;
- these features enter the **within-study ranker** (where the set is known) and the **stacker** (as an extra standardised score: the component-count rank). The regressor is unchanged.

Nested selection exactly as E5 (inner study-grouped folds; stacker candidates: the E5 rank averaging, the same with the structure score as a fifth member at weight 1, and at weight 2; inner score = mean of inner top-1 and C-index; served choice by the majority-of-folds rule). Conformal intervals as in E5 (pooled), so calibration stays comparable.

Run `m1_v2s` on the ET set, spatial and study splits, 5 x 5, full coverage, common subset, paired bootstrap against M1 v2, `component_count`, `m3_gate` and `m0_current+prior`, with calibration, the per-objective breakdown and the Part A subsets (nested and non-nested).

## Part C: the production engine (pre-registered)

- If `m1_v2s` beats M1 v2 (E5) on the spatial split under full coverage, on top-1 or C-index with the paired interval excluding zero, and its 80% intervals cover 75 to 85%: it becomes the served M1 artifact (`model/artifacts/m1_v2/` rebuilt; the E5 artifact kept as `m1_v2_e5/`).
- Otherwise the E5 artifact stays.
- Only learned engines are eligible as the production default. `component_count` and the gates are reported as benchmark diagnostics, not served.
- The chosen artifact is what E8 serves by default (`ADVISOR_ENGINE=m1_v2`); E7.1 does not change the default.

## Report

An E7.1 section appended to `model/reports/methodology_comparison_2026-11-12.md` (or a dated sibling) with Part A and Part B tables in plain words, the Part C outcome, and the E7.1 block in `progress.md`.

## Acceptance

1. Nested and non-nested counts and per-subset metrics for every method reported, labelled diagnostic.
2. `m1_v2s` evaluated once with nested selection; a canary test shows that a held-out query's candidate set and outcomes do not change any inner choice.
3. The Part C rule applied exactly; artifact rebuilt only under it.
4. The amendment draft marked "not approved, 12 Nov 2026"; `m3` stays behind its flag; the default engine unchanged.
5. All runs reproduce; all tests pass; nothing committed.
