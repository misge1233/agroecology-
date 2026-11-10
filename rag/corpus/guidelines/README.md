# `rag/corpus/guidelines`: government guidelines and manuals (Tier 2b)

Official Ethiopian guidelines, technical manuals, training packages and brochures that describe **how** practices are designed and implemented (spacing, slope limits, suitable land use, maintenance), published by the Ministry of Agriculture (MoA) and its programme partners (GIZ SLM, SDR and SURED, WLRC and CDE Bern, PSNP), plus a few national strategies. They complement Tier 1 (study papers, the numbers) and Tier 2 (GARDIAN and CGSpace guidance): in the evidence fusion doctrine they are the **documented** path (implementation guidance and suitability rules), never a source of effect numbers unless a figure is quoted verbatim with its citation.

Catalogued on 10 November 2026 from the MoA document library (`moa.gov.et`: Land Rehabilitation Measures, ISFM manuals and brochures, Productive Use, Suitability, Dry Valley pages; 219 PDFs reviewed, 62 selected) and from WOCATpedia, CGSpace and CIFOR-ICRAF.

## Layout

```
rag/corpus/guidelines/
  manifest.csv      the catalogue: one row per document (in git)
  README.md         this file (in git)
  fetch_guidelines.ps1   downloads every manifest row into pdfs/ (in git)
  pdfs/             the PDFs (git-ignored; rebuilt from manifest.csv)
  texts/            page texts texts/<doc_id>/page_<n>.txt + meta.json (git-ignored; rag/ingest/ingest_guidelines.py)
  chunks.jsonl      page-level chunks, mirror of the Chroma collection "guidelines" (git-ignored)
  ingest_report.md  per document: pages, characters, OCR pages, language (in git)
```

`manifest.csv` columns: `doc_id` (stable key used in citations), `title`, `publisher`, `year`, `language` (en, am), `theme` (swc, gully, watershed, water_harvesting, dryland, isfm, agroecology, agroforestry, fodder, irrigation, crop, pest, livestock, policy, evidence), `audience`, `file_name` (the name in `pdfs/`), `url`, `size_mb`, `status` (`to_download`, `downloaded`, `resolve_pdf` when the URL is a record page rather than the PDF), `notes`.

## Downloading

On a machine with internet access, from the repo root in PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File rag\corpus\guidelines\fetch_guidelines.ps1
```

The script skips files that already exist, reports failures, and leaves rows with `status = resolve_pdf` for manual download (open the record page and save the PDF under the `file_name` given). Total size of the direct downloads is about 100 MB.

## Licence and use

MoA documents are public extension material published for free distribution. They are stored here for text extraction and citation only; the application shows passages with the document title and page, never whole documents. Partner documents (CIFOR-ICRAF, CGSpace records) carry their own licences, recorded in `notes` where known. Nothing in this folder is redistributed by the repository (PDFs are git-ignored).

## How the system will use them (roadmap phase E2)

- Each document is parsed into pages and chunks with `doc_id`, title, year, page and theme, and indexed as Tier 2b in the hybrid retriever.
- Suitability statements (slope ranges, rainfall bands, land use, soil depth, scale) are extracted into the practice taxonomy as eligibility rules with the document and page as provenance.
- Practice descriptions feed the knowledge graph (`Practice` attributes and `DOCUMENTED_IN` edges) and the "how to implement" path in the Advisor and Chat.
- Amharic documents support the Amharic interface directly; Afaan Oromoo material is still to be sourced (Oromia Bureau of Agriculture).
