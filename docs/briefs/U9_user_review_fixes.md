# U9 — Evidence fusion and user-review fixes (1 Nov 2026)

**Binding:**

- `docs/decisions/evidence_fusion.md` (owner decision, 1 Nov);
- CLAUDE.md §1–2 (amended 1 Nov);
- this brief.

**Source of findings:** the Cowork browser review of `localhost:3000`.

- Chrome at 1280×575, plus 390 px.
- Languages en/om/am; light and dark themes.
- Flow: Debre Birhan → Erosion & water → Reduce soil loss → Any crop (hybrid), Top 1 and Top 5; Evidence, Why this? and How to implement; Chat; About.

**Ground rules:**

- Production grade: typed, tested, logged, i18n in en/am/om.
- No data-contract changes.
- API changes are additive.
- Every fix gets a test.
- Report as a U9 block in `progress.md`, with before/after screenshots (1440 and 390 px, light and dark, en/am/om).
- The owner commits.

**Do not regress (verified working):**

- geocode search, pin and belt resolution;
- context card;
- mode badge and reason box;
- Top-N selector;
- Copy link;
- deferred map on mobile;
- dark mode;
- mobile home and advisor layouts;
- i18n key parity (am 413/413, om 413/413);
- no console errors on the English pages.

---

## Part A — Evidence fusion (backend first)

**A1. Evidence bundle per practice.**

- Model estimate with confidence, `n_studies`, `n_obs` and in-zone counts.
- Study evidence from graph `REPORTS_EFFECT` for the requested indicator: per study `{ref, title, year, belt/zone, n_obs, effect = exp(mean_log_rr) − 1, share_positive}`, sorted with in-zone studies first.
- Passages.

Retire the "never read `mean_log_rr`" rule in `explain_service.py`; study evidence is now a source.

**A2. Lead source per practice** (decision §3): `model | study | documented`, plus `disagreement`. This lives in `advisory_service` and uses settings published in `/metadata`. Keep the P9 `mode` field and add `lead_source` per practice.

**A3. Ordering** (decision §4): conservative bound behind `ADVISORY_ORDERING=conservative|model`. Evaluate both: P7 ranking metrics where feasible, plus `rag/eval/mode_report.py` before and after. Report the numbers.

**A4. Numeric guard v2** (decision §5).

- Bind each passage number to its citation sentence-by-sentence. Today any number in any retrieved chunk is allowed anywhere.
- Provenance objects `{value, unit, source, ref}` on every number in the API.
- One rounding/formatting function shared by backend and frontend.

**A5. Two registers.**

- `summary`: plain language, no markers; its numbers come only from the headline values and are still guarded.
- `evidence`: labelled ("Model estimate for your area", "Reported in study [n]") and cited.
- Chat uses `summary` by default and switches to `evidence` on intents like why / how do you know / evidence / source / which study, in en/am/om.
- Update the explain and chat prompts in all three languages.

**A6. Chat request understanding (M10).** Test question: "I grow teff near Bahir Dar and my soil is acidic. What can I do to improve yield?" The current answer recommends "drought-tolerant crops… ~100%" and garbles a practice name.

- Parse soil constraints (acidic / low pH, waterlogging, salinity) into the request, as indicator/family or as documented candidates (pH control / liming, ISFM).
- When the user names a crop, flag practices that replace it.
- Use exact display names.
- Add a caution for effects ≥ +80%.
- Add the question to the chat eval set.

## Part B — Must-fix UI defects

**B1 (M1). Chrome auto-translate crashes the app.** On `/am` it raised React `NotFoundError: removeChild` in `SelectItemText` and showed the error screen. Fix in `src/app/[locale]/layout.tsx`: add `translate="no"` on `<html>` and `<meta name="google" content="notranslate">`. Add an E2E test on all locales.

**B2 (M2). The header is transparent.** `bg-surface/90` compiles to nothing because the tokens are `var(--x)` hex. Convert all colour tokens to channel format (`rgb(var(--x) / <alpha-value>)`) in light and dark, and audit every `token/alpha` use (e.g. `border-primary/25`). E2E: header background alpha ≥ 0.85 over the hero, the CTA band and on mobile.

**B3 (M3). The Evidence panel shows raw Markdown** (`###`, `**`). Render with `assistant-markdown.tsx` (no raw HTML), in print too.

**B4 (M4). Citation integrity.**

- One page/answer-level citation registry keyed by document id, shared by cards, Evidence, Documented practices and print. Today `[G1]` means two different documents on one page.
- No study marker on user-context sentences (today "annual average of 1024 mm [1]").
- Normalise `[1a]`/`[2b]` to the visible numbering.

**B5 (M5). Ranked and documented lists overlap.** Exclude every ranked practice from the documented list. Today, with Top 5, "Biological SWC practices" appears as ranked #3 (−71%) and as documented #4 "evidence for other objectives, no effect numbers". Fix the "other objectives" computation. Test: documented ∩ ranked = ∅.

## Part C — Sources and content quality

**C1 (M7). "How to implement" shows raw chunks** (a bibliography line "B. Van Wesemael… 19. La", a watershed description).

- Filter reference-list, front-matter and boilerplate chunks.
- Set a relevance floor.
- Drop off-region or non-English documents unless highly relevant (a Spanish Andean infiltration-trench document was cited for Ethiopia).
- Show synthesised, numbered steps with `[Gn]`, and put the raw text behind "Show source text".

**C2 (M8). Guidance titles are PDF first-line text** ("Farming System 2 (2024) 100110Contents lists…", "ADDIS ABABA UNIVERSITY COLLEGE OF…").

