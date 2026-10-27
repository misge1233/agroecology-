# AgroAdvisor-ET design system (U1, 26 Oct 2026)

Binding tokens for the production UI. Implemented as CSS variables in
`app/frontend/src/app/globals.css` and exposed to Tailwind in
`app/frontend/tailwind.config.ts`. Components never hard-code a colour.

## 1. Palette — "Ethiopian highland"

| token | light | dark | role |
|---|---|---|---|
| `background` | `#F7F8F5` | `#0F1613` | page |
| `surface` | `#FFFFFF` | `#182019` | cards, header |
| `surface-2` | `#EEF2EE` | `#1F2A22` | wells, map placeholder |
| `text` | `#1C2A22` | `#E8EEE9` | body text |
| `muted` | `#5B6B61` | `#9FB0A5` | secondary text |
| `border` | `#DDE4DE` | `#2A362E` | hairlines |
| `primary` | `#1E6B46` (hover `#175537`) | `#4CAF7A` | actions, high confidence, evidence tier |
| `secondary` (soil / ochre) | `#8C5A2B` | `#C9915A` | practice-record tier (P9) |
| `accent` (sky / water) | `#2E7FB8` | `#6FB3E6` | guidance tier, links |
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
| axe-core 4.14 on home, advisor results (en + am), chat | 0 violations | `lighthouse/axe-*.json` |
| Lighthouse 13.5 (mobile) on `/en`, `/en/advisor`, results, `/en/chat` | A11y 100 everywhere; Perf 74–89; BP 77–81 (see notes) | `lighthouse/README.md` |
| Screenshots light/dark × phone/desktop × en/am/om | 13 PNGs | `screenshots/` |
| Reduced motion | global `prefers-reduced-motion` block; only CSS transitions ≤ 200 ms and one 180 ms keyframe | `globals.css` |
| Focus ring | 2 px `--ring` outline with 2 px offset on every `:focus-visible` | `globals.css` |
