/** Map CSA practice names to image files under /public/practices/. */

export function practiceSlug(name: string): string {
  return name
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

/** Primary image path — add `{slug}.jpg` or `{slug}.webp` under public/practices/. */
export function practiceImageSrc(name: string, ext: "webp" | "jpg" = "webp"): string {
  return `/practices/${practiceSlug(name)}.${ext}`;
}

export const PRACTICE_IMAGE_EXTENSIONS = ["webp", "jpg", "jpeg", "png"] as const;
