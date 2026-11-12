# Cross-source duplicates (E4 Part 0)

Rows of different sources that report the same contrast (same DOI, practice id and outcome id; `lrr` within 0.01 or both means within 1%). The richer record is kept (more of `var_lrr`, `sd_with`, `sd_without`, `se_with`, `se_without`, `n_with`, `n_without`, `lat`, `lon`, `evidence_text`, `extraction_locator`, `duration_years`, `crop`, `comparator` filled; ties by source order ERA, HAB, CSA, then `row_id`); the other row keeps its provenance and carries `extra.dup_of` and `extra.dup_rule = cross_source`. Readers that skip `dup_of` rows (registry, harness queries, engines) see each contrast once.

- DOIs in more than one source: **40** (CSA+ERA+HAB 3, CSA+ERA 36, ERA+HAB 1); rows under them: 2,268
- flagged rows: **49** in 8 (DOI, practice, outcome) groups; by rule: lrr 49

| kept source > flagged source | rows |
|---|---:|
| ERA>CSA | 44 |
| HAB>CSA | 3 |
| HAB>ERA | 2 |

| flagged source | rows |
|---|---:|
| CSA | 47 |
| ERA | 2 |

## Flagged rows

| row_id | dup_of | rule | richness (flagged / kept) |
|---|---|---|---|
| `CSA:CSA_3:28` | `HAB:HAB_Adimassu_2012_11:1` | lrr | 4 / 12 |
| `CSA:CSA_3:7` | `HAB:HAB_Adimassu_2012_12:1` | lrr | 4 / 12 |
| `CSA:CSA_3:9` | `HAB:HAB_Adimassu_2012_11:1` | lrr | 4 / 12 |
| `CSA:CSA_131:28` | `ERA:ERA_JS0251:5` | lrr | 4 / 7 |
| `CSA:CSA_131:29` | `ERA:ERA_JS0251:27` | lrr | 4 / 7 |
| `CSA:CSA_131:30` | `ERA:ERA_JS0251:23` | lrr | 4 / 7 |
| `CSA:CSA_131:31` | `ERA:ERA_JS0251:23` | lrr | 4 / 7 |
| `CSA:CSA_131:32` | `ERA:ERA_JS0251:19` | lrr | 4 / 7 |
| `CSA:CSA_131:38` | `ERA:ERA_JS0251:5` | lrr | 4 / 7 |
| `CSA:CSA_131:39` | `ERA:ERA_JS0251:35` | lrr | 4 / 7 |
| `CSA:CSA_131:40` | `ERA:ERA_JS0251:8` | lrr | 4 / 7 |
| `CSA:CSA_132:11` | `ERA:ERA_JS0258:5` | lrr | 4 / 8 |
| `CSA:CSA_132:12` | `ERA:ERA_JS0258:5` | lrr | 4 / 8 |
| `CSA:CSA_132:13` | `ERA:ERA_JS0258:1` | lrr | 4 / 8 |
| `CSA:CSA_132:14` | `ERA:ERA_JS0258:5` | lrr | 4 / 8 |
| `CSA:CSA_132:15` | `ERA:ERA_JS0258:5` | lrr | 4 / 8 |
| `CSA:CSA_132:19` | `ERA:ERA_JS0258:1` | lrr | 4 / 8 |
| `CSA:CSA_132:9` | `ERA:ERA_JS0258:1` | lrr | 4 / 8 |
| `CSA:CSA_181:16` | `ERA:ERA_JS0258:5` | lrr | 4 / 8 |
| `CSA:CSA_181:18` | `ERA:ERA_JS0258:1` | lrr | 4 / 8 |
| `CSA:CSA_132:3` | `ERA:ERA_JS0258:11` | lrr | 4 / 8 |
| `CSA:CSA_132:4` | `ERA:ERA_JS0258:9` | lrr | 4 / 8 |
| `CSA:CSA_132:5` | `ERA:ERA_JS0258:8` | lrr | 4 / 8 |
| `CSA:CSA_132:6` | `ERA:ERA_JS0258:11` | lrr | 4 / 8 |
| `CSA:CSA_132:7` | `ERA:ERA_JS0258:7` | lrr | 4 / 8 |
| `CSA:CSA_132:8` | `ERA:ERA_JS0258:10` | lrr | 4 / 8 |
| `CSA:CSA_181:10` | `ERA:ERA_JS0258:9` | lrr | 4 / 8 |
| `CSA:CSA_181:11` | `ERA:ERA_JS0258:8` | lrr | 4 / 8 |
| `CSA:CSA_181:12` | `ERA:ERA_JS0258:11` | lrr | 4 / 8 |
| `CSA:CSA_181:13` | `ERA:ERA_JS0258:7` | lrr | 4 / 8 |
| `CSA:CSA_181:14` | `ERA:ERA_JS0258:10` | lrr | 4 / 8 |
| `CSA:CSA_181:9` | `ERA:ERA_JS0258:11` | lrr | 4 / 8 |
| `ERA:ERA_JS0246:55` | `HAB:HAB_Araya_2010_02:1` | lrr | 8 / 14 |
| `ERA:ERA_JS0246:56` | `HAB:HAB_Araya_2010_04:1` | lrr | 8 / 14 |
| `CSA:CSA_183:10` | `ERA:ERA_DK0125:11` | lrr | 4 / 8 |
| `CSA:CSA_183:11` | `ERA:ERA_DK0125:12` | lrr | 4 / 8 |
| `CSA:CSA_183:12` | `ERA:ERA_DK0125:13` | lrr | 4 / 8 |
| `CSA:CSA_183:13` | `ERA:ERA_DK0125:10` | lrr | 4 / 8 |
| `CSA:CSA_183:7` | `ERA:ERA_DK0125:8` | lrr | 4 / 8 |
| `CSA:CSA_183:8` | `ERA:ERA_DK0125:7` | lrr | 4 / 8 |
| `CSA:CSA_183:9` | `ERA:ERA_DK0125:10` | lrr | 4 / 8 |
| `CSA:CSA_191:12` | `ERA:ERA_NJ0150:1` | lrr | 4 / 8 |
| `CSA:CSA_191:13` | `ERA:ERA_NJ0150:2` | lrr | 4 / 8 |
| `CSA:CSA_191:14` | `ERA:ERA_NJ0150:3` | lrr | 4 / 8 |
| `CSA:CSA_158:57` | `ERA:ERA_NN0232:11` | lrr | 4 / 8 |
| `CSA:CSA_158:58` | `ERA:ERA_NN0232:12` | lrr | 4 / 8 |
| `CSA:CSA_158:64` | `ERA:ERA_NN0232:17` | lrr | 4 / 8 |
| `CSA:CSA_158:65` | `ERA:ERA_NN0232:18` | lrr | 4 / 8 |
| `CSA:CSA_158:71` | `ERA:ERA_NN0232:15` | lrr | 4 / 8 |
