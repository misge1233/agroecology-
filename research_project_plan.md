# Research Project Plan — AgroAdvisor-ET: AI-Powered Agroecology+ Solutions

**Project short title:** AI-Powered Agroecology+ Solutions
**System name:** **AgroAdvisor-ET** (evolves from the AgroGuide prototype)
**Author / PI:** Misganu Tuse — Alliance of Bioversity International & CIAT
**Prepared:** 18 August 2026 · **Status:** v1.1 (19 Aug 2026) — Phase-2 corpus
expansion (GARDIAN-CIGI + CGSpace) pulled FORWARD, before the expert study and
manuscript, under a strict two-tier corpus architecture (see §2.5). P0–P3
complete; progress.md in the repo is the execution log of record.

---

## 0. Executive summary

We have a working end-to-end prototype (AgroGuide) that recommends climate-smart
agriculture practices for any point in Ethiopia: 8,664 harmonized paired field
observations (ERA ≈ 84% + CSA workbook ≈ 16%, 337 studies) → an 11-layer, 250 m
geospatial feature stack → a GroupKFold-validated RandomForest ranking engine →
a FastAPI + Next.js app with an LLM layer that explains but never invents numbers.

This plan upgrades that prototype into a **publication-grade, production-grade
system** in three moves:

1. **Reframe** — from "CSA recommender" to **Agroecology+ advisory**: the ML model
   ranks practices from field evidence; a **retrieval-augmented generation (RAG)**
   layer grounds every explanation in the *actual source literature* — starting
   with the ~295 DOI-linked papers behind the ERA training data itself. The model
   owns the numbers; RAG owns the science behind them.
2. **Reorganize** — a new clean, standard research-repo structure; originals kept,
   nothing deleted, every move documented in a migration map.
3. **Publish** — a systems/methods manuscript targeted at
   **Computers and Electronics in Agriculture** (Elsevier), with the hybrid
   ML + RAG architecture and its evaluation as the core contribution.

The unique, publishable idea in one sentence:
> *A recommender whose explanation layer retrieves from the same peer-reviewed
> studies its prediction model was trained on — closing the loop between
> meta-analytic evidence, machine learning, and grounded advisory text.*

To our knowledge, no published agricultural decision-support system does this;
it is a clean, defensible novelty claim.

---

## 1. Framing the idea

### 1.1 From CSA to Agroecology+

"CSA recommender" undersells the system and ties it to one framing. The
reframe:

- **Agroecology+** = agroecological practice recommendation **plus** three
  guarantees that plain LLM advice cannot make:
  - **Evidence-ranked** — every ranking comes from a model trained on paired
    with/without field experiments (effect sizes, not opinions);
  - **Context-resolved** — one map pin auto-derives the full agro-ecological
    context (AEZ belt + 10 geospatial features at 250 m), zero numbers typed;
  - **Literature-grounded** — every explanation is backed by retrieved,
    citable passages from the source studies and CGIAR knowledge products.
- CSA remains a *lens* inside the system (the practice families and much of the
  evidence), not its identity. The five practice families already span crop,
  livestock, soil fertility, erosion/water, and agroforestry — i.e., the
  agroecological practice space; the vocabulary in the UI, API, code, and paper
  shifts from "CSA practices" to "agroecological practices (including CSA)".

### 1.2 The hybrid architecture (the paper's core figure)

