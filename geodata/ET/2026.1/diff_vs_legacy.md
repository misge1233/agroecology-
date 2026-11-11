# Diff: ET/2026.1 versus legacy stack layers/

Per layer: identical or changed by data checksum (SHA-256 of the pixel values); for changed layers the mean and quantile shift over the country mask (new minus old), the median and p99 of the absolute cell difference, and the cells valid now but nodata before (newly filled). A layer with a `legacy_tolerance` in `sources.yaml` (elevation, slope) is accepted when its median and p99 absolute difference are within it; every other legacy layer must be equal.

| Layer | Change | Mean shift | p5 / p50 / p95 shift | Max abs diff | Cells changed (classes) | Median / p99 abs diff | Newly valid cells |
|---|---|---|---|---|---|---|---|
| `aez_belt` | identical |  |  |  |  |  |  |
| `precip_annual` | identical |  |  |  |  |  |  |
| `temp_mean_annual` | changed | +0 | +0 / +0 / +0 | 1.907e-06 |  | 0 / 0 | 0 |
| `precip_seasonality` | identical |  |  |  |  |  |  |
| `lgp_days` | identical |  |  |  |  |  |  |
| `elevation` | changed, within tolerance | +0 | -0.003104 / -0.01282 / +0.06763 | 61.43 |  | 0.02881 / 6.17 | 0 |
| `slope` | changed, within tolerance | +0.08519 | +0.0009383 / +0.03169 / +0.3474 | 18.92 |  | 0.00922 / 1.89 | 0 |
| `soil_clay` | identical |  |  |  |  |  |  |
| `soil_ph` | identical |  |  |  |  |  |  |
| `soil_soc` | identical |  |  |  |  |  |  |
| `land_cover` | identical |  |  |  |  |  |  |
