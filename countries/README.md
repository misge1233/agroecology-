# countries: country configuration

Country is configuration (roadmap principle 5, `docs/decisions/enhancement_v2.md` §4): nothing in
the pipelines, models or UI hard-codes Ethiopia; it reads `countries/<CC>.yaml`. The loader is
`pipelines/common/country_config.py` (`load_country("ET")` returns a validated `CountryConfig`).

| File | Status | Notes |
|---|---|---|
| `ET.yaml` | `active` | Ethiopia: 250 m stack, AEZ belt anchor, en/am/om, ERA + CSA + HAB evidence |
| `KE.yaml` | `draft` | Kenya: dry run of the abstraction, no data behind it |

## Keys

| Key | Meaning |
|---|---|
| `code` | ISO 3166-1 alpha-2, equal to the file name |
| `name` | display name |
| `status` | `active` (served), `draft`, `planned` or `retired` |
| `bbox` | `lon_min, lon_max, lat_min, lat_max` (WGS84); a pin outside it is rejected |
| `grid` | grid definition (repo-relative path) |
| `aez` | `anchor_raster`, `lookup`, `attributes` of the national agro-ecological zone product |
| `languages` | UI languages |
| `evidence_sources` | evidence-store sources enabled for the country (`ERA`, `CSA`, `HAB`, ...) |
| `knowledge_sources` | knowledge layers (`catalogue`, `guidelines`, `gardian`, `era_papers`) |
| `exposure` | `min_rows`, `min_studies`, `min_docs` of the challenge/objective exposure rule (roadmap 5.4) |
| `overlays` | optional landscape overlays (Omo-Gibe), each with a `status` |
| `contact` | responsible institution |

## Validation (fail fast)

`code` is two upper-case letters and matches the file name; `status` is known; the bounding box is
ordered and inside WGS84; thresholds are integers >= 1. For an **active** country `grid` and the
three `aez` paths must be set and the files must exist (repo-relative), and `languages` and
`evidence_sources` must be non-empty. Draft countries and planned overlays are not file-checked.

## Adding a country

Copy `KE.yaml`, fill the keys, add the national AEZ product and lookups, add its evidence sources
to the store, translations to the UI, and set `status: active` only when `load_country` passes.
Then `python pipelines/evidence/build_registry.py --country <CC>`.
