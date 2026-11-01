import { describe, expect, it } from "vitest";
import fixture from "./practice-names.fixture.json";
import { practiceName } from "./glossary";
import type { Locale } from "./routing";

/** The backend (chat answers, app/services/practice_names.py) and the UI must name every practice alike. */
describe("practice names are shared with the backend", () => {
  for (const [practice, names] of Object.entries(fixture as Record<string, Record<Locale, string>>)) {
    it(practice, () => {
      for (const locale of ["en", "am", "om"] as const) expect(practiceName(practice, locale)).toBe(names[locale]);
    });
  }
});
