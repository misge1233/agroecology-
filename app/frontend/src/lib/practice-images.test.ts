import { existsSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { PRACTICE_IMAGES, practiceImagePath } from "./practice-images";

const PUBLIC = join(__dirname, "..", "..", "public");

describe("practice images (U9, D12)", () => {
  it("lists only files that exist", () => {
    for (const slug of PRACTICE_IMAGES) expect(existsSync(join(PUBLIC, "practices", `${slug}.webp`))).toBe(true);
  });

  it("gives Biological SWC practices an existing illustration", () => {
    expect(practiceImagePath("Biological SWC practices")).toBe("/practices/agronomic-biological-swcp.webp");
  });

  it("uses the first illustrated component of a combination", () => {
    expect(practiceImagePath("Improved Varieties-Mulch")).toBe("/practices/mulch.webp");
    expect(practiceImagePath("Mulch")).toBe("/practices/mulch.webp");
  });

  it("returns null instead of a missing file", () => {
    expect(practiceImagePath("Improved Varieties")).toBeNull();
    for (const p of ["Crop Rotation", "Exclosure", "Drought tolerrant crops", "In-situ water harvesting"]) {
      const path = practiceImagePath(p);
      if (path) expect(existsSync(join(PUBLIC, path))).toBe(true);
    }
  });
});
