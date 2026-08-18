# Backend — FastAPI CSA Recommender API

Wraps the canonical recommender engine (`recommend.py` + `groq_agent.py`, the
**source of truth** for all ML logic) behind a clean service layer and exposes:

| Endpoint | Purpose |
|---|---|
| `GET /health` | Liveness + `model_loaded` + version |
| `GET /metadata` | 5 practice families, 7 indicators (key/label/direction), crop types, Ethiopia bounds, honest model metrics |
| `GET /context?lat=&lon=` | Auto-derived agro-ecological context (aez_belt + features) for a map point |
| `POST /recommend` | Two-tier recommendation (`query` / clean `recommendations` / `details`) |
| `POST /chat` | Groq tool-calling advisor → SSE stream (clean text + structured recommendation event) |
| `GET /models` | The single current model's descriptor |

The user provides only: **lat, lon, practice_family, indicator, and an optional
crop_type**. Everything else (rainfall, altitude, slope, soil, zone …) is sampled
from the raster stack by the engine — never typed.

## Layout

```
backend/
  recommend.py              # canonical engine — DO NOT fork; wrapped by the service
  groq_agent.py             # canonical LLM advisor (system prompt, tool, offline fallback)
  artifacts/csa_model.joblib, model_metrics.json
  dataset/CSA_ERA_final_model_ready.csv
  layers/*.tif              # GeoTIFF stack (~730 MB) sampled per request
  aez_belt_lookup.csv
  app/
    services/               # recommender_service, chat_service (thin wrappers)
    routers/                # recommend, chat, metadata, health, models
    schemas.py, config.py, helpers.py, metadata_service.py
```

The engine resolves `artifacts/`, `dataset/`, `layers/`, `aez_belt_lookup.csv`
relative to its own location. The service layer puts `backend/` on `sys.path`,
imports the engine, and warms the model once at startup (FastAPI lifespan). Startup
**fails fast** with a clear message if any required file is missing.

## Setup

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
# Unix:    source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # optionally add OPENAI_API_KEY for OpenAI chat
```

`scikit-learn` is pinned to `1.7.2` to match the pickled model (avoids version
warnings / silent drift).

## Run

```bash
uvicorn app.main:app --reload --port 8000
```

Open http://127.0.0.1:8000/docs

## Chat without a key

If `OPENAI_API_KEY` is unset, `/chat` still works end to end via the canonical
rule-based `CSAAdvisor` fallback in `groq_agent.py` — useful for local dev and tests.

## Tests

```bash
pytest -q
```

Covers: recommend happy path (clean + details, `top_n` respected, evidence-grounded),
a known-point sanity check (8.38, 39.37 · erosion · soil loss → mulch/water-harvesting),
bounds + enum 422s, `/metadata` shape, `/health`, and the offline chat path.
