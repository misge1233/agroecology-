# CSA Practice Recommender — System Overview

End-to-end decision-support system that recommends Climate-Smart Agriculture (CSA)
practices for a location in Ethiopia, grounded in a meta-analysis of paired
`with`/`without` CSA experiments (CSA workbook + ERA database).

## Goal

From a user's location and goal, rank CSA practices by their expected effect and explain
the recommendation in plain language. Three components:

1. **One ML model** — predicts the response ratio of a practice from practice + context + indicator.
2. **`recommend()`** — the recommendation logic (defines model input/output and ranking).
3. **Groq (LLM) layer** — understands the user, calls the model, explains the results.

Front end / back end will later be built with Claude Code; this phase produces the model,
the `recommend()` contract, and the Groq usage design.

## What the user provides (front-end inputs)

| # | UI prompt | Maps to | Required? | Choices |
|---|---|---|---|---|
| 1 | "Where is your site?" (map pin or type lat/long) | `latitude`, `longitude` | **Required** | — |
| 2 | "What challenge would you like to solve / get a recommendation about?" | `practice_family` | **Required** | the 5 families (see below) |
| 3 | "What is your objective?" | `Indicator` | **Required** | the 7 indicators (see below) |
| 4 | "Any specific crop?" | `crop_type` | Optional | crop list; blank = general advice |

**Question 2 — practice_family (pick one to scope the recommendation):**
- Crop production and management
- Livestock production and management
- Integrated soil fertility management
- Erosion control and water management
- Agro-forestry and forest management

**Question 3 — Indicator / objective (pick one), phrased for users:**
- Increase crop yield → `yield`
- Increase biomass / fodder yield → `biomass yield`
- Increase income → `income`
- Improve water-use efficiency → `water use efficiency`
- Improve soil organic matter → `SOM content`
- Reduce soil loss / erosion → `soil loss`
- Reduce runoff → `runoff`

From lat/long the system **auto-derives** (feature stack, nearest-valid fallback), with no
numbers typed by the user: `aez_belt` + the 10 stack features (Rainfall, Altitude_r, slope,
temp_mean_annual, precip_seasonality, lgp_days, soil_clay, soil_ph, soil_soc, land_cover).
If `crop_type` is given, `Crop_group` is derived from it; if left blank the model marginalises
over crop.

So the user answers **1 map pin + 2 dropdowns (+ optional crop)**; everything else is computed.

## The model

- **Task:** regression. **Target:** `log_response_ratio` (= ln(MeanT/MeanC)); report as % change.
- **Inputs (one row per candidate practice):** `CSA_practices` (candidate), `practice_family`,
  `Crop_group`, `crop_type`, `aez_belt`, `Indicator`, and the 10 stack features.
- **Trained on:** `dataset/CSA_ERA_final_model_ready.csv` (8,664 rows, 337 studies).
- **Validation:** GroupKFold by `Study_No_` (a study contributes up to 539 rows → prevent leakage).
- **Not inputs:** `source`, `Study_No_`, `latitude`, `longitude`, `response_ratio`.

## recommend() — the recommendation logic

```
recommend(lat, lon, practice_family, indicator, crop_type=None, top_n=3) -> dict
```
`practice_family` and `indicator` are **required** (the two user dropdowns); `crop_type` optional.
Steps:
1. Extract context from lat/long: `aez_belt` + 10 stack features (+ derive `Crop_group` if
   `crop_type` given; else treat crop as unspecified/marginalise).
2. Build the candidate list: all `CSA_practices` seen in the data within the chosen
   `practice_family`, compatible with the context.
3. For each candidate, assemble a feature row (candidate practice + fixed context + indicator)
   and predict `log_response_ratio`.
4. Convert to % change, rank by the indicator's "better" direction (higher for
   yield/biomass/income/WUE/SOM; lower for soil loss/runoff).
5. Attach evidence: number of supporting observations and an agreement/confidence flag.

**Output (JSON for the LLM):** the resolved context, the goal, and a ranked list of
`{practice, practice_family, predicted_pct_change, direction, n_evidence, confidence}`.

## Groq (LLM) usage

1. **Parse** free-text user input → structured `{lat, lon, indicator, practice_family?, crop_type?}`.
2. **Call** `recommend(...)` — the ML model produces the numbers (the LLM never invents effects).
3. **Explain** the returned ranked JSON in clear language, honouring confidence flags.
4. **Follow-up:** answer "why" by grounding in the dataset and known agronomic facts —
   the local context (e.g. "your zone is Dry Kolla, ~600 mm, clay-rich alkaline soil"),
   the evidence behind the ranking (n studies, effect size), and domain reasoning (e.g. why
   soil bunds cut soil loss on slopes). It explains, it does not fabricate numbers.

Separation of duties: the **model** owns the numbers; **Groq** owns understanding and explanation.

## Build phases (this track) — COMPLETE

1. ✅ Feature selection → 13 features (`feature_selection_report.md`).
2. ✅ Model training & selection → RandomForest, GroupKFold (`train_model.py`, `artifacts/`).
3. ✅ `recommend()` → two-tier output (`recommend.py`).
4. ✅ Groq wiring → `CSAAdvisor` agent (`groq_agent.py`); offline fallback for keyless testing.

### Runtime pieces
- `extract_features.py` / stack layers — lat/long → context.
- `recommend.py` — `recommend(lat, lon, practice_family, indicator, crop_type=None, top_n=3)`.
- `artifacts/csa_model.joblib` — model + encoders + confidence map.
- `groq_agent.py` — `CSAAdvisor().chat(text)`; set `GROQ_API_KEY` for live LLM
  (default model `llama-3.3-70b-versatile`), else a rule-based offline fallback runs.

### For the Claude Code front/back end (later)
Backend: import `CSAAdvisor`, expose `POST /chat` (session-held conversation) and optionally
`POST /recommend` (direct tool call). Front end: map pin + 2 dropdowns (family, objective) +
optional crop; show only the clean `recommendations`; reveal `details` when the user asks why.
Secrets: `GROQ_API_KEY` in backend env.

## Key considerations carried forward
- Practice vocabularies differ by source; `practice_family` harmonises scope, `CSA_practices`
  is the specific output (mixed granularity — a later refinement).
- Source/indicator imbalance (ERA 84%; yield 68%) → evaluate per indicator and per source.
- Rare practices have thin evidence → confidence flag in output.
