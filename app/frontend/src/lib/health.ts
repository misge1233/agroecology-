import { useSyncExternalStore } from "react";
import { API_BASE } from "./api";

export type ApiStatus = "unknown" | "ok" | "starting" | "down";
export interface HealthSnapshot {
  status: ApiStatus;
  version: string | null;
  checkedAt: number | null;
}

const POLL_MS = 30_000;
let snapshot: HealthSnapshot = { status: "unknown", version: null, checkedAt: null };
const listeners = new Set<() => void>();
let timer: ReturnType<typeof setInterval> | null = null;
let inflight: Promise<void> | null = null;

function set(next: HealthSnapshot) {
  snapshot = next;
  listeners.forEach((l) => l());
}

/** One /health probe; never throws. Exported for tests and the retry button. */
export async function checkHealth(): Promise<HealthSnapshot> {
  if (inflight) {
    await inflight;
    return snapshot;
  }
  inflight = (async () => {
    try {
      const res = await fetch(`${API_BASE}/health`, { cache: "no-store" });
      if (!res.ok) throw new Error(String(res.status));
      const body = (await res.json()) as { status?: string; version?: string };
      set({
        status: body.status === "ok" ? "ok" : "starting",
        version: body.version ?? null,
        checkedAt: Date.now(),
      });
    } catch {
      set({ status: "down", version: snapshot.version, checkedAt: Date.now() });
    } finally {
      inflight = null;
    }
  })();
  await inflight;
  return snapshot;
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  if (listeners.size === 1) {
    void checkHealth();
    timer = setInterval(() => void checkHealth(), POLL_MS);
    window.addEventListener("online", onOnline);
  }
  return () => {
    listeners.delete(listener);
    if (listeners.size === 0 && timer) {
      clearInterval(timer);
      timer = null;
      window.removeEventListener("online", onOnline);
    }
  };
}
function onOnline() {
  void checkHealth();
}
const getSnapshot = () => snapshot;
const SERVER: HealthSnapshot = { status: "unknown", version: null, checkedAt: null };
const getServerSnapshot = () => SERVER;

/** Live API status from /health (polled every 30 s and on `online`). */
export function useApiHealth(): HealthSnapshot {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}

/** Test hook: reset the module store. */
export function _resetHealthForTests() {
  snapshot = { status: "unknown", version: null, checkedAt: null };
  listeners.clear();
  if (timer) clearInterval(timer);
  timer = null;
  inflight = null;
}
