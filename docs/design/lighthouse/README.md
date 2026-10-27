# Lighthouse — U1 (mobile emulation, Chrome headless, production build)

Lighthouse 13.5.0; run locally against `node .next/standalone/server.js` with the FastAPI backend on :8000. Full JSON summaries sit next to this file; raw reports are not committed.

| screen | URL | Performance | Accessibility | Best practices | LCP | TBT | CLS |
|---|---|---|---|---|---|---|---|
| advisor-en | `/en/advisor` | 74 | 100 | 77 | 9.6 s | 130 ms | 0 |
| advisor-results-en | `/en/advisor?lat=8.38&lon=39.37&family=Erosion+control+and+water+management&indicator=soil+loss` | 80 | 100 | 81 | 5.3 s | 70 ms | 0.01 |
| chat-en | `/en/chat` | 89 | 100 | 81 | 3.8 s | 70 ms | 0.014 |
| home-en | `/en` | 78 | 100 | 81 | 5.9 s | 30 ms | 0.032 |

## Failing audits (score < 1)

### advisor-en
- **performance** `first-contentful-paint` — First Contentful Paint (1.1 s)
- **performance** `largest-contentful-paint` — Largest Contentful Paint (9.6 s)
- **performance** `total-blocking-time` — Total Blocking Time (130 ms)
- **performance** `speed-index` — Speed Index (2.3 s)
- **performance** `cache-insight` — Use efficient cache lifetimes (Est savings of 30 KiB)
- **performance** `image-delivery-insight` — Improve image delivery (Est savings of 33 KiB)
  - `<img alt="" src="https://c.tile.openstreetmap.org/6/38/30.png" class="leaflet-tile leaflet-tile-loaded" style="width: 256px; height: 256px; transform: translate`
  - `<img alt="" src="https://c.tile.openstreetmap.org/6/39/29.png" class="leaflet-tile leaflet-tile-loaded" style="width: 256px; height: 256px; transform: translate`
  - `<img alt="" src="https://b.tile.openstreetmap.org/6/38/29.png" class="leaflet-tile leaflet-tile-loaded" style="width: 256px; height: 256px; transform: translate`
- **performance** `lcp-discovery-insight` — LCP request discovery (0)
- **performance** `legacy-javascript-insight` — Legacy JavaScript (Est savings of 43 KiB)
- **performance** `network-dependency-tree-insight` — Network dependency tree (0)
- **performance** `render-blocking-insight` — Render-blocking requests (Est savings of 250 ms)
- **performance** `interactive` — Time to Interactive (9.6 s)
- **performance** `max-potential-fid` — Max Potential First Input Delay (120 ms)
- **performance** `unused-css-rules` — Reduce unused CSS (Est savings of 21 KiB)
- **performance** `unused-javascript` — Reduce unused JavaScript (Est savings of 308 KiB)
- **performance** `bf-cache` — Page prevented back/forward cache restoration (2 failure reasons)
- **best-practices** `is-on-https` — Does not use HTTPS (2 insecure requests found)
- **best-practices** `image-size-responsive` — Serves images with low resolution (0)
  - `<img alt="" src="https://a.tile.openstreetmap.org/6/39/30.png" class="leaflet-tile leaflet-tile-loaded" style="width: 256px; height: 256px; transform: translate`
  - `<img alt="" src="https://b.tile.openstreetmap.org/6/38/29.png" class="leaflet-tile leaflet-tile-loaded" style="width: 256px; height: 256px; transform: translate`
  - `<img alt="" src="https://c.tile.openstreetmap.org/6/38/30.png" class="leaflet-tile leaflet-tile-loaded" style="width: 256px; height: 256px; transform: translate`

### advisor-results-en
- **performance** `first-contentful-paint` — First Contentful Paint (1.5 s)
- **performance** `largest-contentful-paint` — Largest Contentful Paint (5.3 s)
- **performance** `total-blocking-time` — Total Blocking Time (70 ms)
- **performance** `forced-reflow-insight` — Forced reflow (0)
- **performance** `image-delivery-insight` — Improve image delivery (Est savings of 32 KiB)
  - `<img alt="Illustration of Mulch + Water harvesting" decoding="async" data-nimg="fill" class="object-cover" sizes="(max-width: 768px) 100vw, 480px" srcset="/_nex`
- **performance** `legacy-javascript-insight` — Legacy JavaScript (Est savings of 43 KiB)
- **performance** `network-dependency-tree-insight` — Network dependency tree (0)
- **performance** `render-blocking-insight` — Render-blocking requests (Est savings of 610 ms)
- **performance** `interactive` — Time to Interactive (7.0 s)
- **performance** `max-potential-fid` — Max Potential First Input Delay (100 ms)
- **performance** `unused-css-rules` — Reduce unused CSS (Est savings of 21 KiB)
- **performance** `unused-javascript` — Reduce unused JavaScript (Est savings of 222 KiB)
- **performance** `bf-cache` — Page prevented back/forward cache restoration (2 failure reasons)
- **best-practices** `is-on-https` — Does not use HTTPS (4 insecure requests found)

