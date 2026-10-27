import { describe, expect, it } from "vitest";
import { createTranslator } from "next-intl";
import en from "../../messages/en.json";
import am from "../../messages/am.json";
import {
  evidenceBaseEntries,
  evidenceBaseSentence,
  studiesInCorpus,
  studiesTooltip,
  studyLine,
  type StudyLabels,
} from "./evidence-base";
import type { EvidenceBaseEntry } from "./types";

// The English catalog drives the sentence; the test proves it still reads
// word-for-word like the backend's (``explain_service.evidence_base_sentence``).
const tEn = createTranslator({ locale: "en", messages: en, namespace: "evidence.evidenceBase" });
const tAm = createTranslator({ locale: "am", messages: am, namespace: "evidence.evidenceBase" });
const labels: StudyLabels = {
  untitled: en.evidence.untitledStudy,
  fullText: en.evidence.evidenceBase.fullText,
  abstractOnly: en.evidence.evidenceBase.abstractOnly,
  notInCorpus: en.evidence.evidenceBase.notInCorpus,
};

const mulching: EvidenceBaseEntry = {
  n_studies: 3,
  n_obs: 17,
  aez_belts: ["Dry Dega", "Moist Weyna Dega"],
  crop_groups: ["Cereal"],
  corpus_status: { full_text: 1, abstract: 1, none: 1 },
  studies: [
    {
      era_code: "NN0123",
      title: "Mulching effects on erosion",
      year: 2019,
      doi: "10.1000/xyz1",
      corpus_status: "full_text",
    },
    {
      era_code: "NN0999",
      title: "Residue cover trial",
      year: 2016,
      doi: null,
      corpus_status: "abstract",
    },
    {
      era_code: null,
      title: null,
      year: null,
      doi: null,
      corpus_status: "none",
    },
  ],
};

const bunds: EvidenceBaseEntry = {
  n_studies: 1,
  n_obs: 1,
  aez_belts: [],
  crop_groups: [],
  corpus_status: { full_text: 1, abstract: 0, none: 0 },
  studies: [],
};

describe("studiesInCorpus", () => {
  it("counts full-text and abstract studies, not the missing ones", () => {
    expect(studiesInCorpus(mulching)).toBe(2);
  });

  it("tolerates a missing corpus_status map", () => {
    expect(studiesInCorpus({ ...mulching, corpus_status: {} })).toBe(0);
  });
});

describe("evidenceBaseEntries", () => {
  it("orders the best-evidenced practice first", () => {
    const entries = evidenceBaseEntries({ "Soil bunds": bunds, Mulching: mulching });
    expect(entries.map(([practice]) => practice)).toEqual(["Mulching", "Soil bunds"]);
  });

  it("is empty for an absent or empty evidence base", () => {
    expect(evidenceBaseEntries(undefined)).toEqual([]);
    expect(evidenceBaseEntries({})).toEqual([]);
  });
});

describe("evidenceBaseSentence", () => {
  it("states counts, belts and corpus coverage", () => {
    expect(evidenceBaseSentence("Mulching", mulching, tEn)).toBe(
      "Mulching: backed by 3 studies / 17 field observations in Dry Dega, " +
        "Moist Weyna Dega; 2 of the studies are in the retrievable corpus."
    );
  });

  it("uses singular forms and omits belts when there are none", () => {
    expect(evidenceBaseSentence("Soil bunds", bunds, tEn)).toBe(
      "Soil bunds: backed by 1 study / 1 field observation; 1 of the studies " +
        "is in the retrievable corpus."
    );
  });

  it("localises the frame and the names but keeps the counts (am)", () => {
    const sentence = evidenceBaseSentence("Mulching", mulching, tAm, { practice: () => "ሙልች" });
    expect(sentence).toContain("ሙልች");
    expect(sentence).toMatch(/[ሀ-፿]/);
    expect(sentence).toContain("3");
    expect(sentence).toContain("17");
    expect(sentence).not.toContain("%");
  });

  it("never shows an effect magnitude", () => {
    const sentence = evidenceBaseSentence("Mulching", mulching, tEn);
    expect(sentence).not.toContain("%");
    expect(sentence).not.toMatch(/log|ratio|mean|median/i);
  });
});

describe("studyLine / studiesTooltip", () => {
  it("renders provenance and retrievability per study", () => {
    expect(studyLine(mulching.studies[0], labels)).toBe(
      "NN0123 · Mulching effects on erosion (2019) — full text"
    );
    expect(studyLine(mulching.studies[1], labels)).toBe(
      "NN0999 · Residue cover trial (2016) — abstract only"
    );
    expect(studyLine(mulching.studies[2], labels)).toBe("Untitled study — not in the corpus");
  });

  it("joins the studies into one tooltip, or none when the list is empty", () => {
    expect(studiesTooltip(mulching, labels)?.split("\n")).toHaveLength(3);
    expect(studiesTooltip(bunds, labels)).toBeUndefined();
  });
});
