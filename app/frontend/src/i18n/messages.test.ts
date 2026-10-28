import { describe, expect, it } from "vitest";
import en from "../../messages/en.json";
import { ADVISOR_NAMESPACES, CHAT_NAMESPACES, HOME_NAMESPACES, SHELL_NAMESPACES, pickMessages } from "./messages";

describe("pickMessages (per-route message split)", () => {
  it("keeps whole and nested namespaces and drops the rest", () => {
    const picked = pickMessages(en, ["common", "chat.protocol"]) as typeof en;
    expect(Object.keys(picked).sort()).toEqual(["chat", "common"]);
    expect(Object.keys(picked.chat)).toEqual(["protocol"]);
    expect(picked.chat.protocol.challenge).toBe(en.chat.protocol.challenge);
    expect((picked as Record<string, unknown>).advisor).toBeUndefined();
  });
  it("every route set is a superset of the shell set and smaller than the catalog", () => {
    const size = (m: unknown) => JSON.stringify(m).length;
    for (const set of [HOME_NAMESPACES, ADVISOR_NAMESPACES, CHAT_NAMESPACES]) {
      for (const ns of SHELL_NAMESPACES) expect(set).toContain(ns);
      expect(size(pickMessages(en, set))).toBeLessThan(size(en));
    }
    expect(size(pickMessages(en, HOME_NAMESPACES))).toBeLessThan(size(en) * 0.5);
  });
});
