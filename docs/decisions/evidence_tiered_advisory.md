# Decision record — Evidence-tiered advisory (Phase P9)

**Status:** implemented 28 Oct 2026 (Phase P9). **Owner of the numbers:** the ML model
(`app/backend/recommend.py`), unchanged. **Doctrine:** CLAUDE.md §1–2 as amended in P9 —
knowledge sources may *propose* practices with provenance, never *quantify* them.

## 1. Why

The P6b-i/U2 reviews showed the same advisory shape for every request, whether the
engine's top practices rest on dozens of field observations in the user's setting or on
a handful measured elsewhere, and a plain error ("No field evidence") when a
challenge × objective pair had no observations at all. P9 makes the evidence depth an
explicit, machine-decided **mode** and adds a second, clearly subordinate layer of
**documented practices** that is shown only when the field-trial evidence is thin or
absent.

## 2. Modes

| mode | when | what the user gets |
|---|---|---|
| **model-led** | a top-3 practice has ≥ `evidence_min_studies` (3) studies **and** ≥ `evidence_min_obs` (10) field observations for the objective, **and** a top-3 practice has ≥ `evidence_min_obs_in_zone` (1) observation in the user's moisture zone | the ranking alone; the source badge says *Field-trial model*; the English narrative is byte-identical to pre-P9 (guarded by a test) |
| **hybrid** | the engine ranks, but one of the two conditions above fails | the ranking **plus** up to five documented practices (sources, counts, no effect numbers) and a reasons card |
| **knowledge-led** | the engine cannot rank: the pair is not supported, the dataset has no observations ("No field evidence"), or every ranked practice has 0 studies for the objective | no ranking at all; the documented practices *are* the answer (replaces the former error) |

Reasons are emitted as catalog keys with parameters (`mode.reason.strong_evidence`,
`thin_evidence`, `in_zone`, `other_zones_only`, `zone_unknown`, `engine_no_evidence`,
`engine_unsupported`, `no_studies`, `graph_unavailable`, `no_candidates`) and rendered
by the UI in en/am/om. Thresholds are settings (`EVIDENCE_MIN_STUDIES`,
`EVIDENCE_MIN_OBS`, `EVIDENCE_MIN_OBS_IN_ZONE`, `KNOWLEDGE_CANDIDATES_MAX`,
`GUIDANCE_CANDIDATES_K`, `GUIDANCE_MIN_QUALITY`) and are published by `/metadata`
under `advisory.thresholds`.

**Degradation.** No knowledge graph → model-led with `mode.reason.graph_unavailable`
(no candidates). A pre-P9 graph store without per-belt counts → in-belt / in-zone
counts fall back to *presence* of the belt in the practice's evidence
(`belt_counts_exact: false` in `evidence_sufficiency`). Guidance retrieval failing →
no guidance candidates, never an error.

## 3. Evidence counts per candidate

`evidence_sufficiency.candidates[]` carries, for every ranked practice (top-N),
`n_studies`, `n_obs`, `n_obs_in_belt`, `n_obs_in_zone`, `aez_belts`, `corpus_status`
(studies by corpus status), `belt_counts_exact` and `in_top3`. Counts come from the
knowledge graph's REPORTS_EFFECT edges, which now carry `obs_by_belt` (built from the
dataset's `aez_belt` column; the store was rebuilt: 720 nodes, 1 961 edges, 867/867
effect edges with belt counts summing to `n_obs`).

### Moisture zone = moisture regime × belt group

The user's `aez_belt` (e.g. *Dry Kolla*) is split into its moisture regime and its
belt, and the belt is grouped so that sparse belts pool:

| belt | group |
|---|---|
| Berha, Kolla | lowland |
| Weyna Dega | midland |
| Dega, High Dega, Wurch | highland |

Zone = `<Dry|Moist|Wet>-<lowland|midland|highland>` (e.g. `Dry-lowland`). An
observation counts as "in zone" when its study belt maps to the same zone.

## 4. Knowledge candidates (documented practices)

Three sources, in support order:

1. **`evidence_other_objectives`** — graph relations: practices of the same family
   that have REPORTS_EFFECT evidence for *other* indicators. Cited per study (`[n]`).
