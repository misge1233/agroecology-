# Advisory mode report (P9 modes, U9 evidence fusion)

Generated 2026-11-01 · 35 cells × 38 pins = 1330 advisories · thresholds {'min_studies': 3, 'min_obs': 10, 'min_obs_in_zone': 1} · guidance retrieval off · 111.1 s

**Overall:** model-led 294 · hybrid 846 · knowledge-led 190 · cells by dominant mode: {'hybrid': 21, 'model-led': 9, 'knowledge-led': 5}

**Knowledge candidates:** mean 3.71 per advisory; by source {'documented_practice_record': 254, 'evidence_other_objectives': 4674} · rationale-number guard: 0 failures in 4928 candidates

**Evidence fusion (ordering = conservative):** lead sources of shown practices {'study': 2273, 'model': 691} · disagreements 772 · top-3 studies per practice (mean) 2.51 · best-studied practice in the top 3: 62.7% of 1140 advisories

**Reasons over all advisories (pins carrying each key):** {'thin_evidence': 658, 'other_zones_only': 596, 'strong_evidence': 482, 'in_zone': 544, 'engine_unsupported': 190} · guidance funnel {'graph': 9173, 'guidance.retrieved': 0, 'guidance.kept': 0, 'guidance.with_component': 0, 'records': 1036}

