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
