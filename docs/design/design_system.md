# AgroAdvisor-ET design system (U1, 26 Oct 2026)

Binding tokens for the production UI. Implemented as CSS variables in
`app/frontend/src/app/globals.css` and exposed to Tailwind in
`app/frontend/tailwind.config.ts`. Components never hard-code a colour.

## 1. Palette — "Ethiopian highland"

| token | light | dark | role |
|---|---|---|---|
| `background` | `#FFFFFF` (U3; was `#F7F8F5`) | `#0F1613` | page |
| `surface` | `#FFFFFF` | `#162019` | cards, header |
| `surface-2` | `#F3F6F2` | `#131C16` | page-header band, alternating sections, wells |
| `text` | `#17241C` | `#E8EEE9` | body text |
| `muted` | `#56655C` (5.9:1 on white) | `#9FB0A5` | secondary text |
| `border` | `#E2E8E2` | `#26322A` | hairlines |
| `band` / `band-fg` / `band-muted` | `#0D3B27` / `#F1F6F2` / `#B5CBBD` (7.3:1) | `#0A1410` / `#E8EEE9` / `#9FB0A5` | footer (U3) |
| `forest-50…950` | fixed | fixed | text, scrims and buttons over photography and the CTA band only (U3) |
| `primary` | `#1E6B46` (hover `#175537`) | `#4CAF7A` | actions, high confidence, evidence tier |
| `secondary` (soil / ochre) | `#8C5A2B` | `#C9915A` | practice-record tier (P9) |
| `accent` (sky / water) | `#2E7FB8` | `#6FB3E6` | guidance tier, links (text token `accent-text` `#286FA3` since U6: 5.0:1 on `surface-2`) |
| `success` | `#2E8B57` | `#2E8B57` | confirmations |
| `warning` | `#C98A1E` | `#C98A1E` | medium confidence |
| `danger` | `#B23A3A` | `#B23A3A` | **system errors only** — never for low confidence |

**Confidence semantics (honest display):** high = primary green badge;
medium = warning-amber badge; **low = neutral grey badge labelled "thin
evidence"**. Low confidence is never red.

**Tier chips:** field evidence = primary outline · implementation guidance =
accent outline · practice record (P9) = secondary outline.

### 1.1 Measured contrast (WCAG 2.1, relative-luminance formula)

Every text/background pair in use. The brief's hues were measured as given;
four of them fail AA **as text**, so derived `*-text` tokens are used for text
while the briefed hue is kept for fills, icons and badges. Filled buttons pick
the foreground that passes: white on the light primary, **dark text on the
dark primary** (white on `#4CAF7A` is only 2.72:1).

