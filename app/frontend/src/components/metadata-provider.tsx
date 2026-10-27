"use client";

import { createContext, useContext, type ReactNode } from "react";
import { refreshMetadata, useMetadataStore } from "@/lib/metadata-store";
import type { Metadata } from "@/lib/types";

const MetadataContext = createContext<{
  meta: Metadata | null;
  loading: boolean;
  error: string | null;
  refresh: () => void;
} | null>(null);

/** Same context API as before U1; the data now comes from an external store. */
export function MetadataProvider({ children }: { children: ReactNode }) {
  const { meta, loading, error } = useMetadataStore();
  return (
    <MetadataContext.Provider value={{ meta, loading, error, refresh: () => void refreshMetadata() }}>
      {children}
    </MetadataContext.Provider>
  );
}

export function useMetadata() {
  const ctx = useContext(MetadataContext);
  if (!ctx) throw new Error("useMetadata must be used within MetadataProvider");
  return ctx;
}
