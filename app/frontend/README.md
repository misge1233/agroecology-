# Frontend — AgroAdvisor-ET (Next.js)

The trilingual (English · አማርኛ · Afaan Oromoo) web UI over the FastAPI recommender.
Every number on screen comes from the field-trial model; the UI translates names,
never figures (see `../../CLAUDE.md`, doctrine 1).

## Screens

| Route | Purpose |
|---|---|
| `/{locale}` | Home — hero, three-step "how it works", live trust strip from `/metadata.evidence`, the five challenge families |
| `/{locale}/advisor` | Four-step Advisor (Location → Challenge → Objective → Crop) → ranked practices with context card, confidence, evidence and "How to implement"; the request lives in the URL (`?lat&lon&family&indicator&crop&top`) so results are shareable; "Save as PDF" prints the advisory sheet |
| `/{locale}/chat` | Conversational advisor (SSE). Quick-reply chips send a sentence in the UI language plus a structured hint; result cards are the Advisor's own; "Open in Advisor" deep-links the scored query |
| `/{locale}/about` | What it is, how to read confidence, data sources, licence |
| `/{locale}/dashboard` | Redirects to the Advisor (the U1 rename) |

`locale` is `en`, `am` or `om`; the proxy (`src/proxy.ts`) picks it from the
`agro-locale` cookie → `Accept-Language` → `en`, and the language switcher keeps the
route and query string.

**Evidence-tiered advisory (P9).** The results view and the chat ask `POST /advise`,
which wraps `/recommend` with an evidence *mode* and, when the field-trial evidence is
thin or absent, up to five *documented practices*:

- **model-led** — the ranking alone; the source badge says "Field-trial model".
- **hybrid** — the ranking plus a "Documented practices" section (secondary outline,
  sources and a "Why this is suggested" line, never an effect number); the badge says
  "Hybrid" and a reasons card explains why (e.g. no observation in the user's moisture zone).
- **knowledge-led** — no ranking at all: an info panel replaces the former "no field
  evidence" error and the documented practices are the answer; the badge says
  "Documented practice".

The badge tooltip lists the backend's reasons (catalog keys rendered by the UI in the
three languages); the print sheet carries the mode, the reasons and the documented
practices; the chat renders the same cards inline (`advisory` SSE event). Components:
`advisor/mode-badge.tsx`, `advisor/knowledge-candidates.tsx`.

## Stack

Next.js 16 (App Router, `output: "standalone"`) · React 19 · TypeScript (strict) ·
Tailwind 3 · next-intl 4 · Radix primitives (dialog, popover, select, tabs, toast,
tooltip) with cva/tailwind-merge · lucide icons · react-leaflet · recharts (lazy, only
inside "Why this?") · react-markdown. Fonts are **self-hosted** (`src/app/fonts/`,
SIL OFL): IBM Plex Sans (variable, latin) and Noto Sans Ethiopic — a production build
never contacts Google Fonts.

## Setup

```bash
cd app/frontend
cp .env.example .env.local        # NEXT_PUBLIC_API_BASE_URL (default http://127.0.0.1:8000)
npm ci
npm run dev                        # http://localhost:3000 → redirects to /en
```

The backend must run on the configured API base (`uvicorn app.main:create_app
--factory --port 8000` from `app/backend`).

## Scripts

| script | what |
|---|---|
| `npm run dev` | Turbopack dev server |
| `npm run build` | production build (`.next/standalone`) |
| `npm start` | serves the production build (`scripts/serve-standalone.mjs`; `next start` cannot serve a standalone build). `PORT`/`HOSTNAME` honoured |
| `npm run lint` | ESLint — 0 errors / 0 warnings is the bar; the React-Compiler hook rules are errors |
| `npm run typecheck` | `tsc --noEmit` |
| `npm test` | vitest: pure logic (`src/lib`, `src/i18n`) and component tests (jsdom, Testing Library); includes the i18n guards below |
| `npm run e2e` | Playwright end-to-end against the production build with the API mocked (`e2e/`) — run `npm run build` first |
| `npm run e2e:ui` / `npm run e2e:report` | Playwright UI mode / last HTML report |
| `npm run i18n:status` | regenerate `docs/i18n/TRANSLATION_STATUS.md` |

