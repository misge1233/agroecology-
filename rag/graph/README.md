# `rag/graph` — the AgroAdvisor-ET knowledge graph

**Phase P6a — foundation.** A zero-ops knowledge graph (`networkx` +
serialized node-link JSON, no new infrastructure) that joins three things
that were previously only implicitly related:

1. the **evidence the ML model was trained on** — `CSA_practices`,
   `practice_family`, studies, indicators, and the per-study effect
   aggregates of `data/processed/CSA_ERA_final_model_ready.csv`;
2. the **retrieval corpus** — `era_code` → chunks, DOIs, corpus coverage;
3. the **WOCAT SLM vocabulary** (QT 2019) and, from P6b, real WOCAT
   practice records from 110 countries.

> **The graph never generates a number.** Every `REPORTS_EFFECT` attribute is
> a plain aggregation of dataset rows; every `REPORTS_IMPACT` attribute is a
> rating a WOCAT compiler recorded. Nothing here is produced by a language
> model (CLAUDE.md doctrine 1), and **every edge carries a `source`
> provenance tag** so any downstream claim can be traced.

## Modules

| Module | Role |
|---|---|
| `schema.py` | The contract: node/edge types, allowed endpoints, required attributes, provenance values, `validate_graph()`, node-link (de)serialization |
| `practice_components.py` | Derived component layer: splits the frozen `CSA_practices` labels on `-` and normalizes the pieces via an alias map |
| `wocat_taxonomy.py` | QT 2019 controlled vocabularies, transcribed from the questionnaire, plus normalizers for the live database's spellings |
| `indicator_map.py` | The 7 model indicators ↔ QT §6.1 impact variables; direction semantics read from `recommend.DIRECTION` |
| `build_graph.py` | CLI that builds `store/graph.json` + `store/graph_report.json`, deterministically and idempotently |
| `query.py` | The read-only API P6b's retriever calls |
| `crosswalk/propose_crosswalk.py` | Writes the component → SLM-vocabulary **proposal** the owner validates |
| `test_graph.py` | pytest on a synthetic CSV fixture — no network, no chromadb, no raster stack |

## Node types

| Node type | Count (23 Oct 2026) | Key | Source |
|---|---:|---|---|
| `PracticeFamily` | 5 | the frozen `practice_family` value | dataset |
| `Practice` | 100 | the frozen `CSA_practices` string | dataset |
| `PracticeComponent` | 44 | normalized atomic component | derived (see below) |
| `Indicator` | 7 | the engine's indicator name | `recommend.DIRECTION` |
| `Study` | 337 | `Study_No_` (`ERA_*` / `CSA_*`) | dataset + corpus manifest |
| `AEZBelt` | 12 | agro-ecological belt | dataset |
| `CropGroup` | 14 | `Crop_group` | dataset |
| `Country` | 1 (+WOCAT) | country name | dataset / WOCAT records |
| `SLMGroup` | 27 | QT §3.5 label | questionnaire |
| `SLMMeasure` | 30 | QT §3.6 code (`A1`…`M7`) | questionnaire |
| `DegradationType` | 32 | QT §3.7 code (`Wt`…`Hw`) | questionnaire |
| `ContextClass` | 40 | `<kind>=<QT label>` | questionnaire §5.1–5.3 |
| `ImpactVariable` | 69 | QT §6.1 variable name | questionnaire |
| `Technology` | 0 (2 fixtures) | WOCAT id | WOCAT export (P6b) |
| `Approach` | 0 (1 fixture) | WOCAT id | WOCAT export (P6b) |
| `GuidanceDoc` | 0 | Tier-2 document id | reserved for P6b |

Node ids are `"<NodeType>:<key>"`, so the type id-spaces are disjoint and the
graph round-trips through JSON without a side index.

### `ContextClass` kinds

`rainfall_band`, `agroclimatic_zone`, `slope_class`, `altitude_zone`,
`soil_texture`, `soil_depth`, `topsoil_om`.

QT §5.2 **landform** is a real questionnaire vocabulary and is transcribed in
`wocat_taxonomy.CONTEXT_CLASSES`, but it is kept as a `Technology` attribute
rather than promoted to a node: the P6a brief fixes the seven kinds above,
and landform is not one of the context dimensions the recommender's own
raster stack can supply, so it cannot participate in context matching.

## Edge types

| Edge | From → To | Attributes | Provenance values used |
|---|---|---|---|
| `IN_FAMILY` | Practice → PracticeFamily | — | `era_rows`, `csa_rows` |
| `COMPOSED_OF` | Practice → PracticeComponent | `position` | `era_rows`, `csa_rows` |
| `REPORTS_EFFECT` | Study → Practice | `indicator`, `n_obs`, `mean_log_rr`, `median_log_rr`, `share_positive`, `aez_belts`, `crop_groups` | `era_rows`, `csa_rows` |
| `STUDIED_IN` | Study → AEZBelt | `n_obs` | `era_rows`, `csa_rows` |
| `MEASURES` | Indicator → ImpactVariable | `direction_good`, `proxy`, `role`, `rationale` | `wocat_taxonomy` |
| `MAPS_TO` | PracticeComponent → SLMMeasure \| SLMGroup | `confidence`, `status`, `rationale`, `owner_note` | `crosswalk_validated`, `crosswalk_auto` |
| `USES_MEASURE` | Technology → SLMMeasure | — | `wocat_fixture`, `wocat_export` |
| `IN_GROUP` | Technology → SLMGroup | — | `wocat_fixture`, `wocat_export` |
| `ADDRESSES` | Technology → DegradationType | — | `wocat_fixture`, `wocat_export` |
| `APPLIED_IN` | Technology \| Approach \| Study → Country | — | all |
| `HAS_CONTEXT` | Technology → ContextClass | `kind` | `wocat_fixture`, `wocat_export` |
| `REPORTS_IMPACT` | Technology → ImpactVariable | `rating`, `rating_index`, `good_direction` | `wocat_fixture`, `wocat_export` |
| `LINKED_APPROACH` | Technology → Approach | — | `wocat_fixture`, `wocat_export` |

