# Build Prompt — Agroecology AI (CSA Practice Recommender) Web App

## Your role
You are a **senior full-stack AI engineer**. Build this into a **production-grade** web app on
the existing stack (FastAPI + Next.js 15/React 19/TypeScript/Tailwind). The repo already
contains an earlier implementation built for a *previous* design. **The ML model, its input
features, the recommendation logic, and the output style have all changed.** The new runtime
artifacts are already copied into `backend/`. Your job: **inspect the current code, then update
it to the new model, contract, and UX** — don't rebuild from scratch, refactor what's there.

## Working method (do this first — do not skip)
1. **Inspect** the whole repo before editing: `backend/app/**`, `backend/recommend.py`,
   `backend/groq_agent.py`, `backend/tests/**`, `frontend/src/**`, both `README.md`,
   `docker-compose.yml`, Dockerfiles, `.env.example` files.
2. Produce a short written **gap analysis** (old vs new) and a migration plan before coding.
3. Refactor incrementally; keep the app runnable at each step; run tests as you go.
4. **Do not** reimplement the ML logic — `backend/recommend.py` and `backend/groq_agent.py`
   are the **source of truth**. Wrap them behind a clean service layer.
5. Never commit secrets. `GROQ_API_KEY` comes from env only.

---

## 1. What the system does now (ground truth)

A decision-support recommender: a user drops a **map pin (lat/long)** in Ethiopia, picks a
**challenge area** and an **objective**, optionally names a **crop**, and gets a short, clean
list of recommended Climate-Smart Agriculture (CSA) practices. A chat assistant (Groq LLM)
presents it naturally and, only when asked "why/how/etc.", explains using evidence + local
context. All numbers come from the model; the LLM never invents them.

### User inputs (the ONLY things the user provides)
| Input | Required | Notes |
|---|---|---|
| `lat`, `lon` | ✅ | Map pin or numeric entry. Ethiopia bounds: lat 3.3–14.9, lon 32.9–48.2. |
| `practice_family` | ✅ | Dropdown: "What challenge would you like to solve?" (5 options below) |
| `indicator` | ✅ | Dropdown: "What is your objective?" (7 options below) |
| `crop_type` | optional | Free/typeahead; blank = general advice |

Everything else is **auto-derived** from lat/long via the raster stack (never typed by the
user): `aez_belt` + 10 features. There is **no manual Region / Agro_zone / Rainfall / Altitude
entry anymore** (that was the old design — remove it).

**practice_family options (exactly these 5 strings):**
- `Crop production and management`
- `Livestock production and management`
- `Integrated soil fertility management`
- `Erosion control and water management`
- `Agro-forestry and forest management`

**indicator options (7) — show the friendly label, send the key:**
| UI label | key |
|---|---|
| Increase crop yield | `yield` |
| Increase biomass / fodder | `biomass yield` |
| Increase income | `income` |
| Improve water-use efficiency | `water use efficiency` |
| Improve soil organic matter | `SOM content` |
| Reduce soil loss / erosion | `soil loss` |
| Reduce runoff | `runoff` |

### The recommendation engine (already in `backend/recommend.py`)
```python
recommend(lat, lon, practice_family, indicator, crop_type=None, top_n=3) -> dict
```
Returns a **two-tier** dict:
```jsonc
{
  "query": {"lat":..., "lon":..., "practice_family":..., "indicator":..., "crop_type":..., "goal_direction":"increase|reduce"},
  "recommendations": [                       // CLEAN — the only thing shown by default
     {"practice": "...", "effect": "~67% reduce in soil loss"}, ...
  ],
  "details": {                               // shown ONLY when the user asks why/explain
     "context": {"aez_belt":"Dry Kolla","Rainfall":756,"temp_mean_annual":20.7,
                 "precip_seasonality":84,"Altitude_r":1416,"slope":2.3,"soil_clay":31.7,
                 "land_cover":30,"lgp_days":214,"soil_ph":7.7,"soil_soc":27.9},
     "crop_group": "Cereal|null",
     "confidence": "high|medium|low",
     "ranked": [{"practice":"...","pct_change":-67.1,"log_ratio":-1.11,"n_evidence":3}, ...],
     "n_candidates": 21,
     "note": "..."
  }
}
```
- Context is extracted from lat/long by sampling GeoTIFFs in `backend/layers/` (nearest-valid
  fallback). Model + encoders in `backend/artifacts/csa_model.joblib`. Candidate practices &
  evidence counts come from `backend/dataset/CSA_ERA_final_model_ready.csv`. Zone names from
  `backend/aez_belt_lookup.csv`. These relative paths already resolve from `backend/`.

