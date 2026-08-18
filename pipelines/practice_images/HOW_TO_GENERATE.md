# Practice images — how to generate the real photos

**Goal:** one photorealistic image per CSA practice (like the "Inorganic Fertilizer" sample),
saved here as `<slug>.webp`, 1200×800.

## Filename = slug of the practice label
lowercase → non-alphanumeric runs to `-` → trim `-`.
| Practice | Filename |
|---|---|
| Mulch | `mulch.webp` |
| Crop Rotation | `crop-rotation.webp` |
| Stone bunds | `stone-bunds.webp` |
| Integrated soil fertility management | `integrated-soil-fertility-management.webp` |

Casing variants share one slug (e.g. both "Deficit Irrigation" spellings → `deficit-irrigation.webp`).

## Files here
- `image_prompts.csv` — 99 practices → `slug`, `filename`, `practice_family`, `n_observations`,
  and a tuned photorealistic `image_prompt` (Ethiopian smallholder context).
- `generate_practice_images.py` — generates every `<slug>.webp` from those prompts.

## Run it (needs an image-model key + internet)
```bash
pip install pillow requests openai
export OPENAI_API_KEY=sk-...        # or GEMINI_API_KEY / STABILITY_API_KEY
python generate_practice_images.py               # all 99
python generate_practice_images.py --only mulch  # a subset
```
Output lands right here with the correct slug filenames. Drop the folder into the app at
`frontend/public/practice-images/` (or point the UI here).

> Note: these photos must be generated with an external image model — they could not be
> produced inside the build sandbox (no image tool / no internet there).
