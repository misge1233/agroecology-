# Retrieval evaluation — hybrid RagRetriever vs silver era_code labels

Success@k (≥1 relevant study in the top k — the primary metric) precedes Recall@k (corpus-coverage diagnostic). Strict labels: family + indicator + practice. `(fam)` columns: family + indicator only.

| group | n | success@4 | success@8 | success@16 | recall@4 | recall@8 | recall@16 | mrr | success@4 (fam) | success@8 (fam) | success@16 (fam) | recall@4 (fam) | recall@8 (fam) | recall@16 (fam) | mrr (fam) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **overall** | 50 | 0.400 | 0.560 | 0.660 | 0.111 | 0.245 | 0.357 | 0.300 | 0.480 | 0.600 | 0.720 | 0.087 | 0.181 | 0.261 | 0.394 |

## Per practice family
| group | n | success@4 | success@8 | success@16 | recall@4 | recall@8 | recall@16 | mrr | success@4 (fam) | success@8 (fam) | success@16 (fam) | recall@4 (fam) | recall@8 (fam) | recall@16 (fam) | mrr (fam) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Agro-forestry and forest management | 5 | 0.000 | 0.400 | 0.400 | 0.000 | 0.250 | 0.250 | 0.080 | 0.200 | 0.400 | 0.400 | 0.036 | 0.255 | 0.255 | 0.140 |
| Crop production and management | 14 | 0.357 | 0.571 | 0.643 | 0.060 | 0.187 | 0.304 | 0.272 | 0.357 | 0.571 | 0.643 | 0.029 | 0.143 | 0.209 | 0.326 |
| Erosion control and water management | 12 | 0.417 | 0.667 | 0.667 | 0.058 | 0.304 | 0.347 | 0.263 | 0.667 | 0.833 | 0.917 | 0.093 | 0.201 | 0.288 | 0.568 |
| Integrated soil fertility management | 10 | 0.600 | 0.600 | 0.900 | 0.159 | 0.172 | 0.377 | 0.423 | 0.600 | 0.600 | 0.900 | 0.122 | 0.136 | 0.250 | 0.423 |
| Livestock production and management | 9 | 0.444 | 0.444 | 0.556 | 0.267 | 0.333 | 0.489 | 0.379 | 0.444 | 0.444 | 0.556 | 0.156 | 0.222 | 0.322 | 0.379 |

## Per indicator
| group | n | success@4 | success@8 | success@16 | recall@4 | recall@8 | recall@16 | mrr | success@4 (fam) | success@8 (fam) | success@16 (fam) | recall@4 (fam) | recall@8 (fam) | recall@16 (fam) | mrr (fam) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| SOM content | 8 | 0.250 | 0.625 | 0.750 | 0.167 | 0.542 | 0.667 | 0.203 | 0.250 | 0.625 | 0.875 | 0.125 | 0.400 | 0.512 | 0.214 |
| biomass yield | 10 | 0.600 | 0.600 | 0.600 | 0.246 | 0.266 | 0.304 | 0.450 | 0.700 | 0.800 | 0.800 | 0.135 | 0.155 | 0.197 | 0.570 |
| income | 6 | 0.167 | 0.167 | 0.667 | 0.056 | 0.056 | 0.389 | 0.207 | 0.167 | 0.167 | 0.667 | 0.033 | 0.033 | 0.192 | 0.207 |
| runoff | 4 | 0.000 | 1.000 | 1.000 | 0.000 | 0.425 | 0.475 | 0.175 | 0.500 | 1.000 | 1.000 | 0.083 | 0.292 | 0.375 | 0.292 |
| soil loss | 4 | 0.500 | 0.500 | 0.500 | 0.062 | 0.250 | 0.281 | 0.208 | 0.500 | 0.500 | 0.500 | 0.111 | 0.278 | 0.306 | 0.500 |
| water use efficiency | 8 | 0.125 | 0.125 | 0.250 | 0.025 | 0.025 | 0.175 | 0.133 | 0.125 | 0.125 | 0.250 | 0.016 | 0.016 | 0.094 | 0.133 |
| yield | 10 | 0.800 | 0.900 | 0.900 | 0.095 | 0.200 | 0.270 | 0.503 | 0.900 | 0.900 | 0.900 | 0.087 | 0.170 | 0.237 | 0.683 |
