import { describe, expect, it } from "vitest";
import { createTranslator } from "next-intl";
import en from "../../messages/en.json";
import am from "../../messages/am.json";
import om from "../../messages/om.json";
import { advisorQuery, challengeMessage, locationMessage, objectiveMessage } from "./chat-protocol";

const EROSION = "Erosion control and water management";
const soilLoss = { key: "soil loss", label: "Reduce soil loss / erosion", direction: "reduce" as const };
const tFor = (locale: "en" | "am" | "om") =>
  createTranslator({ locale, messages: { en, am, om }[locale], namespace: "chat" });

describe("quick-reply protocol (U2)", () => {
  it("keeps the English sentences the backend parser has always read", () => {
    const t = tFor("en");
    expect(challengeMessage(t, "en", EROSION).text).toBe("My challenge is Erosion control and water management.");
    expect(objectiveMessage(t, "en", soilLoss).text).toBe("My objective is to reduce soil loss / erosion.");
    expect(locationMessage(t, "en", 8.38, 39.37, { family: EROSION, indicator: soilLoss }).text).toBe(
      "My farm is at 8.3800, 39.3700. Challenge: Erosion control and water management. Objective: reduce soil loss / erosion."
    );
  });

  it("translates the sentence but keeps canonical values in the hint", () => {
    for (const locale of ["am", "om"] as const) {
      const t = tFor(locale);
      const c = challengeMessage(t, locale, EROSION);
      expect(c.text).not.toContain(EROSION);
      expect(c.hint).toEqual({ practice_family: EROSION });
      const o = objectiveMessage(t, locale, soilLoss);
      expect(o.hint).toEqual({ indicator: "soil loss" });
      const l = locationMessage(t, locale, 8.38, 39.37, { family: EROSION, indicator: soilLoss });
      expect(l.hint).toEqual({ lat: 8.38, lon: 39.37, practice_family: EROSION, indicator: "soil loss" });
      expect(l.text).toContain("8.3800");
    }
    expect(challengeMessage(tFor("am"), "am", EROSION).text).toMatch(/[ሀ-፿]/);
  });

  it("builds the Advisor deep link from the scored query", () => {
    expect(
      advisorQuery({ lat: 8.38, lon: 39.37, practice_family: EROSION, indicator: "soil loss", crop_type: "Maize", goal_direction: "reduce" }, 3)
    ).toEqual({ lat: "8.38", lon: "39.37", family: EROSION, indicator: "soil loss", crop: "Maize", top: "3" });
  });
});
