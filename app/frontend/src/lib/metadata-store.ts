import { useSyncExternalStore } from "react";
import { fetchMetadata } from "./api";
import type { Metadata } from "./types";

/**
 * /metadata as an external store (F-1): components read it with
 * useSyncExternalStore instead of a setState-in-effect, and one fetch is
 * shared by every subscriber.
 */
export interface MetadataSnapshot {
  meta: Metadata | null;
  loading: boolean;
  error: string | null;
}

let snapshot: MetadataSnapshot = { meta: null, loading: true, error: null };
const SERVER: MetadataSnapshot = { meta: null, loading: true, error: null };
const listeners = new Set<() => void>();
let started = false;

function set(next: MetadataSnapshot) {
  snapshot = next;
  listeners.forEach((l) => l());
}

/** (Re)load /metadata. Safe to call any time; errors land in the snapshot. */
export function refreshMetadata(): Promise<void> {
  set({ ...snapshot, loading: true });
  return fetchMetadata()
    .then((meta) => set({ meta, loading: false, error: null }))
    .catch((e: Error) => set({ meta: snapshot.meta, loading: false, error: e.message || "metadata" }));
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  if (!started) {
    started = true;
    void refreshMetadata();
  }
  return () => listeners.delete(listener);
}
const getSnapshot = () => snapshot;
const getServerSnapshot = () => SERVER;

export function useMetadataStore(): MetadataSnapshot {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}

/** Test hook. */
export function _resetMetadataForTests(initial?: Partial<MetadataSnapshot>) {
  snapshot = { meta: null, loading: true, error: null, ...initial };
  listeners.clear();
  started = false;
}
