# Backend — AgroAdvisor-ET API (FastAPI)

Wraps the canonical recommender engine (`recommend.py` + `advisor_agent.py`, the
**source of truth** for all ML logic) behind a clean service layer and exposes:

| Endpoint | Purpose |
|---|---|
| `GET /health` | Liveness + `model_loaded` + version |
| `GET /metadata` | 5 practice families, 7 indicators (key/label/direction), crop types, Ethiopia bounds, honest model metrics |
| `GET /context?lat=&lon=` | Auto-derived agro-ecological context (aez_belt + features) for a map point |
| `POST /recommend` | Two-tier recommendation (`query` / clean `recommendations` / `details`) |
| `POST /chat` | OpenAI tool-calling advisor → SSE stream (clean text + structured recommendation event) |
| `POST /explain` | Grounded, cited explanation of a `/recommend` payload (RAG over the ERA source studies); 503 until the index is built |
| `GET /models` | The single current model's descriptor |

The user provides only: **lat, lon, practice_family, indicator, and an optional
crop_type**. Everything else (rainfall, altitude, slope, soil, zone …) is sampled
from the raster stack by the engine — never typed.

## Layout

```
app/backend/
  recommend.py              # canonical engine — DO NOT fork; wrapped by the service
  advisor_agent.py          # canonical LLM advisor (system prompt, tool, offline fallback)
  groq_agent.py             # backward-compat shim → advisor_agent
  artifacts/csa_model.joblib, model_metrics.json
  dataset/CSA_ERA_final_model_ready.csv
  layers/                   # empty by default — see "Raster stack" below
  aez_belt_lookup.csv
  app/
    services/               # recommender_service, chat_service (thin wrappers)
    routers/                # recommend, chat, metadata, health, models
    schemas.py, config.py, helpers.py, metadata_service.py
```

## Raster stack (LAYERS_DIR)

The 11-layer GeoTIFF stack (~730 MB) lives **once** in the repo at
`../../geodata/layers/`. The engine finds it via `LAYERS_DIR`:

- **Local dev:** set `LAYERS_DIR=../../geodata/layers` in `backend/.env`
  (relative paths resolve against `backend/`), or copy the GeoTIFFs into
  `backend/layers/`.
- **Docker:** nothing to do — `docker-compose.yml` mounts `geodata/layers`
  read-only at `/srv/layers`, the default location.

Startup **fails fast** with a clear message listing any missing file.

## Setup

```bash
cd app/backend
python -m venv .venv
# Windows: .venv\Scripts\activate
# Unix:    source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then set OPENAI_API_KEY (sk-...) and LAYERS_DIR
```

`scikit-learn` is pinned to `1.7.2` to match the pickled model (avoids version
warnings / silent drift).

## Run

```bash
uvicorn app.main:app --reload --port 8000
```

Open http://127.0.0.1:8000/docs

## LLM provider

OpenAI is the chat provider: set `OPENAI_API_KEY` in `backend/.env`; the model
and endpoint are pinned in `app/services/openai_chat.py` (`gpt-4o-mini` by
default). If `OPENAI_API_KEY` is unset, `/chat` still works end to end via the
canonical rule-based `AgroAdvisor` offline fallback in `advisor_agent.py` —
useful for local dev and tests. No key ever leaves the backend.

The `/explain` layer (`app/services/explain_service.py`) is separate from chat:
it retrieves evidence chunks from the RAG index (`rag/retrieve.py`, locations
configurable via `RAG_INDEX_DIR` / `RAG_CHUNKS_PATH`, defaults at
`../../rag/index/store` and `../../rag/corpus/chunks.jsonl`) and asks the LLM
to explain the recommendation citing passages as `[n]`, with a numeric
guardrail: any number not present in the recommendation JSON or the cited
chunks discards the LLM text in favour of a deterministic citation-grounded
template. The `citations` list is deduped per study (`era_code`): the
top-ranked chunk supplies the snippet and `n_passages` counts how many
retrieved passages that study contributed. Without `OPENAI_API_KEY` the
endpoint still works and returns that deterministic fallback
(`llm_used=false`); without the index it returns 503 and `GET /metadata`
reports `rag_ready=false`.

## Tests

```bash
pytest -q
```

Covers: recommend happy path (clean + details, `top_n` respected, evidence-grounded),
a known-point sanity check (8.38, 39.37 · erosion · soil loss → mulch/water-harvesting),
bounds + enum 422s, `/metadata` shape, `/health`, and the offline chat path.
