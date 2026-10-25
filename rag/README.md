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
| `ingest/fetch_papers.py` | DOI → Crossref metadata → OA full text via fallback chain (Unpaywall all locations → OpenAlex → Europe PMC XML → Crossref links) → `corpus/` |
| `ingest/parse_and_chunk.py` | PDFs/XML/abstracts → `corpus/chunks.jsonl` |
| `ingest/build_index.py` | chunks → embeddings → Chroma (`--rebuild` after corpus changes) |
| `index/` | vector store (Chroma, embedded) + BM25; metadata: `{doi, era_code, title, year, section}` |
| `corpus/pdfs/` | downloaded papers (git-ignored) — seeded with the two Adimassu et al. CSA papers |
| `corpus/xml/` | Europe PMC full-text JATS XML (git-ignored) |
| `corpus/manifest.jsonl` | acquisition ledger: per study — OA status, files, licence, `pdf_source`/`abstract_source`/`fulltext_xml` provenance |
| `eval/` | retrieval Recall@k/MRR, RAGAS-style faithfulness, expert-study materials |
| `graph/` | knowledge graph: dataset + corpus + WOCAT vocabularies (`build_graph.py` → `graph/store/graph.json`, `query.py` for the API) |
| `ingest/wocat/` | WOCAT practice-record schema + normalizer (data arrives via the owner's research export; nothing here fetches) |

## Building the corpus + index (run from `rag/`)

```bash
pip install -r requirements.txt

# 1) Acquire: DOI -> Crossref metadata -> OA full text        (resumable)
#    fallback chain: Unpaywall (all locations) -> OpenAlex -> Europe PMC -> Crossref links
export UNPAYWALL_EMAIL="you@example.org"   # any contact email; required by Unpaywall
python ingest/fetch_papers.py --doi-list ../paper/references/era_doi_list.csv --out corpus

# 1b) Coverage remediation: re-run ONLY the studies still missing full text
#     and/or an abstract (manifest rewritten in place; .bak backup kept)
python ingest/fetch_papers.py --doi-list ../paper/references/era_doi_list.csv --out corpus --retry-missing

# 2) Parse + chunk: PDFs/XML/abstracts -> corpus/chunks.jsonl
python ingest/parse_and_chunk.py --corpus corpus

# 3) Embed + index: chunks -> Chroma at index/store            (resumable)
#    key from OPENAI_API_KEY or ../app/backend/.env
#    IMPORTANT: after --retry-missing changed the corpus, use --rebuild —
#    chunk ids get reassigned, so resumable mode would keep stale embeddings
python ingest/build_index.py --corpus corpus --index index/store --rebuild

# sanity check
python retrieve.py "soil bunds effect on soil loss Ethiopia"
```

### 4) Build the knowledge graph (run from the **repo root**)

```bash
python -m rag.graph.build_graph
```

Writes `rag/graph/store/{graph.json, graph_report.json}` from the dataset, the
corpus manifest and the WOCAT vocabularies. Deterministic and idempotent: two
runs over unchanged inputs produce byte-identical files.

The graph modules are a **package** — run them with `python -m`, not as file
paths (`python rag/graph/build_graph.py` raises `attempted relative import
with no known parent package`, by design: package-relative imports are what
keep a top-level `schema` / `query` module out of the API process).

Optional flags:

```bash
# include the hand-built WOCAT fixtures (real Technology #6644 + Approach #6732)
python -m rag.graph.build_graph --wocat rag/ingest/wocat/fixtures

# admit status=proposed crosswalk rows, tagged crosswalk_auto
python -m rag.graph.build_graph --include-proposed

# TESTS ONLY — admits records flagged synthetic:true. Such a graph must never
# feed the app or an evaluation; the default build refuses them and says so.
python -m rag.graph.build_graph --wocat rag/ingest/wocat/fixtures --allow-synthetic
```

The core build needs only `networkx` — no pydantic, no fixtures, no WOCAT
data. `--wocat` additionally needs `pydantic>=2`; without it the records are
skipped with a clear message and the core graph still builds.

Once the store exists, `/metadata` reports `graph_ready: true` and `/explain`
adds a per-practice **evidence base** (how many studies and field
observations stand behind each recommendation, in which AEZ belts, and how
many are retrievable). The graph is optional everywhere: with no store,
`/explain` behaves exactly as it did before.

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
