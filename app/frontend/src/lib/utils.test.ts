import { describe, expect, it } from "vitest";
import { formatPct, isBeneficial } from "./utils";

describe("isBeneficial", () => {
  it("treats reductions as good for reduce goals", () => {
    expect(isBeneficial(-50.9, "reduce")).toBe(true);
    expect(isBeneficial(10, "reduce")).toBe(false);
  });

  it("treats increases as good for increase goals", () => {
    expect(isBeneficial(28, "increase")).toBe(true);
    expect(isBeneficial(-5, "increase")).toBe(false);
  });
});

describe("formatPct", () => {
  it("formats with sign", () => {
    expect(formatPct(12.34)).toBe("+12.3%");
    expect(formatPct(-50.9)).toBe("-50.9%");
  });
});
