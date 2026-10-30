"use client";

import * as ToastPrimitive from "@radix-ui/react-toast";
import { X } from "lucide-react";
import { useSyncExternalStore, type ReactNode } from "react";
import { cn } from "@/lib/utils";

export interface ToastItem {
  id: number;
  title: string;
  description?: string;
  variant?: "default" | "success" | "danger";
}

// Tiny external store so any component can `toast()` without context plumbing.
let items: ToastItem[] = [];
let nextId = 1;
const listeners = new Set<() => void>();
function emit() {
  listeners.forEach((l) => l());
}
export function toast(input: Omit<ToastItem, "id">) {
  items = [...items, { id: nextId++, ...input }];
  emit();
}
function dismiss(id: number) {
  items = items.filter((t) => t.id !== id);
  emit();
}
function subscribe(l: () => void) {
  listeners.add(l);
  return () => listeners.delete(l);
}
const getSnapshot = () => items;
const getServerSnapshot = () => items;

export function useToasts() {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}

export function ToastProvider({ children, closeLabel }: { children: ReactNode; closeLabel: string }) {
  const toasts = useToasts();
  return (
    <ToastPrimitive.Provider swipeDirection="right" duration={5000}>
      {children}
      {toasts.map((t) => (
        <ToastPrimitive.Root
          key={t.id}
          onOpenChange={(open) => !open && dismiss(t.id)}
          className={cn(
            "grid grid-cols-[1fr_auto] items-start gap-2 rounded-card border bg-surface p-4 text-text shadow-2",
            t.variant === "success" && "border-success",
            t.variant === "danger" && "border-danger",
            (!t.variant || t.variant === "default") && "border-border"
          )}
        >
          <div>
            <ToastPrimitive.Title className="text-sm font-semibold">{t.title}</ToastPrimitive.Title>
            {t.description ? (
              <ToastPrimitive.Description className="mt-1 text-sm text-muted">
                {t.description}
              </ToastPrimitive.Description>
            ) : null}
          </div>
          <ToastPrimitive.Close
            aria-label={closeLabel}
            className="inline-flex h-8 w-8 items-center justify-center rounded-control text-muted hover:bg-surface-2"
          >
            <X className="h-4 w-4" aria-hidden />
          </ToastPrimitive.Close>
        </ToastPrimitive.Root>
      ))}
      <ToastPrimitive.Viewport className="fixed bottom-4 right-4 z-[60] flex w-[min(100%-2rem,22rem)] flex-col gap-2" />
    </ToastPrimitive.Provider>
  );
}
