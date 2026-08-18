"use client";

import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { fetchMetadata } from "@/lib/api";
import type { Metadata } from "@/lib/types";

const MetadataContext = createContext<{
  meta: Metadata | null;
  loading: boolean;
  error: string | null;
  refresh: () => void;
} | null>(null);

export function MetadataProvider({ children }: { children: ReactNode }) {
  const [meta, setMeta] = useState<Metadata | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchMetadata()
      .then((m) => {
        if (!cancelled) {
          setMeta(m);
          setError(null);
        }
      })
      .catch((e: Error) => {
        if (!cancelled) setError(e.message || "Failed to load metadata");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [tick]);

  return (
    <MetadataContext.Provider
      value={{
        meta,
        loading,
        error,
        refresh: () => setTick((t) => t + 1),
      }}
    >
      {children}
    </MetadataContext.Provider>
  );
}

export function useMetadata() {
  const ctx = useContext(MetadataContext);
  if (!ctx) throw new Error("useMetadata must be used within MetadataProvider");
  return ctx;
}
