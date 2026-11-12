# AgroAdvisor-ET — Engineering Progress Log

Working protocol (agreed 18 Aug 2026):
- **Senior AI Engineer & Researcher (reviewer):** frames each phase, writes the
  engineering brief, reviews the implementation, records verdict + next steps here.
- **Implementation agent (Claude Code):** executes the brief, then APPENDS a
  phase report to this file: what was built, files touched, design decisions,
  what was verified in the sandbox, and what needs machine-side verification.
- **Misganu (owner):** runs machine-bound steps (corpus download, pytest with
  rasters, npm, git commits) and reports results back.

Report format per phase: `## Phase <id> — <title>` with sections
**Built / Files / Decisions / Verified (sandbox) / Needs local verification**,
followed by a `### Review (Senior Engineer)` block with verdict and next steps.

---

## Phase P0 — Clean repository (18 Aug 2026) — DONE ✅
Repo `agroadvisor-et/` assembled from the AgroGuide prototype: data/, geodata/
(11-layer stack, byte-verified), pipelines/, model/, app/, docs/, rag/, paper/.
MIGRATION_MAP.md records provenance. Git recreated natively on Windows
(233 files, initial commit).

## Phase P1 — Rebrand + refactor (18 Aug 2026) — DONE ✅
AgroAdvisor-ET branding across backend + frontend; canonical agent renamed
`advisor_agent.py` (class `AgroAdvisor`, compat shim kept); `LAYERS_DIR`
config so the raster stack lives once at `geodata/layers`; OpenAI-first chat
(`gpt-4o-mini`, key in backend/.env). **Verified: 25/25 pytest green on
owner's machine.**

## Phase P2a — RAG corpus & index pipeline (18 Aug 2026) — DONE ✅ (code) / ⏳ (corpus run)
`rag/ingest/fetch_papers.py` (DOI → Crossref → Unpaywall, resumable manifest),
`parse_and_chunk.py` (pypdf, refs-trimmed, ~380-word chunks, era_code on every
chunk), `build_index.py` (text-embedding-3-small → persistent Chroma),
`retrieve.py` (hybrid dense+BM25, RRF fusion, query built from the
recommendation JSON). Corpus acquisition running on owner's machine — coverage
numbers pending.

---
(Implementation agent: append Phase P2b report below.)

## Phase P2b — Grounded /explain endpoint (18 Aug 2026)

**Built**
- `POST /explain`: takes a `/recommend` payload (+ optional user question,
  `k` 1–20), retrieves evidence via `rag.retrieve.RagRetriever`
  (`retrieve_for_recommendation`), and returns
  `{explanation, citations[], grounded, llm_used}`.
- LLM path (OpenAI `gpt-4o-mini`, temperature 0.2, **no tools**): prompt =
  recommendation JSON verbatim + passages labeled `[1]…[k]` (era_code, title,
  year) + strict cite-or-silent instructions (explain WHY the practices fit
  this context and HOW to apply them; only numbers from the JSON or quoted
  from cited passages).
- Numeric guardrail: every `\d+(?:\.\d+)?` token in the LLM text must appear
  in the recommendation JSON (any nesting level, rounded forms included), in a
  cited chunk's text/title/year/era_code, or be an integer 0–10 (`[n]`
  citation markers are stripped first). Any other number ⇒ LLM text discarded.
- Deterministic fallback (no key / LLM failure / guardrail trip): one sentence
  per recommended practice = the engine's own effect string + "supported by
  evidence from" + up to 2 practice-matched citations (title + era_code).
  `grounded=true, llm_used=false`. Zero retrieved chunks ⇒ `grounded=false`
  and an explicit no-claims message.
- Degradation: no index/chunks on disk ⇒ 503 with "RAG index not built — run
  rag/ingest …" (checked via cheap filesystem `is_ready()`, no chromadb
  import); rest of the API unaffected. `GET /metadata` now carries
  `rag_ready: bool`.

**Files**
- `app/backend/app/services/explain_service.py` — new; retriever lazy-loaded
  by inserting the repo root (`backend_root.parents[1]`) on `sys.path`
  (mirrors `recommender_service`); retriever injectable via `set_retriever()`
  or `explain(..., retriever=)` for tests.
- `app/backend/app/routers/explain.py` — new, tag "explain", thin.
- `app/backend/app/config.py` — `rag_index_dir` (RAG_INDEX_DIR, default
  `../../rag/index/store`) + `rag_chunks_path` (RAG_CHUNKS_PATH, default
  `../../rag/corpus/chunks.jsonl`), each with a `resolved_*` property
  resolving against `backend_root` like `resolved_layers_dir`.
- `app/backend/app/schemas.py` — `ExplainRequest` / `ExplainCitation` /
  `ExplainResponse`; `MetadataResponse.rag_ready`.
- `app/backend/app/main.py` — include explain router.
- `app/backend/app/metadata_service.py` — `rag_ready` in payload.
- `app/backend/tests/test_explain.py` — new, 18 tests, no rasterio/chromadb/
  network needed.
- `app/backend/README.md` — endpoint row + explain-layer paragraph.

**Decisions**
- Synchronous `httpx.post` in a sync route (FastAPI threadpool) instead of the
  async chat client — /explain is one round-trip, no streaming, no tools.
- Guardrail also whitelists numbers from cited chunks' title/year/era_code
  metadata (not just text) so "(2019)"-style attributions don't false-trip;
  still strictly provenance-bound.
- LLM/HTTP errors degrade to the deterministic fallback (logged warning), never
  a 500 — retrieval already succeeded, so we can still answer grounded.
- `is_ready()` is a pure filesystem check so `/metadata` stays fast and the
  backend never imports chromadb unless `/explain` is actually used.

**Verified (sandbox)**
- `python3 -m py_compile` clean on all touched files.
- `pytest tests/test_explain.py` → **18/18 green** (guardrail allow/reject
  incl. rounded forms + chunk-quoted numbers + `[n]` markers; fallback text
  content incl. practice-matched citations; citation shaping/snippet
  truncation/year coercion; `is_ready()` false/true; explain() no-key,
  no-chunks, guardrail-pass, guardrail-fail, LLM-failure paths; prompt
  content).
- `from rag.retrieve import RagRetriever` confirmed importable with repo root
  on `sys.path` (namespace package, no `rag/__init__.py` needed).
- No TODO/FIXME left; existing tests untouched.

**Needs local verification**
- Full-stack run with the real Chroma index once the P2a corpus build
  finishes: `POST /explain` end-to-end with OPENAI_API_KEY (LLM path +
  guardrail on real generations) and without it (fallback path), plus the 503
  before the index exists.
- `pytest -q` for the whole suite (test_api.py needs rasters/rasterio, absent
  here), and `/metadata` → `rag_ready` flips to true after `build_index.py`.
- Retrieval quality of `retrieve_for_recommendation` on the real corpus
  (k=8 default) — sandbox used a fake retriever only.

### Review (Senior Engineer) — APPROVED with hardening applied ✅
Code quality is high: doctrine respected (numbers stay the model's; cite-or-
silent enforced twice — prompt + guardrail), retriever injection makes the
tests honest, degradation paths are complete (no key → deterministic fallback;
no index → 503; LLM error → fallback, never 500). The two judgment calls
(sync httpx in a sync route; whitelisting numbers from citation metadata so
"(2019)" doesn't false-trip) are both correct.

Hardening applied in review:
1. `is_ready()` now requires `chroma.sqlite3` inside the index dir — an empty
   dir from an interrupted build no longer counts as ready (test updated,
   18/18 green).
2. Router wraps `explain()` in a try/except → clean 503 `explain_failed`
   envelope if the retriever fails to open a corrupt index (was: raw 500).

Accepted known limitations (tracked, not blockers):
- Word-form numbers ("one-third") pass the regex guardrail — mitigated by the
  prompt; will be measured in the P3 faithfulness evaluation rather than
  over-engineered now.

**Owner verification (18 Aug 2026):** corpus built end-to-end on owner's
machine — manifest 306 studies, **23 full-text PDFs**, 678 chunks from
23 full-text + 75 abstract-only studies; Chroma index holds 678 chunks;
**pytest 43/43 green** (25 engine/API + 18 explain). ✅

### Review of corpus results (Senior Engineer) — coverage remediation needed
The pipeline is sound but coverage is the bottleneck: ~208/306 studies
contribute nothing to retrieval. The fetch log shows many `gold`/`green`/
`hybrid`/`bronze` statuses with no PDF — open-access papers where Unpaywall's
*best* location lacked a direct `url_for_pdf`. v1 only tried that one field.
This is legally-open content we simply didn't chase. For the manuscript's
corpus table we want this maximized before freezing numbers.

**Next steps → Phase P2a.1 — OA coverage remediation (assigned to Claude Code):**
Extend `rag/ingest/fetch_papers.py` (OA sources only — never bypass paywalls):
1. `--retry-missing` mode: reprocess only manifest entries with `pdf_file:
   null` (and/or missing abstract), rewriting the manifest in place; successes
   from the first run untouched.
2. Fallback chain per DOI, stopping at first success, polite headers + sleep:
   a. Unpaywall **all** `oa_locations` (not just best): try `url_for_pdf`,
      then `url` with PDF content sniffing (`%PDF` magic, follow redirects).
   b. **OpenAlex** (`https://api.openalex.org/works/https://doi.org/<doi>`,
      `mailto` param): `best_oa_location.pdf_url`, then other locations; also
      reconstruct the abstract from `abstract_inverted_index` when Crossref
      had none (record `abstract_source`).
   c. **Europe PMC** (`https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=DOI:"<doi>"`):
      if `isOpenAccess`, fetch full text XML (`.../fullTextXML`) — save as
      `<code>.xml`; extract abstract otherwise.
   d. Crossref `link` array (full-text URLs some publishers deposit).
3. Manifest additions: `pdf_source` / `abstract_source` / `fulltext_xml`
   (keep all existing fields; parse_and_chunk must handle `.xml` full text —
   simple tag-strip is fine).
4. Rerun `parse_and_chunk.py` + `build_index.py` (both resumable; note:
   changed studies' old chunks may need `--rebuild` handling or index reset —
   agent's call, document it).
5. Report the final coverage table in the phase report: n full-text (pdf/xml),
   n abstract-only, n metadata-only — this table goes into the paper.
Acceptance: coverage strictly improves; no paywall circumvention; existing
tests stay green; phase report appended here.

**Then queued:** Phase P2c (frontend Evidence chips + grounded chat
follow-ups), Phase P3 (evaluation harness: Recall@k/MRR, faithfulness,
expert-study materials).

### End-to-end verification of /explain (Senior Engineer, 18 Aug 2026) ✅
Incident first: initial /explain calls returned 503 `explain_failed` — root
cause was a stale `OPENAI_API_KEY` in `backend/.env` (indexing had used a
fresh key from the shell env, masking it). Fixed: owner updated `.env`;
`rag/retrieve.py` patched to share `build_index.py`'s `.env` fallback and to
raise explicit messages for missing/rejected keys instead of a bare 401.

Live result (Dry Kolla, erosion control, soil loss → Mulch-Water Harvesting,
`grounded=true, llm_used=true`): retrieval surfaced on-topic evidence (in-situ
water-harvesting soil-loss trial EO0016; conservation-agriculture Vertisol
runoff/soil-loss sections NN0206; SWC/terracing studies DK0151, EO0061) and
the generation cited them inline. **Faithfulness audit passed:** the
explanation's "reductions as high as 90% with tied ridges [1]" traces to a
verbatim EO0016 sentence ("…reduced average soil loss … by 82 and 90%
respectively"). Guardrail admitted it correctly (number present in cited
chunk text).

Tracked findings (non-blocking):
1. Citation list shows one entry per chunk → duplicate studies (NN0206 ×3);
   UI must dedupe per study — fold into **P2c**.
2. Crossref titles carry HTML tags/entities (`<i>`, `&amp;`) — add
   tag/entity stripping to the fetcher — fold into **P2a.1**.
3. The 0–10 small-integer guardrail allowance admits implementation
   quantities like "5–10 cm mulch depth" that aren't from evidence. Standard
   agronomy, low risk, but it goes on the **P3** faithfulness-evaluation
   checklist rather than being over-engineered now.
4. One tangential hit at k=8 (NN0412, intercropping/soil moisture) —
   retrieval precision to be quantified in P3.

**Status: P2b closed. Next action: owner launches Claude Code for Phase
P2a.1** (OA coverage remediation, brief above — now including finding #2,
title tag/entity cleaning in `fetch_papers.py`).

## Phase P2a.1 — OA coverage remediation (18 Aug 2026)

**Built**
- `fetch_papers.py --retry-missing`: reprocesses ONLY manifest entries lacking
  full text on disk and/or an abstract (289/306 on the current manifest —
  283 without full text + 6 PDF-holders missing abstracts); manifest rewritten
  in place (atomic `os.replace`, `.bak` backup kept); first-run successes pass
  through untouched apart from metadata cleaning. Entries whose recorded
  `pdf_file` vanished from disk count as missing (self-healing).
- OA fallback chain per DOI (`acquire()`, used by both fresh and retry modes;
  stops at first full-text success; URLs deduped across sources; polite UA +
  `--sleep` throttle; OA sources only — no paywall circumvention):
  (a) Unpaywall **all** `oa_locations` — every `url_for_pdf`, then every
  landing `url`, all with `%PDF` magic sniffing; (b) OpenAlex (`mailto` polite
  pool) — `best_oa_location` + all locations' `pdf_url`/`landing_page_url`,
  plus abstract reconstruction from `abstract_inverted_index`; (c) Europe PMC —
  if `isOpenAccess` with a PMCID, full-text JATS XML saved to
  `corpus/xml/<era_code>.xml`; abstract fallback otherwise; (d) Crossref
  `link` array (content-type `application/pdf`/`unspecified`).
- Manifest provenance fields: `pdf_source` (`unpaywall` / `unpaywall_landing` /
  `openalex` / `crossref_link`), `abstract_source` (`crossref` / `openalex` /
  `europepmc`), `fulltext_xml`.
- **Finding #2 (title tag/entity cleaning):** `clean_html()` strips tags and
  unescapes entities twice (Crossref deposits both `<i>…</i>` and
  double-escaped `&lt;i&gt;…`), applied to title/journal/abstract on every
  fetch AND retroactively to all existing records during the retry rewrite —
  covers the 36 polluted titles in the current manifest.
- `parse_and_chunk.py`: JATS XML full-text support (`source="xml"`) — keeps
  only `<abstract>` + `<body>` (front matter is metadata noise), drops
  `ref-list`/`back`/`xref`/`table-wrap`/`fig`/formulas, tag-strips +
  unescapes; PDF still preferred over XML, abstract remains the last resort.
- `build_index.py --rebuild`: drops the Chroma collection and re-embeds
  everything. **Required after the corpus changes**: chunk ids are
  reassigned per study, so a study upgraded from abstract-only to full text
  reuses `<code>_000` with different text and resumable mode would silently
  keep the stale embedding. parse_and_chunk prints a reminder.

**Files**
- `rag/ingest/fetch_papers.py` — rewritten (fallback chain, retry mode,
  cleaning, provenance, coverage summary).
- `rag/ingest/parse_and_chunk.py` — XML extraction + counts (`N full-text
  (X PDF + Y XML) + Z abstract-only`).
- `rag/ingest/build_index.py` — `--rebuild` flag.
- `rag/README.md` — layout + build steps updated (retry step, `corpus/xml/`,
  `--rebuild` warning).
- `.gitignore` — `rag/corpus/xml/*.xml`, `rag/corpus/manifest.jsonl.bak`.

**Decisions**
- Failed/non-PDF downloads are now deleted instead of renamed to `.html` —
  with up to ~10 candidate URLs per study the old keep-for-review behaviour
  would litter the corpus (the 11 existing `.html` leftovers can be removed).
- Retry mode re-fetches Crossref metadata per retried study (one extra
  request): refreshes cleaned titles and picks up newly deposited abstracts.
- Europe PMC full text is served at `/rest/<PMCID>/fullTextXML` — the
  documented-looking `<source>/<id>` form 404s (verified live); XML kept only
  if the body contains `<article` in the first 4 KB.
- Index-staleness handling = explicit `--rebuild` (reviewer's "agent's call"):
  simplest correct option; content-hash chunk ids were rejected as they'd
  churn every id on any parser tweak and complicate the era_code_NNN join
  convention.

**Verified (sandbox — WSL on owner's machine; real corpus left untouched)**
- `py_compile` clean on all three scripts; backend `test_explain.py`
  **18/18 green** (deps installed to an isolated scratchpad target).
- Offline unit checks: `clean_html` (single + double-escaped, entities, None/
  empty), inverted-index abstract reconstruction, `needs_retry` matrix (pdf on
  disk / xml on disk / abstract-only / vanished file / no-DOI),
  `coverage_summary`, JATS extraction (refs/tables/xref dropped, entities
  unescaped), chunking of XML text.
- **Live API smoke test** on an isolated 11-entry manifest copy (scratchpad,
  sampling gold/green/hybrid/bronze/closed failures from the real manifest):
  3 full-text PDFs recovered (OpenAlex ×2, Unpaywall all-locations ×1, all
  `%PDF`-verified), 6 abstracts recovered (OpenAlex), manifest rewrite
  preserved order/fields, the double-escaped AG0016 title came out clean.
- **Live Europe PMC XML end-to-end** (PMC8486100): 157 KB JATS → 4,693 words
  → 19 chunks, front-matter noise excluded.
- `parse_and_chunk.py` on the scratch corpus: 92 chunks from 4 full-text
  (3 PDF + 1 XML) + 6 abstract-only; chunk schema unchanged (downstream
  retriever/explain unaffected; `source` is unconstrained there).

**Needs local verification (owner)**
- Full remediation run + rechunk + reindex (from `rag/`, ~30–60 min fetch;
  reindex still well under $1):
  `export UNPAYWALL_EMAIL="<email>"`
  `python ingest/fetch_papers.py --doi-list ../paper/references/era_doi_list.csv --out corpus --retry-missing`
  `python ingest/parse_and_chunk.py --corpus corpus`
  `python ingest/build_index.py --corpus corpus --index index/store --rebuild`
- The final coverage table for the paper is printed by both fetch (`N studies:
  X full-text (P PDF + Q XML), Y abstract-only, Z metadata-only`) and
  parse_and_chunk — please report the numbers back. Smoke-sample projection:
  2/10 remediable studies gained full text and 6/10 gained abstracts, so
  expect roughly 60–100+ full-text studies total and most of the 208
  metadata-only studies to become abstract-only.
- `pytest -q` full suite (test_api.py needs rasterio) and a `/explain`
  spot-check after the rebuilt index (citations should now show clean titles).

### Review (Senior Engineer) — P2a.1 APPROVED ✅ (no changes required)
Read the full diff (`fetch_papers.py` rewrite, `parse_and_chunk.py` XML path,
`build_index.py --rebuild`). Verdict: correct and careful work.

What earns the approval:
- **The agent caught the stale-embedding hazard itself** (reused chunk ids
  with changed text after remediation) and handled it properly with
  `--rebuild` (drop collection + re-embed) plus warnings in both scripts.
  This was the subtle bug of the phase.
- Fallback chain is legally clean (OA locations only), polite (shared email,
  throttled), and evidence-safe: PDF magic-byte sniffing, non-PDF downloads
  unlinked, XML sanity-checked for `<article`.
- Retry mode is atomic (tmp + os.replace, .bak kept) and non-destructive:
  first-run successes pass through untouched except metadata cleaning.
- Finding #2 (HTML tags/entities in titles) fixed retroactively across the
  whole manifest via double unescape+strip — correct for Crossref's
  double-encoded titles.
- JATS extraction keeps `<abstract>`+`<body>` only, drops refs/tables/figs/
  xref, turns block closers into paragraph breaks — chunker-compatible.

Minor notes (accepted, no rework): retry of an XML-only study re-attempts PDF
sources (harmless duplication of effort); `--limit` in retry mode skips
metadata cleaning of untouched tail records (cosmetic; full runs unaffected);
`rec in targets` relies on identity-implies-equality (fine at this scale).

**Owner actions to close P2a.1** (from `rag/`, backend venv active,
UNPAYWALL_EMAIL set):
```
python ingest/fetch_papers.py --doi-list ../paper/references/era_doi_list.csv --out corpus --retry-missing
python ingest/parse_and_chunk.py --corpus corpus
python ingest/build_index.py --corpus corpus --index index/store --rebuild
python retrieve.py "mulch water harvesting soil loss Ethiopia Dry Kolla"
```
Then restart uvicorn, re-run the /explain smoke test (titles should now be
clean), run `pytest -q`, commit, and report the final coverage line — that
line is the manuscript's corpus table. Re-embedding the full corpus stays
well under $1.

**Then queued:** P2c (frontend Evidence chips with per-study dedup + grounded
chat follow-ups), P3 (evaluation harness).

**P2a.1 closure (owner run, 18 Aug 2026):**
Incident during first retry run: `KeyError: pdf_source` — v1 manifest records
with a PDF but no provenance field crashed the status printer, and the
end-of-run-only manifest write lost 11 results (downloads survived on disk).
*Review accountability:* this path was missed in the senior review (acquisition
logic was checked; status printing against v1-shaped records was not). Hotfix
applied by the reviewer: safe `.get()` provenance defaults, per-record
try/except (one bad study logs ERROR and continues), manifest checkpointed
every 25 studies + `finally` rewrite (progress survives crash/Ctrl+C).

**Final corpus (FROZEN for the manuscript):**
| Tier | v1 | v2 (P2a.1) |
|---|---|---|
| Full-text | 23 (7.5%) | **40 (13.1%)** = 31 PDF + 9 XML |
| Abstract-only | 75 (24.5%) | **168 (54.9%)** |
| Metadata-only | 98 remain (32.0%) — overwhelmingly `closed` (no legal OA copy) | |
| Contributing studies | 98 (32%) | **208 (68%)** |
| Chunks indexed | 678 | **1,191** |

Retrieval spot-check post-rebuild: clean titles; top hits now FULL-TEXT
sections of EO0016 incl. the 82/90/60% soil-loss passage (previously
abstract-only). Remaining metadata-only studies require institutional access —
recorded as future work, not pursued. **Phase P2a.1 closed.** ✅

### Next steps → Phase P2c — Evidence in the product (assigned to Claude Code)
1. **Backend — citation dedup (finding #1):** in
   `app/backend/app/services/explain_service.py`, dedupe `citations` per
   `era_code` (keep first/best snippet, add `n_passages: int`); update
   `ExplainCitation` schema + tests (currently NN0206 appears 3×).
2. **Frontend — Evidence panel:** on recommendation cards (both `/dashboard`
   and `/chat`), add an "Evidence" action: lazily POST the current
   recommendation to `/explain` (new function in `src/lib/api.ts`, types in
   `src/lib/types.ts`), render the grounded explanation + one chip per study
   (era_code · title · year, linking to `https://doi.org/<doi>` when doi
   present), a subtle `grounded`/`llm_used` badge, loading + error states.
   Hide the action entirely when `/metadata.rag_ready` is false. Follow the
   existing component style (Tailwind, clean-by-default: evidence only on
   demand).
3. **Scope guard:** server-side RAG grounding of chat follow-ups is NOT in
   this phase (queued as P2d) — chat gets the same client-side Evidence panel
   on its recommendation cards, nothing more.
4. Tests: backend dedup unit tests; frontend `npm run test` for the new lib
   function; `npm run build` must pass.
5. Append the phase report to progress.md per CLAUDE.md and stop.

## Phase P2c — Evidence in the product (18 Aug 2026)

**Built**
- **Backend citation dedup (finding #1):** `shape_citations()` now returns one
  citation per **study**, not per chunk — chunks are grouped by `era_code`
  (fallback key: doi → title → unique chunk slot, so two unidentified studies
  never collapse); the highest-ranked chunk supplies `snippet` and `practice`,
  and a new `n_passages` field counts how many retrieved passages the study
  contributed. `ExplainCitation` gains `n_passages: int = Field(default=1,
  ge=1)` (additive — old payloads still validate). The deterministic fallback
  text now also cites each study at most once per practice (previously two
  chunks of the same paper could produce a duplicated title).
- **Frontend Evidence panel** (`EvidencePanel`, wired into
  `RecommendationPanel` — so it appears on recommendation cards in BOTH
  `/dashboard` and `/chat` automatically): an "Evidence" toggle in the same
  style as "Why this?". On first open it lazily POSTs the current
  recommendation to `/explain` via the new `postExplain()` in `src/lib/api.ts`
  and caches the result for the card's lifetime. Renders: the grounded
  explanation; subtle badges ("Grounded in literature" / "No evidence
  retrieved" + "AI summary" / "Deterministic summary" from
  `grounded`/`llm_used`); one chip per study — `era_code · title · year`,
  `×N` passage count when >1, snippet as hover tooltip — linking to
  `https://doi.org/<doi>` (new tab, `noopener noreferrer`) when a DOI exists.
  Loading state (spinner) and error state (message + "Try again" retry).
- **`rag_ready` gate:** `Metadata.rag_ready?: boolean` added to the frontend
  types; when `/metadata` reports false (or the field is absent), the
  Evidence action is not rendered at all — the UI stays exactly as before.
- **Scope guard respected:** no server-side chat grounding — chat gets the
  same client-side panel on its recommendation cards, nothing more (P2d).

**Files**
- `app/backend/app/services/explain_service.py` — per-study dedup in
  `shape_citations()`; one-mention-per-study in `build_fallback_text()`.
- `app/backend/app/schemas.py` — `ExplainCitation.n_passages`, docstring.
- `app/backend/tests/test_explain.py` — 3 new tests (dedup order/counting/
  snippet-from-top-chunk; unidentified studies never collapsed; fallback
  cites each study once) + `n_passages` assertion in the existing shaping
  test.
- `app/backend/README.md` — citation-dedup sentence.
- `app/frontend/src/lib/types.ts` — `ExplainCitation`, `ExplainResponse`,
  `ExplainRequestPayload`, `Metadata.rag_ready`.
- `app/frontend/src/lib/api.ts` — `postExplain()` (reuses `parseError`, so
  the 503 "RAG index not built…" envelope surfaces verbatim in the panel).
- `app/frontend/src/components/evidence-panel.tsx` — new.
- `app/frontend/src/components/recommendation-card.tsx` — renders
  `<EvidencePanel data={data} />` above the disclaimer line.
- `app/frontend/src/lib/api.test.ts` — new vitest suite for `postExplain`.
- `app/frontend/src/components/setup-pickers.tsx` — removed an unused
  `AnimatePresence` import (pre-existing, untouched since the initial commit;
  it failed `next build`'s lint gate, which this phase requires to pass).

**Decisions**
- Dedup lives in `shape_citations()` itself rather than a separate pass —
  every consumer (LLM path, fallback path, router) gets per-study citations
  with no call-site changes; the guardrail still whitelists numbers from ALL
  retrieved chunks (unchanged), so deduping the display list cannot make the
  guardrail stricter or looser.
- The LLM prompt still numbers passages per chunk (`[n]`) — renumbering per
  study would change prompt/guardrail behaviour, out of P2c scope. The UI
  chips are study-level and carry no `[n]`, so no mismatch is displayed.
- One `EvidencePanel` inside `RecommendationPanel` instead of two page-level
  integrations: both `/dashboard` and `/chat` render that component, so the
  feature lands in both with a single code path (and any future surface gets
  it for free).
- Evidence fetch result is cached in component state — collapsing and
  re-opening the panel does not re-POST; "Try again" appears only on error.
- Chip key: `era_code ?? doi ?? title ?? index`, matching the dedup key.

**Verified (sandbox — WSL, Windows Node toolchain via interop)**
- Backend: `py_compile` clean; `pytest tests/test_explain.py` → **21/21
  green** (18 existing + 3 new; `test_api.py` still needs rasterio, not
  runnable here).
- Frontend: `npm ci` + `npm run test` → **16/16 green** (3 suites: existing
  utils/chat-flow + new `api.test.ts` covering URL/method/body defaults,
  question/k forwarding, and the 503 error envelope message); `npm run
  build` → **compiled, lint + type checks passed, all 7 routes generated**.
- Gating logic: `rag_ready` optional in the type, panel returns `null` when
  absent/false — verified by type-check + code path (no UI regression when
  the backend predates P2b's metadata field).

**Needs local verification (owner)**
- Visual pass with the live stack: `/dashboard` → recommend → "Evidence"
  (spinner → explanation + deduped chips, NN0206-style duplicates gone,
  clean titles, DOI links open) and the same on a `/chat` recommendation
  card; badge states with and without `OPENAI_API_KEY`; panel absent after
  temporarily renaming the index dir (`rag_ready=false`).
- `pytest -q` full suite (43+ with rasters) on the machine, then commit.

### Review (Senior Engineer) — P2c APPROVED ✅ (no changes required)
Read the diff. Backend dedup is correct: keyed on `era_code` with `doi`/`title`
fallbacks and a unique per-chunk fallback (two unidentified studies can never
collapse); the top-ranked chunk supplies snippet + practice; `n_passages`
counted; the numeric guardrail still validates against ALL retrieved chunks —
the right call, since the LLM saw all passages. Fallback text now cites each
study once. Frontend `EvidencePanel` is properly engineered: gated on
`/metadata.rag_ready`, lazy fetch cached after first open, loading/error/retry
states, unmount guard, DOI links (`noopener`), snippet tooltips, ×N passage
badges, grounded/llm_used badges, single code path for /dashboard and /chat via
RecommendationPanel. The out-of-scope lint fix (unused import in
setup-pickers.tsx, pre-existing) was necessary for the build gate and honestly
disclosed — accepted.

Tracked finding (polish, non-blocking): inline `[n]` markers in the LLM
explanation are CHUNK-numbered while the chip list is now STUDY-deduped, so a
reader may see `[6]` with fewer than 6 chips. Fix when next touching the
explain layer: renumber prompt passages per study, or post-map chunk markers →
study order. → queued into P2d/P3 backlog.

**Owner actions to close P2c:** visual pass with the live stack (npm run dev +
uvicorn): Evidence toggle on a dashboard card and a chat card; deduped chips;
DOI links open; badges correct with the API key set; then commit.

### Next steps → Phase P3 — Evaluation harness (assigned to Claude Code)
Everything below runs offline against the frozen corpus/index; owner executes.
1. **`rag/eval/build_queries.py`** — build the evaluation query set from
   `data/processed/CSA_ERA_final_model_ready.csv`: sample ~50 scenarios
   (practice_family × indicator × a real study location), stratified across
   the 5 families and 7 indicators. **Silver relevance labels:** for each
   scenario, relevant studies = ERA-source era_codes (strip the `ERA_` prefix
   from `Study_No_`) whose rows match the scenario's practice family +
   indicator (and top practice when available). Skip scenarios whose relevant
   studies contribute zero chunks to the corpus; report how many were
   skipped. Output `rag/eval/queries.jsonl`.
2. **`rag/eval/eval_retrieval.py`** — run the real `RagRetriever` over the
   query set; report Recall@4/8/16 and MRR, overall and per family/indicator;
   write `rag/eval/results/retrieval_metrics.json` + a small md table.
3. **`rag/eval/eval_faithfulness.py`** — for ~30 scenarios call
   `explain_service.explain()` (live LLM path); record grounded/llm_used
   rates and guardrail trips; auto-check every numeric sentence against cited
   chunk text; emit `results/faithfulness_audit.csv` (one row per claim
   sentence: text, cited study, auto-verdict, blank column for the human
   audit) — includes word-form numbers (regex for one/two/…/half/third) so the
   known guardrail gap is MEASURED.
4. **`rag/eval/expert_study/`** — materials for the blinded expert study:
   `protocol.md` (A/B: deterministic model-only text vs model+RAG explanation,
   ~30 scenarios, 3–5 experts, Likert 1–5 on agronomic soundness, usefulness,
   trustworthiness, clarity; randomized order, condition blinded),
   `make_packets.py` producing per-expert scoring sheets (CSV) from the same
   scenario sample.
5. No changes to app/ or rag/retrieve.py in this phase. Tests for the label
   builder (pure functions). Append the phase report per CLAUDE.md and stop.

## Phase P3 — Evaluation harness (20 Aug 2026)

**Built**
- **`rag/eval/build_queries.py` (step 1):** builds the evaluation query set
  from `data/processed/CSA_ERA_final_model_ready.csv`. Scenarios are real ERA
  study locations crossed with the practice family × indicator studied there,
  stratified over the 5 families × 7 indicators (per-cell quota =
  round(n_target / n_cells), anchors drawn per distinct study, deterministic
  seed). Silver labels: relevant studies = ERA-source era_codes (`ERA_`
  prefix stripped from `Study_No_`) whose rows match the scenario's family +
  indicator + top practice, restricted to studies that contribute chunks to
  the corpus; a family-level label set (no practice constraint) is stored
  alongside for looser diagnostics. Candidates whose relevant set is empty
  after the corpus restriction are skipped and counted. Query text is
  composed by the REAL `rag.retrieve.build_query_text` over a
  recommendation-shaped stub (wrap, never fork). Output: `queries.jsonl` +
  `results/queries_build_report.json`. **Actual run: 50 scenarios, 26/29
  cells, all 5 families and all 7 indicators covered, 6 candidates skipped.**
- **`rag/eval/eval_retrieval.py` (step 2):** runs the real hybrid
  `RagRetriever` (via `default_retriever()`) at k=16 per scenario; reports
  study-level Recall@4/8/16 (relevant studies seen within the first k chunks)
  and MRR (first chunk from a relevant study), overall and per family /
  indicator, against both strict and family-level labels. Writes
  `results/retrieval_metrics.json` (summary + per-scenario ranked era_codes)
  and a md table (`results/retrieval_metrics.md`).
- **`rag/eval/eval_faithfulness.py` (step 3):** runs the FULL production
  stack per scenario — `recommender_service.recommend()` (canonical engine,
  real rasters) then `explain_service.explain()` on the live LLM path, with a
  `RecordingRetriever` shim so the audit sees the exact chunks explain() used
  and a logging handler that counts numeric-guardrail trips/rejections.
  Every numeric sentence of the explanation is audited: digit tokens re-checked
  with the service's own `allowed_numbers`/`_number_variants` (production
  rules, not a reimplementation) against all retrieved chunks AND against the
  sentence's own `[n]`-cited passages (stricter `cited_support` column);
  word-form numbers (one/two/…/half/third/quarter/twice/double/…) are
  detected and checked so the known digit-only guardrail gap is measured, not
  assumed. Markdown headings/list enumerators are stripped before sentence
  splitting so "#### 1." never becomes a claim row. Outputs:
  `results/faithfulness_audit.csv` (one row per claim sentence, blank
  `human_verdict`/`human_notes` columns for the human pass),
  `results/faithfulness_summary.json` (llm_used/grounded rates, guardrail
  trips, verdict counts), `results/explanations.jsonl` (both conditions for
  the expert study). Scenarios picked round-robin over cells (stratified ~30).
- **`rag/eval/expert_study/` (step 4):** `protocol.md` — blinded
  within-subject A/B design (A = deterministic model-only text via
  `build_fallback_text(rec, [])`, B = model+RAG explanation; ~30 scenarios,
  3–5 experts, Likert 1–5 on agronomic soundness / usefulness /
  trustworthiness / clarity; randomized order, condition blinded; Wilcoxon +
  Krippendorff's α analysis plan). `make_packets.py` (pure stdlib) — per-expert
  CSV packets with opaque item codes, per-expert scenario shuffle, per-scenario
  A/B position randomization, blank rating columns; `answer_key.csv` kept
  separate with a do-not-send warning.
- **`rag/eval/test_build_queries.py`:** 9 unit tests over the pure functions
  (prefix stripping, label matching incl. corpus filter and family-level
  fallback, skip counting, stratification/determinism/quota, recommendation
  stub + real query-text composition, recall/MRR/aggregation).
- **`rag/eval/README.md`:** run order, requirements per step, label/metric
  definitions.

**Files**
- `rag/eval/build_queries.py`, `rag/eval/eval_retrieval.py`,
  `rag/eval/eval_faithfulness.py`, `rag/eval/test_build_queries.py`,
  `rag/eval/README.md` — new.
- `rag/eval/expert_study/protocol.md`, `rag/eval/expert_study/make_packets.py`
  — new.
- `rag/eval/queries.jsonl`, `rag/eval/results/queries_build_report.json`,
  `rag/eval/results/retrieval_metrics.{json,md}` — generated (real runs).
- No changes to `app/` or `rag/retrieve.py` (scope guard respected).

**Decisions**
- Anchors are sampled from ALL ERA study rows in a cell (not pre-filtered to
  corpus-backed studies) so the mandated skip count actually measures corpus
  coverage; labels are then corpus-restricted per the assignment.
- Recall@k is study-level at chunk depth k and MRR is chunk-rank based —
  matches how the app consumes retrieval (chunks in, per-study citations out).
- `eval_retrieval` uses `retriever.retrieve(query_text)` (single-practice
  scenarios ⇒ identical to the per-practice app path for that practice);
  `eval_faithfulness` uses the real engine + `explain()` end to end.
- The faithfulness audit imports `explain_service`'s own regex/whitelist
  helpers rather than re-implementing them, so it measures the production
  guardrail exactly; word-form numbers get their own verdict classes
  (`fail_wordform`/`fail_both`) to quantify the known gap.
- Both A and B texts are frozen into `explanations.jsonl` at audit time, so
  the expert study rates exactly what the system produced (and packets are
  reproducible pure-stdlib artifacts).

**Verified (sandbox — WSL, backend Windows venv via interop)**
- `py_compile` clean on all 5 new Python files; `pytest test_build_queries.py`
  → **9/9 green**.
- `build_queries.py` executed for real: 50 scenarios / 6 skipped / full
  family+indicator coverage (report above).
- `eval_retrieval.py` executed for real over all 50 scenarios against the
  frozen index (≈50 embedding calls): overall Recall@4/8/16 =
  0.111/0.235/0.333, MRR = 0.321 (strict labels); family-level MRR = 0.402.
  Weakest cells: water use efficiency (Recall@16 = 0.025) and Agro-forestry
  (MRR = 0.069) — genuine findings for the paper, written to
  `results/retrieval_metrics.{json,md}`.
- `eval_faithfulness.py` smoke-tested end-to-end with `--n 2` (real engine +
  rasters + live gpt-4o-mini): 2/2 scenarios completed, llm_used=grounded=1.0,
  0 guardrail trips, 8 clean claim rows with correct digit extraction and
  cited_support columns. Smoke outputs then deleted so `results/` only holds
  full-run artifacts.
- `make_packets.py` smoke-tested from the smoke explanations (2 experts) and
  with a 30-scenario synthetic set: both conditions present per scenario,
  X/Y slots carry both conditions (no positional leak), per-expert orders
  differ, fully deterministic per seed; smoke packets deleted.
- Backend regression: full `pytest -q` in `app/backend` → **46/46 green**
  (this venv has rasterio + layers, so `test_api.py` ran too).

**Needs local verification (owner)**
- The full faithfulness run: `python rag/eval/eval_faithfulness.py --n 30`
  (~30 gpt-4o-mini calls + embeddings) — then eyeball
  `results/faithfulness_summary.json` and fill the `human_verdict` column of
  `results/faithfulness_audit.csv` for the manuscript.
- After that run: `python rag/eval/expert_study/make_packets.py --experts <3-5>`
  and distribute packets per `expert_study/protocol.md` (never send
  `answer_key.csv`).
- Decide whether `rag/eval/queries.jsonl` + `results/` go into git (small,
  reproducible; I left them on disk, nothing committed).

### Review (Senior Engineer) — P3 APPROVED ✅ (independent re-verification, 20 Aug 2026)
Fresh session, fresh eyes: this review re-derived every headline claim from the
raw artifacts rather than trusting the phase report (or the predecessor
session's notes, which were never pasted here — this block is the verdict of
record).

**Independently verified (all reproduced exactly):**
1. **Metrics reproduce from the per-scenario dump.** Recomputed Recall@4/8/16
   and MRR from `results/retrieval_metrics.json`'s `retrieved_era_codes` against
   `queries.jsonl` labels: 0.1106 / 0.2346 / 0.3327, MRR 0.3206 — identical to
   the reported summary; 0 mismatches across all 50 stored per-scenario metric
   rows.
2. **Silver labels rebuilt from scratch.** Re-implemented the label rule
   (ERA-source rows, `ERA_` prefix strip, family+indicator+practice match,
   corpus restriction) directly against `CSA_ERA_final_model_ready.csv` (7,250
   ERA rows, all `ERA_`-prefixed) and `chunks.jsonl` (208 corpus era_codes):
   **0 mismatches in 100 label sets** (50 strict + 50 family-level); every
   strict set ⊆ its family set; all labels corpus-backed as required.
3. **Low Recall@8 is NOT a label-size artifact — confirmed, with sharper
   evidence.** Median strict relevant-set size = 3 (mean 6.4; 17/50 scenarios
   have exactly 1). Scenarios with small label sets (≤3) actually score
   *higher* recall@8 (0.264) than large ones (0.193) — denominator dilution is
   not the story. The real failure mode: 22/50 scenarios retrieve *zero*
   relevant studies in the top 8, and those misses are thin-evidence misses —
   their relevant studies are **96% abstract-only, ~2.6 chunks/study**, vs 63%
   abstract-only, ~13.5 chunks/study for hits. The duplicate-chunk crowding
   ceiling on recall@8 is 0.857, far above the observed 0.235. Evidence
   density, not label size, is the bottleneck — this directly supports the
   19 Aug corpus-expansion decision.
4. **Success@k computed from the dump** (not yet in the script outputs —
   see P3.1 below): strict Success@4/8/16 = **0.40 / 0.56 / 0.64**;
   family-level = 0.48 / 0.60 / 0.70. Success@8 = 0.56 confirmed as the
   headline grounding number.
5. **WUE terminology gap confirmed at the corpus level.** Of the 9 relevant
   WUE studies, only 3 say "water use efficiency" anywhere in their indexed
   text; 3 say "water productivity" instead. WUE recall is flat at 0.025 for
   k=4/8/16 (nothing new enters between k=8 and 16) — a query-vocabulary
   problem, fixable by expansion (queued into P5a).
6. **Faithfulness auditor audits the production rules.** Cross-checked
   `eval_faithfulness.py` against `explain_service.py`: `_NUM_RE`,
   `allowed_numbers`, `_number_variants`, the 0–10 small-int rule and the
   `[n]`-marker strip are the service's own; the RecordingRetriever guarantees
   the audit sees the exact chunks explain() used; word-form detection
   (`fail_wordform`/`fail_both`) measures the known digit-only gap as ordered.
7. **Expert-study blinding verified in code.** Opaque item codes, per-expert
   scenario shuffle, per-scenario A/B→X/Y randomization (shuffle before slot
   assignment — no positional leak), answer key written separately with
   do-not-send warnings, identical scenario context across conditions. Caveat
   (already in protocol.md, accepted): condition B is stylistically
   identifiable via its inline citations — that is the treatment, not a
   blinding failure; the label itself stays hidden.
8. **Tests re-run in this session's sandbox: 9/9 green**; `py_compile` clean on
   all five P3 files.

Minor notes (accepted, no rework):
- Family-level recall@k < strict recall@k (e.g. 0.162 vs 0.235 @8) is
  definitional (larger denominators), while family MRR > strict MRR. Add one
  footnote in the paper so reviewers don't misread it as an inconsistency.
- 8/50 anchors are not in their own relevant set (anchor study contributes no
  chunks) — correct by design; the skip counter measures corpus coverage as
  mandated.
- `eval_retrieval` uses the single-query path; equivalent to the app path for
  these single-practice scenarios, as the phase report's decision note says.

**Researcher's interpretation for the paper:** the system's grounding
guarantee should be reported as Success@8 = 0.56 strict (0.60 family-level)
with MRR 0.32; Recall@k is a secondary corpus-coverage diagnostic. The
measured evidence-density mechanism (point 3) is the empirical justification
for the Tier-2 expansion — write it up as such in Section 8.

### Next steps → Phase P3.1 + P5a — Success@k + guidance corpus (assigned to Claude Code)

**Context.** Decision record (19 Aug 2026, owner + reviewer): expand the RAG
corpus NOW, before the expert study and manuscript, under the binding two-tier
rule — **Tier 1 `era_corpus` is FROZEN** (the paper's novelty + the P3 metrics
above); **Tier 2 `guidance_corpus` is NEW** and powers the R2 function
(implementation how-to, costs, timing, failure modes). Never mix the tiers.

**P3.1 — Success@k in the eval outputs (small, do first).**
1. In `rag/eval/eval_retrieval.py`: add `success@{4,8,16}` (strict + family) —
   1.0 iff ≥1 relevant study appears in the top-k chunks — to per-scenario
   metrics, the summary JSON, and the md table (Success columns FIRST: it is
   the primary metric per research_project_plan.md §2.4). Unit tests for the
   pure function. Re-run `eval_retrieval.py` (queries.jsonl unchanged, ~50
   embedding calls) and confirm strict Success@4/8/16 = 0.40/0.56/0.64,
   family 0.48/0.60/0.70 (reviewer's independent numbers above); flag any drift.

**P5a — GARDIAN guidance corpus (Tier 2).**
2. **Fetch:** new `rag/ingest/fetch_gardian.py`. Source: HF dataset
   `CGIAR/gardian-cigi-ai-documents` (gated). Token: `HF_TOKEN` from
   `app/backend/.env` (reuse the `_find_api_key`-style fallback pattern —
   env var first, then .env; NEVER print it). Use `datasets` with streaming
   or split loading — do not assume the 85k-doc dataset fits in memory.
   Inspect the actual schema first; then filter to **Ethiopia** (country
   metadata if present, else title/text match) **AND** agroecology relevance
   (keyword map over the 5 practice families + core practice terms — document
   the exact filter rules in the phase report). Write
   `rag/corpus/guidance/manifest.jsonl` with full provenance (dataset id,
   document id/handle, title, year, source URL/DOI when present,
   `tier: "guidance"`). Report counts: total scanned → Ethiopia →
   agroecology-relevant → kept. Cap at a sane size (~2–5k docs max; if the
   filter yields more, tighten and say so).
3. **Chunk:** reuse `parse_and_chunk.py` logic (wrap/parameterize, never fork)
   → `rag/corpus/guidance/chunks.jsonl`, same chunk schema PLUS
   `tier: "guidance"` and NO era_code (never fake Tier-1 linkage; the field
   may be null). Chunk ids prefixed `G_` to keep id spaces disjoint.
4. **Index:** parameterize `build_index.py` (`--collection`, `--chunks`) and
   build Chroma collection `guidance_corpus` in the same store dir.
   `era_corpus` untouched — verify its count is still 1,191 after the build.
5. **Retrieve + explain (two-tier, never mixed):** extend `rag/retrieve.py`
   with a guidance-collection retriever (separate BM25 over guidance chunks;
   same hybrid+RRF machinery, parameterized — wrap, never fork).
   `explain_service.explain()`: evidence retrieval unchanged (k=8 from
   `era_corpus`); add guidance retrieval (k≈4 from `guidance_corpus`,
   graceful no-op if the collection is absent). Prompt: a separate
   "GUIDANCE PASSAGES (cite as [G1], [G2]…)" block with instructions that
   guidance may inform HOW-to advice only; numbers quoted from guidance must
   be cited like everything else. Guardrail: extend `allowed_numbers` to
   include guidance chunk text/metadata and extend the cite-marker strip
   regex to `[Gn]` — the numeric rule applies IDENTICALLY (extend, never
   bypass). Citations: add `tier` ("evidence"/"guidance") to
   `ExplainCitation` (additive, default "evidence"); dedupe guidance
   citations per document like evidence ones.
6. **UI:** guidance chips visually distinct from evidence chips (label
   "Guidance", different accent), linking to the source URL when present.
   Types updated; `npm run test` + `npm run build` green.
7. **WUE query-expansion fix (measured, not silent):** add an explicit
   indicator-synonym map to `build_query_text` (at minimum
   "water use efficiency" → append "water productivity"; check the dataset's
   other indicator names for obvious synonyms and document any you add).
   Then re-run `eval_retrieval.py` and report before/after (the P3 numbers
   above stay in the paper as the baseline; this becomes the query-expansion
   ablation row). Do NOT change anything else about Tier-1 retrieval.
8. **Tests:** pure-function tests for the GARDIAN filter rules and tier
   tagging; guardrail tests for `[Gn]` markers + guidance-sourced numbers;
   existing suites stay green (backend 46/46, eval 9/9 + new, frontend 16/16
   + new). `py_compile` everything touched.
9. **Scope guard:** no changes to Tier-1 corpus files, `era_corpus`, or the
   frozen data schema names. CGSpace is P5b — NOT this phase.
10. Append the phase report per CLAUDE.md and stop. Owner runs the fetch
    (network + HF token), index build, eval re-runs, pytest/npm, and commits.

**Owner sequencing note (per the 19 Aug decision):** the full faithfulness run
(`eval_faithfulness.py --n 30`) and `make_packets.py` deliberately WAIT until
after P5a/P5b, so the experts rate the enriched system. Neither has been run
yet (results/ holds only retrieval artifacts) — that is correct, not a gap.

## Phase P3.1 + P5a — Success@k in eval outputs + GARDIAN guidance corpus (20 Aug 2026)

**Built**

*P3.1 — Success@k (primary metric) in the eval outputs.*
- `success_at_k()` pure function in `rag/eval/eval_retrieval.py` (1.0 iff ≥1
  relevant study in the top-k chunks; 0 for empty label sets, mirroring
  `recall_at_k`). Wired into `score_scenario` (strict + family), the summary
  JSON, and `to_markdown` — Success columns come FIRST in every table, before
  Recall (primary metric per research_project_plan.md §2.4), with the header
  note updated to say so.
- `results/retrieval_metrics.{json,md}` regenerated **offline** from the
  stored per-scenario `retrieved_era_codes` (metrics are pure functions of
  those ranked lists, so this is exact — no re-retrieval). Verified first
  that the new `score_scenario` reproduces every one of the 50 stored metric
  rows bit-for-bit (0 mismatches), then confirmed the reviewer's numbers
  with **zero drift**: strict Success@4/8/16 = **0.400 / 0.560 / 0.640**,
  family-level = **0.480 / 0.600 / 0.700**; Recall/MRR unchanged
  (0.1106/0.2346/0.3327, MRR 0.3206).

*P5a — Tier-2 GARDIAN guidance corpus (two-tier rule; Tier-1 frozen).*
- **Fetch** — new `rag/ingest/fetch_gardian.py`: streams the gated HF dataset
  `CGIAR/gardian-cigi-ai-documents` (never loads 85k docs in memory);
  `HF_TOKEN` from env or `app/backend/.env` (find_api_key-style fallback,
  never printed). `--inspect` mode prints the first records' real field
  names/values first; extraction then probes candidate-key lists per logical
  field (id/title/text/country/year/url/doi), so schema variants work and
  the tuples are trivially extendable after inspection. Writes
  `rag/corpus/guidance/manifest.jsonl` (dataset id, doc id, title, year,
  url/doi, country meta, matched families, `tier:"guidance"`) +
  `texts/<doc_id>.txt`; resumable; reports scanned → Ethiopia →
  agroecology-relevant → kept; `--max-docs 3000` cap with a loud WARNING
  when hit (meaning: tighten the filter).
  **Filter rules (exact):** (1) *Ethiopia* — country-like metadata mentions
  "ethiopia" (metadata is authoritative when present: a non-Ethiopia country
  field rejects even if the text mentions Ethiopia); with no country
  metadata, fall back to "ethiopia" in the title, else ≥3 occurrences in the
  body text. (2) *Agroecology relevance* — keyword map over the 5 frozen
  practice families (built from `practice_family` + `CSA_practices`
  vocabulary in the model-ready CSV; ~15 terms/family, e.g. soil bund,
  terrac-, water harvesting, agroforestry, intercrop-, biochar, grazing
  management…): ≥1 keyword in the title OR ≥2 distinct keywords in the body.
  (3) *Usable text* — ≥100 words of body text (chunk input).
- **Chunk** — new `rag/ingest/chunk_guidance.py`: imports `chunk_text` from
  `parse_and_chunk.py` (wrap, never fork — same 380-word windows/overlap) →
  `rag/corpus/guidance/chunks.jsonl`; same chunk schema PLUS
  `tier:"guidance"`, `url`, chunk ids `G_<doc_id>_<nnn>` (disjoint id
  space), and `era_code: null` ALWAYS — Tier-1 linkage is never faked.
- **Index** — `build_index.py` parameterized with `--chunks` and
  `--collection` (defaults unchanged: era path + `era_corpus`); metadata now
  carries `tier` (default "evidence") and `url`; `era_code` tolerates null
  (→ "" in Chroma metadata). Building `guidance_corpus` never touches
  `era_corpus`.
- **Retrieve** — `RagRetriever` gains a `collection=` parameter (default
  `era_corpus`, unchanged); new `GUIDANCE_COLLECTION` constant and
  `default_guidance_retriever()`. Each instance builds BM25 over its own
  chunks file — same hybrid+RRF machinery, strictly separate corpora.
- **Explain (two-tier, never mixed)** — evidence retrieval unchanged (k=8,
  `era_corpus`). New in `explain_service`: `get_guidance_retriever()` /
  `set_guidance_retriever()` (config: additive `RAG_GUIDANCE_CHUNKS_PATH`,
  default `rag/corpus/guidance/chunks.jsonl`); missing file/collection logs
  once and disables the tier — graceful no-op, never raises. Guidance
  (GUIDANCE_K=4, via the same `retrieve_for_recommendation`) is retrieved
  only on the LLM path and appended as a separate "GUIDANCE PASSAGES (cite
  as [G1], [G2], …)" prompt block; system prompt adds the HOW-to-only rule.
  **Guardrail extended, not bypassed:** `_CITE_MARKER_RE` → `\[G?\d+\]`;
  `allowed_numbers` now also harvests `url` and is fed evidence+guidance
  chunks together — every number in the output must still be grounded,
  identically for both tiers. `ExplainCitation` gains additive
  `tier` (default "evidence") and `url`; `shape_citations` tags tier and
  dedupes guidance citations per document (url in the dedup-key chain).
  Guidance citations are returned only on the LLM path — the deterministic
  fallback never cites [Gn], so it never lists guidance sources.
- **Faithfulness auditor made two-tier aware** (`eval_faithfulness.py`) —
  not explicitly on the list, but the owner's post-P5a audit run would
  otherwise mis-flag [Gn] sentences: [Gn] markers are stripped like [n]
  (else "[G12]" leaves an "invented" 12), guidance chunks are recorded via a
  second RecordingRetriever (reset per scenario) and enter the allowed-
  numbers whitelist and the citation-support check; `cite_markers` column
  now shows `G1`-style entries. Evidence-only behaviour is bit-identical
  when no guidance corpus exists.
- **UI** — `ExplainCitation` TS type gains optional `tier`/`url`;
  `evidence-panel.tsx` splits citations into "Source studies (n)" and a new
  "Implementation guidance (n)" section; guidance chips carry an accent-
  colored ring + "GUIDANCE" badge (accent = teal/cyan var, distinct from the
  leaf/indigo evidence hover) and link to the source `url` when present
  (doi fallback).
- **WUE query expansion (measured, not silent)** — `INDICATOR_SYNONYMS` map
  in `build_query_text`: "water use efficiency" → +"water productivity"
  (mandated); plus two documented additions justified the same way
  (corpus vocabulary vs dataset name): "SOM content" → +"soil organic
  matter", "soil loss" → +"soil erosion". Purely additive (original
  indicator always kept); unmapped indicators produce byte-identical
  queries to before. Nothing else about Tier-1 retrieval changed.

**Files** — modified: `rag/eval/eval_retrieval.py`,
`rag/eval/eval_faithfulness.py`, `rag/eval/test_build_queries.py`,
`rag/eval/README.md`, `rag/eval/results/retrieval_metrics.{json,md}`,
`rag/ingest/build_index.py`, `rag/ingest/parse_and_chunk.py` (pypdf import
deferred into `extract_pdf_text` so `chunk_guidance`/tests import without the
PDF stack — no behaviour change), `rag/retrieve.py`,
`app/backend/app/config.py`, `app/backend/app/schemas.py`,
`app/backend/app/services/explain_service.py`,
`app/backend/tests/test_explain.py`, `app/frontend/src/lib/types.ts`,
`app/frontend/src/lib/api.test.ts`,
`app/frontend/src/components/evidence-panel.tsx`. New:
`rag/ingest/fetch_gardian.py`, `rag/ingest/chunk_guidance.py`,
`rag/ingest/test_gardian.py`.

**Decisions**
- P3.1 artifacts regenerated offline from the stored ranked lists instead of
  a live re-run: this sandbox has no chromadb, and the metrics are pure
  functions of `retrieved_era_codes` — verified exact against all 50 stored
  rows before regenerating. Retrieval-drift checking folds into the owner's
  WUE-ablation re-run, which re-retrieves everything anyway.
- Ethiopia metadata is authoritative when present (a doc tagged Kenya that
  mentions Ethiopia is rejected) — favors precision; the fallback text rule
  (title, or ≥3 body mentions) is for records with no country field at all.
- Guidance citations only on the LLM path: the deterministic fallback is
  built from evidence citations alone, so returning guidance sources with it
  would list documents the text never cites (violates cite-or-silent).
- Guidance retrieval reuses `retrieve_for_recommendation` (same per-practice
  query builder, wrap-never-fork), so the indicator-synonym expansion applies
  to both tiers consistently.
- `test_explain.py` gained an autouse fixture stubbing
  `get_guidance_retriever` to None — unit tests stay hermetic even after the
  owner builds the real guidance corpus locally (tests inject fakes via the
  new `guidance_retriever=` argument).

**Verified** (in this sandbox: Python 3.12 venv with fastapi/pytest/rank-bm25,
Linux node v22.14 fetched to scratchpad since only Windows node was on PATH)
- `python -m py_compile` clean on all 13 touched/new Python files.
- Eval suite `rag/eval/test_build_queries.py`: **13 passed** (9 old + success@k
  unit tests + 3 two-tier faithfulness tests, incl. guidance-quoted numbers
  pass / same sentence without guidance fails).
- New `rag/ingest/test_gardian.py`: **11 passed** (field extraction, Ethiopia
  rule incl. metadata-authoritative + threshold cases, family keyword rules,
  tier tagging: `G_` prefix, `tier:"guidance"`, `era_code is None`).
- Backend `tests/test_explain.py`: **32 passed** (21 old — all untouched
  assertions still green — + 11 new: [Gn] marker strip, guidance-sourced
  numbers allowed/invented rejected, tier tagging + per-document dedup,
  prompt block ordering, LLM path appends guidance citations, fallback
  excludes them, broken guidance retriever degrades to evidence-only,
  real availability check returns None when chunks missing).
- Frontend: `vitest run` **16 passed** (fixture now carries a guidance
  citation with tier+url), `next build` **green** (compile + types + lint +
  static generation). Required a Linux-native node + `--no-save` install of
  `@rollup/rollup-linux-x64-gnu` into node_modules (package.json untouched)
  because node_modules was installed from Windows.
- Sanity: WUE/SOM/soil-loss queries gain their synonyms; "yield" query is
  byte-identical to pre-change output. Tier-1 `rag/corpus/chunks.jsonl`
  untouched (still 1,191 lines); no Tier-1 corpus file, schema name, or
  `era_corpus` reference modified.

**Needs local verification** (owner — network, HF token, full stack)
- `fetch_gardian.py --inspect` first (confirm real field names; extend
  `*_KEYS` tuples if the schema differs), then the full fetch; report the
  scanned → Ethiopia → relevant → kept counts and whether the 3,000 cap hit.
- `chunk_guidance.py`, then `build_index.py --chunks ../corpus/guidance/chunks.jsonl
  --collection guidance_corpus --rebuild`; verify `era_corpus` still holds
  exactly **1,191** chunks afterwards.
- Re-run `eval_retrieval.py` for the WUE-ablation before/after row (P3
  numbers stay in the paper as baseline; watch WUE recall@k and the overall
  Success@8 vs 0.56).
- Backend full suite (46+11 expected with rasters), `test_api.py` /
  `test_slot_extraction.py` (need joblib/rasterio — not importable here),
  live /explain smoke with the built guidance collection, then the
  post-P5a/P5b faithfulness run per the sequencing note.

### Review (Senior Engineer) — P3.1 + P5a APPROVED with hardening applied ✅ (20 Aug 2026)
Read the full diff (18 modified + 3 new files) and re-verified the claims in
an independent sandbox rather than trusting the report.

**Verified independently:**
- All three suites re-run here: eval **13/13**, ingest **11/11**, backend
  explain **32/32** (33/33 after the hardening test below); `py_compile`
  clean.
- Regenerated `retrieval_metrics.{json,md}`: Success@4/8/16 strict =
  0.400/0.560/0.640, family 0.480/0.600/0.700, Recall/MRR unchanged —
  matches my own recomputation exactly; Success columns lead every table.
- Synonym expansion: WUE/SOM/soil-loss queries gain exactly their mapped
  terms; a "yield" query is byte-identical to the pre-change composer.
- Two-tier separation: Tier-1 chunks.jsonl untouched (1,191 lines);
  `era_corpus` default paths/collection unchanged; guidance chunks carry
  `era_code: null` always; `G_` id space disjoint; guidance citations only
  on the LLM path (fallback stays evidence-only — correct cite-or-silent
  reading); graceful no-op verified down to the sticky-flag reset.
- The unrequested `eval_faithfulness.py` two-tier fix was the RIGHT call —
  without it the post-P5a audit would flag every `[G12]`-style marker as an
  invented number. Marker-regex order and index mapping are correct
  (`\[(\d+)\]` cannot match inside `[G12]`).
- Ethiopia metadata-authoritative rule, keyword thresholds, cap warning,
  resumability: all as documented, all unit-tested.

**Hardening applied in review (backend re-tested, 33/33):**
1. `allowed_numbers` no longer harvests `url` — URLs never appear in the
   prompt, so their digits (handle ids like 10568/54321, dates) would have
   whitelisted numbers the LLM cannot legitimately quote. Zero false-trip
   cost (docstring updated; regression test added:
   `test_guardrail_does_not_whitelist_numbers_from_urls`).
2. **Ablation procedure corrected** — the phase report's "re-run
   eval_retrieval.py" alone would measure NOTHING: `queries.jsonl` stores
   `query_text` composed at build time with the PRE-synonym composer, and
   `eval_retrieval.py` replays those frozen strings. The owner must
   regenerate the queries first. Verified safe: re-running
   `build_queries.py` (same seed 42) reproduces all 50 scenarios and both
   label sets byte-identically — only `query_text` changes, in exactly the
   20 scenarios of the three mapped indicators (8 WUE + 8 SOM content +
   4 soil loss). The ablation is therefore a clean same-labels comparison,
   and it is a **query-expansion ablation** (3 indicators), not WUE-only —
   frame it that way in the paper.

Minor notes (accepted, no rework): resumed fetch runs can exceed
`--max-docs` in total (the cap counts new docs only); `build_queries.py`
writes its report to the fixed results path regardless of `--out`; the
sticky guidance-unavailable flag holds until process restart (documented).

**Owner actions to close P5a** (PowerShell, venv active, repo root; commit
BEFORE the ablation so the baseline artifacts stay in git history):
```
git add -A ; git commit -m "P3.1+P5a: Success@k primary metric + Tier-2 GARDIAN guidance corpus (reviewed)"
cd rag\ingest
python fetch_gardian.py --inspect          # confirm real schema; extend *_KEYS if needed
python fetch_gardian.py                    # full fetch — report the funnel counts + cap status
python chunk_guidance.py
python build_index.py --chunks ../corpus/guidance/chunks.jsonl --collection guidance_corpus --index ../index/store --rebuild
cd ..\..
python rag/eval/build_queries.py           # regenerate queries WITH synonyms (scenarios/labels identical)
python rag/eval/eval_retrieval.py          # query-expansion ablation run
pytest -q                                  # backend full suite (test_api needs rasters)
cd app\frontend ; npm run test ; npm run build ; cd ..\..
```
Then: verify `era_corpus` still holds exactly 1,191 chunks, `/explain` smoke
with guidance chips visible (and absent when the guidance index is renamed
away), report the ablation table (watch WUE recall/success and overall
Success@8 vs 0.56), and commit again. The faithfulness run + expert packets
still wait for P5b per the sequencing note.

**Then queued:** P5b (CGSpace REST → guidance_corpus additions), then the
faithfulness run + blinded expert study on the enriched system, then P4
(manuscript).

### Review addendum — GARDIAN schema adaptation after --inspect (Senior Engineer, 21 Aug 2026)
Owner ran `fetch_gardian.py --inspect`: the real schema is `metadata /
keywords / sieverID / pagecount / content / tokenCount / images / tables` —
no title, country, year, or url fields at all; the source URL (when present)
is embedded in the "; "-joined `metadata` blob. Adaptations applied by the
reviewer (this was exactly the planned post-inspect step; ingest tests now
**14/14**):
1. `ID_KEYS` gains `sieverid` — document ids now carry GARDIAN provenance
   instead of falling back to positional `docNNNNNN` ids.
2. `url_from_metadata()` — extracts the embedded source URL from the
   metadata blob (`URL_KEYS` probe kept as first choice); feeds the UI chips.
3. `display_title()` — records have no title, so the manifest title falls
   back to the first 12 words of the body (marked
   `title_source: "content_head"`). Display-only: the FILTER rules still see
   the raw empty title, so their documented semantics are unchanged — with
   no country metadata and no titles, Ethiopia = ≥3 body-text mentions and
   relevance = ≥2 distinct family keywords in the body, for every record.
Consequences to watch in the funnel counts: sampled records are SHORT
(tokenCount ~44–146), so the ≥100-word floor and the 3-mention Ethiopia rule
may bite hard. If the kept count comes back very low, the tuning knobs are
`--min-words 60` and `ETHIOPIA_TEXT_MIN = 2` — measure first, tune second.
Year stays None for all GARDIAN records (no date field) — the paper's corpus
table should say so rather than invent one.

### Review addendum 2 — chunk-level filter for the guidance corpus (Senior Engineer, 21 Aug 2026)
Owner's full fetch: **scanned 68,745 → Ethiopia 3,147 → agroecology-relevant
1,459 → kept 1,459** (0 thin, cap not hit). Manifest spot-checked from the
bridge: ids all carry GARDIAN sieverIDs, 1,453/1,459 have source URLs, all
five families covered (825/708/717/594/340), Ethiopia rule matched via body
text for every record as expected.

BUT the size assumption behind P5a was wrong in a good direction: these are
WHOLE documents (median 13,879 words, mean 28,375, max 376,239 — 41.4M words
total), not short guidance notes. Chunking wholesale ⇒ ~130k chunks, which
would swamp the Chroma store (~2.5 GB) and the retriever's in-memory BM25.
Measured on real samples: a keyword-only filter still leaves ~80k chunks
(one 376k-word crop-genepool book alone keeps 1,485 of its 1,592 chunks).

**Fix applied by the reviewer in `chunk_guidance.py` (ingest tests 17/17):**
1. Chunk-level relevance filter — a chunk is kept only if it mentions ≥1
   practice keyword (same FAMILY_KEYWORDS that admitted the document).
2. `--max-chunks-per-doc` cap (default 25) — the chunks with the most
   DISTINCT keywords win (ties: total hits, then earlier position); output
   stays in document order and chunk ids keep their original document
   position (gaps = filtered chunks, provenance preserved).
Sampled outcome: 87 chunks from the 6 probe docs; corpus-wide expect roughly
12–18k chunks (upper bound 1,459 × 25 = 36,475) — embeddings well under $1,
index in the low hundreds of MB. Tier-1 chunking untouched. The chunk
report now prints kept / keyword-empty docs / capped docs — those numbers go
in the phase log when the owner runs it.

### Review addendum 3 — index store relocated off the WSL bridge (Senior Engineer, 21 Aug 2026)
Incident: after the repo moved into WSL (fresh-bridge handoff), every Chroma
open over `\\wsl.localhost` from Windows Python failed with `database is
locked` — WRITES first (guidance index build), then READS too (retrieve.py
smoke) — surviving process cleanup and `wsl --shutdown`. Root cause:
Chroma's SQLite locking does not work across the Windows↔WSL 9P bridge at
all; every earlier successful index operation predates the repo's move to
WSL. Two fixes:
1. **Store relocated to native Windows disk** (built at `C:\temp\chroma_store`
   via local build; permanent home `C:\agroadvisor_data\chroma_store`), with
   `RAG_INDEX_DIR` set in `app/backend/.env`. Verified after build:
   era_corpus **1,191** + guidance_corpus **19,997**.
2. **`retrieve.py`: `_find_index_dir()`** — `default_retriever()` /
   `default_guidance_retriever()` now honor `RAG_INDEX_DIR` (env var, else
   backend/.env, else the repo-relative default), matching the backend's
   existing config path. Eval scripts and the CLI therefore follow the same
   single setting. Tests re-run: eval 13/13, ingest 17/17.
Also this incident's earlier fix, recorded for completeness: `build_index.py`
clips each EMBEDDING input to 7,000 chars (API limit 8,192 tokens; one
GARDIAN chunk exceeded it — pathological unbroken text), stored text
complete. The in-repo `rag/index/store` copy + `store_pre_p5a_backup` remain
as artifacts; runtime uses `RAG_INDEX_DIR`.

### Query-expansion ablation results (Senior Engineer, 21 Aug 2026)
Owner re-ran build_queries (identical 50 scenarios/labels confirmed by the
build report) + eval_retrieval against the relocated store. Baseline (P3,
frozen) vs expansion (WUE/SOM/soil-loss synonyms; 20/50 queries changed):

| metric | baseline | expansion |
|---|---|---|
| Success@8 (primary) | 0.560 | **0.560** |
| Success@16 | 0.640 | **0.660** |
| Recall@8 | 0.235 | **0.245** |
| Recall@16 | 0.333 | **0.357** |
| MRR | 0.321 | 0.300 |

Per changed indicator: **WUE** Success@16 0.12→0.25, Recall@16 0.025→0.175
(7×; Recall@8 unchanged — the gains enter between k=8 and 16); **soil loss**
Recall@8 0.125→0.250 (MRR 0.375→0.208); **SOM** unchanged except MRR
0.257→0.203. Scenario level: 2 improved, 0 worsened (recall@16); Success@k
never decreased anywhere. Untouched indicators byte-identical, as designed.

**Verdict: KEEP the expansion.** The primary metric is non-decreasing with
coverage gains exactly where the terminology gap was diagnosed; the small
MRR dip is rank shuffling among already-found studies, not lost groundings.
Honest framing for the paper: query expansion recovers *rankable* WUE
evidence (visible at k=16) but cannot fix the underlying evidence-density
problem — the WUE-relevant studies are mostly abstract-only in Tier 1, which
is the corpus limitation the paper already reports. Both result sets go in
Section 8 as the ablation row; the paper's headline retrieval numbers remain
the frozen P3 baseline.

## Maintenance — frontend toolchain (15 Oct 2026) + repo repair & sync (23 Oct 2026)
- **15 Oct (reviewer, via bridge):** frontend toolchain aligned to Next 16 — details
  in the SESSION_HANDOFF.md addendum: `package.json` (`@types/node ^22`,
  `tailwindcss ^3.4.17` + `autoprefixer`, `eslint-config-next ^16.4.1`,
  `vitest ^5`, `lint` → `eslint .`), lockfile regenerated, `eslint.config.mjs`
  rewritten as native flat config (two React-Compiler rules at *warn* → follow-up
  F-1), `postcss.config.mjs`, `tsconfig.json`. Verified in a clean clone of
  fa1d412 + these files (Node 22): `npm install` clean, `tsc --noEmit` clean,
  `eslint .` 0 errors / 10 warnings, `vitest run` 16/16, `next build` OK.
  **Not yet committed** (owner commits from Windows).
- **23 Oct (reviewer, via bridge):** the OneDrive checkout's `.git` was found
  damaged — OneDrive had dehydrated most loose objects (`git fsck`: objects
  missing), so `git stash`/`git pull` failed. Repair: `.git` replaced by a fresh
  clone's `.git` (single packfile, `fsck` clean, HEAD = origin/main fa1d412);
  working tree brought to fa1d412 content file-by-file; the six uncommitted
  15-Oct files preserved and verified byte-identical to pre-sync backups;
  `git status` now shows exactly those six files. Nothing committed.
- **Bridge constraints discovered (binding for every bridge session from now
  on):** the Cowork mount of this folder CANNOT rename files — a rename leaves a
  phantom directory entry and the data is lost (`git config`, `git reset`,
  `mv`, `sed -i`, `os.replace` all break this way; this is also the mechanism
  behind the 15-Oct `index.lock` incident). Therefore via the bridge: git is
  READ-ONLY (`GIT_OPTIONAL_LOCKS=0 git status/diff/log` only); writes are
  direct only (`cat >`, `cat >>`, python `open(..., 'w')`, `cp`); `rm` works
  once delete permission is granted. Recommendation to the owner: move the
  canonical clone OUT of OneDrive (e.g. `C:\dev\agroadvisor-et`) or mark the
  folder "Always keep on this device"; OneDrive + git is not reliable.
- **Owner M0 checklist (Windows, repo root):** `git status` (expect the six
  files) → `cd app\frontend && npm ci && npm test && npm run lint && npm run build`
  → `git commit -m "Frontend: align toolchain to Next 16 (Tailwind 3.4, ESLint flat config, vitest 5, @types/node 22)"`
  → `git push` → add `RAG_INDEX_DIR=<path of the Chroma store holding era_corpus
  1,191 + guidance_corpus 19,997>` to `app/backend/.env` (this checkout has no
  such line, so it would run on the in-repo, evidence-only store) → decide the
  repo location.

### DECISION RECORD — WOCAT practice records + knowledge graph; P5b dropped (23 Oct 2026, owner + reviewer)
Supervisor's direction: use **WOCAT** (Global SLM Database, https://wocat.net)
to go beyond Ethiopia. Facts verified by the reviewer in the browser on 23 Oct:
2,124 SLM practices in 110 countries (1,541 Technologies + 583 Approaches);
**Ethiopia: 102**, several documented by the Alliance Bioversity–CIAT (ProSoil /
ISFM+, e.g. Technology #6644 "Crop Residue Management", compiler Gerba Leta).
Every Technology follows the standardized 2019 questionnaire (QT): SLM groups,
SLM measures (A/V/S/M codes), degradation types; context classes (rainfall band
+ mm, agro-climatic zone, slope, altitude, soil depth/texture/OM); establishment
and maintenance activities with timing, inputs and costs per ha; ~40 on-site
impact ratings (crop production, fodder production, farm income, soil moisture,
soil loss, surface runoff, soil organic matter …) that map almost 1:1 onto our
7 indicators; cost–benefit; adoption; strengths/weaknesses and how to overcome
them; references; linked Approaches. Licence **CC BY-NC-SA 4.0** (attribution to
WOCAT + compilers, link to the original, share-alike for derived data, notify
wocat.cde@unibe.ch on reuse). The JSON API (`wocat.net/api/database/...`)
requires credentials and will soon need an API Access Agreement; the site asks
researchers to contact the Secretariat before analysis. The **Alliance
Bioversity–CIAT is a WOCAT Consortium Partner** (listed contact: Job Kihara,
Alliance, Nairobi).

Decisions:
1. **Tier 3 "practice records" (WOCAT) + a knowledge graph** are the next
   engineering phases (P6a–P6c). Tier 1 stays FROZEN; Tier 2 unchanged; tiers
   never mixed; numeric guardrail EXTENDED (citations `[Wn]`), never bypassed.
2. **P5b (CGSpace REST) is DROPPED:** 1,247 of the 1,459 GARDIAN guidance
   documents are already CGSpace bitstreams (checked in the manifest).
3. **"Beyond Ethiopia" in this manuscript** = context-matched cross-country
   practice records in the advisory + a new, expert-free experiment: agreement
   between the ML model's predicted effect direction and WOCAT practitioner-
   reported impact direction per (practice, indicator), in-country vs
   out-of-country. Geographic expansion of the recommender itself (ERA is
   pan-African; WorldClim/SoilGrids/SRTM are global) = Discussion/roadmap and
   a follow-up paper.
4. **Graph store = NetworkX + serialized node-link JSON** (zero-ops, like
   Chroma). No new infrastructure. Neo4j only if a live graph UI is ever needed.
5. **Data access:** OWNER requests a research data export (Technologies +
   Approaches, EN, JSON/CSV, all countries) through the Alliance partnership
   (supervisor → Job Kihara / wocat.cde@unibe.ch; state research use, CC BY-NC-SA,
   attribution). **Bulk or automated fetching of wocat.net is forbidden.**
   Derived WOCAT data files released with the paper carry CC BY-NC-SA.
Sequence: **P6a** (graph foundation + WOCAT taxonomy & crosswalk scaffolding —
data-independent, starts now) → **P6b** (WOCAT ingestion from the export, graph
enrichment, Tier-3 retrieval + `/explain` + UI) → **P6c** (evaluation: direction
agreement; retrieval ablation hybrid vs hybrid+graph) → faithfulness run →
blinded expert study on the Tier 1+2+3 system → **P4** manuscript (+ a section
"Knowledge graph and cross-country practice transfer"). Methods sections 3–5 of
the manuscript are drafted by the reviewer in parallel.

### Next steps → Phase P6a — Knowledge-graph foundation + WOCAT taxonomy & crosswalk scaffolding (assigned to Claude Code)
Data-independent by design: everything below is built and tested WITHOUT the
WOCAT export (the owner is requesting it). Read CLAUDE.md first. Priority order
if budget runs short: items 0–4 complete and tested, then 5. The scope guard
(item 7) is binding.

0. **Measure before building** (numbers go in the phase report). From
   `data/processed/CSA_ERA_final_model_ready.csv`: distinct `CSA_practices`
   (expect 100). Decompose each into ATOMIC COMPONENTS by splitting on `-`
   (e.g. `Biochar-Inorganic Fertilizer-Organic Fertilizer` → 3 components;
   `Intercropping or Rotation` stays one component). Report the number of
   distinct components (expect ~30) and the alias/typo clusters you find
   (`Deficit Irrigation`/`Deficit irrigation`, `Drought tolerrant crops`,
   `organic amedements`, …). `CSA_practices` strings are FROZEN (data contract):
   components are a NEW derived layer with normalized labels + an alias map —
   never rewrite the dataset.
1. **Package `rag/graph/`** (new; pure Python on `networkx`; add
   `networkx>=3.2` to `rag/requirements.txt`; add `rag/graph/store/` to
   `.gitignore`).
   - `schema.py` — node types: `PracticeFamily` (5), `Practice` (100; label =
     frozen `CSA_practices` string), `PracticeComponent` (~30, normalized),
     `Indicator` (7), `Study` (`era_code`; attrs: source ERA/CSA, title/year/doi
     from `rag/corpus/manifest.jsonl` when present, `corpus_status` ∈
     {full_text, abstract, none}, `n_chunks` from `rag/corpus/chunks.jsonl`),
     `AEZBelt`, `CropGroup`, `Country`, `SLMGroup`, `SLMMeasure`,
     `DegradationType`, `ContextClass` (kinds: rainfall_band, agroclimatic_zone,
     slope_class, altitude_zone, soil_texture, soil_depth, topsoil_om),
     `ImpactVariable` (QT §6.1), `Technology` and `Approach` (WOCAT — EMPTY in
     P6a except fixtures), `GuidanceDoc` (Tier 2, optional). Edge types, each
     with `source` provenance ∈ {era_rows, csa_rows, manifest, wocat_taxonomy,
     crosswalk_auto, crosswalk_validated, wocat_fixture, wocat_export}:
     `IN_FAMILY`, `COMPOSED_OF`, `REPORTS_EFFECT` (Study→Practice; attrs:
     indicator, n_obs, mean_log_rr, median_log_rr, share_positive, aez_belts,
     crop_groups — aggregates of dataset rows, i.e. the data's numbers, never
     generated), `STUDIED_IN` (Study→AEZBelt), `MEASURES` (Indicator↔
     ImpactVariable; attrs: direction_good, proxy), `MAPS_TO`
     (PracticeComponent→SLMMeasure / SLMGroup; attrs: confidence, status ∈
     {proposed, validated, rejected}), and the WOCAT-record edges
     `USES_MEASURE`, `IN_GROUP`, `ADDRESSES`, `APPLIED_IN`, `HAS_CONTEXT`,
     `REPORTS_IMPACT`, `LINKED_APPROACH` (defined now, populated in P6b).
     Document everything in `rag/graph/README.md` with a table that can become
     the manuscript's graph-schema table.
   - `build_graph.py` — CLI; builds nodes/edges from the CSV + manifest +
     chunks + the taxonomy module + the crosswalk CSV (validated rows only
     unless `--include-proposed`); writes `rag/graph/store/graph.json`
     (node-link JSON) and `rag/graph/store/graph_report.json` (node/edge counts
     per type; coverage: practices with ≥1 study, studies with chunks,
     components mapped). Deterministic and idempotent.
   - `query.py` — the functions P6b's retriever will call:
     `evidence_summary(practice, indicator)` (studies with n_obs, mean effect,
     contexts, corpus_status), `components_of(practice)`,
     `slm_measures_for(practice)` (via validated crosswalk only),
     `related_practices(practice, k)` (shared components / shared studies),
     `similar_context_technologies(context, practice, k)` (Jaccard over
     ContextClass nodes + measure overlap; returns `[]` when no Technology
     nodes exist), `explain_paths(practice, indicator, max_paths)`.
   - `test_graph.py` — pytest on a synthetic CSV fixture (no network, no
     chromadb): decomposition + aliasing; node/edge counts; provenance present
     on every edge; a `REPORTS_EFFECT` aggregate equal to a hand-computed value;
     the validated-only gate; every query function; JSON round-trip.
2. **`rag/graph/wocat_taxonomy.py`** — controlled vocabularies transcribed from
   the public *Questionnaire on SLM Technologies (2019)* — download it yourself
   (DOCX https://wocat.net/documents/447/QT_English_2019_CClicence.docx, PDF
   https://wocat.net/documents/448/Questionnaire_on_SLM_Technologies_-_English_FINAL.pdf;
   cite it + its CC BY-NC-SA licence in the module docstring): §3.5 SLM groups,
   §3.6 SLM measures (A1–A7, V1–V5, S1–S11, M1–M7 + A3 tillage and A6 residue
   sub-options), §3.7 degradation types (W/E/C/P/B/H codes), §5.1–5.3 context
   classes, §6.1 on-site impact variables by category + the rating scale,
   §6.4 cost–benefit classes, §6.5 adoption classes. The reviewer's DRAFT from
   a partial read is in `docs/decisions/wocat_taxonomy_draft.md` — verify every
   label against the questionnaire; do not trust the draft. Tests: code
   uniqueness, expected counts, every impact variable has a `good_direction`.
3. **`rag/graph/indicator_map.py`** — the 7 indicators ↔ WOCAT impact
   variables: yield→crop production; biomass yield→fodder production (secondary
   biomass/above-ground C); income→farm income; SOM content→soil organic
   matter/below-ground C; soil loss→soil loss; runoff→surface runoff; water use
   efficiency→soil moisture (`proxy=True`; secondary evaporation). Direction
   semantics import `recommend.DIRECTION` (wrap, never fork). One documented
   rationale line per mapping.
4. **Crosswalk proposal** — `rag/graph/crosswalk/propose_crosswalk.py`: for
   every PracticeComponent (NOT the 100 combinations) propose SLM groups + SLM
   measure codes with (a) deterministic rules — family priors + a keyword table
   you write (e.g. Mulch→A1 + improved ground/vegetation cover; Physical SWC
   measures→S1/S2 + cross-slope measure; Water Harvesting→S4/S5/S7 + water
   harvesting; Biochar→A2 + ISFM; Exclosure→area closure + M1; Parklands→V1 +
   agroforestry; Reduced Tillage→A3 reduced tillage + minimal soil disturbance;
   Improved Varieties→A5 + improved plant varieties …) and (b) an OPTIONAL
   `--llm` pass (gpt-4o-mini, temperature 0, JSON output, taxonomy definitions
   in the prompt; key via the existing find-api-key fallback; never printed;
   the owner runs it). Output `docs/decisions/wocat_crosswalk_proposal.csv`
   with columns: component, aliases, families, n_rows, proposed_groups,
   proposed_measures, confidence, rationale, status=proposed, owner_decision
   (blank), owner_note. `build_graph.py` admits only `status=validated` rows
   into `MAPS_TO` (tested). The owner validates in Excel — same procedure as
   `docs/decisions/practice_family_mapping.md`.
5. **WOCAT record schema + normalizer (data-independent)** —
   `rag/ingest/wocat/schema.py` (pydantic v2 `WocatTechnology`,
   `WocatApproach`: id, title, country, region, slm_groups, measures,
   degradation, land_use, water_supply, context classes, rainfall_mm,
   activities[], costs (establishment/maintenance, currency, per-ha),
   impacts{variable: rating}, cost_benefit, adoption, strengths[],
   weaknesses[], references[], url, compiler, licence, linked_approaches[]) and
   `rag/ingest/wocat/normalize_wocat.py` with an adapter interface and
   `--inspect` (prints the real keys of whatever export format arrives —
   GARDIAN-style probing) → `rag/corpus/wocat/technologies.jsonl`. Fixtures:
   hand-build 2–3 records in `rag/ingest/wocat/fixtures/` from PUBLIC Ethiopian
   technology pages read individually (e.g. Technology #6644 "Crop Residue
   Management"; record URL, compiler, licence in each fixture). Reading two or
   three pages by hand is fine; **any bulk or automated fetching of wocat.net
   is FORBIDDEN.** Tests: fixtures normalize; `build_graph.py --wocat
   <fixtures>` ingests them (Technology nodes + `USES_MEASURE`/`HAS_CONTEXT`/
   `REPORTS_IMPACT` edges with `source=wocat_fixture`);
   `similar_context_technologies` returns them for a matching context.
6. **Verify:** `python -m py_compile` on everything touched; `pytest` for
   `rag/graph` and `rag/ingest/wocat`; run `build_graph.py` for real on the
   repo data and report node/edge counts, component count, coverage; existing
   suites untouched and green where runnable (eval 13, ingest 17, backend
   explain 33).
7. **Scope guard:** NO changes to `app/`, `rag/retrieve.py`,
   `explain_service.py`, Tier-1/Tier-2 corpus files, `era_corpus` /
   `guidance_corpus`, or frozen schema names. Retrieval/explain/UI integration
   is P6b. No network calls except downloading the questionnaire and reading
   ≤3 public pages for fixtures.
8. Append the phase report per CLAUDE.md and stop.

**Owner actions in parallel:** M0 checklist (Maintenance entry above); WOCAT
data-export request via the Alliance partnership; when
`docs/decisions/wocat_crosswalk_proposal.csv` lands, validate the ~30 rows.

**Launch (repo root):**
`claude "Read CLAUDE.md, then progress.md. The latest '### Next steps → Phase P6a' block is your task. Implement it exactly, verify as instructed, append your phase report to progress.md, and stop."`

## Phase P6a — Knowledge-graph foundation + WOCAT taxonomy & crosswalk scaffolding (23 Oct 2026)

**Built** A new, data-independent graph layer `rag/graph/` (pure Python on
`networkx`, node-link JSON store — zero new infrastructure) plus the WOCAT
record scaffolding `rag/ingest/wocat/`. Nine modules, two test suites, one
owner-facing crosswalk proposal. The graph joins the model's evidence base,
the Tier-1 corpus and the WOCAT QT vocabularies; it generates no number and
every edge carries a `source` provenance tag that `validate_graph()`
enforces.

**0 — Measurements (before building).** From
`data/processed/CSA_ERA_final_model_ready.csv` (8,664 rows, 337 studies —
204 ERA-only, 133 CSA-only; 5 families, 7 indicators, 12 AEZ belts, 14 crop
groups):

- **100 distinct `CSA_practices`** (as expected).
- Naive splitting on `-` gives **46** tokens but is **wrong**: it shatters
  `In-situ water harvesting` into `In` + `situ water harvesting`. With that
  literal protected: **45 raw tokens → 44 canonical components.**
- **This is 44, not the ~30 the brief expected.** The gap is a deliberate
  decision, not an omission: aliasing merges only case/spelling variants of
  the *same* label. The one real cross-source cluster is
  `Deficit Irrigation` (ERA, 216 rows) / `Deficit irrigation` (CSA, 74).
  Typos fixed by the alias map: `Drought tolerrant crops` →
  `Drought Tolerant Crops`, `organic amedements` → `Organic Amendments`,
  `agronomic/biological SWCP` → `Agronomic/Biological SWC Practices`,
  `furrow irrigation_alternate` → `Alternate Furrow Irrigation`.
  Reaching ~30 would require merging semantically adjacent but differently
  named practices across sources — `Organic Fertilizer` (ERA) vs
  `Organic Amendments` (CSA), `Reduced Tillage` (ERA) vs
  `Conservation Tillage` (CSA), and the four SWC labels. That is a research
  judgement for the owner, and the crosswalk already relates them downstream
  by mapping both onto the same SLM measures (e.g. both fertiliser labels →
  A2). **Flagged for your decision; say the word and the merge is a
  three-line change to `ALIASES`.**

**1–3 — Graph, taxonomy, indicator map.**
`schema.py` (16 node types, 13 edge types, allowed endpoints, required
attributes, 8 provenance values, `validate_graph()`, deterministic node-link
(de)serialization); `practice_components.py` (the derived component layer);
`build_graph.py`; `query.py` (all six functions the P6b retriever will call);
`wocat_taxonomy.py`; `indicator_map.py`; `rag/graph/README.md` with the
node/edge tables (written to drop straight into the manuscript).

`wocat_taxonomy.py` is transcribed from the questionnaire itself, downloaded
and read in full — **not** from the draft. Counts verified: **27 SLM groups,
30 SLM measures (A1–A7, V1–V5, S1–S11, M1–M7, with the A3 tillage and A6
residue sub-options), 32 degradation codes, 40 context-class values across
7 kinds, 69 on-site impact variables** (25 socio-economic, 10 socio-cultural,
34 ecological), the 7-point rating scale, §6.4 cost–benefit and §6.5
adoption classes. Four corrections to
`docs/decisions/wocat_taxonomy_draft.md`, all recorded in the module
docstring:
1. **QT §1.3 states CC BY-NC-SA 4.0 International**, not 3.0 Unported as the
   draft recorded — so the questionnaire and the database agree, and the
   data-availability text only needs one licence.
2. §6.1 has one more variable than the draft captured: **`micro-climate`**
   (worsened/improved) in the climate/DRR block.
3. §6.5 adoption bands in the questionnaire are `single cases/experimental`,
   `1-10%`, `10-50%`, `more than 50%`; the live database renders its own
   (`11 – 50 %`, `91 – 100 %`). `normalize_adoption_band()` maps both.
4. §6.1 **`pests/ diseases` has its poles printed inverted** relative to
   every other harmful-outcome row (`decreased` as the negative end, where
   `harmful species` uses `increased`). The poles are transcribed verbatim,
   `good_direction` follows the substantive meaning, and the discrepancy is
   recorded in the variable's `source_note` rather than silently "fixed".
   The live record #6644 shows the same inversion, so it is the source's.

The PDF URL in the brief (`.../448/Questionnaire_on_SLM_Technologies_-_English_FINAL.pdf`)
**returns HTTP 404**; the DOCX URL works and is what was used.

`indicator_map.py` maps the 7 indicators to QT §6.1 variables with one
rationale line each (yield→crop production; biomass yield→fodder production
+ biomass/above-ground C; income→farm income; SOM content→soil organic
matter/below-ground C; soil loss→soil loss; runoff→surface runoff; water use
efficiency→soil moisture, `proxy=True`, + evaporation). **Direction
semantics are never redefined here**: it imports `recommend.DIRECTION`, and
if the engine's heavy deps are absent it reads the same literal out of
`recommend.py` with `ast`. Both paths were exercised and agree;
`direction_source()` reports which ran, and the build report records it.

**4 — Crosswalk.** `crosswalk/propose_crosswalk.py` emits
`docs/decisions/wocat_crosswalk_proposal.csv` — **44 rows, one per
component** (not per combination), with the brief's exact columns. 26
keyword rules (each citing the QT clause that justifies it) plus family
priors as fallback; **every component got at least one measure**, mean
confidence 0.87, lowest `Weeding` at 0.45 (no dedicated QT code — A7). Rules
support negative keywords so the generic water-harvesting rule does not
offer S5 dams/ponds for *in-situ* harvesting. The optional `--llm` pass
(gpt-4o-mini, `temperature=0`, JSON output, QT definitions in the prompt,
key via `build_index.find_api_key`, never printed) is wired and **not run** —
that is yours. **The gate is tested**: `build_graph.py` admits a row only
when `owner_decision`/`status` reads `validated`; `--include-proposed` admits
proposed rows but tags them `crosswalk_auto`; `rejected` rows are admitted
under neither flag; and `query.slm_measures_for()`/`explain_paths()` filter
to `validated` regardless of how the graph was built.

**5 — WOCAT records.** `rag/ingest/wocat/schema.py` (pydantic v2
`WocatTechnology`/`WocatApproach` with every field the brief lists) and
`normalize_wocat.py` (adapter interface + `PassThroughAdapter` +
`KeyProbeAdapter`, and `--inspect` which prints the real key shape of
whatever export arrives — the GARDIAN-style probe). Controlled vocabularies
are normalized against the questionnaire and **anything outside them is
dropped with a warning, never invented**.

Fixtures — **please read this paragraph.** `technology_6644.json` ("Crop
Residue Management", Ethiopia/Oromia, compiler Gerba Leta, ISFM+/ProSo(i)l,
Alliance Bioversity-CIAT) and `approach_6732.json` (the ISFM Approach it
links to) are hand-transcribed from the two PUBLIC record pages, read once
each in a browser — 39 on-site impact ratings, 9 context classes, 5 measures,
9 degradation types, costs, activities, adoption, strengths/weaknesses,
references. **I could not obtain a second real Technology**: the site's
search returns 0 results anonymously because it is served by the same
credentialed `/api/database/` endpoint the decision record gates, and
guessing record ids would be exactly the automated probing that is
forbidden. Rather than fabricate a plausible-looking WOCAT record, the third
fixture is `technology_synthetic_0001.json`, **explicitly flagged
`synthetic: true`** with `licence: "not applicable (synthetic test
fixture)"`, carried through to a `synthetic` flag on the graph node and in
`similar_context_technologies()` output, and warned about by the normalizer
CLI. It exists only so the context-similarity ranking has a structurally
different second Technology to rank against. It must never be cited, and two
more real fixtures should replace it when the export lands.

**Files** New: `rag/graph/{__init__,schema,practice_components,wocat_taxonomy,indicator_map,build_graph,query,test_graph}.py`,
`rag/graph/README.md`, `rag/graph/crosswalk/{__init__,propose_crosswalk}.py`,
`rag/ingest/wocat/{__init__,schema,normalize_wocat,test_wocat}.py`,
`rag/ingest/wocat/fixtures/{technology_6644,approach_6732,technology_synthetic_0001}.json`,
`docs/decisions/wocat_crosswalk_proposal.csv`.
Modified (2 lines each): `rag/requirements.txt` (`networkx>=3.2`,
`pydantic>=2.7`), `.gitignore` (`rag/graph/store/`, `rag/corpus/wocat/`).
**Scope guard honoured — zero changes under `app/`, and none to
`rag/retrieve.py`, `explain_service.py`, the Tier-1/Tier-2 corpus files, or
any frozen schema name.** (The repo-wide `M` flags on other files are the
pre-existing CRLF churn from the 23 Oct repair: `git diff --ignore-all-space`
over all of them is empty.)

**Decisions**
- **Split rule**: `-` only, with a protected-literals list; aliasing limited
  to case/typo variants (rationale above).
- **`ContextClass` kinds**: the seven the brief names. QT §5.2 **landform**
  is transcribed in the taxonomy but kept as a Technology attribute, not a
  node — the recommender's raster stack cannot supply it, so it cannot
  participate in context matching.
- **`GuidanceDoc`** is defined in the schema but **not populated**: no edge
  type connects it yet, so the 1,459 Tier-2 docs would be isolated nodes.
  Reserved for P6b when a Tier-2 edge type exists.
- **Node-link endpoint keys are `from`/`to`, not `source`/`target`** —
  networkx's default endpoint key would silently overwrite the mandatory
  `source` provenance attribute on every edge. Round-trip is asserted.
- **`build_graph --wocat` validates through the pydantic model**, so raw
  fixtures and the normalized `.jsonl` behave identically.
- **`rag/corpus/wocat/` is git-ignored** (rebuildable from the in-git
  fixtures; the CC BY-NC-SA export is not redistributed through this repo).
- `strip_era_prefix` is imported from `rag/eval/build_queries.py` rather than
  re-implemented (wrap, never fork); it transitively needs `requests`, which
  is already a declared `rag` dependency. No chromadb, no network.

**Verified** (WSL, Python 3.12, clean venv from `rag/requirements.txt` +
`app/backend/requirements.txt`)
- `python -m py_compile` clean on all **14** touched Python files.
- **`rag/graph/test_graph.py` — 40 passed**; **`rag/ingest/wocat/test_wocat.py`
  — 20 passed** (synthetic CSV fixture; no network, no chromadb, no model).
  Covers: decomposition + protected literals + aliasing; node/edge counts;
  `source` present and valid on **every** edge; a `REPORTS_EFFECT` aggregate
  equal to a hand-computed value (n_obs 3, mean 0.066667, median 0.1,
  share_positive 0.666667, belts, crop groups); the validated-only gate in
  all three states; all six query functions incl. the empty-graph degrade;
  JSON round-trip; fixture ingestion and impact/context edges; schema
  rejection of bad provenance, endpoints and status.
- Existing suites green at the expected counts, **untouched**: eval **13**,
  ingest **17**, backend explain **33** — and the full backend suite
  (`app/backend/tests/`) **58 passed** once `rasterio` was installed, since
  `geodata/layers` is present in this checkout.
- **`build_graph.py` run for real on the repo data** (with fixtures):
  **722 nodes, 1,981 edges, `validation: []`**, `direction_source:
  "import recommend"`.
  Nodes — Study 337, Practice 100, ImpactVariable 69, PracticeComponent 44,
  ContextClass 40, DegradationType 32, SLMMeasure 30, SLMGroup 27, CropGroup
  14, AEZBelt 12, Indicator 7, PracticeFamily 5, Technology 2, Country 2,
  Approach 1.
  Edges — REPORTS_EFFECT 867, STUDIED_IN 401, APPLIED_IN 340, COMPOSED_OF
  179, IN_FAMILY 100, REPORTS_IMPACT 44, HAS_CONTEXT 16, ADDRESSES 11,
  MEASURES 9, USES_MEASURE 8, IN_GROUP 5, LINKED_APPROACH 1.
  Provenance — era_rows 1,262, csa_rows 622, wocat_fixture 88,
  wocat_taxonomy 9.
  Coverage — practices 100, **practices with ≥1 study 100 (100%)**,
  components 44, components mapped to WOCAT **0** (correct: no validated
  crosswalk yet), studies matched to manifest 204/204 ERA, **studies with
  chunks 147**, with full text 35.
- **Determinism/idempotence**: two consecutive builds produce byte-identical
  `graph.json` (asserted in the suite and re-checked by `cmp`).

**Needs local verification / your decisions**
1. **Validate `docs/decisions/wocat_crosswalk_proposal.csv`** (44 rows) in
   Excel — fill `owner_decision` with `validated`/`rejected`. Until then the
   graph has zero `MAPS_TO` edges by design, so `slm_measures_for()` and
   `measure_overlap` return empty. Optionally run `--llm` first.
2. **The 44-vs-~30 component question** above — your call whether to merge
   the cross-source near-duplicates.
3. **Data-quality finding, reported not fixed (frozen dataset):**
   `Supplemental Irrigation` and its two combinations (311 rows) are assigned
   `practice_family = "Livestock production and management"`, contradicting
   `docs/decisions/practice_family_mapping.md`, which puts all irrigation
   under ECWM and even uses `Improved Varieties-Supplemental Irrigation →
   ECWM` as a worked example. The crosswalk is keyword-driven so the
   proposal is unaffected, but **the recommender ranks this practice inside
   the wrong family**, which is a live `/recommend` issue beyond P6a's scope.
4. **Replace the synthetic fixture** with two more real Ethiopian
   Technologies once the WOCAT export arrives (see the §5 paragraph above
   for why only one real Technology could be obtained).
5. Not verifiable here: the `--llm` crosswalk pass (needs the key, owner
   runs it) and the real WOCAT export adapter (no export yet — `--inspect`
   is the tool for it).

### Review (Senior Engineer) — P6a APPROVED with hardening applied ✅ (23 Oct 2026)
Independent re-verification in a clean sandbox (upstream clone + the P6a files):
- **Every count reproduces from the raw data:** 100 practices → 46 naive `-`
  tokens → 45 with `In-situ water harvesting` protected → 44 canonical
  components; 337 studies (204 ERA + 133 CSA); REPORTS_EFFECT 867 = distinct
  (study, practice, indicator) triples; STUDIED_IN 401 = distinct (study,
  belt) pairs; 147 of the 204 dataset ERA studies have corpus chunks (the
  corpus's 208 contributing studies include studies dropped from the
  model-ready dataset); 35 with full text; 14 crop groups; 12 belts.
- **`build_graph.py` here produced a `graph.json` byte-identical to the one
  on the owner's machine** (722 nodes, 1,981 edges, `validation: []`) — the
  build is deterministic across machines and OSes.
- Suites re-run: graph **40/40**, wocat **20/20**, eval **13/13**, ingest
  **17/17**; `py_compile` clean.
- Taxonomy counts re-derived from the module match the questionnaire
  structure (27 / 30 / 32 / 40 context values in 7 kinds / 69 impact
  variables = 25 + 10 + 34). The `pests/ diseases` pole inversion is real —
  the live record #6644 renders it the same way (checked in the browser on
  23 Oct). Licence: the DOCX (CC-licence version) states 4.0; the older PDF
  this reviewer's partial read quoted (3.0 Unported) now 404s — cite the DOCX
  and 4.0, as the module does.
- Fixture #6644 cross-checked against the public page text captured on
  23 Oct (measures, degradation types, context classes, rainfall 1,947 mm,
  adoption bands, activities, costs): faithful.
- The crosswalk gate works in all three states; `query.py` filters to
  `validated` independently of how the graph was built — correct
  belt-and-braces.

**Hardening applied in review:** `rag/requirements.txt` floor raised to
`networkx>=3.4` — `schema.py` calls `node_link_data(..., edges="links")`,
and the `edges=` keyword only exists from 3.4 (verified against the 3.3
wheel: its signature is `link="links"`); on 3.2/3.3 the build would raise
`TypeError`. No code change needed.

**Decisions (owner + reviewer, 23 Oct):**
1. **Components stay at 44.** Cross-source near-duplicates (`Organic
   Fertilizer`/`Organic Amendments`, `Reduced Tillage`/`Conservation
   Tillage`) are NOT merged: the two sources define them differently and the
   model treats the frozen strings as distinct categories; the crosswalk
   relates them through shared SLM measures, which is the honest statement.
2. **The synthetic fixture is accepted for P6a only.** P6b must (a) refuse
   `synthetic: true` records in any build that feeds the app or an
   evaluation (`--allow-synthetic` for tests only) and (b) replace it with
   two real Ethiopian Technologies from the export.
3. **Data-quality finding #3 is confirmed and must be fixed before any
   evaluation run** — see P6a.1 below. Root cause: the LPM keyword
   `"supplement"` (meant for feed supplementation) matches `Supplemental
   Irrigation`, and LPM outranks ECWM in the priority rule. This reviewer's
   audit of all 49 multi-keyword ERA practice names found it to be the ONLY
   false keyword match; every other multi-hit resolves by the documented
   priority order.

**Tracked for P6b (not blockers):** (i) the graph modules import each other
by bare name after `sys.path.insert(0, rag/graph)` (`import schema`,
`from query import …`) — the backend must import only `rag.graph.query` /
`rag.graph.schema`, and P6b should convert the package to relative imports
(`from . import schema`) so no top-level `schema`/`query` module is ever
created inside the API process; (ii) a `context_to_classes()` mapper is
missing (engine context → QT classes: rainfall mm → band, slope % → class,
altitude → zone, soil_clay → texture, lgp_days → agro-climatic zone) —
`similar_context_technologies` cannot be called from `/explain` without it;
(iii) **doctrine for graph numbers in prompts:** `REPORTS_EFFECT`
aggregates (mean/median log RR) must NOT appear in generated text — they
are dataset aggregates that can contradict the model's prediction for the
user's context; only counts (n_studies, n_obs), directions
(share_positive) and provenance go to the LLM, effect magnitudes stay the
model's; (iv) Ethiopia-first ranking policy in `similar_context_technologies`.

**Crosswalk validation notes for the owner** (reviewer's reading of the 44
rows; decide in Excel, `owner_decision` = `validated` / `rejected`, edit
`proposed_measures`/`proposed_groups` freely): `Water Harvesting` → prefer
`S4; S2` (in-field micro-catchments and bunds; keep `S5` only if pond/dam
systems are meant); `Mulch` → `A1` is the core, `A2` optional; `Weeding`
(A7, 0.45) is fine; `IWM` (0.6) and `Crop Rotation` (A2; M2) deserve a
second look; everything else reads correctly to me. `Supplemental
Irrigation`'s `families` cell will change to ECWM after P6a.1 (the
proposal itself is unaffected).

### Maintenance — RAG artefact recovery, canonical store layout (23 Oct 2026)
- The Tier-2 artefacts were not on the OneDrive checkout or the new clone;
  the full 21-Aug store was found at `C:\Users\MTuse\OneDrive - CGIAR\
  Documents\C\agroadvisor_data\chroma_store` (395 MB). New utility
  `rag/ingest/index_tools.py` (`list` / `copy-collection` /
  `export-chunks` / `compare`; refuses to create empty stores — the mistake
  that created a stray store earlier that day) was tested in the sandbox
  (exact Tier-1 round-trip; identical rankings after transplant) and run by
  the owner: `guidance_corpus` (19,997) transplanted into the canonical
  in-repo store `rag/index/store` next to `era_corpus` (1,191);
  `rag/corpus/guidance/chunks.jsonl` regenerated from the collection
  (19,997 chunks; only the diagnostic `kw_distinct` is null — nothing
  downstream reads it). `compare` proved the August store's `era_corpus`
  is **bit-identical** to the P3-evaluated one (provenance note for the
  paper: the 21-Aug ablation ran on exactly the frozen evidence index).
  Smoke: Tier-1 query returns the EO0016 full-text soil-loss passages;
  guidance retriever returns hits.
- **Layout decision:** everything lives under `C:\dev\agroadvisor-et` at the
  repo's default paths; `RAG_INDEX_DIR` is no longer set. A local copy of
  the full store at `rag/index/store_full_2026-08-21/` (git-ignored via
  `rag/index/.gitignore`) can be deleted after P6b's smoke tests.
  `rag/corpus/guidance/texts/` remains absent (only needed to re-chunk).

### Next steps → Phase P6a.1 — practice_family data-quality fix + regenerated artefacts (assigned to Claude Code)
Scope: fix ONE keyword collision and regenerate everything downstream of it
through the existing pipeline — no hand edits to data files. Read CLAUDE.md
first. The dataset column NAMES stay frozen; this phase changes VALUES of
`practice_family` for exactly the 311 rows of `Supplemental Irrigation`,
`Improved Varieties-Supplemental Irrigation` and `Inorganic
Fertilizer-Supplemental Irrigation` (LPM → ECWM), as
`docs/decisions/practice_family_mapping.md` already prescribes.
1. **Fix + test.** `pipelines/dataset/build_practice_family.py`: in
   `KW["LPM"]` replace `"supplement"` by `"supplementation"` and
   `"feed supplement"`. Add `pipelines/dataset/test_practice_family.py`
   (pytest, pure function `classify_era`): the three irrigation labels →
   ECWM; the mapping doc's worked examples (`Improved
   Varieties-Supplemental Irrigation` → ECWM, `Mulch-Reduced Tillage` →
   ECWM, `Inorganic Fertilizer` → ISFM, `Improved Varieties` → CPM,
   `Water Harvesting` → ECWM, `Agroforestry Fallow` → FAF); a feed
   supplementation label → LPM. Update the keyword list and add an
   "Erratum (23 Oct 2026)" paragraph in `practice_family_mapping.md`.
2. **Paths.** The pipeline and training scripts still point at legacy
   `*/dataset/` locations (`build_practice_family.py` `F=…/dataset/
   CSA_ERA_merged_model_ready.csv`, `train_model.py`
   `F=…/dataset/CSA_ERA_final_model_ready.csv`). Parameterize both with
   `--dataset`/`--out` arguments defaulting to the repo layout
   (`data/processed/…`, `model/artifacts/…`), keeping the frozen file
   names. Document the chain in `docs/reports/merged_dataset_notes.md`:
   merged → (practice_family) → final; the three copies
   (`data/processed/*_merged_*`, `data/processed/*_final_*`,
   `app/backend/dataset/*_final_*`) must be byte-identical after the run.
3. **Regenerate the dataset** by running the script (owner may run it if
   pandas is unavailable to you): assert exactly 311 rows changed, only in
   `practice_family`, only LPM → ECWM; row order, all other columns and the
   row count (8,664) unchanged. Report the new family × source table.
4. **Retrain** (`model/train_model.py`; sklearn 1.7.2 pinned; seconds):
   new `csa_model.joblib` + `model_metrics.json` in `model/artifacts/`,
   copied to `app/backend/artifacts/`. Report before/after: CV R², RMSE,
   baseline R², per-indicator R², per-source, and the **confidence flags**
   (any flag that flips is a UI-visible change — list it). `practice_family`
   is a model feature, so small drift is expected; large drift is a bug.
5. **Evaluation re-run on the corrected dataset (owner runs; ≈100 embedding
   calls, well under $1).** Add `--no-query-expansion` to
   `rag/eval/build_queries.py`, implemented as an `expand: bool = True`
   parameter on `rag.retrieve.build_query_text` (additive; default
   behaviour byte-identical). Then: `build_queries.py --no-query-expansion
   --out rag/eval/queries_v2_baseline.jsonl`, `build_queries.py --out
   rag/eval/queries_v2.jsonl`, `eval_retrieval.py` on each (give
   `eval_retrieval.py` `--queries`/`--out` arguments if it lacks them),
   writing `results/retrieval_metrics_v2_baseline.{json,md}` and
   `results/retrieval_metrics_v2.{json,md}`. The P3/21-Aug numbers stay in
   this log as the history on dataset v1; the manuscript reports v2. Note
   that the stratified sample itself changes (families moved), so v1→v2 is
   not a paired comparison — say so in the report.
6. **Graph + crosswalk.** Make `propose_crosswalk.py` preserve existing
   `owner_decision`/`owner_note`/edited target cells when re-run over an
   existing CSV (merge by `component`; new rows appended; report what was
   preserved). Re-run it, then `build_graph.py --wocat
   rag/ingest/wocat/fixtures`; report the new counts (IN_FAMILY edges move;
   nodes unchanged). Tests for the merge behaviour.
7. **Backend.** Full `pytest -q` in `app/backend` (58 expected): adjust
   only assertions whose expected values legitimately changed with the
   family move, and list each one. `/recommend` smoke: `Erosion control and
   water management` × `yield` must now be able to return `Supplemental
   Irrigation`; `Livestock production and management` must not.
8. **Scope guard:** no changes to `rag/retrieve.py` beyond the additive
   `expand` parameter; none to `explain_service.py`, the Tier-1/Tier-2
   corpora, `era_corpus`/`guidance_corpus`, or any column/file name.
9. Append the phase report per CLAUDE.md (include the full before/after
   metrics tables) and stop.

**Launch (repo root):**
`claude "Read CLAUDE.md, then progress.md. The latest '### Next steps → Phase P6a.1' block is your task. Implement it exactly, verify as instructed, append your phase report to progress.md, and stop."`

## Phase P6a.1 — practice_family data-quality fix + regenerated artefacts (23 Oct 2026)

**Built** One keyword fix in `pipelines/dataset/build_practice_family.py`, a
new regression suite for the classifier, both pipeline scripts parameterised,
and every downstream artefact regenerated through the pipeline — no hand
edits to any data file. Plus the eval ablation switch, the crosswalk re-run
merge, and a rebuilt graph.

### 1. The fix, and one deviation from the brief you need to approve

`KW["LPM"]`: `"supplement"` -> `"supplementation"`, `"feed supplement"`.
Verified blast radius: the bare token matched only the three
`Supplemental Irrigation` labels (311 rows); the real feed practices
(`Feed Addition-Feed Processing`, `Feed Substitution`, `Animal feed
management`) match on `feed` and are untouched.

**Deviation — the 311 rows do NOT all go to ECWM.** The brief says
"LPM -> ECWM"; the unchanged PRIORITY rule actually splits them:

| `CSA_practices` | rows | before | after |
|---|---:|---|---|
| `Supplemental Irrigation` | 277 | LPM | **ECWM** |
| `Improved Varieties-Supplemental Irrigation` | 24 | LPM | **ECWM** |
| `Inorganic Fertilizer-Supplemental Irrigation` | 10 | LPM | **ISFM** |

The last row has the **identical keyword signature** to the mapping
document's own worked example `Inorganic Fertilizer-Water Harvesting -> ISFM
("fertilizer beats water")`: both hit {ISFM, ECWM}, and ISFM outranks ECWM.
Forcing it to ECWM would mean special-casing it against the documented rule
the brief cites as the authority for the fix. I left the rule alone and
report the split: **301 -> ECWM, 10 -> ISFM**. Say the word if you want the
10 rows forced to ECWM instead; that needs a rule change, not a keyword one.

`pipelines/dataset/test_practice_family.py` (new, **25 tests**) pins the three
labels, all the mapping document's worked examples, the priority rule, the
CSA explicit-lookup dispatch, and the keyword-table invariants — so the code
and the document cannot drift apart again. `practice_family_mapping.md` gets
the corrected LPM keyword line and a full **"Erratum (23 Oct 2026)"** section
with the table above.

### 2. Paths parameterised, chain documented
`build_practice_family.py`: `--dataset` / `--out` / `--sync-copies`, defaulting
to `data/processed/…`; it preserves the input file's **line terminator** (the
canonical CSVs are CRLF — writing LF would have rewritten all 8,665 lines and
buried the real diff) and prints the three copies' md5s.
`train_model.py`: `--dataset` / `--artifacts` / `--copy-to` / `--no-copy`,
defaulting to `data/processed/…` and `model/artifacts/` -> `app/backend/artifacts/`.
Both legacy `*/dataset/` paths are gone. The chain is drawn in
`docs/reports/merged_dataset_notes.md`.

### 3. Dataset regenerated — exactly as specified
`311 of 8664` rows changed. Verified mechanically: **`practice_family` is the
only column whose values differ**; row count 8,664 unchanged; **row order
preserved** (every non-family column compares equal row-wise); CRLF preserved
(8,665 CRLF, 0 bare LF); `git diff --numstat` = `311 311`. All three copies
byte-identical (`md5 1b621130c46a59e656d465b74fe39b1a`). Every changed row is
a `Supplemental Irrigation` label, every one came **from** LPM, and **no row
moved into** LPM.

`practice_family` x `source`:

| family | CSA before | ERA before | CSA after | ERA after | total after |
|---|---:|---:|---:|---:|---:|
| Agro-forestry and forest management | 74 | 319 | 74 | 319 | 393 |
| Crop production and management | 202 | 1536 | 202 | 1536 | 1738 |
| Erosion control and water management | 816 | 904 | 816 | **1205** | **2021** |
| Integrated soil fertility management | 240 | 4164 | 240 | **4174** | **4414** |
| Livestock production and management | 82 | 327 | 82 | **16** | **98** |

**Consequence worth your attention:** LPM is now a **thin family — 98 rows, 5
practices** (`Animal feed management`, `grazing management`,
`Pasture Management`, `Feed Addition-Feed Processing`, `Feed Substitution`),
and for `yield` only **2 grounded candidates**. That is the honest state of
the livestock evidence once irrigation is removed from it, but it makes LPM
advisories much thinner than before. Worth a line in the manuscript's
limitations.

### 4. Retrained — and the committed v1 metrics are not reproducible

Ran with the pinned **scikit-learn 1.7.2** (8 s). But the committed
`model_metrics.json` (RandomForest, cv_r2 0.1898, baseline 0.1884) **could not
be reproduced in any environment I could build**, so I retrained the *previous*
dataset in the same pinned environment as a control. That isolates the data
effect from the environment effect:

| metric | committed v1 (historic env) | v1 data, pinned env | **v2 data, pinned env** |
|---|---:|---:|---:|
| model chosen | RandomForest | HistGBM | **HistGBM** |
| cv_r2 | 0.1898 | 0.2333 | **0.2339** |
| cv_rmse | 0.5846 | 0.5687 | **0.5684** |
| baseline_r2 | 0.1884 | 0.1672 | **0.1672** |
| per_source CSA / ERA | 0.324 / 0.117 | 0.354 / 0.167 | **0.356 / 0.167** |

Per-indicator R2 (n unchanged), and the confidence flags:

| indicator | n | committed | v1 pinned | **v2** | flag committed -> v2 |
|---|---:|---:|---:|---:|---|
| SOM content | 111 | -0.646 | -0.372 | **-0.432** | low -> low |
| biomass yield | 1525 | 0.022 | 0.060 | **0.058** | medium -> medium |
| income | 208 | 0.002 | -0.129 | **-0.065** | **medium -> low (FLIP)** |
| runoff | 359 | -0.164 | -0.179 | **-0.182** | low -> low |
| soil loss | 296 | -0.230 | -0.108 | **-0.144** | low -> low |
| water use efficiency | 255 | -0.194 | -0.031 | **-0.007** | low -> low |
| yield | 5910 | 0.025 | 0.088 | **0.092** | medium -> medium |

**Read the middle column, not the first.** Comparing like with like (v1 pinned
-> v2) the P6a.1 data fix moves the model by **cv_r2 0.2333 -> 0.2339**, the
baseline is **identical to 4 dp** (as it must be — the baseline is a
practice x indicator mean and never sees `practice_family`, which is a good
sanity check on the whole chain), and **no confidence flag changes**. That is
the "small drift expected" the brief predicted.

**Two changes are environment, NOT data, and both already appear on the v1
data in the pinned env:** (a) the best model switches **RandomForest ->
HistGBM**, and (b) the `income` flag flips **medium -> low** (the one
UI-visible flag change relative to what is committed). I also tried
scikit-learn 1.5.2 + numpy 1.26 + pandas 2.2 as a cross-check: baseline 0.199,
RF 0.200, HistGBM 0.208 — **still HistGBM, still not the committed numbers**.
So the committed artefact predates the current pin and the fold assignment has
shifted with the library versions (`GroupKFold` internals changed around
sklearn 1.6). **This is a reproducibility problem for the manuscript, not a
P6a.1 regression — please confirm the new artefact on your machine before we
quote any of these numbers.**

New `csa_model.joblib` + `model_metrics.json` written to `model/artifacts/`
and copied to `app/backend/artifacts/` (both pairs md5-identical).

### 5. Evaluation scaffolding (the runs are yours)
`rag.retrieve.build_query_text` gains `expand: bool = True` — purely additive,
default behaviour byte-identical, only the `INDICATOR_SYNONYMS` terms are
dropped when False. `build_queries.py` gains `--no-query-expansion` (threaded
through `build_scenarios`, recorded as `query_expansion` in the build report)
and writes its report next to `--out`. `eval_retrieval.py` gains `--out`
(stem; `.json` + `.md`) and records the queries file in its JSON.

Both query sets are generated and committed:
`rag/eval/queries_v2.jsonl` and `rag/eval/queries_v2_baseline.jsonl`,
**45 scenarios each**. Verified: same scenario ids in the same order, **every
field except `query_text` identical**, and `query_text` differs in exactly
**18 of 45** scenarios — the three indicators that have synonyms (SOM content,
soil loss, water use efficiency). Clean ablation arm.

**v1 -> v2 is not a paired comparison, as the brief warned**, and the effect is
larger than expected: the stratified sample drops from **50 to 45** scenarios
and LPM coverage from **9 to 3**, because the sampler draws from
(family x indicator) cells and LPM lost 311 of its 409 rows. Report v1 and v2
as separate measurements, never as a delta.

Still to run (needs the index + key, ~100 embedding calls, well under $1):
```
python rag/eval/eval_retrieval.py --queries rag/eval/queries_v2_baseline.jsonl \
    --out rag/eval/results/retrieval_metrics_v2_baseline
python rag/eval/eval_retrieval.py --queries rag/eval/queries_v2.jsonl \
    --out rag/eval/results/retrieval_metrics_v2
```

### 6. Crosswalk re-run merge + graph
`propose_crosswalk.py` now **merges onto an existing csv** by `component`:
`owner_decision` and `owner_note` are always kept, `status` follows the
decision, new components are appended, vanished ones dropped, and it logs
exactly what it preserved. `--no-merge` forces a clean overwrite (and warns).

One design call: `proposed_groups`/`proposed_measures` are preserved verbatim
**only on a row whose `owner_decision` is non-empty**. On an undecided row they
are refreshed from the rules — the csv alone cannot tell an owner edit from a
rule change, and freezing stale rule output on 44 untouched rows would be the
worse failure. The measured columns (`aliases`, `families`, `n_rows`) always
refresh; that is exactly what P6a.1 needs to move.

Exercised on the real file: I seeded a `validated` decision with an edited
`proposed_measures` on `Mulch`, re-ran, and confirmed the decision, note,
edit and `status=validated` all survived while `Supplemental Irrigation`'s
`families` refreshed from LPM to `Erosion control and water management;
Integrated soil fertility management`. **I then reverted that seeded decision
(`--no-merge`) — the committed csv has all 44 rows `status=proposed` with
blank `owner_decision`. The validation decisions are yours to make, and I did
not fake one.** 9 new tests cover the merge behaviour.

`build_graph.py --wocat rag/ingest/wocat/fixtures` re-run: **722 nodes, 1,981
edges, `validation: []`** — node and edge *counts* unchanged exactly as the
brief predicted, but the substance moved: **3 `IN_FAMILY` edges retargeted**
(the three Supplemental Irrigation practices) and the `PracticeFamily` node
`n_rows` now read ECWM 1720->2021, ISFM 4404->4414, LPM 409->98. `graph.json`
md5 changed. `MAPS_TO` stays 0 (no validated crosswalk rows yet — correct).

### 7. Backend
**Full `pytest -q` in `app/backend`: 58 passed — no assertion needed changing.**
The suite does not hard-code family membership for these practices, so nothing
legitimately changed. (Nothing to list for this item.)

`/recommend` smoke, at the engine's own demo point (8.38, 39.37):

| query | candidates | grounded | `Supplemental Irrigation` reachable |
|---|---:|---:|---|
| `Erosion control and water management` x `yield` | 23 | 21 | **yes** (ranked 5th) |
| `Livestock production and management` x `yield` | 5 | 2 | **no** |

Both as required.

**Files** Modified: `pipelines/dataset/build_practice_family.py`,
`model/train_model.py`, `rag/retrieve.py` (additive `expand` only),
`rag/eval/build_queries.py`, `rag/eval/eval_retrieval.py`,
`rag/graph/crosswalk/propose_crosswalk.py`, `rag/graph/test_graph.py`,
`docs/decisions/practice_family_mapping.md`,
`docs/reports/merged_dataset_notes.md`,
`docs/decisions/wocat_crosswalk_proposal.csv`, the three dataset copies, and
both `model_metrics.json` + `csa_model.joblib` pairs.
New: `pipelines/dataset/test_practice_family.py`,
`rag/eval/queries_v2.jsonl`, `rag/eval/queries_v2_baseline.jsonl`,
`rag/eval/results/queries_v2{,_baseline}_build_report.json`.
**Scope guard honoured:** no change to `explain_service.py`, the Tier-1/Tier-2
corpora, `era_corpus`/`guidance_corpus`, or any column or file name; the only
`rag/retrieve.py` change is the additive `expand` parameter.
`git diff --ignore-all-space --stat` lists exactly these 15 tracked files and
nothing else (the repo-wide `M` flags remain the pre-existing CRLF churn).

**Decisions**
- `Inorganic Fertilizer-Supplemental Irrigation` -> ISFM, not ECWM (§1).
- Line terminators preserved on CSV rewrite, so the diff is only the 311 rows.
- Crosswalk target cells are owner-owned only once `owner_decision` is set (§6).
- The regenerated crosswalk is left fully undecided; no simulated validation.
- Reported the pinned-environment v1 re-train as the control for §4 rather
  than comparing against non-reproducible committed numbers.
- **Line endings.** `progress.md` and the two docs I edited are LF in HEAD
  but had been left CRLF in the working tree by the earlier repo repair, so
  editing them would have shown a whole-file rewrite. I normalised **only the
  four files this phase touches** (`progress.md`,
  `practice_family_mapping.md`, `merged_dataset_notes.md`, and the crosswalk
  csv) back to HEAD's LF, which is why their diffs now show just the real
  changes (+44/-2, +45/-1, +3/-3 and a clean +253/-0 append). The hundreds of
  other CRLF-churned files are left exactly as they were — not my phase to
  touch. `propose_crosswalk.py` now passes `lineterminator="\n"` to its
  `DictWriter` (the csv module defaults to CRLF on every platform), so the
  churn cannot come back on each re-run. The CSV **datasets** stay CRLF,
  which is what HEAD has for them.

**Verified** (WSL, Python 3.12, fresh venv: scikit-learn **1.7.2** pinned,
pandas 2.3, numpy 2.2, networkx 3.7, rasterio 1.5.2)
- `python -m py_compile` clean on all 8 touched Python files.
- **pipelines/dataset 25 · rag/graph 49 (40 + 9 new) · rag/ingest/wocat 20 ·
  rag/eval 13 · rag/ingest 17 · app/backend 58 — 182 passed, 0 failed.**
- Dataset regeneration mechanically verified (§3); three copies md5-identical.
- Retraining run three times (v2 pinned, v1 pinned control, v1 under sklearn
  1.5.2) to separate data effect from environment effect.
- Ablation arms verified to differ only in `query_text`, and only by synonyms.
- Crosswalk merge verified on the real 44-row file and by 9 unit tests.
- Graph rebuild verified down to the individual retargeted edges.
- `/recommend` smoke run against the real rasters and the new model.

**Needs local verification / your decisions**
1. **Approve or reject the ISFM split** for the 10
   `Inorganic Fertilizer-Supplemental Irrigation` rows (§1).
2. **Confirm the retrained model on your machine** (§4). The committed v1
   metrics are not reproducible here; the best model is HistGBM in every
   environment I tried, on both datasets, and `income` drops to a `low`
   confidence flag — a UI-visible change. If your machine reproduces
   RandomForest/0.1898 on the v1 data, tell me and I will pin whatever that
   environment is before we quote numbers in the manuscript.
3. **Run the two retrieval evaluations** (§5) and paste the results back;
   report v1 and v2 side by side, never as a delta.
4. **Validate the 44 crosswalk rows** — still all `proposed`, so the graph
   still has 0 `MAPS_TO` edges.
5. Consider noting the **thin LPM family** (98 rows, 2 grounded yield
   candidates) in the manuscript's limitations (§3).

### Review (Senior Engineer) — P6a.1 APPROVED ✅, with a corrected diagnosis of the reproducibility finding (24 Oct 2026)
Independently re-verified in a clean sandbox (upstream clone + the P6a.1 files):
- **Dataset change is exactly as reported:** 311 rows differ, `practice_family`
  is the only column that differs, row count/order unchanged; 301 → ECWM,
  10 (`Inorganic Fertilizer-Supplemental Irrigation`) → ISFM. **Decision: the
  ISFM split is APPROVED** — it is the documented priority rule ("fertilizer
  beats water", the mapping document's own worked example), not a
  special case.
- Suites re-run here: pipelines/dataset 25, graph 49, eval 13, ingest 17,
  wocat 20 — all green. `expand=False` verified: unmapped indicators
  byte-identical, mapped ones differ only by their synonym terms; the two v2
  query arms are identical except `query_text` (18/45 scenarios differ, as
  expected for the three mapped indicators); v2 = 45 scenarios, 25/28 cells,
  LPM 3 (the honest size of that family now).
- **Reproducibility finding — corrected diagnosis.** In this reviewer's
  sandbox (scikit-learn 1.7.2, pandas 3.0.5, numpy 2.5.3) `train_model.py` on
  the v1 data reproduces the committed metrics **exactly** (RandomForest,
  cv_r² 0.190, baseline 0.188, every per-indicator value identical), and on
  the v2 data gives RandomForest 0.212 (baseline 0.188, unchanged as it must
  be). The implementation agent's environment (pandas 2.3, numpy 2.2) gave
  HistGBM 0.233 / baseline 0.167, and its sklearn-1.5.2 cross-check a third
  set. So the committed artefact IS reproducible; what is not stable is the
  **fold assignment**: `GroupKFold` orders groups by size with
  `np.argsort`, and **298 of the 337 studies share their row count with at
  least one other study**, so fold membership is decided by numpy's
  tie-breaking, which differs between numpy versions/CPU code paths. Three
  environments → three fold assignments → three baselines, and even the
  winning model family flips (RF here, HistGBM there). This is a real
  methodological hazard for the manuscript and is fixed in P7 (persisted
  deterministic folds + repeated grouped CV). **Until P7 lands, no model
  number is quotable**; the v2 artefact written by P6a.1 (HistGBM) is
  accepted as an INTERIM serving model only.
- The LPM thinness (98 rows, 5 practices) goes into the limitations as
  suggested. Line-ending normalisation of the four touched files: accepted.

**Owner actions to close P6a.1:** run the two retrieval evaluations (venv
active, repo root; ~100 embedding calls):
```
python rag/eval/eval_retrieval.py --queries rag/eval/queries_v2_baseline.jsonl --out rag/eval/results/retrieval_metrics_v2_baseline
python rag/eval/eval_retrieval.py --queries rag/eval/queries_v2.jsonl --out rag/eval/results/retrieval_metrics_v2
```
paste both summary tables back (reported side by side with v1, never as a
delta), then commit: `git add -A ; git commit -m "P6a.1: practice_family fix (supplement keyword), dataset v2, interim retrain, eval scaffolding (reviewed)"`.

### Owner question (24 Oct 2026): drop GroupKFold to raise R²? — reviewer's analysis and recommendation
Measured on dataset v2 in the sandbox (RandomForest, same hyper-parameters):
| protocol | R² |
|---|---:|
| grouped 5-fold by study (current, honest) | **0.212** |
| random 5-fold (rows of the same study in train and test) | 0.507 |
| in-sample ceiling: (study, practice, indicator) cell means | 0.563 |
| study effect alone: (study, indicator) means | 0.493 |
| (practice, indicator) means, no study information | 0.386 |
Reading: the random-split number is leakage, not skill — half of the
variance in the target is the study (site/season/management) effect, which a
random split lets the model memorise and which is unavailable for a new pin.
Even an oracle that knows the exact study cell only reaches 0.56, because 44%
of the variance is within-cell replicate noise. A study-blind R² of ~0.2 is
therefore respectable, not embarrassing — but R² is also the wrong headline
for a *ranking* tool. Under the same honest grouped CV the model's **ranking
skill** is already measurable: within the 68 (study × indicator) cells that
compare ≥3 practices, Spearman ρ(predicted, observed) = 0.45 (median 0.50),
the predicted-best practice is the observed-best **59%** of the time (chance:
27.5%) and lands in the observed top half 68% of the time. (Sign accuracy
0.73 equals the 73% base rate of beneficial observations — the model does not
separate beneficial from harmful; balanced accuracy/AUC will say so honestly.)
**Recommendation: keep grouped CV as the primary protocol; report the
random-split number as the leakage ablation; make ranking metrics the
headline; add the noise-ceiling analysis; and fix fold determinism.** This is
Phase P7 — scheduled BEFORE P6b because every downstream result (faithfulness
run, expert study, manuscript tables) depends on a stable model.

### Next steps → Phase P7 — Model evaluation protocol: deterministic folds, repeated grouped CV, ranking metrics, leakage ablation (assigned to Claude Code)
Read CLAUDE.md first. Doctrine: the artefact format `recommend.py` loads
(`{model, cat_maps, features, cat, num, cat_mask, target, model_name,
indicator_confidence}`) is a contract — keep it byte-compatible; dataset
column names frozen; `recommend.py`/`advisor_agent.py` untouched.
1. **Deterministic folds** — new `pipelines/dataset/assign_folds.py`: writes
   `data/processed/cv_folds.csv` (`Study_No_`, `fold_rep00` … `fold_rep09`):
   10 repetitions of a 5-fold grouped assignment. Repetition 0 = studies
   ordered by (row count desc, `Study_No_` asc) then greedy balanced
   assignment (fewest rows first); repetitions 1–9 = the same greedy
   assignment after a seeded shuffle (`random.Random(rep)`) of the study
   order. Pure Python, no numpy sort involved. Tests: determinism across
   runs, every study in exactly one fold per repetition, fold-size balance
   within 5%, repetition 0 reproducible from the rule by hand on a toy set.
2. **Evaluation protocol** — new `model/evaluate.py` (importable functions +
   CLI), used by `train_model.py` (wrap: `train_model.py` keeps its CLI and
   artefact outputs, delegates CV to `evaluate.py`). For each of
   {mean baseline (practice × indicator), RandomForest, HistGBM}, run
   grouped CV over all 10 fold repetitions, per repetition collecting
   out-of-fold predictions; report **mean ± sd across repetitions** of:
   R², RMSE (overall, per indicator, per source); ranking metrics within
   (study, indicator) cells with ≥3 distinct practices after direction
   alignment with `recommend.DIRECTION` (import it): Spearman ρ, top-1 hit
   rate, top-half hit rate, pairwise concordance (C-index), plus the chance
   level for top-1; direction metrics: balanced accuracy and ROC-AUC for
   "beneficial" (sign of direction-aligned log RR) with the base rate
   stated. Add two reference rows: **random 5-fold (leakage ablation)** and
   the **noise ceiling** (R² of cell means, study means, practice×indicator
   means, in-sample). Model selection = highest mean grouped R² with
   ranking metrics reported alongside; ties → simpler model.
   **Confidence flags** = from the mean per-indicator grouped R² across
   repetitions (thresholds unchanged: ≥0.10 high, ≥0 medium, else low), so
   flags no longer flip with fold luck.
3. **Hyper-parameters (small, honest grid)** inside the same protocol: RF
   `min_samples_leaf ∈ {3, 5, 10}`, `n_estimators ∈ {150, 400}`; HistGBM
   `learning_rate ∈ {0.03, 0.06}`, `max_iter ∈ {400, 800}`,
   `min_samples_leaf ∈ {20, 50}`. Report the full table; choose by mean
   grouped R². `--quick` flag (2 repetitions, 1 setting) for tests/CI.
4. **Feature ablation row (report only, do NOT adopt):** the 13 features
   plus `lgp_days`, `soil_ph`, `soil_soc` (present in the dataset and the
   raster stack; currently explanation-only in `recommend.py`). If the gain
   exceeds one sd, say so; adoption is a separate decision because it
   changes the serving feature contract.
5. **Outputs:** `model/artifacts/model_eval.json` (every number above),
   `docs/reports/model_evaluation_report.md` (paper-ready tables: protocol
   comparison incl. leakage and ceiling rows; model comparison; per-
   indicator; ranking metrics; hyper-parameter grid), final
   `csa_model.joblib` + `model_metrics.json` (same keys as today, plus
   `protocol: "grouped-cv-10x5-deterministic"`, `cv_r2_sd`,
   `ranking_metrics`, `fold_file`) in `model/artifacts/` and copied to
   `app/backend/artifacts/`.
6. **Tests:** `model/test_evaluate.py` — fold loader, metric functions on a
   synthetic dataset with known answers (a perfect ranker → ρ=1, top-1=1;
   a reversed one → ρ=-1), direction alignment, flag derivation, artefact
   key compatibility with `recommend.py` (load the bundle and run one
   prediction through `recommend._load`-style access without rasters).
   Existing suites green (backend 58 incl. `test_api.py` if rasters present).
7. **Scope guard:** no changes to `recommend.py`, `advisor_agent.py`, the
   backend, RAG code, or data column names. `cv_folds.csv` is a NEW file
   (additive), the dataset files are untouched.
8. Append the phase report with the full tables (mean ± sd), the chosen
   model and why, which flags changed vs the committed v1 and why, and
   stop. The owner runs the full protocol if it exceeds your budget
   (`--quick` for your own verification).

**Launch (repo root):**
`claude "Read CLAUDE.md, then progress.md. The latest '### Next steps → Phase P7' block is your task. Implement it exactly, verify as instructed, append your phase report to progress.md, and stop."`

**P6a.1 closure (owner runs, 24 Oct 2026):** retrieval evaluation on dataset
v2 (45 scenarios, same frozen index). Baseline arm (no query expansion):
Success@4/8/16 = 0.378 / **0.556** / 0.600, Recall@8 0.230, MRR 0.351;
expansion arm: 0.378 / **0.556** / 0.622, Recall@8 0.241, Recall@16 0.339,
MRR 0.328. Same picture as v1 (Success@8 0.56 on 50 scenarios; expansion
non-decreasing on Success@k with coverage gains at k=16 and a small MRR
dip). Manuscript reports v2; v1 stays here as history. Committed as
aab597e. **P6a.1 closed.** ✅

## Phase P7 — Model evaluation protocol: deterministic folds, repeated grouped CV, ranking metrics, leakage ablation (24 Oct 2026)

**Built** Deterministic persisted folds, a repeated-CV protocol module that
`train_model.py` now delegates to, ranking/direction metrics, the leakage and
noise-ceiling reference rows, a 14-setting hyper-parameter grid, a feature
ablation, and a generated paper-ready report. 43 new tests.

### The headline: the reproducibility hazard is gone, and it is provable

The P6a.1 review's diagnosis was exactly right. With folds persisted,
**the baseline R² in this environment is now 0.188 ± 0.009 — matching the
reviewer's sandbox (0.188) to three decimals**, where before the same code
gave 0.167 here and 0.188 there. The baseline depends only on the fold
assignment, never on model internals, so it is the clean test of the fix:
it now agrees across environments because the split is read from a file
instead of being recomputed by `np.argsort`.

### 1. Deterministic folds — `pipelines/dataset/assign_folds.py`

Writes `data/processed/cv_folds.csv` (337 studies × `fold_rep00`…`fold_rep09`,
LF, sorted, 10 KB). Pure Python; no numpy sort anywhere. Repetition 0 is the
brief's rule exactly: order by (row count desc, `Study_No_` asc), then assign
each study to the fold holding the fewest rows (ties → lowest index).

**One refinement to the brief, measured.** The brief specifies a full
`random.Random(rep)` shuffle for repetitions 1–9. Implemented literally, that
destroys fold balance — a 539-row study arriving last lands wholly in one
fold, and **the worst fold deviated 21.5% from the mean row count**, far
outside the 5% the brief's own test requires, and itself a source of the
variance this phase exists to remove. I tried shuffling only *within size
ties*: perfect balance, but it pins the 39 uniquely sized studies (including
the five largest) to the same fold in every repetition, which would
understate the uncertainty. The adopted rule is a **local shuffle**: sort by
size, then shuffle only within consecutive blocks of 4. Measured outcome:

| shuffle rule | worst fold deviation | studies pinned to one fold | studies moving between rep0/rep1 |
|---|---:|---:|---:|
| full shuffle (brief, literal) | **21.5%** | — | — |
| within size ties only | 0.05% | 39 (incl. all 5 largest) | 234 |
| **within blocks of 4 (adopted)** | **0.05%** | **1** | **252** |

All ten repetitions balance to 1733/1733/1733/1733/1732 rows. `--block` is a
CLI argument so the choice is auditable.

### 2–3. Protocol and grid — `model/evaluate.py`

Importable functions plus a CLI. `train_model.py` keeps its CLI and artefact
outputs and now **delegates all CV to this module** — it re-exports
`FEATURES`/`CAT`/`NUM`/`build_cat_maps`/`encode` from it rather than keeping a
second copy (asserted by a test). Direction semantics import
`recommend.DIRECTION` (plain import when rasterio is present, `ast` parse of
the same literal otherwise — the mechanism `rag/graph/indicator_map.py`
already uses).

**Protocol comparison (10 reps × 5 folds, mean ± sd):**

| protocol | R² | reading |
|---|---:|---|
| **Grouped CV by study (primary)** | **0.251 ± 0.015** | what a new pin actually gets |
| Random 5-fold (leakage ablation) | 0.511 ± 0.004 | same study on both sides — not skill |
| Ceiling: (study, practice, indicator) means | 0.563 | oracle knowing the exact cell |
| Ceiling: (study, indicator) means | 0.493 | the study effect alone |
| Ceiling: (practice, indicator) means | 0.386 | practice effect, no study info |

All three ceilings reproduce the reviewer's sandbox exactly (0.563 / 0.493 /
0.386), as do the 68 scored cells and the 27.5% top-1 chance level — four
independent reimplementations agreeing is good evidence both are right.
~44% of the target is within-cell replicate noise no model can reach.

**Model comparison — selected: `HistGBM(learning_rate=0.03, max_iter=400,
min_samples_leaf=50)`, R² 0.251 ± 0.015.** Full 14-setting grid in
`docs/reports/model_evaluation_report.md` §5; the top and bottom:

| setting | R² | Spearman ρ | top-1 |
|---|---:|---:|---:|
| HistGBM lr=0.03, iter=400, leaf=50 **← selected** | **0.251 ± 0.015** | 0.39 ± 0.03 | 52.2% ± 3.1% |
| HistGBM lr=0.03, iter=400, leaf=20 | 0.248 ± 0.015 | 0.39 ± 0.04 | 51.6% ± 4.0% |
| RandomForest leaf=10, n=400 | 0.242 ± 0.013 | 0.36 ± 0.03 | 45.6% ± 5.2% |
| RandomForest leaf=3, n=150 (the old default) | 0.218 ± 0.018 | 0.36 ± 0.04 | 48.8% ± 3.5% |
| Baseline (practice × indicator mean) | 0.188 ± 0.009 | 0.30 ± 0.03 | 44.3% ± 2.4% |

Tuning is worth more than the model family: the best HistGBM beats the worst
by 0.029 R², and **every one of the 14 settings beats the baseline**. Note
the honest tension — the R²-selected model is *not* the best ranker in the
grid (HistGBM lr=0.06/iter=800/leaf=50 reaches ρ 0.40 ± 0.04 at R² 0.223).
The difference is well inside one sd, so I applied the brief's rule (highest
mean grouped R²) rather than second-guessing it, and report both.

**Ranking skill of the selected model** (68 cells, ≥3 practices, direction-aligned):

| metric | value | chance |
|---|---:|---|
| Spearman ρ (mean / median over cells) | 0.39 ± 0.03 / 0.51 ± 0.03 | 0 |
| top-1 hit rate | 52.2% ± 3.1% | 27.5% |
| top-half hit rate | 77.1% ± 2.3% | ~50% |
| C-index (584 pairs) | 0.70 ± 0.02 | 0.50 |

**Direction** — base rate of beneficial observations 73.1%; accuracy
74.6% ± 0.9% (i.e. barely above the base rate and therefore meaningless on
its own), **balanced accuracy 0.608 ± 0.013, ROC-AUC 0.682 ± 0.009**. The
model does separate beneficial from harmful, but weakly; quote the balanced
figures, never the plain accuracy.

**Per-indicator (selected model):**

| indicator | n | R² | flag |
|---|---:|---:|---|
| yield | 5910 | 0.100 ± 0.026 | high |
| biomass yield | 1525 | 0.078 ± 0.044 | medium |
| soil loss | 296 | -0.001 ± 0.050 | low |
| water use efficiency | 255 | -0.077 ± 0.068 | low |
| runoff | 359 | -0.138 ± 0.064 | low |
| income | 208 | -0.150 ± 0.100 | low |
| SOM content | 111 | -0.718 ± 0.492 | low |

Per source: CSA 0.374 ± 0.023, ERA 0.184 ± 0.015.

### 4. Feature ablation (report only, NOT adopted)

Adding `lgp_days`, `soil_ph`, `soil_soc` to the 13 serving features:
**R² 0.251 ± 0.016 vs 0.251 ± 0.015 — gain +0.0000, far inside one sd.**
There is no evidence of a gain, so there is nothing to trade against changing
the serving feature contract. Not adopted, as instructed.

### 5. Confidence flags — exactly one changes, and it is a coin flip

Flags now come from the **mean** per-indicator grouped R² across the ten
repetitions, so they no longer move with fold luck. Against the committed
v1 artefact, **one flag changes: `yield` medium → high.** That is
UI-visible (it drives the advisory's confidence wording).

**Please read this before accepting it.** `yield` scores
**R² = 0.10037 against a 0.10 threshold — a margin of +0.0004, which is 1.4%
of its own sd (0.0264)**. `soil loss` is the mirror image: -0.0012 against
the 0.0 threshold, 2.4% of its sd. Both flags are effectively undetermined;
which side they fall is a policy choice about where the thresholds sit, not
a measurement. Six of the fourteen grid settings put `yield` below 0.10. The
report now detects this automatically (`threshold_margins()`) and prints a
"Flags sitting on a threshold" table, so it can never be read as a finding.
**My recommendation: either widen to a band (e.g. high ≥ 0.15) or require
the lower confidence bound to clear the threshold. Your call — I did not
change the thresholds, since the brief said to keep them.**

### 6. Outputs

- `model/artifacts/model_eval.json` (81 KB) — every number above, including
  all 14 grid settings per repetition. Committed as the report's evidence.
- `docs/reports/model_evaluation_report.md` — **generated** from that JSON by
  `evaluate.format_report()`, so the tables cannot drift from the data. Seven
  sections incl. protocol comparison, grid, per-indicator, and reproduction.
- `model/artifacts/csa_model.joblib` + `model_metrics.json`, copied to
  `app/backend/artifacts/`. `model_metrics.json` keeps every published key
  with its exact shape (`per_indicator` is still `{indicator: [n, r2]}`;
  `metadata_service.py` reads `model`/`cv_r2`) and adds `protocol`,
  `cv_r2_sd`, `cv_rmse_sd`, `baseline_r2_sd`, `fold_file`, `n_reps`,
  `n_folds`, `model_params`, `model_label`, `ranking_metrics`,
  `direction_metrics`, `per_indicator_detail`, `noise_ceiling`,
  `leakage_ablation_r2`.
- Side benefit: the artefact drops from **15 MB to 1.97 MB** (HistGBM vs a
  150-tree forest) — still git-ignored, but smaller images and faster startup.
- `model_eval.json` is deliberately **not** copied to `app/backend/artifacts/`:
  the API reads only the joblib and `model_metrics.json`, and copying it would
  commit 81 KB twice.

**Files** New: `pipelines/dataset/assign_folds.py`,
`pipelines/dataset/test_assign_folds.py`, `model/evaluate.py`,
`model/test_evaluate.py`, `data/processed/cv_folds.csv`,
`model/artifacts/model_eval.json`, `docs/reports/model_evaluation_report.md`.
Modified: `model/train_model.py` (delegates CV; keeps its CLI, gains
`--folds`, `--quick`, `--no-grid`, `--no-ablations`, `--reuse-eval`,
`--report`), `model/artifacts/model_metrics.json` +
`app/backend/artifacts/model_metrics.json` (regenerated), both
`csa_model.joblib` (git-ignored).
**Scope guard honoured:** `git diff` over `app/backend/recommend.py`,
`advisor_agent.py`, `app/backend/app/`, all of `rag/`, and the dataset CSVs is
**empty**. `cv_folds.csv` is additive; no column or file name changed.

**Decisions**
- Local block shuffle (block 4) for repetitions 1–9 instead of a full
  shuffle — the only way to satisfy both the brief's balance test and its
  requirement that repetitions differ (§1).
- Selection by mean grouped R² per the brief, even though a different
  setting ranks marginally better; both reported (§2–3).
- Thresholds left unchanged; the near-threshold condition is *detected and
  printed* rather than silently resolved (§5).
- `train_model.py` re-exports the shared contract from `evaluate.py` rather
  than keeping a second definition (wrap, never fork).
- The markdown report is generated, never hand-written.

**Verified** (WSL, Python 3.12, scikit-learn **1.7.2** pinned, pandas 2.3.3,
numpy 2.2.6, joblib 1.6.0)
- `python -m py_compile` clean on all 5 touched Python files.
- **225 tests pass, 0 fail:** folds **16** (new) · model **27** (new) ·
  pipelines/dataset family 25 · rag/graph 49 · wocat 20 · rag/eval 13 ·
  rag/ingest 17 · **app/backend 58 (full suite incl. `test_api.py` with the
  rasters present) — no assertion needed changing.**
- New tests cover: the hand-worked repetition-0 rule on a toy set,
  determinism across runs and across dict ordering, partition completeness,
  the <5% balance bound on the real study-size distribution, that
  repetitions genuinely differ, LF/sorted round-trip, **and that the
  committed `cv_folds.csv` is exactly what the script reproduces**; a perfect
  ranker scoring ρ=1/top-1=1 and a reversed one ρ=-1/top-1=0, tie handling in
  ranks and concordance, per-practice averaging, direction alignment, flag
  derivation at the thresholds, grouped folds never splitting a study, and
  **the serving-artefact contract** (load the bundle and push one row through
  it exactly as `recommend.py` does — no rasters needed).
- `cv_folds.csv` byte-identical on re-run (`cmp`).
- `/recommend` smoke against the real rasters and the new model: ECWM×yield →
  In-situ water harvesting / Water Harvesting / Biological SWC (confidence
  high); ISFM×yield and ECWM×soil loss also sane.
- Full protocol wall time ~19 min (14 settings × 10 reps × 5 folds + baseline
  + 2 ablations). `--quick` (2 reps, 1 setting, ~19 s) is what the tests use.

**Needs local verification / your decisions**
1. **The `yield` flag (§5).** It clears the "high" threshold by 0.0004.
   Decide whether to keep the thresholds, widen them, or require a lower
   confidence bound — this is the one UI-visible change in the phase.
2. **Re-run `python model/train_model.py` on your machine** and confirm the
   selection. The folds are now fixed, so the baseline (0.188) and the
   ceilings must match exactly; the model R²s may still move a little with
   library versions, and the grid's top three are within 0.003 of each other,
   so a different environment could legitimately pick a different HistGBM
   setting. If that happens the right fix is to pin the setting, not to
   re-tune.
3. **Confirm the model-family change is acceptable for serving** —
   RandomForest → HistGBM, now on a measured basis (0.251 vs 0.242 for the
   best RF) rather than the P6a.1 interim accident.
4. Nothing in this phase re-ran the retrieval evaluation or touched the RAG
   layer; P6a.1's numbers stand.

### Review (Senior Engineer) — P7 APPROVED with hardening applied ✅ (24 Oct 2026)
Independently re-verified in a clean sandbox:
- **Fold determinism achieved and proven across machines:** `assign_folds.py`
  regenerated here produces a `cv_folds.csv` **byte-identical** to the
  owner's; all ten repetitions balance to 0.05%; 336/337 studies change fold
  across repetitions (the report's "~250" undercounts — cosmetic). The
  block-of-4 shuffle refinement is accepted: it fixes the balance problem a
  literal per-rep shuffle would have had, without pinning the large studies.
- **Headline metrics reproduce exactly** from my own independent
  implementation over the persisted folds (selected HistGBM, 10 × 5):
  R² 0.251 ± 0.015, Spearman 0.390 ± 0.031, top-1 0.522 ± 0.031 (chance
  0.275), balanced accuracy 0.608, AUC 0.682, yield R² 0.100 ± 0.026;
  baseline 0.188 ± 0.009 = the committed v1 baseline, closing the
  reproducibility incident. Noise ceilings 0.563 / 0.493 / 0.386 and the 68
  scored cells also match.
- Suites: pipelines/dataset 40 (+1 skip), model 27 → 28 after hardening.
- Two definitional notes for the manuscript (not defects): (i) the C-index
  gives prediction ties half credit (Harrell's convention); ties are 6.7% of
  comparable pairs because HistGBM returns identical predictions for rare
  practices in the same study — report the tie share with the C-index
  (strict version ≈ 0.66); (ii) **"top-half hit" has a chance level of
  0.635** (cells of three practices make the "upper half" two of three), so
  0.771 is a modest gain and MUST be reported with its chance level or
  dropped — decision: **drop it from the headline; lead with top-1 (0.52 vs
  0.275 chance), Spearman and the C-index.**
- An honest finding worth a sentence in the paper: for *direction*
  (beneficial or not), the practice × indicator mean baseline is as good as
  or better than every model (balanced accuracy 0.627 vs 0.608, AUC 0.700 vs
  0.682); the models' advantage is in *ranking* (Spearman 0.39 vs 0.30,
  C-index 0.70 vs 0.64) and magnitude (R² 0.251 vs 0.188). That is exactly
  the claim the system makes.

**Decisions:**
1. **Model selection by mean grouped R² stands** (HistGBM lr 0.03, 400
   iterations, min leaf 50); the marginally better ranker (ρ 0.398 at R²
   0.223) is within one sd on both metrics. Tuning mattered more than model
   family; the feature ablation gain is +0.0000, so the serving contract
   stays as is.
2. **Confidence-flag rule hardened (reviewer, applied):** a flag is granted
   only when the LOWER end of the mean ± 1 sd band clears the threshold
   (`evaluate.confidence_flags`, `CONFIDENCE_K_SD = 1.0`;
   `train_model.py --reuse-eval` now refreshes flags under the current rule
   and rewrites the payload so payload, report and artefact agree; test
   added, 28/28). Effect: `yield` → **medium** (0.100 − 0.026 < 0.10),
   `income` → low (was medium in v1; its v1 R² of 0.002 was never
   defensible), everything else unchanged. The thresholds themselves are
   untouched.
3. The interim P6a.1 artefact is superseded; after the owner's `--reuse-eval`
   run the artefact is **quotable** (protocol `grouped-cv-10x5-deterministic`).

**Owner actions to close P7** (venv active, repo root; ~20 s, no re-evaluation):
```
cd model ; python -m pytest test_evaluate.py -q ; cd ..
python model/train_model.py --reuse-eval
cd app/backend ; python -m pytest -q ; cd ../..
git add -A ; git commit -m "P7: deterministic folds, repeated grouped CV, ranking metrics, leakage/ceiling ablations; flags from the lower CV band (reviewed)" ; git push origin main
```
Expected: "confidence flags refreshed … yield → medium"; backend 58 passed;
`docs/reports/model_evaluation_report.md` regenerated with the new flag
paragraph.

### Next steps → Phase P6b-i — Graph integration that needs no WOCAT data (assigned to Claude Code)
The WOCAT export is pending; this phase lands everything in the P6b design
that does not depend on it, so P6b-ii (ingestion + practice records) is a
short step when the data arrives. Read CLAUDE.md first; doctrine 1 applies
with the P6a review's rule: **graph aggregates of effect magnitude
(`mean_log_rr`, `median_log_rr`) never reach the LLM prompt or the UI —
only counts, directions (`share_positive`) and provenance do.**
1. **Package hygiene** — convert `rag/graph/` (and `rag/ingest/wocat/`) to
   package-relative imports (`from . import schema`, `from .schema import …`);
   remove the `sys.path.insert(0, GRAPH_DIR)` hacks; tests run as
   `python -m pytest rag/graph rag/ingest/wocat` from the repo root (add a
   root `conftest.py` or `pytest.ini` with `pythonpath = .` if needed). No
   top-level module named `schema`, `query` or `build_graph` may exist in
   the API process (test: import `rag.graph.query` and assert
   `"schema" not in sys.modules`).
2. **`rag/graph/context_classes.py`** — `context_to_classes(ctx: dict) ->
   dict[kind, value]` mapping the engine's resolved context (keys as
   `recommend.extract_context` returns them: `Rainfall` mm, `slope` %,
   `Altitude_r` m, `soil_clay` %, `lgp_days`, `temp_mean_annual`) onto the
   QT classes in `wocat_taxonomy.CONTEXT_CLASSES`: rainfall band, slope
   class, altitude zone, soil texture from clay % (USDA-style bands:
   < 18 % coarse, 18–35 medium, > 35 fine — document the rule), agro-climatic
   zone from `lgp_days` (FAO LGP bands: < 75 arid, 75–180 semi-arid,
   180–270 sub-humid, > 270 humid — document and cite). Exhaustive tests on
   band edges; unmappable inputs → omitted key, never a guess.
3. **Synthetic guard** — `build_graph.py` refuses records with
   `synthetic: true` unless `--allow-synthetic`; `query.similar_context_
   technologies` drops synthetic nodes unless `include_synthetic=True`;
   tests for both. The fixture directory keeps the synthetic record for
   tests only.
4. **Graph evidence block in `/explain` (Tier-1 data only).** In
   `explain_service.explain()`, after evidence retrieval, call
   `rag.graph.query.evidence_summary(practice, indicator)` for each
   recommended practice (graceful no-op when `rag/graph/store/graph.json`
   is absent: log once, skip). Add to the response an additive
   `evidence_base` field per practice: `{n_studies, n_obs, aez_belts,
   crop_groups, corpus_status: {full_text, abstract, none}, studies:
   [{era_code, title, year, doi, corpus_status}]}` — counts and provenance
   only, NO effect magnitudes. Prompt: a short "EVIDENCE BASE" line per
   practice ("backed by N studies / M field observations in <belts>; K of
   the studies are in the retrievable corpus") placed before the passages;
   extend `allowed_numbers` with these counts (extend, never bypass). The
   deterministic fallback text gains the same sentence. `ExplainResponse`
   schema additive; `/metadata` gains `graph_ready: bool`.
5. **UI** — the Evidence panel shows the evidence-base line above the
   chips (counts + belts), with a tooltip listing the studies; hidden when
   `graph_ready` is false. Types updated; `npm test` + `npm run build`.
6. **Graph build in the owner workflow** — `rag/README.md` documents
   `python -m rag.graph.build_graph` as a step after the index build;
   `build_graph.py` default run (no `--wocat`) must succeed without
   fixtures and without pydantic (core graph only).
7. **Tests:** backend explain tests for the evidence block (present /
   absent graph, numbers whitelisted, fallback sentence), context mapper
   edges, synthetic guard, import hygiene; all existing suites green
   (backend 58 + new, graph 49 + new, frontend 16 + new).
8. **Scope guard:** Tier-1/Tier-2 corpora, `era_corpus`/`guidance_corpus`,
   `rag/retrieve.py`, `recommend.py`, the model artefacts and the dataset
   are untouched. No WOCAT fetching of any kind.
9. Append the phase report per CLAUDE.md and stop.

**Launch (repo root):**
`claude "Read CLAUDE.md, then progress.md. The latest '### Next steps → Phase P6b-i' block is your task. Implement it exactly, verify as instructed, append your phase report to progress.md, and stop."`

## Phase P6b-i — Graph integration that needs no WOCAT data (25 Oct 2026)

**Built** The whole P6b design that does not depend on the pending export:
`rag/graph` and `rag/ingest/wocat` converted to real packages, a context
mapper, a two-sided synthetic guard, the Tier-1 evidence base through
`/explain` to the UI, and the graph build documented in the owner workflow.
124 new tests.

### 1. Package hygiene — the API process can no longer be shadowed

Every `sys.path.insert(0, GRAPH_DIR)` is gone from `rag/graph` and
`rag/ingest/wocat`; the modules now import each other relatively
(`from . import schema`, `from .schema import …`). A new repo-root
`pytest.ini` (`pythonpath = .`, plus `norecursedirs` so a bare `pytest` at
the root does not wander into `.venv`/`node_modules`) is all that is needed
for `python -m pytest rag/graph rag/ingest/wocat`.

The assertion the brief asked for is a test:
`test_importing_the_graph_creates_no_top_level_modules` imports
`rag.graph.query`, `rag.graph.schema`, `rag.graph.build_graph` and
`rag.graph.context_classes` and asserts that **none** of `schema`, `query`,
`build_graph`, `wocat_taxonomy`, `practice_components`, `indicator_map`,
`context_classes` exists in `sys.modules`. A second test asserts importing
the graph does not mutate `sys.path` at all.

A pleasant consequence: `rag/ingest/wocat/schema.py` needed a 20-line
`importlib.util.spec_from_file_location` hack in P6a purely because
`rag/graph/schema.py` shares its name. With both as packages the collision
cannot happen, so the hack is deleted — `from rag.graph.schema import
CONTEXT_CLASS_KINDS` now says exactly what it means, and a test pins that
the wocat module really does get the graph's object (`is` identity).

**Consequence to know:** `python rag/graph/build_graph.py` now fails with
`attempted relative import with no known parent package`. That is inherent
to relative imports, not a bug — the CLIs are `python -m rag.graph.build_graph`
and `python -m rag.graph.crosswalk.propose_crosswalk`, documented in both
READMEs with a line explaining why.

### 2. `rag/graph/context_classes.py` — the engine context → QT classes

`context_to_classes(ctx)` maps `recommend.extract_context` output onto the
QT §5.1-§5.3 vocabularies. Five mappings, each with its source cited in the
module docstring:

| engine key | QT kind | rule |
|---|---|---|
| `Rainfall` mm | rainfall_band | QT §5.1 verbatim |
| `slope` % | slope_class | QT §5.2 verbatim |
| `Altitude_r` m | altitude_zone | QT §5.2 verbatim |
| `soil_clay` % | soil_texture | USDA-style: < 18 coarse, 18-35 medium, > 35 fine |
| `lgp_days` | agroclimatic_zone | FAO/QT LGP: < 75 arid, 75-180 semi-arid, 180-270 sub-humid, > 270 humid |

Two judgement calls, both documented in the module rather than hidden:

* **The questionnaire's bands have one-unit gaps** (`< 250 mm` then
  `251-500 mm`; `flat (0-2%)` then `gentle (3-5%)`) because it expects
  integer answers, but raster values are continuous. The gaps are closed
  **upward**: a value goes in the first band whose upper bound it does not
  exceed, so 250.4 mm is `< 250 mm` and 250.6 mm is `251-500 mm`. Both sides
  of every boundary are tested.
* **`temp_mean_annual`, `soil_depth`, `topsoil_om` are not mapped.** The QT
  has no temperature class, and the serving stack carries neither soil depth
  nor organic matter. `soil_soc` is organic *carbon*; turning it into
  organic *matter* needs the Van Bemmelen factor (~1.724) — an assumption I
  will not make silently. It is a two-line addition if you want it.

Unmappable input (missing, NaN, non-numeric, or a nodata sentinel like
-9999, or out of physical range) **omits the key** rather than guessing a
nearest band. Every emitted label is validated against
`wocat_taxonomy.CONTEXT_CLASSES`, so a typo in the band table raises instead
of inventing a class. **98 tests**, including one that parses
`recommend.STACK` with `ast` to prove the source keys are names the engine
actually produces.

### 3. Synthetic guard — two independent barriers

* `build_graph.py` **refuses** records with `synthetic: true` unless
  `--allow-synthetic`, logging which ids it dropped; with the flag it warns
  that the graph must not feed the app or an evaluation. The flag is
  recorded in `graph_report.json`.
* `query.similar_context_technologies()` **drops** synthetic nodes unless
  `include_synthetic=True` — belt and braces, so even a graph that somehow
  contains one cannot surface it in an advisory. The test proves the filter
  is load-bearing: on a steep semi-arid context the synthetic record would
  otherwise rank **first**.

The canonical store is rebuilt accordingly: **720 nodes, 1,961 edges**, one
Technology (#6644) and one Approach (#6732), `validation: []`,
byte-identical on re-run.

### 4. Evidence base in `/explain` — counts and provenance, never magnitudes

`explain_service` gains a graph layer with the same shape as the Tier-2
guidance layer: `graph_is_ready()` (cheap file check), `get_graph_query()`
(lazy, caches, logs once and disables itself on any failure) and
`set_graph_query()` for injection. `build_evidence_base()` calls
`rag.graph.query.evidence_summary(practice, indicator)` per recommended
practice and copies **only** `{n_studies, n_obs, aez_belts, crop_groups,
corpus_status: {full_text, abstract, none}, studies: [{era_code, title,
year, doi, corpus_status}]}`.

**Doctrine 1 is enforced, not assumed.** `evidence_summary` returns
`mean_log_rr`, `median_log_rr` and `share_positive`; none is copied. The
test fixture deliberately *includes* those fields and then asserts they are
absent from the serialized output and that the key sets are exactly the
allowed ones — so the test fails if someone widens the copy later.

* **Prompt:** an `EVIDENCE BASE` block before the passages, one sentence per
  practice, introduced as "counts and provenance only; these are NOT effect
  sizes and must not be described as such", plus a matching system-prompt
  rule. Tested for position (before the passages) and for the absence of
  `mean_log_rr`.
* **Guardrail:** `allowed_numbers()` **extends** (never bypasses) with the
  study/observation counts and study years, because those now appear in the
  prompt. Two tests pin both halves: a sentence quoting "3 studies and 17
  field observations" is rejected without the evidence base and accepted
  with it, while "cuts soil loss by 77.4%" is still rejected either way.
* **Fallback:** the deterministic template gains the identical sentence, so
  both paths state the same facts.
* `ExplainResponse.evidence_base` is additive and always present (`{}` when
  the graph is absent, never null); `/metadata` gains `graph_ready`.

Smoke-tested against the **real** graph: `Water Harvesting` × `soil loss`
returns "backed by 11 studies / 107 field observations in Dry Dega, Dry
Kolla, … ; 8 of the studies are in the retrievable corpus", with the eleven
studies and their DOIs in `studies`, and no magnitude anywhere in the
payload.

### 5. UI

`EvidencePanel` shows an **Evidence base** list above the citation chips,
hidden unless `/metadata` reports `graph_ready`, with the full study list
(era_code · title · year — full text / abstract only / not in the corpus) in
the `title` tooltip.

The panel's vitest environment is `node`, not jsdom, so rendering tests
would have meant adding `jsdom` + `@testing-library/react`. Instead the
presentation logic lives in a new `src/lib/evidence-base.ts`
(`evidenceBaseEntries`, `evidenceBaseSentence`, `studiesInCorpus`,
`studyLine`, `studiesTooltip`) and is unit-tested there — the repo's own
pattern (`chat-flow.test.ts`), a thinner component, and the sentence stays
word-for-word identical to the backend's. **9 new frontend tests**, one of
which asserts the sentence never contains `%` or `log|ratio|mean|median`.

### 6. Owner workflow

`rag/README.md` gains step 4 (`python -m rag.graph.build_graph`), the
optional flags, the `-m`-not-a-path explanation, and what `graph_ready`
turns on. `rag/graph/README.md` is updated for the package layout and gains
a "Synthetic records" section. **Verified: the default build (no `--wocat`)
succeeds with pydantic blocked** — 718 nodes, `validation: []`, `pydantic`
never imported; `--wocat` without pydantic degrades with a clear message
instead of crashing.

### A defect I found in my own P7 work, and fixed

`model/test_evaluate.py` called `train_model.main([...])` without
`--no-report`, and `--report` defaults to the **real**
`docs/reports/model_evaluation_report.md`. Every run of the model suite
therefore overwrote the repo's evaluation report with one generated from the
96-row synthetic fixture (I caught it because the working copy's report said
`Protocol: SENTINEL-NOT-RECOMPUTED … 96 rows, 12 studies`). All four calls
now pass `--no-report`, and I regenerated the real report with
`train_model.py --reuse-eval`: **it came back byte-identical to the
committed one**, and a cmp-before-and-after test run confirms the suite no
longer touches it. That `--reuse-eval` also rewrote
`model/artifacts/model_metrics.json`, which is now **semantically identical
to the committed version** (it had drifted to 5,240 bytes in the working
tree before my session started — mtime 00:34, before my first edit at
00:39). `model_eval.json` I did not touch; it is semantically equal to HEAD,
differing only in formatting from your closure run.

**Files** New: `rag/graph/context_classes.py`,
`rag/graph/test_context_classes.py`, `pytest.ini`,
`app/frontend/src/lib/evidence-base.ts`,
`app/frontend/src/lib/evidence-base.test.ts`.
Modified: `rag/graph/{query,build_graph,indicator_map,test_graph}.py`,
`rag/graph/crosswalk/propose_crosswalk.py`,
`rag/ingest/wocat/{schema,normalize_wocat,test_wocat}.py`,
`app/backend/app/services/explain_service.py`, `app/backend/app/schemas.py`,
`app/backend/app/metadata_service.py`, `app/backend/tests/test_explain.py`,
`app/frontend/src/lib/types.ts`,
`app/frontend/src/components/evidence-panel.tsx`, `rag/README.md`,
`rag/graph/README.md`, `model/test_evaluate.py`, and the regenerated
`docs/reports/model_evaluation_report.md` + `model_metrics.json` pair.
**Scope guard honoured:** `git diff` over `recommend.py`,
`advisor_agent.py`, `rag/retrieve.py`, `rag/corpus/`, `rag/index/`,
`data/processed/` and `app/backend/dataset/` is **empty**. No WOCAT fetching
of any kind. `rag/README.md` was normalised to HEAD's LF (it had drifted to
CRLF in the working tree) so its diff shows only the 41 added lines.

**Decisions**
- `--allow-synthetic` + `include_synthetic` as two independent guards rather
  than one, so neither a bad build nor a bad query can leak scaffolding.
- Band gaps closed upward, and unmappable context omitted rather than
  snapped to the nearest band (§2).
- `soil_soc` → `topsoil_om` deliberately NOT mapped: it needs a conversion
  factor that is a research assumption, not a lookup.
- Frontend logic extracted to `lib/evidence-base.ts` instead of adding jsdom
  to the toolchain (§5).
- Four P6a graph tests were updated because the synthetic record is now
  refused by default — `test_fixtures_ingest_as_technology_and_approach_nodes`
  (2 → 1 technologies) and three that need the synthetic record now opt in
  with `allow_synthetic=True` / `include_synthetic=True`. These are
  intended-behaviour changes, not weakened assertions.

**Verified** (WSL, Python 3.12 / scikit-learn 1.7.2 venv; frontend via the
Windows Node 24.19 in `node_modules`)
- `python -m py_compile` clean on all 16 touched Python files.
- **349 Python tests pass, 0 fail:** rag/graph + rag/ingest/wocat **174**
  (49 → 174: +98 context mapper, +7 synthetic/hygiene, +20 wocat), pipelines
  + model **69**, rag/eval **13**, rag/ingest **17**, **app/backend 76**
  (58 → 76: +18 evidence base). Plus **25 frontend tests** (16 → 25).
- Import hygiene proven by test and by hand: importing `rag.graph.query`
  leaves `sys.modules` free of every bare name and `sys.path` unmodified.
- `/metadata` over the real app returns `rag_ready = True, graph_ready = True`.
- Real-graph `/explain` smoke (above) with no magnitude in the payload.
- Core build with **pydantic blocked**: 718 nodes, `validation: []`.
- Graph store rebuilt: 720 nodes / 1,961 edges, byte-identical on re-run.
- Frontend `tsc --noEmit` clean; `eslint .` **0 errors**, 10 warnings — all
  pre-existing React-Compiler warnings (follow-up F-1), **none in the files
  I touched**.
- An autouse `_no_auto_graph` fixture was added to the backend suite: without
  it the existing tests would silently depend on whether a graph store
  happens to exist on the machine.

**Needs local verification / your decisions**
1. **`npm run build` could not be verified here.** It fails in this
   environment with `next/font/google queries have exactly one entry` /
   `Can't resolve '@vercel/turbopack-next/internal/font/google/font'` —
   a Turbopack font-resolution failure in `src/app/layout.tsx`, a file I did
   not touch. I proved it is not mine: **reverting my two changed frontend
   files and rebuilding gives the identical error.** It is most likely the
   Windows-installed `node_modules` being driven from WSL. Please run
   `npm run build` on Windows; `npm test` (25) and `tsc --noEmit` both pass
   here.
2. **Check `model/artifacts/model_metrics.json` and `model_eval.json`** are
   what you expect after the repair described above — they were already
   modified in the working tree when this session began.
3. Decide whether `soil_soc` → `topsoil_om` should be mapped (§2); it needs
   your call on the carbon→organic-matter factor.
4. P6b-ii remains: ingest the WOCAT export, replace the synthetic fixture
   with two real Ethiopian Technologies, and wire
   `similar_context_technologies` into `/explain` using
   `context_to_classes` — which is now the only missing piece on that path.

### Review (Senior Engineer) — P6b-i APPROVED with hardening applied ✅ (25 Oct 2026)
Independently re-verified in a clean sandbox (upstream clone + the P6b-i files):
- Suites from the repo root: rag/graph + rag/ingest/wocat **174/174**; backend
  `test_explain.py` **51/51** (52 after hardening); model **28/28**; context
  mapper **98/98**. Import hygiene confirmed in a fresh interpreter: after
  `import rag.graph.query, rag.graph.build_graph, rag.ingest.wocat.schema` no
  top-level `schema`/`query`/`build_graph` module exists and `sys.path` is
  untouched. The model suite no longer overwrites
  `docs/reports/model_evaluation_report.md` (checked: unchanged after a run).
- **The P7 artefacts the agent asked us to sanity-check are intact:**
  `model_metrics.json` (both copies), `model_eval.json` and the evaluation
  report differ from HEAD only in line endings — zero content changes;
  flags still `yield: medium`, `income: low`.
- Evidence-base block: doctrine 1 holds end to end — the response, prompt
  sentence and fallback carry counts/belts/provenance only; the test that
  plants `mean_log_rr` in the fixture and asserts its absence is the right
  kind of test. Synthetic guard verified as two independent barriers.
- `context_to_classes`: bands are QT-verbatim, edges tested; rule = first
  band whose upper bound the value does not exceed (inclusive).

**Hardening applied in review (backend 52/52):**
1. `allowed_numbers` now harvests from the evidence base **exactly the three
   numbers the prompt sentence states** (n_studies, n_obs, studies in
   corpus). Study years/era codes and per-bucket corpus counts were being
   whitelisted although they never reach the prompt — the same class of
   hole as the URL digits fixed in P5a. Regression test added
   (`test_guardrail_whitelists_only_the_numbers_the_prompt_states`).
2. `context_classes.py` docstring aligned with the implemented rule (it
   claimed 250.4 mm → "< 250 mm"; the code and the 98 tests say 250.0 →
   "< 250 mm", 250.1 → "251-500 mm"; likewise clay 18.0 / LGP 75.0).

Accepted as reported: the four P6a graph tests updated for the synthetic
guard (intended behaviour); `npm run build` failing under WSL on the
Windows-installed `node_modules` (owner builds on Windows).

**Owner actions to close P6b-i** (Windows, venv active):
```
cd app\backend ; python -m pytest -q ; cd ..\..
cd app\frontend ; npm test ; npm run build ; cd ..\..
python -m rag.graph.build_graph
git add -A ; git commit -m "P6b-i: graph integration without WOCAT data — relative imports, context classes, synthetic guard, evidence-base block in /explain + UI (reviewed, hardened)" ; git push origin main
```
Expected: backend 77 passed; frontend 25 passed + build OK; graph 722 nodes.
Then `npm run dev` + uvicorn once: the Evidence panel should show
"backed by N studies / M field observations in …" above the chips.

### Next steps → Phase P8 — Expert-study readiness: citation numbering, Tier-2 chunk quality, audit dry run (assigned to Claude Code)
Purpose: make the texts the experts will rate clean and defensible, whether
or not the WOCAT export arrives in time. Read CLAUDE.md first.
1. **Per-study citation numbering (P2c tracked finding).** Today the prompt
   numbers evidence passages per CHUNK (`[n]`) while the UI chips and the
   citation list are per STUDY, so a reader sees `[6]` with four chips.
   Change `_build_messages` so passages are grouped and numbered per study
   (`[1]` = first study; several passages of one study share its number and
   are shown as `[1a]`, `[1b]` … in the prompt but cited as `[1]`), the
   guardrail's marker regex and `shape_citations` numbering follow, the
   Evidence panel shows the same `[n]` on each chip, and the faithfulness
   auditor's `cite_markers`/`cited_support` logic maps markers to studies.
   Tier 2 keeps `[Gn]` per document (already per document). Tests for
   prompt numbering, marker stripping, citation ↔ chip consistency, auditor
   mapping. Existing P3 artefacts are not re-run.
2. **Tier-2 chunk quality filter.** 11.1% of the 19,997 guidance chunks are
   tables, reference lists or OCR-shattered text (reviewer sample, 25 Oct:
   alpha ratio < 0.70, or short-token share > 0.35, or all-caps share
   > 0.30). Add `rag/ingest/quality.py` with a documented, tested
   `chunk_quality(text) -> {score, flags}` (alpha ratio, short-token share,
   caps share, digit share, mean word length, reference-list and table
   patterns) and a `--min-quality` gate in `chunk_guidance.py`; add
   `rag/ingest/prune_collection.py` that deletes failing chunk ids from an
   existing Chroma collection and rewrites the chunks file (no
   re-embedding; uses `index_tools`-style safety: refuses to create stores,
   prints the funnel). Calibrate the threshold on a labelled sample of 100
   chunks (you label them, write the sample + labels to
   `rag/ingest/quality_sample.csv` for the owner to spot-check), target
   ≥ 95% precision on "garbage". Tier 1 is NOT filtered (frozen). Report the
   expected removal count; the owner runs the prune.
3. **Faithfulness audit dry run.** `eval_faithfulness.py --n 2` against the
   live stack (owner runs; needs key + rasters) must work with the new
   numbering, the evidence base and guidance; fix whatever breaks; confirm
   the audit CSV columns and that `explanations.jsonl` carries both A and B
   conditions. `make_packets.py --experts 3` dry run on those two
   scenarios, then delete the smoke outputs.
4. **Protocol check.** Read `rag/eval/expert_study/protocol.md` against the
   current system and list in the report every statement that is now stale
   (tiers, citation style, evidence-base line) — do not rewrite the
   protocol; the reviewer will.
5. Scope guard: no changes to Tier-1 corpus/index, the model, the dataset,
   `recommend.py`; `era_corpus` untouched; guidance pruning is a deletion
   of flagged ids only, never a re-chunk of Tier 1.
6. Append the phase report per CLAUDE.md and stop.

**Launch (repo root):**
`claude "Read CLAUDE.md, then progress.md. The latest '### Next steps → Phase P8' block is your task. Implement it exactly, verify as instructed, append your phase report to progress.md, and stop."`

### DECISION RECORD — product direction: production-grade trilingual UI, then evidence-tiered advisory (26 Oct 2026, owner + supervisor + reviewer)
1. **UI redesign to production grade** (supervisor's request: attractive,
   intuitive, standard) in two reviewed phases, U1 and U2, BEFORE P8. Three
   languages: English (`en`), Amharic (`am`, Ethiopic script), Afaan Oromoo
   (`om`, Latin/Qubee). Machine-drafted translations are explicitly marked
   for native review by the owner before release.
2. **Evidence-tiered advisory (Phase P9, brief after U2):** the system goes
   beyond the ML ranking when field-trial evidence is thin. Three provenance
   modes decided from the knowledge graph's evidence base per (family,
   indicator, context): **model-led** (sufficient trials: ML ranks; RAG +
   WOCAT explain and show how), **hybrid** (thin evidence: ML ranking with a
   thin-evidence flag PLUS a documented-practice shortlist from WOCAT/GARDIAN,
   clearly labelled), **knowledge-led** (no trial evidence: instead of today's
   "No field evidence" error, documented practices from similar contexts with
   provenance). Doctrine 1 is restated, not weakened: *effect numbers come
   only from the model; knowledge sources may propose practices with
   provenance but never quantify effects.* U1 designs the result card with a
   source badge for these three modes so P9 is a backend change only.
3. Order: U1 → review → U2 → review → P8 → P9 → P6b-ii when the WOCAT export
   arrives → faithfulness run → expert study → manuscript.

### Next steps → Phase U1 — UI foundation: design system, app shell, i18n (en/am/om), Advisor flow (assigned to Claude Code)
Read CLAUDE.md first, then inspect the existing frontend end to end
(`app/frontend/src/**`, 5.6k lines; `lib/api.ts`, `lib/chat-flow.ts`,
`lib/types.ts`, `metadata-provider.tsx` are working logic to WRAP, not
rewrite). Branding stays **AgroAdvisor-ET · Agroecology+**. The backend API
contract is unchanged except the additive `language` field below. Honest
display rules are binding: every number shown comes from the API; a low
confidence flag is presented as *thin evidence*, never as danger; nothing in
the UI invents a claim.

**A. Design language (binding tokens; document them in `docs/design/
design_system.md` and implement as CSS variables in `globals.css` +
`tailwind.config.ts`):**
- Palette "Ethiopian highland", light and dark, WCAG AA on every text/
  background pair (state the measured contrast ratios in the doc):
  background warm off-white `#F7F8F5` / dark `#0F1613`; surface `#FFFFFF` /
  `#182019`; text `#1C2A22` / `#E8EEE9`; muted text `#5B6B61` / `#9FB0A5`;
  border `#DDE4DE` / `#2A362E`; **primary (green)** `#1E6B46` hover
  `#175537`, dark-mode primary `#4CAF7A`; **secondary (soil/ochre)**
  `#8C5A2B` / `#C9915A`; **accent (sky/water)** `#2E7FB8` / `#6FB3E6`;
  success `#2E8B57`, warning `#C98A1E`, danger `#B23A3A` (danger is for
  system errors ONLY). Confidence semantics: high = primary green, medium =
  warning amber, low = neutral grey with the label "thin evidence". Chart
  palette: 6 steps derived from primary/secondary/accent, colour-blind
  safe (state the check). Tier chips: evidence = green outline, guidance =
  accent outline, practice record (P9) = secondary outline.
- Typography: one UI family, IBM Plex Sans (already loaded) with tabular
  numerals for figures; **Noto Sans Ethiopic** (next/font/google, subset
  `ethiopic`) applied when `locale === "am"`; drop the serif display font
  (headings = Plex Sans 600/700). Type scale 12/14/16/18/22/28/36 px;
  line-height 1.5 body, 1.2 headings; Ethiopic needs +2 px line-height.
- Spacing on a 4 px grid; radius 12 px cards / 8 px controls / full pills;
  two elevation levels; focus ring 2 px primary with offset; motion ≤ 200 ms,
  respects `prefers-reduced-motion`.
- Icons: lucide-react (already). Images: the 55 practice images in
  `public/practices` via `next/image` with explicit sizes.

**B. Component library.** Adopt the shadcn/ui pattern — copy-in components
on Radix primitives (`@radix-ui/react-dialog`, `-popover`, `-tooltip`,
`-tabs`, `-select`, `-toast`, `-slot`), styled with the tokens via
class-variance-authority + tailwind-merge (both already dependencies):
`Button` (primary/secondary/outline/ghost, sizes, loading), `Card`,
`Badge`/`Chip`, `Tabs`, `Dialog`, `Sheet` (mobile bottom sheet), `Tooltip`,
`Select`/`Combobox`, `Toast`, `Skeleton`, `Alert`, `Stepper`. Replace the
ad-hoc `ui/button.tsx`, `ui/section.tsx`, `chips.tsx` usages; keep
`ui/motion.tsx` only if it respects reduced motion.

**C. Information architecture and screens.**
1. App shell: header (logo/wordmark, nav: Advisor · Chat · About, language
   switcher, theme toggle), content, footer (Alliance Bioversity–CIAT
   attribution, "evidence-ranked, not a forecast" disclaimer, version from
   `/health`, link to the data sources). Mobile-first; header collapses to
   a bottom tab bar on phones.
2. `/` Home (short): hero with the one-sentence promise and two CTAs
   ("Get a recommendation" → Advisor, "Ask the advisor" → Chat); a
   three-step "how it works"; a live trust strip from `/metadata` (field
   observations, studies, practices, AEZ belts — numbers from the API, no
   hard-coding); the five challenge families; footer. Remove or fold the
   current demo/powers/provenance sections into these.
3. `/advisor` (new primary screen; `/dashboard` redirects to it): a
   four-step stepper with a persistent summary rail — **1 Location** (map
   with pin, place search, "use my location", coordinates shown; outside
   Ethiopia = inline validation), **2 Challenge** (five family cards with
   icon + one-line description), **3 Objective** (indicator chips valid for
   that family, with plain-language labels), **4 Crop** (optional
   combobox) → **Results**. Results: a context card (AEZ belt + rainfall,
   altitude, slope, soil, LGP with units and one-line meaning), the ranked
   practice cards (rank, translated practice name, effect sentence from the
   API with the confidence badge and its plain-language meaning,
   "n field observations", practice image), per card: "Why this?" (details
   as today), "Evidence" (the existing EvidencePanel incl. the evidence-base
   line and tier chips), "How to implement" (guidance chips). A **source
   badge** per result set — `Field-trial model` now; `Hybrid` and
   `Documented practice` reserved for P9 — with its explanatory tooltip
   copy in all three languages. Empty, loading (skeletons), API-down and
   no-evidence states designed, not improvised. Results persist in the URL
   (`?lat&lon&family&indicator&crop`) so an advisory can be re-opened.
4. `/chat`: keep working as is in U1 (restyled by the new shell/tokens
   only); full redesign is U2.
5. `/about`: what the system is, how to read confidence, data sources,
   authorship, licence; replaces the popover.

**D. Internationalisation (standard: `next-intl`).** App Router `[locale]`
segment (`/en`, `/am`, `/om`), middleware with locale detection
(cookie → Accept-Language → `en`), `<html lang>` set per locale, language
switcher in the header that preserves the current route and query.
Catalogs `messages/en.json`, `am.json`, `om.json` with namespaced keys;
**no user-visible string may remain hard-coded** (add an ESLint rule or a
test that greps `src/` for JSX text outside the catalogs). Data-contract
strings stay English in the API; display translations live in
`src/i18n/glossary.ts`: the 5 families, 7 indicators, 12 AEZ belts, crop
groups, confidence labels, tier labels, the 44 practice components (the 100
practice names are composed from components with a localised joiner, e.g.
"Biochar + Inorganic Fertilizer"). Numbers/dates via `Intl`. Draft the
Amharic and Afaan Oromoo catalogs yourself; write
`docs/i18n/TRANSLATION_STATUS.md` listing every key with status
`machine-draft` — the owner marks `reviewed`. A build-time check fails when
`am`/`om` miss a key that `en` has.
**Backend (additive only):** `language: Literal["en","am","om"] = "en"` on
`ChatRequest` and `ExplainRequest`; the chat and explain system prompts gain
"Reply in <English | Amharic (አማርኛ) | Afaan Oromoo>" and keep every other
rule; the deterministic fallback texts, clarification messages and social
replies get catalogs in `app/backend/app/i18n/{en,am,om}.py` (the numeric
guardrail is script-independent: digits only, and Western digits are used
in all three); `/metadata` lists `languages`. Tests: prompt carries the
language instruction; fallback text in `am` contains Ethiopic; `en`
behaviour byte-identical to today.

**E. Quality bar (production grade).** TypeScript strict; `eslint .` **0
errors, 0 warnings** — this includes fixing the ten React-Compiler-era hook
sites flagged since 15 Oct (follow-up F-1: `useSyncExternalStore` for
storage reads, derived state/`key` for prop→input sync, set refs in effects)
and restoring those two rules to `error`; vitest + Testing Library for the
stepper, result card, language switcher and glossary; `next build` green;
Lighthouse on `/en/advisor` (document the run: Chrome, mobile preset) with
Performance ≥ 90, Accessibility ≥ 95, Best Practices ≥ 95; axe checks on
the three screens; keyboard-only completion of the advisor flow (the map
pin must be settable by keyboard: coordinate inputs); `aria-live` for
results; colour contrast verified; `prefers-reduced-motion` respected;
error boundaries per route; 404 page; an "API unreachable" banner driven by
`/health`.

**F. Scope guard.** No changes to `recommend.py`, the model, the RAG
pipeline, `explain_service.py` beyond the `language` plumbing, or the API
response shapes (additive fields only). Do not remove the Evidence panel's
tier chips or the evidence-base line. No new backend dependencies. Keep
`npm test`/`npm run build` runnable on Windows (the owner's build
environment).

**G. Report.** Append the phase report per CLAUDE.md with: screenshots
(light/dark, phone/desktop, en/am/om) saved under `docs/design/
screenshots/`, the Lighthouse scores, the contrast table, the translation
status summary, and anything you deliberately left for U2. Then stop.

**Launch (repo root):**
`claude "Read CLAUDE.md, then progress.md. The latest '### Next steps → Phase U1' block is your task. Implement it exactly, verify as instructed, append your phase report to progress.md, and stop."`

**Queued — Phase U2 (brief written after the U1 review):** chat redesign
(conversation layout, inline result cards, quick replies, streaming states,
language-aware input and voice-to-text hook point), printable/shareable
advisory (print stylesheet + "Save as PDF" + share link), Playwright E2E for
advisor + chat against a mocked API, translation-review workflow, offline/
low-bandwidth behaviour (image fallbacks, retry), final a11y/perf pass.

## Phase U1 — UI foundation: design system, app shell, i18n (en/am/om), Advisor flow (2026-10-26)

**Built**
- **Design system** ("Ethiopian highland"): light/dark tokens as CSS variables + Tailwind theme (`globals.css`, `tailwind.config.ts`); WCAG AA measured for every text/background pair and documented with ratios in `docs/design/design_system.md` — four brief hues fail AA as *text* (light warning 2.76:1, accent 4.07, success 3.98, dark danger 3.11) so derived `*-text` tokens are used for text while the brief's hues stay for fills/borders; dark primary buttons take dark text (white on `#4CAF7A` is 2.72:1). Confidence semantics high = green, medium = amber fill with dark text, low = neutral grey "Thin evidence"; danger red only for system errors. 6-step chart palette found by random search for CVD safety (min CIE76 ΔE 15.6 light / 17.5 dark under protan/deutan/tritan). IBM Plex Sans 400/500/600 with tabular numerals; Noto Sans Ethiopic under `html[lang="am"]` with +2 px leading; 4 px grid, radii 12/8/full, two elevations, 2 px focus ring, motion ≤ 200 ms behind a global reduced-motion block; lucide icons; the 55 practice photos through `next/image`.
- **Component library** (`src/components/ui/`, shadcn pattern on Radix + cva + tailwind-merge): Button (Slot/asChild, loading), Card, Badge (+`confidenceVariant`/`tierVariant`), Chip (aria-pressed), Tabs, Dialog, Sheet (bottom sheet on phones), Tooltip, Select, Combobox (WAI-ARIA combobox/listbox, keyboard complete), Toast (external store), Skeleton, Alert, Stepper, Input/Label. `ui/section.tsx`, `ui/motion.tsx`, `chips.tsx`, `setup-pickers.tsx`, `about-popover.tsx`, the old headers/footer, `dashboard-panel.tsx`, `location-picker.tsx`, `recommendation-card.tsx` and `home/{demo,powers,provenance,stats}` are deleted; framer-motion removed from `package.json`.
- **App shell** (`src/app/[locale]/layout.tsx` + `components/shell/`): `<html lang>` per locale, fonts via next/font, `NextIntlClientProvider`, theme provider on `useSyncExternalStore` with a `next/script beforeInteractive` bootstrap (no flash), metadata and `/health` external stores, Tooltip/Toast providers, skip link, "API unreachable" banner driven by `/health` (polled 30 s + `online`), header (logo, Advisor·Chat·About, language switcher that preserves route **and** query, theme toggle), footer (Alliance Bioversity–CIAT attribution, "evidence-ranked, not a forecast", version from `/health`, data-sources/method/licence links), mobile bottom tab bar, route-level `error.tsx` (root, advisor, chat), localised `not-found.tsx` + `[...rest]` catch-all.
- **Screens**: `/` home (hero + 2 CTAs, 3-step how, **live** trust strip from the new `/metadata.evidence` counts — 8 664 observations / 337 studies / 100 practices / 12 belts / 5 families / 7 objectives — five family cards); `/advisor` four-step stepper (Location: Leaflet map with token-coloured pin, offline place search via new `GET /geocode`, "Use my location", keyboard coordinate fields that commit on blur/Enter with outside-Ethiopia validation and the resolved belt; Challenge cards; Objective chips limited to evidence-backed indicators; Crop combobox) + summary rail with per-step edit → Results (context card with units **and** meaning for belt/rainfall/temperature/altitude/slope/clay/pH/SOC/LGP; ranked cards with translated practice name over the English data name, the API's effect sentence — in am/om the same `pct_change` in a translated frame with the original sentence in `title` —, confidence badge + meaning, n field observations, photo, "Why this?" (confidence, chart of `details.ranked`, API note/scope), "Evidence" (existing explain flow: grounded/AI badges, explanation, evidence-base line with tier chips, source studies, guidance) and "How to implement" (guidance documents); **source badge** "Field-trial model" with tooltip, Hybrid/Documented reserved for P9; Top-N select; copy-link; "Explain in chat"); designed empty / loading / API-down / no-evidence / error states; request persisted in the URL `?lat&lon&family&indicator&crop&top` (a complete URL scores immediately, `/recommend` in parallel with `/metadata`); `/dashboard` → `/advisor` redirect; `/chat` kept working and restyled (Sheet map, chips, quick replies on the shared ChallengeCards/ObjectiveChips, every string from the catalog, `language` sent, "Explain in chat" pre-fills the composer via `?q=` — nothing auto-sends); `/about` page replaces the popover.
- **i18n**: next-intl App Router `[locale]` (`/en|/am|/om`), `src/proxy.ts` detection cookie `agro-locale` → Accept-Language → en (verified: `am-ET` → `/am`, `om` → `/om`, cookie beats header, default sets the cookie), switcher preserves route + query; `messages/{en,am,om}.json` (290 keys, ICU plurals); `src/i18n/glossary.ts` (5 families + short/blurb, 7 indicators + nouns, 12 belts, 14 crop groups, confidence + meaning, tiers, source modes, 44 components mirroring `rag/graph/practice_components.py` with the alias table, `practiceName` with a localised joiner, `effectSentence`); Intl number formatting; `docs/i18n/TRANSLATION_STATUS.md` generated by `app/frontend/scripts/translation_status.py` (458 keys, all `machine-draft`, 7 `chat.protocol.*` keys `protocol-en`). Hard-coded-string guard: `src/lib/i18n-audit.test.ts` parses every `src/**/*.tsx` with the TypeScript compiler (JSX text + user-facing attributes) and checks am/om key parity + ICU placeholder validity with `@formatjs/icu-messageformat-parser`.
- **Backend (additive, no new dependencies)**: `app/i18n/{__init__,en,am,om}.py` catalogs (`t`, `term`, `reply_instruction`); `language: Literal["en","am","om"]="en"` on `ChatRequest`/`ExplainRequest`; prompts end with "Reply in English | Amharic (አማርኛ) | Afaan Oromoo"; fallback/clarification/social/evidence-base texts localised (Western digits everywhere; engine error strings pass through verbatim); `/metadata` gains `languages` and `evidence` counts (`recommender_service.evidence_counts()` reads the canonical table — counts only); new `GET /geocode?q=` wrapping the chat gazetteer (offline, network fallback off). English outputs are byte-identical to a pre-refactor snapshot (`tests/fixtures/en_texts_pre_u1.json`).

**Files**
- New: `app/backend/app/i18n/*`, `app/backend/app/routers/geocode.py`, `app/backend/tests/test_i18n.py`, `tests/fixtures/en_texts_pre_u1.json`; `app/frontend/messages/*.json`, `src/i18n/{routing,request,navigation,glossary}.ts`, `src/proxy.ts`, `src/app/[locale]/**` (layout, page, advisor, chat, about, dashboard, error, not-found, [...rest]), `src/app/fonts/NotoSansEthiopic-ethiopic.woff2` (+README), `src/components/ui/*`, `src/components/shell/*`, `src/components/advisor/*`, `src/components/home/trust-strip.tsx`, `src/lib/{health,metadata-store}.ts`, `scripts/translation_status.py`, tests (`glossary.test.ts`, `health.test.ts`, `i18n-audit.test.ts`, `stepper.test.tsx`, `result-card.test.tsx`, `language-switcher.test.tsx`), `rag/graph/test_glossary_sync.py`; `docs/design/design_system.md`, `docs/design/screenshots/*.png` (13), `docs/design/lighthouse/{README.md,*.json,axe-*.json}`, `docs/i18n/TRANSLATION_STATUS.md`.
- Modified: backend `schemas.py`, `metadata_service.py`, `main.py`, `routers/{chat,explain}.py`, `services/{chat_service,explain_service,slot_extraction,recommender_service}.py`, `tests/test_api.py`; frontend `next.config.ts` (next-intl plugin), `tailwind.config.ts`, `globals.css`, `eslint.config.mjs` (hook rules back to **error**), `vitest.config.ts`/`vitest.setup.ts` (jsdom polyfills, RTL cleanup), `package.json`/lock (next-intl, Radix, testing deps, axe-core; framer-motion removed), `src/lib/{api,types,evidence-base,chat-flow}.ts` (+ tests), `components/{chat-panel,chat-quick-replies,evidence-panel,pct-chart,practice-image,location-map,metadata-provider,theme-provider,assistant-markdown}.tsx`, `components/home/{hero,how,families}.tsx`, `components/ui/button.tsx`.
- Deleted: listed under *Built*.

**Decisions**
1. **Numbers stay the model's.** Cards show `recommendations[].effect` verbatim in English; am/om render the identical `details.ranked[].pct_change` inside a translated frame (`effectSentence`) and keep the English sentence reachable (`title`); the chart plots `details.ranked` as returned; evidence base shows counts only. No UI code rounds, re-estimates or invents a figure; the trust strip reads counts from `/metadata`.
2. **Data-contract strings stay English on the wire** (family/indicator/crop/practice names, chat protocol messages); the UI translates through the glossary at render time and passes unknown values through unchanged. Chat protocol strings are therefore `protocol-en` in all catalogs — the backend slot extractor is English-only, so free-text chat in am/om gets an Amharic/Oromo *reply* but no slot filling (U2).
3. **Ethiopic font self-hosted** (`next/font/local`) instead of the brief's `next/font/google`: Turbopack's Google-font loader rejects Noto Sans Ethiopic ("next/font/google queries have exactly one entry") and 500'd every page of the owner's `next dev` (verified against the owner's running dev server before/after; it now serves `/am` with both font variables). Same zero-layout-shift behaviour, no third-party font requests, OFL licence noted in `src/app/fonts/README.md`.
4. **F-1 fixed structurally**: theme, `/health` and `/metadata` are external stores read with `useSyncExternalStore`; prop→input sync uses derived state (coordinate fields keyed by the external point, commit on blur/Enter); every "loading" flag is derived from whether the stored answer matches the current request key, so no effect sets state synchronously; `react-hooks/set-state-in-effect` and `react-hooks/refs` are errors again and the tree lints clean.
5. **Advisor route is dynamic** (`dynamic = "force-dynamic"`): the request lives in the query string, so step 1 / the results shell is server-rendered with real params instead of a static shell that bails out to client rendering; chat is dynamic through `searchParams` (`?q=`).
6. `/geocode` is a new additive endpoint (gazetteer only, Nominatim stays off) so the location step's place search never leaks queries to a third party; `/metadata.evidence` is additive and counts-only.
7. Context-aware indicator labels (`indicatorLabelForFamily`) are replaced by one glossary label per indicator in all three languages; `deriveDashboardSetup`/`shortFamilyName` remain in `chat-flow.ts` for their tests but are unused by the UI (U2 cleanup).
8. Tier chips and the evidence-base line are kept; Evidence/How-to share one `POST /explain` per recommendation (`ExplainProvider`), citations filtered to the card's practice with a fall-back to all.

**Verified**
- Backend: `python -m py_compile` on every touched file; `pytest tests/test_api.py tests/test_i18n.py tests/test_explain.py` → **104 passed** (includes the new `/metadata` evidence+languages and `/geocode` tests, with the raster stack); `pytest rag/graph/test_glossary_sync.py` → 2 passed (TS alias table == `ALIASES`, 44 components == `CANONICAL_COMPONENTS`).
- Frontend (Windows node 24 from WSL): `tsc --noEmit` 0 errors; `eslint .` **0 errors, 0 warnings** (hook rules at error); `vitest run` **110 tests / 10 files passed** (api, chat-flow, utils, evidence-base incl. Amharic sentence, health store, glossary, i18n audit over 44 component files + catalog parity/ICU validity, Stepper, ResultCard en/am incl. lazy chart, LanguageSwitcher route+query preservation); `next build --webpack` green (18 static pages for 3 locales; advisor/chat dynamic).
- Running build (standalone server + U1 backend): locale detection and `<html lang>` per locale, `/en/dashboard` → `/en/advisor`, 404 page, images, gzip on HTML/CSS/JS all confirmed with HTTP probes.
- **Lighthouse 13.5** (Chrome headless, mobile emulation, production build, two consecutive runs; full table + notes in `docs/design/lighthouse/README.md`):

  | screen | Perf (run A / B) | A11y | Best practices | LCP (B) |
  |---|---|---|---|---|
  | `/en/advisor` (step 1) | 69 / **74** | **100** | 77 | 9.6 s (OSM tile) |
  | `/en/advisor?lat…&indicator` (results) | 74 / **80** | **100** | 81 | 5.3 s |
  | `/en/chat` | 79 / **89** | **100** | 81 | 3.8 s |
  | `/en` | 77 / **78** | **100** | 81 | 5.9 s |

  Best practices loses only `is-on-https` (the measurement topology calls the API over plain http on a non-localhost address; with the shipped localhost default the same build measured 96) and the OSM tile-resolution audit. **Performance ≥ 90 is not met** — analysis and the U1 mitigations already applied are in the README.
- **axe-core 4.14** inside the page on `/en`, `/en/advisor` results, `/en/chat`, `/am/advisor` results: **0 violations** (one `color-contrast` node marked "needs review"). Contrast table with measured ratios: `docs/design/design_system.md`.
- Screenshots (13): home/advisor/results/chat/about × light/dark × phone (390 px)/desktop (1440 px) × en/am/om under `docs/design/screenshots/` (reviewed: Ethiopic font, dark palette, bottom tab bar, live trust strip, translated cards all render as designed).
- Translation status: 458 keys (290 UI + 114 glossary + 54 backend) → 902 `machine-draft` cells, 14 `protocol-en`, 0 reviewed.
- Owner's own Turbopack `next dev` (read-only GETs) now returns 200 for `/en/advisor`, `/am`, `/om/chat`.

**Needs local verification**
- `npm run build` with **Turbopack** on Windows (the agent can only build with `--webpack` from WSL); `npm test`/`npm run build` on Windows after `npm install` (lockfile changed).
- A manual **keyboard-only** walkthrough of the advisor in a real browser (the agent's browser pane cannot reach localhost): Tab order header → stepper → map region hint → search → latitude/longitude (commit on blur/Enter) → Next → challenge cards (Space/Enter, aria-pressed) → objective chips → crop combobox (type/↑↓/Enter/Esc) → Get recommendation → results `aria-live` announcement.
- Screen-reader pass (VoiceOver/NVDA) on the results `aria-live` region and the stepper's current/completed announcements.
- Real-device performance on a low-end Android phone over 3G/4G (Lighthouse simulated figures above).
- Native-speaker review of every am/om string (`docs/i18n/TRANSLATION_STATUS.md`; flip rows to `reviewed` via `REVIEWED` in `scripts/translation_status.py`).

**Left for U2**
- Performance: defer the Leaflet map on phones until the user interacts (step-1 LCP is a map tile), split next-intl messages per route, trim Radix/next-intl payload, measure on device; consider a static map placeholder image.
- Language-aware chat intent parsing so am/om users can type naturally (today the chat reply is localised but slot extraction expects English; the quick-reply chips keep the flow usable).
- Native review of translations; glossary review of the 44 component names with an agronomist.
- Hybrid / Documented-practice source badges and WOCAT records (P9), per-practice "How to implement" content beyond the guidance corpus.
- Minor: language-switcher trigger truncates on narrow phones in Amharic; API prose fields (`details.note`, `ranking_scope`) still English (`lang="en"`); remove the now-unused helpers in `chat-flow.ts`; the home trust strip counts belts in the training table (12) — rename the label if "agro-ecological belts covered" is preferred.

### Review (Senior Engineer) — U1 APPROVED ✅ with four must-fix items carried into U2 (26 Oct 2026)
Independently re-verified in a clean sandbox (snapshot of `app/frontend`,
`app/backend/app`, `app/backend/tests`, catalogs, docs):
- Backend: `test_explain` + `test_i18n` + `test_slot_extraction` **89/89**
  (slot tests need the model artefact; `test_api` needs the rasters — owner's
  104 stands). Glossary-sync test 2/2. English outputs byte-identical to the
  pre-U1 fixture by test.
- Frontend from the new lockfile: `tsc --noEmit` clean, `eslint .` **0/0**
  with the two React-Compiler rules at `error` (follow-up F-1 closed),
  `vitest run` **110/110**. Catalogs: 290 keys in each of en/am/om, no gaps;
  the 12 Amharic values without Ethiopic script are units, the app name and
  the chat protocol strings — correct.
- `next build` (Turbopack) **could not run here**: the sandbox cannot reach
  `fonts.googleapis.com` for IBM Plex Sans — the same limitation as the 15 Oct
  sandbox. The owner's Windows build is the verification of record, and this
  is also a product finding (item 0c below).
- Screenshots reviewed: the design language is as specified — calm highland
  palette, one typeface, Ethiopic rendering clean, live trust strip, stepper
  with summary rail, "thin evidence" badge instead of red, source badge
  present. The chat, home and about screens read as one system.

**Must-fix items (carried into U2 as item 0, not applied in review because
each is cross-cutting frontend work):**
- **0a. Phone-width overflow.** `advisor-en-light-phone.png` (390 px) shows
  the right edge clipped on the header language switcher, the summary rail
  card, the results toolbar and the context card captions. Either the page
  overflows horizontally at 390 px or the capture viewport was wider than
  the saved image; U2 must determine which on a real device/DevTools,
  fix any overflow, and add an automated check (`document.scrollWidth <=
  window.innerWidth`) at 360/390/412/768/1440 px for every screen.
- **0b. Effect-sentence grammar.** "~76% reduce in soil loss" comes from the
  engine's own string (`recommend.py`: `f"~{eff:.0f}% {goal_txt} in
  {indicator}"`) and is mirrored by the English frame in `glossary.ts`.
  Change the wording to "~76% reduction in soil loss" / "~12% increase in
  yield" in BOTH places (`goal_direction` keeps the values `reduce`/
  `increase` — only the sentence changes); update the three test fixtures.
- **0c. Self-host IBM Plex Sans** via `next/font/local` next to Noto Sans
  Ethiopic (SIL OFL; keep the licence file): a production build must not
  depend on reaching Google Fonts (CI, air-gapped and low-connectivity
  deployments in Ethiopia), and it removes the Turbopack font-loader
  fragility met in U1.
- **0d. Mobile performance.** Lighthouse mobile Performance 74/80 on the
  advisor is below the 90 target; the LCP is the first map tile. Apply the
  mitigations U1 already identified (defer the map on phones until the
  Location step is interacted with or visible, split next-intl messages per
  route, size-constrained tiles) and re-measure; document whatever the
  honest ceiling is on the production build.

Accepted as reported: Noto Sans Ethiopic self-hosted (right call); chat
protocol strings English in all languages until the intent parser is
language-aware (U2 item 1); the two additive endpoints (`/metadata.evidence`,
offline `/geocode`).

**Owner actions to close U1 (Windows, venv + node):**
```
cd app\frontend ; npm ci ; npm test ; npm run lint ; npm run build ; cd ..\..
cd app\backend ; python -m pytest -q ; cd ..\..
git add -A ; git commit -m "U1: production UI foundation — design system, Radix component library, app shell, next-intl (en/am/om), Advisor flow, backend language plumbing (reviewed)" ; git push origin main
```
Then `npm run dev` + uvicorn: walk the Advisor flow keyboard-only once in
each language, check a phone-width window (DevTools → 390 px) for any
horizontal scroll (item 0a), and begin the native review in
`docs/i18n/TRANSLATION_STATUS.md` — start with the glossary terms (families,
indicators, belts, components), which appear on every screen.

### Next steps → Phase U2 — Chat redesign, print/share, E2E, hardening (assigned to Claude Code)
Read CLAUDE.md first; the U1 report and review above are the context. The
same design tokens, components and quality bar apply; no API shape changes
except additive fields.
0. **Must-fix from the U1 review** — items 0a–0d above, in that order, each
   with its own test or measurement. 0b touches `recommend.py` only in the
   effect sentence (one f-string); `goal_direction` values are unchanged.
1. **Chat redesign.** Conversation layout on the new shell (message list
   with role styling, timestamps, markdown rendering kept), **inline result
   cards that reuse the Advisor's `ResultCard`/`ContextCard`/source badge**
   (one component path, as with the Evidence panel), quick replies as chips,
   explicit streaming/thinking/error states, "Open in Advisor" on any
   result (deep link with the query), and a map sheet for "Pick on map".
   **Language-aware intent parsing:** when `OPENAI_API_KEY` is set, the
   backend's slot extraction runs an LLM pass for `am`/`om` free text
   (structured JSON output; the English rule-based parser stays as is);
   without a key, a localised message steers the user to the Advisor flow.
   The chat protocol strings become translatable once the parser is
   language-aware; update `TRANSLATION_STATUS.md` statuses accordingly.
   Tests for the extractor (fixtures in all three languages) and the UI.
2. **Printable / shareable advisory.** A print stylesheet for the results
   view (context, ranked practices with effect + confidence + evidence
   base line, source badge, citations, the disclaimer, generation date,
   the share link as text), a "Save as PDF" action (`window.print`), and
   the existing "Copy link" kept. The printed page must carry the same
   honesty copy as the screen.
3. **Playwright E2E** (`app/frontend/e2e/`, mocked API via Playwright
   route interception with fixtures from the real response shapes): the
   Advisor flow end to end in en/am/om, chat happy path with streaming,
   keyboard-only completion, the 0a overflow check at five widths, axe on
   every screen, dark mode. `npm run e2e` script; runs headless on Windows
   and Linux.
4. **Translation review workflow.** `scripts/translation_status.py
   --export review.csv` (key, en, am, om, status) and `--import review.csv`
   (owner edits am/om cells and marks `reviewed`); the glossary terms
   listed first; a vitest guard that a `reviewed` cell cannot silently
   change without returning to `machine-draft`.
5. **Low-bandwidth behaviour.** Practice images lazy with a lightweight
   placeholder and a text fallback; API calls with bounded retry/backoff
   and a visible retry; map tile failure shows a message and keeps the
   coordinate inputs usable; the API-down banner already exists.
6. **Docs.** `app/frontend/README.md` (stack, scripts, i18n workflow,
   design tokens pointer, E2E), root `README.md` quick start updated for
   the trilingual UI; `docs/design/design_system.md` kept in sync.
7. Scope guard: engine/model/RAG untouched beyond 0b; Evidence panel
   semantics kept; no new backend dependencies beyond what the LLM
   extractor needs (none — it uses the existing OpenAI client).
8. Append the phase report with screenshots (chat en/am/om, print preview,
   phone 390 px proof of no overflow), the E2E summary, the Lighthouse
   re-measure, and stop.

**Launch (repo root):**
`claude "Read CLAUDE.md, then progress.md. The latest '### Next steps → Phase U2' block is your task. Implement it exactly, verify as instructed, append your phase report to progress.md, and stop."`

## Phase U2 — Chat redesign, print/share, E2E, hardening (2026-10-28)

**Built**
- **0a Phone-width overflow — root cause found and guarded.** Measured with Playwright (`document.scrollWidth <= window.innerWidth`): the header's language-switcher trigger (icon + label, `min-w-[8.5rem]`) plus the brand block pushed the header past 390 px, which gave the whole document a horizontal scroll and clipped every screen's right edge. Fix: icon-only switcher below `sm` (label stays in the accessible name), `min-w-0`/`truncate` on the brand, `shrink-0` on the controls. Guard: `e2e/overflow.spec.ts` checks nine screens (home, advisor step 1, results en/am/om, chat en/am, about, 404) at 360/390/412/768/1440 px; `e2e/advisor.phone.spec.ts` repeats it under Pixel-7 emulation. Proof: `docs/design/screenshots/u2-advisor-results-en-light-phone-390.png`.
- **0b Effect-sentence grammar.** `recommend.py` builds `~76% reduction in soil loss` / `~12% increase in yield` (one f-string; `goal_direction` keeps `reduce`/`increase`); `glossary.ts` `effectSentence` mirrors it for `en`; the three frontend fixtures (`glossary.test.ts`, `result-card.test.tsx`, `api.test.ts`) updated; the E2E flow asserts the API's own wording on the card and on the print sheet.
- **0c IBM Plex Sans self-hosted** (`src/app/fonts/IBMPlexSans-latin{,-italic}.woff2`, variable `wght`, latin) via `next/font/local` next to Noto Sans Ethiopic, both OFL licence texts committed (`LICENSE-IBMPlexSans.txt`, `LICENSE-NotoSansEthiopic.txt`), README updated. A production build makes no request to Google Fonts (verified: zero `fonts.gstatic`/`googleapis` references in the built CSS/HTML).
- **0d Mobile performance.** (1) The map is not mounted on phones until "Show the map" is tapped or a pin exists (`useIsPhone` on `matchMedia` through `useSyncExternalStore`; server snapshot "unknown" so hydration mounts nothing); (2) the Advisor's title, subtitle and stepper render before `/metadata` (they had been behind the metadata gate and were the LCP text); (3) per-route message splitting (`src/i18n/messages.ts`: the layout ships the shell namespaces, each page re-provides shell + its own — the home bundle carries < 50 % of the catalog); (4) phone map 14 rem, `keepBuffer=0`, `updateWhenIdle`; recharts stays lazy. Re-measured below.
- **1 Chat redesign** (`chat-panel.tsx`, `chat-quick-replies.tsx`, `lib/chat-protocol.ts`): message log (`role="log"`, polite live region) with role label + `<time>` per turn; explicit assistant states thinking → scoring → writing → done, or an error alert with "Send again" (re-sends the same message and hint); inline **`ContextCard` (compact) + `RecommendationPanel`/`ResultCard` + source badge** — the same component path as the Advisor; "Open in Advisor" deep link (`?lat&lon&family&indicator&crop&top`); quick replies as chips (challenge families, evidence-backed objectives, map / device location); map sheet kept (eager map inside the sheet); "New conversation". **Language-aware intent parsing (backend):** quick-reply chips send a sentence in the UI language **plus a structured `hint`** (additive `ChatSlotsHint` on `ChatRequest`), so the backend never guesses from translated text; typed protocol sentences in any language are parsed deterministically from the catalog templates (`parse_protocol`, reverse lookup through `family.*`, `indicator.*` and the new `indicator_label.*` terms); Amharic/Afaan Oromoo **free text** goes through one JSON-mode LLM reading (`app/services/intent_llm.py`, existing OpenAI client, `temperature 0`, `response_format json_object`) only when `OPENAI_API_KEY` is set, every value validated against the enumerations/bounds and place names resolved by the offline gazetteer; without a key a localised message (`clarify.use_advisor`) steers to the chips/Advisor. English stays on the rule parser and never calls the model. The chat protocol strings are now translated in am/om (`chat.protocol.*` ↔ backend `protocol.*`, equality asserted by `tests/test_i18n_sync.py`).
- **2 Printable advisory** (`advisor/print-sheet.tsx`, print CSS in `globals.css`): request, context table with units and meanings, every ranked practice with the model's effect sentence (API wording, am/om frame + original), confidence + meaning, field-observation count, the evidence-base line and the sources (ERA code · title · year · DOI/URL, guidance tagged), the source badge text, the model note, the disclaimer, the generation date and the share link as text. "Save as PDF" loads `/explain` first (promise-returning `load()` on the shared `ExplainProvider`, now lifted into `Results`), then `window.print()`; "Copy link" kept; app chrome and the interactive view are `no-print`.
- **3 Playwright E2E** (`app/frontend/e2e/`, `npm run e2e`; `playwright.config.ts`; system Chrome via `channel: "chrome"`, no browser download; `PLAYWRIGHT_CHANNEL=chromium` after `npx playwright install chromium` on CI without Chrome). API mocked in the browser from **fixtures captured from the real FastAPI responses** (`e2e/fixtures/*.json`: health, metadata, context, geocode, recommend, explain, chat-slots); OSM tiles answered with a 1×1 PNG. Specs: Advisor end to end in en/am/om; shared-URL scoring + reload; no-evidence and API-down states; axe-core on home, advisor step 1, results (en + am), chat, about (including colour-contrast); dark mode (OS preference + toggle + token check); print sheet; chat happy path with streamed answer, Open-in-Advisor link and timestamps; am chip → translated sentence + hint; failed stream → error + retry; map sheet; keyboard-only completion (skip link → fields → Next → cards → chips → score → `aria-live` announcement → visible 2 px focus ring); overflow at five widths; phone project (deferred map, tile failure keeps inputs usable, 390 px fit); documentation screenshots. `scripts/serve-standalone.mjs` (also `npm start`) serves the standalone build.
- **4 Translation review workflow.** `scripts/translation_status.py --export review.csv` (glossary terms first; columns `source,key,en,am,om,status_am,status_om`) and `--import review.csv` (writes am/om back into `messages/*.json`, `glossary.ts` and the backend catalogs — the `.py` catalogs are regenerated from their dict — and fingerprints every `reviewed` cell in `messages/review-status.json`). Guards: `src/i18n/review-status.test.ts` (UI + glossary) and `tests/test_translation_review.py` (backend) fail when a reviewed string changes without the workflow; `TRANSLATION_STATUS.md` shows `changed-since-review` for such rows. `protocol-en` no longer exists — the protocol strings are drafts like everything else.
- **5 Low-bandwidth.** Practice photos: blurred 16×9 SVG placeholder in the palette, lazy except the first card, text fallback with the practice name; `fetchWithRetry` (600 ms, 1.8 s backoff on network errors and 502–504, never on 4xx, never on the chat stream) for `/metadata`, `/context`, `/geocode`, `/recommend`, `/explain` with a warning-toned "retrying…" strip under the header (`retry-store.ts`); tile failure (`tileerror` without any `tileload`) shows a warning alert and the inputs keep working; the `/health` banner unchanged.
- **6 Docs.** `app/frontend/README.md` rewritten (screens, stack, scripts, tokens pointer, i18n workflow, E2E, low-bandwidth); root `README.md` quick start for the trilingual UI and the optional LLM key; `docs/design/design_system.md` (U2 additions + verification table); `docs/design/lighthouse/README.md` (U2 runs + U1 history); `app/backend/.env.example` documents what the key enables.
- Also fixed on the way: the Advisor auto-advanced to step 2 the moment a pin was committed (the E2E keyboard test caught it) — params updates now keep the current step unless the caller moves on; `CardTitle` takes `as` so the About page keeps a valid heading order (axe); the quick-reply protocol regex uses numeric groups for coordinates with a digit guard (the real chat fixture showed `lon=39` for "…39.37 and I want…"); backend `indicator.yield` was missing in am/om and the am `SOM content` noun differed from the glossary — aligned and now asserted.

**Files**
- New: `app/backend/app/services/intent_llm.py`, `tests/test_intent.py` (20 tests), `tests/test_i18n_sync.py`, `tests/test_translation_review.py`; `app/frontend/e2e/**` (6 specs, `support/api.ts`, `support/axe.ts`, 7 fixtures), `playwright.config.ts`, `scripts/serve-standalone.mjs`, `src/app/fonts/IBMPlexSans-latin{,-italic}.woff2` + two licence files, `src/components/advisor/print-sheet.tsx`, `src/i18n/messages.ts` (+ test), `src/i18n/review-status.test.ts`, `src/lib/chat-protocol.ts` (+ test), `src/lib/retry-store.ts`, `src/lib/client-value.ts`, `messages/review-status.json`, `docs/design/screenshots/u2-*.png` (6).
- Modified: `recommend.py` (effect sentence only); `app/schemas.py` (`ChatSlotsHint`, `ChatRequest.hint`); `app/routers/chat.py`; `app/services/{chat_service,slot_extraction}.py`; `app/i18n/{en,am,om}.py` (`protocol.*`, `clarify.use_advisor`, `indicator.yield`, `indicator_label.*`); `.env.example`; frontend `package.json`/lock (`@playwright/test`, `@axe-core/playwright`; scripts `start`, `typecheck`, `e2e*`, `i18n:status`), `.gitignore`, `messages/{en,am,om}.json` (+37 keys, protocol strings translated), `src/app/[locale]/{layout,page,advisor/page,chat/page,about/page}.tsx`, `globals.css` (print), `src/components/{chat-panel,chat-quick-replies,evidence-panel,location-map,practice-image}.tsx`, `advisor/{advisor-flow,location-step,results,context-card,recommendation-panel,result-card}.tsx`, `shell/{site-header,language-switcher,api-status-banner,site-footer,bottom-tab-bar,skip-link}.tsx`, `ui/card.tsx`, `src/lib/{api,types}.ts` (+ tests), `src/i18n/glossary.ts` (+ test), `src/lib/i18n-audit.test.ts`, `scripts/translation_status.py`, `src/app/fonts/README.md`, `rag/graph/test_glossary_sync.py` (indent regex), `docs/design/{design_system.md,lighthouse/*}`, `docs/i18n/TRANSLATION_STATUS.md`, both READMEs.

**Decisions**
1. **Structured hints over parsing translated chips.** A chip is structured input; sending the canonical values alongside the localised sentence (additive `hint`) is more robust than reverse-parsing Amharic. The deterministic protocol parser still exists for typed/pasted sentences in any language, and the backend/frontend vocabularies are forced identical by a test.
2. **LLM only for am/om free text, only with a key, never for numbers.** The extractor reads intent (enumerated values, a place name, coordinates, a crop); every output is validated and place names go through the gazetteer; English never touches it; without a key the user is steered rather than guessed at. Doctrines 1–3 untouched: engine, model, RAG, `explain_service.py` unchanged.
3. **One `/explain` per result** shared by the cards and the print sheet (`ExplainProvider` lifted into `Results`, `RecommendationPanel` `withProvider={false}` there; the chat keeps its own).
4. **E2E against the production build with mocked API** rather than the live backend: hermetic on Windows and Linux, no rasters, fixtures are real responses. Lighthouse, by contrast, is measured against the live backend on the shipped default API base.
5. **Review workflow fingerprints, not statuses in code.** `review-status.json` holds a hash per reviewed cell; the guards compare hashes, so a well-meaning edit cannot silently overwrite a native speaker's sign-off.
6. `next start` replaced by `scripts/serve-standalone.mjs` in `npm start` (`output: "standalone"` was never servable by `next start`); the Dockerfile is unchanged.

**Verified**
- Backend (owner's Windows venv, rasters present): `python -m pytest -q` → **140 passed, 1 skipped** (the skip is the review guard with no reviewed strings yet); `rag/graph/test_glossary_sync.py` 2 passed; `py_compile` on every touched file.
- Frontend (Windows node 24 from WSL): `tsc --noEmit` 0 errors (e2e included); `eslint .` **0 errors, 0 warnings**; `vitest run` **121 tests / 13 files** (adds retry/backoff, protocol+hint, message split, review guard); `next build --webpack` green.
- **Playwright E2E: 25 / 25 passed** (desktop 22, phone 3; the chat spec repeated ×3 after fixing a timing assumption) — flows in en/am/om, keyboard-only, overflow at five widths on nine screens, axe on six screens, dark mode, print, chat streaming/error/retry/hint, phone deferred map and tile failure.
- **Lighthouse 13.5, mobile, production build, live backend, two runs** (`docs/design/lighthouse/README.md`):

  | screen | Perf A / B | A11y | Best practices | LCP A / B |
  |---|---|---|---|---|
  | `/en/advisor` | **98 / 99** | 100 | 100 | 2.2 s / 1.8 s |
  | results URL | **97 / 83** | 100 | 100 | 2.3 s / 4.4 s |
  | `/en/chat` | **95 / 94** | 100 | 100 | 2.9 s / 3.0 s |
  | `/en` | **93 / 94** | 100 | 100 | 3.2 s / 3.0 s |

  U1 was 74 / 80 / 89 / 78 with Best practices 77–81. The results page's 83 in run B is the live `/recommend` call landing inside the simulated window (97 in run A); the honest ceiling and the remaining ~300 KiB of shared framework JavaScript are documented.
- Screenshots (`docs/design/screenshots/u2-*`): chat en light desktop, chat am dark phone, chat om light phone (each after a scored answer, inline cards), advisor results en light 390 px (0a proof), print preview en, advisor results en dark desktop.
- Translation status regenerated: 494 keys (320 UI, 60 backend, 114 glossary) → 988 am+om cells `machine-draft`, 0 reviewed; export/import round-trip exercised on a scratch CSV.
- Real-fixture capture doubled as an integration check: `/chat` with the hint-enabled schema, `/explain` grounded with 6 citations of both tiers, `/geocode`, `/context`.

**Needs local verification**
- Turbopack `npm run build` on Windows (the agent builds with `--webpack` from WSL) and `npm run e2e` from a Windows terminal with the owner's Chrome.
- The LLM extractor against the real API with a key (tests use a canned JSON reply): one Amharic and one Afaan Oromoo free-text message in the chat, checking the slots event shows `source: "llm"` and sensible values; rate/cost acceptable (one extra call per am/om free-text turn).
- A printed PDF from a real browser's print dialog (the E2E checks print-media rendering and content, not the dialog) — page breaks on a long Top-5 advisory.
- Native-speaker review of the 37 new keys and the translated chat protocol sentences via the CSV workflow.
- Lighthouse on a real low-end Android phone over 3G/4G (simulated figures above).

**Left for U3**
- The ~300 KiB shared framework JavaScript (Next/React/next-intl/Radix) if a hard ≥ 95 on the results page is wanted; server-rendering the chat shell.
- Amharic/Afaan Oromoo social-ack detection ("thank you") in the chat without a key; am/om examples on the chat landing.
- P9 source badges (Hybrid / Documented practice) and WOCAT records in the print sheet.

### Review (Senior Engineer) — U2 APPROVED ✅ (28 Oct 2026)
Independently re-verified in a clean sandbox from a snapshot of the working
tree:
- Frontend: `tsc` clean, `eslint .` 0/0, `vitest run` **121/121**. **`next
  build` (Turbopack) now succeeds offline** — the self-hosted fonts (0c)
  removed the Google Fonts dependency that blocked the sandbox build in U1.
- **Playwright E2E run here against the production build with the mocked
  API: 24 passed, 1 flaky** (the axe test timed out once and passed on
  retry and in isolation — add a `networkidle` wait before the scan). The
  sandbox needed a local config override to use its preinstalled Chromium;
  nothing in the repo changed.
- The four U1 must-fixes verified: 0a — overflow guard at 360/390/412/768/
  1440 px passes and the new 390 px screenshot fits; 0b — `recommend.py`
  emits "~76% reduction in soil loss" (one f-string, `goal_direction`
  untouched); 0c — IBM Plex Sans + Noto Sans Ethiopic self-hosted with both
  OFL licences; 0d — map deferred on phones, messages split per route,
  Lighthouse mobile 93–99 (owner's runs; the results page varies with live
  backend timing).
- Backend: explain/i18n/i18n-sync/intent/translation-review/slot suites
  **118 passed, 1 skipped, 1 failed here only because it runs a real
  recommendation and this sandbox has no rasters**
  (`test_chip_hint_completes_the_request_without_a_key`); the owner's 140
  with rasters stands. Minor: give that test the same "needs the raster
  stack" skip guard as `test_api.py`.
- Chat redesign, print sheet, language-aware parsing (LLM pass only with a
  key; localised steer without one), retry/backoff, translation-review
  export/import with fingerprint guards: present, tested, as briefed.

**One defect found in review (must-fix in the next UI-touching phase):**
the E2E fixture `e2e/fixtures/explain.json` contains mojibake
("Semiâ‐Arid", "â€¦") — the fixtures were captured from the real API on
Windows through a cp1252 console. The corpus itself is clean (the manifest
title reads "Semi‐Arid"), so this is a capture artefact, but it surfaced in
the print-preview screenshot. Fix: re-capture fixtures with explicit UTF-8,
and add an E2E guard that no rendered text contains `â€`/`Ã` sequences.
Owner: please confirm on the live app that Evidence-panel titles render
"Semi‐Arid" correctly (if not, the Windows backend has an encoding default
problem and we fix it there).

**Owner actions to close U2 (Windows):**
```
cd app\frontend ; npm ci ; npm test ; npm run lint ; npm run build ; npm run e2e ; cd ..\..
cd app\backend ; python -m pytest -q ; cd ..\..
git add -A ; git commit -m "U2: chat redesign, print/share advisory, Playwright E2E, self-hosted fonts, overflow/perf fixes, translation review workflow (reviewed)" ; git push origin main
```
Then a real print dialog on a long advisory and the LLM extractor with a key
(Amharic free text → slots), as the report requests.

### DECISION RECORD — WOCAT API Access Agreement v1.0 (14 Jun 2026) reviewed; data route and compliance (28 Oct 2026)
Document: `docs/WOCAT_API_Access_Agreement_SC_SU.docx` (University of
Bern/CDE for the WOCAT Secretariat). Reviewer's reading:
- **Data licence unchanged: CC BY-NC-SA 4.0** (Art. 2.1). The agreement
  only adds a cost-recovery model for the API infrastructure (Art. 4) and
  usage rules (Art. 5).
- **Tiers:** Public–Free (individual researchers/students: personal key,
  reduced rate limit, no SLA, USD 0); Public–Small/Standard/Large
  (USD 1,500 / 3,000 / 6,000 per year by institutional budget) + a one-time
  setup fee of CHF 4,000 for paid tiers; Commercial tiers need a separate
  commercial data licence (not our case — AgroAdvisor-ET is a free public
  good). **Exemptions:** free access under a Project Agreement whose budget
  includes WOCAT cost recovery (Art. 4.5); developing-country fee waiver for
  institutions on the OECD DAC list with public-interest SLM objectives,
  explicitly including "extension services reaching smallholder farmers"
  and "research with results shared freely" — but institutions developing
  products within donor-funded programmes are excepted (Art. 4.6).
- **Permitted Public Use** explicitly covers scientific research and
  publication, decision support, and "development of open-access tools and
  platforms that do not generate revenue" (Art. 3.1) — our use.
- **Binding restrictions (Art. 5):** no commercial use; **no redistribution
  of WOCAT data in raw form** (free or paid); keep attribution metadata;
  no credential sharing; no scraping/bulk techniques that circumvent rate
  limits; no derivative datasets that misrepresent origin/accuracy/
  currency. On termination, cached copies must be deleted (Art. 8.4).
- **Attribution (Annex A):** cite "WOCAT Secretariat (2025). WOCAT Global
  Sustainable Land Management Database … https://doi.org/10.48620/97493,
  CC BY-NC-SA 4.0" with source name, URL, licence statement and the
  month/year of retrieval.
- **API (v3, `wocat.net/api/database/redoc/`, token auth):** full QT
  records for Technologies (name, country, state/province,
  `location_geometry`, land use, water supply, SLM group/measures,
  degradation, establishment/maintenance activities + cost breakdowns +
  totals + currency, rainfall band + mm, agro-climatic zone, slopes,
  landforms, altitude zone, soil depth/texture/organic matter, water,
  biodiversity, land-user characteristics, tenure, access to services, all
  on-site/off-site impacts, climate-change coping, cost–benefit, adoption,
  adaptation, references, images, technical drawings, labels, funding);
  Approaches (stakeholders, decision-making, training, advisory,
  institutions, budget, subsidies/credit, impacts, sustainability); and the
  modules **CCA** (climate-change adaptation: exposure, thresholds,
  adaptation measures, costs, assets), **CBP** (carbon benefits
  assessment), **Gender** (gender-responsive SLM), plus UNCCD PRAIS
  archives, countries, institutions, labels, projects. Translation versions
  per language (not am/om).

Decisions:
1. **Route to access:** the owner applies now for a **Public–Free personal
   token** (email wocat.cde@unibe.ch with the WOCAT login e-mail and the
   purpose: non-commercial research + an open-access advisory tool; accept
   the agreement) — sufficient for ingestion (~2,700 requests once, then
   incremental refresh). **Before any public production launch**, the
   Alliance holds the licence: ask the WOCAT focal point (Job Kihara) for a
   partner/Project-Agreement arrangement (Art. 4.5) rather than paying the
   Public–Large tier; the developing-country waiver is unlikely to apply to
   an international organisation in a donor-funded programme.
2. **Architecture for compliance:** the app never calls WOCAT live. An
   **offline sync** (`fetch_wocat.py`, polite rate, incremental by
   `updated_at`) fills a **git-ignored** raw cache; the repo ships code, the
   list of record ids + access dates, and derived artefacts only; every
   record shown carries attribution + URL + access month/year; the Annex A
   citation appears in About, the print sheet and the manuscript's data
   availability statement; derived data released with the paper are
   CC BY-NC-SA 4.0; the token lives only in `backend/.env`.
3. **What we integrate, in order of value:** (a) Tier-3 practice records +
   graph enrichment (P6b-ii) — context-matched documented practices with
   activities, costs, adoption, strengths/weaknesses; the `location_geometry`
   of the ~102 Ethiopian records lets us compute OUR raster context for them
   (direct comparability, cross-country transfer by context class);
   (b) **implementation cost estimates** per practice (establishment +
   maintenance breakdowns, currency, year) — a capability the system lacks
   entirely today; (c) **CCA module** → a climate-resilience lens (which
   practices cope with drought/floods/heat); (d) **CBP module** → a carbon/
   mitigation lens (ratings with provenance, never model numbers);
   (e) **Gender module** → labour/benefit distribution notes (agroecology's
   social principles); (f) **Approaches** → implementation pathways for
   extension agents (training, incentives, institutions); (g) degradation-
   type → practice lookup beyond our 7 indicators; (h) an **Agroecology+
   profile** per practice derived from WOCAT impact variables mapped to the
   13 HLPE agroecology principles (qualitative, counts of records, with
   provenance) — a distinctive feature for the paper and the UI.
   Sequence: P8 (expert-study readiness) → **P6b-ii** (ingestion + Tier 3)
   → P9 (evidence-tiered advisory, uses Tier 3) → P6c (direction-agreement
   + graph ablation) → faithfulness run → expert study → manuscript.

### Next steps → Phase P6b-ii — WOCAT ingestion via the API, Tier-3 practice records, graph enrichment (assigned to Claude Code; runs once the owner has the token)
Read CLAUDE.md first, then the P6a/P6b-i reports and the decision record
above (the agreement's restrictions are binding). `WOCAT_API_TOKEN` is read
from the environment or `app/backend/.env`; never print or log it.
1. **Fetch — `rag/ingest/wocat/fetch_wocat.py`.** Auth header
   `Authorization: Token …`. `--inspect` first: fetch 3 technologies, 1
   approach, 1 cca, 1 cbp, 1 gender record and print the real key shapes.
   Then: list endpoints for technologies, approaches, cca, cbp, gender (+
   labels, countries, institutions, projects once), retrieve every record
   with `?language=en` (fallback: the primary language), store raw JSON in
   the git-ignored `rag/corpus/wocat/raw/<type>/<id>.json` with an
   `access_date`, and write `rag/corpus/wocat/manifest.jsonl` (id, type,
   name, country, state/province, lat/lon centroid from
   `location_geometry`, updated_at, access_date, url, licence) — the
   manifest is small metadata and may be committed. Polite client: ≤ 2
   requests/s, exponential backoff on 429/5xx, resumable, `--since` for
   incremental refresh by `updated_at`, `--limit` for tests. **No scraping
   of wocat.net HTML; the API only.** Report the funnel: records per type,
   per country (top 10 + Ethiopia), with coordinates, with each module.
2. **Adapter — `normalize_wocat.py` gains `WocatApiAdapter`** mapping the
   real fields onto `WocatTechnology`/`WocatApproach` (extend the schema
   additively for: lat/lon, land-user characteristics, cost breakdowns with
   currency/year, climate coping, modules `cca`/`cbp`/`gender` as optional
   sub-objects, images/technical drawings as URL lists). Map enumerations
   to the QT vocabularies (`VERYNEGATIVE…` → rating keys; adoption and
   cost–benefit enums; SLM measure/degradation codes); unknown codes are
   dropped with a warning, never invented. Output
   `rag/corpus/wocat/technologies.jsonl` + `approaches.jsonl`.
3. **Spatial enrichment (Ethiopia records):** for every record with
   coordinates inside Ethiopia, a script the owner runs calls the canonical
   engine's `extract_context(lat, lon)` (wrap, never fork) and stores the
   resolved context (AEZ belt + stack features) and the
   `context_to_classes()` output on the record (`context_source:
   "raster_stack"`); other records keep their QT classes
   (`context_source: "questionnaire"`).
4. **Graph:** `build_graph.py --wocat rag/corpus/wocat/technologies.jsonl`
   (+ approaches). New edge `LOCATED_IN` (Technology → AEZBelt, Ethiopia
   only). Synthetic fixture deleted; two real Ethiopian records become the
   test fixtures. Report node/edge counts and the crosswalk status
   (`MAPS_TO` only for validated rows — the owner's validation is now on
   the critical path).
5. **Text tier — `wocat_corpus`:** `chunk_wocat.py` (reuse `chunk_text`)
   over description/definition, activities, strengths/weaknesses, climate
   coping and comments; chunk ids `W_<id>_<nnn>`, metadata `tier:
   "practice"`, wocat_id, type, country, title, url
   (`https://wocat.net/en/database/technologies/<id>/`), compiler, licence
   `CC BY-NC-SA 4.0`, access_date, `era_code: null`. `build_index.py
   --collection wocat_corpus`; `index_tools.py list` must show era_corpus
   1,191 / guidance_corpus unchanged / wocat_corpus N.
6. **Retrieval + explain:** `default_practice_retriever()`; in
   `explain_service.explain()`, a Tier-3 step: `context_to_classes(resolved
   context)` → `similar_context_technologies(…, practice, k=3)` with
   **Ethiopia-first** ranking (then same agro-climatic zone), no synthetic
   records → a "PRACTICE RECORDS (cite as [W1], [W2]…)" prompt block with a
   structured facts line per record (activities with timing; costs with
   currency and year; adoption band; one strength, one weakness) plus the
   retrieved passages; system-prompt rule: practice records inform HOW and
   WHERE ELSE, never effect sizes. Guardrail: `allowed_numbers` extended
   with exactly the numbers in the facts lines (same rule as the evidence
   base); `[Wn]` markers stripped like `[Gn]`. Citations gain tier
   "practice" + url + attribution fields; the deterministic fallback never
   cites records. `/metadata` reports `practice_records_ready`.
7. **UI:** "Practice record" chips (secondary outline) in the Evidence
   panel; the "How to implement" panel shows the record's activities and
   costs (currency + year stated) with the attribution line and the
   access month/year; the print sheet and About carry the Annex A
   citation. Catalog keys for all three languages.
8. **Compliance docs:** `docs/decisions/wocat_data_use.md` (licence,
   agreement articles relied on, what is cached and where, refresh and
   deletion policy, attribution text, the manuscript's data-availability
   sentence). `.gitignore` for `rag/corpus/wocat/raw/`, `texts/`,
   `chunks.jsonl`.
9. **Tests:** adapter on the real fixtures, enum mappings, chunking,
   graph counts, explain block (whitelist exactly what is prompted;
   fallback excludes records; graceful no-op without the collection), UI;
   existing suites green. Also: re-capture the E2E fixtures in UTF-8 and
   add the mojibake guard from the U2 review.
10. Scope guard: Tier 1/2 corpora and collections untouched; the model
    and dataset untouched; the crosswalk gate unchanged; the token never
    appears in logs, reports or tests.
11. Append the phase report with the funnel counts and stop. The owner
    runs the fetch, the spatial enrichment, the index build and the graph
    build.

**Launch (repo root, after `WOCAT_API_TOKEN` is in `app/backend/.env`):**
`claude "Read CLAUDE.md, then progress.md. The latest '### Next steps → Phase P6b-ii' block is your task. Implement it exactly, verify as instructed, append your phase report to progress.md, and stop."`

**Order of launches from here:** P8 first (its brief stands above, "Next
steps → Phase P8"; launch line unchanged), then P6b-ii when the token has
arrived, then P9.

### Decision (owner + reviewer, 28 Oct 2026) — P8 split; product track first
P8 is not run as a phase. Its two user-facing items (per-study citation
numbering; Tier-2 chunk-quality filter + prune) move into P9 below; its
publication items (faithfulness audit dry run, expert-study protocol check)
move to a later "publication readiness" phase. Order now: **P9 → P6b-ii
(when the WOCAT token arrives) → P10 (production deployment: CI, Docker,
TLS, observability, backups) → publication readiness.**

Measured motivation for P9 (dataset v2, 35 challenge × objective cells):
2 cells have no field evidence at all (today an error), 14 more have
evidence but no practice with ≥ 3 studies and ≥ 10 observations, 19 have
at least one such practice. Roughly half of all possible requests are thin
or empty — exactly where knowledge sources must carry the advice.

### Next steps → Phase P9 — Evidence-tiered advisory: model-led / hybrid / knowledge-led (assigned to Claude Code)
Read CLAUDE.md first; then the decision record of 26 Oct (product
direction) and the P6b-i review. This phase changes the product's core
behaviour, so the doctrine is amended first and everything else follows it.

**A. Doctrine amendment (edit `CLAUDE.md`, doctrine 1 and 2; keep the
numbering):** *"The ML model owns every effect number. Knowledge sources
(retrieved guidance documents, WOCAT practice records, graph relations) may
PROPOSE practices with provenance, but never quantify an effect, a
percentage, a ranking score or a study count that the model or the dataset
did not produce."* and *"Cite or stay silent applies to every proposed
practice: a knowledge candidate without at least one citation is not
shown."* Record the amendment date and this phase id in the file.

**B. Evidence sufficiency (new `app/backend/app/services/evidence_service.py`).**
For a request (family, indicator, resolved context) and the engine's
candidate pool, compute from the knowledge graph (`evidence_summary`) per
candidate: `n_studies`, `n_obs`, `n_obs_in_belt` (observations whose AEZ
belt equals the user's belt) and `n_obs_in_zone` (same moisture class:
Dry/Moist/Wet × belt group — define and document the belt-grouping table
from the 12 belts), `corpus_status`. Decide the **mode** with documented,
config-driven thresholds (`app/config.py`, env-overridable, defaults
below; `docs/decisions/evidence_tiered_advisory.md` explains them and
shows the 35-cell table):
- `model-led` — at least one of the top-3 ranked candidates has
  `n_studies ≥ 3` and `n_obs ≥ 10`, AND at least one of the top-3 has
  `n_obs_in_zone ≥ 1`;
- `hybrid` — the engine returns a ranking but the condition above fails
  (thin evidence, or evidence only from other zones);
- `knowledge-led` — the engine raises its "No field evidence" error, or
  every candidate has `n_studies = 0` for this indicator.
Return a structured `evidence_sufficiency` object with the per-candidate
counts and the reason strings (catalog keys, not prose) so the UI can
explain the mode in all three languages.

**C. Knowledge candidates (same service).** Sources, in this order, all
WOCAT-independent now with the WOCAT slot wired:
1. **Graph relations:** practices of the same family that have evidence
   for OTHER indicators (via `related_practices` and the component layer);
   label `evidence_other_objectives`; support = which indicators and how
   many studies (counts only).
2. **Guidance documents (Tier 2):** retrieve `guidance_corpus` passages
   for the family × indicator × context query (reuse
   `build_query_text`, `k ≈ 12`); map practice mentions in the passages to
   the 44 components with the keyword table (import/extend
   `FAMILY_KEYWORDS` from `fetch_gardian.py` — wrap, never fork) and roll
   them up to components; label `documented_in_guidance`; support = number
   of passages/documents, each candidate carrying its passage citations.
   Apply the Tier-2 quality filter (item F) before this step so garbage
   never becomes a candidate.
3. **Practice records (Tier 3, WOCAT):** call
   `similar_context_technologies(context_to_classes(ctx), practice=None,
   k=5)`; label `documented_practice_record`; empty until P6b-ii — the code
   path, schema and UI must already handle it.
Rank candidates by support (distinct sources > distinct documents >
passages), de-duplicate by component, cap at 5. Each candidate: component
label (glossary key), the frozen practice strings it maps to (if any),
source labels, support counts, citations (title/url/era_code/doc id),
and a **deterministic template rationale** (no LLM) built only from
citation metadata — no numbers other than counts. An optional LLM
phrasing of the rationale goes through `explain_service`'s guardrail with
the counts whitelisted exactly as the evidence base is.

**D. API (wrap, never fork).** New `POST /advise` (`advisory_service.
advise()`): calls `recommender_service.recommend()` (catching the
no-evidence `ValueError`), computes B and C, and returns
`{mode, reasons, model: <the unchanged /recommend payload or null>,
knowledge_candidates: [...], evidence_sufficiency: {...}, language}`.
`/recommend` and `/explain` are unchanged. `/chat`'s slot flow calls
`advise()` and the narrative states the mode in plain words (catalog keys
per language; the English texts byte-identical where the mode is
model-led and no candidates exist, guarded by a test).

**E. UI.** The Advisor results view consumes `/advise`: the source badge
shows the mode (`Field-trial model` / `Hybrid` / `Documented practice`)
with the reason text; model cards as today; a new **"Documented
practices"** section (secondary-outline styling, never with an effect
number, each card listing its sources and a "Why this is suggested"
template line) shown in hybrid and knowledge-led modes; knowledge-led
mode replaces the current no-evidence error state. Chat renders the same
cards inline. Print sheet carries the mode and the candidates with their
sources. Three languages. E2E: the three modes against mocked `/advise`
fixtures (captured in UTF-8; add the mojibake guard from the U2 review).

**F. Quality items folded in from P8.**
1. **Per-study citation numbering:** group evidence passages per study in
   the prompt (`[1a]`, `[1b]` shown, cited as `[1]`), align the guardrail
   marker regex, `shape_citations` and the Evidence-panel chips, and the
   faithfulness auditor's marker mapping; Tier 2 keeps `[Gn]` per
   document; Tier 3 `[Wn]` per record. Tests for numbering, stripping and
   chip ↔ marker consistency.
2. **Tier-2 chunk quality:** `rag/ingest/quality.py` with a documented,
   tested `chunk_quality(text) -> {score, flags}` (alpha ratio, short-token
   share, caps share, digit share, mean word length, reference-list and
   table patterns), a `--min-quality` gate in `chunk_guidance.py`, and
   `rag/ingest/prune_collection.py` that deletes failing chunk ids from
   an existing Chroma collection and rewrites the chunks file (no
   re-embedding; `index_tools`-style safety). Calibrate on a labelled
   sample of 100 chunks written to `rag/ingest/quality_sample.csv`
   (owner spot-checks); target ≥ 95% precision on "garbage". Tier 1 is
   never filtered. Report the expected removal count; the owner runs the
   prune.

**G. Offline mode report (light, for the product and later the paper).**
`rag/eval/mode_report.py`: for all 35 cells × the 50 P3 scenario pins
(`rag/eval/queries_v2.jsonl` locations), call `advise()` and tabulate the
mode distribution, candidate counts per source, and a guard that no
knowledge-candidate rationale contains a number other than its counts.
Writes `rag/eval/results/mode_report.{json,md}`. Owner runs it (rasters).

**H. Tests and scope.** Unit tests for the mode rules on synthetic
graphs (every branch), candidate extraction from passage fixtures,
`advise()` with fake retrievers/graph (incl. the no-evidence path → 200 +
knowledge-led, never a 4xx), the LLM-free rationale has no stray numbers,
citation numbering, quality filter; UI tests + E2E; all existing suites
green. Scope guard: `recommend.py`, the model, the dataset, Tier-1 corpus
and `era_corpus` untouched; `/recommend` and `/explain` response shapes
unchanged (additive only).

**I. Report** with the 35-cell mode table, screenshots of the three modes
(en + am), the quality-filter funnel, and stop.

**Launch (repo root):**
`claude "Read CLAUDE.md, then progress.md. The latest '### Next steps → Phase P9' block is your task. Implement it exactly, verify as instructed, append your phase report to progress.md, and stop."`

## Phase P9 — Evidence-tiered advisory: model-led / hybrid / knowledge-led (28 Oct 2026)

**Built**

- **A. Doctrine.** CLAUDE.md §1–2 amended as briefed (knowledge sources may *propose* practices with provenance, never quantify; "cite or stay silent" now covers every proposed practice).
- **B. Evidence sufficiency** (`app/backend/app/services/evidence_service.py`, new). Per ranked practice: `n_studies`, `n_obs`, `n_obs_in_belt`, `n_obs_in_zone`, `aez_belts`, `corpus_status`, `belt_counts_exact`, `in_top3`. Zone = moisture regime × belt group (Berha/Kolla → lowland, Weyna Dega → midland, Dega/High Dega/Wurch → highland; e.g. `Dry-lowland`). Mode rules with config thresholds (`EVIDENCE_MIN_STUDIES=3`, `EVIDENCE_MIN_OBS=10`, `EVIDENCE_MIN_OBS_IN_ZONE=1`, plus `KNOWLEDGE_CANDIDATES_MAX=5`, `GUIDANCE_CANDIDATES_K=12`, `GUIDANCE_MIN_QUALITY=0.55`), reasons as catalog keys + params (`mode.reason.strong_evidence | thin_evidence | in_zone | other_zones_only | zone_unknown | engine_no_evidence | engine_unsupported | no_studies | graph_unavailable | no_candidates`). The graph had no per-belt observation counts, so `REPORTS_EFFECT` edges now carry `obs_by_belt` (`rag/graph/build_graph.py`), `evidence_summary` returns `obs_by_belt` + `belt_counts_exact` (`rag/graph/query.py`), and the store was **rebuilt** (720 nodes, 1 961 edges, 867/867 effect edges with counts summing to `n_obs`). A pre-P9 store degrades to presence-based in-zone counts flagged `belt_counts_exact: false`; no graph → model-led with `graph_unavailable`. Decision record: `docs/decisions/evidence_tiered_advisory.md` (rules, zone table, 35-cell table, calibration).
- **C. Knowledge candidates.** Three sources: graph relations (`evidence_other_objectives`, same family, evidence for other indicators, cited per study), guidance passages (`documented_in_guidance`: `build_query_text` reused, k=12, quality gate first, mentions mapped to the 44 components by `rag/graph/component_keywords.py` — 41 components keyworded, left word-boundary regex so "organic fertilizer" never fires inside "inorganic fertilizer", import-time drift guard against `FAMILY_KEYWORDS`/`CANONICAL_COMPONENTS`), WOCAT records via `similar_context_technologies` (`documented_practice_record`). Candidates are components of practices of the requested family, de-duplicated by component, ranked sources > documents > passages, capped at 5, each with a deterministic template rationale (counts only; `rationale_numbers_are_counts` guard) and numbered citations. A citation must carry an identity (ERA code, dataset `study_no`, URL, WOCAT id, DOI or title) or it is refused; a candidate without citations is dropped.
- **D. `POST /advise`** (`routers/advise.py`, `services/advisory_service.py`): `{mode, reasons, model, knowledge_candidates, evidence_sufficiency, context, language}`; `model` is the unchanged `/recommend` payload (null in knowledge-led); unsupported pairs and engine "No field evidence" return **200 knowledge-led** while `/recommend` keeps its 422. `/recommend` and `/explain` shapes unchanged (additive: `ExplainCitation.ref`, `MetadataResponse.advisory`). `/chat` calls `advise()`, emits an `advisory` SSE event (mode, reasons, candidates, sufficiency, context, resolved query) before `recommendation`; model-led narrative byte-identical (test), hybrid adds one sentence, knowledge-led streams a deterministic list.
- **E. UI.** Results consume `/advise`; `ModeBadge` (mode + reasons tooltip) replaces the static source badge; `ModeReasons` card and a secondary-outline **Documented practices** section (sources, support counts, "Why this is suggested", citation chips `[n]`/`[Gn]`/`[Wn]`, first six + "Show all", never an effect number) in hybrid; knowledge-led replaces the no-evidence error with an info panel + context + reasons + candidates; chat renders the same cards inline (hybrid under the ranking, knowledge-led turn without a ranking, "Open in Advisor" from the advisory's query, quick replies do not reappear); print sheet carries mode, reasons and candidates; Evidence-panel chips show `[ref]`; en/am/om keys added (32 + 3). E2E `advisory-modes.spec.ts`: three modes × en/am, chat hybrid + knowledge-led, print sheet, mojibake guard (`â€|Ã.`), screenshots.
- **F1. Per-study numbering.** `explain_service`: `study_key`, `group_chunks_by_study`, `shape_citations` one entry per study/document with `ref` and `n_passages`; prompt labels passages `[1a]/[1b]` and asks for `[1]`; guardrail regex `\[[GW]?\d+[a-z]?\]`; `[Gn]` per guidance document, `[Wn]` records; faithfulness auditor maps markers to study groups (`rag/eval/eval_faithfulness.py`).
- **F2. Quality filter.** `rag/ingest/quality.py` (`chunk_quality(text) → {score, flags, stats}`, `MIN_QUALITY=0.55`), `--min-quality` gate in `chunk_guidance.py`, `rag/ingest/prune_collection.py` (dry run by default, refuses `era_corpus`), calibration sample `rag/ingest/quality_sample.csv` (100 stratified chunks, hand-labelled: 58 garbage / 3 mixed / 39 ok).
- **G. `rag/eval/mode_report.py`** → `rag/eval/results/mode_report.{json,md}` (35 cells × 38 pins, per-cell mode counts, reason counts, candidates by source, rationale-number guard); `--guidance` run → `mode_report_guidance.{json,md}`.
- **H. Tests.** Backend: `tests/test_evidence_service.py` (mode rules every branch, zone parsing, counts fallback, candidate extraction per source, ranking/dedupe/cap, rationale guard, dataset-only citations), `tests/test_advisory.py` (advise with fakes, no-evidence → knowledge-led, no graph → model-led, chat events, narrative identity), `test_explain.py` (+7 numbering/auditor tests), `test_api.py` (+5: `/advise` identity with `/recommend`, unsupported pair 200 vs 422, bounds, metadata block, chat advisory). Graph: `test_component_keywords.py` (5), `test_graph.py` (+1 per-belt). Ingest: `test_quality.py` (9). UI: `mode-badge.test.tsx`, `knowledge-candidates.test.tsx`.

**Files** CLAUDE.md · backend: `app/config.py`, `app/main.py`, `app/metadata_service.py`, `app/schemas.py`, `app/i18n/{en,am,om}.py`, `app/routers/advise.py`*, `app/services/{advisory_service,evidence_service}.py`*, `app/services/{chat_service,explain_service}.py`, `tests/{test_advisory,test_evidence_service}.py`*, `tests/{test_api,test_explain}.py` · rag: `graph/{build_graph,query,test_graph}.py`, `graph/README.md`, `graph/component_keywords.py`*, `graph/test_component_keywords.py`*, `graph/store/graph.json` + `graph_report.json` (rebuilt), `ingest/chunk_guidance.py`, `ingest/{quality,prune_collection,test_quality}.py`*, `ingest/quality_sample.csv`*, `eval/eval_faithfulness.py`, `eval/mode_report.py`*, `eval/results/mode_report{,_guidance}.{json,md}`* · frontend: `README.md`, `e2e/support/api.ts`, `e2e/advisor-flow.spec.ts`, `e2e/advisory-modes.spec.ts`*, `e2e/fixtures/advise-{model,hybrid,knowledge}{,.am,.om}.json`*, `e2e/fixtures/{explain,metadata,recommend}.json` (re-captured, UTF-8), `messages/{en,am,om}.json`, `src/lib/{api,types}.ts`, `src/components/{chat-panel,evidence-panel}.tsx`, `src/components/advisor/{results,recommendation-panel,print-sheet}.tsx`, `src/components/advisor/{mode-badge,knowledge-candidates}.tsx`* (+ tests*), `src/components/advisor/source-badge.tsx` (removed, superseded) · docs: `docs/decisions/evidence_tiered_advisory.md`*, `docs/design/design_system.md`, `docs/design/screenshots/p9-{model-led,hybrid,knowledge-led}-{en,am}.png`*, `docs/i18n/TRANSLATION_STATUS.md` (regenerated). (* = new)

**Decisions**

1. **Mode distribution is hybrid-heavy under the briefed thresholds.** Over the 35 cells × 38 pins: model-led 281, hybrid 859, knowledge-led 190 (cells by dominant mode 9 / 21 / 5). The binding condition is the evidence depth of the engine's **own top 3**, not the zone: `thin_evidence` on 746 of 1 140 ranked advisories vs `other_zones_only` on 555. The ranking favours combination practices with few observations (at the demo pin, ECWM × soil loss ranks Mulch-Water Harvesting with 1 study / 3 obs while Physical SWC Measures has 19 soil-loss studies and is not in the top 3), so the demo cell itself is hybrid. I implemented the rule exactly as briefed and left the thresholds as settings; whether the "strong" test should look at the family's best-evidenced practice rather than the top 3, or lower `min_obs`, is the reviewer's call — the per-cell reason counts in the report give the data.
2. **Candidates stay inside the family** (components of the family's frozen practices); a practice from another family is never proposed. Citation numbering is global per response (`[n]` studies, `[Gn]` guidance documents, `[Wn]` records), one number per distinct source; studies outside the ERA corpus (no code, no title) are cited by their dataset id ("Dataset study #CSA_18") instead of appearing as anonymous "Untitled study" rows.
3. **Knowledge-led is reachable from chat and the API, not from the stepper.** The Advisor's objective step still offers only evidence-backed objectives (U2 decision), and a URL with an unsupported objective falls back to that step, so the five unsupported pairs never reach the results view; the E2E therefore mocks the knowledge-led answer onto the demo request (which is exactly what the backend returns when the engine has no evidence at a pin). Offering all seven objectives now that knowledge-led exists is a product decision I did not take.
4. **Quality gate calibrated at 0.55** after adding bibliography-initials and dot-leader cues to recover reference lists and tables of contents: precision 95.5 % strict (43/45; 100 % counting "mixed" chunks as removable), recall 72.4 % on the labelled garbage; expected removal **2 073 of 19 997 chunks (10.4 %)**, 1 455 of 1 459 documents keep ≥ 1 chunk. Not applied — `prune_collection.py` ran as a dry run only; the Tier-1 corpus is never filtered.
5. `/metadata.advisory.sources.practice_records` reflects the graph (true when non-synthetic Technology nodes exist — currently the P6b-i fixture records, which also yield the 38 `documented_practice_record` candidates in Livestock × income); `GraphQuery.has_practice_records()` added.
6. The mode report's guidance retrieval is opt-in (`--guidance`); the default run keeps the report reproducible without the Chroma index and a key.

**Verified**

- `py_compile` on every touched Python file. Backend (owner's Windows venv, rasters + model): **190 passed, 1 skipped**. `rag/graph`: 62 passed; `rag/ingest`: 26 passed; `rag/eval`: 13 passed.
- Frontend: `tsc --noEmit` clean, `eslint` clean (0 warnings), vitest **128 passed** (15 files), `next build --webpack` OK, Playwright full suite (desktop + phone projects, mocked API, fresh standalone build) **33 passed, 1 failed** — the failure was the very first navigation of the run (`page.goto … net::ERR_ABORTED` while the web server came up), the same test passes alone (1 passed) and in the two previous full runs; the three-mode spec `advisory-modes.spec.ts` (9 tests: 3 modes × en/am, chat hybrid, chat knowledge-led, screenshots) passes in every run.
- `/advise` fixtures captured from a backend started from this working tree (port 8001, stopped afterwards) in UTF-8 (`ensure_ascii=False`) at the demo pin, in en/am/om (the mock serves the am/om files when the request's `language` says so, so rationales and the knowledge-led copy are the backend's own in every language): water use efficiency → model-led (`strong_evidence`: drip irrigation 8 studies / 28 obs; `in_zone`: furrow irrigation 11 obs in Dry-lowland), soil loss → hybrid (`thin_evidence`, `other_zones_only`), income → knowledge-led (`engine_unsupported`); no `â€`/`Ã` anywhere in the fixtures or catalogs (E2E guard).
- Mode report: 35 cells × 38 pins = 1 330 advisories, 0 errors, rationale-number guard 0 failures in 5 207 candidates (table in `docs/decisions/evidence_tiered_advisory.md` and `rag/eval/results/mode_report.md`). A second run with `--guidance` (1 145 s) gives the same modes (retrieval never decides the mode) and 5 161 graph / 4 316 guidance / 38 record provenances; the quality-filter funnel measured on a 5-pin sample (`mode_report_guidance_sample.json`, 175 advisories, 144 with retrieval): 1 728 passages retrieved → 1 618 kept by the quality gate (110 = 6.4 % dropped at 0.55) → 948 mention a canonical component (58.6 % of kept).
- English model-led narrative byte-identical to pre-P9 (`test_chat_emits_the_advisory_event_and_keeps_the_model_led_narrative_byte_identical`); `/advise.model` identical to `/recommend` for the same request (`test_api`).
- Screenshots: `docs/design/screenshots/p9-{model-led,hybrid,knowledge-led}-{en,am}.png` (desktop 1280, full page, mocked API).
- Scope guard: `recommend.py`, the model, the dataset, the Tier-1 corpus and `era_corpus` untouched; `backend/.env` untouched; nothing committed.

**Needs local verification**

- Amharic / Afaan Oromoo copy for the 35 new keys is machine-drafted (TRANSLATION_STATUS regenerated: 554 keys, all still "machine-draft") — the native-speaker review workflow from U2 applies.
- `rag/ingest/prune_collection.py --apply` on the guidance collection (I only ran the dry run), then re-check `/explain` guidance citations.
- Threshold choice (Decision 1) and whether the stepper should offer unsupported objectives (Decision 3).
- Housekeeping: WSL `git status` fails on this checkout ("index uses extension … index file corrupt") while Windows git works — the index was rewritten by Windows git at 10:12; I did not touch it. A `uvicorn … --reload --port 8000` started from the owner's environment at 11:35 is still running (it reloads the P9 code; it answered one intermediate capture); the final fixtures and the explain fixture came from backends I started on port 8001 from this working tree, all stopped afterwards. The stray `3.4` file (a pip notice redirected by one of my commands) was removed; `docs/~$CAT_API…docx` is the owner's Word lock file.

## Phase U3 — Site redesign: four pages, clean standard layout (30 Oct 2026)

Owner request (direct, not from a Senior Engineer review): make the UI clean, modern and production-grade, with four pages (Home, About, Advisor, Chat), standard page width, a standard background, an agroecology image on the landing page, and redundant elements removed.

**Built**
- Shell: header with Home / Advisor / Chat / About (underline active state), language + theme controls, a "Get advice" button (lg+); phones get a hamburger disclosure menu (Escape closes) in place of the bottom tab bar. New deep-green footer: brand + attribution, Explore (four pages), Resources (About anchors), bottom bar with disclaimer, copyright, version; hidden on `/chat` (full-height app view).
- Tokens: white page background, `surface-2` band for alternating sections, theme-aware `band` footer colours, fixed `forest` scale for text over photos, display sizes `4xl`/`5xl`, `.container-page` (1280 px, 16/24/32 px gutters), `.eyebrow`; `inverse`/`outline-inverse`/`xl` button variants.
- Home: full-bleed hero on the terraced-highland practice photo with a forest scrim; evidence figures as one card overlapping the hero (4 figures: observations, studies, practices, belts; still live from `/metadata`); three-step "how it works" with connector; five challenge areas as photo cards linking to the Advisor with the family preset (compact rows on phones); closing CTA band.
- About: `PageHeader` band, main column (what it is, confidence levels, data sources as icon cards), sticky aside (authorship, licence, Advisor CTA).
- Advisor: title in a compact `PageHeader`; standard container; empty "Your request" summary hidden on phones until something is set.
- Chat: removed the empty bordered composer strip shown before the first message; composer bar now full width; second headline line in primary green.

**Removed as redundant**: bottom tab bar (`bottom-tab-bar.tsx` deleted); duplicated "Click the map…" hint under the map (now "No pin yet"); repeated footer column heading/link; family/objective counts in the figures strip; "Start with …" link text inside cards that are themselves links; floating Next.js dev badge (`devIndicators: false`).

**Files** `tailwind.config.ts`, `next.config.ts`, `src/app/globals.css`, `src/app/[locale]/{layout,page,about/page}.tsx`, `src/components/shell/{nav-items.ts,site-header,site-footer,page-header,api-status-banner}.tsx`, `src/components/home/{hero,trust-strip,how,families,cta-band}.tsx`, `src/components/advisor/{advisor-flow,location-step}.tsx`, `src/components/chat-panel.tsx`, `src/components/ui/{button,toast}.tsx`, `messages/{en,am,om}.json` (+6 keys: `nav.cta`, `footer.explore`, `footer.resources`, `home.cta.title`, `home.cta.body`), `e2e/advisor.phone.spec.ts`, `docs/design/design_system.md`, `docs/i18n/TRANSLATION_STATUS.md`, screenshots `docs/design/screenshots/u3-*.png`.

**Decisions**
1. Hamburger menu instead of the U1 bottom tab bar, per the owner's "standard site" request; the phone E2E now asserts the menu instead of the bar.
2. Hero and card images reuse the shipped practice photos (no new assets, no external fetches).
3. Unused catalog keys (`nav.bottom`, `home.trust.families/objectives`, `home.families.open`) left in place rather than deleted, to keep the catalog diff additive; safe to prune later.

**Verified**: `tsc --noEmit` clean; `eslint src e2e` clean (0 warnings); vitest 129 passed (15 files, incl. i18n hard-coded-string and catalog-parity gates). Visual check in the running dev server (Chrome via Playwright) at 1440 px and 390 px for all four pages, dark mode, Amharic, and the open phone menu; no horizontal overflow at 390 px.

**Needs local verification**: Playwright E2E suite not run (Playwright's bundled browsers are not installed here); `next build` not run (dev server was using `.next`). Amharic / Afaan Oromoo copy for the 6 new keys is machine-drafted.
## Phase U4 — Home: "Under the hood" architecture section (31 Oct 2026)

Owner request: explain on the home page how the ML model, RAG, the knowledge graph and the data sources work together, and show WOCAT and worldwide coverage as the future direction.

**Built** New `HomeArchitecture` section after "How it works": four layer cards in pipeline order (Geospatial context, Machine-learning ranking, Retrieval-augmented explanation (RAG), Knowledge graph), each with its role and its sources, joined by connectors on wide screens; a "The model owns every number" card stating doctrine 1 and the cite-or-fallback rule; a "What comes next" card with WOCAT practice records and worldwide coverage marked Planned. Step 3 of "How it works" now mentions the cited explanation. Challenge areas moved to a white background so sections keep alternating.

**Files** `src/components/home/architecture.tsx` (new), `src/app/[locale]/page.tsx`, `src/components/home/{families,cta-band}.tsx`, `messages/{en,am,om}.json` (+`home.architecture.*`, 25 keys; `home.how.steps.results.body` reworded), `docs/i18n/TRANSLATION_STATUS.md`.

**Decisions** The section carries no figures, so it cannot drift from the model or dataset. WOCAT and worldwide coverage are labelled Planned because the graph currently holds only fixture WOCAT records and the stack covers Ethiopia only.

**Verified** `tsc` clean, `eslint` clean, vitest 130 passed. Rendered in the dev server at 1440 px and 390 px (en) and 1440 px (am); no horizontal overflow.

**Needs local verification** Amharic and Afaan Oromoo copy is machine-drafted. Playwright E2E and `next build` not run here.
## Phase U5 — Advisor page redesign (31 Oct 2026)

Owner request: remove the "Your request" panel so the map gets the space, centre the map on Ethiopia, polish and standardise the page (type, blocks, buttons, solid background) and remove em/en dashes.

**Built**
- Layout: white header band (title, subtitle, "Start over" once anything is set) over a solid `surface-2` work area; every input step is one white panel with the same eyebrow ("Step n of 5"), heading, helper text and footer (Back left, primary action right) via new `step-layout.tsx`.
- Stepper: segmented progress bars per step with number, label and the value chosen there (belt, family, objective, crop); completed steps stay clickable. This replaces the summary rail (`summary-rail.tsx` deleted).
- Location: large map (up to 32 rem) with search, coordinates, "Use my location", belt status and Next in a side panel; with no pin the map fits the country bounds from `/metadata` (quarter-step zoom). Chat's map sheet keeps its compact layout.
- Challenge: photo cards (shared `FAMILY_IMAGES`) with a check and ring on the selected family. Objective: option tiles stating the direction (Increase / Reduce). Crop: same panel and footer.
- Results: practice cards put the photo beside the summary from md up; opened Why / Evidence / How-to panels span the card width on a tinted well.
- Dashes: all em/en dashes removed from the en/am/om catalogs (rewritten by hand in en; native separators in am/om; ranges now "to" / "እስከ" / "hanga"), the glossary, the print sheet, the result card and the evidence-base tooltip.

**Files** `src/components/advisor/{advisor-flow,step-layout (new),location-step,challenge-step,objective-step,crop-step,result-card,print-sheet,family-icons}.tsx|ts`, `src/components/advisor/summary-rail.tsx` (deleted), `src/components/ui/stepper.tsx`, `src/components/location-map.tsx`, `src/components/home/families.tsx`, `src/i18n/glossary.ts`, `src/lib/evidence-base{,.test}.ts`, `messages/{en,am,om}.json` (+`advisor.objective.increase/decrease`; 16 strings per language reworded), `docs/i18n/TRANSLATION_STATUS.md`.

**Verified** `tsc` clean, `eslint` clean, vitest 130 passed. Walked the whole flow in the dev server against the live backend at 1440 px (all five steps, pinned and unpinned map, results) and 390 px (location, objective, results); no horizontal overflow.

**Needs local verification** Playwright E2E (stepper markup changed; selectors use roles and catalog text, so they should hold) and `next build` not run here. Reworded am/om strings are machine drafts.
**U5 follow-up (owner feedback, 31 Oct 2026)** Advisor header band now uses a soft brand tint (`primary-soft`) with faint terrace contour lines and a compass icon tile, so it is distinct from the white site header and the grey work area; stepper inactive bars and circles switched to `surface` for contrast on the tint. Checked in light, dark and 390 px; tsc, eslint and vitest (130) pass.

## Phase U6 — Chat page redesign and voice (31 Oct 2026)

Owner request: a standard chatbot page with a designed background and layout, voice input in English, Amharic and Afaan Oromoo, the recommendation read back aloud, and a clean page.

**Built**
- Layout: full-height chat on a solid `surface-2` background; a slim toolbar (assistant identity, read-aloud toggle, New conversation); a centred 768 px conversation column; welcome view with icon, headline, three example cards and the map / location chips; one composer docked at the bottom at all times (mic, map pin, auto-growing input, Ask) with a one-line footnote. User messages are green bubbles on the right; assistant answers sit beside a leaf avatar on white cards with a Listen action and timestamp. The context chips (challenge, objective, crop) and the Top-N switch sit above the composer once there is a result.
- Voice input: mic in the composer; while listening the composer becomes a recording bar (pulsing mic, timer, live level meter or live transcript, Cancel and Done). The text lands in the composer for review; Enter or Ask sends it.
- Voice output: Listen / Stop on every finished answer; an answer to a spoken question is read aloud automatically; the toolbar toggle reads every answer. One speaker for the page (a new answer stops the old one). Spoken text is the assistant's own text with Markdown, citation markers and links removed; no word or number is changed (doctrine 1).
- Backend: `POST /speech/transcribe?language=` (raw audio body, no multipart dependency; English pinned, Amharic and Oromo steered by a prompt in that language), `POST /speech/synthesize` (MP3), `GET /speech/status` (free, cached probe of the configured models). `metadata.speech_ready` added. Settings `SPEECH_STT_MODEL`, `SPEECH_TTS_MODEL`, `SPEECH_TTS_VOICE`, `SPEECH_MAX_UPLOAD_MB` (documented in `.env.example`). Shares the chat rate limit; 503 without a key, 415/400/413 on bad uploads, 502 on upstream failure.
- Engine choice per direction and language (`src/lib/speech.ts`): server when `/speech/status` says the model is reachable, else the browser Web Speech API (SpeechRecognition with en-US / am-ET / om-ET; speechSynthesis with a voice for that language). No engine, no control: the mic or Listen button is simply not shown.
- Cleaned: the empty bordered strip, duplicate composers (hero and footer), the user avatar, and the lat/lon chips (the context card already shows them).

**Files** backend: `app/services/speech_service.py`, `app/routers/speech.py` (new), `app/{config,main,metadata_service,schemas}.py`, `tests/test_speech.py` (new, 14 tests), `.env.example`. frontend: `src/lib/speech.ts` (new), `src/lib/speech.test.ts` (new), `src/lib/api.ts`, `src/lib/types.ts`, `src/components/chat-panel.tsx`, `messages/{en,am,om}.json` (+`chat.voice.*`, `chat.footnote`; 16 keys), `docs/i18n/TRANSLATION_STATUS.md`.

**Decisions**
1. **The configured OpenAI project has no access to audio models.** `gpt-4o-mini-tts` and `tts-1` both return 403 `model_not_found` and the project's model list has no audio ids. Server speech is therefore off today (`/speech/status` → `{"stt":false,"tts":false}`) and the UI runs on the browser engines. Enabling audio models for the project (or setting `SPEECH_*_MODEL` to models it can use) switches it on with no code change.
2. Dictation, not auto-send: the transcript is placed in the composer so a misheard word can be fixed before asking.
3. `language` is passed to the transcription model for English only; Amharic and Oromo use a language prompt, because an unsupported language code would fail the request.

**Verified** Backend `py_compile`; full backend suite 204 passed, 1 skipped (incl. `test_speech.py` 14). Frontend `tsc` and `eslint` clean, vitest 133 passed. Live: `/speech/status` reports the missing model access correctly. Dev server (Chrome via Playwright, fake microphone): welcome view, listening bar, a full conversation against the live backend with Listen shown, dark mode, Amharic at 390 px; console clean; no horizontal overflow.

**Needs local verification**
- Real microphone and speakers, per language. Browser engines depend on the device: on this Windows Chrome there are English voices only, so Listen shows in English and is hidden in Amharic and Afaan Oromoo. Chrome's recognition is expected to handle am-ET; om-ET support is unverified and falls back to a clear "type your question" message.
- Amharic and Afaan Oromoo voice output needs a server voice. With OpenAI audio enabled, quality for Amharic and especially Afaan Oromoo must be judged by native speakers; Azure Speech (am-ET neural voices) or Meta MMS-TTS (has Oromo) are candidates if it falls short.
- Playwright E2E (selectors kept: Message textbox, Ask button, chat-status / chat-recommendation test ids) and `next build` not run here. New am/om strings are machine drafts.
**U6 follow-up (owner feedback, 31 Oct 2026)** (1) The chat toolbar is gone: the read-aloud switch sits in the composer beside the mic, and New conversation joins the context row above the composer (shown once a chat has started). (2) Hands-free voice: a recording ends by itself when the speaker pauses (browser engine: single-utterance recognition; server engine: level-based silence detection, 1.6 s pause, 8 s no-speech and 60 s caps), the transcript is sent at once with no review step, and the answer is read aloud when ready. Spoken questions carry a small mic mark. Done and Cancel remain as manual overrides; +1 key `chat.voice.autoSend`. Verified with a scripted recognizer in Chrome against the live backend: auto-sent, en-US recognition, answer handed to speech synthesis with its figures unchanged, Stop shown while speaking. tsc, eslint, vitest (133) pass.

## Phase U7 — Conversational chat, Afaan Oromoo voice, theme-script fix (31 Oct 2026)

Owner request: (1) fix the "Encountered a script tag while rendering React component" console error; (2) Afaan Oromoo speech, or say if impossible; (3) make the chat entirely conversational, no buttons or forms.

**Built**
1. **Script error.** The theme bootstrap moved from `next/script` (a client component, so React created the `<script>` in the browser) to a plain server-rendered `<script>` in `<head>`; its text lives in `src/lib/theme-script.ts` (a client module's exports reach server code only as references). The language switcher now does a full document navigation (`src/lib/hard-navigate.ts`): re-mounting the `[locale]` root layout client-side was the last place React created the script, and a fresh server render also brings the right `<html lang>` and fonts. Verified: console clean on load, client navigation, reload with dark mode, and a switch to Afaan Oromoo.
2. **Afaan Oromoo (and Amharic) voice, local.** Neither OpenAI audio nor any browser offers Oromo voices, so the backend gained an optional local provider (`app/services/local_speech.py`) on Meta MMS (CC-BY-NC-4.0): TTS `facebook/mms-tts-orm` / `-amh` (~145 MB each), STT `facebook/mms-1b-all` with the `orm` / `amh` adapters (~3.9 GB), recordings decoded with PyAV. Installed from the new `requirements-voice.txt`. Routing (`speech_service.provider`): local first for am/om, then OpenAI where the project has access; `/speech/status` is now per language and only offers local recognition once the recognizer is loaded or fully cached. The MMS voices have no digits in their alphabet, so `app/services/speech_numbers.py` spells every number out in Oromo or Amharic (integers to 999 999, decimals, %, mm, m, °C; Oromo prefix "%76") before synthesis: the spoken answer keeps every figure (doctrine 1). Amharic is romanized with `uroman` for the voice only. The UI speaks server audio sentence by sentence (first piece plays while the next is synthesized): a long Oromo answer now starts in about 5 s instead of 15 s. Models preload in a background thread at startup (`SPEECH_LOCAL_PRELOAD`).
3. **Conversational chat.** Removed the quick-reply chips (`chat-quick-replies.tsx` deleted), the map offer, the map sheet, the location chips, the setup line, the context chips and the Top-N buttons, and the map button in the composer. The assistant asks for whatever is missing in words; the backend clarifications now ask for "the nearest town or village, or coordinates" instead of a map pin and no longer say "use the choices below" or "use the form" (en/am/om; dashes removed there too). Answers are words plus one compact attachment (`components/chat/chat-evidence.tsx`): the ranked practices with the model's effect, observations and confidence, the evidence mode, documented practices named without effects (hybrid), and a link to the full analysis in the Advisor. Chat asks for the top 3 so the reply can name alternatives. Typing indicator with animated dots; Copy action beside Listen.

**Files** backend: `app/services/{local_speech,speech_numbers}.py` (new), `app/services/speech_service.py`, `app/routers/speech.py`, `app/{config,main,metadata_service}.py`, `app/i18n/{en,am,om}.py`, `requirements-voice.txt` (new), `.env.example`, `tests/test_speech.py` (36 tests), `tests/test_advisory.py`, `tests/fixtures/en_texts_pre_u1.json` (22 of 41 English entries re-snapshotted: only the intended wording changes). frontend: `src/app/[locale]/layout.tsx`, `src/lib/{theme-script,hard-navigate}.ts` (new), `src/components/theme-provider.tsx`, `src/components/shell/language-switcher{,.test}.tsx`, `src/components/chat-panel.tsx` (rewritten), `src/components/chat/chat-evidence.tsx` (new), `src/components/chat-quick-replies.tsx` (deleted), `src/components/advisor/objective-step.tsx`, `src/lib/{api,speech,speech.test}.ts`, `src/app/globals.css` (`--accent-text` #286FA3: the guidance badge measured 4.43:1 on the new surface-2 band), `messages/{en,am,om}.json`, `e2e/{chat,advisory-modes}.spec.ts`, `e2e/support/api.ts`, `docs/design/design_system.md`.

**Decisions**
1. MMS licence is CC-BY-NC-4.0: fine for this research software, not for a commercial deployment without another voice provider.
2. The English snapshot test (`test_i18n`) was regenerated deliberately for the conversational wording; the diff was checked entry by entry.
3. Language switch is a full page load (a deliberate trade for correctness: fresh `<html lang>`, fonts and theme script).

**Verified** Backend: py_compile; full suite 226 passed, 1 skipped. Frontend: tsc, eslint clean; vitest 134 passed; `next build --webpack` OK; **Playwright full suite 34/34 passed** (desktop + phone; new specs for the conversational flow in Amharic and hands-free voice, axe clean). Live backend: Oromo and Amharic synthesis return WAV (Oromo 2.7 s, Amharic 13 s incl. first load); an Oromo conversation in the browser shows Listen / Copy and plays the answer.

**Needs local verification**
- Oromo and Amharic speech **recognition** end to end: the 3.9 GB recognizer was still downloading (Hugging Face CDN stalls); `/speech/status` keeps `stt.am/om` false until it is cached, then a page refresh switches the mic to it.
- Native-speaker review of the Oromo / Amharic voices and of the number words (machine drafts).
- Observed, not changed: an Oromo request for reducing soil erosion near Debre Birhan was read by the intent LLM as water-use efficiency (backend `intent_llm`), worth a look in the next backend phase.
## Phase U8 — About page redesign (31 Oct 2026)

Owner request: remove the Authorship and Licence blocks, add a horizontal Contact section with m.tuse@cgiar.org, polish the page and its backgrounds.

**Built** Tinted hero (primary-soft with the terrace contour lines, now a shared `components/shell/contour-lines.tsx` also used by the Advisor) with the Advisor CTA; then alternating white / surface-2 sections: "What it is" with a field photo; "How to read confidence" as three level cards side by side (colour bar, outlined level pill, sentence); "Data sources" as four titled cards (WOCAT marked Planned); a full-width horizontal Contact band (mail icon, text, the address as selectable text, "Send an email" mailto button). Authorship and Licence removed (their catalog keys deleted); the footer's "Licence and data" link now reads "Contact" and points to `/about#contact`.

**Files** `src/app/[locale]/about/page.tsx`, `src/components/shell/{contour-lines.tsx (new),site-footer.tsx}`, `src/components/advisor/advisor-flow.tsx`, `messages/{en,am,om}.json` (−`about.authors`, −`about.licence`; +`about.contact.*`, +`about.sources.names.*`, +`footer.contact`), `docs/i18n/TRANSLATION_STATUS.md`.

**Decisions** The email is a code constant (`CONTACT_EMAIL`), not a catalog string, so it never gets "translated". Confidence pills are outlined on white: the amber pill on its soft fill measured 4.26:1 (axe).

**Verified** tsc, eslint clean; vitest 135 passed; `next build --webpack` OK; Playwright 34/34 (axe contrast clean on /en, /am, /om about); screenshots at 1440 px (light, dark, Amharic) and 390 px with no overflow; console clean.

**Needs local verification** New am/om strings are machine drafts.

### Review (Senior Engineer) — user-level review of P9 + U3–U8 + R1; owner decision: evidence fusion (1 Nov 2026)

**Scope.** Browser review of `localhost:3000` as a user (Chrome, 1280 px and 390 px; en/om/am; light/dark): Home, the full Advisor flow (Debre Birhan → Erosion & water → soil loss; Top 1 and Top 5; Why this? / Evidence / How to implement), Chat, About. Code review of P9/U3–U8 is still pending; this block covers behaviour and UX.

**Verdict.** The design is strong and the flow works end to end (geocode, pin, belt, context card, mode badge, reasons, Top-N, copy link, deferred map, dark mode, mobile layout, i18n key parity 413/413). It is not release-ready. Must-fix: Chrome auto-translate crashes the app (React `removeChild`); the header is transparent (`bg-surface/90` on `var()` hex tokens); the Evidence panel shows raw Markdown; citation labels collide across panels (`[G1]` = two documents) and a study is cited for the user's own rainfall; ranked and documented lists overlap and contradict each other; "How to implement" shows raw chunks (bibliography lines); guidance titles are PDF first-line text; CSA sources have no reference; chat ignored "acidic soil" and recommended drought-tolerant crops (~100%) to a teff grower.

**Owner decision (1 Nov 2026) — evidence fusion.** The system no longer treats the model as the only source of numbers. The best evidence for the user's context leads (model-led, study-led or documented); numbers reported by studies are allowed with provenance ("reported in study [n]"), shown as labels in Why/Evidence, print and on request in chat, while default answers stay in plain language. Recorded in `docs/decisions/evidence_fusion.md`; CLAUDE.md doctrine §1–2 amended; `evidence_tiered_advisory.md` marked superseded in part.

**Next steps.** Phase **U9 — Evidence fusion and user-review fixes**: implement `docs/briefs/U9_user_review_fixes.md` exactly (Parts A–E; Part F, the hero image, is deferred by the owner), verify as listed under Acceptance, append the U9 report here, and stop.

## Phase R1 — Rename to AgroEcoAdvisor (1 Nov 2026)

### Decision record (owner + supervisor + reviewer, 31 Oct 2026)
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

**Built** Display name `AgroEcoAdvisor` and tagline `AI-Powered Agroecology+ Solutions` (am: `በAI የተደገፉ የAgroecology+ መፍትሔዎች`, om: `Furmaata Agroecology+ AI irratti hundaa'an`, machine drafts) across the UI catalogs, header wordmark (tagline as a second line from lg), page titles (`AgroEcoAdvisor — <tagline>`, template `%s · AgroEcoAdvisor`), Open Graph metadata, footer (`© {year} AgroEcoAdvisor · Alliance of Bioversity International and CIAT`), print sheet, About; backend LLM persona and prompts (`advisor_agent.py`, `explain_service.py`), FastAPI title, model label, `recommend.py` docstring; User-Agents `AgroEcoAdvisor corpus builder (research use; mailto:{email})` and `agroecoadvisor/1.0`; `package.json` name `agroecoadvisor-frontend` (lockfile regenerated, name lines only); docs (README x3, design system, rag/graph README and docstrings, CLAUDE.md, research plan and manuscript skeleton with "Formerly AgroAdvisor-ET (renamed 31 Oct 2026)" and the new working title); `model/evaluate.py` title with `docs/reports/model_evaluation_report.md` regenerated from the stored `model_eval.json` (diff: the title line only).

**Before inventory** (`AgroAdvisor-ET` occurrences per file, outside history files):

| File | Count |
|---|---|
| CLAUDE.md | 3 |
| README.md | 2 |
| app/backend/README.md | 1 |
| app/backend/advisor_agent.py | 3 |
| app/backend/app/config.py | 1 |
| app/backend/app/routers/models.py | 1 |
| app/backend/app/services/explain_service.py | 1 |
| app/backend/recommend.py | 1 |
| app/frontend/README.md | 1 |
| app/frontend/messages/am.json | 7 |
| app/frontend/messages/en.json | 7 |
| app/frontend/messages/om.json | 7 |
| app/frontend/src/app/[locale]/about/page.tsx | 1 |
| app/frontend/src/app/globals.css | 1 |
| app/frontend/src/lib/i18n-audit.test.ts | 1 |
| app/frontend/src/lib/types.ts | 1 |
| docs/design/design_system.md | 1 |
| docs/reports/model_evaluation_report.md | 1 |
| model/evaluate.py | 1 |
| paper/manuscript/manuscript_skeleton.md | 2 |
| rag/graph/README.md | 1 |
| rag/graph/__init__.py | 1 |
| rag/graph/build_graph.py | 1 |
| rag/graph/schema.py | 1 |
| rag/ingest/fetch_papers.py | 1 |
| research_project_plan.md | 6 |

**Kept as is (per brief)** internal class `AgroAdvisor` (+ `CSAAdvisor` alias, `groq_agent` shim); the folder `agroadvisor-et/` in the research plan's tree and the P1 history row; `progress.md`, `SESSION_HANDOFF.md`, `MIGRATION_MAP.md`; corpus/index/graph store (diff empty); storage keys (`agro-theme`, `agro-locale`: no brand inside).

**Fixture** `tests/fixtures/en_texts_pre_u1.json` needed no regeneration: the brand occurs in none of the snapshotted deterministic texts, and `test_i18n` passes unchanged.

**Verified** py_compile on all touched Python; backend 226 passed, 1 skipped; frontend tsc, `eslint .` 0/0, vitest 135 passed, `next build --webpack` OK, Playwright 34/34. Final grep: zero `AgroAdvisor-ET`/`agroadvisor-et` outside history files, the two allowed folder/history lines and the "Formerly" lines; `AgroAdvisor` only as the internal class. Screenshots `docs/design/screenshots/r1-home-{en,am,om}.png`, `r1-header-390.png`.

**Needs local verification** Native review of the two tagline translations; renaming the GitHub repository and local folder is a later decision.

## Phase U9 — Evidence fusion and user-review fixes (1 Nov 2026)

**Built**

*A. Backend fusion* (`docs/decisions/evidence_fusion.md`, binding)
- `fusion_service.py`: one evidence bundle per shown practice: the model estimate (confidence, observations in zone, SE from the P7 out-of-fold RMSE), the study-level effects from the dataset (graph `REPORTS_EFFECT`, per-study SD), the match level (zone → belt group → moisture → other), the lead source (model-led when confidence is medium/high and ≥ 1 observation in the zone, else study-led when a matching study exists), disagreement (opposite sign or a gap > 25 points: the headline becomes a range) and the ≥ 80 % caution.
- Ordering: `ADVISORY_ORDERING=conservative|model` (default conservative, `bound = d·est − k·SE`, k = `CONFIDENCE_K_SD`). `/advise` fetches all practices, fuses, orders, trims; the engine's own items are returned unchanged in the fused order (wrap, never fork).
- Guard v2 (`explain_service.guard_v2`): sentence-level; model/study/context/count numbers allowed anywhere, a passage number only in the sentence that cites it; a count must have no unit after it; unsourced sentences are removed; too many removals fall back to the deterministic fused text. Numbers come back as provenance objects `{value, unit, source, ref, display}`.
- Two registers: `summary` (plain, no markers) and `evidence` (labelled, cited). Chat switches to the evidence register when the user asks why / for evidence, in en/am/om.
- Request fit: soil constraints from chat text (`acidic_soil` → pH Control, …); a constraint pick is added when nothing shown matches; replaces-crop note for drought-tolerant crops. The acidic-soil teff question (eval case C001) now parses to ISFM / yield / Teff / Bahir Dar / acidic soil.

*B. Must-fix defects*
- B1 `translate="no"` + notranslate meta; B2 header alpha (RGB-channel tokens); B3 Evidence renders Markdown, never literal `###`/`**`.
- B4 one citation registry per page (`citation-registry.ts`, `CitationsProvider`, `CitationsScope` for components outside a page provider), keyed by source identity; context-only sentences lose study markers; `[1a]` → `[1]`.
- B5 documented ∩ ranked = ∅.

*C. Source quality*
- C1 guidance passage filter (quality, English, region, relevance) and synthesised how-to steps (JSON LLM call + guard, cited `[Gn]`).
- C2 CGSpace titles, years and handle pages for guidance (background agent: `rag/ingest/backfill_guidance_metadata.py` → `rag/corpus/guidance/doc_metadata.json`; 1,248 of 1,459 documents resolved, all that have a DSpace link; 211 non-DSpace documents keep their content-head title).
- C3 dataset-study references (`pipelines/dataset/build_csa_references.py` → `data/processed/csa_study_references.json`; all 133 `CSA_*` ids mapped; ambiguous / truncated / short-form entries flagged per entry; unmapped ids cite the Adimassu et al. 2024 compilation with the study number).
- Wired through `source_meta.enrich_citation` in `shape_citations`, the fused study registry and documented candidates; identity fields never change, so registry labels stay stable. New fields `reference`, `reference_truncated`, `compilation`, `source_url` on both citation schemas; the UI shows the reference as the chip tooltip and in print.

*D. UI/UX*
- D1 card: plain headline from the bundle ("About 84% less soil loss" / range when sources disagree), one source chip (Field-trial model / Field study · your zone / similar area / similar rainfall), "Why this?" with labelled model and study values, disagreement note, 0-anchored dot-and-interval chart (hidden below 2 rows).
- D2 Top 3 by default; skeletons; top card's explanation prefetched; `/explain` cache per (locale, pin, family, indicator, crop, practices).
- D3 ICU plurals ("1 study", "1 field observation") in `messages/*.json` and backend `reason_text`; "Among the top-ranked practices, {practice} has the most evidence…"; the "clearly labelled, and never" comma.
- D4 zone names go through the glossary everywhere (belt names translated; the source chip names the match level instead of internal codes).
- D5 one confidence vocabulary: backend `fusion.confidence.*` = glossary labels (test enforces parity); the chat attachment shows the Advisor's headline and source chip from the bundles now sent on the chat `advisory` event.
- D6 print: Save as PDF waits for the evidence (prefetched anyway); fused headline + source label; registry labels; full study reference.
- D7 map: `isolate` stacking context (controls stay under the sticky header); `fitBounds(Ethiopia)` after `invalidateSize` on mount and on panel resize; tile provider configurable via `NEXT_PUBLIC_MAP_TILE_URL` / `NEXT_PUBLIC_MAP_TILE_ATTRIBUTION` (default OSM; `.env.example` documents a keyed provider).
- D8 the step heading is scrolled to and focused on every step change (reduced-motion aware); "Complete the steps above" replaces "four steps".
- D9 chat: the route is pinned to one viewport (no double scrollbar, also with the API banner); composer shows a scrollbar only past its height cap, placeholder stays on one line; compact welcome block at short heights; one visible author line; axe fixes (live log wraps the list, sr-only h1 once the conversation starts).
- D10 place name with coordinates ("Near Adama (8.38, 39.37)") from a new offline `GET /geocode/nearest` (gazetteer, none beyond 40 km); SOC unit g/kg; raw dataset labels removed under display names (card, documented card, print); chat lists documented practices by display name.
- D11 om/am leaks: no duplicated English headline in print; the engine's English note and ranking scope replaced by translated copy; practice display names inside am/om reason sentences (the reason dict keeps the frozen English string).
- D12 practice images resolve against the list of files on disk (no 404 requests): own photo, alias (Biological SWC practices → agronomic-biological-swcp), or the first illustrated component of a combination.
- D13 see Verified (Lighthouse, axe, layout shift).

*E. Copy and docs (en/am/om)*
- Home "Every number has a source" card and the architecture section; Advisor subtitle; About: "How the advisor decides" (model-led / study-led / documented / disagreement), confidence and sources updated, "Licences, privacy and citation" (data licences, voice privacy, version, how to cite), "bluffing" and the doubled "Thin evidence" removed; footer shows the build version (`NEXT_PUBLIC_APP_VERSION`, default package.json) and links to "How the advisor decides" / "How to cite"; mode tooltip no longer says "every number comes from that model".
- Docs: README.md, app/frontend/README.md, docs/decisions/rag_design.md (amendment note + guard v2 row), research_project_plan.md, paper/manuscript/manuscript_skeleton.md (working title and framing per decision §9), docstrings in explain_service.py, evidence_service.py, recommender_service.py, rag/graph/schema.py.

**Evaluation**

Mode report, 35 cells × 38 pins = 1,330 advisories, 0 errors, rationale-number guard failures 0 (`rag/eval/results/mode_report_u9_{model,conservative}.{json,md}`; run without guidance retrieval):

| Run | model-led | hybrid | knowledge-led |
|---|---|---|---|
| P9 baseline | 281 | 859 | 190 |
| U9, model ordering | 281 | 859 | 190 |
| U9, conservative ordering | 294 | 846 | 190 |

Fusion metrics over the shown practices:

| Metric | Model ordering | Conservative ordering |
|---|---|---|
| Lead source study / model | 1,973 / 991 | 2,273 / 691 |
| Disagreements | 1,238 | 772 |
| Mean studies per top-3 practice | 2.33 | 2.51 |
| Best-studied practice in the top 3 | 51.1 % (of 1,140) | 62.7 % |

Ordering comparison, pin by pin (`rag/eval/results/ordering_comparison_u9.json`, `rag/eval/compare_orderings.py`): 1,140 advisories compared, mean top-3 overlap 0.717, top-1 agreement 0.532; physical SWC measures in the soil-loss top 3: 0/38 (model) vs 13/38 (conservative). Mulch and Organic Fertilizer most often enter the top 3 under the conservative order; Water-Harvesting combinations most often leave it.

**Decisions**
- Conservative ordering is the default; `ADVISORY_ORDERING=model` restores the P9 order (both are reported).
- Cross-validated ranking metrics (P7 style) for the conservative order are not reported: the bound uses in-sample study evidence, so a CV score would leak.
- Display names replace raw dataset labels on screen and in print; the frozen names stay in the API and data.
- Map tiles stay on OSM by default so nothing breaks; production needs a keyed provider (OSM's tile policy).
- The C3 compilation fallback is Adimassu et al. (2024), *Farming System* 2(4) 100110 (the agent's choice, reasoning in `data/processed/README.md`): **owner to confirm**.
- `/advise` E2E fixtures recaptured from the current backend (`app/backend/scripts/capture_advise_fixtures.py`), so the mocked UI shows the fused cards.

**Files** (main)
- Backend new: `app/services/{fusion_service,numbers,practice_names,source_meta}.py`, `scripts/capture_advise_fixtures.py`; tests `test_fusion.py`, `test_guard_v2.py`, `test_chat_u9.py`, `test_guidance_quality.py`, `test_source_meta.py`, `test_source_titles.py`, `test_nearest_place.py`.
- Backend changed: `config.py`, `schemas.py`, `metadata_service.py`, `routers/geocode.py`, services `advisory`, `chat`, `evidence`, `explain`, `geocode`, `recommender`, `slot_extraction`; `i18n/{en,am,om}.py`; tests `test_advisory.py`, `test_api.py`, `test_explain.py`, `test_evidence_service.py`.
- Frontend new: `lib/{numbers,citation-registry}.ts` (+ tests), `components/citations.tsx`, `components/advisor/{evidence-why.tsx,use-place.ts,u9-acceptance.test.tsx}`, `lib/practice-images.test.ts`, `i18n/component-names.json` (+ practice-names test), e2e `axe-locales.spec.ts`, `u9-screenshots.spec.ts`.
- Frontend changed: result card, recommendation panel, results, knowledge candidates, evidence panel, print sheet, context card, advisor flow, step layout, location map, practice image, chat panel, chat evidence, site header, site footer, about page, glossary, types, api, `globals.css`, `next.config.ts`, `.env.example`, `messages/{en,am,om}.json`, e2e support and specs, recaptured fixtures.
- Data/RAG: `rag/eval/{mode_report,compare_orderings}.py`, `rag/eval/chat_eval.jsonl`, results above, C2/C3 sidecars and scripts.
- Screenshots: `docs/design/screenshots/u9/{home,about,advisor,chat}-{en,am,om}-{light,dark}-{390,1440}.png` (48).

**Verified**
- `py_compile` on every touched Python file; backend pytest **306 passed, 1 skipped**.
- Frontend: `tsc --noEmit` clean; `eslint .` 0 errors; vitest **264 passed**; `next build --webpack` OK.
- Playwright **46 passed** (desktop + phone; 12 opt-in screenshot tests skipped in the normal run), including axe A/AA + contrast on Home, About, Advisor results and an answered chat in **en, am and om, light and dark**.
- Lighthouse 12.8.2 (desktop preset, production build): accessibility **100** and best practices **96** on Home, About, Advisor results, Chat (en), Home (am) and About (om); performance 88–97. The remaining best-practices deduction is console errors from CORS: the audit server ran on port 3200, which the backend does not allow-list, so pages were audited with the API blocked. The same setup caused the Advisor's layout shift of 0.154 (the footer moves when the error state replaces the loading skeleton); elsewhere CLS is 0.037. The one real finding (brand link name ≠ visible text) is fixed.
- Local speech: the MMS recognizer download is now complete (blob SHA-256 verified, `asr_ready()` true). Round trip TTS → STT: Amharic returned almost verbatim ("ገለባ ሽፋን ያፈር መሸርሸርን ይቀንሳል"), Afaan Oromoo kept the key words with spelling drift ("haftii ruwwesuun dhiqama biyyee kerrisaa").

**Needs local verification**
- Native-speaker review of all new am/om copy (About sections, fusion strings, engine note, place labels); the D11 Amharic visual re-check is covered only by screenshots.
- Lighthouse with the API reachable (allow-list the audit origin or audit on port 3000) to confirm CLS < 0.1 on Advisor results.
- Data licences text (WorldClim, Copernicus DEM, FAO, CGSpace per-document licences) against the providers' current terms.
- C3: the compilation fallback, the 19 ambiguous and 36 truncated CSA references; 211 guidance documents still without CGSpace titles; no Crossref DOI lookup.
- A production map tile provider and key.
- Two stale partial downloads of the recognizer (about 2.4 GB of `*.incomplete` blobs in the Hugging Face cache) can be deleted by hand; they are not used.
- Nothing committed (the owner commits).

## Phase U9.1 — Advisor opens at the top, four steps, new hero image (1 Nov 2026)

Owner requests after the U9 review.

**Built**
- **Advisor opens at the top.** The U9 step-focus effect used a "first render" flag, which React Strict Mode (development) defeats by running effects twice, so `/advisor` jumped to "Step 1 of 5". The effect now compares with the previous step: the page load opens at the top like every page. On a real step change it focuses the heading and scrolls only when the heading is off screen.
- **Four steps for every challenge: Location, Challenge, Objective, Results.** The Crop step is gone. The optional crop picker now sits inside the Objective step and appears only for "Crop production and management". It lists the crops measured in that family: a new additive metadata field `crop_types_by_family` has 42 crops, without the livestock and land-cover labels of the global list of 80. Choosing an objective selects it, and an explicit "Get recommendation" submits, for every challenge. Switching to another challenge drops the crop. A crop that arrives in the URL (for example from a chat question that names one) is kept and shown in the stepper ("Increase crop yield · Teff"). Chat users can still name a crop in their question. The print sheet shows the crop row only when a crop is set.
- **Hero image (Part F, now requested by the owner).** `public/practices/hero_image.png` (1915×821) is optimised to `public/hero/agroecology-landscape.webp` (298 KB) and statically imported: known size (no layout shift), blurred preview, `priority`. The crop keeps the farmers and terraces in view on phones (`object-[78%_center]`), and the scrim is dense behind the text and clear on the right. The original PNG is left in place and is not served by any page.

**Files** `advisor-flow.tsx`, `advisor-state.ts` (+ new `advisor-state.test.ts`), `objective-step.tsx`, `crop-step.tsx` (deleted), `print-sheet.tsx`, `home/hero.tsx`, `public/hero/agroecology-landscape.webp`, `lib/types.ts`, `messages/{en,am,om}.json` (the "Crop" step label removed), e2e `advisor-flow.spec.ts` (new crop-field test, starts-at-top check) and `fixtures/metadata.json`; backend `recommender_service.py`, `metadata_service.py`, `schemas.py`, `tests/test_api.py`.

**Verified** backend pytest 306 passed, 1 skipped; tsc, `eslint .`, vitest 267 passed, `next build --webpack`; Playwright 47 passed (12 opt-in screenshot tests skipped). Screenshots of the Advisor on load (1440 and 390 px), the crop production Objective step and the new hero (1440 and 390 px) were reviewed by eye.

**Needs local verification** Crop names in the picker are the dataset's English labels in all three languages (data contract, as before). The U9 report screenshots in `docs/design/screenshots/u9/` predate these changes. Nothing committed.

## Phase U9.2 — Duplicate source key fix (1 Nov 2026)

**Problem** On `/en/advisor?lat=8.6577&lon=36.6616&family=Crop+production+and+management&indicator=yield&crop=Maize`, React reported two children with the same key (`G1-https://cgspace.cgiar.org/handle/10568/151652`) in a documented-practice card. The cause was a side effect of C2: several PDFs belong to one CGSpace item (12 handles are shared by 2–3 documents), and after enrichment they share its handle page. `_Candidate.add_citation` de-duplicated before enrichment, so both rows survived.

**Fix**
- Backend (`evidence_service.py`): enrich first, then de-duplicate by source identity. Guidance documents are counted per CGSpace item (its handle page), not per PDF.
- Frontend: `uniqueSources` and `sourceKey` (`lib/citation-registry.ts`). Every displayed list shows a source once and keys it by its identity: documented-practice chips, Evidence source lists, guidance snippets and both print lists. The explanation's citation list keeps both rows, because its text cites each by its own marker; the page registry already gives them one label.

**Verified** The reported request run in-process: hybrid, 4 documented practices, 0 duplicate sources in any card. New tests: backend `test_two_pdfs_of_one_cgspace_item_are_one_source`; vitest `uniqueSources / sourceKey` and "one chip per source" (no duplicate-key warning). Backend 307 passed, 1 skipped; tsc, eslint, vitest 269 passed, build OK, Playwright 47 passed. The running backend (`--reload`) and dev server pick the change up without a restart. Nothing committed.

## Phase U9.3 — Chat: wider, conversational, no evidence card (1 Nov 2026)

**Built**
- **Wider chat.** The conversation and composer are 64 rem wide instead of 48 rem (`max-w-5xl`).
- **No evidence card under answers.** The "Evidence behind this answer" card (ranking, chips, mode badge, documented list) is removed from the chat. The answer is the conversation; the ranking and its sources are one link away through a quiet "Open in Advisor" action beside Listen and Copy, which carries the resolved request. `components/chat/chat-evidence.tsx` is deleted, along with its unused `chat.evidence.*` and `chat.advisory.*` strings in en/am/om.
- **Evidence only on request, in prose.** When the user asks why or for evidence, the existing evidence register answers. It is now one short paragraph per practice plus one sentence naming the sources, with the same labelled values and markers: no bold headings, bullets or source list. The default plain answer is one paragraph too.
- **The AI writer talks, not lists.** `CONVERSATION_STYLE` is added to both narrative prompts: one or two short paragraphs, no lists, headings, tables or menus.

**Files** `components/chat-panel.tsx`, `components/chat/chat-evidence.tsx` (deleted), `messages/{en,am,om}.json`; e2e `chat.spec.ts`, `advisory-modes.spec.ts`, `axe-locales.spec.ts`, `screenshots.spec.ts`, `u9-screenshots.spec.ts`; backend `services/chat_service.py`, `tests/test_chat_u9.py` (prose and style tests).

**Verified** backend 309 passed, 1 skipped; tsc, eslint, vitest 268 passed, build OK; Playwright 47 passed, including axe on the answered chat in en/am/om, light and dark. A 1440 px chat screenshot was reviewed by eye.

**Needs local verification** The tone of LLM-written answers with the new style rule (it depends on the live model). The U9 report screenshots in `docs/design/screenshots/u9/` still show the earlier chat. Nothing committed.

### Review (Senior Engineer): roadmap approved, new data in place, next phase E0/E1 (10 Nov 2026)

**State.** U9, U9.1 to U9.3 and the AE+ Transform rename are deployed for the Sodo validation (agroecoadvisor.duckdns.org). The team discussion of 9 Nov is framed in `docs/roadmap/AE+_enhancement_roadmap.md` (approved by the owner on 10 Nov): one unified evidence store, problem-based challenges derived from the data, context as a vector with the belt as one attribute, a versioned geospatial pipeline refreshed on schedule, Methodology 1 (evidence model plus RAG) against Methodology 2 (LLM evidence reasoning) and their hybrid under one evaluation protocol, country as configuration, an Omo-Gibe Living Landscape overlay and a Methodology page. Phases E0 to E10 are listed there with acceptance criteria.

**New data in the repo (all git-ignored, never redistributed).** `data/raw/grist_habtamu/` (Habtamu Sewnet's extraction database: 1,617 rows, 47 columns, 605 study ids, 181 DOIs, 67 countries, no coordinates; profile in the roadmap section 1); `data/raw/catalogue/` (Agroecology+ Solutions Catalogue, 30 entries, docx); `rag/corpus/guidelines/` (62 government guidelines and manuals catalogued in `manifest.csv`, PDFs downloaded, README explains the tier); `data/raw/Typology/` and `data/raw/hotspot and coldspot/` (empty, Omo-Gibe rasters to come).

**Next steps.** Phase **E0/E1: contracts, unified evidence store, taxonomies and registry**: implement `docs/briefs/E1_evidence_store.md` exactly (Parts A to E), verify as listed under Acceptance, append the E1 report here, and stop. Additive only: the current dataset, model, engine and app keep working unchanged.

## Phase E0/E1 — Contracts, unified evidence store, taxonomies and registry (10 Nov 2026)

**Built** Everything in `docs/briefs/E1_evidence_store.md` Parts A to E, additive only.
- **E0 contracts.** Decision record `docs/decisions/enhancement_v2.md` (7 binding decisions, linked from CLAUDE.md "Read first"; the doctrine text is unchanged). Frozen evidence schema `pipelines/evidence/schema.py` (v1.0: Appendix A + `hlpe_principle`, `mfl_domain`, `extra`, plus `direction_reviewed` from C2; `validate`, `write_store`, `read_store`). `countries/ET.yaml` (active), `countries/KE.yaml` (draft), `countries/README.md`, and the validating loader `pipelines/common/country_config.py`. `data/taxonomy/README.md`. `.gitignore` now covers the store rows and the LLM cache.
- **E1 store.** Loaders `load_era.py` (all 14,792 rows and all 59 outcomes), `load_csa.py` (3,344) and `load_habtamu.py` (1,617), sharing `common.py`. `crop_lookup.py` and `reconcile.py`. `build_evidence_store.py` writes `data/evidence/evidence_rows.parquet` + `.csv` (git-ignored), `store_manifest.json`, `cards/{ERA,CSA,HAB}.md`, `README.md` and a one-screen summary.
- **Taxonomies.** `pipelines/taxonomy/{rules,seed,taxonomy_io,propose_mappings}.py` write `practices.csv` (151), `practice_aliases.csv` (397), `outcomes.csv` (130), `outcome_aliases.csv` (845) and `challenges.csv` (13). They also write the review sheets `review/HAB_practices_review.csv` (214 labels) and `review/HAB_outcomes_review.csv` (211 labels), with the top-3 rapidfuzz candidates, plus `review/practice_merges.csv` (28 proposals). Optional `--llm` mode (constrained, cached; fills `llm_suggestion` only) and `--apply-review`.
- **Catalogue.** `parse_catalogue.py` produces `data/taxonomy/catalogue_entries.{json,csv}`: 30 entries with name and category, normalised `key_problems`, and photo captions (taken from paragraphs and from the one table).
- **Registry.** `build_registry.py --country ET` writes `data/evidence/registry_ET.json`. Backend: `GET /registry?country=ET` (new router `routers/registry.py`, service `services/registry_service.py` with an mtime-checked cache, Pydantic models appended to `schemas.py`). Responses: 404 for an unknown country, 503 with the build command when a country is configured but its registry is not built.

**Files** New: `pipelines/requirements.txt`, `pipelines/conftest.py`, `pipelines/common/{__init__,country_config,test_country_config}.py`, `pipelines/evidence/{__init__,schema,common,crop_lookup,reconcile,load_era,load_csa,load_habtamu,parse_catalogue,build_evidence_store,build_registry}.py`, `pipelines/evidence/test_{schema,common,loaders,catalogue,registry,data_sources}.py`, `pipelines/taxonomy/{__init__,rules,seed,taxonomy_io,propose_mappings,test_propose_mappings}.py`, `countries/{ET.yaml,KE.yaml,README.md}`, `data/taxonomy/*` (incl. `crop_harmonisation.csv`, `review/`), `data/evidence/{README.md,store_manifest.json,registry_ET.json,cards/}`, `docs/decisions/enhancement_v2.md`, `app/backend/app/routers/registry.py`, `app/backend/app/services/registry_service.py`, `app/backend/tests/test_registry.py`, `app/backend/tests/fixtures/registry_TT.json`. Edited (additive): `app/backend/app/config.py` (EVIDENCE_DIR, COUNTRIES_DIR), `app/backend/app/main.py` (one router), `app/backend/app/schemas.py` (registry models), `CLAUDE.md` (one Read-first line), `README.md` (layout rows + one paragraph), `.gitignore`. Untouched: the dataset files, `model/`, `recommend.py`, `advisor_agent.py`, the rasters and the frontend.

**Decisions** (judgement calls; all are recorded in code docstrings and cards)
1. **CSA practice label.** The brief calls `CSA_practi` "the frozen label". However, the frozen `CSA_practices` values of the 1,414 CSA rows are the 20 `CSA_catago` categories, not the 338 `CSA_practi` names. `practice_raw = CSA_catago` (required by the contract and the reconciliation); `CSA_practi` is kept in `extra`.
2. **Two undocumented legacy rules, found by reconciliation.** (a) The merge-time deduplication (681 rows) ignored `Study_No_`: rows of *different* studies with identical site, practice, crop, indicator and ratio were collapsed, keeping the first. Deduplicating on all columns gives 7,264 ERA rows; on all columns except `Study_No_` it gives exactly 7,250. The ERA card lists the 15 cross-study collapses and the CSA card lists 31. (b) The CSA cleaning dropped the 110 in-scope rows with a blank `Crop_type`; the report says "blank -> Unspecified", but the frozen file has no `Unspecified`. Both rules are written into `reconcile.py` and the cards.
3. **Crop rule recovered as data.** `pipelines/dataset/` has no crop-group function to wrap: the harmonisation script is not in the repo. `crop_lookup.py` applies the documented scope and drop rules, which reproduce `ERA_Ethiopia_model_ready.csv` (7,827) and `CSA_practices_model_ready.csv` (1,518) row for row (asserted). It pairs each raw label with the harmonised value and asserts that the pairing is one-to-one, giving `data/taxonomy/crop_harmonisation.csv` (131 labels). Raw labels outside the lookup keep their name with `crop_group = null` (counted). The store's `crop` is the harmonised `crop_type`; `Product` and `Product.Simple` go to `extra`.
4. **Nothing dropped by any loader.** Rows the legacy model excluded stay in the store with `lrr` null or their own outcome. Exact repeats are flagged with `extra.dup_of`: 0 in ERA, 84 in CSA, 7 in HAB. The legacy rules are applied only in `reconcile.py`.
5. **ERA numbers.** SE, SEM and grouped SE are converted to SD with `sqrt(Rep)` (2,459 rows). CV and SED stay in `extra` (1,017). `Duration > 50` is set to null, since those are livestock days, not years (917 rows, raw value in `extra`). `outcome_raw` uses `Partial.Outcome.Name` only when it names a partial outcome ("Not assessed" counts as absent). `outcome_id` maps through the ERA outcome name (1:1 with `Outcode`). `yi` equals `ln(MeanT/MeanC)`; the comparison is in the card.
6. **Habtamu parsing.** A range is null for means and the midpoint for context, with the range kept in `extra`. `~`, thousands separators and `±` (first number) are parsed. `<0.05` is a bound and becomes null. `1,2` is never guessed. Quality mapping: Medium-High, Moderate-High and Moderate become Medium; shifted cells (years, scales: 41 rows) become NR with the raw value in `extra`. `year` comes from the `Study_ID` suffix first (publication year, Appendix A), else the last year of `Study_period`. Durations: seasons count 0.5 year, months 1/12; bounds such as ">15 years" become null. Multi-country values keep the first (flagged). `loc_precision = site` when `Agroecological_Zone` names a place; coordinates stay null. SEs are not converted for this source (the brief says "as given"). The two locator and evidence columns look partly swapped in the sheet; they are kept as specified and flagged.
7. **Directions.** Only the 7 legacy indicators are `frozen`, with directions from `recommend.DIRECTION` via `rag.graph.indicator_map.direction_map()` (wrapped, not copied). Every other outcome direction is a proposal: those rows carry `direction = null` and `direction_reviewed = false` and do not count in the registry.
8. **Taxonomy rules.** Rules extend `rag.graph.component_keywords` and never replace it: the base table wins on equal spans. Matching is leftmost-longest, a keyword must start a word ("ley" does not match "barley"), and bracketed text counts only as a fallback. Labels that negate a practice or name the comparator ("without compost", "conventional") are never rule-mapped. The first-mentioned-component rule has confidence 0.6. The `Deficit Irrigation` (ERA) / `Deficit irrigation` (CSA) id collision gives two source-suffixed ids plus a `same_practice` merge proposal. Catalogue technologies are new practices, each with a `narrower_than` proposal toward the frozen category. Nothing in the alias files is accepted (`accepted` empty everywhere).
9. **Challenges.** `challenges.csv` gains one column, `outcome_ids`: the exact objectives within the objective groups. Without it, every water outcome would be an objective of every water challenge. `catalogue_problem_terms` keeps only terms that occur in the parsed catalogue.
10. **Weights.** Inverse variance, capped at the 99th percentile (cap 39,681), applies to 3,598 rows. The other 16,155 rows get `factor x median inverse variance` (82.8), with factors High 1.0, Medium 0.8, NR 0.8 and Low 0.5. NR is treated like Medium because "not rated" is not evidence of low quality.
11. **Registry counting rule.** A row counts when it has country ET, a reviewed direction, a computable `lrr`, is not a `dup_of`, and has a practice family belonging to the challenge. `n_rows_pending_review` is added for information only and is never used for exposure. The backend reads the registry through new `EVIDENCE_DIR` and `COUNTRIES_DIR` settings (defaults `../../data/evidence`, `../../countries`).

**Verified** (owner's Windows machine, backend venv Python 3.11.9; pinned deps installed from `pipelines/requirements.txt`)
- `python pipelines/evidence/build_evidence_store.py` runs end to end: **19,753 rows** (ERA 14,792, CSA 3,344, HAB 1,617), 1,104 studies; `schema.validate`: **0 errors**. Coordinates 91.4%, `var_lrr` 18.2%, `lrr` 92.6%, reviewed direction 52.8%. By country: ET 18,294, CN 143, IT 142, ES 140, US 100 (+50 more). By family: ISFM 8,625, ECWM 4,403, CPM 3,485, LPM 1,408, FAF 1,186, unmapped (HAB in review) 646.
- **Reconciliation: EXACT.** ERA 7,250 of 7,250 and CSA 1,414 of 1,414: same `(study_id, practice_raw, Indicator, crop)` multiset, max |Δlrr| 8.9e-16 and 6.7e-16. Step tables are in the cards.
- **Habtamu:** 1,617 rows (none dropped); `lrr` 1,312; `var_lrr` **643** against the expected 646, because 3 rows have SD = 0 (explained in the card); Ethiopia 158 rows (129 with `lrr`); `.grist` MasterData (sqlite, read-only) has **1,617** rows.
- **Mapping coverage by rules (share of rows):** practices: ERA 100%, CSA 100%, catalogue 100%, HAB **60.0%** (971 of 1,617; just over the target, without padding the rules); outcomes: ERA 100%, CSA 100%, HAB 82.2%. Rows waiting in review: 646 (practices) and 287 (outcomes). Nothing is accepted automatically.
- **Catalogue:** 30 entries, consecutive numbers, each with a name and a category; key problems normalised.
- **Registry ET** (`registry_ET.json`, 9,757 counted rows, 131 practices; thresholds 30 rows, 5 studies, 3 docs):

| Challenge | Rows | Studies | Documented practices | Exposed | Rows pending direction review |
|---|---:|---:|---:|---|---:|
| SOIL_EROSION | 721 | 94 | 22 | yes | 10 |
| GULLY_EROSION | 666 | 80 | 8 | yes | 0 |
| SOIL_FERTILITY_DECLINE | 6,687 | 337 | 21 | yes | 829 |
| MOISTURE_STRESS_DROUGHT | 2,714 | 223 | 21 | yes | 1,105 |
| WATERLOGGING_EXCESS_RUNOFF | 620 | 75 | 10 | yes | 2 |
| LOW_CROP_PRODUCTIVITY | 8,184 | 338 | 0 | yes | 602 |
| FEED_SHORTAGE | 430 | 37 | 8 | yes | 817 |
| PESTS_AND_DISEASES | 0 | 0 | 0 | no | 14 |
| DEFORESTATION_FUELWOOD | 0 | 0 | 2 | no | 17 |
| DEGRADED_HILLSIDES | 666 | 80 | 1 | yes | 22 |
| LOW_INCOME_MARKET_ACCESS | 226 | 23 | 0 | yes | 1,531 |
| SOIL_ACIDITY | 0 | 0 | 0 | no | 8 |
| WATER_SCARCITY_IRRIGATION | 218 | 47 | 3 | yes | 950 |

  No challenge is "documented only" yet: the three unexposed ones have fewer than 3 catalogue entries, and guidelines arrive in E2. Today only the 7 legacy outcomes have reviewed directions; reviewing `outcomes.csv` (for example SOIL_ORGANIC_CARBON, SOIL_MOISTURE, GROSS_MARGIN) will bring in the pending rows.
- `GET /registry?country=ET` returns 200 with 13 challenges; KE returns 503 (configured, not built); FR returns 404.
- Tests: `python -m pytest pipelines -q` **145 passed**: 104 new (including the 4 data tests on the real files) plus the 41 existing `pipelines/dataset` tests. Backend `pytest -q`: **313 passed, 1 skipped** (309 before + 4 new). Frontend `vitest run`: **268 passed**. `python model/evaluate.py --quick` (outputs redirected to a temp folder) runs cleanly. `build_practice_family.py --dataset ... --out <tmp> --no-sync-copies` runs ("All ERA practices matched at least one keyword"). `py_compile` passes on every touched Python file. `git status` shows no change under `data/processed/`, `model/`, `app/backend/dataset/`, `recommend.py` or `advisor_agent.py`.

**Needs local verification**
- **Review sheets (Habtamu and the owner):** `data/taxonomy/review/HAB_practices_review.csv` (214 labels, 646 rows; largest: "Organic farming" 49, cover-crop and "regenerative" systems, biofertilisers, all with no canonical component yet) and `HAB_outcomes_review.csv` (211 labels, 287 rows). The rule mappings in both alias files (`method`, `confidence`; the 0.6 `component_primary` rows deserve a look). The direction proposals in `outcomes.csv` (`status = seed`, with notes on ambiguous ones such as ERA "Water Use" and labour). The 28 merge/parent proposals in `review/practice_merges.csv`.
- **Licences:** ERA (Dataverse terms) and the CSA compilation are tagged `ERA-Dataverse-terms` and `Adimassu-compilation-internal`; the owner to confirm. `data/taxonomy/catalogue_entries.*` holds partner catalogue text and is in git as the brief specifies; add it to `.gitignore` if it must not be redistributed yet. The review sheets also contain Habtamu's raw labels.
- **Not run:** Playwright (frontend unchanged; it needs the running app), `--llm` (it sends partner labels to OpenAI: the owner's call), and Python 3.12 (only the 3.11.9 backend venv exists here).
- **Deployment:** the backend container does not include `data/evidence/` or `countries/`, so `/registry` returns 404 there until both are mounted or `EVIDENCE_DIR`/`COUNTRIES_DIR` are set. Nothing else changes. Nothing committed.

### Review (Senior Engineer): E0/E1 APPROVED ✅; next E2 and E3 in parallel (10 Nov 2026)

**Verified independently** on the working tree: `evidence_rows.csv` has 19,753 rows with unique `row_id`; `lrr` equals `ln(mean_with / mean_without)` on all 18,294 computable rows (max error 8.9e-16); `direction_reviewed` true on 10,421 rows; Habtamu practice coverage 60.0% and outcome coverage 82.3% by rules; the taxonomy files, review sheets (top-3 candidates, nothing accepted) and `registry_ET.json` are as reported; `routers/registry.py` and `services/registry_service.py` follow the existing patterns (error envelope, mtime cache, 404/503 semantics); CLAUDE.md, config and main changes are additive. The reconciliation finding is accepted and important: the legacy merge collapsed 46 cross-study rows (15 ERA, 31 CSA) and dropped 110 blank-crop CSA rows; the new store keeps them, and the manuscript's data section will cite the cards.

**Decisions on the report's judgement calls.** All eleven are accepted as recorded, with two notes. (1) `CSA_catago` as the frozen CSA practice label is correct; the brief was wrong, and the roadmap text will say "the frozen `CSA_practices` labels" without naming a workbook column. (2) Default weights: accepted for E1; the weighting scheme is re-examined in E5 with the evaluation harness, where inverse-variance against quality-default weights becomes an ablation.

**Actions taken by the reviewer.** `data/taxonomy/catalogue_entries.{csv,json}` are now git-ignored (partner text, not yet cleared for sharing); the parser and its fixture tests stay. A first-pass review of the 123 proposed outcome directions is in `data/taxonomy/review/outcomes_direction_review.csv` (accept 103, flip 4, exclude 12 descriptors and blank labels, context-dependent 3 such as soil pH, merge 1; a `climate` objective group is proposed): the owner confirms by filling `accepted`, and E2 applies only confirmed rows.

**Owner decisions requested (in the E2 launch prompt).** (a) Allow `--llm` for the two Habtamu review sheets: the calls send only the raw intervention or outcome label and the candidate ids, never dataset rows; recommended yes, since the rapidfuzz candidates are weak for descriptive labels. (b) Confirm the licence tags for ERA and the Adimassu compilation. (c) Who reviews the Habtamu sheets: Habtamu for his labels, the owner for directions and merges.

**Carry-overs (not blockers).** Python 3.12 is the target in CLAUDE.md; the local venv is 3.11.9 and the server is 3.12, so the pipelines must stay 3.11-compatible until the venv is rebuilt. `/registry` on the validation server works after `git pull` (registry and countries are in git) with no extra setting; the Docker compose file is not maintained and stays out of scope. 60 of 130 outcomes sat in `objective_group = other`; the review sheet regroups them.

**Next steps.** Two phases, independent, may run in parallel in separate Claude Code sessions or one after the other: **E2: reviews applied, geocoding, guidelines and catalogue in the knowledge layer** (`docs/briefs/E2_knowledge_and_geocoding.md`) and **E3: geospatial context v2** (`docs/briefs/E3_geodata_v2.md`). Each: implement exactly, verify as listed under Acceptance, append its report block here, and stop. E4 (evaluation harness) follows both.

## Phase E2 — Reviews applied, geocoding, guidelines and catalogue in the knowledge layer (10 Nov 2026)

**Owner decisions (launch prompt, confirmed in session).** `--llm` allowed for both jobs (mapping proposals and site extraction). Licence tags kept (`ERA-Dataverse-terms`, `Adimassu-compilation-internal`). The review sheets have no accepted rows yet, so the appliers were built, tested and run with 0 rows applied. GeoNames was downloaded and papers fetched in this session; the owner installs Tesseract. Unpaywall/OpenAlex/Crossref were contacted with the owner's address for this run only (not stored).

**Built**
- **A. Reviews.** `pipelines/taxonomy/review_apply.py`:
  - `--apply-outcome-review [SHEET]` applies accepted rows only: `accept`/`flip` → direction, group, `reviewed`; `exclude` → `excluded`; `context_dependent` → no direction, note kept; `merge_into` → aliases moved, `merged`.
  - `--apply-review` ingests the Habtamu sheets (an existing id, or `NEW:<ID>` to create a practice or outcome) and `practice_merges.csv` (`same_practice` moves aliases and sets the merged id to `merged`; `narrower_than` records the parent).
  - Reviewer and date go into `notes`. Applied rows are protected from re-seeding: any status other than `seed`, or an alias with a reviewer.
  - Schema v1.1: `climate` objective group plus the three new statuses. `SCHEMA_VERSION = "1.1"` is in the manifest.
  - The seed id `MEAN_TREE_HEIGHT_DIFFERENCXE` is renamed to `TREE_HEIGHT`; the old id is recorded in the alias `notes` and the outcome notes.
  - The registry gains a before/after diff, and its pending count leaves out excluded, context-dependent and merged outcomes. The alias files gain an optional `notes` column.
  - A3 LLM: the prompt lists the top-10 candidates with names and components, plus `NEW`; model `gpt-4o-mini` (the backend's fixed model) recorded per cache line; requests run concurrently with retries.
- **B. Geocoding.**
  - `pipelines/evidence/fetch_habtamu_papers.py` wraps `fetch_papers.acquire`, reuses files by DOI, records the download URL, and finds DOIs by Crossref author + year search when the first author's family name, the year and two title words all match. It writes HAB rows to `rag/corpus/manifest.jsonl` (existing rows gain `source: ERA`) and `data/evidence/review/habtamu_papers_missing.csv`.
  - `pipelines/evidence/geocode_sites.py`:
    - Extraction: a regex pass for decimal and DMS coordinates (non-overlapping) and site sentences, plus a constrained LLM JSON extraction (cache `review/geocode_llm_cache.jsonl`, git-ignored).
    - Hallucination guard: an LLM-stated coordinate counts only if the regex finds it in the text (within 0.05°) inside the country bbox; a quote is marked verified only if it occurs verbatim in the text.
    - Resolution: GeoNames (`ET.txt`, `cities500.txt`, classes P/A). Matching is exact, else fuzzy (85, or 92 for short names), and a fuzzy match is rejected when the named admin units disagree. Fallback: the named admin units, then the exact tokens of the sheet's zone text, at `district` precision.
    - Outputs: review sheet, Leaflet map, and `--apply-geocoding` → `data/evidence/hab_geocoding.csv`, which `build_evidence_store.py` applies. Unchecked rows are `geocoded_llm_unchecked`; rows marked `accepted = yes` become `geocoded_llm_checked`. The download manifest is `pipelines/evidence/geonames_manifest.json` (CC BY 4.0).
- **C. Guidelines (Tier 2b).**
  - `rag/ingest/ingest_guidelines.py`: `pdftotext -layout` page split, the brief's image-page rule, OCR via pypdfium2 + Tesseract (eng/amh when installed, otherwise pages are listed as pending), language detection, and page-level chunks.
  - Chunking reuses `chunk_text` and the Tier 2 quality gate; there is no keyword filter or per-document cap, because these are curated documents. Chunk id `GL_<doc>_p<page>_<i>`, `tier = guidelines`, citation label.
  - `build_index.py` additively stores `doc_id, page, language, theme, publisher, citation` when a chunk has them, so Tier 1/2 metadata are unchanged.
  - New Chroma collection `guidelines`; Tier 1 and Tier 2 are untouched.
  - `rag/retrieve.py`: tier tag on every hit; `TieredRetriever` fuses the tiers by the same RRF; `RAG_GUIDELINES_ENABLED` (default true).
  - Backend: `get_guidance_retriever()` returns Tier 2 fused with Tier 2b, or the identical Tier 2 object when disabled or not built. Guideline pages share the `[Gn]` numbering and are cited "MoA 2016, Guidelines …, p. 34" in citations, the how-to passages and knowledge candidates. The numeric guard is unchanged.
  - C4: `pipelines/taxonomy/extract_suitability.py` (rules only) → `data/taxonomy/review/suitability_review.csv`. Nothing is applied.
- **D. Graph.**
  - `rag/graph/schema.py` (v `e2.1`, additive): `Challenge` and `CatalogueEntry` node types, `GuidanceDoc` with required attributes; `ADDRESSES_PROBLEM`, `DESCRIBED_BY`, `DOCUMENTED_IN`, `SUITABLE_IN` edges; provenance `catalogue`, `guidelines_title_match`, `catalogue_text`.
  - `rag/graph/knowledge_layer.py` is called from `build_graph.main`; `build()` without the new argument builds exactly the P6a graph, so the fixture tests are unchanged.
  - The catalogue's 30 canonical practices are Practice nodes with `origin = catalogue`, `n_rows = 0` and no `COMPOSED_OF`/`IN_FAMILY` edges, so the candidate pool and ranking never see them.
  - `rag/graph/query.py` gains `practices_for_challenge` (catalogue links plus field evidence on the challenge's legacy objectives), `documents_for_practice` and `catalogue_entry`.
  - The evidence service attaches `catalogue` and `guideline_docs` to knowledge candidates; both are new optional fields in `schemas.py`, and citations gain `page`/`doc_id`/`language`.

**Files** New: `pipelines/taxonomy/{review_apply,extract_suitability,test_review_apply}.py`, `pipelines/evidence/{fetch_habtamu_papers,geocode_sites,test_geocode,test_data_e2}.py`, `pipelines/evidence/geonames_manifest.json`, `rag/ingest/{ingest_guidelines,test_ingest_guidelines}.py`, `rag/test_retrieve_tiers.py`, `rag/graph/{knowledge_layer,test_knowledge_layer}.py`, `app/backend/tests/test_guidelines_e2.py`, `rag/corpus/guidelines/ingest_report.md`, `data/evidence/review/{geocoding_review.csv,geocoding_review.html,habtamu_papers_missing.csv}`, `data/evidence/hab_geocoding.csv`, `data/taxonomy/review/suitability_review.csv`. Edited (additive): `pipelines/taxonomy/{propose_mappings,seed,taxonomy_io}.py`, `pipelines/evidence/{schema,build_evidence_store,build_registry}.py`, `pipelines/evidence/test_schema.py` (version 1.1), `pipelines/requirements.txt` (+ pypdfium2 4.30.0, pypdf 6.21.2), `rag/retrieve.py`, `rag/ingest/build_index.py`, `rag/graph/{schema,build_graph,query}.py`, `rag/corpus/manifest.jsonl` (+605 HAB rows, `source` on all), `rag/corpus/guidelines/README.md`, `app/backend/app/{config.py (RAG_GUIDELINES_ENABLED, RAG_GUIDELINES_CHUNKS_PATH), schemas.py}`, `app/backend/app/services/{explain_service,evidence_service}.py`, `data/taxonomy/README.md`, `.gitignore` (geocode LLM cache, GeoNames cache, guideline chunk mirror). Rebuilt: the store, cards, `data/evidence/README.md`, the registry, `rag/graph/store/*`, the Chroma collection `guidelines`. Untouched: `recommend.py`, `advisor_agent.py`, `model/`, the dataset files, the frontend, and the `era_corpus` and `guidance_corpus` collections.

**Decisions**
1. **Merge gated too.** The `SOIL_INFLITRATION_RATE_TRATION_RATES` merge is a `merge_into` row of the sheet, so it waits for the owner's tick like every other row. The `TREE_HEIGHT` rename is applied because the brief orders it.
2. **Guideline chunking.** The Tier 2 keyword filter and 25-chunk cap are not applied to guidelines (curated, on-topic; the cap would drop most pages); the quality gate is (for English text). One citation per guideline *page*: grouping by URL would merge every page of a document into one reference.
3. **OCR.** `pdftotext -layout` (Git's xpdf 4.06) extracts the four documents the 10 Nov check flagged (Soil Matters 300k characters, CBPWD Part 1A 222k, Runoff Analysis 129k, Irrigation Agronomy 755k), so no document needs whole-document OCR. The remaining image pages are covers and figures. pypdfium2 (Apache/BSD) renders them, not PyMuPDF (AGPL).
4. **Graph.** Catalogue entries are linked to frozen practices through the E1 `narrower_than` proposals (`DESCRIBED_BY relation = narrower_than`, carrying the review state); a `no` in the merge sheet removes the link. `practices_for_challenge` adds field-evidence practices, because several exposed challenges (low crop productivity, low income) have no catalogue terms. `SUITABLE_IN` expands a bare belt name to its moisture variants present in the graph; "all agro-ecologies" maps to every belt (`rule` attribute).
5. **Geocoding rules (anti-hallucination).** LLM coordinates must be confirmed by the regex in the text. A fuzzy name needs admin agreement when admins are named (this removed "Nairobi" → Ethiopian "Ail Robi", "Kenna" → a Gambela "Kena", "National" → "Āt’ī’ona"). The zone-text fallback is exact only, at district precision. No numbers from dataset rows are sent; Supporting Evidence sentences are used by the regex but not sent to the LLM.
6. **DOI search.** A Crossref author + year search is accepted only on family name, year and two shared title words (14 DOIs found), each tagged `doi_source = crossref_author_year_search` with the matched title for the reviewer.

**Verified** (Windows, backend venv Python 3.11.9)
- **A.** 0 of 123 outcome-review rows, 0 of 425 Habtamu sheet rows and 0 of 28 merges accepted, so 0 applied. The registry diff shows every challenge unchanged (rows and pending equal). Store rebuilt: **19,753 rows, schema 1.1, 0 validation errors**; reconciliation still exact (ERA 7,250, CSA 1,414). LLM proposals: 214 practice labels (212 `NEW`, agreement with rapidfuzz top-1 0.5%) and 211 outcome labels (189 `NEW`, agreement 3.3%). The low agreement is expected: rapidfuzz top-1 candidates for descriptive labels are weak (for example "Whole soil N": rapidfuzz `SOIL_PH`, LLM `SOIL_TOTAL_NITROGEN`).
- **B1.** 605 studies; 581 with a DOI (567 from the sheet, 14 by search), 171 unique DOIs; **open-access full text for 53 of 171 unique DOIs (31%)**, 175 of 581 studies. This is slightly below the brief's "a third to a half". 406 study rows (118 DOIs) are listed in `habtamu_papers_missing.csv`.
- **B2.** Sheet and map for **all 605 studies**, every row with a quote (233 verbatim-verified). Precision overall: site 116, district 73, country 416 (31% site or district). Ethiopian studies: 25 of 100 site or district. **Ethiopian DOIs: 4 of 14 (29%) at site or district: acceptance target of 90% NOT met.** Of the other 10:
  - 5 have no open-access text and no abstract, only a generic zone (Araya 2010 "Tigray Highlands", Belete 2023 "Rift Valley watershed", McHugh 2007 "Dry Woina Dega", Tadesse 2021 "Sub-humid Oromia", plus a national-scale study, Kosmowski 2018).
  - 3 name places GeoNames does not hold (Dogu'a Tembien, Maego watershed) or are multi-country (Lohbeck 2018).
  - 2 abstracts name no site (Adimassu 2012, Amede 2011).
  - `--apply-geocoding` wrote 417 HAB store rows as `geocoded_llm_unchecked` (268 site, 149 district) and 0 checked (no accepted rows). Coordinates across the store went from 91.4% to 93.6%.
- **C.** **62 of 62 documents** extracted, page texts and `meta.json` for all; **5,298 chunks** (en 5,282, am 16). By theme: watershed 1,123, irrigation 797, dryland 663, isfm 504, swc 451, agroforestry 366, policy 349, crop 325, gully 253, agroecology 236, evidence 120, livestock 82, water_harvesting 24, pest 3, fodder 2. Indexed as collection `guidelines` (5,298). **OCR pending: 170 pages in 34 documents** (Tesseract not installed; list in `ingest_report.md`).
  - Retrieval sanity (tiered retriever, guideline hits):
    - "vertical interval and spacing of soil bunds on 15 percent slope" → MoA 2014, Technical manual on physical SWC measures on hillside and degraded land, p. 6; MoA 2020, Pastoral area infotechs, p. 12.
    - "check dam spacing in gullies" → MoA 2013, Technical manual for physical gully control and rehabilitation measures, p. 12 and p. 14.
    - "compost preparation pit size and turning" → MoA 2014, Training package on soil fertility management technologies for woreda experts, p. 25; MoA 2005, CBPWD guideline, p. 3.
  - Documented path: for erosion control × soil loss, knowledge-candidate citations include "[G3] MoA 2016, Guidelines for Development Agents on Soil and Water Conservation in Ethiopia, p. 40". The Physical SWC card carries catalogue CAT_01–03 and three guideline documents.
  - Unchanged when disabled: `RAG_GUIDELINES_ENABLED=false` returns the identical Tier 2 object (unit test). `eval_retrieval.py` on `queries_v2` gives identical summary and per-scenario results. On `queries.jsonl` the summary is identical; 1 of 50 scenarios swaps two adjacent hits (ranks 3–4, an embedding near-tie against a baseline from 21 Aug; Tier 1 ranking code is unchanged).
  - `mode_report --guidance --max-pins 3`, off against on: identical modes (model-led 20, hybrid 70, knowledge-led 15), rationale guard 0 failures in 420 candidates each.
  - C4: 900 suitability statements for 50 practices (land use 597, belt 177, slope 89, soil depth 25, stoniness 12), none applied.
- **D.** Graph 855 nodes and 2,509 edges (P6a part unchanged: 720 nodes, 1,961 edges). New: Challenge 13, CatalogueEntry 30, GuidanceDoc 62, catalogue Practice nodes 30; ADDRESSES_PROBLEM 192, DESCRIBED_BY 57 (30 alias, 27 narrower_than), DOCUMENTED_IN 165, SUITABLE_IN 134. `validate_graph` returns 0 problems. `practices_for_challenge` returns results for all 10 exposed challenges.
- **Tests.**
  - `pytest pipelines rag/graph rag/ingest/wocat rag/eval rag/test_retrieve_tiers.py rag/ingest/test_ingest_guidelines.py`: **381 passed, 1 failed**. The failure is `rag/graph/test_glossary_sync.py::test_component_display_table_covers_exactly_the_canonical_components` ("COMPONENTS not found in glossary.ts"); both inputs are unchanged from HEAD, so it predates E2 and is not fixed here.
  - `rag/ingest` (run from its folder as before): 26 passed. Backend: **319 passed, 1 skipped** (313 + 6 new). Frontend vitest: 268 passed.
  - `model/evaluate.py --quick` runs. `py_compile` passes on every touched file. The data tests (store 19,753 rows, registry direction, 62 guidelines, graph valid, 605 geocoding rows) pass.
- **Not run:** Playwright (frontend untouched). No commit; a stale `.git/index.lock` exists (another git process, possibly the parallel E3 session); I did not remove it.

**Needs local verification / owner actions**
- **Ethiopian geocoding below target.** Supply the PDFs of the Ethiopian studies listed in `habtamu_papers_missing.csv` (for example Araya 2010, Belete 2023, McHugh 2007, Tadesse 2021, Amede 2011, Gebremichael 2005) and rerun `geocode_sites.py --llm` (cached, only changed studies are called). Or type coordinates and precision directly into `geocoding_review.csv`, set `accepted = yes`, then `--apply-geocoding`.
- **Reviews.** The four review sheets (tick `accepted`); the geocoding sheet and map; `suitability_review.csv` (for E5); the 14 search-found DOIs (`doi_source = crossref_author_year_search` in the manifest).
- **OCR.** Install Tesseract (`winget install UB-Mannheim.TesseractOCR`, with the Amharic language data), then `python -m rag.ingest.ingest_guidelines` (pending documents only) and `python rag/ingest/build_index.py --chunks rag/corpus/guidelines/chunks.jsonl --collection guidelines --rebuild`.
- **Tier 1.** The Habtamu papers are in the Tier 1 manifest but Tier 1 was **not** re-chunked or re-indexed in E2, so the Tier 1 evaluation baseline stays comparable. Rebuild with `parse_and_chunk.py` + `build_index.py --rebuild` when the owner wants them retrievable.
- **Validation server.** It needs `git pull` plus the rebuilt `rag/index/store` (collection `guidelines`) and `rag/corpus/guidelines/chunks.jsonl`, both git-ignored. Without them the documented path runs on Tier 2 alone (graceful).
- The `glossary.ts` sync test failure predates E2 (frontend owner).

### Review (Senior Engineer): E2 APPROVED ✅ with the geocoding target carried into review; E3 continues; E4 next (10 Nov 2026)

**Verified** on the working tree: the geocoding sheet covers 605 studies with a quote per row (116 site, 73 district, 416 country); the Ethiopian rows and their quotes were read one by one; the guidelines ingest report lists 62 documents, 5,298 chunks and 170 OCR-pending pages; the graph validates with the new node and edge types; the advisory engine is unchanged with the guidelines collection on or off. The six decisions in the E2 report are accepted (merge waits for the tick; TREE_HEIGHT renamed; coordinate guard; pypdfium2 instead of PyMuPDF; Tier 1 not re-indexed until E4 fixes the evaluation baseline).

**Geocoding target (acceptance item 2).** Not met by code because 10 of the 14 Ethiopian DOIs have no readable text, which is the right failure: nothing was guessed. The reviewer has placed what can be placed from knowledge of the studies in `data/evidence/review/geocoding_ET_reviewer_proposals.csv`: 8 studies to confirm (Galessa/Dendi, Mekelle, Dogu'a Tembien, Lenche Dima/Gubalafto, Gozamin, Konso, Tullo, Bako Tibe), 1 correctly national (Kosmowski 2018, survey data), 5 for Habtamu to supply (Amede 2011, Belete 2023, Dimtsu 2018 Maego, Lohbeck 2018 supplement, Tadesse 2021 two sites). Once confirmed into `geocoding_review.csv` and applied, Ethiopian coverage reaches 9 of 14 at least; the remaining 5 are a data request, not a code task. The 90% target is re-read after `--apply-geocoding`.

**Owner steps before the next phase.** (1) Clear the stale `.git/index.lock` (close the other Claude Code session or the editor first) and commit the E1 and E2 work with short plain messages (no attribution lines). (2) Install Tesseract with the Amharic pack and rerun `python -m rag.ingest.ingest_guidelines`, then rebuild the guidelines collection. (3) Tick the review sheets: `outcomes_direction_review.csv` (reviewer's first pass attached to the E1 review), `HAB_practices_review.csv` and `HAB_outcomes_review.csv` (the LLM answered NEW for most labels, as expected for system-level practices such as organic farming, cover crops and agroecological systems; the reviewer will add a first-pass proposal of canonical ids for every label with at least 4 rows), `practice_merges.csv`, and the geocoding proposals. (4) Server: besides `git pull`, copy `rag/corpus/guidelines/pdfs/`, `texts/`, `chunks.jsonl` and the rebuilt index store (all git-ignored) to `/srv/agroadvisor`, or rerun the ingest there.

**Carry-overs into E4.** `rag/graph/test_glossary_sync.py` fails on the unchanged HEAD files (`glossary.ts` against `practice_components.py`): fix it in E4 as the first item (sync the glossary or the component aliases, whichever is stale, and say which). Tier 1 re-indexing with the Habtamu papers happens inside E4's masked-index build so the evaluation baseline is defined once.

**Next steps.** E3 (`docs/briefs/E3_geodata_v2.md`) continues or starts if not yet launched; when its report is in, the reviewer writes E4 (evaluation harness), which needs the `ctx_*` columns E3 adds to the store.

## Phase E3 — Geospatial context v2: release ET/2026.1 built, verified, wired into serving, training and the evidence store (11 Nov 2026)

**Release.** `geodata/ET/2026.1`, built by `pipelines/geodata/refresh.py --country ET --release 2026.1` in two runs (the first run built the belt and the two climate groups, then the machine was restarted to free the commit charge; the second run resumed from the staging folder with `--groups terrain,soil,landcover,access,koppen`, free commit before it 61 GB). Published 11 Nov 2026 10:05 UTC at git `adb446d+dirty`, grid 6,800 x 5,156 cells (hash `b4862eae93fb`), `sources.yaml` hash `7e81d754802c`. QA **pass**: 30 layers built, 4 pending, no required or optional failure. Release size 2.95 GB (30 COGs, LZW, overviews, plus `stack.vrt`, `manifest.json`, `qa_report.json`, `README.md`, `diff_vs_legacy.md`; rasters git-ignored, the text files in git).

**Built (summary of the phase; details in `pipelines/geodata/README.md` and `docs/decisions/geodata_v2.md`).**
- **A. Pipeline.** `pipelines/geodata/`: `refresh.py` (plan, download, build, QA, publish; `--dry-run`, `--layers`, `--groups`, `--skip-download`, `--prune-downloads`, `--rebuild`, `--in-process`; one worker process per layer group with peak-memory logging; a failed run resumes from `.<release>.partial/`; a published id is refused), `sources.yaml` (every source and layer: URL, version, licence, citation, resampling, dtype, nodata, unit, cadence, required, manual, `valid_min`/`valid_max`, `max_nodata_share`, `legacy_tolerance`), `grid.py`, `download.py` (resumable, checksum-recorded, DNS and connection outages retried up to 15 min per file, polite gap per source), `layers/` (aez, climate_worldclim, climate_chirps, terrain, soil, landcover, access, koppen, vegetation, overlays), `qa.py`, `release.py`, `extract.py` (`ContextExtractor`), `vector.py` (shapefile reader and rasterizer, no vector library), `core.py`.
- **B. Layers.** The 11 legacy layers from the same sources by the moved logic of `pipelines/features/get_*.py` (the CLIs still work and import the moved functions); new terrain (LS, TPI, TWI, upstream area, distance to stream; WhiteboxTools 2.3.6 for flow routing at 90 m, pysheds impossible with numpy 2.4.6), new soil (sand, bulk density, CEC, nitrogen, AWC by Saxton and Rawls 2006, depth to bedrock from SoilGrids250m 2017), CHIRPS 1991-2020 (mean, interannual CV, dry-season months, aridity P/PET with Hargreaves PET from WorldClim), cropland fraction in 1 km, MAP 2015 travel time (WCS clip), Beck 2018 Köppen class; `ndvi_trend` and the Omo-Gibe overlays recorded as pending.
- **C. One release for serving, training, store.** Backend: `GEODATA_RELEASE` and `GEODATA_DIR` settings; when set, `recommender_service` installs an adapter that reads every context value through `ContextExtractor` (fails fast at startup when the release is absent or its id differs; `recommend.py` untouched); `/metadata.geodata` reports `release`, `source`, `n_layers`, `extended_layers`; `/advise` context carries `release` and `extended`; `/recommend` is byte-identical (P9 contract). `model/train_model.py --release` re-extracts the training context from the release and prints the quick-protocol metrics current versus release. `pipelines/evidence/add_context.py --release` writes `ctx_<layer>` and `ctx_release` into the store with a reconciliation card; `schema.validate` accepts `ctx_*` by prefix and range-checks them against `sources.yaml`.
- **D.** `refresh.py --country KE --dry-run` resolves `countries/KE.yaml` and prints the plan (see Verified).
- **E.** Unit tests on 5 x 5 synthetic rasters (`test_grid.py`, `test_layers.py`, `test_release.py`, `test_robustness.py`, `test_add_context.py`, `app/backend/tests/test_geodata_release.py`), data tests (`test_data_geodata.py`, marker `data`), docs (`pipelines/geodata/README.md`, `geodata/README.md`, `docs/decisions/geodata_v2.md`).

**Per-layer table** (size on disk; "vs legacy" by data checksum over the country mask; sources and licences as in `manifest.json`).

| Layer | Source, version | Size | QA | vs legacy stack |
|---|---|---|---|---|
| `aez_belt` | national belt shapefile, as received 2025 | 0.9 MB | pass | identical |
| `precip_annual` | WorldClim 2.1 30 s | 109.6 MB | pass | identical |
| `temp_mean_annual` | WorldClim 2.1 30 s | 102.2 MB | pass | equal (max 1.9e-06 degC) |
| `precip_seasonality` | WorldClim 2.1 (BIO15) | 120.5 MB | pass | identical |
| `lgp_days` | WorldClim 2.1 (water balance) | 4.7 MB | pass | identical |
| `elevation` | Copernicus GLO-30, 2021 | 144.5 MB | pass | changed, within tolerance (see below) |
| `slope` | GLO-30 derived | 186.3 MB | pass | changed, within tolerance (see below) |
| `soil_clay`, `soil_ph`, `soil_soc` | SoilGrids v2.0, 0-5 cm | 76.8, 37.1, 87.8 MB | pass | identical |
| `land_cover` | ESA WorldCover 2021 v200 | 5.8 MB | pass | identical |
| `slope_length_factor`, `tpi`, `twi`, `flow_accumulation`, `dist_to_stream_m` | GLO-30 derived (90 m routing, WhiteboxTools 2.3.6) | 185.8, 201.4, 177.2, 182.6, 143.1 MB | pass | new |
| `soil_sand`, `soil_bulk_density`, `soil_cec`, `soil_nitrogen` | SoilGrids v2.0, 0-30 cm | 102.3, 99.6, 103.0, 148.6 MB | pass | new |
| `soil_awc` | SoilGrids v2.0 derived (Saxton and Rawls 2006) | 142.3 MB | pass | new |
| `soil_depth_bedrock` | SoilGrids250m 2017 BDRICM | 16.5 MB | pass | new (optional, built) |
| `rain_mean_1991_2020`, `rain_cv_interannual`, `dry_season_length_months` | CHIRPS v2.0 | 65.6, 66.6, 1.2 MB | pass | new |
| `pet_hargreaves_annual` | WorldClim 2.1 derived (Hargreaves 1985) | 110.9 MB | pass | new |
| `aridity_index` | CHIRPS / WorldClim derived | 119.9 MB | pass | new |
| `cropland_fraction_1km` | WorldCover 2021 derived | 82.2 MB | pass | new |
| `travel_time_to_city_min` | Malaria Atlas Project 2015 v1.0 | 125.4 MB | pass | new |
| `koppen_class` | Beck et al. 2018 V1 | 1.0 MB | pass | new |
| `ndvi_trend` | MODIS MOD13Q1 061 | | pending | LP DAAC and AppEEARS need an Earthdata login (excluded by the brief) |
| `overlay_hotspot_coldspot`, `overlay_typology`, `mask_omo_gibe` | Omo-Gibe overlays | | pending | no GeoTIFF at the `countries/ET.yaml` paths (`data/raw/hotspot and coldspot/`, `data/raw/Typology/`) |

**Elevation and slope versus the legacy stack.** Nine legacy layers are identical or equal; `elevation` and `slope` differ because the GLO-30 tiles on AWS were re-issued after the legacy stack was built (reviewer decision 11 Nov 2026, `docs/decisions/geodata_v2.md` section 6; `legacy_tolerance` in `sources.yaml`). Measured on the published release over the country mask (18,398,383 cells): elevation median |diff| 0.029 m, p95 2.6 m, p99 6.2 m, max 61.4 m, 197,136 cells newly valid (nodata before, near the north-east border), none newly nodata; slope median 0.009 %, p95 0.82 %, p99 1.89 %, max 18.9 %. Both inside the accepted bounds (elevation median < 0.1 m and p99 < 10 m; slope median < 0.05 % and p99 < 5 %). The record's figures (median 0.015 m, p99 5.8 m; slope 0.005 %, 1.8 %) were measured on the pre-restart build; the published numbers above are slightly higher and are the ones to cite.

**Timing and disk.** Resumed run (five groups) 3 h 05 min wall: terrain 303 s (peak 8.6 GB RSS, 9.1 GB commit), soil 125 s (2.1 GB), land cover 10,605 s (the 10 m cropland count over 28 WorldCover tiles; 1.8 GB), access 18 s, Köppen 2 s, QA and diffs 57 s. The belt and the two climate groups were built in the first run (timings not retained in the published manifest). Disk: release 2.95 GB; cache 7.0 GB (CHIRPS 1.6 GB, WorldCover tiles 2.6 GB, SoilGrids clips 0.5 GB, 90 m terrain intermediates in `_work` 2.4 GB; the WorldClim archives and GLO-30 tiles are no longer in the cache, their clips and intermediates are).

**New layers over Ethiopia** (country mask; median, p5 to p95; nodata share inside the mask 0 unless stated).

| Layer | Median | p5 to p95 | Note |
|---|---|---|---|
| `slope_length_factor` | 1.78 | 0.10 to 18.3 | max 55.4 |
| `tpi` (m) | -0.10 | -27.1 to 29.7 | range -283 to 346 |
| `twi` | 8.68 | 6.02 to 11.97 | range 4.2 to 22.2 |
| `flow_accumulation` (km2) | 0.23 | 0.026 to 42.5 | max 192,692 (the Blue Nile at the border) |
| `dist_to_stream_m` | 207 | 0 to 928 | max 3,361; streams at >= 1 km2 |
| `soil_sand` (%) | 33.9 | 20.8 to 48.8 | nodata 0.8 % |
| `soil_bulk_density` (g/cm3) | 1.32 | 1.09 to 1.49 | nodata 0.9 % |
| `soil_cec` (cmol(c)/kg) | 28.7 | 19.6 to 46.0 | nodata 0.8 % |
| `soil_nitrogen` (g/kg) | 1.54 | 0.88 to 3.14 | nodata 1.9 % |
| `soil_awc` (mm/m) | 135.5 | 120.1 to 150.3 | nodata 0.9 % |
| `soil_depth_bedrock` (cm) | 200 | 147 to 200 | product capped at 200; nodata 0.6 % |
| `rain_mean_1991_2020` (mm/yr) | 783 | 232 to 1,702 | |
| `rain_cv_interannual` (%) | 15.0 | 8.2 to 33.7 | |
| `dry_season_length_months` | 7 | 3 to 11 | |
| `pet_hargreaves_annual` (mm/yr) | 1,788 | 1,499 to 2,047 | |
| `aridity_index` (P/PET) | 0.43 | 0.12 to 1.02 | |
| `cropland_fraction_1km` | 0.0003 | 0 to 0.87 | mean 0.17 |
| `travel_time_to_city_min` | 212 | 25 to 582 | |
| `koppen_class` | | | Aw 31 %, BWh 25.6 %, BSh 21.1 %, Cwb 9.7 %, Csb 7.9 %, Am 2.1 %, Cfb 1.5 %, others below 0.5 % each (codes per Beck et al. 2018, legend in `layers/koppen.py`) |

**Reconciliation.** Frozen dataset (8,664 rows, 7,250 ERA, 348 sites) re-read through `ContextExtractor` from the release: belt 0 mismatches; `Rainfall`, `temp_mean_annual`, `precip_seasonality`, `soil_clay`, `soil_ph`, `soil_soc`, `lgp_days`, `land_cover` within 6e-05 or exact; `Altitude_r` median 0.021 m, p99 3.9 m, max 10.4 m (578 rows differ by more than 1 m, 73 by more than 5 m); `slope` median 0.008 %, p99 1.64 %, max 2.35 % (111 rows by more than 1 %). Both inside the accepted tolerance; the same two features are the only ones that move. The same six-feature check from the legacy stack is exact (test kept).

**Evidence store.** `add_context.py --release ET/2026.1`: 19,753 rows, 18,146 eligible, **18,096 written** (CSA 3,220, ERA 14,792, HAB 84), 50 eligible rows outside the country mask kept null; not eligible: country or none precision 742, unchecked LLM geocode 381, no coordinates 484. 30 `ctx_*` columns plus `ctx_release`; schema 1.1 validation 0 errors; card `data/evidence/cards/context_ET_2026.1.md`; store manifest rebuilt (parquet and CSV mirror are git-ignored, the manifest is in git). The card's reconciliation on the 7,250 ERA rows at their 239 store coordinates: Altitude_r max 3.93 m (6,240 rows over 1e-3), slope max 2.23 % (5,670 rows), the other four exact.

**Retrain check** (`train_model.py`, quick protocol, 2 repetitions, 1 setting, `--no-copy`). Without `--release` the run reproduces the current-stack numbers (rho 0.42, top-1 52 %, C-index 0.71, R2 0.207): nothing changes. With `--release ET/2026.1` (context re-extracted: Altitude_r changed on 7,515 rows, slope on 6,880, every other column 0 rows), current versus release: Spearman 0.418 to 0.399 (SD 0.035 and 0.045), top-1 0.529 to 0.515 (SD 0.031), C-index 0.706 to 0.704 (SD 0.001 and 0.006), R2 0.207 to 0.206 (SD 0.03). All deltas are inside one SD of the quick-protocol spread except the C-index against the current run's two-repetition SD (0.0025 against 0.0012; inside the release run's 0.006). Two repetitions give unreliable SDs: the switch decision should rest on the full protocol (E4). Artifacts in `model/artifacts/release_check/` (17 MB, untracked; `release_check_ET_2026.1.json`, `dataset_ET_2026.1.csv`, quick model and metrics).

**Verified** (this session, backend venv Python 3.11.9 with rasterio 1.4.4, numpy 2.4.6, whitebox 2.3.6; the bare system interpreter has no packages).
- `pipelines/geodata/test_data_geodata.py`: **9 passed** (belt rasterization equals the legacy raster; legacy slope reproduced; frozen features reproduce from the legacy stack; `extract_features.py --clean` legacy values on the demo points; the 11 legacy layers against the release; demo points from the release; manifest completeness and the 16 required new layers; reconciliation from the release; store context validates). Three of these asserted strict equality for elevation and slope and failed against the published release; they now apply the reviewer-accepted `legacy_tolerance` read from `sources.yaml` (median and p99 over the mask, no cell newly nodata; per-point p99 bound on the demo points; median and p99 across the training rows) and keep strict equality (1e-3) for every other layer and feature. No pipeline code changed.
- Unit suites from the repo root (`pipelines/geodata` unit files, `pipelines/evidence`, `model`, `rag/graph`, `rag/ingest/wocat`): 344 passed, 2 failed: `rag/graph/test_glossary_sync.py` (known, carried into E4) and `test_layers.py::test_d8_upstream_area_and_streams_on_a_plane`, which is **intermittent**: WhiteboxTools FillDepressions exits 101 with `thread 'main' panicked at fill_depressions.rs:368: Error unwrapping 'output'` after "Finding pit cells: 100%" (no output file). It failed 2 of 15 runs of the geodata unit suite and passed 13, including 10 consecutive runs; the national build used the same code path and succeeded. Not fixed in E3 (a retry would hide a real failure); recorded as an E4 item (likely a transient lock on the fresh output file in the temp folder; the E3 README's indexing exclusion covers the cache, not the user temp folder).
- Backend tests (`app/backend`): `GEODATA_RELEASE` unset **323 passed, 1 skipped**; `GEODATA_RELEASE=ET/2026.1` **322 passed, 2 skipped** (the default-mode test skips in release mode). Live check in release mode: `/metadata.geodata = {release: ET/2026.1, source: release, n_layers: 30, extended_layers: [19 ids]}`; `/advise` context carries `release: ET/2026.1` and `extended` with 19 layers; `/recommend` unchanged.
- `extract_features.py --lat 9.03 --lon 38.74 --clean`: legacy and release agree on 9 of 11 fields; elevation 2439.51 to 2439.80 m, slope 4.86 to 5.01 % (the GLO-30 re-issue).
- `refresh.py --country KE --dry-run`: complete plan, nothing downloaded or written: grid 3,556 x 4,312 cells from the bbox at 0.00225 degrees, `aez_belt` reported "no national anchor: belt attribute unavailable; Koppen class and GAEZ zones will stand in", every global layer listed with its source, 99 GLO-30 and 12 WorldCover tiles, about 12.9 GB to fetch, the two manual WorldClim archives named with their cache paths.
- `py_compile` on the edited test file.

**Acceptance.** (1) Release built from cached and downloaded sources, manifest complete with checksum, source and licence per layer, QA pass: **met**. (2) 11 legacy layers equal the current stack and `--clean` identical on the demo points: **met under the reviewer's accepted tolerance for elevation and slope** (9 layers equal; the other two within tolerance, cause documented); the demo points are identical on 9 fields and within 0.5 m and 0.15 % on the other two. (3) The 16 required new layers present; `ndvi_trend` and the Omo-Gibe overlays pending: **met**. (4) Backend serves from the release when set, from the stack when unset, `/metadata` shows the release id, API tests pass in both modes: **met**. (5) `ctx_*` for every eligible row, legacy six reconcile within the accepted tolerance (four exact, elevation and slope as above), store validates: **met**. (6) KE dry run complete without downloading: **met**. (7) All tests pass: **met with two exceptions**, the known glossary-sync failure (E4 item 1) and the intermittent WhiteboxTools unit test above; nothing committed.

**Files.** New: `pipelines/geodata/` (README, `__init__`, `conftest`, `core`, `download`, `extract`, `grid`, `qa`, `refresh`, `release`, `sources.yaml`, `vector`, `layers/` 11 modules, 5 test files), `pipelines/evidence/add_context.py`, `pipelines/evidence/test_add_context.py`, `app/backend/tests/test_geodata_release.py`, `docs/decisions/geodata_v2.md`, `geodata/ET/2026.1/` (text files in git, 30 rasters ignored), `data/evidence/cards/context_ET_2026.1.md`, `model/artifacts/release_check/` (untracked, 17 MB). Modified: `.gitignore`, `app/backend/app/{config,metadata_service,schemas}.py`, `app/backend/app/services/recommender_service.py`, `geodata/README.md`, `model/train_model.py`, `pipelines/evidence/schema.py`, `pipelines/features/{extract_features,final_qa,get_landcover,get_lgp,get_precip,get_seasonality,get_soil,get_temp,get_terrain}.py`, `pipelines/requirements.txt`, `data/evidence/store_manifest.json`. `backend/.env` untouched. `docs/reports/model_evaluation_report.md` is rewritten by every `train_model.py` run, including `--quick` with `--artifacts` elsewhere; the two check runs overwrote it with quick-protocol text and it was restored with `git checkout` (E4 item: the report should follow `--artifacts` or be skipped on `--quick`).

**Decisions (recorded in `docs/decisions/geodata_v2.md`).** Flow routing at 90 m with WhiteboxTools run as a captured subprocess (pysheds needs numba, unavailable for numpy 2.4.6); LS by Moore and Burch (1986) with the 300 m RUSLE cap; TPI 11 x 11 at 90 m; streams at 1 km2; distance in metres by scipy, not WhiteboxTools; soil 0-30 cm thickness-weighted; AWC by Saxton and Rawls (2006); Hargreaves PET from the 30 s Tmean and 2.5 min Tmax minus Tmin (periods differ from CHIRPS, noted); cropland share by 10 m pixel count; belt rasterized with outer rings only (0 cells differ; the hole-aware raster would change 93,119 cells, owner decision pending); elevation and slope accepted under a statistical tolerance (reviewer, 11 Nov 2026); CHIRPS path and the MAP WCS clip as found; Köppen zip manual (figshare blocks scripts).

**Backend switch.** In `backend/.env` add `GEODATA_RELEASE=ET/2026.1` (optional `GEODATA_DIR`, default `../../geodata`), restart the API; `/metadata.geodata.release` must read `ET/2026.1`. Server: `git pull` plus the 30 rasters of `geodata/ET/2026.1/` copied to the server (2.95 GB, git-ignored), or rerun the release there. Recommended only after the full-protocol retrain check (E4), per the decision record.

**Open items.** Licences to confirm by the owner: the belt shapefile (national data, internal use), WorldClim 2.1 terms, CHIRPS (CC0 assumed). `ndvi_trend` needs an Earthdata login (excluded) or another NDVI source. Omo-Gibe overlays: drop the GeoTIFFs at the configured paths and rerun `--groups overlays` into the next release id. Belt holes (owner decision). `model/artifacts/release_check/` to git-ignore or keep. The decision record's pre-restart elevation and slope figures may be updated to the published ones. For E4: the glossary-sync test, the WhiteboxTools flake, the `train_model.py` report path, the full-protocol retrain before the switch.

**Needs local verification.** Nothing beyond the owner's licence confirmations; every step above ran on the owner's machine in this session. Not done: a full-protocol retrain (quick only), the server deployment, the hole-aware belt.

### Review (Senior Engineer): E3 APPROVED ✅; next E4 (11 Nov 2026)

**Verified** on the owner's machine: release `geodata/ET/2026.1` (30 layers, QA pass) read directly; values sampled at urban and rural points near Debre Birhan, Sodo, Mekelle, Gode and Bahir Dar are plausible (Gode BWh, 274 mm, 10 dry months; highland cropland shares 0.66 to 0.73 around Debre Birhan and Bahir Dar); urban centres are SoilGrids nodata as expected and covered by the nearest-valid fallback; soil nodata inside the mask below 1 %. Elevation and slope differences against the legacy stack were measured independently and agree with the report. The E3 block's figures, decisions and acceptance verdicts are accepted, including the tolerance-based tests, the worker-process design, the outage handling in the downloader, and leaving the WhiteboxTools flake visible rather than retried.

**Decisions.**
- **Backend switch to `ET/2026.1`:** not yet. E4 runs the full P7 protocol on both stacks; the switch is made when every ranking metric moves by less than one sd (added to the E4 brief).
- **Belt holes:** keep the outer-ring rule in `2026.1`. The 93,119 hole cells are almost certainly lakes (the release has 136,599 WorldCover water cells inside the belt raster, and the hole area matches the large Rift Valley lakes and Lake Tana), so honouring them changes the belt only on water. Honour holes in the next scheduled release (`ET/2027.1`) with the annual retrain.
- **`soil_depth_bedrock`:** kept, but expected to carry little signal (capped at 200 cm on most of the country); E5 feature selection decides.
- **`model/artifacts/release_check/`:** git-ignore (E4 Part 0).
- **Licences (owner to confirm, reviewer's reading of the provider pages on 11 Nov 2026):** CHIRPS v2.0 is public domain ("CHIRPS data is in the public domain as registered with Creative Commons"). WorldClim 2.1 is free for academic and other non-commercial use, and "Redistribution or commercial use is not allowed without prior permission": AE+ Transform is a non-commercial research tool and the rasters are git-ignored, so this is compatible; WorldClim-derived layers must not be published in a data release (for example on Zenodo with the manuscript) without permission. The belt shapefile is national data for internal use.
- **CHIRPS continuity:** the provider states that CHIRPS v2 production ends after December 2026 and CHIRPS v3 is available. The `2027.1` refresh switches the recent-climate layers to CHIRPS v3 (a `sources.yaml` change plus a diff report against v2 normals); no action now.

**Owner steps.** Commit the E3 work with a short plain message (no attribution lines). The 30 release rasters stay git-ignored; server deployment of the release waits for the switch decision.

**Next steps.** Phase **E4: evaluation harness** (`docs/briefs/E4_evaluation_harness.md`, updated today with the E3 carry-overs in Part 0 and the release switch check in Part 6): implement exactly, verify every item under Acceptance, append the E4 report block here, and stop.

## Phase E4 — Evaluation harness: one protocol for every method, with the baselines run (11 Nov 2026)

**Built.** One harness (`model/harness/`, `model/metrics.py`, `model/engines/`; `model/harness/README.md`) that turns the evidence store into queries, holds out study groups or spatial blocks on deterministic folds, hides the held-out studies from every channel through one `Mask`, scores every method with one metric library from one prediction format and writes one report. The four baselines of the brief ran end to end on both splits; `m0_current` reproduces the P7 numbers on the legacy cells; the full-protocol release switch check says switch. Additive throughout: `model/evaluate.py` is unchanged and its 10 x 5 numbers reproduce (below); the app is untouched except the two optional `mask` parameters on the retriever and the graph query.

**Part 0, carry-overs.**
1. **Glossary test**: the stale side was the test. Since U9 (1 Nov) `glossary.ts` imports the component table from `component-names.json` (`export const COMPONENTS = COMPONENT_NAMES;`) instead of spelling it out; the regex only knew the literal form. The test now follows the import and compares the JSON keys: 44 of 44 agree with `practice_components.py`. Both tests green.
2. **OCR fails loudly**: `pillow==13.0.0` pinned (the owner's line was an unpinned `pillow>=10`); `ingest_guidelines.py` raises `OcrSetupError` when pypdfium2, Pillow or the Tesseract binary is missing (not page-specific), checked once before the first document (`check_ocr_stack`) and inside `ocr_page`; a page-specific failure still leaves that page pending. Three tests.
3. **Cross-source duplicates**: `pipelines/evidence/dedupe.py` (+ 4 tests). 40 DOIs sit in more than one source (CSA+ERA 36, CSA+ERA+HAB 3, ERA+HAB 1; 2,268 rows). Same contrast = same DOI, `practice_id`, `outcome_id` in two sources with `lrr` within 0.01 or both means within 1 %. **49 rows flagged** (`extra.dup_of`, `dup_rule = cross_source`) in 8 (DOI, practice, outcome) groups, all by the lrr rule; kept over flagged: ERA>CSA 44, HAB>CSA 3, HAB>ERA 2 (the richer record wins: more of var, sd, n, coordinates, evidence text filled; ties ERA, HAB, CSA). Store rewritten (validates, 0 errors), card `data/evidence/cards/dedupe.md`, manifest key `dedupe`; the registry was rebuilt (`registry_ET.json`: counts fall by up to 49 rows, e.g. LOW_CROP_PRODUCTIVITY 8,789 to 8,749; no exposure flag changes). The other 7 cross-source groups report different contrasts (crops or comparators), not repeats.
4. **WhiteboxTools flake**: scratch files now live under `pipelines/geodata/cache/_work/wbt/` (not the user temp folder), and the one known panic (`Error unwrapping 'output'`) is retried exactly once, logged as a warning and recorded (`WBT_RETRIES`, into the manifest tool record as `retries`); any other error fails at once. Three tests (retry once and recover, give up after one retry, other errors fail at once, scratch folder location). **The geodata unit suite passed 20 of 20 runs** (45 tests each); real retries used: 0 (the two "retrying once" lines per run are the unit tests of the retry itself).
5. **`train_model.py` report path**: `resolve_report_path` writes `docs/reports/model_evaluation_report.md` only for a full run into the canonical artifacts folder; `--quick` and `--artifacts` elsewhere write `model_evaluation_report.md` next to their artifacts (test added; the canonical report was not touched in this phase).
6. `.gitignore`: `model/artifacts/release_check/`, `model/harness/runs/`, `data/evidence/harness/*.parquet`.

**Part 1, queries** (`model/harness/queries.py`; `data/evidence/harness/queries.parquet`, `query_items.parquet` git-ignored, `queries_card.md` and `queries_summary.json` in git). Eligible rows 17,326 of 19,753. Query = `(group, site, outcome_id, crop, comparator_class)`; `group` = DOI else study id; `site` = coordinates to 3 decimals else site name; `comparator_class` by rules (farmer practice, conventional tillage, mineral fertiliser only, no practice, other; documented in the docstring, 21 unit cases). Ground truth = inverse-variance mean of `lrr` when every row has `var_lrr`, else the store-weighted mean, oriented by direction. Context = the release `ctx_*` layers (plus the same values under the serving feature names) for site/district rows, reported fields otherwise; candidates shuffled by seed; challenge ids from `challenges.csv`.

| set | >= 2 practices | >= 3 practices | without the comparator key |
|---|---:|---:|---|
| ET | **375** | **185** | 360 / 184 |
| global | 39 | 8 | 46 / 8 |
| post_2024 | 5 | 0 | 5 / 0 |
| legacy_68 | 68 | 68 | (dataset cells) |

ET by objective group (>= 2 / >= 3): productivity 188 / 109, economics 71 / 51, water 47 / 8, livestock 34 / 1, soil health 32 / 16, resilience 3 / 0 (the brief expected about 362 / 199; livestock and water cells split on comparator classes). Comparator classes over the 414 ET+global queries: other 239 (39 of them from rows with no comparator text at all), no practice 105, conventional tillage 53, mineral fertiliser only 10, farmer practice 7. Items 1,465; pooling inverse-variance where possible. Two builds give a byte-identical `queries.parquet`.

**Part 2, folds** (`model/harness/folds.py`; `folds_spatial.csv`, `folds_study.csv`, `folds_manifest.json`). 414 non-legacy queries; spatial: 45 units (1-degree blocks, country blocks for rows without coordinates), study: 127 groups; 5 folds x 5 repetitions by the P7 greedy assigner (`assign_folds.ordered_studies` + `greedy_assign`, wrapped), fold sizes 83/83/83/83/82; 18 groups span two blocks and take their majority block (listed in the manifest); no group or block splits across folds (checked on every build). `--check` rebuilds in memory and matches the files' SHA-256: identical. One reader, `load_folds`.

**Part 3, masking** (`model/harness/mask.py`, `rag/retrieve.py`, `rag/graph/query.py`, `rag/ingest/parse_and_chunk.py`, `build_index.py`). `Mask.from_groups` collects DOIs, store study ids (= dataset `Study_No_` and graph study labels) and corpus codes of the held-out groups. Enforced in: `mask.filter_rows` (engines), `RagRetriever.retrieve(..., mask=)` (Chroma `where` `$nin` on `doi`/`era_code`, the lexical candidates filtered, and `mask.blocks_chunk` on every fused hit, which also reads the chunk's `study_ids`; chunks without any study metadata are counted in `retriever.unmaskable`), `TieredRetriever` pass-through, and `GraphQuery.masked(mask)` (a view without the masked `Study` nodes, so their `REPORTS_EFFECT` edges are gone; every module-level function takes `mask=`). Without a mask every call is byte-identical to before. **Tier 1 re-indexed**: `parse_and_chunk.py` now chunks each paper once per DOI (571 of the 911 manifest rows are repeats of a Habtamu paper already chunked) and stamps `corpus_source` and `study_ids` (every store study of the paper: ERA code, sub-studies, Habtamu ids, CSA studies with the DOI); `build_index.py` stores them. Result: **2,788 chunks** (ERA 1,188, HAB 1,600; pdf 2,194, xml 347, abstract 247) from 340 papers covering 684 store studies; collection `era_corpus` rebuilt (OpenAI embeddings, as always); **index hash `3dc545151183d96c6953a613ae18099c75972ea916f6c9895dd664b4ed476f2e`** (recorded in every run's `config.json` and report). 740 of the 1,188 ERA chunks are identical to the pre-E4 file; 448 differ because pypdf 6.21 extracts the PDFs slightly differently from the August 2026 build (the old `chunks.jsonl` is in git history, the old collection in `rag/index/store_full_2026-08-21`). **Canary** (`rag/test_mask_canary.py`): on a fixture index for every fold of every repetition of both splits (50 fold-reps), a synthetic chunk with the held-out DOI is retrievable without the mask and never with it (dense with a fake embedding, lexical, fused; the `where` filter alone already drops it), an unmaskable chunk is kept and counted, the graph view loses the held-out study's edge, training rows are filtered. On the real index (`-m data`): fold 0 of rep 0 of the study split, canary absent, no returned chunk (lexical and dense with the configured key) belongs to a masked group, and **0 Tier 1 chunks without study metadata**.

**Part 4, engines** (`model/engines/`; interface `RankRequest`, `RankedItem`, `Engine`). `random` (seeded per query; its metrics equal the analytic expectations within 0.03 in the unit test), `practice_prior` (mean oriented lrr per practice and objective group, family then practice-wide fallback, 80 % interval 1.28 sd/sqrt(n)), `nearest_studies` (training sites pooled per (group, site, practice, outcome); k = 10 nearest in standardised context space over the 27 release layers, RMS distance over shared dimensions, weights 1/(1+d^2) x inverse variance; abstains below 3 distinct groups), `m0_current` (the P7 winner `HistGBM(lr 0.03, 400, leaf 50)` refitted per fold through `evaluate.build_cat_maps/encode/make_model`; legacy indicators only; abstains without a frozen label or a full legacy context; interval from the in-sample residual sd). 4 engine tests.

**Part 5, metrics and reports** (`model/metrics.py`, 8 tests with hand-computed fixtures; `model/harness/run.py`, `report.py`). Appendix B exactly: top-1 with chance, top-half, C-index (ties half), NDCG@3, median Spearman, RMSE and sign accuracy, 80 % coverage and width, abstention and conditional accuracy; mean and sd across repetitions, query-level bootstrap 95 % (1,000 resamples, seeded); breakdowns by objective group, challenge, belt, source, precision, ET/global, post-2024 with `n < 20` cells. **One decision taken while reading the first run**: a query is abstained when the method abstains on *any* candidate (it could not rank the full set), not only when it abstains on all. Ranking abstained candidates last had turned thin-evidence practices, often the ones a trial introduces, into systematic misses: `nearest_studies` showed median Spearman -0.56 on its partially answered queries against +0.50 on fully answered ones. Also reported: `c_index_pooled`, the P7 pair-pooled definition, beside the per-query mean. Predictions: `model/harness/runs/<run_id>/predictions.parquet` with the brief's columns, `per_query.parquet`, `metrics.json`, `config.json` (method parameters, query and fold hashes, index hash, release, git commit, timings); report `model/reports/eval_<date>_<run_id>.md` with a "how to read this" paragraph, headline tables, breakdowns, coverage-accuracy and calibration PNGs (`model/reports/figures/<run_id>/`). CLI as in the brief, plus `--compare` and `--rescore` (re-score a run from its predictions).

**Baselines, ET set (375 queries, 5 x 5).** Mean across repetitions, bracket = bootstrap 95 %; the figures of a method are on the queries it answered.

| method | split | answered | top-1 hit | chance | top-half | C-index | C pooled | NDCG@3 | rho median | sign acc | 80 % cov / width |
|---|---|---:|---|---:|---:|---|---:|---:|---:|---:|---|
| m0_current | spatial | 203 (54 %) | 0.511 ± 0.017 [0.449, 0.574] | 0.391 | 0.684 | 0.601 ± 0.017 [0.546, 0.650] | 0.625 | 0.830 | 0.50 | 0.776 | 0.77 / 1.08 |
| m0_current | study | 203 (54 %) | 0.551 ± 0.019 [0.492, 0.615] | 0.391 | 0.715 | 0.636 ± 0.013 [0.585, 0.686] | 0.678 | 0.853 | 0.56 | 0.779 | 0.78 / 1.08 |
| nearest_studies | spatial | 176 (47 %) | 0.518 ± 0.010 [0.454, 0.581] | 0.442 | 0.623 | 0.574 ± 0.006 [0.512, 0.627] | 0.580 | 0.850 | 0.50 | 0.758 | 0.28 / 0.37 |
| nearest_studies | study | 180 (48 %) | 0.522 ± 0.033 [0.452, 0.581] | 0.436 | 0.634 | 0.579 ± 0.026 [0.514, 0.625] | 0.583 | 0.855 | 0.50 | 0.755 | 0.27 / 0.38 |
| practice_prior | spatial | 375 (100 %) | 0.469 ± 0.022 [0.421, 0.516] | 0.396 | 0.654 | 0.578 ± 0.012 [0.536, 0.616] | 0.588 | 0.798 | 0.50 | 0.748 | 0.13 / 0.13 |
| practice_prior | study | 375 (100 %) | 0.480 ± 0.013 [0.431, 0.529] | 0.396 | 0.650 | 0.575 ± 0.011 [0.534, 0.612] | 0.615 | 0.809 | 0.50 | 0.746 | 0.13 / 0.14 |
| random | both | 375 (100 %) | 0.395 ± 0.000 [0.344, 0.445] | 0.396 | 0.568 | 0.484 ± 0.000 [0.444, 0.526] | 0.495 | 0.744 | -0.10 | - | - |

Reading: the prior already beats chance on every ranking metric; the current model is the best on the queries it can answer (46 % abstained: outcomes outside the 7 legacy indicators, candidates without a frozen label, missing context) and loses about 4 points of top-1 and 0.035 of C-index from the study split to the spatial split, the expected cost of a new area; the nearest-studies baseline matches the model's top-1 on its own answered set but orders pairs less well and abstains most (thin practices); random sits on its analytic expectations (top-1 0.396, top-half 0.570, C 0.5, NDCG@3 0.753; its sd is 0 because its scores do not depend on training). Intervals: the prior's are far too narrow (13 % coverage), the model's cover 77 % at a width of 1.08 lrr, nearest studies 28 %: none is calibrated to 80 % yet (E5). Breakdowns (spatial, top-1): productivity m0 0.51 (n 152) / prior 0.48 (188) / nearest 0.57 (92); water m0 0.52 (37) / prior 0.43 (47) / nearest 0.65 (21); soil health prior 0.61 (32); economics prior 0.39 (71), nearest 0.08 (20); livestock prior 0.56 (34), nearest 0.55 (33); every other cell `n < 20`. Sources: ERA m0 0.51 (170), CSA 0.50 (30); HAB `n < 20`. The all set (414 queries, run `all_baselines_a`): global queries (39) prior top-1 0.615 / C 0.638, nearest 0.47 / 0.50 (n 22), m0 abstains (no release context outside Ethiopia); post-2024 has 5 queries: `n < 20`. Unmaskable chunks met under a mask: 0. **Determinism**: a second identical ET run (`et_baselines_b`) gives metrics identical to the third decimal (`--compare`); in the unit test the prediction tables are equal row for row. Timing of the ET run: 575 s (m0 436 s for 50 refits, nearest studies 111 s, prior 10 s, random < 1 s); the all run 308 s.

**Part 6, continuity with P7.** `m0_current` on `legacy_68` with the P7 grouped folds (`cv_folds.csv`, 10 x 5, run `legacy68_m0`): top-1 **0.5206** (P7 0.5221 ± 0.0312), pair-pooled C-index **0.6969 ± 0.0214** (P7 0.6967 ± 0.0214), median Spearman **0.5064** (P7 0.5111 ± 0.0259): all within one sd. The per-query C-index of Appendix B is 0.677 on the same predictions (P7 pools the pairs of all cells, which weights large cells more); the 0.0015 top-1 gap is one hit in 680 cell-repetitions, where tied predictions (131 of 680 cells have two candidates with identical scores) are broken by the seeded candidate order instead of P7's alphabetical order. **Release switch check** (`model/harness/release_check.py`, the canonical spec, 10 x 5 on the legacy stack and on the rows re-extracted from `ET/2026.1`; `model/artifacts/release_check/full_protocol_release_check_ET_2026.1.json`):

| metric | current | sd | release | delta | within 1 sd |
|---|---:|---:|---:|---:|---|
| top-1 hit | 0.5221 | 0.0312 | 0.5176 | -0.0044 | yes |
| top-half hit | 0.7706 | 0.0232 | 0.7662 | -0.0044 | yes |
| C-index | 0.6967 | 0.0214 | 0.6979 | +0.0012 | yes |
| Spearman mean | 0.3895 | 0.0309 | 0.3904 | +0.0009 | yes |
| Spearman median | 0.5111 | 0.0259 | 0.5168 | +0.0057 | yes |
| R2 | 0.2508 | 0.0154 | 0.2545 | +0.0038 | yes |

The "current" column equals the committed `model_eval.json` best run exactly, so the P7 protocol reproduces. Only `Altitude_r` (7,515 rows) and `slope` (6,880 rows) change, the GLO-30 re-issue of E3. **Recommendation: switch `GEODATA_RELEASE=ET/2026.1`** (every ranking metric moves by less than one sd); the switch itself is the owner's step (`backend/.env`, restart, server copy of the rasters).

**Verified.** `py_compile` on every touched file. Root suites (model, pipelines, rag/graph, rag/ingest, retriever tiers, canary; data tests deselected): **441 passed**; the two script-style ingest tests run from `rag/ingest`: 26 passed; data tests (9 geodata + the real-index canary): 10 passed; backend: **323 passed, 1 skipped**; geodata unit suite 20 of 20. New tests: 69 (harness 27, canary 2, metrics 8, engines 4, runner 2, dedupe 4, robustness 3, OCR 3, glossary rewrite, report path 1, plus the parametrised comparator cases). Acceptance: (1) Part 0 done as listed: **met**. (2) query tables and card with counts per set and objective, with and without the comparator key: **met**. (3) deterministic folds, hash match, no split group or block: **met**. (4) canary for every fold on the fixture index and on the real index for one fold; chunks without metadata counted (0): **met**. (5) Tier 1 re-indexed with the Habtamu papers, index hash recorded: **met**. (6) baselines on both splits, report and metrics.json, two runs identical to the third decimal: **met**. (7) P7 numbers reproduced within one sd on `legacy_68`; full-protocol switch check with a clear recommendation: **met**. (8) all tests pass, nothing committed: **met**.

**Files.** New: `model/harness/{__init__,queries,folds,mask,run,report,release_check,test_harness,test_run}.py`, `model/harness/README.md`, `model/metrics.py`, `model/test_metrics.py`, `model/engines/{__init__,base,random_engine,practice_prior,nearest_studies,m0_current,test_engines}.py`, `pipelines/evidence/{dedupe,test_dedupe}.py`, `rag/test_mask_canary.py`, `data/evidence/harness/{queries_card.md,queries_summary.json,folds_spatial.csv,folds_study.csv,folds_manifest.json}` (parquet tables ignored), `data/evidence/cards/dedupe.md`, `model/reports/eval_2026-11-11_{et_baselines_a,all_baselines_a,legacy68_m0}.md` + `figures/`. Modified: `.gitignore`, `model/train_model.py`, `model/test_evaluate.py`, `pipelines/geodata/layers/terrain.py`, `pipelines/geodata/test_robustness.py`, `pipelines/requirements.txt` (pillow pinned, matplotlib 3.10.8 added and installed in the venv), `rag/retrieve.py`, `rag/graph/query.py`, `rag/graph/test_glossary_sync.py`, `rag/ingest/{parse_and_chunk,build_index,ingest_guidelines,test_ingest_guidelines}.py`, `rag/corpus/chunks.jsonl` (the re-chunked Tier 1, tracked), `data/evidence/store_manifest.json`, `data/evidence/registry_ET.json`; the store parquet/CSV (ignored) carry the 49 `dup_of` flags. Git-ignored outputs on disk: `model/harness/runs/{et_baselines_a,et_baselines_b,all_baselines_a,legacy68_m0}/`, `model/artifacts/release_check/`, the rebuilt `rag/index/store` (`era_corpus` 2,788). `backend/.env` untouched. Nothing committed.

**Decisions and judgement calls.** (a) Null comparator text is classed `other` (39 of 414 queries come only from such rows) rather than guessed as "no practice". (b) A partially answered query counts as abstained (above). (c) One paper is chunked once per DOI, with every study id of the paper on its chunks (otherwise the Habtamu sheet's one-row-per-contrast-set manifest put the same paper into the index up to ten times). (d) `m0_current` builds category maps on the whole dataset as the P7 protocol does (a fixed vocabulary, no target information). (e) The pair-pooled C-index is reported beside the Appendix B per-query C-index for continuity. (f) `practice_prior` falls back to the family mean of the objective group before the practice's own mean over other groups. (g) The random engine is seeded per query, not per repetition, so its sd across repetitions is 0 by construction.

**Open items.** `post_2024` holds 5 queries: the memorisation check for Methodology 2 needs the Habtamu geocoding confirmations (381 rows wait as `geocoded_llm_unchecked`) and more 2024-2025 multi-practice studies. The global set is 39 queries. No baseline gives calibrated 80 % intervals; conformal intervals on grouped folds are an E5 item. `m0_current` abstains on 46 % of ET queries (non-legacy outcomes, unlabeled candidates, country precision); M1 v2 must cover the canonical outcomes. `nearest_studies` with k_min = 3 abstains on 53 %; the threshold and the distance weights are E5 ablations. The ERA chunk texts changed for 448 chunks with the pypdf version; if the P3/P5 retrieval evaluation (`eval_retrieval.py`) is rerun it will not be byte-comparable with the August 2026 baseline. The expert-panel and citation-precision metrics of roadmap 11.3 are not in the harness yet (no method produces citations beyond study ids).

**Needs local verification.** Nothing: every run, test and check above ran on the owner's machine in this session (the re-index used the configured OpenAI key, 2,788 chunks). Not done: a Methodology 2 or hybrid engine (E5/E6), the retrieval evaluation rerun on the new index, the backend switch itself.

### Review (Senior Engineer): E4 APPROVED ✅; next E5 (Methodology 1 v2); E6 after it (11 Nov 2026)

**Verified** by reading the E4 block, the harness README, `queries_summary.json` and the reports on the owner's machine. The harness is what the roadmap asked for: one query set (375 ET queries with at least two practices, 185 with at least three, against 68 under P7), deterministic study and spatial folds, one Mask enforced in rows, retrieval and graph with a canary on every fold, one metric library and report, determinism to the third decimal, and P7 continuity (top-1 0.521, pooled C 0.697, median rho 0.506). Part 0 carry-overs are closed, including the honest finding that the glossary test, not the data, was stale.

**Decisions on the judgement calls.** (a) Null comparator classed `other`: accepted. (b) A partially answered query counts as abstained: accepted as a definition, but it means each method is scored on a different subset, which can flatter a method that abstains more. From E5 on, the headline uses **full coverage** (abstentions filled by `practice_prior`, labelled `<method>+prior`) and the **common subset**, with paired bootstrap differences; the per-method answered metrics become secondary (E5 Part 0). (c) One paper chunked once per DOI with all its study ids: accepted; the pypdf text change on 448 ERA chunks is accepted, and E5 Part 0 records a new retrieval baseline on the E4 index. (d) to (g): accepted.

**Reading of the baselines.** The current model is the best ranker where it can answer, but it answers only 54% of the Ethiopian queries; the practice prior already beats chance everywhere with full coverage; intervals are uncalibrated across the board (prior 13%, model 77%, nearest studies 28% coverage at 80% nominal); economics is the weakest objective for every method; the global and post-2024 sets are too small for headline use (39 and 5 queries), so the memorisation check for Methodology 2 will rely on the no-retrieval variant against the retrieval variant rather than on post-2024 studies alone.

**Release switch.** The full-protocol check moves every ranking metric by less than one sd: the owner switches `GEODATA_RELEASE=ET/2026.1` in `backend/.env` locally now; the server follows with the deployment batch.

**Sequencing.** E5 and E6 touch the same engine registry, harness runner and `progress.md`, and the parallel sessions of E2 and E3 left a stale git lock; they run one after the other: **E5 now**, E6 (Methodology 2) when E5 is approved, then E7 (comparison, decision and fusion v2).

**Next steps.** Phase **E5: Methodology 1 v2** (`docs/briefs/E5_methodology1_v2.md`): implement exactly, verify every item under Acceptance, append the E5 report block here, and stop.

## Phase E5 — Methodology 1 v2, the evidence model (11–12 Nov 2026)

**Result first.** The success criterion stated in the brief is **not met**. On the ET set, spatial split, full coverage, `m1_v2` beats `practice_prior` on top-1 hit (+0.051 [+0.020, +0.085]) and C-index (+0.025 [+0.002, +0.048]), and its 80 % intervals cover **0.817** of held-out effects (target 0.75 to 0.85). It does **not** beat `m0_current+prior`: top-1 +0.038 [−0.001, +0.077] and C-index +0.026 [−0.005, +0.055], both intervals touching zero. Nothing was tuned against the outer folds after seeing this. What M1 v2 does deliver: it answers 100 % of the 375 ET queries (the current model answers 54 %), it is the best method under full coverage on every ranking metric on both splits, its intervals are calibrated (the baselines cover 13 to 49 %), and it matches or beats the current model on the legacy 68 cells.

**Built.**
- **Part 0, harness.** `model/metrics.py`: `fill_abstentions` (the `<method>+prior` full-coverage variants), `common_subset` (queries every compared method answered in every repetition, with its size), `paired_bootstrap` (query-level, 1,000 draws, seeded; "beats" only when the interval excludes zero), wired into `model/harness/run.py` (`metrics.json` keys `full_coverage`, `common_subset`, `paired`; `--no-fill`; `--rescore` re-scores old runs) and the report (full coverage and common subset first, paired differences, per-method answered tables as a secondary section). 2 new metric tests. The runner now also records engine parameters after fitting (per-fold choices). Reference run `et_baselines_c`: the E4 metrics of `et_baselines_a` reproduce with 0 differences at 3 decimals. **Retrieval baseline on the E4 index** (`rag/eval/results/retrieval_baseline_e4index.md`, index hash `3dc54515…`): `queries.jsonl` success@8 0.520 (August index 0.560), MRR 0.315 (0.300); `queries_v2.jsonl` success@8 0.511 (0.556), MRR 0.338 (0.328). The silver labels know only ERA studies, so the 1,600 new Habtamu chunks can only displace labelled chunks; the chat evaluation does not use the index.
- **Part 1, data** (`model/m1/data.py`). Harness-eligible store rows after `mask.filter_rows`; target `y = direction × lrr`; features: the 27 release layers (or the 9 legacy numeric layers), belt, Köppen class, land cover, crop group, practice family, outcome id, objective group, source, quality flag, location precision, duration, `ctx_missing`, practice components (multi-hot, 49) and the practice target encoding with counts (smoothed, out-of-fold on the inner folds). Weights: capped inverse variance (store `weight`) or quality default. Inner folds: study-grouped, P7 greedy assigner. Country-precision rows use the reported rainfall, altitude and slope and the `ctx_missing` flag.
- **Part 2, components** (`model/m1/`). `regressor.py` (HistGBM on `y`, 4-setting grid scored by the inner pooled C-index over training queries); `ranker.py` (LightGBM 4.6.0 `LGBMRanker` lambdarank, installed cleanly with numpy 2.4.6 and pinned; graded relevance = rank within the cell; symmetric pairwise HistGBM fallback; no site identifiers in the features; about 331 training queries and 977 items per outer fold); `matched.py` (k nearest training sites by standardised context distance, DerSimonian–Laird random-effects pooling with distance decay, k and decay tuned on inner folds, abstains below 3 groups); `prior.py` (empirical Bayes per practice and objective group, shrunk toward component, family and grand means, kappa from method-of-moments variances); `stack.py` (ridge per availability pattern on standardised inner out-of-fold scores, or rank averaging when the ridge does not beat it on the inner folds; lead source = largest contribution); `conformal.py` (normalised split conformal, difficulty = 0.05 + matched spread + 0.5 × distance to the nearest site, finite-sample 80 % quantile of the inner out-of-fold residuals); `select.py` (grouped permutation importance on the inner folds; groups whose permutation does not lower the inner score are dropped); `engine.py` (the nested fit and the fallback chain); `model/engines/m1_v2.py` (the harness engine and 15 variants), registered in `model/engines/__init__.py`.
- **Part 4, artifact and serving.** `python -m model.m1.train --release ET/2026.1` writes `model/artifacts/m1_v2/` (`m1_v2.joblib` git-ignored; `config.json` with store, release, query, fold and index hashes; `features.json`; `feature_stability.json`; `per_fold_choices.json`; `model_card.md`). Backend: `ADVISOR_ENGINE` (`legacy` default, `m1_v2` optional) and `M1_ARTIFACT_DIR` settings; `app/services/m1_service.py` (loads the artifact, fails fast at startup when enabled and missing); new `POST /rank` (any registry challenge and objective; 503 on the legacy engine, 422 for unknown ids); additive `m1_v2` list on `/advise` and `advisor_engine` on `/metadata`; lead sources mapped to the fusion labels (model → model-led, matched studies → study-led, prior → documented). `recommend.py`, `csa_model.joblib` and the default path are untouched. 6 backend tests on a fixture artifact. No UI change.

**Headline, ET set, full coverage** (mean ± sd across 5 × 5; 375 queries).

| method | split | top-1 | chance | C-index | C pooled | NDCG@3 | RMSE | 80 % cov. | width |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **m1_v2** | spatial | **0.519 ± 0.024** | 0.396 | **0.603 ± 0.019** | 0.624 | **0.830** | 0.448 | **0.817** | 1.30 |
| m0_current+prior | spatial | 0.482 ± 0.012 | 0.396 | 0.578 ± 0.012 | 0.587 | 0.797 | 0.456 | 0.479 | 0.65 |
| nearest_studies+prior | spatial | 0.460 ± 0.011 | 0.396 | 0.579 ± 0.004 | 0.582 | 0.785 | 0.473 | 0.194 | 0.24 |
| practice_prior | spatial | 0.469 ± 0.022 | 0.396 | 0.578 ± 0.012 | 0.588 | 0.798 | 0.460 | 0.129 | 0.13 |
| **m1_v2** | study | **0.546 ± 0.017** | 0.396 | **0.618 ± 0.019** | 0.650 | **0.844** | 0.446 | **0.800** | 1.27 |
| m0_current+prior | study | 0.505 ± 0.010 | 0.396 | 0.596 ± 0.009 | 0.628 | 0.812 | 0.448 | 0.486 | 0.65 |
| nearest_studies+prior | study | 0.482 ± 0.023 | 0.396 | 0.581 ± 0.019 | 0.610 | 0.799 | 0.471 | 0.197 | 0.25 |
| practice_prior | study | 0.480 ± 0.013 | 0.396 | 0.575 ± 0.011 | 0.615 | 0.809 | 0.456 | 0.130 | 0.14 |

**Paired differences, M1 v2 minus other** (95 % bootstrap; * = excludes zero).

| vs | split | top-1 | C-index | NDCG@3 |
|---|---|---:|---:|---:|
| practice_prior | spatial | +0.051 [+0.020, +0.085] * | +0.025 [+0.002, +0.048] * | +0.032 [+0.019, +0.047] * |
| m0_current+prior | spatial | +0.038 [−0.001, +0.077] | +0.026 [−0.005, +0.055] | +0.033 [+0.017, +0.053] * |
| nearest_studies+prior | spatial | +0.060 [+0.031, +0.097] * | +0.025 [−0.005, +0.052] | +0.045 [+0.030, +0.060] * |
| practice_prior | study | +0.066 [+0.037, +0.096] * | +0.043 [+0.020, +0.067] * | +0.035 [+0.022, +0.048] * |
| m0_current+prior | study | +0.041 [+0.005, +0.076] * | +0.022 [−0.009, +0.051] | +0.033 [+0.019, +0.046] * |
| nearest_studies+prior | study | +0.064 [+0.030, +0.102] * | +0.037 [+0.005, +0.066] * | +0.045 [+0.032, +0.059] * |

**Common subset** (queries all four answered: spatial n = 87, study n = 83; top-1 / C-index): spatial m1_v2 0.634 / 0.636, m0_current 0.600 / 0.624, nearest_studies 0.630 / 0.659, practice_prior 0.586 / 0.603; study m1_v2 0.684 / 0.686, m0_current 0.641 / 0.674, nearest_studies 0.670 / 0.697, practice_prior 0.600 / 0.623. On this subset matched studies order pairs best.

**Components** (each alone, the shrunken prior answering what it cannot; spatial / study, top-1 and C-index): regressor 0.492 / 0.590 and 0.527 / 0.612; **ranker 0.514 / 0.613 and 0.516 / 0.603**; matched studies 0.438 / 0.558 and 0.435 / 0.552; shrunken prior 0.475 / 0.585 and 0.483 / 0.575 (the E4 prior: 0.469 / 0.578). The within-study ranker carries most of the gain; alone it has the best spatial C-index of any configuration.

**Ablations** (spatial, M1 v2 minus ablation, top-1 / C-index; * = interval excludes zero): ranker removed +0.034 * / +0.026 *; stacker forced to ridge +0.058 * / +0.035 *; context reduced to the 11 legacy layers +0.019 * / +0.001; no inner tuning or selection +0.013 / +0.008; belt removed +0.002 / −0.001; matched studies removed +0.003 / −0.006; country-precision rows removed −0.004 / +0.001; Habtamu rows removed −0.009 / −0.006; weights quality default −0.001 / −0.003; stacker rank averaging −0.006 / −0.007. Reading: the ranker and the v2 context layers help; the belt adds nothing beyond the context vector (the roadmap's claim holds); matched studies, the Habtamu rows and the weight scheme do not move the ranking measurably. All ablations stay calibrated (0.79 to 0.82).

**Calibration** (80 % intervals, held-out items, spatial / study): overall 0.825 / 0.817 at a median width of 1.33 lrr; economics 0.850 / 0.840, productivity 0.839 / 0.832, soil health 0.895 / 0.905, water 0.732 / 0.715, livestock 0.707 / 0.690 (the two thin groups under-cover; resilience 30 items, not read). Lead sources of M1 v2 items: model 84.1 %, matched studies 9.0 %, prior 6.9 %.

**Breakdowns** (spatial, M1 v2 top-1 / C-index): productivity 0.48 / 0.62 (188 queries), economics 0.58 / 0.63 (71, the E4 weak spot now the best group), water 0.54 / 0.52 (47), livestock 0.56 / 0.52 (34), soil health 0.54 / 0.65 (32). Full tables by challenge, belt, source and precision in the report.

**All set** (414 queries, spatial / study): m1_v2 top-1 0.524 / 0.542, C-index 0.601 / 0.610; m0_current+prior 0.494 / 0.512 and 0.583 / 0.597; practice_prior 0.483 / 0.490 and 0.584 / 0.578.

**Continuity** (legacy 68 cells, P7 grouped folds, 10 × 5): m0_current top-1 0.521 ± 0.030, pooled C 0.697, NDCG@3 0.840; **m1_v2 top-1 0.537 ± 0.049, pooled C 0.705, NDCG@3 0.854**.

**Nested, never leaky.** Every learned quantity (regressor grid, matched k and decay, feature selection, target encoding, stacker weights and choice, conformal quantile, prior variances) is fitted inside the outer training fold on inner study-grouped folds. The canary test (`model/m1/test_m1.py`) fits with and without a held-out canary study that carries an absurd effect (+5 lrr): features, stacker patterns and choice, conformal quantile, prior and the canary practice's estimate are identical, while the same canary unmasked does move the estimate.

**Feature selection.** Kept groups per spatial outer fold (repetition 0): 83, 85, 84, 80 and 86 columns; `ctx_missing` was dropped in every fold. **Stable in at least 4 of 5 folds: 80 columns**, served exactly. Unstable (dropped in 2 or more folds): land cover, location precision, source, aridity index, distance to stream, dry-season length, CHIRPS rainfall mean, bulk density, SOC, TWI, duration. `soil_depth_bedrock`, Köppen class and travel time survived.

**Decisions.**
1. **The served stacker is the choice made inside the majority of outer folds (rank averaging, 8 of 10 fits, all 5 spatial folds)**, not the choice of the final full-data fit (ridge, by pooled C-index 0.684 against 0.667, although rank averaging had the better inner top-1). This is the same stability rule as for features. The ablation that forces ridge shows it is clearly worse out of fold (−0.058 top-1); serving it would ship a configuration the evaluation did not measure. **Reviewer to confirm.**
2. LightGBM is used for the ranker only; the regressor stays on sklearn.
3. Rank averaging takes the effect estimate from the first available of regressor, matched studies and prior; the interval comes from the conformal quantile of that estimate.
4. The single-process ablation run crashed with a segmentation fault (native code, exit 139) after about 3.5 hours, losing its predictions. The ablations were rerun one variant per process with `-X faulthandler`, three at a time; none crashed, and they were merged with the headline's predictions (`model/m1/report.py merge`, same queries and folds checked by hash). The crash was not reproduced and its cause is unknown (LightGBM or HistGBM threads under contention are the likely suspects).
5. Partial abstention keeps the E4 definition; full coverage is now the headline, as the review asked.

**Verified.** `py_compile` on every touched file. Root suites: **455 passed**; `rag/ingest` script tests 26 passed; `rag/eval` 13 passed; data tests 10 passed; backend **329 passed, 1 skipped** (the E3 release test teardown was fixed: it restored a stale extractor through `monkeypatch`, which broke any later test that starts the app). **Determinism:** `e5_headline_b` reproduces `e5_headline` with 0 metric differences at 3 decimals and identical prediction rows; a refit of the artifact reproduces its features, stacker and conformal quantile. **Live check** with `ADVISOR_ENGINE=m1_v2 GEODATA_RELEASE=ET/2026.1`: `/rank` ranks 38 registry candidates for soil erosion and 90 for low crop productivity, with intervals and fusion labels; `/advise` carries the `m1_v2` list; `/recommend` unchanged. Timings: one nested M1 v2 fit takes 30 to 90 s on the real store (inner grid and selection dominate). The 5 × 5 headline took 70 minutes for M1 v2 alone on a shared CPU; the ablations about 2 hours in three processes. The final fit takes 30 s with the fixed configuration.

**Acceptance.** (1) Part 0 in place, retrieval baseline recorded, `et_baselines_c` run: **met**. (2) `m1_v2` answers 100 % of ET queries with `lead_source` on every item: **met**. (3) Every learned quantity is fitted inside the outer fold, with the canary test: **met**. (4) Headline, component, ablation, calibration and continuity tables for both splits, and two runs identical to the third decimal: **met**. (5) Success criterion evaluated and reported plainly: **met, the criterion itself is not**. (6) Artifact with model card, backend behind `ADVISOR_ENGINE=m1_v2` with tests, default path unchanged: **met**. (7) All tests pass, nothing committed: **met**.

**Files.** New: `model/m1/{__init__,data,inner,regressor,ranker,matched,prior,stack,conformal,select,engine,train,stability,report,test_m1}.py`, `model/engines/m1_v2.py`, `app/backend/app/services/m1_service.py`, `app/backend/app/routers/rank.py`, `app/backend/tests/test_m1_engine.py`, `model/artifacts/m1_v2/{config.json,features.json,feature_stability.json,per_fold_choices.json,model_card.md}` (`m1_v2.joblib` ignored), `model/reports/eval_2026-11-12_m1v2.md` (+ the per-run reports and figures), `rag/eval/results/retrieval_{baseline_e4index.md,metrics_e4index.*,metrics_v2_e4index.*}`. Modified: `model/metrics.py`, `model/test_metrics.py`, `model/harness/{run,report,test_run,README}`, `model/engines/__init__.py`, `app/backend/app/{config,main,schemas,metadata_service}.py`, `app/backend/app/services/advisory_service.py`, `app/backend/tests/test_geodata_release.py`, `.gitignore` (`model/artifacts/m1_v2/*.joblib`), `pipelines/requirements.txt` (`lightgbm==4.6.0`). Runs (git-ignored): `et_baselines_c`, `e5_headline`, `e5_headline_b`, `e5_all`, `e5_components`, `e5_abl_*`, `e5_ablations` (merged), `e5_legacy68`. The E4 work is still uncommitted in the same tree.

**Open items.**
- **The smallest change worth testing** for the criterion: let the stacker weight the ranker more. The ranker alone has a spatial C-index of 0.613 against 0.603 for the full stack, and rank averaging gives it one vote in four. Test rank averaging over ranker, regressor and prior only (matched studies removed costs nothing), or a learned blend scored by top-1 as well as C on the inner folds. This needs a new nested run, never a choice read off the outer folds. The gap to `m0_current+prior` is +0.038 top-1 with a lower bound of −0.001, so a modest gain would clear it.
- Under-coverage for water (0.73) and livestock (0.71): conformal by objective group (Mondrian) is the standard fix.
- The fused `/advise` path still leads with the legacy model; how `m1_v2` replaces or joins it is E7 (fusion v2), with the reviewer's choice of default.
- **For E6 (Methodology 2):** the harness now scores any engine under full coverage with paired differences. The E5 runs give M2 its reference rows on identical queries and folds. The masked retriever and the E4 index hash are ready.
- **For E7:** the stacker, the lead-source mapping and the conformal intervals are the inputs the fusion v2 gate needs (evidence density, nearest-site distance, interval width are all in the item records).
- The native crash of the long single-process run is unexplained; long evaluation runs should keep one variant per process.

### Review (Senior Engineer): E5 APPROVED ✅ (criterion not met, reported as such); next E6 with the E5.1 follow-up first (12 Nov 2026)

**Verified** by reading the E5 block, the report and the artifact files on the owner's machine. The work is what the brief asked for and the reporting is exemplary: the success criterion was stated before the runs, it is not met against `m0_current+prior` on the spatial split (top-1 +0.038 [-0.001, +0.077], C-index +0.026 [-0.005, +0.055]), and nothing was tuned after seeing it.

**Reading.** Methodology 1 v2 is the best method on every ranking metric under full coverage on both splits, beats the practice prior with intervals excluding zero, beats the current model plus prior on NDCG@3 on both splits and on top-1 on the study split, answers 100% of queries against 54%, and is the only method with calibrated intervals (0.817 at 80%). Against the current model plus prior on the spatial split the point estimates favour M1 v2 but the data cannot yet separate them: 375 queries give intervals about 0.08 wide on top-1. The within-study ranker carries the gain; the belt adds nothing beyond the context vector, which supports the roadmap's design; matched studies and the Habtamu rows add nothing measurable to ranking. Economics, the weakest objective in E4, is now the best group. Water and livestock intervals under-cover (0.71 to 0.73).

**Decisions.**
1. **Served stacker: rank averaging, confirmed.** Serving the configuration chosen inside the majority of outer folds is right: it is the configuration the evaluation measured; ridge out of fold is clearly worse.
2. **One pre-registered follow-up, E5.1**, fixed today before any run: (a) the inner selection may also choose rank averaging over ranker, regressor and prior, or a ranker-weighted average (weight 2 or 3), scored on the inner folds by the mean of top-1 and C-index; (b) group-conditional (Mondrian) conformal quantiles. Run once, labelled post-hoc in every table, reported whatever the result; no further M1 variants before E7. It runs as Part 0 of E6.
3. M1 v2 enters E7 as Methodology 1. The pre-registered criterion is reported as not met in the manuscript, with the full-coverage and calibration results beside it.
4. Long evaluation runs keep one variant per process; the native crash stays an open note.

**Owner decisions for E6 (12 Nov 2026).** Evidence cards from all sources, including Habtamu's database, may be sent to the OpenAI API (the owner confirmed with the data holder). Models: `gpt-4o-mini` for all variants, plus one stronger model on the owner's key for the full variant, run only after the owner sees the cost estimate; minimal evaluation design (spatial split, repetition 0, all 375 ET queries, about 375 calls per variant); cap 100 USD for the phase.

**Next steps.** Phase **E6: E5.1 follow-up, then Methodology 2** (`docs/briefs/E6_methodology2.md`): implement exactly, stop for the owner's go before the paid stronger-model run, verify every item under Acceptance, append the E6 report block here, and stop.

## Phase E6 — E5.1 follow-up, then Methodology 2: LLM evidence reasoning (12 Nov 2026)

**Built** the E5.1 follow-up of Methodology 1, then Methodology 2 as a harness engine with four pre-registered variants, run on the owner's minimal design: spatial split, repetition 0, all 375 ET queries, one call per query per variant. Full report: `model/reports/eval_2026-11-12_m2.md`; E5.1 harness report: `model/reports/eval_2026-11-12_e6_e51.md`.

### E5.1 (post-hoc, pre-registered 12 Nov 2026)

Both pre-registered changes are opt-in settings (`stacker_set="e51"`, `conformal_by_group=True`), so the E5 default is unchanged. A one-repetition rerun of E5 `m1_v2` after the change matched all 1,093 E5 predictions exactly. `m1_v2_e51` ran on both splits, 5 × 5, in its own process (57 minutes).

**Full coverage** (mean across 5 × 5):

| method | split | top-1 | C-index | NDCG@3 | 80 % coverage | width |
|---|---|---:|---:|---:|---:|---:|
| M1 v2 E5.1 | spatial | 0.535 | 0.614 | 0.843 | 0.828 | 1.37 |
| M1 v2 (E5) | spatial | 0.519 | 0.603 | 0.830 | 0.817 | 1.30 |
| M1 v2 E5.1 | study | 0.549 | 0.618 | 0.858 | 0.813 | 1.36 |
| M1 v2 (E5) | study | 0.546 | 0.618 | 0.844 | 0.800 | 1.27 |

**Paired, E5.1 minus other** (95 % bootstrap; * = excludes zero):

| comparison | split | top-1 | C-index | NDCG@3 |
|---|---|---:|---:|---:|
| minus E5 | spatial | +0.015 [−0.007, +0.037] | +0.011 [−0.008, +0.031] | +0.013 * |
| minus current model + prior | spatial | +0.053 [+0.014, +0.098] * | +0.037 [+0.003, +0.067] * | +0.046 * |
| minus E5 | study | +0.004 [−0.026, +0.030] | +0.000 [−0.023, +0.023] | +0.014 * |

- **Rebuild rule not met:** neither the top-1 nor the C-index interval over E5 on the spatial split excludes zero, so `model/artifacts/m1_v2/` stays the E5 artifact.
- **Calibration per objective group:** Mondrian conformal brings livestock from 0.71 to 0.77 and water from 0.73 to 0.79 on the spatial split. Soil health moves from 0.90 to 0.85 with narrower intervals; overall 0.83.
- **Stacker choices** inside the 50 outer fits: ranker weight 3 in 20, ranker weight 2 in 16, three-component average in 6, four-component average in 5, ridge in 3.
- As the brief says, no further Methodology 1 variants run before E7.

### Methodology 2 headline (spatial, repetition 0, 375 ET queries, full coverage)

| method | model | top-1 | C-index | NDCG@3 | abstention before fill |
|---|---|---:|---:|---:|---:|
| `m2_zero` + prior | gpt-4o-mini | 0.517 | 0.628 | 0.823 | 9.1 % |
| `m2_cards` + prior | gpt-4o-mini | 0.477 | 0.566 | 0.801 | 31.2 % |
| `m2_rag` + prior | gpt-4o-mini | 0.480 | 0.563 | 0.802 | 29.9 % |
| `m2_graph` + prior | gpt-4o-mini | 0.491 | 0.580 | 0.802 | 28.0 % |
| `m2_zero` + prior | gpt-4.1-mini | **0.595** | **0.646** | **0.888** | 15.2 % |
| `m2_graph` + prior | gpt-4.1-mini | 0.523 | 0.594 | 0.828 | 20.8 % |
| M1 v2 (E5, its repetition-0 rows) | | 0.491 | 0.591 | 0.816 | 0 % |
| current model + prior | | 0.488 | 0.591 | 0.803 | |
| practice prior | | 0.445 | 0.570 | 0.791 | |

Chance top-1 is 0.396. Repetition 0 is a weaker fold assignment for M1 v2 than its five-repetition mean (top-1 0.519).

**Paired differences** (95 % bootstrap; * = excludes zero):

| comparison | top-1 | C-index |
|---|---:|---:|
| `m2_graph`+prior (4o-mini) minus M1 v2 | −0.000 [−0.056, +0.053] | −0.011 [−0.052, +0.034] |
| `m2_graph`+prior (4.1-mini) minus M1 v2 | +0.032 [−0.024, +0.085] | +0.003 [−0.039, +0.047] |
| `m2_zero`+prior (4.1-mini) minus M1 v2 | +0.104 [+0.045, +0.165] * | +0.055 [+0.014, +0.095] * |
| `m2_zero`+prior (4.1-mini) minus current model + prior | +0.107 [+0.043, +0.171] * | +0.055 [+0.008, +0.102] * |

### Variant ladder, memorisation and the stronger model

- **Evidence lowers ranking quality with both models.** With `gpt-4o-mini`, cards minus zero is −0.040 [−0.101, +0.019] on top-1 and −0.063 [−0.109, −0.015] * on C-index. With `gpt-4.1-mini`, graph minus zero is −0.072 [−0.131, −0.016] * on top-1 and −0.052 [−0.096, −0.004] * on C-index.
- **Passages and graph facts add almost nothing beyond the cards.** Graph minus RAG is +0.011 top-1 and +0.017 C-index; neither excludes zero.
- **Part of the drop is abstention.** With evidence the model says "unknown" more often, and those queries fall back to the prior. Even on the queries it answers, the graph variant does not reach the zero variant with `gpt-4.1-mini` (top-1 0.579 against 0.635).
- **The stronger model is better.** `gpt-4.1-mini` minus `gpt-4o-mini` is +0.077 * top-1 for `m2_zero` and +0.032 top-1 for `m2_graph`, the latter not excluding zero.
- **Memorisation cannot be separated.** The ET set has 0 `post_2024` queries; the global set has 5, which the harness withholds below 20 queries. The zero-shot result may come from general agronomic knowledge, from knowing these published studies, or both. This is not interpreted here; it is the first open item for E7.

**Global set** (39 queries outside Ethiopia, `m2_graph`, gpt-4o-mini): top-1 0.538 and C-index 0.549 with the prior fill, against the practice prior's 0.590 and 0.609.

### Stability (40 fixed queries, `m2_graph`, gpt-4o-mini)

| pair | top-1 agreement | mean Kendall tau |
|---|---:|---:|
| repeat 1 vs repeat 2 | 100 % | 0.98 |
| main vs each repeat | 100 % | 0.96 and 0.98 |
| shuffle 1 vs shuffle 2 | 89.7 % | 0.85 |
| main vs each shuffle | 86.5 % and 83.8 % | 0.73 and 0.67 |

Repeats are fresh calls with their own cache keys. Candidate order matters: it changes the top pick in 10 to 16 % of queries.

### Citation validity, numeric guard, cost and calibration

- **Citations:** 0 cited ids outside the prompt in any final answer, all variants. Every cited card's practice is the ranked item or a related practice shown for it (100 %). 85 to 87 % of items cite a card with `gpt-4o-mini` and 97 % with `gpt-4.1-mini`. First answers invented 1 to 9 ids per evidence variant, and 38 in the 4.1-mini zero variant, which had no cards to cite. The retry with the validation error corrected all but the queries counted as invalid twice (0 to 3 per variant).
- **Numeric guard:** estimates and intervals are computed by code from the cited cards of the practice only. A test feeds a reason containing numbers and checks that none reaches `est_lrr`, `lo`, `hi`, the score or the citations. The reason text is logged and never parsed.
- **Cost and latency per query:** `gpt-4o-mini` costs 0.0002 USD (zero) to 0.0005 USD (graph), median 2.7 to 3.1 s, p95 up to 7.8 s. `gpt-4.1-mini` costs 0.0006 to 0.0014 USD, median 1.7 to 2.1 s. The phase total is **1.42 USD** of the 100 USD cap, including the stability check, the global run, one rerun call and the embeddings.
- **Card-derived intervals** cover 36 to 39 % of held-out effects at 80 %, as expected; reported, not fixed.

**Files.**
- **New:** `model/m2/{__init__,cards,knowledge,prompt,client,engine,run,report,test_m2}.py`, `model/m2/prices.yaml`, `model/m2/model_card.md`.
- **New reports:** `model/reports/eval_2026-11-12_m2.md`, `model/reports/eval_2026-11-12_e6_e51.md` (with `figures/e6_e51/`).
- **Changed:** `model/m1/{stack,conformal,engine,test_m1}.py`, `model/engines/m1_v2.py` (adds the `m1_v2_e51` variant).
- **Changed:** `docs/decisions/enhancement_v2.md` (addendum: data sent to the API and the model scope).
- **Changed:** `.gitignore` (`model/m2/cache/`) and `pipelines/requirements.txt` (`tiktoken==0.12.0`).
- **Runs** (git-ignored): `e51_m1`, `e51_e5check`, `e6_e51`, `e6_m2_{zero,cards,rag,graph}_et` with `_b` reruns, `e6_m2_{zero,graph}__gpt-4.1-mini_et` with `_b` reruns, `e6_m2_graph_global`, `e6_m2_stability`, `e6_m2_headline`.

**Decisions.**
1. **The API is called with `httpx`, as the backend does;** no SDK dependency.
2. **Structured output** uses a strict JSON schema with candidate ids as an enum. Card ids are free text so that invented ids stay measurable.
3. **Prompt limits follow the updated Part 5:** 4 cards per candidate, 32 per prompt, 4 passages per prompt, 60 tokens of graph facts. The largest prompt is 5,436 tokens: 11-candidate queries reach the 32-card cap. The mean graph prompt is 2,261 tokens.
4. **The run has three steps:** build every prompt under its fold's mask without calling, send the uncached ones concurrently through the capped client, then score through the harness from the cache.
5. **Stability queries** are the 40 ET queries first by the hash of their id. Shuffles always change the order; a shuffle that equals the original order is rotated by one.
6. **Owner decision (12 Nov):** `gpt-4.1-mini` is the stronger model, and Methodology 2 is evaluated with deployable low-cost models only. The key lists no other chat model. Recorded in the model card and the decision addendum.
7. **The reviewer's addition is in:** the stronger model ran `m2_zero` as well as `m2_graph`.

**Incidents.**
1. **Ledger corruption.** Four processes appending to one ledger file interleaved lines, and the first launch failed before scoring anything. Each process now writes its own ledger file; the total sums them all and skips another process's half-written line (test). The ledger was rebuilt from the cached answers and the intact embedding lines; the damaged file is kept as `ledger_corrupt_20261112.bak`.
2. **Tied passages swapped on rerun.** One query's two tied guideline passages came back in swapped order, from the approximate dense search. Retrieval results are now cached on disk by query text and mask (test). `m2_rag` and `m2_graph` were rerun from the cache; one prompt changed, costing one call.
3. **Two bugs in the new code, found by the tests before any paid run.** A card shown as own evidence for one candidate and as related evidence for another was dropped from the first estimate. The Kendall tau sign was inverted. Both fixed.

**Verified.**
- `py_compile` on every touched file.
- Root suites (`model`, `pipelines`, `rag/graph`, `rag/ingest/wocat`, the retrieval-tier, mask-canary and guideline tests): **480 passed**. `rag/eval`: 13 passed. Backend: **329 passed, 1 skipped**, including loading the E5 artifact pickled before the calibrator change. M1 and M2 tests after the last change: 27 passed.
- **Determinism:** two runs from the cache give identical predictions for all six M2 runs (3,279 rows each, offline reruns).
- **E5 unchanged:** the rerun of E5 `m1_v2` matched bit for bit.

**Acceptance.**
1. E5.1 ran once with the two pre-registered changes, labelled post-hoc and reported against E5. The rebuild rule was not met, so the artifact is kept: **met**.
2. Cards, passages and graph facts are masked (three canary tests). The dry run gives the token and cost estimate. The budget-cap tests stop a request before sending: **met**.
3. All four `gpt-4o-mini` variants and the stronger model (after the owner's go, on `m2_zero` and `m2_graph`) ran on the 375 ET queries, spatial repetition 0. Full coverage, common subset and paired differences against the other methods on the same folds are reported: **met**.
4. Stability, citation validity, numeric guard and cost tables are reported, with 0 cited ids outside the prompt: **met**.
5. Two runs from the cache give identical predictions: **met**.
6. All tests pass; nothing committed: **met**.

**Open items for E7.**
1. **Memorisation versus knowledge.** `gpt-4.1-mini` with no evidence is the best ranker measured so far (top-1 +0.104 over M1 v2), but the ET set has no post-2024 queries to tell knowledge from recall of the published studies. A held-out set the model cannot have read is needed before this can count.
2. **Why evidence hurts.** More abstention, order sensitivity, or the cards pulling the model toward noisy single-site effects. The per-query logs (`responses.jsonl`) allow this to be examined without new calls.
3. **Intervals.** M2's card-derived intervals are not calibrated, while M1 v2's are. Any hybrid would take numbers from M1 (doctrine 1) and might take the ranking from the LLM.
4. **Single-repetition caveat.** The M2 comparison uses one fold assignment, on which M1 v2 is below its five-repetition mean.

**Needs local verification.** None beyond the owner's review. The price table (`model/m2/prices.yaml`) has not yet been checked against the current OpenAI price list; the ledger's dollar figures depend on it.

### Review (Senior Engineer): E6 APPROVED ✅; the LLM result is promising but not yet trusted; next E7 (12 Nov 2026)

**Verified** by reading the E6 block and `model/reports/eval_2026-11-12_m2.md` on the owner's machine. The phase is complete and clean: masked cards, passages and graph facts with canaries; no cited id outside a prompt; the numeric guard tested; repeats stable; every run reproducible from the cache; 1.42 USD spent of 100. E5.1 did not meet its rebuild rule and the E5 artifact stays, exactly as pre-registered.

**The finding and why it is not yet accepted.** `gpt-4.1-mini` with no evidence is the best ranker measured (top-1 0.595, C-index 0.646 on the spatial repetition-0 folds; +0.104 and +0.055 over M1 v2), and evidence makes both models worse. Because `m2_zero` uses no data, its score does not depend on the folds, while M1 v2 sits below its five-repetition mean on repetition 0; the fair reference is the five-repetition mean (E7 A1). More importantly, three explanations predict the same score and have opposite consequences: location-aware knowledge, a generic ordering of practices (including the structure of trial designs, where combined treatments are usually built to win), or recall of the very studies the test queries come from. The test queries are published Ethiopian trials, mostly years before the model's training cutoff, and none is from after 2024. Until these are separated, the result cannot shape the product or be claimed in the manuscript.

**Decisions.**
1. M2 is evaluated with deployable models only (owner, 12 Nov); `gpt-4.1-mini` is the stronger model. Accepted.
2. Evidence cards, passages and graph facts in the prompt lowered ranking quality with both models, partly through more "unknown" answers; this is a finding to report, not a defect to tune away in E6.
3. E7 is pre-registered today: validity tests first (names only, context swap, heuristic baselines, recall probes, fair reference), then two hybrids that let the LLM reorder evidence-backed candidates while every number, interval and citation still comes from M1 v2, then a decision by fixed branches. Any LLM influence on ordering needs an owner-approved amendment to the evidence fusion doctrine.
4. A fresh test set of Ethiopian multi-practice trials published after June 2024 is requested from the data team (Habtamu's extraction format); it is the only clean test against recall and the strongest evidence for the manuscript. E7 does not wait for it.
5. Cost ledger per process and the cached retrieval results: accepted. Prices in `model/m2/prices.yaml` stay to be checked by the owner (the dollar figures depend on them; the amounts are small).

**Next steps.** Phase **E7: validity of the LLM result, the hybrid, and the methodology decision** (`docs/briefs/E7_validity_hybrid_decision.md`): implement exactly, verify every item under Acceptance, append the E7 report block here, and stop.
