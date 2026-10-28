# Lighthouse — mobile emulation, production build

Lighthouse 13.5.0, Chrome headless (system Chrome 156), **mobile** preset (slow-4G +
4× CPU simulation), run against `node .next/standalone/server.js` on `:3005` with the
FastAPI backend live on `127.0.0.1:8000` (the shipped default `NEXT_PUBLIC_API_BASE_URL`).
Per-screen JSON summaries (scores, metrics, LCP element, failing audits) sit next to
this file; raw reports (~0.6 MB each) are not committed. Re-run with:

```bash
npm run build && npm start            # :3000, backend on :8000
npx lighthouse@13 http://localhost:3000/en/advisor --only-categories=performance,accessibility,best-practices --output=json --output-path=advisor.json
```

## U2 (28 Oct 2026) — two consecutive runs

| screen | URL | Perf A / B | A11y | Best practices | LCP A / B | LCP element |
|---|---|---|---|---|---|---|
| advisor step 1 | `/en/advisor` | **98 / 99** | 100 | 100 | 2.2 s / 1.8 s | subtitle text |
| advisor results | `/en/advisor?lat…&indicator=soil+loss` | **97 / 83** | 100 | 100 | 2.3 s / 4.4 s | subtitle text |
| chat | `/en/chat` | **95 / 94** | 100 | 100 | 2.9 s / 3.0 s | intro text |
| home | `/en` | **93 / 94** | 100 | 100 | 3.2 s / 3.0 s | hero `<h1>` |

TBT 40–160 ms, CLS 0–0.035 on every screen. Remaining Performance findings are
`unused-javascript` (220–370 KiB of framework/next-intl/Radix code before compression)
and a 160–550 ms render-blocking stylesheet; nothing fails Accessibility or Best
practices any more.

**What moved the needle since U1** (74 / 80 / 89 / 78 → above):

1. The Leaflet map is no longer mounted on phones until the user taps "Show the
   map" (`location-step.tsx`, `useIsPhone` via `useSyncExternalStore`); the first
   OSM tile had been the LCP element at ~10 s simulated.
2. The Advisor's title, subtitle and stepper render before `/metadata` arrives
   (they were behind the metadata gate, so the LCP text painted only after
   hydration + the fetch). The step area alone shows a skeleton while loading.
3. Both typefaces self-hosted through `next/font/local` (no Google Fonts round
   trip; one preload each for the Latin faces, none for Ethiopic).
4. Per-route message splitting: the layout ships only the shell namespaces to the
   client; each page adds its own (`src/i18n/messages.ts`).
5. Tiles: `keepBuffer=0`, `updateWhenIdle`, phone map height 14 rem; recharts
   stays lazy behind "Why this?".

**Honest ceiling.** Run B's 83 on the results page is variance from the live
`/recommend` call (the ML scoring plus raster reads) landing inside Lighthouse's
simulated window; with the same build run A measured 97. Everything else sits at
93–99 under slow-4G / 4× CPU. The remaining ~300 KiB of unused JavaScript is
Next/React/next-intl/Radix framework code shared by every route; trimming it means
dropping Radix for hand-rolled primitives or server-rendering the chat, which U2
did not do.

**Best practices 100** now that the API is on `127.0.0.1` (the shipped default);
U1's measurement topology (API on a non-localhost address) had cost the
`is-on-https` audit.

## U1 (26 Oct 2026) — for the record

| screen | Perf | A11y | BP | LCP |
|---|---|---|---|---|
| advisor step 1 | 69–74 | 100 | 77 | 9.6 s (OSM tile) |
| advisor results | 74–80 | 100 | 81 | 5.3 s |
| chat | 79–89 | 100 | 81 | 3.8 s |
| home | 77–78 | 100 | 81 | 5.9 s |

axe-core 4.14: 0 violations on home, advisor results (en + am) and chat in U1
(`axe-*.json`); in U2 the Playwright suite runs axe on home, advisor step 1,
results, chat, about and the Amharic advisor on every run.
