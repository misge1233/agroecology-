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
