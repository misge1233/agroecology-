# data/taxonomy: practice, outcome and challenge taxonomies

Controlled vocabularies that every evidence row is mapped onto (brief E1 Part C; roadmap 5.3).
Built the way `pipelines/dataset/build_practice_family.py` was built: **rules propose, a human
ticks, ids freeze**. All files are CSV, UTF-8, LF, with a header row. Ids are upper snake case and
**permanent: never reused, never renamed**. A retired id stays in its file with a note.

## Files

| File | Columns | What it is |
|---|---|---|
| `practices.csv` | `practice_id, name_en, practice_family, components, era_codes, catalogue_ids, wocat_group, wocat_measure, status, notes` | canonical practices. `practice_family` is one of the 5 frozen families; `components` (`;`) come from `rag/graph/practice_components.py`; `era_codes` are ERA `T1..T14` codes seen with the label; `wocat_*` are the *proposed* WOCAT groups and measures of `docs/decisions/wocat_crosswalk_proposal.csv` |
| `practice_aliases.csv` | `alias, source, practice_id, method, confidence, accepted, reviewer, date` | raw label in a source (`CSA, ERA, HAB, CAT, WOCAT`) -> canonical practice |
| `outcomes.csv` | `outcome_id, name_en, direction, unit_class, objective_group, legacy_indicator, status, notes` | canonical outcomes; `direction` +1 higher is better, -1 lower is better; `legacy_indicator` is one of the 7 frozen indicator strings or empty |
| `outcome_aliases.csv` | as `practice_aliases.csv` with `outcome_id` | raw outcome label -> canonical outcome |
| `challenges.csv` | `challenge_id, name_en, description_en, objective_groups, practice_families, catalogue_problem_terms, outcome_ids, status` | problem-based challenges. `outcome_ids` (added to the brief's columns) names the objectives precisely within the objective groups; `catalogue_problem_terms` are the normalised "key problems" phrases of the catalogue, so the catalogue -> challenge link is data |
| `catalogue_entries.json`, `.csv` | see `pipelines/evidence/parse_catalogue.py` | the 30 parsed catalogue entries (partner document text; see the note at the end) |
| `crop_harmonisation.csv` | `source, crop_raw, crop, crop_group, n_rows, method` | the crop spelling and group rule of the frozen dataset, recovered as data (`pipelines/evidence/crop_lookup.py`) |
| `review/HAB_practices_review.csv`, `review/HAB_outcomes_review.csv` | `raw_label, n_rows, candidate_1..3, score_1..3, llm_suggestion, accepted, <id>, reviewer, date` | labels no rule could map, with their row count and the top-3 candidates by rapidfuzz token-set ratio |
| `review/practice_merges.csv` | `practice_id_a, practice_id_b, relation, reason, accepted, reviewer, date` | proposed merges (`same_practice`) and parent links (`narrower_than`); **never applied in E1** |
| `review/llm_cache.jsonl` | | cache of the optional `--llm` proposals (git-ignored) |

Vocabularies: `status` in `seed | reviewed | frozen | excluded | context_dependent | merged` (the last three since E2); `unit_class` in
`yield | mass | fraction | concentration | money | count | rate | index | other`;
`objective_group` in `productivity | soil_health | water | economics | resilience_biodiversity | livestock | climate | other` (`climate` since E2, schema v1.1);
alias `method` in `exact | normalised | component | component_primary | era_code | catalogue | keyword | domain | seed_new | llm | manual`.

## Review protocol

1. **Rules propose.** `python pipelines/taxonomy/propose_mappings.py` (also run by
   `build_evidence_store.py`) writes rule mappings into the alias files with `accepted` empty, and
   unmatched labels into the review sheets. Optional `--llm` fills `llm_suggestion` only (one
   constrained call per label: a candidate id or `NEW`; cached).
2. **A human ticks.** In an alias file: set `accepted` to `yes` or `no` and write your name in
   `reviewer` (a rejected alias is no longer used by the store). In a review sheet: set `accepted =
   yes`, fill `practice_id`/`outcome_id` with an existing id, `reviewer` and `date`, then run
   `python pipelines/taxonomy/propose_mappings.py --apply-review`. In `outcomes.csv`: check
   `direction`, then set `status = reviewed`. In `practice_merges.csv`: tick or reject; merges are
   applied in a later phase, never silently.
   **E2 appliers.** `--apply-outcome-review [SHEET]` applies the rows of
   `review/outcomes_direction_review.csv` that the owner marked `accepted = yes`: `accept`/`flip`
   (direction, group, `status = reviewed`), `exclude` (`status = excluded`, no direction),
   `context_dependent` (no direction, note kept), `merge_into` (aliases moved, `status = merged`).
   `--apply-review` also accepts `NEW:<ID>` in a Habtamu sheet (a new canonical practice or outcome
   from the label) and applies accepted rows of `practice_merges.csv` (`same_practice`: aliases
   moved, merged id `status = merged`; `narrower_than`: parent recorded in `notes`). `--llm` fills
   `llm_suggestion` only (model `gpt-4o-mini`, top-10 candidates with their components, cached).
   `review/suitability_review.csv` (E2, rules only) proposes slope, rainfall, land-use, belt, soil
   depth and stoniness statements per practice with document, page and quote; nothing is applied
   before E5.
3. **Ids freeze.** A row with `status = reviewed`/`frozen`, or an alias with `accepted` set or a
   reviewer, is never overwritten by a re-run of the rules (tested in
   `pipelines/taxonomy/test_propose_mappings.py`).

**Direction rule (brief C2).** Only reviewed or frozen outcomes give rows a `direction`; every
other row has `direction = null`, `direction_reviewed = false` and is excluded from ranking and
from the registry counts. Today only the 7 legacy indicators are `frozen` (direction from
`recommend.DIRECTION`); all other directions are proposals waiting for review.

## Seeding rules (what the rules did)

- **Practices.** (1) the 100 frozen `CSA_practices` labels, family from
  `build_practice_family.classify` (asserted equal to the frozen `practice_family`), components from
  the component layer; `Deficit Irrigation` (ERA) and `Deficit irrigation` (CSA) differ only by case,
  so they are `DEFICIT_IRRIGATION_ERA` and `DEFICIT_IRRIGATION_CSA` with a `same_practice` merge
  proposal; (2) ERA `PrName` and CSA categories outside the frozen set: normalised match, else a new
  practice; (3) catalogue names: normalised match, else a new practice with components by keyword
  and a `narrower_than` proposal towards the frozen category with the same component set;
  (4) Habtamu labels: normalised match, exact component set, else the first-mentioned component's
  practice (`component_primary`, confidence 0.6); labels that negate or name a comparator
  ("without compost", "conventional") are never rule-mapped.
- **Outcomes.** The 7 legacy indicators; the 59 ERA outcome names (`Outcode`, attributes proposed
  per name in `pipelines/taxonomy/rules.py`); the keyword-rule targets; CSA indicator labels by
  rules, else a new seed; Habtamu `Outcome_name` by normalised match, ordered keyword rules
  (specific before general: weed biomass before biomass, nutrient runoff before runoff), and a
  biodiversity-domain fallback; the rest to review.

## Note on partner material

`catalogue_entries.*` hold text extracted from the partner catalogue (descriptions, limitations,
photo captions). The brief places them here, in git; if the catalogue must not be redistributed
before publication, add them to `.gitignore` (the owner decides).
