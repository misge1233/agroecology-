# Phase R1 — Rename the product to AgroEcoAdvisor (brief)

Written by the Senior AI Engineer, 31 Oct 2026. Read `CLAUDE.md` first, then
this brief. When done, append the phase report to `progress.md` per
CLAUDE.md (begin it with the decision record below, copied verbatim) and stop.

## Decision record (owner + supervisor + reviewer, 31 Oct 2026)
- **Display name:** `AgroEcoAdvisor` (one word, this exact casing).
- **Tagline:** `AI-Powered Agroecology+ Solutions` (the supervisor's programme
  name). Header, page titles, print sheet, About and README use both.
- **Why:** the work now extends beyond Ethiopia ("-ET" no longer fits) and
  belongs to the AI-Powered Agroecology+ Solutions programme. A light web check
  (31 Oct) found no product named AgroEcoAdvisor; an unrelated "AgroAdvisor"
  product exists elsewhere, another reason to move away from the old name.
- **Previous names:** AgroGuide (prototype) → AgroAdvisor-ET (18 Aug – 31 Oct
  2026) → AgroEcoAdvisor.
- **Slug** (where a lowercase identifier is needed): `agroecoadvisor`.
- **Languages:** the brand stays in Latin script in all three languages
  (`AgroEcoAdvisor`); the tagline is translated in `am` and `om` (machine
  draft, status `machine-draft` in `docs/i18n/TRANSLATION_STATUS.md`; keep
  "AI" and "Agroecology+" recognisable).

## Scope — what changes
Replace the brand tokens `AgroAdvisor-ET` and `AgroAdvisor` (as a product
name) by `AgroEcoAdvisor`, and `agroadvisor-et` / `agroadvisor` slugs by
`agroecoadvisor`, in exactly these kinds of places (inventory measured on
31 Oct; re-grep before editing):
1. **UI:** `app/frontend/messages/{en,am,om}.json` (app name, tagline, every
   string mentioning the product), `src/app/[locale]/layout.tsx` metadata
   (title template `%s · AgroEcoAdvisor`, default title `AgroEcoAdvisor —
   AI-Powered Agroecology+ Solutions`, description, Open Graph), header
   wordmark + tagline line, footer (`© 2026 AgroEcoAdvisor · Alliance of
   Bioversity International and CIAT`), About page, print sheet header,
   `globals.css` comments, `lib/types.ts`/test comments, `i18n-audit.test.ts`
   allow-list, `package.json` `name` (`agroecoadvisor-frontend`; regenerate the
   lockfile with `npm install --package-lock-only`, no dependency changes).
2. **Backend:** LLM persona and prompt texts in `advisor_agent.py`,
   `app/services/chat_service.py`, `app/services/explain_service.py`,
   `groq_agent.py` (compat shim); `app/config.py` `app_name` (FastAPI title);
   `app/routers/models.py`; i18n catalogs `app/i18n/{en,am,om}.py`;
   `recommend.py` docstring only. HTTP User-Agent strings:
   `rag/ingest/fetch_papers.py` → `AgroEcoAdvisor corpus builder (research
   use; mailto:{email})`, `app/services/geocode.py` → `agroecoadvisor/1.0`.
3. **Docs:** `README.md`, `app/backend/README.md`, `app/frontend/README.md`,
   `docs/design/design_system.md`, `rag/graph/README.md`, docstrings in
   `rag/graph/{__init__,schema,build_graph}.py`, the title string in
   `model/evaluate.py` (then regenerate `docs/reports/model_evaluation_report.md`
   FROM THE EXISTING `model/artifacts/model_eval.json` with
   `ev.format_report(payload)` — no re-evaluation; the diff must be the title
   line only), `CLAUDE.md` (title line and doctrine 4's branding sentence:
   "User-facing branding is **AgroEcoAdvisor — AI-Powered Agroecology+
   Solutions**"), `research_project_plan.md` and
   `paper/manuscript/manuscript_skeleton.md` (system name and working title;
   add one line "Formerly AgroAdvisor-ET (renamed 31 Oct 2026)"). Proposed
   working title for the skeleton (owner may edit): *"AgroEcoAdvisor:
   coupling meta-analytic machine learning, retrieval-augmented generation and
   a knowledge graph for evidence-grounded agroecological advisory — a case
   study from Ethiopia"*.

## Scope — what must NOT change
- **Corpus data:** nothing under `rag/corpus/`, `rag/index/`, `rag/graph/store/`
  (the word "agroadvisory" occurs ~30 times inside guidance documents — it is
  source text, not our brand). Use exact, case-sensitive brand tokens; never a
  blanket case-insensitive replace.
- **Data-contract names** (CLAUDE.md doctrine 4): `CSA_practices`,
  `practice_family`, dataset columns, `csa_model.joblib`, Chroma collection
  names, API routes and response field names.
- **Internal identifiers:** the class `AgroAdvisor` in `advisor_agent.py` and
  its compat shim, module and package names — keep (renaming them is churn
  with no user-visible benefit).
- **History:** `progress.md` entries before this phase, `SESSION_HANDOFF.md`,
  `MIGRATION_MAP.md` stay as written (historical record).
- **Folders and remotes:** the local clone `C:\dev\agroadvisor-et` and the
  GitHub repository name stay (renaming them would break the owner's tooling
  and the Cowork connection; a later, separate decision).
- **Browser storage:** no storage key or cookie name may change (none contains
  the brand today — verify).

## Tests and verification
- The English byte-identity fixture `app/backend/tests/fixtures/en_texts_pre_u1.json`
  is regenerated deliberately; add a check (in the report) that the ONLY
  differences versus the previous fixture are the brand/tagline tokens.
- Backend `pytest -q` (all green; with rasters on the owner's machine),
  frontend `tsc`, `eslint .` 0/0, `vitest run`, `next build`, Playwright E2E
  (update text assertions that mention the old name).
- A final repo-wide grep, reported in full: zero occurrences of
  `AgroAdvisor-ET` / `agroadvisor-et` outside the allowed history files and
  the "formerly" lines; zero `AgroAdvisor` as a product name outside the
  internal class name and history files; `git diff --stat -- rag/corpus
  rag/index rag/graph/store` empty.
- Screenshots: header + home hero in en/am/om (desktop) and the 390 px header,
  saved under `docs/design/screenshots/r1-*.png`.

## Report
Append to `progress.md`: the decision record, the before/after inventory
(counts per file), the fixture diff summary, test results, the final grep,
and anything left for the owner (native review of the two tagline
translations; renaming the GitHub repo/folder later if desired). Then stop.
