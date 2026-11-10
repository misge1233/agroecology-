# E2: reviews applied, geocoding, guidelines and catalogue in the knowledge layer (10 Nov 2026)

**Binding:** `docs/roadmap/AE+_enhancement_roadmap.md` (sections 5.2, 5.3, 5.5, 12.2), `docs/decisions/enhancement_v2.md`, `docs/decisions/evidence_fusion.md`, `docs/decisions/rag_design.md`, CLAUDE.md, the E1 report in `progress.md`, this brief.

**Purpose.** Make the evidence store usable for modelling and the knowledge layer complete: apply the human reviews produced after E1; give Habtamu's rows a map position where the papers allow it; bring the 62 government guidelines (Tier 2b) and the 30 catalogue entries into retrieval and the knowledge graph; extend Tier 1 with the open-access Habtamu papers. No model training, no UI change, no change to the advisory engine's ranking (the documented path may show the new sources through the existing evidence service, additively).

**Ground rules:** as E1 (production grade, additive, nothing dropped silently, no automatic acceptance, partner data out of git), plus:

- Every LLM call in this phase is one of two constrained, cached jobs (mapping proposals, site extraction) that send only labels, candidate ids and paper text to OpenAI; never the numbers of a dataset row. Cache files are git-ignored. Both jobs run only when `--llm` is passed and the key exists.
- Network steps run on the owner's machine; every download is listed with its URL in a manifest and is resumable.
- Report as an **E2 block in `progress.md`**, then stop. The owner commits.

**Do not regress:** E1 acceptance items (store build, reconciliation, registry endpoint), backend and frontend test suites, `python model/evaluate.py --quick`.

---

## Part A: apply the reviews

**A1. Outcome directions.** `pipelines/taxonomy/propose_mappings.py --apply-outcome-review data/taxonomy/review/outcomes_direction_review.csv`: for every row with `accepted = yes`, apply `proposed_decision`: `accept` and `flip` set `direction = proposed_direction`, `objective_group = proposed_group`, `status = reviewed`; `exclude` sets `status = excluded`, `direction` null (rows keep their `outcome_id` in the store but never count); `context_dependent` sets `status = context_dependent`, `direction` null, with the note kept; `merge_into` moves every alias to the target id and sets `status = merged`. Add `climate` to the `objective_group` enum (schema v1.1, recorded in `SCHEMA_VERSION` and the manifest). Rename the seed id `MEAN_TREE_HEIGHT_DIFFERENCXE` to `TREE_HEIGHT` and `SOIL_INFLITRATION_RATE_TRATION_RATES` is merged (ids with `status = seed` may be renamed once; the alias file records the old id in `notes`). Record `reviewer` and `date` from the sheet. The sheet from the Senior Engineer is a proposal: only rows the owner marks `accepted = yes` are applied; rows left empty stay as they are.

**A2. Alias reviews.** `--apply-review` ingests `HAB_practices_review.csv`, `HAB_outcomes_review.csv` and `practice_merges.csv` rows with `accepted = yes` (practices: new canonical practice when `practice_id = NEW:<id>`; merges: move aliases, mark the merged id `status = merged`). Rebuild the store and the registry; the registry report shows the rows that moved from pending to counted.

**A3. LLM mapping proposals (only if the owner says yes in the launch prompt).** Run `propose_mappings.py --llm` for the two Habtamu review sheets; the prompt holds the raw label, the top-10 candidate ids with their names and components, and the instruction to answer with one id or `NEW` plus a one-line reason; model fixed and recorded; cache in `review/llm_cache.jsonl`. Fill `llm_suggestion` only. Report agreement between the LLM and the rapidfuzz top-1 as a sanity figure.

---

## Part B: site geocoding for Habtamu's rows (roadmap 5.5)

**B1. Paper acquisition.** `pipelines/evidence/fetch_habtamu_papers.py`: for the 181 DOIs (and the 605 study ids without a DOI, by title search where `Study_ID` gives author and year), reuse `rag/ingest/fetch_papers.py` (wrap, never fork) to resolve open-access PDFs (Unpaywall and Crossref as that module does) into `rag/corpus/pdfs/` with manifest rows tagged `source: HAB` (the Tier 1 manifest gains a `source` column; existing rows get `ERA`). Non-OA papers are listed with their landing URL in `data/evidence/review/habtamu_papers_missing.csv` for the owner. Expected: a third to a half open access; report the actual.

