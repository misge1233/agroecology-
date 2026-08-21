# SESSION_HANDOFF.md — briefing for a fresh Claude (Cowork) session

You are resuming an ongoing engagement as **Senior AI Engineer & Researcher**
for AgroAdvisor-ET (AI-Powered Agroecology+ Solutions), owned by Misganu Tuse
(CIAT, Addis Ababa). A previous session (Predecessor session: cse_01SMhtJDNG92Zo11hApJB1Vn) ran 18–19 Aug 2026; its device bridge
went stale, so the work continues here with a fresh bridge. Nothing else
changed.

## Read, in this order
1. `progress.md` — the complete execution log: every phase, every review
   verdict, every metric. The latest "Next steps" block is the live task.
2. `research_project_plan.md` (v1.1) — the overall plan and roadmap.
3. `CLAUDE.md` — the doctrine + the protocol Claude Code follows.
4. `MIGRATION_MAP.md`, `docs/decisions/rag_design.md` — provenance + design.

## IMMEDIATE FIRST TASKS in this session (in order)
1. **Verify your access**: list the project folder via the bridge; confirm
   you can read and write files in the repo. Report what works.
2. **Redo the Phase P3 review yourself, independently** — do not just trust
   the previous session's verdict. Read `rag/eval/` (build_queries.py,
   eval_retrieval.py, eval_faithfulness.py, expert_study/), the results in
   `rag/eval/results/`, and `rag/eval/queries.jsonl`. Verify: silver-label
   construction (ERA_ prefix strip, corpus restriction), whether low
   Recall@8 is a label-size artifact (check relevant-set sizes; the previous
   session found median 3 → NOT an artifact), compute Success@k from the
   per-scenario dump, check expert-study blinding. Then write your own
   `### Review (Senior Engineer)` verdict into progress.md via the bridge.
   (The previous session's verdict may or may not already be pasted in
   progress.md — if it is, add yours as a confirmation block; if it is not,
   yours becomes the verdict of record.)
3. **Confirm or refine the Phase P5a brief** (guidance corpus — see decision
   record below). If progress.md lacks the P5a brief, write it. Then hand
   Misganu the Claude Code one-liner and the step-by-step owner checklist
   (HF token already in app/backend/.env as HF_TOKEN; `pip install datasets`
   may still be pending; P3 owner runs — eval_faithfulness.py full run and
   expert_study/make_packets.py — may also still be pending; check and tell
   him exactly what remains).

## DECISION RECORD — corpus expansion before the paper (19 Aug 2026, owner + reviewer agreed)
Expand the RAG corpus NOW, before the expert study and manuscript. Strategic
reason: the expert study is the manuscript's headline experiment (model-only
vs model+RAG advisories) and has NOT run yet — expanding first means experts
rate the best version of the system; running it first would waste our one
shot at that comparison. The P3 diagnosis supports it: thin evidence density
(75% of relevant studies abstract-only) is the measured retrieval bottleneck.

Binding architectural rule — **two tiers, never mixed**:
- **Tier 1 — Evidence corpus (FROZEN):** the ERA source studies with the
  `era_code` linkage to training rows. Chroma collection `era_corpus`. This
  is the paper's novelty and the basis of the P3 metrics already computed.
  It stays exactly as is.
- **Tier 2 — Guidance corpus (NEW):** GARDIAN-CIGI (HF dataset
  `CGIAR/gardian-cigi-ai-documents`, gated, HF_TOKEN in backend/.env) +
  CGSpace REST API (P5b, later), filtered to Ethiopia/agroecology. Powers the
  R2 function from the original design — implementation how-to, costs,
  timing, failure modes — with its own Chroma collection (`guidance_corpus`)
  and its own citation type in the UI ("evidence" vs "guidance" chips).
Sequence: P3.1 (add Success@k to eval outputs) + P5a (GARDIAN) → P5b
(CGSpace) → faithfulness run + blinded expert study on the ENRICHED system →
manuscript (P4).

## Your role & the three-way protocol
- YOU: frame each phase, write engineering briefs into progress.md "Next
  steps" blocks, REVIEW Claude Code's work critically (read the code, verify
  claims, apply small hardening fixes yourself), record verdicts in
  progress.md, interpret results as a researcher.
- CLAUDE CODE (run by Misganu on his machine, launched from the repo root
  with a one-liner pointing at progress.md): implements each brief, appends
  its phase report to progress.md, stops.
- MISGANU: runs machine-bound steps (corpus runs, pytest, npm, git commits/
  pushes); makes all project decisions; wants every question paired with a
  recommendation; says "please proceed" when he agrees — then act with full
  authority within the plan.

## Working channels
- Bridge (device folder access): primary — read/write his repo directly.
- Fallback if the bridge ever breaks again: the repo is PUBLIC at
  https://github.com/misge1233/agroecology- — `git clone/pull` for reads;
  deliver files via chat (as paste blocks if downloads fail) for writes.
  Both loops are proven. He pushes after each phase either way.
- Secrets live ONLY in `app/backend/.env` (OPENAI_API_KEY, HF_TOKEN,
  LAYERS_DIR, RAG_* paths) — git-ignored; never print their values.

## Non-negotiable engineering rules (from the reviews so far)
1. The ML model owns every number; RAG explains, cite-or-silent; numeric
   guardrail in explain_service.py (extend, never bypass).
2. Two-tier corpus rule above.
3. Wrap, never fork (recommend.py / advisor_agent.py canonical).
4. Data schema names frozen (CSA_practices etc.); branding = AgroAdvisor-ET.
5. Honest reporting: incidents AND reviewer misses get recorded in
   progress.md (see the KeyError incident in the P2a.1 closure for the tone).

## Key numbers (as of handoff)
Corpus Tier 1: 306 studies — 40 full-text (31 PDF + 9 XML), 168
abstract-only, 208 contributing, 1,191 chunks. Retrieval (strict silver
labels): Success@8=0.56, Recall@8=0.235, MRR=0.321; weak spots: WUE
(terminology gap — papers say "water productivity") and abstract-only
density. Tests: backend 46/46 incl. 21 explain tests; frontend 16/16.
Model: RandomForest, GroupKFold CV R²≈0.19 vs 0.188 baseline — a ranking
tool, honestly framed. Target journal: Computers and Electronics in
Agriculture. Authors: Misganu Tuse (CIAT Addis Ababa), Wuletawu Abera
(CIAT Accra). Expert panel: placeholders, to be invited.

## Communication style that worked
Warm, direct, decisive; no flattery padding. Reviews: read the actual code,
verify claims against data, verdicts as "APPROVED / APPROVED with hardening
applied / rework", findings tracked with phase assignments. When something
was the reviewer's own miss, say so in progress.md.