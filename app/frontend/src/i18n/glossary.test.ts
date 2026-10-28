import { describe, expect, it } from "vitest";
import {
  AEZ_BELTS, COMPONENTS, COMPONENT_ALIASES, CROP_GROUPS, FAMILIES, INDICATORS,
  aezName, canonicalComponent, effectSentence, familyName, indicatorLabel, practiceComponents, practiceName, splitPractice,
} from "./glossary";
import { LOCALES } from "./routing";

describe("practice decomposition (mirrors rag/graph/practice_components.py)", () => {
  it("splits on '-' but protects In-situ water harvesting", () => {
    expect(splitPractice("Biochar-Inorganic Fertilizer-Organic Fertilizer")).toEqual(["Biochar", "Inorganic Fertilizer", "Organic Fertilizer"]);
    expect(splitPractice("In-situ water harvesting")).toEqual(["In-situ water harvesting"]);
    expect(splitPractice("Intercropping or Rotation")).toEqual(["Intercropping or Rotation"]);
  });
  it("normalises case and the frozen typos through the alias table", () => {
    expect(canonicalComponent("Deficit irrigation")).toBe("Deficit Irrigation");
    expect(canonicalComponent("organic amedements")).toBe("Organic Amendments");
    expect(canonicalComponent("Drought tolerrant crops")).toBe("Drought Tolerant Crops");
    expect(practiceComponents("Mulch-Mulch-Reduced Tillage")).toEqual(["Mulch", "Reduced Tillage"]);
  });
  it("has exactly the 44 canonical components, all translated in three languages", () => {
    const canonical = new Set(Object.values(COMPONENT_ALIASES));
    expect(canonical.size).toBe(44);
    expect(new Set(Object.keys(COMPONENTS))).toEqual(canonical);
    for (const entry of Object.values(COMPONENTS)) for (const l of LOCALES) expect(entry[l]).toBeTruthy();
  });
});

describe("display names", () => {
  it("composes practice names with a localised joiner", () => {
    expect(practiceName("Biochar-Inorganic Fertilizer", "en")).toBe("Biochar + Inorganic fertilizer");
    expect(practiceName("Biochar-Inorganic Fertilizer", "am")).toBe("ባዮቻር + ኬሚካል ማዳበሪያ");
    expect(practiceName("Biochar-Inorganic Fertilizer", "om")).toBe("Baayoochaarii + Xaa'oo keemikaalaa");
  });
  it("passes unknown data values through unchanged instead of guessing", () => {
    expect(practiceName("Brand New Practice", "am")).toBe("Brand New Practice");
    expect(aezName("Unknown Belt", "om")).toBe("Unknown Belt");
    expect(familyName(null, "en")).toBe("");
  });
  it("covers every family, indicator, belt and crop group in all three languages", () => {
    for (const table of [FAMILIES, INDICATORS, AEZ_BELTS, CROP_GROUPS]) {
      for (const entry of Object.values(table)) for (const l of LOCALES) expect(entry[l]).toBeTruthy();
    }
    expect(Object.keys(FAMILIES)).toHaveLength(5);
    expect(Object.keys(INDICATORS)).toHaveLength(7);
    expect(Object.keys(AEZ_BELTS)).toHaveLength(12);
    expect(Object.keys(CROP_GROUPS)).toHaveLength(14);
    expect(indicatorLabel("soil loss", "am")).toContain("መሸርሸር");
  });
});

describe("effectSentence uses only API numbers", () => {
  it("reproduces the engine's English sentence", () => {
    expect(effectSentence(-42.3, "reduce", "soil loss", "en")).toBe("~42% reduction in soil loss");
    expect(effectSentence(31.6, "increase", "yield", "en")).toBe("~32% increase in yield");
  });
  it("translates the frame, not the number", () => {
    expect(effectSentence(-42.3, "reduce", "soil loss", "am")).toBe("በየአፈር መሸርሸር ~42% ቅናሽ");
    expect(effectSentence(31.6, "increase", "yield", "om")).toBe("oomisha ~32% dabaluu");
  });
});
