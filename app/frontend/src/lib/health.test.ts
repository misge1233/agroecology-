import { afterEach, describe, expect, it, vi } from "vitest";
import { _resetHealthForTests, checkHealth } from "./health";

afterEach(() => {
  vi.unstubAllGlobals();
  _resetHealthForTests();
});

describe("checkHealth", () => {
  it("reports ok with the version when /health answers", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ status: "ok", version: "1.0.0" }), { status: 200 })));
    const snap = await checkHealth();
    expect(snap.status).toBe("ok");
    expect(snap.version).toBe("1.0.0");
  });
  it("reports starting while the model is loading", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ status: "starting", version: "1.0.0" }), { status: 200 })));
    expect((await checkHealth()).status).toBe("starting");
  });
  it("reports down on a network failure and never throws", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("ECONNREFUSED")));
    expect((await checkHealth()).status).toBe("down");
  });
});
