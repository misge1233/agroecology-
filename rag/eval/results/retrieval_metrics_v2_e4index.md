# Retrieval evaluation — hybrid RagRetriever vs silver era_code labels

Success@k (≥1 relevant study in the top k — the primary metric) precedes Recall@k (corpus-coverage diagnostic). Strict labels: family + indicator + practice. `(fam)` columns: family + indicator only.

| group | n | success@4 | success@8 | success@16 | recall@4 | recall@8 | recall@16 | mrr | success@4 (fam) | success@8 (fam) | success@16 (fam) | recall@4 (fam) | recall@8 (fam) | recall@16 (fam) | mrr (fam) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **overall** | 45 | 0.400 | 0.511 | 0.556 | 0.128 | 0.227 | 0.279 | 0.338 | 0.533 | 0.600 | 0.644 | 0.093 | 0.147 | 0.192 | 0.418 |

## Per practice family
| group | n | success@4 | success@8 | success@16 | recall@4 | recall@8 | recall@16 | mrr | success@4 (fam) | success@8 (fam) | success@16 (fam) | recall@4 (fam) | recall@8 (fam) | recall@16 (fam) | mrr (fam) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Agro-forestry and forest management | 5 | 0.200 | 0.200 | 0.200 | 0.050 | 0.050 | 0.050 | 0.050 | 0.200 | 0.200 | 0.200 | 0.018 | 0.036 | 0.036 | 0.050 |
| Crop production and management | 14 | 0.286 | 0.500 | 0.571 | 0.059 | 0.168 | 0.250 | 0.264 | 0.357 | 0.500 | 0.571 | 0.029 | 0.117 | 0.165 | 0.321 |
| Erosion control and water management | 13 | 0.538 | 0.692 | 0.769 | 0.235 | 0.444 | 0.521 | 0.481 | 0.846 | 0.923 | 1.000 | 0.182 | 0.256 | 0.340 | 0.658 |
| Integrated soil fertility management | 10 | 0.600 | 0.600 | 0.600 | 0.164 | 0.182 | 0.203 | 0.500 | 0.700 | 0.700 | 0.700 | 0.133 | 0.148 | 0.171 | 0.550 |
| Livestock production and management | 3 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |

## Per indicator
| group | n | success@4 | success@8 | success@16 | recall@4 | recall@8 | recall@16 | mrr | success@4 (fam) | success@8 (fam) | success@16 (fam) | recall@4 (fam) | recall@8 (fam) | recall@16 (fam) | mrr (fam) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| SOM content | 8 | 0.250 | 0.375 | 0.500 | 0.125 | 0.250 | 0.375 | 0.163 | 0.250 | 0.375 | 0.625 | 0.125 | 0.150 | 0.237 | 0.175 |
| biomass yield | 9 | 0.444 | 0.444 | 0.444 | 0.149 | 0.194 | 0.217 | 0.389 | 0.667 | 0.667 | 0.667 | 0.051 | 0.081 | 0.129 | 0.556 |
| income | 6 | 0.500 | 0.500 | 0.500 | 0.306 | 0.306 | 0.306 | 0.375 | 0.500 | 0.500 | 0.500 | 0.221 | 0.221 | 0.221 | 0.375 |
| runoff | 4 | 0.000 | 0.750 | 1.000 | 0.000 | 0.500 | 0.600 | 0.175 | 0.500 | 1.000 | 1.000 | 0.083 | 0.375 | 0.458 | 0.267 |
| soil loss | 4 | 0.500 | 0.500 | 0.500 | 0.062 | 0.219 | 0.281 | 0.375 | 0.500 | 0.500 | 0.500 | 0.111 | 0.250 | 0.306 | 0.500 |
| water use efficiency | 6 | 0.167 | 0.167 | 0.167 | 0.033 | 0.033 | 0.033 | 0.167 | 0.333 | 0.333 | 0.333 | 0.033 | 0.033 | 0.033 | 0.222 |
| yield | 8 | 0.750 | 0.875 | 0.875 | 0.141 | 0.193 | 0.255 | 0.619 | 0.875 | 0.875 | 0.875 | 0.053 | 0.085 | 0.122 | 0.719 |
