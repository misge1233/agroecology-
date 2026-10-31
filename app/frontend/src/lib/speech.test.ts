import { describe, expect, it } from "vitest";
import { SPEECH_LANG, speakableText, speechSegments } from "./speech";

describe("speakableText (what the speaker reads)", () => {
  it("removes formatting, citations and links but keeps every number", () => {
    const md = [
      "### Top practice",
      "**Mulch + Water harvesting** cut soil loss by ~76% [1][G2] (https://doi.org/10.1/x).",
      "- Based on 3 field observations [3, 4]",
      "1. Read the [guide](https://example.org/guide)",
    ].join("\n");
    const out = speakableText(md);
    expect(out).toContain("76%");
    expect(out).toContain("3 field observations");
    expect(out).toContain("Read the guide");
    for (const gone of ["**", "###", "[1]", "[G2]", "[3, 4]", "https://", "]("]) expect(out).not.toContain(gone);
  });

  it("ends each line as a sentence and keeps the Ethiopic full stop", () => {
    expect(speakableText("ማልች ይጠቀሙ።\nውሃ ይሰብስቡ")).toBe("ማልች ይጠቀሙ። ውሃ ይሰብስቡ.");
    expect(speakableText("Steps:\nDig the pit")).toBe("Steps. Dig the pit.");
  });

  it("groups sentences into short segments for incremental server speech, losing nothing", () => {
    const text = "One. Two is here. ማልች ይጠቀሙ። " + "Long ".repeat(60).trim() + ". End?";
    const segs = speechSegments(text, 40);
    expect(segs[0]).toBe("One. Two is here. ማልች ይጠቀሙ።");
    expect(segs.join(" ")).toBe(text);
    expect(segs.at(-1)).toBe("End?");
  });

  it("maps every UI language to a BCP-47 tag for the browser engines", () => {
    expect(SPEECH_LANG).toEqual({ en: "en-US", am: "am-ET", om: "om-ET" });
  });
});
