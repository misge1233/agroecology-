import { describe, expect, it } from "vitest";
import type { Metadata } from "@/lib/types";
import { STEP_ORDER, autoStep, cropOptions, familyTakesCrop, parseParams, toSearch } from "./advisor-state";

const CROP = "Crop production and management";
const ISFM = "Integrated soil fertility management";

describe("four-step Advisor (1 Nov 2026)", () => {
  it("has Location, Challenge, Objective and Results for every challenge", () => {
    expect(STEP_ORDER).toEqual(["location", "challenge", "objective", "results"]);
  });

  it("offers the crop filter for crop production only", () => {
    expect(familyTakesCrop(CROP)).toBe(true);
    expect(familyTakesCrop(ISFM)).toBe(false);
    expect(familyTakesCrop(null)).toBe(false);
  });

  it("lists the crops measured in the family, else the global list", () => {
    const meta = { crop_types: ["Cattle", "Maize", "Teff"], crop_types_by_family: { [CROP]: ["Maize", "Teff"] } } as unknown as Metadata;
    expect(cropOptions(meta, CROP)).toEqual(["Maize", "Teff"]);
    expect(cropOptions(meta, ISFM)).toEqual(["Cattle", "Maize", "Teff"]);
  });

  it("keeps a crop that arrives in the URL (a chat deep link) and goes straight to results", () => {
    const p = parseParams(new URLSearchParams(`lat=11.6&lon=37.4&family=${encodeURIComponent(ISFM)}&indicator=yield&crop=Teff`), null);
    expect(p.crop).toBe("Teff");
    expect(autoStep(p)).toBe("results");
    expect(toSearch(p)).toContain("crop=Teff");
  });
});
