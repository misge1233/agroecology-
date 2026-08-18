# Frontend — Agroecology AI (Next.js)

Premium three-page UI over the FastAPI CSA recommender.

## Information architecture

| Route | Purpose |
|---|---|
| **`/` Home** | Marketing / scrollytelling landing — hero ask input, animated stats, how-it-works, science bento, demo charts, practice families, data provenance, CTA |
| **`/chat` Chat** | Natural-language advisor (SSE). Quick chips for objectives + challenges, in-chat map picker, clean recommendation cards + “Why this?” |
| **`/dashboard` Dashboard** | Analyst surface — map pin + synced lat/long, challenge/objective/crop/top-N form, ranked practices, effect chart, local context, copy/CSV export |

Shared sticky translucent header (Home / Chat / Dashboard), theme toggle, and multi-column footer on the landing page.

## Design system

Tokens live in `src/app/globals.css` + `tailwind.config.ts` (leaf greens + blue→violet→pink accents, glass, aurora panels). Reusable primitives under `src/components/ui/` (`Button`, `Reveal`/`Section`/`GlassCard`/`GradientText`, `StatCounter`/`Chip`/`MarqueeRow`).

## Setup

```bash
cd frontend
cp .env.example .env.local
npm install
npm run dev
```

Open http://localhost:3000

Set `NEXT_PUBLIC_API_BASE_URL` to the backend (default `http://127.0.0.1:8000`).

## Stack

Next.js 15 (App Router) · React 19 · TypeScript · Tailwind · framer-motion ·
recharts · react-markdown · react-leaflet + leaflet · Manrope + Fraunces fonts.

## Scripts

```bash
npm run build   # production build
npm run lint    # eslint
npm run test    # vitest (lib/util unit tests)
```

## Notes

- Location: Leaflet pin and numeric lat/long stay in sync; Ethiopia bounds validated; AEZ zone resolved via `/context`.
- Chat seeds from Home/Dashboard via `sessionStorage` key `agro-seed-message`.
- Recommendation/chat contracts are unchanged — restyle only; see `src/lib/api.ts` and `src/lib/types.ts`.
