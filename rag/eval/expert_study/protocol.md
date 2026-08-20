# Blinded expert study — model-only vs model+RAG advisories

Phase P3 protocol (see `docs/decisions/rag_design.md` §Evaluation plan).

## Question

Does grounding the advisory text in retrieved ERA literature (RAG) improve
its quality in the eyes of domain experts, compared with the deterministic
model-only text, holding the underlying recommendation constant?

## Design

- **Within-subject A/B**, condition blinded, order randomized.
  - **Condition A — model-only:** the deterministic template built from the
    engine output alone (practice + effect estimate; no citations, no LLM).
  - **Condition B — model+RAG:** the grounded explanation produced by the
    live `/explain` path (LLM over retrieved ERA passages, numeric
    guardrail, citations).
- **Scenarios:** ~30, sampled from `rag/eval/queries.jsonl` stratified over
  the 5 practice families × 7 indicators and AEZ belts (the same sample the
  faithfulness audit ran on — `results/explanations.jsonl` is the source of
  both texts, so every rated advisory is a real system output).
- **Raters:** 3–5 experts in Ethiopian agronomy / climate-smart agriculture.
  Each expert rates BOTH conditions of every scenario (paired design).
- **Blinding:** conditions are shown as anonymous advisories with opaque
  item codes; A/B position within each scenario is randomized per expert;
  the mapping lives only in `answer_key.csv`, which is NOT sent to experts.

## Materials

`make_packets.py` produces one CSV packet per expert
(`packets/expert_<i>.csv`). Each row = one advisory to rate:

| column | content |
|---|---|
| `item_code` | opaque id (e.g. `E1-S007-X`) — no condition information |
| `scenario_context` | location (AEZ belt, rainfall, slope), crop, challenge (practice family), objective (indicator), and the model's ranked practices with effect estimates — identical for both conditions of a scenario |
| `advisory_text` | the text to rate (condition hidden) |
| `agronomic_soundness_1to5` … `clarity_1to5` | blank — expert fills in |
| `comments` | blank — optional free text |

## Rating instructions (include when sending packets)

For each advisory, rate 1–5 (1 = very poor, 3 = acceptable, 5 = excellent):

1. **Agronomic soundness** — is the advice technically correct for this
   context (AEZ, rainfall, slope, crop)?
2. **Usefulness** — would this help an extension worker act?
3. **Trustworthiness** — would you rely on it; does it justify its claims?
4. **Clarity** — is it plain, well-organized, appropriately concise?

Rate each advisory on its own merits; scenarios repeat with two advisory
variants — this is intentional, do not try to make the two consistent.
Work in row order (it is already randomized). Do not discuss items with
other raters until all packets are returned.

## Analysis plan

- Per dimension: paired comparison A vs B per scenario per rater —
  Wilcoxon signed-rank on scenario-level means (report effect size and
  median Δ); descriptive means ± SD per condition.
- Inter-rater agreement: Krippendorff's α (ordinal) per dimension.
- Secondary: Δ by practice family / indicator / AEZ belt (descriptive only,
  n is small).
- Unblinding happens only after all ratings are collected, by joining
  `answer_key.csv` on `item_code`.

## Integrity notes

- The scenario context (including effect numbers) is identical across
  conditions — experts judge the advisory TEXT, not the recommendation.
- `answer_key.csv` must never be included in a packet email.
- If an expert recognizes a study from a citation in condition B, that is
  part of the treatment, not a blinding failure (citations ARE the
  intervention); the condition label itself stays hidden.
