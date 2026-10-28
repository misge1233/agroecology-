# Self-hosted fonts (U1 → U2)

Both typefaces ship with the app so a production build never reaches Google Fonts
(CI, air-gapped and low-connectivity deployments) and so `next dev`/`next build` do
not depend on the Turbopack Google-font loader (which rejects Noto Sans Ethiopic —
"next/font/google queries have exactly one entry"). Loaded through `next/font/local`
in `src/app/[locale]/layout.tsx`.

| file | face | subset / axes | licence |
|---|---|---|---|
| `IBMPlexSans-latin.woff2` | IBM Plex Sans, upright | latin, variable `wght` 100–700 (declared 400–600) | SIL OFL 1.1 — `LICENSE-IBMPlexSans.txt` |
| `IBMPlexSans-latin-italic.woff2` | IBM Plex Sans, italic | latin, variable `wght` 100–700 (declared 400–600) | SIL OFL 1.1 — `LICENSE-IBMPlexSans.txt` |
| `NotoSansEthiopic-ethiopic.woff2` | Noto Sans Ethiopic | ethiopic, variable `wght` 100–900 (declared 400–600) | SIL OFL 1.1 — `LICENSE-NotoSansEthiopic.txt` |

Sources: the Google Fonts CSS API served files (IBM Plex Sans v23 variable,
Noto Sans Ethiopic v47 variable), downloaded on 2026-10-26/27. Reserved Font Names
("Plex", "Noto") apply per the OFL; the files are unmodified.

`unicode-range` for Noto Sans Ethiopic is limited to the Ethiopic blocks
(`U+1200-1399, U+2D80-2DDE, U+AB01-AB2E, U+1E7E0-1E7FE` + `U+030E`) so Latin
letters and digits inside Amharic text still render in IBM Plex Sans.
