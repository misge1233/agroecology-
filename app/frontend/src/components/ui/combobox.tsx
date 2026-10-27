"use client";

import * as Popover from "@radix-ui/react-popover";
import { Check, ChevronDown, X } from "lucide-react";
import { useId, useMemo, useState, type KeyboardEvent } from "react";
import { cn } from "@/lib/utils";

export interface ComboboxOption {
  value: string;
  label: string;
}

/**
 * Accessible searchable single-select (WAI-ARIA combobox with listbox popup).
 * Keyboard: type to filter, ↑/↓ to move, Enter to choose, Esc to close,
 * Backspace on an empty field clears. Built on Radix Popover + native input.
 */
export function Combobox({
  options,
  value,
  onChange,
  placeholder,
  emptyLabel,
  clearLabel,
  label,
  id,
  className,
}: {
  options: ComboboxOption[];
  value: string | null;
  onChange: (value: string | null) => void;
  placeholder: string;
  emptyLabel: string;
  clearLabel: string;
  label: string;
  id?: string;
  className?: string;
}) {
  const generatedId = useId();
  const inputId = id ?? generatedId;
  const listId = `${inputId}-listbox`;
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);

  const selected = options.find((o) => o.value === value) ?? null;
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    const list = q ? options.filter((o) => o.label.toLowerCase().includes(q)) : options;
    return list.slice(0, 50);
  }, [options, query]);

  function choose(option: ComboboxOption | null) {
    onChange(option?.value ?? null);
    setQuery("");
    setOpen(false);
  }

  function onKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setOpen(true);
      setActive((i) => Math.min(i + 1, filtered.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter") {
      if (open && filtered[active]) {
        e.preventDefault();
        choose(filtered[active]);
      }
    } else if (e.key === "Escape") {
      setOpen(false);
    } else if (e.key === "Backspace" && query === "" && selected) {
      choose(null);
    }
  }

  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <div className={cn("relative", className)}>
        <label htmlFor={inputId} className="mb-1.5 block text-sm font-medium text-text">
          {label}
        </label>
        <Popover.Anchor asChild>
          <div className="flex h-10 items-center rounded-control border border-border bg-surface pr-1 focus-within:outline focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-ring">
            <input
              id={inputId}
              role="combobox"
              aria-expanded={open}
              aria-controls={listId}
              aria-autocomplete="list"
              aria-activedescendant={open && filtered[active] ? `${listId}-${active}` : undefined}
              value={open ? query : (selected?.label ?? "")}
              placeholder={placeholder}
              onChange={(e) => {
                setQuery(e.target.value);
                setActive(0);
                setOpen(true);
              }}
              onFocus={() => setOpen(true)}
              onKeyDown={onKeyDown}
              className="h-full flex-1 bg-transparent px-3 text-sm text-text outline-none placeholder:text-muted"
              autoComplete="off"
            />
            {selected ? (
              <button
                type="button"
                onClick={() => choose(null)}
                aria-label={clearLabel}
                className="inline-flex h-8 w-8 items-center justify-center rounded-[6px] text-muted hover:bg-surface-2 hover:text-text"
              >
                <X className="h-4 w-4" aria-hidden />
              </button>
            ) : (
              <ChevronDown className="mr-2 h-4 w-4 text-muted" aria-hidden />
            )}
          </div>
        </Popover.Anchor>
        <Popover.Portal>
          <Popover.Content
            align="start"
            sideOffset={4}
            onOpenAutoFocus={(e) => e.preventDefault()}
            className="z-50 w-[var(--radix-popover-trigger-width)] rounded-control border border-border bg-surface p-1 shadow-2"
          >
            <ul id={listId} role="listbox" className="max-h-64 overflow-y-auto">
              {filtered.length === 0 ? (
                <li className="px-3 py-2 text-sm text-muted">{emptyLabel}</li>
              ) : (
                filtered.map((o, i) => (
                  <li
                    key={o.value}
                    id={`${listId}-${i}`}
                    role="option"
                    aria-selected={o.value === value}
                    onMouseDown={(e) => e.preventDefault()}
                    onClick={() => choose(o)}
                    onMouseEnter={() => setActive(i)}
                    className={cn(
                      "flex cursor-pointer items-center gap-2 rounded-[6px] px-3 py-2 text-sm",
                      i === active ? "bg-surface-2" : "",
                      o.value === value ? "font-semibold" : ""
                    )}
                  >
                    {o.value === value ? <Check className="h-4 w-4 text-primary" aria-hidden /> : <span className="w-4" />}
                    {o.label}
                  </li>
                ))
              )}
            </ul>
          </Popover.Content>
        </Popover.Portal>
      </div>
    </Popover.Root>
  );
}
