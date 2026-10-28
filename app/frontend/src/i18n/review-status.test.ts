/**
 * Review-status guard (U2 item 4). `messages/review-status.json` fingerprints
 * every am/om string a native speaker signed off through
 * `scripts/translation_status.py --import`. A reviewed string that is edited
 * any other way fails here, so a sign-off cannot be silently overwritten.
 * (Backend catalog keys are guarded by the pytest twin.)
 */
import { describe, expect, it } from "vitest";
import { createHash } from "node:crypto";
import fs from "node:fs";
import path from "node:path";

const MESSAGES = path.resolve(__dirname, "../../messages");
const GLOSSARY = path.resolve(__dirname, "./glossary.ts");

type Tree = { [k: string]: string | Tree };
function flatten(tree: Tree, prefix = ""): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [k, v] of Object.entries(tree)) {
    const key = prefix ? `${prefix}.${k}` : k;
    if (typeof v === "string") out[key] = v;
    else Object.assign(out, flatten(v, key));
  }
  return out;
}
const sha1 = (s: string) => createHash("sha1").update(s, "utf8").digest("hex").slice(0, 16);

function glossaryValue(tableKey: string, lang: string): string | undefined {
  const [table, key] = tableKey.split("::");
  const src = fs.readFileSync(GLOSSARY, "utf8");
  const m = src.match(new RegExp(`export const ${table}[^=]*=\\s*\\{([\\s\\S]*?)\\n\\};`));
  if (!m) return undefined;
  const entry = new RegExp(`^ {2}"?${key.replace(/[.*+?^${}()|[\\]\\\\]/g, "\\$&")}"?: \\{([\\s\\S]*?)\\n? *\\},?$`, "m").exec(m[1]);
  if (!entry) return undefined;
  const val = new RegExp(`\\b${lang}: "((?:[^"\\\\]|\\\\.)*)"`).exec(entry[1]);
  return val ? (JSON.parse(`"${val[1]}"`) as string) : undefined;
}

describe("reviewed translations are not silently changed", () => {
  const statusPath = path.join(MESSAGES, "review-status.json");
  const status: Record<string, Record<string, { status: string; sha1: string }>> = fs.existsSync(statusPath)
    ? JSON.parse(fs.readFileSync(statusPath, "utf8"))
    : {};
  const catalogs: Record<string, Record<string, string>> = {};
  for (const lang of ["am", "om"]) {
    catalogs[lang] = flatten(JSON.parse(fs.readFileSync(path.join(MESSAGES, `${lang}.json`), "utf8")));
  }

  it("status file parses and only carries reviewed entries", () => {
    for (const [key, langs] of Object.entries(status)) {
      for (const [lang, entry] of Object.entries(langs)) {
        expect(["am", "om"], key).toContain(lang);
        expect(entry.status).toBe("reviewed");
        expect(entry.sha1).toMatch(/^[0-9a-f]{16}$/);
      }
    }
  });

  for (const [fullKey, langs] of Object.entries(status)) {
    const [source, key] = [fullKey.slice(0, fullKey.indexOf("::")), fullKey.slice(fullKey.indexOf("::") + 2)];
    if (source === "backend") continue;
    for (const [lang, entry] of Object.entries(langs)) {
      it(`${fullKey} (${lang}) still matches its reviewed fingerprint`, () => {
        const current = source === "messages" ? catalogs[lang][key] : glossaryValue(key, lang);
        expect(current, `${fullKey} is missing from the ${lang} catalog`).toBeDefined();
        expect(
          sha1(current as string),
          `"${fullKey}" (${lang}) was reviewed but its text changed — re-import review.csv (or set it back to machine-draft)`
        ).toBe(entry.sha1);
      });
    }
  }
});
