"use client";

import { createContext, useContext, useMemo, type ReactNode } from "react";
import {
  buildRegistry,
  citationIdentity,
  relabelMarkers,
  type Citable,
  type CitationRegistry,
} from "@/lib/citation-registry";

const RegistryContext = createContext<CitationRegistry | null>(null);

/**
 * One citation registry for a page or an answer (U9, B4). `lists` are the
 * sources in display priority: the cards' study effects first, then the
 * documented practices, then the explanation's passages — earlier sources
 * keep the lower numbers, so labels do not shift as evidence loads.
 */
export function CitationsProvider({
  lists,
  children,
}: {
  lists: Citable[][];
  children: ReactNode;
}) {
  const key = lists
    .map((l) => l.map((c) => citationIdentity(c) ?? "").join("¦"))
    .join("‖");
  // eslint-disable-next-line react-hooks/exhaustive-deps -- `key` captures the identities of `lists`
  const registry = useMemo(() => buildRegistry(...lists), [key]);
  return (
    <RegistryContext.Provider value={registry}>
      {children}
    </RegistryContext.Provider>
  );
}

/**
 * A registry scope for a component that may render without a page provider
 * (chat, tests, print): reuses the page registry when there is one, otherwise
 * numbers its own sources from `lists` so labels stay unique within the scope.
 */
export function CitationsScope({
  lists,
  children,
}: {
  lists: Citable[][];
  children: ReactNode;
}) {
  const shared = useContext(RegistryContext);
  if (shared) return <>{children}</>;
  return <CitationsProvider lists={lists}>{children}</CitationsProvider>;
}
/** Labels and marker rewriting from the nearest registry (a local one outside a provider). */
export function useCitations() {
  const shared = useContext(RegistryContext);
  const local = useMemo(() => buildRegistry(), []);
  const registry = shared ?? local;
  return {
    registry,
    /** The visible label of a source ("3", "G1"), registering it if new. */
    label: (c: Citable) => registry.label(c) ?? registry.register(c),
    /** Rewrite one response's markers to the registry's labels. */
    relabel: (text: string, citations: Citable[]) =>
      relabelMarkers(text, citations, registry),
  };
}