**B2. Site extraction.** `pipelines/evidence/geocode_sites.py`:

- Input: one record per Habtamu study (`study_id`, DOI, title, `Agroecological_Zone` text, country, `Supporting Evidence` sentences) plus the paper text when available (first 4 pages and any "Materials and methods" or "Study area" section found by heading match).
- Extraction with `--llm`: constrained JSON `{sites: [{name, admin: [...], lat, lon, coordinate_source: "stated"|"none", quote}], confidence}`; without `--llm` a regex pass for decimal and DMS coordinates and the sentences that contain "located", "study area", "district", "woreda", "zone".
- Resolution: stated coordinates win (validated inside the country's bbox from `countries/<cc>.yaml` or a world bbox table); otherwise names are resolved against GeoNames (`ET.txt` for Ethiopia and `cities500.txt` for the rest, downloaded once by the owner into `pipelines/evidence/cache/geonames/`, URL in the manifest; licence CC BY 4.0 recorded), feature classes P and A, best match by token similarity and admin agreement; `loc_precision` set to `site` (stated coordinates or a populated place within 25 km of a named site), `district` (admin-2 centroid), `country` (nothing resolved).
- Output: `data/evidence/review/geocoding_review.csv` (study, site name, lat, lon, precision, method, confidence, the quote, `accepted`, `reviewer`, `date`) and a map `data/evidence/review/geocoding_review.html` (Leaflet, one marker per study, popup with the quote) for the reviewer.
- Store update: `--apply-geocoding` writes `lat`, `lon`, `loc_precision`, `loc_method = geocoded_llm_checked` for accepted rows and `geocoded_llm_unchecked` for the rest; the registry and cards are rebuilt. Unchecked rows stay out of training by the `loc_method` filter that E3 and E5 will apply.
- Acceptance: at least 90% of the 14 Ethiopian DOIs resolved to `site` or `district`; overall share reported; every row has a quote the reviewer can check.

---

## Part C: government guidelines as Tier 2b

**C1. Text extraction.** `rag/ingest/ingest_guidelines.py`: for every row of `rag/corpus/guidelines/manifest.csv`, extract page-wise text with `pdftotext -layout` (or PyMuPDF if already a dependency), write `rag/corpus/guidelines/texts/<doc_id>/page_<n>.txt`, and measure characters per page. Pages below 200 characters in a document where most pages are rich are treated as image pages and go through OCR with Tesseract (`eng` and `amh` language packs; the owner installs Tesseract; the brief lists the command). Documents with no extractable text at all (the 10 Nov check found low counts for `MoA_2026_Soil_Matters_Technical_Guide`, `MoA_2005_CBPWD_Guideline_Part1_A`, `MoA_2014_Manual_for_Runoff_Analysis`, `MoA_2011_Guideline_on_Irrigation_Agronomy`) are OCR'd whole. The card `rag/corpus/guidelines/ingest_report.md` lists per document: pages, characters, OCR pages, language detected.

**C2. Chunking and indexing.** Reuse `rag/ingest/chunk_guidance.py` and `build_index.py` (wrap, never fork): chunks of the same size as Tier 2, each carrying `doc_id`, `title`, `publisher`, `year`, `language`, `theme`, `page`, `tier = guidelines`. Amharic documents are chunked but flagged `language = am` so the retriever can filter by the interface language. Index into the existing Chroma store as a separate collection `guidelines` (the Tier 2 collection is untouched), with a `rag/corpus/guidelines/chunks.jsonl` mirror. Report chunk counts per theme.

**C3. Retrieval.** `rag/retrieve.py` gains the `guidelines` collection in the hybrid retriever with the same scoring as Tier 2 and a tier tag in every hit; the evidence service's documented path includes guideline hits in "how to implement" with citations in the form `MoA 2016, Guidelines for Development Agents on SWC, p. 34` (title from the manifest, page from the chunk). The numeric guard applies unchanged. Existing eval sets must give the same results when the new collection is disabled (`RAG_GUIDELINES_ENABLED=false`, default `true`).

**C4. Suitability statements (seed for eligibility, roadmap 7).** `pipelines/taxonomy/extract_suitability.py` scans guideline chunks and catalogue entries for slope ranges (`3-15%`, `above 50%`), rainfall bands, land-use mentions (cultivated, grazing, forest, degraded), belt names and soil depth or stoniness statements attached to a practice name found in `practices.csv` or its aliases; writes `data/taxonomy/review/suitability_review.csv` (practice_id, attribute, operator, value, unit, doc_id, page, quote, accepted). Rules only; no LLM in this part. Nothing is applied in E2; E5 consumes accepted rows.

---

## Part D: catalogue and guidelines in the knowledge graph

**D1. Schema additions** (`rag/graph/schema.py`, additive): node types `Challenge` (from `challenges.csv`), `CatalogueEntry` (`CAT_01..30`, attributes: name, category, farming system, scaling stage, scale, evidence base, limitations) and `GuidanceDoc` filled for guidelines (doc_id, title, publisher, year, language, theme); edge types `ADDRESSES_PROBLEM` (CatalogueEntry or Practice → Challenge, provenance `catalogue`), `DESCRIBED_BY` (Practice → CatalogueEntry, via the catalogue aliases of E1), `DOCUMENTED_IN` (Practice → GuidanceDoc, provenance `guidelines_title_match` when the practice name or an alias occurs in the document title or in at least 3 chunks; the count is an edge attribute), `SUITABLE_IN` (CatalogueEntry → AEZBelt or ContextClass, from the catalogue's "suitable land use and agroecology" text, rules only, provenance `catalogue_text`). `validate_graph()` extended; `build_graph.py` reads the taxonomy files and the manifests; `graph_report.json` shows the new counts.

**D2. Query API.** `rag/graph/query.py` gains `practices_for_challenge(challenge_id)`, `documents_for_practice(practice_id)` and `catalogue_entry(practice_id)`; the evidence service's documented path uses `documents_for_practice` to attach the catalogue entry and guideline documents to a practice card (additive fields in the response schema: `catalogue`, `guideline_docs`; the frontend ignores unknown fields today).

---

## Part E: tests, cards, report

- Unit tests: review appliers (fixture sheets covering every decision type), geocoding resolver (fixture GeoNames file, DMS and decimal regexes, bbox validation), guideline ingest (a 2-page fixture PDF built in the test with reportlab or a committed tiny PDF), chunk metadata, retriever tier tag, graph schema additions, query functions.
- Data tests (`@pytest.mark.data`): store rebuild after reviews keeps 19,753 rows; registry counts change only in the expected direction (more counted rows, never fewer, unless an exclusion removed them, and the diff is printed); 62 guideline documents ingested; graph validates.
- Cards: `cards/HAB.md` gains the geocoding section; `rag/corpus/guidelines/ingest_report.md`; `data/evidence/README.md` updated.
- `progress.md` E2 block with: review application counts, geocoding coverage by precision, OA paper share, guideline chunk counts by theme and language, OCR list, graph node and edge counts, retrieval sanity examples (three queries whose top hits are guideline pages, with page numbers), and the open items for the owner (missing papers, unresolved sites, suitability review sheet).

## Acceptance

1. Reviews applied only where `accepted = yes`; store and registry rebuilt; pending-review counts in the registry fall accordingly; schema v1.1 validated.
2. Geocoding sheet and map produced for all 605 Habtamu studies; Ethiopian coverage at least 90% at site or district precision; `--apply-geocoding` updates the store with the right `loc_method` values.
3. 62 guideline documents extracted (OCR where needed), chunked with page numbers, indexed in a separate collection, retrievable with tier tags; the documented path cites them with title and page; the existing Tier 1 and Tier 2 behaviour is unchanged when the collection is disabled.
4. Knowledge graph validates with the new node and edge types; counts reported; `practices_for_challenge` returns results for every exposed challenge.
5. Suitability review sheet written (rules only), nothing applied.
6. All tests pass; nothing committed.