| mode | foreground | hex | background | hex | ratio | WCAG |
|---|---|---|---|---|---:|---|
| light | text | `#1C2A22` | background | `#F7F8F5` | 14.03:1 | AA |
| light | text | `#1C2A22` | surface | `#FFFFFF` | 14.96:1 | AA |
| light | muted | `#5B6B61` | background | `#F7F8F5` | 5.30:1 | AA |
| light | muted | `#5B6B61` | surface | `#FFFFFF` | 5.64:1 | AA |
| light | primary | `#1E6B46` | background | `#F7F8F5` | 6.07:1 | AA |
| light | primary | `#1E6B46` | surface | `#FFFFFF` | 6.47:1 | AA |
| light | white | `#FFFFFF` | primary | `#1E6B46` | 6.47:1 | AA (buttons) |
| light | white | `#FFFFFF` | primary-hover | `#175537` | 8.78:1 | AA |
| light | secondary | `#8C5A2B` | background | `#F7F8F5` | 5.45:1 | AA |
| light | white | `#FFFFFF` | secondary | `#8C5A2B` | 5.81:1 | AA |
| light | accent (fill) | `#2E7FB8` | background | `#F7F8F5` | 4.07:1 | AA-large only → |
| light | **accent-text** | `#2B77AD` | background | `#F7F8F5` | 4.53:1 | AA (derived) |
| light | success (fill) | `#2E8B57` | background | `#F7F8F5` | 3.98:1 | AA-large only → |
| light | **success-text** | `#2B8151` | background | `#F7F8F5` | 4.52:1 | AA (derived) |
| light | warning (fill) | `#C98A1E` | background | `#F7F8F5` | 2.76:1 | **FAIL as text** → |
| light | **warning-text** | `#976816` | background | `#F7F8F5` | 4.57:1 | AA (derived) |
| light | dark text | `#0F1613` | warning fill | `#C98A1E` | 6.24:1 | AA (badge) |
| light | danger | `#B23A3A` | background | `#F7F8F5` | 5.53:1 | AA |
| light | white | `#FFFFFF` | danger | `#B23A3A` | 5.90:1 | AA |
| light | border | `#DDE4DE` | background | `#F7F8F5` | 1.21:1 | decorative hairline |
| dark | text | `#E8EEE9` | background | `#0F1613` | 15.59:1 | AA |
| dark | text | `#E8EEE9` | surface | `#182019` | 14.16:1 | AA |
| dark | muted | `#9FB0A5` | background | `#0F1613` | 8.06:1 | AA |
| dark | muted | `#9FB0A5` | surface | `#182019` | 7.33:1 | AA |
| dark | primary | `#4CAF7A` | background | `#0F1613` | 6.75:1 | AA |
| dark | **dark text** | `#0F1613` | primary | `#4CAF7A` | 6.75:1 | AA (buttons) |
| dark | white | `#FFFFFF` | primary | `#4CAF7A` | 2.72:1 | **FAIL — not used** |
| dark | secondary | `#C9915A` | background | `#0F1613` | 6.71:1 | AA |
| dark | accent | `#6FB3E6` | background | `#0F1613` | 8.10:1 | AA |
| dark | warning | `#C98A1E` | background | `#0F1613` | 6.24:1 | AA |
| dark | success (fill) | `#2E8B57` | background | `#0F1613` | 4.32:1 | AA-large only → |
| dark | **success-text** | `#5FBF8B` | background | `#0F1613` | ≥ 4.5:1 | AA (derived) |
| dark | danger (fill) | `#B23A3A` | background | `#0F1613` | 3.11:1 | AA-large only → |
| dark | **danger-text** | `#C26363` | background | `#0F1613` | 4.59:1 | AA (derived) |
| dark | border | `#2A362E` | background | `#0F1613` | 1.46:1 | decorative hairline |

Rule: body and label text use `text`/`muted`; coloured **text** uses the
`*-text` token; coloured **fills** use the base token with the `*-fg`
foreground. All pairs listed above as "AA" are ≥ 4.5:1.

### 1.2 Chart palette (6 categorical steps)

Derived from the three brand hues (primary green, secondary ochre, accent
blue), two lightness levels each, assigned by a search that maximises the
minimum CIE76 ΔE between any two steps under normal vision **and** under
protanopia, deuteranopia and tritanopia (Machado et al. 2009 simulation,
severity 1.0), subject to every step having ≥ 3:1 contrast against the page
background (WCAG non-text UI minimum).

| step | light | dark |
|---|---|---|
| chart-1 | `#3F2E1D` | `#AE6F34` |
| chart-2 | `#193C55` | `#6695B6` |
| chart-3 | `#246345` | `#4CD895` |
| chart-4 | `#169055` | `#E39C5A` |
| chart-5 | `#9C591A` | `#8CC6EE` |
| chart-6 | `#2692DE` | `#C6EDDA` |

Measured: light — min pairwise ΔE 26.1 (normal), 19.6 (protan), 16.1
(deutan), **15.6 (tritan)**; contrast vs background 3.15–12.16:1. Dark — min
pairwise ΔE 17.7 / 17.5 / 17.9 / 17.7; contrast 4.48–14.44:1. A ΔE of 15 is
clearly noticeable; the palette is CVD-safe for six categories, and charts
also label series directly (never colour alone).

## 2. Typography

- One UI family: **IBM Plex Sans** (400/500/600/700) with tabular numerals
  (`font-feature-settings: "tnum"`) for every figure.