| challenge | objective | pins | model-led | hybrid | knowledge-led | dominant | reasons (pins) | candidates by source |
|---|---|---:|---:|---:|---:|---|---|---|
| Crop production and management | yield | 38 | 11 | 27 | 0 | hybrid | {'thin_evidence': 10, 'other_zones_only': 21, 'strong_evidence': 28, 'in_zone': 17} | {'documented_practice_record': 27} |
| Crop production and management | biomass yield | 38 | 36 | 2 | 0 | model-led | {'strong_evidence': 38, 'in_zone': 36, 'other_zones_only': 2} | {'evidence_other_objectives': 9, 'documented_practice_record': 1} |
| Crop production and management | income | 38 | 5 | 33 | 0 | hybrid | {'thin_evidence': 29, 'in_zone': 13, 'other_zones_only': 25, 'strong_evidence': 9} | {'evidence_other_objectives': 165} |
| Crop production and management | water use efficiency | 38 | 0 | 38 | 0 | hybrid | {'thin_evidence': 38, 'other_zones_only': 24, 'in_zone': 14} | {'evidence_other_objectives': 190} |
| Crop production and management | SOM content | 38 | 0 | 38 | 0 | hybrid | {'thin_evidence': 38, 'other_zones_only': 25, 'in_zone': 13} | {'evidence_other_objectives': 190} |
| Crop production and management | soil loss | 38 | 24 | 14 | 0 | model-led | {'strong_evidence': 38, 'other_zones_only': 14, 'in_zone': 24} | {'evidence_other_objectives': 70} |
| Crop production and management | runoff | 38 | 30 | 8 | 0 | model-led | {'strong_evidence': 38, 'in_zone': 30, 'other_zones_only': 8} | {'evidence_other_objectives': 40} |
| Livestock production and management | yield | 38 | 0 | 0 | 38 | knowledge-led | {'engine_unsupported': 38} | {'evidence_other_objectives': 190} |
| Livestock production and management | biomass yield | 38 | 0 | 38 | 0 | hybrid | {'thin_evidence': 38, 'other_zones_only': 18, 'in_zone': 20} | {'evidence_other_objectives': 152, 'documented_practice_record': 38} |
| Livestock production and management | income | 38 | 0 | 38 | 0 | hybrid | {'thin_evidence': 38, 'other_zones_only': 18, 'in_zone': 20} | {'evidence_other_objectives': 114, 'documented_practice_record': 38} |
| Livestock production and management | water use efficiency | 38 | 0 | 0 | 38 | knowledge-led | {'engine_unsupported': 38} | {'evidence_other_objectives': 190} |
| Livestock production and management | SOM content | 38 | 0 | 0 | 38 | knowledge-led | {'engine_unsupported': 38} | {'evidence_other_objectives': 190} |
| Livestock production and management | soil loss | 38 | 0 | 38 | 0 | hybrid | {'thin_evidence': 38, 'other_zones_only': 26, 'in_zone': 12} | {'evidence_other_objectives': 152, 'documented_practice_record': 38} |
| Livestock production and management | runoff | 38 | 0 | 38 | 0 | hybrid | {'thin_evidence': 38, 'other_zones_only': 15, 'in_zone': 23} | {'evidence_other_objectives': 152, 'documented_practice_record': 38} |
| Integrated soil fertility management | yield | 38 | 3 | 35 | 0 | hybrid | {'thin_evidence': 17, 'other_zones_only': 30, 'strong_evidence': 21, 'in_zone': 8} | {'evidence_other_objectives': 69, 'documented_practice_record': 35} |
| Integrated soil fertility management | biomass yield | 38 | 1 | 37 | 0 | hybrid | {'thin_evidence': 25, 'other_zones_only': 34, 'strong_evidence': 13, 'in_zone': 4} | {'evidence_other_objectives': 185} |
| Integrated soil fertility management | income | 38 | 5 | 33 | 0 | hybrid | {'strong_evidence': 8, 'in_zone': 13, 'thin_evidence': 30, 'other_zones_only': 25} | {'evidence_other_objectives': 165} |
| Integrated soil fertility management | water use efficiency | 38 | 0 | 38 | 0 | hybrid | {'thin_evidence': 38, 'other_zones_only': 27, 'in_zone': 11} | {'evidence_other_objectives': 190} |
| Integrated soil fertility management | SOM content | 38 | 9 | 29 | 0 | hybrid | {'thin_evidence': 25, 'in_zone': 17, 'other_zones_only': 21, 'strong_evidence': 13} | {'evidence_other_objectives': 145} |
| Integrated soil fertility management | soil loss | 38 | 0 | 38 | 0 | hybrid | {'thin_evidence': 38, 'other_zones_only': 24, 'in_zone': 14} | {'evidence_other_objectives': 190} |
| Integrated soil fertility management | runoff | 38 | 0 | 38 | 0 | hybrid | {'thin_evidence': 38, 'other_zones_only': 24, 'in_zone': 14} | {'evidence_other_objectives': 190} |
| Erosion control and water management | yield | 38 | 9 | 29 | 0 | hybrid | {'strong_evidence': 20, 'other_zones_only': 28, 'thin_evidence': 18, 'in_zone': 10} | {'evidence_other_objectives': 81, 'documented_practice_record': 29} |
| Erosion control and water management | biomass yield | 38 | 12 | 26 | 0 | hybrid | {'thin_evidence': 14, 'other_zones_only': 20, 'in_zone': 18, 'strong_evidence': 24} | {'evidence_other_objectives': 130} |
| Erosion control and water management | income | 38 | 0 | 0 | 38 | knowledge-led | {'engine_unsupported': 38} | {'evidence_other_objectives': 190} |
| Erosion control and water management | water use efficiency | 38 | 34 | 4 | 0 | model-led | {'strong_evidence': 38, 'in_zone': 34, 'other_zones_only': 4} | {'evidence_other_objectives': 20} |
| Erosion control and water management | SOM content | 38 | 22 | 16 | 0 | model-led | {'strong_evidence': 38, 'in_zone': 22, 'other_zones_only': 16} | {'evidence_other_objectives': 80} |
| Erosion control and water management | soil loss | 38 | 22 | 16 | 0 | model-led | {'strong_evidence': 27, 'in_zone': 32, 'thin_evidence': 11, 'other_zones_only': 6} | {'evidence_other_objectives': 80} |
| Erosion control and water management | runoff | 38 | 24 | 14 | 0 | model-led | {'thin_evidence': 11, 'in_zone': 30, 'strong_evidence': 27, 'other_zones_only': 8} | {'evidence_other_objectives': 70} |
| Agro-forestry and forest management | yield | 38 | 0 | 38 | 0 | hybrid | {'strong_evidence': 26, 'other_zones_only': 37, 'thin_evidence': 12, 'in_zone': 1} | {'evidence_other_objectives': 180, 'documented_practice_record': 10} |
| Agro-forestry and forest management | biomass yield | 38 | 0 | 38 | 0 | hybrid | {'thin_evidence': 38, 'in_zone': 19, 'other_zones_only': 19} | {'evidence_other_objectives': 190} |
| Agro-forestry and forest management | income | 38 | 0 | 0 | 38 | knowledge-led | {'engine_unsupported': 38} | {'evidence_other_objectives': 190} |
| Agro-forestry and forest management | water use efficiency | 38 | 0 | 38 | 0 | hybrid | {'thin_evidence': 38, 'other_zones_only': 29, 'in_zone': 9} | {'evidence_other_objectives': 190} |
| Agro-forestry and forest management | SOM content | 38 | 0 | 38 | 0 | hybrid | {'thin_evidence': 38, 'in_zone': 19, 'other_zones_only': 19} | {'evidence_other_objectives': 190} |
| Agro-forestry and forest management | soil loss | 38 | 22 | 16 | 0 | model-led | {'strong_evidence': 38, 'other_zones_only': 16, 'in_zone': 22} | {'evidence_other_objectives': 80} |
| Agro-forestry and forest management | runoff | 38 | 25 | 13 | 0 | model-led | {'strong_evidence': 38, 'other_zones_only': 13, 'in_zone': 25} | {'evidence_other_objectives': 65} |