2. **`documented_in_guidance`** — Tier-2 guidance passages retrieved with the same
   `build_query_text` as `/explain` (k = `guidance_candidates_k`, 12), quality-filtered
   first (`rag/ingest/quality.py`, `min_quality` 0.55), mapped to the 44 canonical
   components with `rag/graph/component_keywords.py` (left word boundary so
   "organic fertilizer" never fires inside "inorganic fertilizer"). Cited per document
   (`[Gn]`).
3. **`documented_practice_record`** — WOCAT records from
   `similar_context_technologies` (`[Wn]`); populated from the P6b-i fixtures until
   P6b-ii ingests real records.

Candidates are **components of practices of the requested family** (never a practice
from another family), de-duplicated by component, ranked by *distinct sources > distinct
documents > passages* and capped at `knowledge_candidates_max` (5). A candidate without
a citation is dropped (doctrine 2). A citation must carry an identity — ERA code,
dataset study id (`study_no`, shown as "Dataset study #CSA_18" when the study is not in
the ERA corpus and has no title), URL, WOCAT id, DOI or title — otherwise it is refused;
numbering is global per response and one number per distinct source. The rationale is a deterministic template whose only
numbers are counts (`rationale_numbers_are_counts` is tested and the mode report runs it
over every candidate: 0 failures in 5 207). The practices listed on a card are all
frozen practices of the family that contain the component.

## 5. Mode report over the 35 cells (rag/eval/mode_report.py)

Run 28 Oct 2026 over 5 families × 7 indicators × 38 de-duplicated pins of
`rag/eval/queries_v2.jsonl` (1 330 advisories, thresholds 3 / 10 / 1, guidance
retrieval off; `rag/eval/results/mode_report.{json,md}`):

- overall: **model-led 281 · hybrid 859 · knowledge-led 190**; cells by dominant
  mode: hybrid 21, model-led 9, knowledge-led 5 (the five pairs the engine does not
  support);
- reasons over all advisories: thin_evidence 746, other_zones_only 555,
  strong_evidence 394, in_zone 585, engine_unsupported 190 — the binding condition is
  **evidence depth of the engine's own top 3**, not the zone: the ranking favours
  combination practices with few observations, so cells with a well-studied single
  practice (e.g. *Physical SWC Measures*, 19 soil-loss studies) are still hybrid when
  that practice is not in the top 3;
- candidates: mean 3.92 per advisory; 5 169 from graph relations, 38 practice records.
  With `--guidance` (Tier-2 retrieval on, 1 145 s; `mode_report_guidance.{json,md}`) the
  modes are identical (retrieval never decides the mode) and the candidates carry
  5 161 graph, **4 316 guidance** and 38 record provenances. Quality-filter funnel on a
  5-pin sample (`mode_report_guidance_sample.json`, 144 advisories with retrieval):
  1 728 passages retrieved → 1 618 kept (110 dropped at 0.55) → 948 mention a canonical
  component.

