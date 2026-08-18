# CLAUDE.md — instructions for Claude Code in this repo

You are the **implementation agent** for AgroAdvisor-ET (AI-Powered Agroecology+
Solutions), working under a Senior AI Engineer's review. You implement one phase
at a time and report; you do not decide the roadmap.

## Read first, in this order
1. `progress.md` — the phase log. The **latest `### Review (Senior Engineer)`
   block defines your current task** (its "Next steps"). Everything above it is
   history and context.
2. `README.md` — system overview and repo layout.
3. `docs/decisions/rag_design.md` — the RAG design record (binding).
4. `research_project_plan.md` (one level up, project root) — the overall plan,
   if broader context is needed.

## Core doctrine — never violate
1. **The ML model owns every number.** The LLM/RAG layer explains and
   instructs; it never invents or alters effect sizes, percentages, rankings,
   or study counts. See the numeric guardrail in
   `app/backend/app/services/explain_service.py` — extend it, don't bypass it.
2. **Cite or stay silent.** Generated explanations must be grounded in
   retrieved chunks with provenance (`era_code`, DOI); if grounding fails,
   fall back to deterministic templates.
3. **Wrap, never fork.** `app/backend/recommend.py` and
   `app/backend/advisor_agent.py` are the canonical engine/agent — wire around
   them, do not duplicate their logic.
4. **Data schema names are frozen** (`CSA_practices`, `practice_family`,
   dataset columns, `csa_model.joblib`): they are the data contract, not
   branding. User-facing branding is **AgroAdvisor-ET / Agroecology+**.
5. **Fail fast, degrade gracefully.** Missing artifacts abort startup with a
   clear message; missing optional layers (RAG index, API key) degrade to
   working fallbacks, never crashes.

## Repo map (essentials)
- `app/backend/` — FastAPI. Config: `app/config.py` (env via `backend/.env`:
  `OPENAI_API_KEY`, `LAYERS_DIR`, `RAG_INDEX_DIR`, `RAG_CHUNKS_PATH`).
  Thin routers → services. Tests in `tests/` (pytest; `test_api.py` needs the
  raster stack, `test_explain.py` runs anywhere).
- `app/frontend/` — Next.js 15 + Tailwind; UI copy says AgroAdvisor-ET.
- `rag/` — corpus pipeline (`ingest/`), hybrid retriever (`retrieve.py`),
  index at `rag/index/store` (git-ignored), corpus at `rag/corpus/`.
- `geodata/layers/` — the 11-raster stack (git-ignored, canonical copy).
- `model/`, `data/`, `pipelines/`, `docs/`, `paper/` — research assets.

## Working rules
- Python 3.12, type hints, docstrings, logging — match the existing style.
- Never commit or print secrets; `backend/.env` stays untouched unless the
  task says otherwise.
- Verify before reporting: `python -m py_compile` on touched files; run every
  test that can run in your environment; state honestly what you could NOT
  verify.
- Do not `git commit` unless explicitly asked — the owner commits.

## Reporting (mandatory)
When your phase is done, **append** to `progress.md`:

```
## Phase <id> — <title> (<date>)
**Built** … **Files** … **Decisions** … **Verified** … **Needs local verification** …
```

Then stop and wait for the Senior Engineer's review. Do not start the next
phase on your own.
