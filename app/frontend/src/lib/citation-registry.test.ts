import { describe, expect, it } from "vitest";
import { buildRegistry, citationIdentity, relabelMarkers } from "./citation-registry";

const studyA = { tier: "evidence", era_code: "NN0123", title: "Mulch trial" };
const studyB = { tier: "evidence", study_no: "CSA_18", title: "Bunds" };
const guideX = { tier: "guidance", url: "https://cgspace.cgiar.org/handle/10568/1", title: "Guide X" };
const guideY = { tier: "guidance", url: "https://cgspace.cgiar.org/handle/10568/2", title: "Guide Y" };

describe("one citation registry per page", () => {
  it("gives each distinct source one label, numbered per tier, stable as sources arrive", () => {
    const reg = buildRegistry([guideX, studyA], [studyB, guideY, { ...studyA, title: "same study, other title" }]);
    expect(reg.label(studyA)).toBe("1");
    expect(reg.label(studyB)).toBe("2");
    expect(reg.label(guideX)).toBe("G1");
    expect(reg.label(guideY)).toBe("G2");
    expect(reg.size).toBe(4);
  });

  it("makes [G1] mean one document across two responses that both numbered from 1", () => {
    const reg = buildRegistry([guideX]); // documented practices registered first
    const explainCitations = [{ ...guideY, ref: "G1" }, { ...guideX, ref: "G2" }, { ...studyA, ref: "1" }];
    const text = relabelMarkers("Dig the pits [G1]. Mulch helps [1a][1b]. See also [G2].", explainCitations, reg);
    expect(text).toBe("Dig the pits [G2]. Mulch helps [1][1]. See also [G1].");
  });

  it("leaves unknown markers alone and never invents an identity", () => {
    const reg = buildRegistry();
    expect(relabelMarkers("Claim [9].", [], reg)).toBe("Claim [9].");
    expect(citationIdentity({ tier: "guidance" })).toBeNull();
  });
});

describe("uniqueSources / sourceKey", () => {
  it("keeps the first row per source, in order, and gives stable keys", async () => {
    const { uniqueSources, sourceKey } = await import("./citation-registry");
    const a = { tier: "guidance", url: "https://cgspace.cgiar.org/handle/10568/1", ref: "G1" };
    const b = { tier: "guidance", url: "https://cgspace.cgiar.org/handle/10568/1", ref: "G2" };
    const c = { tier: "evidence", era_code: "NN0001" };
    const out = uniqueSources([a, c, b]);
    expect(out).toEqual([a, c]);
    expect(new Set(out.map(sourceKey)).size).toBe(out.length);
    expect(sourceKey({}, 3)).toBe("row-3");
  });
});

