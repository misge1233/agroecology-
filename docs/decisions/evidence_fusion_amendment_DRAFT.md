# DRAFT amendment to `docs/decisions/evidence_fusion.md` (E7, 12 Nov 2026), NOT APPLIED

**Status: draft for the owner's approval.** Drafted by the implementation agent as E7 Part C
requires; `docs/decisions/evidence_fusion.md` and CLAUDE.md are unchanged until the owner
approves this text. The decision it serves is E7 branch 2 (`m3_gate`), available only behind
`ADVISOR_ENGINE=m3`; the default engine is unchanged.

## Proposed paragraph (to be added to the fusion doctrine, after the rule on numbers)

> **Order may be informed by general agronomic knowledge.** Where the field evidence behind a
> request is thin (fewer than five distinct studies per candidate practice, the threshold chosen
> in the evaluation of 12 Nov 2026), the order in which practices are shown may come from a
> language model's general agronomic knowledge, asked with the farm context, the objective, the
> crop and the practice names only. The language model never supplies a number, an interval or
> a citation: every number, interval and citation shown still comes from the evidence (the
> evidence model's estimate with its calibrated 80 % interval, study-level effects, cited
> passages) exactly as this doctrine already requires, and the lead-source labels are those of
> the evidence. The evaluation found that this ordering reflects knowledge that is the same for
> every place (it does not change with the farm context), so it is presented as general
> guidance, never as location-specific advice; where the evidence is dense, the evidence model
> orders the practices. The Methodology page states this in plain words.

## What changes if approved

- CLAUDE.md doctrine 1 gains one sentence pointing to this paragraph.
- The Methodology page (E8) explains the ordering rule and its limits.
- Nothing changes in how numbers, intervals or citations are produced or guarded.
