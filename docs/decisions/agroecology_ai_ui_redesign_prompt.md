# Build Prompt — Agroecology AI: Premium UI Redesign (keep all functionality)

## Your role
Senior full-stack + product designer engineer. **Redesign the entire frontend** of this app
into a stunning, modern, "wow" experience — WITHOUT changing any functionality, API contract,
model, or recommendation logic. Backend endpoints stay exactly as they are
(`/recommend`, `/chat` SSE, `/metadata`, `/health`). Only the Next.js frontend changes.

## Design north star — study and emulate glean.com
Open **https://www.glean.com/** in the browser and study it carefully (hero, header, motion,
spacing, color, sections). **Emulate its visual language**, adapted to our agroecology brand.

### Observed hero anatomy (from a reference recording of glean.com — mirror this structure)
- **Header:** clean, near-white, sticky; logo far left; centered text nav items with small
  dropdown carets; a pill **search** field; a text **"Sign in"** link; and a **gradient pill
  CTA** (blue→purple) far right. Thin/no border, lots of breathing room.
- **Hero (centered):** a tiny, letter-spaced **eyebrow** line at top; then a **very large, bold,
  near-black two-line headline**; then **dual CTAs** — a solid dark pill primary + a secondary
  "See how it works" text button with a small circular play icon.
- **Hero showcase panel:** a big `rounded-3xl` panel filled with a **vivid fluid gradient / 3D
  blob** (electric blue → magenta/pink → warm orange), and floating on top a **glassy white
  "ask" input card** whose placeholder **types out cycling example questions** (typewriter
  animation), with a filter + mic icon and a row of small **source chips** beneath it.
- A floating round **helper/chat bubble** bottom-right.

