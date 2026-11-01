/** Map practice names to image files under /public/practices/. */

export function practiceSlug(name: string): string {
  return name
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

/**
 * The images that exist (every file is WebP). Resolving against this list
 * means no request is made for a missing image: no 404s in the console and
 * no flash of a broken image (U9, D12/D13). Regenerate when adding photos.
 */
export const PRACTICE_IMAGES: ReadonlySet<string> = new Set([
  "agroforestry-fallow",
  "agroforestry-pruning",
  "agroforestry-pruning-inorganic-fertilizer",
  "agroforestry-pruning-inorganic-fertilizer-reduction",
  "agronomic-biological-swcp",
  "alleycropping",
  "alleycropping-crop-rotation",
  "alleycropping-crop-rotation-improved-varieties",
  "alleycropping-crop-rotation-improved-varieties-inorganic-fertilizer",
  "alleycropping-improved-varieties-inorganic-fertilizer-intercropping",
  "alleycropping-improved-varieties-intercropping",
  "alleycropping-inorganic-fertilizer",
  "alleycropping-inorganic-fertilizer-intercropping",
  "alleycropping-intercropping",
  "animal-feed-management",
  "biochar-inorganic-fertilizer",
  "biochar-inorganic-fertilizer-organic-fertilizer",
  "biochar-organic-fertilizer",
  "inorganic-fertilizer",
  "inorganic-fertilizer-reduction",
  "inorganic-fertilizer-supplemental-irrigation",
  "inorganic-fertilizer-water-harvesting",
  "intercropping",
  "intercropping-mulch",
  "intercropping-or-rotation",
  "intercropping-reduced-tillage",
  "intercropping-water-harvesting",
  "isfm",
  "iwm",
  "mulch",
  "mulch-organic-fertilizer",
  "mulch-organic-fertilizer-reduced-tillage",
  "mulch-other-agroforestry-reduced-tillage",
  "mulch-reduced-tillage",
  "mulch-water-harvesting",
  "multistrata-agroforestry",
  "organic-amedements",
  "organic-fertilizer",
  "organic-fertilizer-ph-control",
  "organic-fertilizer-water-harvesting",
  "other-agroforestry",
  "other-agroforestry-reduced-tillage",
  "overhead-irrigation-with-mulching",
  "parklands",
  "pasture-management",
  "ph-control",
  "ph-control-water-harvesting",
  "physical-biological-swc-practices",
  "physical-swc-measures",
  "reduced-tillage",
  "reduced-tillage-water-harvesting",
  "supplemental-irrigation",
  "water-harvesting",
  "weeding",
]);

/** Practices whose photo is filed under another name (spelling variants, synonyms). */
const ALIASES: Record<string, string> = {
  "biological-swc-practices": "agronomic-biological-swcp",
  "physical-swc-practices": "physical-swc-measures",
  "organic-amendments": "organic-amedements",
  "in-situ-water-harvesting": "water-harvesting",
  "crop-residue-incorporation": "mulch",
  "conservation-tillage": "reduced-tillage",
  "intercropping-or-rotation": "intercropping-or-rotation",
  "biochar": "biochar-organic-fertilizer",
  "grazing-management": "pasture-management",
  "exclosure": "pasture-management",
  "feed-substitution": "animal-feed-management",
  "feed-addition-feed-processing": "animal-feed-management",
  "improved-fallow": "agroforestry-fallow",
  "deficit-irrigation": "supplemental-irrigation",
  "drip-irrigation": "supplemental-irrigation",
  "furrow-irrigation": "supplemental-irrigation",
  "furrow-irrigation-alternate": "supplemental-irrigation",
};

function resolveSlug(slug: string): string | null {
  if (PRACTICE_IMAGES.has(slug)) return slug;
  const alias = ALIASES[slug];
  return alias && PRACTICE_IMAGES.has(alias) ? alias : null;
}

/**
 * The image for a practice: its own photo, an alias, or for a combination
 * ("Improved Varieties-Mulch") the photo of its first component that has one.
 * Null when nothing fits; the card then shows its illustrated fallback.
 */
export function practiceImagePath(name: string): string | null {
  const own = resolveSlug(practiceSlug(name));
  if (own) return `/practices/${own}.webp`;
  for (const part of name.split("-")) {
    const hit = resolveSlug(practiceSlug(part));
    if (hit) return `/practices/${hit}.webp`;
  }
  return null;
}

/** Primary image path for a practice slug (kept for older callers). */
export function practiceImageSrc(name: string, ext: "webp" | "jpg" = "webp"): string {
  return `/practices/${practiceSlug(name)}.${ext}`;
}

export const PRACTICE_IMAGE_EXTENSIONS = ["webp", "jpg", "jpeg", "png"] as const;
