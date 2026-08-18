# RAG layer — literature-grounded explanation

Phase 2 of `../../research_project_plan.md`. The RAG layer retrieves passages
from the **source studies behind the training data** (Phase-1 corpus: the
~300 DOI-linked ERA studies, manifest at `../paper/references/era_doi_list.csv`)
and grounds every advisory explanation in them, with citations. The retrieval
query is the **structured recommendation output** (practice × resolved context ×
indicator), not the user's free text.

## Layout

| Path | Role |
|---|---|
| `ingest/fetch_papers.py` | DOI → Crossref metadata → open-access PDF (Unpaywall) → `corpus/` |
| `ingest/` (next) | parse (GROBID/pypdf) → section-aware chunking → embeddings |
| `index/` | vector store (Chroma, embedded) + BM25; metadata: `{doi, era_code, title, year, section}` |
| `corpus/pdfs/` | downloaded papers (git-ignored) — seeded with the two Adimassu et al. CSA papers |
| `corpus/manifest.jsonl` | acquisition ledger: per study — OA status, files, licence |
| `eval/` | retrieval Recall@k/MRR, RAGAS-style faithfulness, expert-study materials |

## Building the corpus + index (run from `rag/`)

```bash
pip install -r requirements.txt

# 1) Acquire: DOI -> Crossref metadata -> Unpaywall OA PDF   (resumable)
export UNPAYWALL_EMAIL="you@example.org"   # any contact email; required by Unpaywall
python ingest/fetch_papers.py --doi-list ../paper/references/era_doi_list.csv --out corpus

# 2) Parse + chunk: PDFs/abstracts -> corpus/chunks.jsonl
python ingest/parse_and_chunk.py --corpus corpus

# 3) Embed + index: chunks -> Chroma at index/store            (resumable)
#    key from OPENAI_API_KEY or ../app/backend/.env
python ingest/build_index.py --corpus corpus --index index/store

# sanity check
python retrieve.py "soil bunds effect on soil loss Ethiopia"
```

Expected outcome (typical OA rates for this literature): full text for roughly
half the corpus, abstract + metadata for the rest — every study contributes at
least metadata. The manifest records exactly what each study contributed, which
feeds the paper's corpus table. Indexing ~300 studies costs well under $1 of
embeddings (text-embedding-3-small).

## Design rules (do not break)

1. **Numbers are the model's.** Retrieved text explains and instructs; any
   quantitative claim in generated text must match the recommendation JSON.
2. **Cite or stay silent.** Every generated explanation sentence is attributable
   to a retrieved chunk; otherwise the advisor falls back to the deterministic
   evidence summary (existing behaviour).
3. **Provenance is first-class.** `era_code` links every chunk to the exact
   training rows behind a recommendation — this linkage is the paper's novelty.