- **Noto Sans Ethiopic** (self-hosted through `next/font/local`, ethiopic subset, variable 400–600 — see `app/frontend/src/app/fonts/README.md`; Turbopack's Google-font loader rejects this family) is applied when
  `<html lang="am">`; body line-height gets +2 px, headings +2 px.
- The serif display face is dropped; headings are Plex Sans 600/700.
- Scale: 12 / 14 / 16 / 18 / 22 / 28 / 36 px. Line-height 1.5 body, 1.2
  headings. Letter-spacing −0.01em on headings.

## 3. Spacing, shape, elevation, motion

- 4 px grid (Tailwind default scale).
- Radius: **12 px cards** (`rounded-card`), **8 px controls**
  (`rounded-control`), full pills for chips and badges.
- Two elevation levels: `shadow-1` (resting cards), `shadow-2` (dialogs,
  sheets, popovers).
- Focus ring: 2 px `primary` with 2 px offset, on every interactive element
  via `:focus-visible`.
- Motion ≤ 200 ms (`duration-fast` 120 ms, `duration-base` 200 ms);
  `prefers-reduced-motion: reduce` collapses all animation and transitions.

## 4. Iconography and imagery

- Icons: lucide-react, 16–20 px, `aria-hidden` unless they are the only label.
- Practice images: the 54 WebP files in `public/practices` via `next/image`
  with explicit `sizes`; a tokenised placeholder when a practice has no image.

## 5. Components (shadcn/ui pattern on Radix)

Copy-in components under `src/components/ui`, styled with the tokens through
class-variance-authority + tailwind-merge: `Button` (primary / secondary /
outline / ghost / danger; sm / md / lg; loading), `Card`, `Badge`, `Chip`,
`Tabs`, `Dialog`, `Sheet` (mobile bottom sheet), `Tooltip`, `Select`,
`Combobox`, `Toast`, `Skeleton`, `Alert`, `Stepper`.

## 6. Honest-display rules (binding)

1. Every number on screen comes from the API; the UI composes sentences from
   API numbers but never computes a new effect, count or percentage.
2. Low confidence is "thin evidence" in neutral grey — never danger red.
3. Danger red is reserved for system errors (API unreachable, request failed).
4. Effect magnitudes from the knowledge graph never reach the UI; the
   evidence-base line shows counts and provenance only.
5. Source badge per result set: **Field-trial model** today; **Hybrid** and
   **Documented practice** reserved for P9, with tooltip copy in all three
   languages so P9 is a backend change only.

## Verification (U1)

| check | result | where |
|---|---|---|
| WCAG AA contrast, every text/background pair | all ≥ 4.5:1 after the derived `*-text` tokens (table above) | this file |
| CVD safety of the 6-step chart palette | min CIE76 ΔE 15.6 (light) / 17.5 (dark) under protan/deutan/tritan simulation | this file |
| axe-core 4.14 on home, advisor step 1, results (en + am), chat, about | 0 violations (now a Playwright test on every run) | `app/frontend/e2e/advisor-flow.spec.ts` |
| Lighthouse 13.5 (mobile) on `/en`, `/en/advisor`, results, `/en/chat` | U2: A11y 100, Best practices 100 everywhere; Perf 93–99 (results 83–97 across runs) — U1 was 74–89 | `lighthouse/README.md` |
| Screenshots light/dark × phone/desktop × en/am/om | 13 PNGs | `screenshots/` |
| Reduced motion | global `prefers-reduced-motion` block; only CSS transitions ≤ 200 ms and one 180 ms keyframe | `globals.css` |
| Focus ring | 2 px `--ring` outline with 2 px offset on every `:focus-visible` | `globals.css` |

## U2 additions (27–28 Oct 2026)

- **Typography is fully self-hosted.** IBM Plex Sans (variable, latin + italic) joins
  Noto Sans Ethiopic under `app/frontend/src/app/fonts/` with both OFL licences; no
  Google Fonts request is made by a production build. Weights used: 400 / 500 / 600.
- **Effect sentence grammar.** The engine's sentence is now "~42% reduction in soil
  loss" / "~12% increase in yield" (`recommend.py`, one f-string); `goal_direction`
  still carries `reduce` / `increase`. The glossary frame for en mirrors it; am/om
  frames unchanged.
- **Chat.** Turns carry a role label and a timestamp; the assistant turn shows an
  explicit state (thinking → scoring → writing → done, or an error with "Send again");
  result cards are the Advisor's `ResultCard` + compact `ContextCard` + source badge;
  quick replies are chips (challenge, objective, map / device location) that send a
  sentence in the UI language plus a structured hint; "Open in Advisor" deep-links the
  scored query.
- **Print sheet** (`advisor/print-sheet.tsx`): black on white, 11 pt, one column; the
  request, the context table, each ranked practice with the model's effect sentence,
  confidence + meaning, field-observation count, evidence-base line and sources, the
  source badge text, the disclaimer, the generation date and the share link. The app
  chrome and the interactive results are `no-print`.
- **Low bandwidth.** Blurred 16×9 placeholder in the palette for practice photos and a
  text fallback; bounded retry (600 ms, 1.8 s) with a warning-toned "retrying…" strip;
  map deferred on phones behind "Show the map"; tile failure → warning alert, inputs
  stay usable.
- **Phone width.** The header's language switcher is icon-only below `sm` (the full
  trigger pushed the header past 390 px — the U1 review's item 0a); every screen is
  guarded at 360/390/412/768/1440 px by the Playwright overflow test.

## P9 additions (28 Oct 2026) — evidence-tiered advisory

- **Source badge is now mode-driven.** `ModeBadge` (`advisor/mode-badge.tsx`) maps the
  API mode to the U1 glossary modes reserved for this: `model-led → "Field-trial model"`
  (outline-primary), `hybrid → "Hybrid"` (outline-accent), `knowledge-led → "Documented
  practice"` (outline-secondary). The tooltip explains the mode and lists the backend's
  reasons; `ModeReasons` repeats them as a card above the ranking in hybrid and
  knowledge-led mode. Reasons are catalog keys (`advisor.results.mode.reason.*`) with
  params; the practice inside a reason is localised through the glossary, the moisture
  zone stays an English code (`Dry-lowland`).
- **Documented practices** (`advisor/knowledge-candidates.tsx`): secondary-outline cards
  (`border-secondary/50`) ranked "Suggested #n", one source chip per provenance
  (evidence green = field evidence for other objectives, guidance sky = described in
  guidance documents, practice ochre = practice record), the glossary label of the
  component, the backend's deterministic "Why this is suggested" line (counts only — the
  rationale-number guard is tested), support counts, the frozen practices of the family
  that contain the component, and citation chips with the per-study / per-document /
  per-record markers `[n]`, `[Gn]`, `[Wn]` (first six shown, "Show all sources (n)"
  folds the rest; a study outside the ERA corpus is labelled "Dataset study #id" rather
  than "Untitled study"). **Never a percentage, never an effect sentence, never a chart** — the
  honest-display rules of §6 apply unchanged; the E2E asserts no `%`/`±` in the section.