`REPORTS_EFFECT` carries one parallel edge per indicator (multigraph key
`REPORTS_EFFECT:<indicator>`); `STUDIED_IN`, `HAS_CONTEXT`, `REPORTS_IMPACT`,
`USES_MEASURE`, `IN_GROUP` and `ADDRESSES` key on their target.

### Provenance vocabulary

`era_rows` · `csa_rows` · `manifest` · `wocat_taxonomy` · `crosswalk_auto` ·
`crosswalk_validated` · `wocat_fixture` · `wocat_export`.

`validate_graph()` rejects any edge without one of these.

## The derived component layer

`CSA_practices` is a frozen data contract and is never rewritten. Components
are a new layer on top of it:

* **split** on `-`, except for the literals in `PROTECTED_COMPONENTS` whose
  own names contain a hyphen (`In-situ water harvesting` must not become
  `In` + `situ water harvesting`). Labels with no hyphen — including
  `Intercropping or Rotation` — stay one component;
* **normalize** each piece through `ALIASES`, which absorbs the two sources'
  case conventions (ERA Title Case vs CSA lower case) and the typos frozen
  into the strings (`Drought tolerrant crops`, `organic amedements`).

Measured on the real dataset: **100 practices → 46 raw `-`-split tokens → 45
after protecting `In-situ water harvesting` → 44 canonical components.**
The only cross-source alias cluster is
`Deficit Irrigation` (ERA) / `Deficit irrigation` (CSA).

**Aliasing is deliberately narrow.** Only case and spelling variants of the
*same* label merge. Semantically adjacent but differently named practices
from the two sources — `Organic Fertilizer` (ERA) vs `Organic Amendments`
(CSA), `Reduced Tillage` (ERA) vs `Conservation Tillage` (CSA), and the four
SWC labels — are kept apart. Merging them is a research judgement for the
owner, and the WOCAT crosswalk already relates them downstream by mapping
both onto the same SLM measures. This is why the component count is 44 and
not the ~30 a more aggressive merge would give.

## Usage

```bash
# Build from the repo data (no WOCAT records, no crosswalk admitted yet)
python rag/graph/build_graph.py

# Build including the hand-built WOCAT fixtures
python rag/graph/build_graph.py --wocat rag/ingest/wocat/fixtures

# Propose the crosswalk for the owner to validate in Excel
python rag/graph/crosswalk/propose_crosswalk.py
python rag/graph/crosswalk/propose_crosswalk.py --llm     # owner only

# Tests (no network, no chromadb, no raster stack)
python -m pytest rag/graph/test_graph.py rag/ingest/wocat/test_wocat.py -q
```

```python
from rag.graph.query import GraphQuery

gq = GraphQuery.load()                                    # rag/graph/store/graph.json
gq.evidence_summary("Mulch-Reduced Tillage", "yield")     # studies + dataset aggregates
gq.components_of("Mulch-Reduced Tillage")                 # ['Mulch', 'Reduced Tillage']
gq.slm_measures_for("Mulch")                              # validated crosswalk rows ONLY
gq.related_practices("Mulch", k=5)                        # shared components / studies
gq.similar_context_technologies({"agroclimatic_zone": "sub-humid"}, "Mulch")
gq.explain_paths("Mulch-Reduced Tillage", "yield")        # provenance chains
```

## The crosswalk gate

`propose_crosswalk.py` always writes `status=proposed` with a blank
`owner_decision`. `build_graph.py` admits a row into `MAPS_TO` **only** when
`owner_decision` (or `status`) reads `validated`; `--include-proposed` admits
proposed rows but tags them `crosswalk_auto` so the two can never be
confused, and `rejected` rows are admitted under neither flag.
`query.slm_measures_for()` and `explain_paths()` filter to
`status == "validated"` regardless of how the graph was built, so an
unvalidated guess can never reach an advisory.

## Store

`store/graph.json` and `store/graph_report.json` are git-ignored and rebuilt
by `build_graph.py`. The build is deterministic — sorted nodes, sorted links,
sorted JSON keys, floats rounded to 6 dp — so two runs over unchanged inputs
produce byte-identical files (asserted in `test_graph.py`).

## Sources and licence

The WOCAT vocabularies are transcribed from WOCAT (2019), *Questionnaire on
Sustainable Land Management (SLM) Technologies*, English version, CDE,
University of Bern — [DOCX](https://wocat.net/documents/447/QT_English_2019_CClicence.docx).
The questionnaire and the data documented through WOCAT are
**CC BY-NC-SA 4.0 International** (stated in QT §1.3): attribution to WOCAT
and the compilers, a link to the original, and share-alike on derived data.

WOCAT records reach this repo through the owner's research data export,
requested via the Alliance Bioversity-CIAT / WOCAT partnership. **Bulk or
automated fetching of wocat.net is forbidden** and nothing in `rag/graph` or
`rag/ingest/wocat` fetches anything.
