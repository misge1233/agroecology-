# RAG design decision record

**Date:** 18 Aug 2026 · **Status:** approved (research_project_plan.md §2)

## Decision

Add a retrieval-augmented generation layer whose **Phase-1 corpus is the set of
source studies behind the training data itself** — the ~300 DOI-linked ERA
studies (306 unique study codes, 295 unique DOIs in the raw
`ERA_Ethiopia_dataset.csv`) plus the Adimassu et al. CSA papers. Phase 2 expands
to CGSpace (REST API) and the GARDIAN-CIGI corpus (Hugging Face, 85,782 docs,
filtered to Ethiopia/agroecology).

## Why this corpus first

- **Perfect alignment:** the RAG explains exactly the evidence the model
  learned from — retrieved passages and predicted effects share provenance.
- **The linkage is the novelty:** every chunk carries `era_code` (= `Study_No_`),
  joining a retrieved passage to the exact training rows behind a
  recommendation. Free silver labels for retrieval evaluation.
- **Tractable:** ~300 papers, not 85k documents; quality-controllable for the
  manuscript's evaluation.

## Two named RAG functions

- **R1 — evidence grounding:** why this practice works *here* (mechanisms,
  observed outcomes in similar AEZ/rainfall/slope contexts), cited.
- **R2 — advisory enrichment (Phase 2):** implementation guidance — spacing,
  timing, labour, costs, failure modes — from CGIAR knowledge products.

## Architecture choices

| Stage | Choice | Note |
|---|---|---|
| Acquisition | Crossref + Unpaywall via `rag/ingest/fetch_papers.py` | resumable manifest; closed papers contribute abstract+metadata |
| Parsing | GROBID (structure-aware), pypdf fallback | sections preserved for retrieval |
| Chunking | section-aware, ~512 tokens, 15% overlap | |
| Embeddings | BGE-M3 or API-class equivalent | multilingual headroom; swappable |
| Store | Chroma (embedded) → Qdrant if scaled | zero-ops, fits Docker deploy |
| Retrieval | hybrid dense+BM25; metadata pre-filter on practice family & indicator; top-k≈8 + rerank | the query is the **structured recommendation output**, not user free text |
| Generation | existing Groq/OpenAI-swappable client; cite-or-silent prompt | extends current honesty guardrails |
| Guardrail | numeric claims in text must match recommendation JSON | regex check, as chat_service does for practices |

## Evaluation plan

Recall@k / MRR on ~50 hand-checked queries (silver labels via era_code linkage);
RAGAS-style faithfulness + citation precision (hand-audited sample); blinded
expert rating of model-only vs model+RAG advisories (~30 scenarios across AEZ
belts, 3–5 experts); ablations (no-RAG / unfiltered / metadata-filtered).
