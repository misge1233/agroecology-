import { describe, expect, it } from "vitest";
import fixture from "./number-format.fixture.json";
import { displayText } from "./numbers";

describe("display rounding (shared with the backend)", () => {
  for (const { in: value, out } of fixture as Array<{ in: number; out: string }>) {
    it(`${value} -> ${out}`, () => expect(displayText(value)).toBe(out));
  }
});