- Backfill `title`, `year` and `handle` from CGSpace/GARDIAN metadata as a metadata update. No re-embedding; copy, never destructive in place.
- Link the handle page, not `/bitstreams/.../retrieve`.

**C3 (M9). "Dataset study #CSA_18" has no reference.** Map CSA study ids to their bibliographic entries (Adimassu et al. compilation source list). If that is impossible, show the compilation citation plus the study number.

**C4 (S13). Source relevance.** Sort sources by relevance to the requested objective; Mulch currently lists ginger bacterial wilt and termite damage first. Show 6, then "and N more".

## Part D — Should-fix UI/UX (clean, attractive, standard)

- **D1. Result card.** A plain-language headline in words, plus one source chip (*Field-trial model* / *Field study · similar area* / *Guidance*).
  - "Why this?" shows the labelled model and study values and a disagreement note.
  - Replace the single-bar chart (axis −82%…−78%, not anchored at 0) with a 0-anchored dot + interval, or hide it for a single item.
- **D2. Defaults and speed.**
  - Default to Top 3 (now Top 1).
  - Skeletons instead of bare spinners: results take ≈10 s and Evidence ≈30 s.
  - Stream or prefetch the explanation for the top card.
  - Cache `/explain` per (pin, family, indicator, practice, locale).
- **D3. Copy (ICU plurals, all languages).**
  - "1 studies" → "1 study".
  - "The best-evidenced practice" → "The top-ranked practice".
  - "clearly labelled and, never" → "clearly labelled, and never".
  - Fix in `messages/*.json` and `backend/app/i18n/*`.
- **D4. Zone names.** "Wet Dega" vs "Wet-highland" vs "Dry Weyna Dega": show the mapping and translate the zone names.
- **D5. One confidence vocabulary across Advisor and Chat.** Today chat says "Medium" where the Advisor says "Thin evidence".
- **D6. Print/PDF** fetches evidence for the shown practices before printing. Today it says "Evidence details were not loaded before printing…".
- **D7. Map.**
  - Leaflet controls overlap the sticky header: use `isolation:isolate`.
  - The initial view is on the Red Sea: `fitBounds(Ethiopia)` after `invalidateSize`.
  - Choose a production tile provider.
- **D8. Steps.** Scroll to and focus the step heading on step change; "four steps" vs a 5-step stepper.
- **D9. Chat.**
  - Double scrollbar.
  - At 390 px the composer placeholder wraps and shows spinner arrows.
  - The examples are hidden behind the composer at short heights.
  - The author line is duplicated ("You, 01:13 PM" / "You · 01:13 PM").
- **D10. Labels.**
  - Show the place name with coordinates ("Debre Birhan (9.68, 39.53)").
  - Add units (SOC "28.3" has none).
  - Use display names, not internal labels ("Physical SWC Measures", "SOM content", lowercase "soil loss").
  - "Sources: 17 · Passages: 1" → "17 field studies · 1 guidance document".
- **D11. Localisation leaks (om).**
  - The English headline is duplicated in print.
  - The "Effects are model estimates…" footnote is untranslated.
  - Dates are not localised.
  - English practice names sit inside Oromo templates.
  - Re-check Amharic visually after B1.
- **D12.** "NO ILLUSTRATION YET" on Biological SWC practices: map it to an existing image.
- **D13. Visual quality bar.**
  - One type scale and spacing rhythm; clear card hierarchy.
  - No raw ids or jargon.
  - AA contrast.
  - No layout shift on load.
  - Lighthouse ≥ 90 for accessibility and best practices.

## Part E — Copy and docs (en/am/om)

Reframe everything from "the model owns every number" to **evidence fusion**:

- **Home:** the card "The model owns every number" → "Every number has a source": recommendations combine field-trial models, published studies, guidance and a knowledge graph; each number comes from one of them, never from the AI writer, and the source is one click away. Update the architecture section the same way.
- **Advisor subtitle:** "Every number shown comes from the field-trial model" → "Every number comes from field trials or published studies, with its source one click away".
- **About:**
  - add "How the advisor decides" (model-led / study-led / documented, plus disagreement);
  - update confidence and sources;
  - add data licences and attribution, a voice privacy note, version, and how to cite;
  - remove "bluffing" and the doubled "Thin evidence: Thin evidence".
- **Footer:** replace "Version not available" with the build version.
- **Docs:**
  - `README.md`;
  - `docs/decisions/rag_design.md`;
  - `research_project_plan.md`;
  - `paper/manuscript/manuscript_skeleton.md` (framing and title per decision §9);
  - docstrings citing the old doctrine (`explain_service.py`, `evidence_service.py`, `recommender_service.py`, `rag/graph/schema.py`).

## Part F — Hero image: deferred

Owner decision, 1 Nov: keep the current hero image. Do not change the image, its file or its layout in U9. It will be replaced later if a better image is found.

## Acceptance

All existing tests green, plus new tests for:

- the lead-source rules and disagreement (A2);
- the ordering switch (A3);
- guard v2 sentence binding and provenance objects (A4);
- register switching in chat in en/am/om (A5);
- the acidic-soil eval (A6);
- `translate="no"` (B1);
- header alpha (B2);
- no `###`/`**` text in Evidence (B3);
- unique citation keys and no study marker on context sentences (B4);
- documented ∩ ranked = ∅ (B5);
- the reference-chunk filter (C1);
- titles and handles present (C2);
- ICU plurals (D3).

Also: Playwright and axe pass on all locales, and the mode report and ordering evaluation are included in the U9 report.
