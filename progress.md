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
