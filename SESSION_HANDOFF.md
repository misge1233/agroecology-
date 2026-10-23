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
## ADDENDUM — 15 Oct 2026 session: frontend toolchain aligned to Next 16

**Symptom.** `npm install -D tailwindcss@3.4.17 postcss autoprefixer eslint@9
eslint-config-next@16.4.1` failed with ERESOLVE: vitest@5.0.5 wants
`@types/node ^22 || >=24`, the root pinned `@types/node ^20`.

**Root cause.** `app/frontend/package.json` had drifted into a mixed state
(next ^16.4.1, vitest ^5, tailwindcss ^4.3.3, eslint-config-next ^14.2.35).
Four separate breakages hide behind the one npm error: (1) vitest 5 / vite 8
need Node >= 22.12 and `@types/node` >= 22; (2) Tailwind v4 does not match
our v3-style setup (`tailwind.config.ts`, `@tailwind` directives in
globals.css, `tailwindcss: {}` in postcss.config.mjs); (3) `next lint` was
removed in Next 16; (4) eslint-config-next 16 ships native flat config and
can no longer be loaded through FlatCompat/@eslint/eslintrc.

**Fix applied (app/frontend, via the bridge).**
- package.json: `@types/node ^22`; `tailwindcss ^3.4.17` + `autoprefixer
  ^10.4.21`; `eslint-config-next ^16.4.1`; `vitest ^5.0.5` kept;
  `@eslint/eslintrc` dropped; `lint` script -> `eslint .`.
- package-lock.json regenerated (platform-complete; win32 entries present).
- eslint.config.mjs rewritten to native flat config. The two new
  React-Compiler-era rules (`react-hooks/set-state-in-effect`,
  `react-hooks/refs`) are set to **warn**: they flag 10 long-standing,
  working sites (chat/page.tsx, home/hero.tsx, location-picker.tsx x5,
  metadata-provider.tsx, theme-provider.tsx, ui/motion.tsx). Refactoring
  those is follow-up F-1 below, not part of this dependency fix.
- postcss.config.mjs (tailwindcss + autoprefixer) and tsconfig.json
  (Next 16's own edits: jsx react-jsx, .next/dev/types include) left as-is.

**Verification (clean clone of origin/main fa1d412 + these files, Node 22):**
`npm install` clean (no ERESOLVE) · `tsc --noEmit` clean · `eslint .`
0 errors / 10 warnings · `vitest run` 16/16 · `next build` (Next 16.4.1,
Turbopack) OK, routes /, /chat, /dashboard, /_not-found; Tailwind utilities
present in emitted CSS. The build check used a sandbox-only stub for
`next/font/google` (no font network in the sandbox); nothing of that is in
the repo. A `npm install --dry-run` on the owner's actual tree also resolves
(adds 325, removes 26, changes 5 packages).

**Owner checklist (Misganu):**
1. `node --version` must be >= 22.12 (Dockerfile already uses node:22-alpine;
   Node 20 reached end-of-life Apr 2026). If it prints 20.x, install Node 22
   or 24 LTS first — vitest 5 will refuse to run on 20.
2. `git pull` at the repo root FIRST: this checkout is behind origin/main by
   fa1d412 (P3.1+P5a: Success@k, GARDIAN Tier-2 corpus, +492 lines in
   progress.md, frontend evidence-panel/types/api.test changes). The pull is
   conflict-free with the four modified frontend files.
3. `cd app/frontend && npm ci` (clean reinstall from the new lockfile; drops
   Tailwind 4 and the stale tree), then `npm test && npm run lint && npm run
   build`, then `npm run dev` and eyeball the UI once (Tailwind 3 styling
   back, dark mode toggle, map, chat).
4. Commit: "Frontend: align toolchain to Next 16 (Tailwind 3.4, ESLint flat
   config, vitest 5, @types/node 22)" and push.
5. Delete the `_to_delete/` folder at the repo root (see incident).

**Incident (reviewer's own miss).** My first `git status` through the bridge
created `.git/index.lock`, and the bridge shell cannot delete files, so the
lock stayed behind. I moved it to `_to_delete/index.lock` so git is usable
again. Rule for bridge sessions from now on: only read-only git, and always
`GIT_OPTIONAL_LOCKS=0 git status` (never bare `git status`/`git diff HEAD`).

**Follow-up F-1 (small, separate PR):** refactor the 10 flagged hook sites to
React 19 idioms — `useSyncExternalStore` for localStorage/sessionStorage
reads, derived state/`key` for prop->input sync, `useEffectEvent` (or set
the ref inside an effect) for the latest-callback pattern — then restore
`react-hooks/set-state-in-effect` and `react-hooks/refs` to `error`.

**Pending bookkeeping:** append this fix as a short "Maintenance" entry to
progress.md AFTER step 2 (appending before the pull would conflict with
fa1d412's progress.md additions). Decide which clone Claude Code runs in —
the P3.1+P5a commit was pushed from a checkout other than this OneDrive one.
