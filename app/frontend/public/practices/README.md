# CSA practice images

Drop one image per practice here. The chat UI resolves files from the **practice name** returned by the API.

## File naming

Use a URL-friendly slug of the practice label:

| Practice name (example) | Filename |
|-------------------------|----------|
| Mulching | `mulching.webp` |
| Crop rotation | `crop-rotation.webp` |
| Stone bunds | `stone-bunds.webp` |

Preferred format: **WebP** or **JPEG**, roughly **1200×800** (3:2 or 16:10), subject centered.

The app tries, in order: `.webp`, `.jpg`, `.jpeg`, `.png`. If none exist, a styled placeholder is shown until you add the file.