```
                      ┌─────────────────────────────────────────┐
 User (pin + goal or  │            AgroAdvisor-ET               │
 free-text question)  │                                         │
        │             │  ┌───────────┐    ┌──────────────────┐  │
        ▼             │  │ Geospatial │   │  Evidence model  │  │
  Slot extraction ────┼─▶│ context    │──▶│  (RandomForest,  │  │
  (LLM / rules)       │  │ engine     │   │  ranks practices)│  │
                      │  └───────────┘    └────────┬─────────┘  │
                      │                            │ ranked JSON │
                      │  ┌─────────────────────────▼──────────┐ │
                      │  │        RAG explanation layer        │ │
                      │  │  retrieve: practice × context ×     │ │
                      │  │  indicator → passages from ERA      │ │
                      │  │  source papers (+ CGSpace/GARDIAN)  │ │
                      │  │  generate: grounded, cited advisory │ │
                      │  └─────────────────────────┬──────────┘ │
                      └────────────────────────────┼────────────┘
                                                   ▼
                        Advisory: ranked practices + % effect +
                        confidence + cited "why & how" per practice
```

**Division of labour (extends the current "honesty" design):**

| Layer | Owns | Never does |
|---|---|---|
| RandomForest model | all effect sizes, rankings, confidence flags | explain |
| Geospatial engine | the context (AEZ belt + 10 features from lat/lon) | — |
| RAG layer | *why it works here* + *how to implement*, with citations | invent or alter numbers |
| LLM | phrasing, dialogue, slot extraction | free-form agronomic claims |

RAG serves two distinct functions, and the paper should name them:

- **R1 — Evidence grounding (explanation):** for each recommended practice,
  retrieve passages from the source studies (matched on practice, similar AEZ /
  rainfall / slope context, and indicator) that describe mechanisms and observed
  outcomes. The advisor cites them: *"Soil bunds reduced soil loss 60–98% in
  highland Vertisol trials [Adimassu 2017; NJ0128]"*.
- **R2 — Advisory enrichment (implementation):** retrieve implementation
  guidance the effect-size model cannot know — spacing, timing, labour, costs,
  complementary practices, known failure modes — from CGIAR knowledge products
  (Phase 2 corpus). This is what turns a *ranking* into an *advisory*.

### 1.3 Naming and title

- **System:** AgroAdvisor-ET (repo/app); tagline "AI-Powered Agroecology+
  Solutions". The deck's "AgroGuide" is acknowledged as the prototype name.
- **Working manuscript title (primary):**
  > **"AgroAdvisor-ET: coupling meta-analytic machine learning with
  > retrieval-augmented generation for evidence-grounded agroecological
  > practice recommendation in Ethiopia"**
- Alternates to keep in reserve:
  - "From evidence to advisory: a hybrid machine-learning and
    retrieval-augmented-generation system for context-specific agroecological
    practice recommendation"
  - "Evidence in, advice out: an AI advisor that ranks agroecological practices
    from field trials and explains them from the literature"

### 1.4 Contribution claims (what reviewers must be able to verify)

1. A harmonization pipeline unifying two evidence corpora (ERA + national CSA
   workbook) into one effect-size dataset (documented, reproducible).
2. A train/serve-consistent 250 m geospatial context engine (11 aligned layers;
   one pin → full feature row; zero train/serve skew).
3. A grouped-validation ranking model with honest per-indicator confidence —
   framed explicitly as a *ranking* tool (CV R² ≈ 0.19 reported, not hidden;
   this honesty is a strength in review, not a weakness).
4. **New:** a RAG layer over the model's own evidence base (295 DOI-linked
   studies) with quantitative faithfulness/grounding evaluation.
5. **New:** end-to-end system evaluation including expert review of advisories.

---

## 2. RAG integration — engineering plan

### 2.1 Corpus (phased, per decision)

