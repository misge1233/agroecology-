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