### The chat brain (already in `backend/groq_agent.py`)
`CSAAdvisor` exposes `recommend()` to Groq as a function-calling tool with a system prompt that
enforces: **clean/short/context-led default answers**; evidence, confidence, and numeric
context surfaced **only** on follow-up "why/how/how-sure/compare/…"; intelligently handle any
follow-up intent; re-call the tool if goal/family/crop/location change; never fabricate numbers.
It has an offline rule-based fallback when `GROQ_API_KEY` is unset (keep for local/dev/tests).

### Model reality (be honest in UX)
Pooled RandomForest; grouped R² ≈ 0.19 (≈ evidence mean). It is a **ranking** tool. Default UI
shows only the clean recommendation. Evidence counts + confidence exist to **justify on
request**, not to decorate the default answer.

---

## 2. Current repo (what exists) & the gap

Stack (keep it): Backend FastAPI (`backend/app/`, uvicorn, pydantic v2, groq). Frontend Next.js
15 App Router, React 19, TS, Tailwind, framer-motion, recharts, react-markdown, lucide.

**Old design still wired in the code — must be replaced:**
| Old (remove/replace) | New |
|---|---|
| Manual context: `Crop_group, Region, Agro_zone, Rainfall, Altitude_r` | `lat, lon` → auto context; user also picks `practice_family` + `indicator`; optional `crop_type` |
| Model features incl. `CSA_catago, Region, Agro_zone` (7) | 13 features incl. `CSA_practices, practice_family, aez_belt, temp_mean_annual, precip_seasonality, slope, soil_clay, land_cover` |
| `app/recommender.py` + `registry.py` + `direction_map.json` + monorepo `outputs/` paths | `backend/recommend.py` (self-contained) as the engine |
| `app/llm/chat.py` + `system_prompt.md` asking for 6 fields incl. rainfall/altitude medians | `backend/groq_agent.py` `CSAAdvisor` (tool-calling, clean-by-default) |
| Flat output: `predicted_ratio, pct_change, evidence_in_zone, confidence` all exposed | Two-tier: clean `recommendations` by default; `details` only on "why" |
| `evidence_only`, `top_n` up to 21 exposed in UI | Internal only; UI shows top 3 clean |
| Frontend collects rainfall/altitude/region/zone | Frontend collects map pin + 2 dropdowns + optional crop |

Concrete files embodying the old contract to update: `backend/app/schemas.py`,
`app/recommender.py`, `app/registry.py`, `app/routers/{recommend,chat,metadata,models,health}.py`,
`app/llm/{chat.py,system_prompt.md}`, `app/metadata_service.py`, `app/config.py`,
`app/helpers.py`, `backend/tests/test_api.py`; frontend `src/lib/{types.ts,api.ts}`,
`src/components/*`, `src/app/**`.

---

## 3. Backend tasks

1. **Service layer.** Add `app/services/recommender_service.py` that imports and calls
   `recommend()` from `backend/recommend.py` (treat it as canonical; do not duplicate its
   logic). Load the model + rasters **once at startup** (FastAPI lifespan / singleton) so the
   joblib and GeoTIFF handles are warm; sampling per request stays fast. If import-path issues
   arise, add `backend/` to `sys.path` or move `recommend.py`/`groq_agent.py` under `app/services/`
   **preserving identical logic and the relative data/layers/artifacts paths**.
