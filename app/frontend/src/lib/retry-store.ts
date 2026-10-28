import { useSyncExternalStore } from "react";

/**
 * Tiny external store that says whether an API call is currently being
 * retried after a network failure (U2 item 5). The status banner shows a
 * "retrying…" strip while it is true, so a slow link is never silent.
 */
let pending = 0;
const listeners = new Set<() => void>();
function emit() {
  listeners.forEach((l) => l());
}
export function retryStarted() {
  pending += 1;
  emit();
}
export function retryFinished() {
  pending = Math.max(0, pending - 1);
  emit();
}
function subscribe(l: () => void) {
  listeners.add(l);
  return () => listeners.delete(l);
}
const getSnapshot = () => pending > 0;
const getServerSnapshot = () => false;
export function useRetrying(): boolean {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}
/** Test hook. */
export function _resetRetryForTests() {
  pending = 0;
  listeners.clear();
}
