import { useState, useRef, useEffect, useCallback } from "react";
import { Badge, Text } from "@radix-ui/themes";
import { CaretDown, MagnifyingGlass, X } from "@phosphor-icons/react";
import type { RadixColor } from "../../lib/theme";

interface Option {
  value: string;
  label: string;
  /** Optional group label (shown as a section header) */
  group?: string;
  /** Optional Radix color for the badge/dot */
  color?: RadixColor;
}

interface MultiSelectDropdownProps {
  /** Button label when nothing selected */
  placeholder: string;
  /** All available options */
  options: Option[];
  /** Currently selected values */
  selected: Set<string>;
  /** Called when selection changes */
  onChange: (selected: Set<string>) => void;
  /** Show search input (useful for long lists) */
  searchable?: boolean;
  /** Max height of the options list */
  maxHeight?: number;
  /** Show group headers */
  grouped?: boolean;
}

export default function MultiSelectDropdown({
  placeholder,
  options,
  selected,
  onChange,
  searchable = false,
  maxHeight = 320,
  grouped = false,
}: MultiSelectDropdownProps) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const containerRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);

  // Close on click outside
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
        setSearch("");
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  // Focus search on open
  useEffect(() => {
    if (open && searchable && searchRef.current) {
      searchRef.current.focus();
    }
  }, [open, searchable]);

  const toggle = useCallback(
    (value: string) => {
      const next = new Set(selected);
      if (next.has(value)) next.delete(value);
      else next.add(value);
      onChange(next);
    },
    [selected, onChange],
  );

  const clearAll = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      onChange(new Set());
    },
    [onChange],
  );

  // Filter options by search
  const filtered = search
    ? options.filter((o) => o.label.toLowerCase().includes(search.toLowerCase()))
    : options;

  // Group options if needed
  const groups: { label: string; items: Option[] }[] = [];
  if (grouped) {
    const map = new Map<string, Option[]>();
    for (const o of filtered) {
      const g = o.group || "";
      if (!map.has(g)) map.set(g, []);
      map.get(g)!.push(o);
    }
    for (const [label, items] of map) {
      groups.push({ label, items });
    }
  }

  return (
    <div ref={containerRef} className="relative">
      {/* Trigger button */}
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 h-7 px-2 text-[13px] rounded border transition-colors"
        style={{
          borderColor: selected.size > 0 ? "var(--accent-7)" : "var(--gray-6)",
          background: selected.size > 0 ? "var(--accent-2)" : "white",
          color: selected.size > 0 ? "var(--accent-11)" : "var(--gray-11)",
          fontWeight: selected.size > 0 ? 500 : 400,
        }}
      >
        {placeholder}
        {selected.size > 0 && (
          <Badge size="1" color="jade" variant="solid" className="ml-0.5">
            {selected.size}
          </Badge>
        )}
        <CaretDown size={12} style={{ opacity: 0.5, marginLeft: 2 }} />
        {selected.size > 0 && (
          <span
            onClick={clearAll}
            className="ml-0.5 flex items-center justify-center rounded-full hover:bg-[var(--gray-4)] transition-colors"
            style={{ width: 16, height: 16 }}
          >
            <X size={10} />
          </span>
        )}
      </button>

      {/* Dropdown panel */}
      {open && (
        <div
          className="absolute top-full left-0 mt-1 rounded-lg border shadow-lg z-50"
          style={{
            background: "white",
            borderColor: "var(--gray-6)",
            minWidth: 220,
            maxWidth: 300,
          }}
        >
          {/* Search input */}
          {searchable && (
            <div className="flex items-center gap-2 px-3 py-2 border-b" style={{ borderColor: "var(--gray-4)" }}>
              <MagnifyingGlass size={14} style={{ color: "var(--gray-9)", flexShrink: 0 }} />
              <input
                ref={searchRef}
                type="text"
                placeholder="Search..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="flex-1 text-[13px] outline-none bg-transparent"
                style={{ color: "var(--gray-12)" }}
              />
            </div>
          )}

          {/* Options list */}
          <div className="overflow-y-auto py-1" style={{ maxHeight }}>
            {filtered.length === 0 && (
              <div className="px-3 py-4 text-center">
                <Text size="2" style={{ color: "var(--gray-9)" }}>No matches</Text>
              </div>
            )}

            {grouped
              ? groups.map((g) => (
                  <div key={g.label}>
                    {g.label && (
                      <div
                        className="px-3 pt-2 pb-1 text-[11px] font-medium uppercase tracking-wider"
                        style={{ color: "var(--gray-9)" }}
                      >
                        {g.label}
                      </div>
                    )}
                    {g.items.map((o) => (
                      <OptionRow key={o.value} option={o} checked={selected.has(o.value)} onToggle={toggle} />
                    ))}
                  </div>
                ))
              : filtered.map((o) => (
                  <OptionRow key={o.value} option={o} checked={selected.has(o.value)} onToggle={toggle} />
                ))}
          </div>

          {/* Footer with count + clear */}
          {selected.size > 0 && (
            <div
              className="flex items-center justify-between px-3 py-2 border-t"
              style={{ borderColor: "var(--gray-4)" }}
            >
              <Text size="1" style={{ color: "var(--gray-9)" }}>
                {selected.size} selected
              </Text>
              <button
                onClick={(e) => { clearAll(e); }}
                className="text-[12px] font-medium hover:underline"
                style={{ color: "var(--accent-11)" }}
              >
                Clear all
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ============================================================
// Option row sub-component
// ============================================================

function OptionRow({
  option,
  checked,
  onToggle,
}: {
  option: Option;
  checked: boolean;
  onToggle: (value: string) => void;
}) {
  return (
    <button
      className="flex items-center gap-2 w-full px-3 py-1.5 text-left text-[13px] transition-colors hover:bg-[var(--gray-2)]"
      style={{
        color: checked ? "var(--gray-12)" : "var(--gray-11)",
        fontWeight: checked ? 500 : 400,
      }}
      onClick={() => onToggle(option.value)}
    >
      {/* Checkbox indicator */}
      <span
        className="flex items-center justify-center rounded border transition-colors"
        style={{
          width: 16,
          height: 16,
          flexShrink: 0,
          borderColor: checked ? "var(--accent-9)" : "var(--gray-7)",
          background: checked ? "var(--accent-9)" : "transparent",
        }}
      >
        {checked && (
          <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
            <path d="M2 5L4 7L8 3" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        )}
      </span>

      {/* Color dot */}
      {option.color && (
        <span
          className="rounded-full"
          style={{
            width: 8,
            height: 8,
            flexShrink: 0,
            background: `var(--${option.color}-9)`,
          }}
        />
      )}

      <span className="truncate">{option.label}</span>
    </button>
  );
}