- **Knowledge-led state** replaces the "no field evidence" error: an info Alert
  (`advisor.results.knowledgeLed.*`) with the badge, the context card when the belt
  resolved, the reasons card and the documented practices. No "Explain in chat" button
  (there is no ranking to explain); "Save as PDF" stays and prints the same sections.
- **Chat**: the `advisory` SSE event arrives before `recommendation`; hybrid turns show
  the compact documented-practice cards under the ranking with a one-line caption,
  knowledge-led turns show the badge + caption + cards and the "Open in Advisor" link
  built from the advisory's own query. Quick-reply chips do not reappear after a
  knowledge-led answer (the setup is complete).
- **Evidence panel chips** show the citation marker (`[1]`, `[G2]`) the explanation
  uses, so a reader can match a sentence to its study.
- **Print sheet** carries the mode in the header, the reasons under the source line, and
  a "Documented practices" section in hybrid / knowledge-led mode.


## U3 — site structure and layout (30 Oct 2026)

- **Four pages, one header.** Home `/`, About `/about`, Advisor `/advisor`,
  Chat `/chat` (`nav-items.ts`). Desktop: underline-active links plus a
  "Get advice" button from `lg`. Phones: a hamburger disclosure panel
  (`#mobile-nav`, Escape closes); the U1 bottom tab bar is removed.
- **One container.** `.container-page` (globals.css): max 1280 px, gutters
  16 / 24 / 32 px. Every section uses it; no ad-hoc `max-w-*` page widths.
- **Page header band.** Inner pages open with `PageHeader` (surface-2 band,
  h1, one lead sentence); `compact` on task pages (Advisor).
- **Type.** Display sizes `4xl` 44 px and `5xl` 56 px for the hero and page
  titles; `.eyebrow` (13 px, uppercase, primary) above section headings.
- **Imagery.** Home hero and challenge-area cards use the shipped practice
  photos (`public/practices`), decorative (`alt=""`) with a forest scrim
  under any text. Buttons over photos use the `inverse` / `outline-inverse`
  variants.
- **Footer.** Brand band: brand + attribution, Explore (the four pages),
  Resources (About anchors), bottom bar with disclaimer, copyright, version.
  Hidden on `/chat`, which is a full-height app view.