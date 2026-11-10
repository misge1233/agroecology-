# AgroEcoAdvisor — AI-Powered Agroecology+ Solutions

**Evidence-grounded agroecological practice recommendation for Ethiopia.**
A user drops a map pin, states a challenge and an objective — AgroEcoAdvisor ranks
agroecological practices (including CSA) by expected effect from 8,664 paired
with/without field observations, and explains each recommendation with passages
retrieved from the peer-reviewed studies the model itself was trained on.

> Every number has a source, and the best evidence leads. The field-trial model,
> study-level field evidence, retrieved passages, guidance and the knowledge graph
> are fused per practice (`docs/decisions/evidence_fusion.md`); the LLM phrases
> and cites, it never invents or alters a number.

Evolved from the **AgroGuide** prototype (see `docs/presentations/`).
Full project plan: `../research_project_plan.md`.

## Architecture

```
pin + goal / free text
        │
        ▼
 geospatial context engine ──▶ evidence model (RandomForest) ──▶ ranked practices
 (AEZ belt + 10 features,       trained on ERA + CSA corpus       + % effect
  250 m stack, one pin)         GroupKFold by study               + confidence
        │                                                             │
        └──────────────▶  RAG explanation layer  ◀────────────────────┘
                          retrieves from the ~300 DOI-linked ERA
                          source papers (+ CGIAR corpora, phase 2)
                          → cited "why it works here" + "how to apply"
```

## Repository layout

| Path | Contents |
|---|---|
| `data/raw/` | ERA Ethiopia dataset (Harvard Dataverse), CSA workbook — inputs, never edited |
| `data/processed/` | model-ready CSVs (harmonized, merged; see `docs/reports/`) |
| `data/lookups/` | AEZ belt lookup/attributes, grid definition, demo points |
| `data/evidence/` | the unified evidence store (`evidence_rows.parquet`/`.csv`, git-ignored), manifest, data cards, `registry_ET.json` |
| `data/taxonomy/` | practice, outcome and challenge taxonomies, aliases, review sheets, parsed catalogue, crop lookup |
| `geodata/layers/` | the 11 aligned 250 m GeoTIFFs + VRT (git-ignored — see `geodata/README.md`) |
| `geodata/sources/` | AEZ shapefiles, soil grids, agroclimatic rasters |
| `pipelines/features/` | scripts that built the raster stack + `extract_features.py` (train/serve shared) |
| `pipelines/dataset/` | dataset harmonization / practice-family crosswalk scripts |
| `pipelines/evidence/` | unified evidence store (E1): schema, loaders (ERA, CSA, Habtamu), catalogue parser, store and registry builders, reconciliation |
| `pipelines/taxonomy/` | practice/outcome/challenge taxonomy rules, review sheets, `propose_mappings.py` (rules propose, a human ticks) |
| `countries/` | country configuration (`ET.yaml` active, `KE.yaml` draft); loader in `pipelines/common/country_config.py` |
| `model/` | `train_model.py`, `feature_selection.py`, trained artifact + metrics |
| `rag/` | RAG corpus acquisition, indexing, retrieval, evaluation (phase 2 of the plan) |
| `app/backend/` | FastAPI service wrapping the canonical engine (`recommend.py`, advisor) |
| `app/frontend/` | Next.js UI — guided chat + map finder |
| `docs/` | preprocessing reports, data dictionary, design decisions, prototype deck |
| `paper/` | manuscript, figures, references (target: *Computers and Electronics in Agriculture*) |

**Evidence store (E1, 10 Nov 2026).** `countries/` holds the country configuration, so Ethiopia is one instance of a general pipeline. `pipelines/evidence/` loads ERA Ethiopia, the Adimassu CSA compilation and Habtamu Sewnet's extraction database into one frozen schema with provenance and writes `data/evidence/` (store, data cards, challenge registry served by `GET /registry`); `pipelines/taxonomy/` maps every raw practice and outcome label onto the taxonomies in `data/taxonomy/` by rules, with review sheets for a human to tick. The current dataset, model and engine are unchanged. See `data/evidence/README.md` and `docs/decisions/enhancement_v2.md`.

`MIGRATION_MAP.md` records where every file came from in the original project
folders (which remain untouched).

## Quick start

```bash
# Backend (requires geodata/layers — see geodata/README.md and app/backend/layers/README.md)
cd app/backend
python -m venv .venv && . .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Frontend (trilingual UI: /en, /am, /om — the proxy picks the language from
# the agro-locale cookie, then Accept-Language, then English)
cd app/frontend
cp .env.example .env.local
npm ci && npm run dev            # http://localhost:3000/en
npm test && npm run lint         # vitest (i18n guards included) + eslint
npm run build && npm run e2e     # production build + Playwright end-to-end (mocked API)
```

Optional: set `OPENAI_API_KEY` in `app/backend/.env` to let the chat read free text
in Amharic / Afaan Oromoo (one validated LLM call); without it the chat guides those
users through the quick-reply chips and the Advisor, which need no model.

Docker: `docker compose up --build` from the repo root (rasters mounted read-only).

## Honesty by design

Grouped cross-validated R² ≈ 0.19 (per-indicator and per-source metrics in
`model/artifacts/model_metrics.json`) — this is a **ranking** tool, not a yield
forecaster. Thin-evidence objectives ship with a low-confidence flag; the advisor
says so instead of bluffing. Coordinates outside Ethiopia are rejected, not
extrapolated. Every preprocessing drop is a documented rule (`docs/reports/`).

## Authors

Misganu Tuse¹, Wuletawu Abera²
¹ International Center for Tropical Agriculture (CIAT), Addis Ababa, Ethiopia
² International Center for Tropical Agriculture (CIAT), Accra, Ghana
