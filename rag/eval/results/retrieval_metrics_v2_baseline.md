# Retrieval evaluation — hybrid RagRetriever vs silver era_code labels

Success@k (≥1 relevant study in the top k — the primary metric) precedes Recall@k (corpus-coverage diagnostic). Strict labels: family + indicator + practice. `(fam)` columns: family + indicator only.

| group | n | success@4 | success@8 | success@16 | recall@4 | recall@8 | recall@16 | mrr | success@4 (fam) | success@8 (fam) | success@16 (fam) | recall@4 (fam) | recall@8 (fam) | recall@16 (fam) | mrr (fam) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **overall** | 45 | 0.378 | 0.556 | 0.600 | 0.103 | 0.230 | 0.317 | 0.351 | 0.489 | 0.600 | 0.689 | 0.072 | 0.143 | 0.229 | 0.444 |

## Per practice family
| group | n | success@4 | success@8 | success@16 | recall@4 | recall@8 | recall@16 | mrr | success@4 (fam) | success@8 (fam) | success@16 (fam) | recall@4 (fam) | recall@8 (fam) | recall@16 (fam) | mrr (fam) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Agro-forestry and forest management | 5 | 0.000 | 0.400 | 0.400 | 0.000 | 0.250 | 0.250 | 0.069 | 0.200 | 0.400 | 0.400 | 0.036 | 0.255 | 0.255 | 0.129 |
| Crop production and management | 14 | 0.357 | 0.571 | 0.643 | 0.060 | 0.187 | 0.304 | 0.271 | 0.357 | 0.571 | 0.643 | 0.029 | 0.108 | 0.173 | 0.325 |
| Erosion control and water management | 13 | 0.462 | 0.692 | 0.769 | 0.165 | 0.354 | 0.513 | 0.472 | 0.692 | 0.769 | 1.000 | 0.100 | 0.163 | 0.367 | 0.638 |
| Integrated soil fertility management | 10 | 0.600 | 0.600 | 0.600 | 0.166 | 0.186 | 0.208 | 0.550 | 0.700 | 0.700 | 0.700 | 0.134 | 0.151 | 0.185 | 0.650 |
| Livestock production and management | 3 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |

## Per indicator
| group | n | success@4 | success@8 | success@16 | recall@4 | recall@8 | recall@16 | mrr | success@4 (fam) | success@8 (fam) | success@16 (fam) | recall@4 (fam) | recall@8 (fam) | recall@16 (fam) | mrr (fam) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| SOM content | 8 | 0.250 | 0.625 | 0.750 | 0.125 | 0.500 | 0.625 | 0.257 | 0.250 | 0.625 | 0.875 | 0.125 | 0.338 | 0.425 | 0.268 |
| biomass yield | 9 | 0.444 | 0.444 | 0.444 | 0.149 | 0.178 | 0.201 | 0.389 | 0.667 | 0.667 | 0.667 | 0.051 | 0.069 | 0.137 | 0.611 |
| income | 6 | 0.333 | 0.333 | 0.500 | 0.139 | 0.139 | 0.361 | 0.344 | 0.333 | 0.333 | 0.500 | 0.054 | 0.054 | 0.254 | 0.344 |
| runoff | 4 | 0.000 | 1.000 | 1.000 | 0.000 | 0.425 | 0.475 | 0.175 | 0.500 | 1.000 | 1.000 | 0.083 | 0.292 | 0.375 | 0.292 |
| soil loss | 4 | 0.500 | 0.500 | 0.500 | 0.062 | 0.125 | 0.281 | 0.375 | 0.500 | 0.500 | 0.500 | 0.111 | 0.167 | 0.306 | 0.500 |
| water use efficiency | 6 | 0.167 | 0.167 | 0.167 | 0.033 | 0.033 | 0.033 | 0.167 | 0.167 | 0.167 | 0.333 | 0.017 | 0.017 | 0.050 | 0.185 |
| yield | 8 | 0.750 | 0.875 | 0.875 | 0.128 | 0.186 | 0.257 | 0.619 | 0.875 | 0.875 | 0.875 | 0.070 | 0.105 | 0.142 | 0.750 |