**Phase 1 — ERA source papers (v1, the paper's corpus):**
- The raw `ERA_Ethiopia_dataset.csv` carries `DOI`, `Author`, `Journal`, `Code`
  per row: **306 unique studies, 295 unique DOIs** (verified 18 Aug 2026).
- Acquisition pipeline: DOI list → Crossref (metadata) → open-access resolution
  (Unpaywall / publisher OA / CGSpace mirror) → PDF/XML download where licensed
  → for closed papers, fall back to abstract + metadata only (recorded per
  study). Also query the Harvard Dataverse API for the ERA deposit itself
  (documentation + any bundled docs).
- Every chunk keeps provenance: `{doi, era_code, title, year, section}` — the
  `era_code` (`Study_No_`) is the join key that links a retrieved passage to
  the exact training rows behind a recommendation. **This linkage is the
  novelty; implement it as a first-class metadata field.**

**Phase 2 — guidance-corpus expansion (v1.1: moved BEFORE the expert study
and manuscript):** CGSpace REST API (CGIAR publications) and the GARDIAN-CIGI
HF dataset (85,782 processed docs) filtered to Ethiopia / agroecology / the
five practice families — powering R2 implementation guidance.

### 2.5 Two-tier corpus architecture (binding design rule, v1.1)

- **Tier 1 — Evidence corpus (FROZEN):** the ~300 ERA source studies with the
  `era_code` ↔ training-row linkage. Chroma collection `era_corpus`. Basis of
  the R1 explanation function, the retrieval/faithfulness evaluation, and the
  paper's novelty claim. Never mixed with Tier 2.
- **Tier 2 — Guidance corpus (NEW):** GARDIAN-CIGI + CGSpace documents,
  filtered to Ethiopia + agroecological practices. Separate Chroma collection
  (`guidance_corpus`), separate manifest, `tier` recorded on every chunk.
  Powers R2 (implementation how-to, costs, timing, caveats). Cited in the UI
  as distinct "guidance" chips; the numeric guardrail applies identically.
- Rationale: the expert study rates the enriched system (strongest headline
  experiment), while Tier-1 metrics already computed remain valid — expansion
  adds a capability without touching the evaluated evidence base.

### 2.2 Pipeline & stack (as built; updated v1.1)

| Stage | Choice (as built) | Rationale |
|---|---|---|
| Text extraction | pypdf for PDFs + JATS XML (Europe PMC) for full text; references trimmed | simple, robust; XML gives clean full text for OA papers |
| Chunking | paragraph-aware, ~380 words (~512 tokens), 60-word overlap | standard, works well for scientific prose |
| Embeddings | `text-embedding-3-small` (OpenAI API) | cheap (<$1 per full rebuild); swappable |
| Vector store | **Chroma** (embedded) v1 → Qdrant if scaled | zero-ops, fits the Docker deployment; no new infra |
| Retrieval | hybrid dense + BM25 with reciprocal-rank fusion; per-practice queries; top-k≈8 | practice/indicator-structured queries exploit the recommendation JSON — most RAG systems don't have one |
| Generation | OpenAI-first (`gpt-4o-mini`), no tools, temperature 0.2; deterministic offline fallback | reuses the app's single LLM configuration; works keyless |
| Guardrail | every number in advisory text must appear in the model JSON or a cited chunk (regex check); guardrail trip → deterministic fallback | extends the existing honesty machinery |

**Key design point:** the RAG *query is not the user's free text* — it is the
**structured recommendation output** (practice + resolved context + indicator).
This makes retrieval precise and is a nice methodological point for the paper.

### 2.3 New backend surface (wrap, never fork — same doctrine as today)

- `rag/` package: `ingest/` (DOI fetch, parse, chunk, embed), `index/` (store),
  `retrieve.py` (structured query builder), and the backend's
  `explain_service.py` (grounded generation).
- API: `POST /explain` (recommendation JSON → cited explanation);
  `/chat` gains grounded follow-ups; `/metadata` reports corpus stats.
- UI: citations rendered as expandable "Evidence" chips on practice cards;
  "why?" answers show sources.

### 2.4 RAG evaluation (reviewers will ask)

- **Retrieval:** Success@k / Recall@k / MRR against a silver-labelled set
  (~50 queries: practice × context × indicator → known relevant studies via
  the `era_code` ↔ training-row linkage). Primary metric: **Success@k**
  (≥1 relevant study retrieved — the grounding guarantee the system is
  designed for); Recall@k/MRR secondary — see progress.md P3 review for the
  rationale.
- **Groundedness/faithfulness:** RAGAS-style faithfulness + citation precision
  (does each cited passage actually support the sentence?), sample audited by
  hand.
- **Answer quality:** blinded expert rating (3–5 agronomists / extension
  specialists) of advisories for ~30 scenario prompts across AEZ belts —
  model-only vs model+RAG (this comparison is the paper's headline experiment).
- **Ablation:** no-RAG / RAG-unfiltered / RAG-with-metadata-filter.

---

## 3. Project reorganization — new clean structure, originals kept

New top-level layout (created alongside the current folders; files **copied or
moved with a written migration map**; `_archive/` holds superseded items;
nothing deleted):

```
AI_BAsed_Agroecology+/
├── agroadvisor-et/                  # ← the clean, canonical repo (git)
│   ├── README.md                    # system overview (from SYSTEM_OVERVIEW.md, updated)
│   ├── docs/
│   │   ├── reports/                 # all preprocessing/feature/merge reports (.md)
│   │   ├── data_dictionary.md
│   │   └── decisions/               # feature decision, crosswalk rules, RAG design
│   ├── data/
│   │   ├── raw/                     # ERA_Ethiopia_dataset.csv, CSA workbook  (git-ignored/DVC)
│   │   ├── processed/               # *_model_ready.csv, merged final
│   │   └── lookups/                 # aez_belt_lookup, aez_attributes, grid_definition
│   ├── geodata/
│   │   ├── layers/                  # 11 GeoTIFFs + VRT (git-ignored; fetch script)
│   │   └── sources/                 # shapefiles: agroecology_belt, AEZ_32, soil_wrb1…
│   ├── pipelines/
│   │   ├── features/                # get_*.py, build_stack.py, extract_features.py…
│   │   └── dataset/                 # preprocessing + merge + practice-family scripts
│   ├── model/
│   │   ├── train_model.py, feature_selection.py
│   │   └── artifacts/               # csa_model.joblib, model_metrics.json
│   ├── rag/                         # NEW (see §2.3)
│   ├── app/
│   │   ├── backend/                 # FastAPI app (current agroecology_ai/backend)
│   │   └── frontend/                # Next.js app
│   ├── paper/
│   │   ├── manuscript/              # main.docx/md, cover letter, highlights
│   │   ├── figures/                 # scripted figures (make_maps.py output etc.)
│   │   └── references/              # .bib, ERA DOI list
│   ├── docker-compose.yml
│   └── .gitignore                   # excludes .venv, __pycache__, .next, node_modules,
│                                    #   large rasters/zips, raw WorldClim archives
├── _archive/                        # superseded/duplicate copies (e.g. the older
│                                    #   feature_stack copies of recommend/groq_agent)
└── (original folders untouched until you confirm deletion — never assumed)
```

Hygiene actions bundled with the reorg: single canonical copy of
`recommend.py`/`groq_agent.py`/artifacts (backend is canonical; feature_stack
copies archived); the two ~1–4 GB WorldClim zips in `feature_stack/raw/` stay
out of git with a `fetch_data.sh` script instead; a `MIGRATION_MAP.md` lists
every file's old → new path.

---

## 4. Manuscript plan — Computers and Electronics in Agriculture

**Article type:** Original research (systems + methods). ~8,000–9,500 words,
6–8 figures, 3–4 tables. CEA expects rigorous evaluation, reproducibility, and
data/code availability — all achievable here.

### 4.1 Skeleton mapped to existing assets

| Section | Content | Already have |
|---|---|---|
| 1. Introduction | evidence–advice gap in Ethiopian/African extension; why context-specific; why LLM advice alone is untrustworthy; contributions list | deck slides 1–3 |
| 2. Related work | agri decision-support & recommenders; meta-analysis (ERA); LLM/RAG in agriculture (thin literature — advantage) | needs lit search |
| 3. Data | two corpora, harmonization rules, crosswalk, final dataset table | 4 preprocessing reports (near paper-ready) |
| 4. Geospatial context engine | 11 layers, grid, train/serve consistency, fallback | reports + deck 8–11 |
| 5. Ranking model | feature selection, GroupKFold, baselines, per-indicator confidence | feature_selection_report, metrics.json |
| 6. RAG explanation layer | corpus, linkage design, retrieval, generation, guardrails | §2 of this plan (built) |
| 7. System | architecture, API, UI, honesty-by-design | deck 15–19, code |
| 8. Evaluation | model metrics; RAG metrics; expert study (model vs model+RAG); ablations | harness built; runs pending |
| 9. Discussion | ranking-not-forecasting honesty; imbalance & thin indicators; transferability beyond Ethiopia; limitations | deck 13, 19–20 |
| 10. Conclusion | | |

**Figures:** F1 architecture; F2 data harmonization flow (PRISMA-style row
counts); F3 stack maps (from `make_maps.py`); F4 permutation importance +
per-indicator R²; F5 RAG pipeline + linkage; F6 worked example (pin → ranked
cards → cited explanation); F7 expert-evaluation results.

**Statements:** data availability (ERA via Harvard Dataverse DOI; merged
dataset + code on GitHub/Zenodo), AI-use disclosure, author contributions
(CRediT). Anticipated reviewer pushbacks and our pre-loaded answers: low R²
(→ ranking framing + baseline comparison + confidence flags), source imbalance
(→ per-source metrics + source-as-diagnostic), practice-taxonomy granularity
(→ crosswalk section + limitation).

### 4.2 Writing order

Methods-first (Sections 3–5 are transcriptions of existing reports) → build &
evaluate RAG → Sections 6–8 → Introduction/Discussion last → internal
co-author review → CEA submission.

---

## 5. Phased roadmap

| Phase | Work | Output | Status (19 Aug 2026) |
|---|---|---|---|
| **P0 · Reorganize** | clean repo, migration map, git | clean repo | ✅ done |
| **P1 · Reframe** | AgroAdvisor-ET rebrand, LAYERS_DIR, OpenAI-first | consistent system | ✅ done |
| **P2 · RAG build (Tier 1)** | ERA corpus (306 studies; 40 full-text, 208 contributing), index, `/explain`, Evidence UI | working grounded advisory | ✅ done |
| **P3 · Evaluation harness** | silver-label retrieval metrics (Success@8=0.56, MRR=0.32), faithfulness audit, expert-study materials | results for Sec. 8 | ✅ harness done; faithfulness run + expert study pending |
| **P5 · Guidance corpus (Tier 2)** ← *v1.1: pulled forward* | GARDIAN-CIGI (filtered) + CGSpace ingestion → `guidance_corpus`; two-tier retrieval/explain; guidance chips in UI; WUE query-expansion fix | enriched advisory for the expert study | ⏳ next |
| **P3-run · Expert study** | run faithfulness audit + blinded expert study on the ENRICHED system | headline results | after P5 |
| **P4 · Manuscript** | scripted results tables; Sections 3–5 first, then 6–8, Intro/Discussion last | submission-ready draft | starts in parallel with P5 |
| **P6 · Submission & release** | Zenodo deposit, cover letter, submit to CEA | submission | final |

---

## 6. Open items

1. **Expert panel (the only open item):** 3–5 named AEZ/extension specialists
   for the blinded study — invite before P5 completes so the study can run
   on the enriched system without delay. Placeholders stand in
   `paper/manuscript/manuscript_skeleton.md`.

*Resolved: plan approved and P0–P3 executed (see progress.md); co-authors =
Misganu Tuse (CIAT Addis Ababa) + Wuletawu Abera (CIAT Accra); no
institutional clearance needed; branding, journal (CEA), and reorg decisions
locked 18 Aug 2026.*