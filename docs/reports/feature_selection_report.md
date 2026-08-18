# Feature Selection — Decision

**Method:** HistGradientBoostingRegressor (native categorical handling, no target-encoding
leakage) with **GroupKFold by `Study_No_`**; grouped permutation importance on held-out
studies; numeric multicollinearity scan. Target: `log_response_ratio`.

## Findings
- **Performance (GroupKFold, honest):** R² ≈ 0.15, RMSE ≈ 0.58 (log-ratio units). Effect-size
  prediction across heterogeneous studies is inherently hard.
- **Per-indicator out-of-fold R²:** yield +0.035, biomass +0.045; income, SOM, soil loss,
  runoff, WUE negative (barely beat the mean). → weak-indicator recommendations need a
  confidence flag.
- **Permutation importance:** `Indicator` (0.32) and `CSA_practices` (0.27) dominate;
  `crop_type` (0.06) and `precip_seasonality` (0.04) modest; `aez_belt`/`Crop_group`/
  `practice_family`/`land_cover` small-positive; `soil_soc`/`soil_ph`/`lgp_days`/`Altitude_r`
  ≈0 or negative.
- **Multicollinearity:** `Altitude_r`≈`temp_mean_annual` (0.94); `Rainfall`≈`soil_ph` (0.82).

## Decision — 13 model-input features

**Keep (required, design):** `CSA_practices`, `practice_family`, `Indicator`.
**Keep (context):** `crop_type`, `Crop_group`, `aez_belt`, `Rainfall`, `temp_mean_annual`,
`precip_seasonality`, `slope`, `soil_clay`, `land_cover`, **`Altitude_r`**.
**Drop from model inputs:** `lgp_days`, `soil_ph`, `soil_soc` (≈0/negative importance;
`soil_ph` also collinear with `Rainfall`).

Rationale for **keeping `Altitude_r`** despite r=0.94 with temperature: altitude is a primary
agro-ecological driver in Ethiopia (the belt system is altitude-based); its low permutation
importance is a redundancy artifact (temperature carries the same signal), not evidence it is
uninformative. We use a **tree ensemble**, which is robust to correlated inputs (collinearity
harms linear models and importance attribution, not tree predictions). Empirically the
13-feature set matches/slightly beats the 16-feature set (R² 0.159 vs 0.151, RMSE 0.582),
so keeping altitude and dropping the 3 is both scientifically sound and marginally better.

**Dropped features remain available to the explanation (Groq) layer** — `lgp_days`, `soil_ph`,
`soil_soc` (and everything else in the stack) can be cited to explain *why* a practice fits a
site, even though they are not model inputs.

## Implications for the recommender
- Use the model primarily to **rank practices within a family for a goal** — its strongest,
  most reliable signals (`CSA_practices` × `Indicator`) are exactly the ranking-relevant ones.
- Show predicted % change **with a confidence flag**; treat weak-indicator magnitudes as
  indicative, backed by evidence counts.

## Recommended verification / modelling settings (next phase)
- Validation: GroupKFold(5) by `Study_No_`; report per-indicator and per-source metrics.
- Candidate models: HistGradientBoosting (primary), RandomForest, and a mean-per
  (practice×indicator) baseline to confirm the model adds value.