2. **New schemas** (`app/schemas.py`, pydantic v2):
   - `RecommendRequest { lat: float, lon: float, practice_family: enum(5), indicator: enum(7),
     crop_type: str|None, top_n: int=3 }` with validators: Ethiopia bounds, enum membership.
   - `RecommendResponse` mirroring the two-tier dict: `query`, `recommendations:[{practice,effect}]`,
     `details:{context, crop_group, confidence, ranked:[{practice,pct_change,log_ratio,n_evidence}],
     n_candidates, note}`.
   - Keep a typed error envelope.
3. **Endpoints:**
   - `POST /recommend` → calls the service, returns the two-tier response. Validate inputs;
     clear 422 on out-of-bounds/unknown enum.
   - `POST /chat` → drives `CSAAdvisor` (Groq tool-calling). **Keep SSE streaming** (the frontend
     expects `text/event-stream`). Integrate `groq_agent`'s tool + system prompt with the existing
     streaming mechanism: stream assistant tokens; emit a structured event when a recommendation
     is produced (so the UI can render the clean cards) while the assistant text stays clean.
     Preserve conversation history; re-call the tool when the user changes location/goal/crop.
   - `GET /metadata` → now returns: `practice_families` (5), `indicators` (7 with label+key+direction),
     `crop_types` (from the dataset), Ethiopia bounds, and honest model metrics from
     `artifacts/model_metrics.json`. Drop regions/agro_zones/rainfall-altitude ranges.
   - `GET /health` → liveness + model loaded + version. `GET /models` → keep or simplify to the
     single current model; remove the monorepo registry paths.
4. **Config/env:** `GROQ_API_KEY`, `GROQ_MODEL` (default `llama-3.3-70b-versatile`),
   `ALLOWED_ORIGINS`, chat rate limit. Fix `config.py` paths to the new `backend/`-relative
   layout (no monorepo `outputs/`, `data/processed`). Update `.env.example`.
5. **Robustness:** startup check that model + all required layers + dataset exist (fail fast with
   a clear message). Handle points outside Ethiopia and unknown crop gracefully. Structured
   logging with request IDs. CORS from env. Rate-limit `/chat`. Never expose raw stack traces.
6. **Tests** (`backend/tests/`, pytest): recommend happy path (returns clean + details, top_n
   respected, evidence-grounded), bounds/enum validation errors, `/metadata` shape, `/health`,
   chat offline-fallback path (no API key) end-to-end, and a known-point sanity check
   (e.g. lat 8.38, lon 39.37, Erosion control, soil loss → mulch/water-harvesting practices).

---

## 4. Frontend tasks

1. **Inputs UI** (replace the old manual-context form). Location has **two synced entry modes**
   for the same point:
   - **Map pin (primary):** add `react-leaflet` + `leaflet` with OSM tiles; click/drag to drop
     or move the pin.
   - **Numeric lat/long entry (alternative):** two number fields the user can type directly.
   The two must stay **in sync** — dropping/moving the pin fills the lat/long fields, and editing
   the fields moves the pin (and recenters the map). Validate Ethiopia bounds (lat 3.3–14.9,
   lon 32.9–48.2) in both modes with a clear inline message when out of range, and show the
   resolved `aez_belt` zone once a valid point is set.
   Plus two dropdowns (**challenge** = practice_family, **objective** = indicator) and an optional
   **crop** typeahead. Remove all Region/Agro_zone/Rainfall/Altitude inputs.
2. **Default result = clean & short.** Render only `recommendations` (practice name + one-line
   effect) as tidy cards; lead with the context-aware sentence the assistant returns. Do **not**
   show percentages tables, evidence counts, or confidence badges by default.