## Design tokens and components

Tokens (palette, light/dark, chart colours, radii, elevations, motion) live in
`src/app/globals.css` and `tailwind.config.ts`; the measured contrast table, CVD check
and honest-display rules are in `../../docs/design/design_system.md`. Primitives are
under `src/components/ui/` (Button, Card, Badge/Chip, Tabs, Dialog/Sheet, Tooltip,
Select, Combobox, Toast, Skeleton, Alert, Stepper, Input). Confidence: high = green,
medium = amber, low = neutral "thin evidence"; red is for system errors only.

## Internationalisation

* UI strings: `messages/{en,am,om}.json` (next-intl, ICU plurals). Per-route message
  splitting: the layout ships only the shell namespaces; each page re-provides the
  shell plus its own (`src/i18n/messages.ts`).
* Data-contract names (families, indicators, belts, crop groups, the 44 practice
  components that compose the 100 practice names): `src/i18n/glossary.ts`.
* Texts the API itself produces (clarifications, summaries, quick-reply sentences):
  `../backend/app/i18n/{en,am,om}.py`. `tests/test_i18n_sync.py` keeps the two
  vocabularies identical.
* Guards (vitest): no hard-coded user-visible string in `src/**/*.tsx`
  (`src/lib/i18n-audit.test.ts`), `am`/`om` carry every `en` key with valid ICU
  placeholders, and reviewed strings cannot change silently
  (`src/i18n/review-status.test.ts`).

### Review workflow (native speakers)

```bash
python scripts/translation_status.py --export review.csv   # glossary terms first
# edit the am / om cells, set status_am / status_om to "reviewed"
python scripts/translation_status.py --import review.csv   # writes all three catalogs + fingerprints
npm test                                                     # guards pass; docs/i18n/TRANSLATION_STATUS.md regenerated
```

The chat's Amharic / Afaan Oromoo **free text** is read by one validated LLM call
when the backend has `OPENAI_API_KEY`; without it the chat steers the user to the
chips / the Advisor. Chips never need the model (they carry a structured hint).

## End-to-end tests

`e2e/` (Playwright 1.58): the Advisor flow in en/am/om, the chat happy path with a
streamed answer, keyboard-only completion, the no-horizontal-overflow guard at
360/390/412/768/1440 px on every screen, axe-core on every screen, dark mode, the
print sheet, and phone-specific behaviour (deferred map, tile failure). The API is
intercepted in the browser and answered from `e2e/fixtures/*.json`, which were
captured from the real FastAPI responses — no backend, rasters or network needed.

Browser: the system Chrome (`channel: "chrome"`, no download). Without Chrome:

```bash
npx playwright install chromium
PLAYWRIGHT_CHANNEL=chromium npm run e2e
```

`advisory-modes.spec.ts` covers the three modes in English and Amharic against
`/advise` fixtures captured from the real backend at the demo pin
(`advise-model.json` water use efficiency, `advise-hybrid.json` soil loss,
`advise-knowledge.json` income; `advise-<name>.am.json` / `.om.json` are the same
advisories answered in Amharic and Afaan Oromoo, served by the mock when the request's
`language` says so), the chat's inline cards, the print sheet and a mojibake guard
(`â€`, `Ã` must never reach the page). Fixtures are written in UTF-8
with `ensure_ascii=False`; re-capture them with the backend running:
`app\backend\.venv\Scripts\python.exe` + `urllib` (see the P9 report in `progress.md`).

## Low-bandwidth behaviour

Practice photos are lazy with a blurred placeholder and a text fallback; `GET`
calls and the idempotent `POST`s (`/recommend`, `/explain`) retry twice with backoff
on network errors / 502–504 while a "retrying…" strip is shown; map tiles failing
shows a message and leaves the coordinate inputs usable; the map is not mounted on
phones until the user asks for it; the "API unreachable" banner is driven by
`/health`.
