# Retrieval evaluation — hybrid RagRetriever vs silver era_code labels

Strict labels: family + indicator + practice. `(fam)` columns: family + indicator only.

| group | n | recall@4 | recall@8 | recall@16 | mrr | recall@4 (fam) | recall@8 (fam) | recall@16 (fam) | mrr (fam) |
|---|---|---|---|---|---|---|---|---|---|
| **overall** | 50 | 0.111 | 0.235 | 0.333 | 0.321 | 0.080 | 0.162 | 0.237 | 0.402 |

## Per practice family
| group | n | recall@4 | recall@8 | recall@16 | mrr | recall@4 (fam) | recall@8 (fam) | recall@16 (fam) | mrr (fam) |
|---|---|---|---|---|---|---|---|---|---|
| Agro-forestry and forest management | 5 | 0.000 | 0.250 | 0.250 | 0.069 | 0.036 | 0.255 | 0.255 | 0.129 |
| Crop production and management | 14 | 0.060 | 0.187 | 0.304 | 0.271 | 0.029 | 0.108 | 0.173 | 0.325 |
| Erosion control and water management | 12 | 0.058 | 0.262 | 0.331 | 0.318 | 0.093 | 0.164 | 0.272 | 0.568 |
| Integrated soil fertility management | 10 | 0.159 | 0.172 | 0.277 | 0.466 | 0.089 | 0.136 | 0.200 | 0.466 |
| Livestock production and management | 9 | 0.267 | 0.333 | 0.489 | 0.379 | 0.156 | 0.222 | 0.322 | 0.379 |

## Per indicator
| group | n | recall@4 | recall@8 | recall@16 | mrr | recall@4 (fam) | recall@8 (fam) | recall@16 (fam) | mrr (fam) |
|---|---|---|---|---|---|---|---|---|---|
| SOM content | 8 | 0.167 | 0.542 | 0.667 | 0.257 | 0.083 | 0.338 | 0.425 | 0.268 |
| biomass yield | 10 | 0.246 | 0.266 | 0.304 | 0.450 | 0.135 | 0.155 | 0.197 | 0.570 |
| income | 6 | 0.056 | 0.056 | 0.389 | 0.207 | 0.033 | 0.033 | 0.192 | 0.207 |
| runoff | 4 | 0.000 | 0.425 | 0.475 | 0.175 | 0.083 | 0.292 | 0.375 | 0.292 |
| soil loss | 4 | 0.062 | 0.125 | 0.281 | 0.375 | 0.111 | 0.167 | 0.306 | 0.500 |
| water use efficiency | 8 | 0.025 | 0.025 | 0.025 | 0.125 | 0.016 | 0.016 | 0.031 | 0.125 |
| yield | 10 | 0.095 | 0.200 | 0.270 | 0.503 | 0.087 | 0.170 | 0.237 | 0.683 |
