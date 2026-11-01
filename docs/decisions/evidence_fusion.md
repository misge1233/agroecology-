# Decision record — Evidence fusion: the best evidence leads, and every number has a source

**Status:** decided by the owner (Misganu Tuse), 1 Nov 2026. To be implemented in Phase U9.
**Supersedes:** the P9 wording of CLAUDE.md doctrine §1 ("the ML model owns every effect number").
**Amends:** `docs/decisions/evidence_tiered_advisory.md` §2–§4. Its modes stay as an internal, backward-compatible signal; the candidate rules change as below.
**Binding for:** backend, chat, UI, copy in en/am/om, docs and manuscript framing.

## 1. Decision

AgroEcoAdvisor is an **evidence-fusion advisor**, not a front-end to one model. Each recommendation draws on six sources: the field-trial ML model, study-level field evidence, retrieved study passages, guidance documents, practice records (WOCAT), and the knowledge graph that links them. For each practice, the strongest evidence for the user's context leads, and the other sources support it.

- When a context-matched field study is stronger than the model's estimate, the study leads.
- When the model is well supported, it leads and the studies back it up.
- Numbers reported by studies are allowed. Internally each one is labelled "reported in study [n]".
- Users see plain-language recommendations by default. The labels and citations appear when they open "Why this?"/"Evidence", in print, or when they ask in chat ("why?", "how do you know?", "what is the evidence?", "which study?").

## 2. Evidence sources

| Source | Provides | Numbers allowed | Label (Why/Evidence view) |
|---|---|---|---|
| ML model (`recommend.py`) | context-conditioned effect estimate, confidence, ranking | yes | "Model estimate for your area" |
| **Study evidence**: graph `REPORTS_EFFECT` edges (study → practice, per indicator), aggregated from dataset rows | each study's measured effect: `exp(mean_log_rr) − 1`, `n_obs`, belts/zone, crop groups, share positive | yes; computed from rows, never by an LLM | "Reported in study [n]" |
| Study passages (Tier 1, `era_corpus`) | mechanisms, conditions, quoted results | only when stated verbatim in the cited passage | "reported in study [n]" |
| Guidance documents (Tier 2, GARDIAN/CGSpace) | how-to, conditions, costs, labour | only when verbatim in the cited passage | "reported in [Gn]" |
| Practice records (Tier 3, WOCAT; pending the token) | documented technologies, compiler impact ratings | ratings as recorded | "WOCAT record [Wn]" |
| Knowledge graph | components, related practices, context classes, provenance | counts only | — |
| User context (raster stack) | site values at the pin | yes | "your area" |

The LLM writes and explains. It is **never a source of numbers**.

## 3. Who leads (per practice × objective × context)

Decided deterministically in the backend (`advisory_service`). Thresholds are settings published by `/metadata`.

1. **Model-led:** the model's confidence for this indicator is at least *medium*, and the practice has at least `EVIDENCE_MIN_OBS_IN_ZONE` observations in the user's moisture zone.
2. **Study-led:** the model is *thin* or has no in-zone evidence, **and** at least one study directly measured this indicator for this practice in the user's zone.
   - If no study is in the zone, fall back to the same belt group, then the same context class.
   - The headline is the study effect. With more than one study, use the median of the study means and show the numbers of studies and observations.
   - The model estimate is shown as supporting evidence.
3. **Documented:** there is no quantitative evidence for this objective in this context.
   - The practice is proposed from guidance, records and graph relations, with citations and no headline number.
   - A number can appear only if a cited source states it verbatim, and it is labelled.
4. **Disagreement:** if the model and the leading studies point in opposite directions, or differ by more than `EVIDENCE_DISAGREE_PCT` (default 25 points), set `disagreement: true`.
   - The headline becomes a range, or no number with the note "evidence varies".
   - The Evidence view shows both values.

## 4. Ordering

There is one list across lead sources, ordered by a **conservative effect** in the desired direction:

`bound = estimate − k · uncertainty`

- `k` is `CONFIDENCE_K_SD`, the same value P7 uses for confidence flags.
- Model uncertainty is the out-of-fold residual SD for the indicator.
- Study uncertainty is the between-observation SD / √n. Single-observation studies use the indicator's pooled SD.

This stops thin combination practices from burying well-studied ones. The P9 mode report showed *Physical SWC Measures*, with 19 soil-loss studies, outside the top 3.

The setting is `ADVISORY_ORDERING = conservative | model`, default `conservative`. Evaluate both: P7 ranking metrics where feasible, plus the mode report before and after. Report the results in `progress.md`. The owner confirms the default.

## 5. Numeric guard v2

Every number in generated text must be one of the following:

- (a) a model output for this request;
- (b) a study-effect value from the evidence bundle;
- (c) a figure verbatim in a cited passage, **in the same sentence as that passage's citation**;
- (d) a user context value;
- (e) a count or a year.

Display rounding comes from one shared function. A sentence with an unsourced number is removed. If removal breaks grounding, the deterministic template is used.

**Provenance on the wire:** every number in API responses is an object `{value, unit, source: model|study|passage|context|count, ref}`. The UI decides when to show the label. The current "never read `mean_log_rr`" rule in `explain_service.py` is retired for study evidence.

## 6. Presentation

- **Default** (result cards, chat answers): plain language. The headline effect is in words ("cuts soil loss by about 80%"), with one small source chip: *Field-trial model*, *Field study · similar area* or *Guidance*. No `[n]` markers and no "reported in" phrasing.
- **Why/Evidence, print/PDF, and chat when the user asks why or for evidence:**
  - labelled numbers, for example "Model estimate for your area: about 79% less soil loss (thin evidence: 1 study, 3 observations)" and "Reported in study [1] — Araya et al. 2017, Tigray: about 85% less (3 observations)";
  - the citations;
  - one line when sources disagree.
- **One citation registry per page or answer:** stable keys shared by cards, panels and print.
- **Words never used:** "proven", "guaranteed", "will increase". Use "trials found", "about", "in similar areas".

## 7. What does not change

- The frozen data contract, the model, the dataset and `era_corpus`.
- "Cite or stay silent" (now for every number and every proposed practice), "wrap, never fork", and "fail fast, degrade gracefully".
- API changes are additive: `lead_source`, `headline {value, unit, source, ref, words}`, `sources[]`, `disagreement`, and provenance objects. The P9 `mode` field is kept.

## 8. Docs and copy that change

- CLAUDE.md §1–2 (done 1 Nov).
- The home "model owns every number" card.
- The Advisor subtitle.
- About: how the advisor decides, confidence, sources.
- Hybrid/knowledge copy, the chat system prompt and the explain prompts in en/am/om.
- `README.md`, `docs/decisions/rag_design.md` and `evidence_tiered_advisory.md` (supersede note added 1 Nov).
- `research_project_plan.md` and `paper/manuscript/manuscript_skeleton.md`.
- Docstrings that cite the old doctrine: `explain_service.py`, `evidence_service.py`, `recommender_service.py`, `rag/graph/schema.py`.

## 9. Manuscript framing

The contribution is **evidence fusion** for agroecological advisory: a context-conditioned meta-analytic model, study-level field evidence, retrieval-augmented generation and a knowledge graph, combined with explicit rules for which evidence leads and a provenance guarantee for every number.

Evaluation:

- the lead-source distribution over the 35 challenge × objective cells;
- ordering metrics (conservative vs model);
- guard faithfulness;
- citation correctness;
- later, an expert review.

Working title: *"AgroEcoAdvisor: evidence fusion of meta-analytic machine learning, field-study evidence, retrieval-augmented generation and a knowledge graph for agroecological advisory — a case study from Ethiopia."*
