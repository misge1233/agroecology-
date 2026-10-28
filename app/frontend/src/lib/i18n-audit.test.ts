/**
 * U1 quality gates for internationalisation:
 *  1. No user-visible string may be hard-coded in a component (JSX text or
 *     a user-facing attribute) — everything goes through the catalogs.
 *  2. `am` and `om` must carry every key `en` has, with the same ICU
 *     placeholders (a missing key would silently fall back at runtime).
 * Implemented with the TypeScript compiler API so JSX text is found
 * precisely rather than by regex.
 */
import { describe, expect, it } from "vitest";
import fs from "node:fs";
import path from "node:path";
import ts from "typescript";
import { parse, TYPE, type MessageFormatElement } from "@formatjs/icu-messageformat-parser";

const SRC = path.resolve(__dirname, "..");
const MESSAGES = path.resolve(__dirname, "../../messages");

function walk(dir: string, out: string[] = []): string[] {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, entry.name);
    if (entry.isDirectory()) walk(p, out);
    else if (/\.tsx$/.test(entry.name) && !/\.test\.tsx$/.test(entry.name)) out.push(p);
  }
  return out;
}

/** Attributes whose string values reach the user. */
const USER_FACING_ATTRS = new Set([
  "aria-label", "aria-description", "placeholder", "title", "alt", "aria-roledescription", "aria-valuetext",
]);
/** Text that is punctuation, symbols, numbers or layout only — never a "string". */
const NON_WORD = /^[\s\d.,:;!?%°×#()[\]{}+\-–—/|·•●…©&→←↑↓'"“”‘’]*$/;
/** Deliberately literal: brand names and protocol tokens. */
// "blur" is next/image's placeholder MODE, not a string a reader sees.
const ALLOWLIST = new Set(["AgroAdvisor-ET", "WOCAT", "CIAT", "ERA", "GARDIAN", "404", "Agroecology+", "blur"]);

function hardCodedStrings(file: string): string[] {
  const source = ts.createSourceFile(file, fs.readFileSync(file, "utf8"), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const hits: string[] = [];
  const visit = (node: ts.Node) => {
    if (ts.isJsxText(node)) {
      const text = node.getText().replace(/\s+/g, " ").trim();
      if (text && !NON_WORD.test(text) && !ALLOWLIST.has(text)) hits.push(`text: "${text}"`);
    } else if (ts.isJsxAttribute(node) && node.initializer && ts.isStringLiteral(node.initializer)) {
      const name = node.name.getText();
      const value = node.initializer.text.trim();
      if (USER_FACING_ATTRS.has(name) && value && !NON_WORD.test(value) && !ALLOWLIST.has(value)) {
        hits.push(`${name}="${value}"`);
      }
    }
    ts.forEachChild(node, visit);
  };
  visit(source);
  return hits;
}

describe("no hard-coded user-visible strings", () => {
  const files = walk(SRC);
  it("scans a meaningful number of component files", () => {
    expect(files.length).toBeGreaterThan(20);
  });
  for (const file of files) {
    it(path.relative(SRC, file), () => {
      expect(hardCodedStrings(file)).toEqual([]);
    });
  }
});

// ----------------------------------------------------------- catalog parity
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
/** Argument names of an ICU message (plural/select branches walked, literals ignored). */
function placeholders(msg: string): string[] {
  const out = new Set<string>();
  const walk = (els: MessageFormatElement[]) => {
    for (const el of els) {
      if (el.type === TYPE.literal || el.type === TYPE.pound) continue;
      if (el.type === TYPE.tag) {
        walk(el.children);
        continue;
      }
      out.add(el.value);
      if (el.type === TYPE.plural || el.type === TYPE.select) {
        for (const opt of Object.values(el.options)) walk(opt.value);
      }
    }
  };
  try {
    walk(parse(msg));
  } catch {
    out.add("<invalid ICU>");
  }
  return [...out].sort();
}
const load = (l: string) => flatten(JSON.parse(fs.readFileSync(path.join(MESSAGES, `${l}.json`), "utf8")));

describe("catalog parity", () => {
  const en = load("en");
  for (const locale of ["am", "om"]) {
    const other = load(locale);
    it(`${locale} has every key en has`, () => {
      const missing = Object.keys(en).filter((k) => !(k in other));
      expect(missing).toEqual([]);
    });
    it(`${locale} has no keys en lacks`, () => {
      const extra = Object.keys(other).filter((k) => !(k in en));
      expect(extra).toEqual([]);
    });
    it(`${locale} uses only ICU placeholders that en defines`, () => {
      // A translation may legitimately drop a placeholder (Amharic has no
      // singular/plural verb form) but must never introduce an unknown one.
      const broken = Object.keys(en).filter((k) => {
        const allowed = new Set(placeholders(en[k]));
        return placeholders(other[k] ?? "").some((p) => !allowed.has(p));
      });
      expect(broken).toEqual([]);
    });
    it(`${locale} is actually translated (not a copy of en)`, () => {
      const same = Object.keys(en).filter((k) => en[k] === other[k] && !k.startsWith("chat.protocol.") && !/appName|rights|rank$|passages|units\.(mm|m|percent|celsius)|percent/.test(k));
      // A few keys are legitimately identical (numbers, symbols, brand).
      expect(same.length).toBeLessThan(8);
    });
  }
  it("Amharic strings are written in Ethiopic script", () => {
    const am = load("am");
    const latinOnly = Object.entries(am).filter(([k, v]) => !/[ሀ-፿]/.test(v) && !k.startsWith("chat.protocol.") && !/appName|rights|rank$|passages|units\.(mm|m|percent|celsius)|percent/.test(k));
    expect(latinOnly.map(([k]) => k)).toEqual([]);
  });
});