**Adapt for us:** keep this exact hero *shape*, but the fluid-gradient blob becomes an
agroecology palette (greens + our blue→purple→pink), the floating "ask" card types cycling
**farmer questions** (e.g. "How do I cut soil erosion at 8.38, 39.37?", "Best practice to raise
maize yield in the highlands?", "Reduce runoff with water management") and routes to `/chat`,
and the "source chips" become our **data sources** (WorldClim, SoilGrids, Copernicus DEM,
ESA WorldCover, AICCRA/ERA evidence).

### General Glean style to replicate
- Clean, premium, spacious enterprise-AI look; generous whitespace; big confident headlines
  with tight tracking; concise sub-copy; gradient-highlighted keywords.
- Soft **aurora / mesh gradient** backgrounds (blurred color blobs), glassy translucent cards
  with soft shadows and `rounded-3xl`, subtle borders.
- Sticky **translucent blurred header**; pill buttons (solid primary + ghost secondary).
- Animated **hero** with a floating product/UI mock + glow + gentle parallax, and an "ask"
  input in the hero.
- Auto-scrolling **logo/marquee** ("powered by / data sources"), **stats band** with big
  animated number counters, **bento** feature grids, alternating text/visual sections,
  **scroll-reveal** animations (fade/slide-up), tasteful looping motion, large multi-column
  **footer**.
Adapt the palette to **agroecology**: earthy greens + the existing blue→purple→pink gradient
already in the app; keep light + dark themes. Use only ORIGINAL copy/visuals — do not copy
Glean's text, logos, or images.

## Tech (already in the project — use these, add nothing heavy)
Next.js 15 App Router, React 19, TypeScript, TailwindCSS, **framer-motion** (animations),
**recharts** (charts), **react-markdown**, **lucide-react** (icons), **react-leaflet/leaflet**
(maps). Keep the existing `src/lib/api.ts`, `src/lib/types.ts`, `metadata-provider`, and the
recommendation/chat data flow intact — reuse and restyle components, don't rewrite the data layer.

## Information architecture — a real header with 3 pages
Sticky translucent header: logo "**Agroecology AI**" (left), centered nav, theme toggle + a
primary CTA "Get recommendation" (right), responsive mobile menu. Nav routes:

### 1) Home — `/` (NEW landing page; currently `/` is the chat — move chat to `/chat`)
A marketing/scrollytelling page that shows off the data + model + AI. Sections:
- **Hero:** headline "**Agroecology AI**" + tagline "AI-Powered Agroecology Intelligence &
  Recommendation Platform." Sub-copy: "Agroecology AI is an evidence-driven decision-support
  system that delivers context-specific, agroecology-based agricultural recommendations by
  integrating climate-smart agriculture (CSA) evidence, geospatial data, soil, climate,
  landscape, and farm-management information with advanced artificial intelligence." Include an
  "ask" input that routes to `/chat` with the text seeded, and primary/secondary CTAs
  (Get a recommendation → /chat; Explore dashboard → /dashboard). Animated hero visual: a
  stylized glowing **map of Ethiopia with agro-ecological zones** and floating data chips
  (rainfall, soil pH, slope, LGP) with parallax/glow.
- **Stats band** (animated counters, pull live from `/metadata` where possible, else these
  real numbers): 8,664 field observations · 337 studies · 15 agro-ecological belts ·
  11 geospatial layers · 5 practice families · 7 objectives · nationwide ~250 m resolution.
- **How it works** (3 animated steps): 1 Pick your location (map) → 2 Choose your challenge &
  goal → 3 Get ranked, evidence-based practices.
- **What powers it** bento grid: (a) Geospatial feature stack — animate the 11 layers /
  show the AEZ map; (b) Evidence base — meta-analysis of CSA field trials; (c) The model —
  ranks practices by expected effect; (d) The AI assistant — explains in plain language.
- **Interactive demo / charts** (recharts, animated on scroll): a sample recommendation with
  effect bars; the 15-zone / practice-family distribution; a "response ratio" explainer. Make
  it feel alive and data-rich.
- **Practice families** (5 cards) and **Objectives** (7 chips) with icons and short blurbs.
- **Data & science provenance** marquee: WorldClim, SoilGrids, Copernicus DEM, ESA WorldCover,
  AICCRA/ERA evidence, Ethiopian AEZ (Hurni et al.). (Text chips, original — no external logos.)
- **Mission / honesty** note: evidence-driven, transparent, ranking not guarantees.
- **Final CTA band** → /chat. Large multi-column **footer**.
All sections use scroll-reveal motion, mesh-gradient backgrounds, glassy cards, hover lift.

### 2) Chatbot — `/chat` (redesign the existing chat; keep the SSE + recommendation flow)
Standard, polished chatbot UI: clean message list (user right / assistant left avatars),
streaming tokens, markdown, the existing **clean recommendation cards + "Why this?"** detail
expansion (keep as-is functionally). Add:
- **Quick-action chips** above/!in the composer: the **7 objectives** and the **5 challenges
  (practice_family)** as one-tap buttons that insert/guide the query; plus a few example
  prompts and a "use my location" affordance.
- **Intelligent map in conversation:** the assistant should, when a location would help and the
  user hasn't given precise coordinates, ask conversationally "Would you like to pick your
  location on a map?" If the user says yes, the assistant surfaces a **map** in the chat — an
  inline expandable Leaflet mini-map / a clearly styled "Open map" card — where dropping a pin
  fills lat/long (synced with numeric entry) and continues the flow. Keep Ethiopia-bounds
  validation. (Implement the "offer map on intent" as a frontend affordance triggered by the
  assistant/flow; do not require backend changes.)
- Empty state with friendly intro; typing indicator; error/retry; scroll-to-latest; mobile-first.

### 3) Dashboard — `/dashboard` (standardize the form-based flow)
A clean, professional analyst view: left/side **input panel** (map pin + synced numeric
lat/long, challenge dropdown, objective dropdown, optional crop typeahead, top-N), and a main
**results area** with the clean ranked practices, an effect **bar chart** (recharts), the
resolved **local context** panel (zone + climate/soil/terrain), confidence, evidence counts,
and export (copy/CSV). Well-aligned grid, cards, filters, loading/empty/error states. This is
the "power user" surface; it may show more detail than chat by default, but keep it tidy and
standardized.

## Cross-cutting requirements
- **No functional regressions:** all current behavior (parse → recommend → clean answer →
  explain on why; bounds validation; SSE streaming; two-tier output) must keep working. Reuse
  `api.ts`/`types.ts`/`metadata-provider`; restyle, don't refactor the contract.
- **Design system:** define tokens (colors, gradients, radii, shadows, typography scale) in
  Tailwind config + `globals.css`; build reusable primitives (Button, Card, Chip, Section,
  GradientText, StatCounter, MarqueeRow, Reveal wrapper). Consistent across all pages.
- **Motion:** framer-motion for hero, scroll reveals, counters, hovers, page transitions —
  smooth and tasteful, never janky; respect `prefers-reduced-motion`.
- **Responsive & accessible:** mobile-first, keyboard-navigable, ARIA labels, good contrast in
  light and dark, focus states; lazy-load the map and heavy visuals; keep Lighthouse-friendly.
- **Performance:** code-split routes; dynamic-import Leaflet/recharts; optimize images (use the
  existing `feature_maps_final.png` / `aez_belt_map_final.png` if helpful, in `public/`).
- **Quality:** TypeScript strict, ESLint clean, keep/extend vitest tests for `lib` utils; update
  `frontend/README.md` with the new IA and any new components.

## Working method
1. Open glean.com and capture its patterns; write a short **style guide** (tokens + components)
   before building. 2. Inspect current `src/app/**` and `src/components/**`; plan the move of
   chat to `/chat` and the new `/` landing. 3. Build the design system, then Home, then restyle
   Chat and Dashboard. 4. Verify every existing flow still works end-to-end. 5. Keep it runnable
   at each step.

## Definition of done
- Three polished routes (Home `/`, Chat `/chat`, Dashboard `/dashboard`) with a shared premium
  header/footer and consistent design system, clearly Glean-inspired but agroecology-branded.
- Home is animated, data-rich, and genuinely impressive ("wow"); stats/charts reflect real data.
- Chat has objective + challenge quick-buttons and the intelligent in-chat map offer; all
  recommendation/explanation functionality preserved.
- Dashboard is a clean, standardized analytical surface.
- Fully responsive, accessible, dark/light, no functional or API regressions; README updated.
