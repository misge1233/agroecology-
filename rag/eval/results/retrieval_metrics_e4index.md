# Retrieval evaluation — hybrid RagRetriever vs silver era_code labels

Success@k (≥1 relevant study in the top k — the primary metric) precedes Recall@k (corpus-coverage diagnostic). Strict labels: family + indicator + practice. `(fam)` columns: family + indicator only.

| group | n | success@4 | success@8 | success@16 | recall@4 | recall@8 | recall@16 | mrr | success@4 (fam) | success@8 (fam) | success@16 (fam) | recall@4 (fam) | recall@8 (fam) | recall@16 (fam) | mrr (fam) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **overall** | 50 | 0.380 | 0.520 | 0.600 | 0.110 | 0.220 | 0.299 | 0.315 | 0.480 | 0.580 | 0.660 | 0.075 | 0.151 | 0.209 | 0.382 |

## Per practice family
| group | n | success@4 | success@8 | success@16 | recall@4 | recall@8 | recall@16 | mrr | success@4 (fam) | success@8 (fam) | success@16 (fam) | recall@4 (fam) | recall@8 (fam) | recall@16 (fam) | mrr (fam) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Agro-forestry and forest management | 5 | 0.200 | 0.200 | 0.200 | 0.050 | 0.050 | 0.050 | 0.050 | 0.200 | 0.200 | 0.200 | 0.018 | 0.036 | 0.036 | 0.050 |
| Crop production and management | 14 | 0.286 | 0.500 | 0.571 | 0.059 | 0.168 | 0.250 | 0.264 | 0.357 | 0.500 | 0.571 | 0.029 | 0.117 | 0.165 | 0.321 |
| Erosion control and water management | 12 | 0.417 | 0.583 | 0.667 | 0.058 | 0.293 | 0.347 | 0.312 | 0.750 | 0.833 | 0.917 | 0.101 | 0.188 | 0.266 | 0.525 |
| Integrated soil fertility management | 10 | 0.600 | 0.700 | 0.800 | 0.155 | 0.188 | 0.262 | 0.476 | 0.600 | 0.700 | 0.800 | 0.085 | 0.148 | 0.187 | 0.476 |
| Livestock production and management | 9 | 0.333 | 0.444 | 0.556 | 0.244 | 0.333 | 0.489 | 0.365 | 0.333 | 0.444 | 0.556 | 0.133 | 0.222 | 0.322 | 0.365 |

## Per indicator
| group | n | success@4 | success@8 | success@16 | recall@4 | recall@8 | recall@16 | mrr | success@4 (fam) | success@8 (fam) | success@16 (fam) | recall@4 (fam) | recall@8 (fam) | recall@16 (fam) | mrr (fam) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| SOM content | 8 | 0.250 | 0.375 | 0.500 | 0.167 | 0.292 | 0.417 | 0.225 | 0.250 | 0.375 | 0.625 | 0.083 | 0.150 | 0.237 | 0.237 |
| biomass yield | 10 | 0.600 | 0.600 | 0.600 | 0.240 | 0.281 | 0.307 | 0.450 | 0.800 | 0.800 | 0.800 | 0.139 | 0.166 | 0.216 | 0.533 |
| income | 6 | 0.167 | 0.333 | 0.667 | 0.056 | 0.083 | 0.333 | 0.224 | 0.167 | 0.333 | 0.667 | 0.033 | 0.054 | 0.158 | 0.224 |
| runoff | 4 | 0.000 | 0.750 | 1.000 | 0.000 | 0.500 | 0.600 | 0.175 | 0.500 | 1.000 | 1.000 | 0.083 | 0.375 | 0.458 | 0.267 |
| soil loss | 4 | 0.500 | 0.500 | 0.500 | 0.062 | 0.219 | 0.281 | 0.375 | 0.500 | 0.500 | 0.500 | 0.111 | 0.250 | 0.306 | 0.500 |
| water use efficiency | 8 | 0.125 | 0.125 | 0.125 | 0.025 | 0.050 | 0.050 | 0.125 | 0.125 | 0.125 | 0.125 | 0.016 | 0.031 | 0.031 | 0.125 |
| yield | 10 | 0.700 | 0.900 | 0.900 | 0.099 | 0.209 | 0.260 | 0.490 | 0.800 | 0.900 | 0.900 | 0.060 | 0.163 | 0.214 | 0.645 |