### chat-en
- **performance** `first-contentful-paint` — First Contentful Paint (1.1 s)
- **performance** `largest-contentful-paint` — Largest Contentful Paint (3.8 s)
- **performance** `total-blocking-time` — Total Blocking Time (70 ms)
- **performance** `legacy-javascript-insight` — Legacy JavaScript (Est savings of 43 KiB)
- **performance** `network-dependency-tree-insight` — Network dependency tree (0)
- **performance** `render-blocking-insight` — Render-blocking requests (Est savings of 230 ms)
- **performance** `interactive` — Time to Interactive (7.4 s)
- **performance** `max-potential-fid` — Max Potential First Input Delay (90 ms)
- **performance** `unused-css-rules` — Reduce unused CSS (Est savings of 22 KiB)
- **performance** `unused-javascript` — Reduce unused JavaScript (Est savings of 340 KiB)
- **performance** `bf-cache` — Page prevented back/forward cache restoration (2 failure reasons)
- **best-practices** `is-on-https` — Does not use HTTPS (2 insecure requests found)

### home-en
- **performance** `first-contentful-paint` — First Contentful Paint (1.5 s)
- **performance** `largest-contentful-paint` — Largest Contentful Paint (5.9 s)
- **performance** `forced-reflow-insight` — Forced reflow (0)
- **performance** `legacy-javascript-insight` — Legacy JavaScript (Est savings of 43 KiB)
- **performance** `network-dependency-tree-insight` — Network dependency tree (0)
- **performance** `render-blocking-insight` — Render-blocking requests (Est savings of 530 ms)
- **performance** `interactive` — Time to Interactive (6.0 s)
- **performance** `max-potential-fid` — Max Potential First Input Delay (70 ms)
- **performance** `unused-css-rules` — Reduce unused CSS (Est savings of 23 KiB)
- **performance** `unused-javascript` — Reduce unused JavaScript (Est savings of 227 KiB)
- **best-practices** `is-on-https` — Does not use HTTPS (2 insecure requests found)


## Notes on the measurement (U1)

- **Topology.** The agent runs in WSL; Chrome, Node and the owner's own dev stack run on Windows. The
  measured bundle was built with `NEXT_PUBLIC_API_BASE_URL=http://172.25.96.212:8000` (the WSL
  address of the test backend) so that Windows Chrome reached the U1 backend rather than the
  backend already listening on the owner's `127.0.0.1:8000`. That is why **Best practices** loses
  the `is-on-https` audit (plain-http API calls to a non-localhost address, 4–5 points) — with the
  shipped default (`http://127.0.0.1:8000`, exempt as localhost) the same build scored **96** on
  Best practices in the run taken while the API was unreachable. The remaining Best-practices
  finding is `image-size-responsive` on OpenStreetMap raster tiles (256 px tiles on a 2.6× screen),
  inherent to OSM's standard tile set.
- **Accessibility 100 / axe 0 violations** on `/en`, `/en/advisor` (results), `/en/chat` and
  `/am/advisor` (results) with axe-core 4.14.0 run inside the page (`axe-*.json`). axe lists one
  `color-contrast` node as *incomplete* (needs a human check, not a failure) on the results screens;
  every text/background pair in the palette is tabulated in `../design_system.md`.
- **Performance ≥ 90 was not reached on `/en/advisor` (69–74).** The LCP element on step 1 is an
  OpenStreetMap tile (`lcp-breakdown-insight`: ~3.2 s resource-load delay — the map only mounts after
  hydration — plus ~1 s tile download), stretched to ~10 s by Lighthouse's slow-4G / 4× CPU
  simulation. On the results URL the LCP is the server-rendered subtitle text (5 s simulated), i.e.
  the page is paint-bound by the JavaScript still needed before first contentful render under 4×
  CPU throttling (≈ 1.3 MB of script before compression: React/Next framework ≈ 450 KB, next-intl +
  Radix + app code). Run-to-run variance on the same machine was ±8 points (home scored 98 and chat
  100 in one idle run; 77–89 in later runs while the owner's dev server was recompiling).
  Done in U1: recharts lazy-loaded behind "Why this?" (−390 KB), `preconnect` to the tile hosts,
  `keepBuffer=0` tiles, `/recommend` fired in parallel with `/metadata` on a complete URL, step 1
  server-rendered (`dynamic = "force-dynamic"`), one font weight dropped. Left for U2 (see
  progress.md): defer the map on phones until the user interacts, split next-intl messages per
  route, measure on a real low-end device.
- **Console errors.** The first runs logged a recoverable React hydration error (#418) on the two
  streamed routes only under throttling; its cause was a raw inline `<script>` placed in `<head>`
  for the theme bootstrap. It now goes through `next/script` (`beforeInteractive`) and two further
  runs logged no console errors.
- Raw Lighthouse reports (~0.6 MB each) are not committed; re-run with
  `npx lighthouse@13 http://localhost:3000/en/advisor --only-categories=performance,accessibility,best-practices`
  against `node .next/standalone/server.js` and the backend on :8000.
