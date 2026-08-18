import { describe, expect, it } from "vitest";
import {
  deriveChatSetup,
  deriveDashboardSetup,
  indicatorsForFamily,
  parseFamilyFromMessage,
} from "./chat-flow";
import type { Metadata } from "./types";

const meta: Metadata = {
  practice_families: [
    "Crop production and management",
    "Livestock production and management",
  ],
  indicators: [
    { key: "yield", label: "Increase crop yield", direction: "increase" },
    { key: "biomass yield", label: "Increase biomass / fodder", direction: "increase" },
    { key: "income", label: "Increase income", direction: "increase" },
  ],
  indicators_by_family: {
    "Crop production and management": ["yield", "biomass yield", "income"],
    "Livestock production and management": ["biomass yield", "income"],
  },
  crop_types: [],
  bounds: { lat: [3.3, 14.9], lon: [32.9, 48.2] },
  model: { name: "test", note: "" },
};

describe("deriveChatSetup", () => {
  it("moves to objective after challenge is chosen", () => {
    const turns = [
      { role: "user", content: "hello" },
      { role: "assistant", content: "Hi" },
      { role: "user", content: "My challenge is Crop production and management." },
      { role: "assistant", content: "Great — what is your objective?" },
    ];
    const setup = deriveChatSetup(turns, null, null, null, meta);
    expect(setup.stage).toBe("objective");
    expect(setup.family).toBe("Crop production and management");
    expect(setup.indicatorKey).toBeNull();
  });

  it("uses the latest challenge when the user changes their mind", () => {
    const turns = [
      { role: "user", content: "My challenge is Crop production and management." },
      { role: "user", content: "My challenge is Livestock production and management." },
    ];
    const setup = deriveChatSetup(turns, null, null, null, meta);
    expect(setup.family).toBe("Livestock production and management");
  });
});

describe("indicatorsForFamily", () => {
  it("follows metadata indicators_by_family from the API", () => {
    const keys = indicatorsForFamily(meta, "Livestock production and management").map(
      (i) => i.key
    );
    expect(keys).toEqual(["biomass yield", "income"]);
  });
});

describe("deriveDashboardSetup", () => {
  it("requires location before challenge", () => {
    expect(deriveDashboardSetup(null, null, "", "", false).stage).toBe("location");
  });

  it("shows objectives only after challenge", () => {
    expect(
      deriveDashboardSetup(8.38, 39.37, "Crop production and management", "", false)
        .stage
    ).toBe("objective");
  });

  it("is complete when all slots filled", () => {
    expect(
      deriveDashboardSetup(
        8.38,
        39.37,
        "Crop production and management",
        "yield",
        false
      ).stage
    ).toBe("complete");
  });
});

describe("parseFamilyFromMessage", () => {
  it("parses structured challenge messages", () => {
    expect(
      parseFamilyFromMessage(
        "My challenge is Livestock production and management.",
        meta.practice_families
      )
    ).toBe("Livestock production and management");
  });
});

describe("natural language setup", () => {
  const fullMeta: Metadata = {
    ...meta,
    practice_families: [
      ...meta.practice_families,
      "Erosion control and water management",
      "Integrated soil fertility management",
      "Agro-forestry and forest management",
    ],
    indicators: [
      ...meta.indicators,
      { key: "soil loss", label: "Reduce soil loss / erosion", direction: "reduce" },
      { key: "runoff", label: "Reduce runoff", direction: "reduce" },
    ],
  };

  it("infers erosion challenge and soil-loss objective from free text", () => {
    const turns = [
      {
        role: "user",
        content: "I want to reduce soil loss on my sloping field near Debre Birhan",
      },
    ];
    const setup = deriveChatSetup(turns, null, null, null, fullMeta);
    expect(setup.family).toBe("Erosion control and water management");
    expect(setup.indicatorKey).toBe("soil loss");
    expect(setup.hasLocation).toBe(true);
  });

  it("uses server slots when provided", () => {
    const setup = deriveChatSetup([], null, null, null, fullMeta, {
      practice_family: "Erosion control and water management",
      indicator: "soil loss",
      lat: 9.68,
      lon: 39.53,
      place_name: "Debre Birhan",
    });
    expect(setup.stage).toBe("complete");
    expect(setup.placeName).toBe("Debre Birhan");
  });

  it("parses hyphenated water-use efficiency replies", async () => {
    const { parseIndicatorFromMessage } = await import("./chat-flow");
    const indicators = [
      ...fullMeta.indicators,
      {
        key: "water use efficiency",
        label: "Improve water-use efficiency",
        direction: "increase" as const,
      },
    ];
    expect(parseIndicatorFromMessage("improve water-use efficiency", indicators)).toBe(
      "water use efficiency"
    );
    expect(
      parseIndicatorFromMessage(
        "Near Hawassa — improve water-use efficiency with water management",
        indicators
      )
    ).toBe("water use efficiency");
  });
});
