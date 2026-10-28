import { useSyncExternalStore } from "react";

const noop = () => () => {};

/**
 * Read a browser-only value (window.location, the clock) without a hydration
 * mismatch and without setState-in-effect (F-1): the server snapshot is the
 * fallback, the client snapshot is read after hydration.
 */
export function useClientValue<T extends string | number | boolean>(get: () => T, fallback: T): T {
  return useSyncExternalStore(noop, get, () => fallback);
}