3. **Explain on demand.** Provide a subtle "Why this?" / "Explain" affordance (and it also works
   via chat) that reveals `details` — local context (zone, rainfall, soil, slope), evidence
   counts, confidence, and the estimated effect — using the assistant's explanation. `recharts`
   may visualize the ranked `pct_change` only inside this expanded/explanation view.
4. **Chat panel:** natural conversation that can both collect the inputs and answer follow-ups;
   consume the SSE stream; render clean assistant text (react-markdown) and the recommendation
   cards from the structured event. Keep it friendly and concise.
5. **Rewire lib:** update `src/lib/types.ts` and `src/lib/api.ts` to the new request/response
   shapes and `/metadata`; drop `FarmContext`, `predicted_ratio`, `evidence_*`, region/zone.
   Fetch enums/labels from `/metadata` (don't hardcode) but the 5/7 lists above are the contract.
6. **UX/quality:** loading and error states, mobile-responsive, accessible (labels, keyboard,
   ARIA), graceful message when a point is outside Ethiopia, and when confidence is low the
   explanation should say evidence is limited (honesty). Keep framer-motion polish tasteful.

---

## 5. API contract (target)

```
POST /recommend
  req:  { "lat":8.38, "lon":39.37, "practice_family":"Erosion control and water management",
          "indicator":"soil loss", "crop_type":null, "top_n":3 }
  res:  { query, recommendations:[{practice,effect}], details:{...} }   // see §1

POST /chat  (SSE; text/event-stream)
  req:  { "message":"...", "history":[{role,content}], "stream":true }
  events: token stream + a structured "recommendation" event {query, recommendations, details}
          + done/error. Assistant text is clean; details used only when the user asks why.

GET /metadata -> { practice_families:[5], indicators:[{key,label,direction}], crop_types:[...],
                   bounds:{lat:[3.3,14.9],lon:[32.9,48.2]}, model:{name,cv_r2,note} }
GET /health   -> { status, model_loaded, version }
```

---

## 6. Non-functional / production requirements
- **Performance:** load model + open raster datasets once at startup; keep per-request latency
  low (point sampling only). Cache the dataset/candidate lists in memory.
- **Reliability:** fail-fast startup validation; typed errors; no stack traces to clients;
  timeouts on Groq calls; offline fallback keeps `/chat` working without a key.
- **Security:** secrets via env only; `.env` git-ignored; CORS locked to configured origins;
  input validation on every endpoint; basic rate limiting on `/chat`.
- **DevEx & deploy:** update `backend/README.md`, `frontend/README.md`, `.env.example` (both),
  `requirements.txt` (add `rasterio`), frontend `package.json` (add map lib if used), Dockerfiles
  and `docker-compose.yml` so `docker compose up` runs the full stack; ensure `backend/layers/`,
  `artifacts/`, `dataset/`, `aez_belt_lookup.csv` are present in the image/volume (they are large
  ~730 MB rasters — mount or copy appropriately, document it).
- **Tests & CI-ready:** backend pytest green; frontend `vitest` for lib/util changes; lint clean.

## 7. Definition of done
- Old manual-context flow fully removed; new lat/long + 2-dropdown + optional-crop flow works
  end to end (form and chat).
- `/recommend` returns the two-tier response; UI shows only the clean list by default and
  reveals `details` on "why".
- `/chat` streams, understands free-text, returns clean answers, explains intelligently on
  follow-ups, and never invents numbers.
- Honest, evidence-grounded behavior; graceful handling of out-of-Ethiopia points, unknown
  crops, and missing API key.
- Backend tests pass; `docker compose up` serves API + UI; READMEs and `.env.example` updated.
- Deliver a short migration summary of what changed and any decisions/assumptions.

## 8. Constraints
- Treat `backend/recommend.py` and `backend/groq_agent.py` as canonical logic — wrap, don't fork.
- Keep the existing tech stack and project structure; refactor rather than rewrite.
- Ask for clarification only if genuinely blocked; otherwise proceed with sensible, documented
  defaults. Work in small, verifiable steps.