| challenge | objective | model-led | hybrid | knowledge-led | dominant | pins with strong top-3 evidence | pins with in-zone evidence |
|---|---|---:|---:|---:|---|---:|---:|
| Crop production and management | yield | 14 | 24 | 0 | **hybrid** | 20 | 23 |
| Crop production and management | biomass yield | 36 | 2 | 0 | **model-led** | 38 | 36 |
| Crop production and management | income | 0 | 38 | 0 | **hybrid** | 0 | 8 |
| Crop production and management | water use efficiency | 0 | 38 | 0 | **hybrid** | 0 | 14 |
| Crop production and management | SOM content | 0 | 38 | 0 | **hybrid** | 0 | 13 |
| Crop production and management | soil loss | 24 | 14 | 0 | **model-led** | 38 | 24 |
| Crop production and management | runoff | 30 | 8 | 0 | **model-led** | 38 | 30 |
| Livestock production and management | yield | 0 | 0 | 38 | **knowledge-led** | 0 | 0 |
| Livestock production and management | biomass yield | 0 | 38 | 0 | **hybrid** | 0 | 20 |
| Livestock production and management | income | 0 | 38 | 0 | **hybrid** | 0 | 20 |
| Livestock production and management | water use efficiency | 0 | 0 | 38 | **knowledge-led** | 0 | 0 |
| Livestock production and management | SOM content | 0 | 0 | 38 | **knowledge-led** | 0 | 0 |
| Livestock production and management | soil loss | 0 | 38 | 0 | **hybrid** | 0 | 12 |
| Livestock production and management | runoff | 0 | 38 | 0 | **hybrid** | 0 | 23 |
| Integrated soil fertility management | yield | 5 | 33 | 0 | **hybrid** | 5 | 24 |
| Integrated soil fertility management | biomass yield | 1 | 37 | 0 | **hybrid** | 3 | 19 |
| Integrated soil fertility management | income | 1 | 37 | 0 | **hybrid** | 4 | 13 |
| Integrated soil fertility management | water use efficiency | 0 | 38 | 0 | **hybrid** | 0 | 9 |
| Integrated soil fertility management | SOM content | 1 | 37 | 0 | **hybrid** | 2 | 15 |
| Integrated soil fertility management | soil loss | 0 | 38 | 0 | **hybrid** | 0 | 14 |
| Integrated soil fertility management | runoff | 0 | 38 | 0 | **hybrid** | 0 | 14 |
| Erosion control and water management | yield | 29 | 9 | 0 | **model-led** | 31 | 30 |
| Erosion control and water management | biomass yield | 26 | 12 | 0 | **model-led** | 38 | 26 |
| Erosion control and water management | income | 0 | 0 | 38 | **knowledge-led** | 0 | 0 |
| Erosion control and water management | water use efficiency | 31 | 7 | 0 | **model-led** | 38 | 31 |
| Erosion control and water management | SOM content | 20 | 18 | 0 | **model-led** | 38 | 20 |
| Erosion control and water management | soil loss | 2 | 36 | 0 | **hybrid** | 3 | 20 |
| Erosion control and water management | runoff | 13 | 25 | 0 | **hybrid** | 17 | 21 |
| Agro-forestry and forest management | yield | 1 | 37 | 0 | **hybrid** | 5 | 18 |
| Agro-forestry and forest management | biomass yield | 0 | 38 | 0 | **hybrid** | 0 | 13 |
| Agro-forestry and forest management | income | 0 | 0 | 38 | **knowledge-led** | 0 | 0 |
| Agro-forestry and forest management | water use efficiency | 0 | 38 | 0 | **hybrid** | 0 | 9 |
| Agro-forestry and forest management | SOM content | 0 | 38 | 0 | **hybrid** | 0 | 19 |
| Agro-forestry and forest management | soil loss | 22 | 16 | 0 | **model-led** | 38 | 22 |
| Agro-forestry and forest management | runoff | 25 | 13 | 0 | **model-led** | 38 | 25 |

The report is re-runnable by the owner (rasters needed); `--guidance` adds Tier-2
retrieval (slower, needs the Chroma index) and `--out-name` keeps both runs.

## 6. Quality gate for guidance chunks (F2)

`rag/ingest/quality.py` scores a chunk from surface statistics (alpha ratio, short
tokens, caps, digits, mean word length, reference-list, bibliography, table,
numeric-token and dot-leader cues). Calibration on 100 stratified, hand-labelled
chunks (`rag/ingest/quality_sample.csv`; 58 garbage, 3 mixed, 39 ok) at the default
threshold 0.55: **precision 95.5 % strict (43/45; 100 % counting "mixed" as removable),
recall 72.4 %** of the labelled garbage. Over the current guidance corpus the gate would
remove **2 073 of 19 997 chunks (10.4 %)**, leaving 1 455 of 1 459 documents with at
least one chunk; flags among removed: alpha_ratio 1 710, bibliography 905, digit share
690, reference pattern 586, table pattern 576, numeric tokens 522, short tokens 372,
dot leaders 211, mean word length 55, caps 8. `prune_collection.py` applies it (dry run
by default; refuses the frozen `era_corpus`); the Tier-1 corpus is never filtered.

## 7. What did not change

`recommend.py`, the model, the dataset, the Tier-1 corpus and `era_corpus`; the
`/recommend` and `/explain` response shapes (additive fields only: `ref` on citations,
`advisory` on `/metadata`); the English model-led narrative.
