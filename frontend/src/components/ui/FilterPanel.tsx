/**
 * FilterPanel — collapsible filter sidebar for list pages.
 *
 * Provides range inputs, select dropdowns, and multi-select controls
 * in a consistent layout. Renders as a left-side panel that collapses
 * to a button bar.
 */
import { useState } from "react";
import { Text, Button, Badge } from "@radix-ui/themes";
import { FunnelSimple, X, CaretRight, CaretDown } from "@phosphor-icons/react";

// ── Sub-components for filter controls ──────────────────────────────

interface RangeFilterProps {
  label: string;
  minValue: string;
  maxValue: string;
  onMinChange: (v: string) => void;
  onMaxChange: (v: string) => void;
  placeholder?: [string, string];
  format?: "number" | "currency" | "decimal";
}

export function RangeFilter({
  label,
  minValue,
  maxValue,
  onMinChange,
  onMaxChange,
  placeholder = ["Min", "Max"],
}: RangeFilterProps) {
  return (
    <div className="flex flex-col gap-1.5">
      <Text size="1" weight="medium" style={{ color: "var(--gray-9)" }}>
        {label}
      </Text>
      <div className="flex gap-1.5">
        <input
          type="number"
          value={minValue}
          onChange={(e) => onMinChange(e.target.value)}
          placeholder={placeholder[0]}
          className="w-full h-7 px-2 text-[13px] rounded border border-[var(--gray-6)] bg-white outline-none focus:border-[var(--accent-7)] transition-colors"
          style={{ color: "var(--gray-12)" }}
        />
        <span
          className="flex items-center text-[12px]"
          style={{ color: "var(--gray-8)" }}
        >
          –
        </span>
        <input
          type="number"
          value={maxValue}
          onChange={(e) => onMaxChange(e.target.value)}
          placeholder={placeholder[1]}
          className="w-full h-7 px-2 text-[13px] rounded border border-[var(--gray-6)] bg-white outline-none focus:border-[var(--accent-7)] transition-colors"
          style={{ color: "var(--gray-12)" }}
        />
      </div>
    </div>
  );
}

interface SelectFilterProps {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
  placeholder?: string;
}

export function SelectFilter({
  label,
  value,
  onChange,
  options,
  placeholder = "All",
}: SelectFilterProps) {
  return (
    <div className="flex flex-col gap-1.5">
      <Text size="1" weight="medium" style={{ color: "var(--gray-9)" }}>
        {label}
      </Text>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="h-7 px-2 text-[13px] rounded border border-[var(--gray-6)] bg-white outline-none focus:border-[var(--accent-7)] transition-colors"
        style={{ color: value ? "var(--gray-12)" : "var(--gray-9)" }}
      >
        <option value="">{placeholder}</option>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </div>
  );
}

interface NumberFilterProps {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
}

export function NumberFilter({
  label,
  value,
  onChange,
  placeholder = "Min",
}: NumberFilterProps) {
  return (
    <div className="flex flex-col gap-1.5">
      <Text size="1" weight="medium" style={{ color: "var(--gray-9)" }}>
        {label}
      </Text>
      <input
        type="number"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full h-7 px-2 text-[13px] rounded border border-[var(--gray-6)] bg-white outline-none focus:border-[var(--accent-7)] transition-colors"
        style={{ color: "var(--gray-12)" }}
      />
    </div>
  );
}

// ── Combo filter: select + number (e.g., "Shoppers Drug Mart" + "min 2") ──

interface ComboFilterProps {
  label: string;
  selectValue: string;
  numberValue: string;
  /** Optional max value — when provided, shows min/max range inputs instead of a single number */
  maxNumberValue?: string;
  onSelectChange: (v: string) => void;
  onNumberChange: (v: string) => void;
  onMaxNumberChange?: (v: string) => void;
  options: { value: string; label: string }[];
  selectPlaceholder?: string;
  numberPlaceholder?: string;
  maxNumberPlaceholder?: string;
}

export function ComboFilter({
  label,
  selectValue,
  numberValue,
  maxNumberValue,
  onSelectChange,
  onNumberChange,
  onMaxNumberChange,
  options,
  selectPlaceholder = "Select...",
  numberPlaceholder = "Min",
  maxNumberPlaceholder = "Max",
}: ComboFilterProps) {
  const hasRange = onMaxNumberChange !== undefined;
  return (
    <div className="flex flex-col gap-1.5">
      <Text size="1" weight="medium" style={{ color: "var(--gray-9)" }}>
        {label}
      </Text>
      <select
        value={selectValue}
        onChange={(e) => onSelectChange(e.target.value)}
        className="h-7 px-2 text-[13px] rounded border border-[var(--gray-6)] bg-white outline-none focus:border-[var(--accent-7)] transition-colors"
        style={{ color: selectValue ? "var(--gray-12)" : "var(--gray-9)" }}
      >
        <option value="">{selectPlaceholder}</option>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
      {hasRange ? (
        <div className="flex gap-1.5">
          <input
            type="number"
            value={numberValue}
            onChange={(e) => onNumberChange(e.target.value)}
            placeholder={numberPlaceholder}
            min="1"
            disabled={!selectValue}
            className="w-full h-7 px-2 text-[13px] rounded border border-[var(--gray-6)] bg-white outline-none focus:border-[var(--accent-7)] transition-colors disabled:opacity-40"
            style={{ color: "var(--gray-12)" }}
          />
          <span className="flex items-center text-[12px]" style={{ color: "var(--gray-8)" }}>–</span>
          <input
            type="number"
            value={maxNumberValue ?? ""}
            onChange={(e) => onMaxNumberChange!(e.target.value)}
            placeholder={maxNumberPlaceholder}
            min="1"
            disabled={!selectValue}
            className="w-full h-7 px-2 text-[13px] rounded border border-[var(--gray-6)] bg-white outline-none focus:border-[var(--accent-7)] transition-colors disabled:opacity-40"
            style={{ color: "var(--gray-12)" }}
          />
        </div>
      ) : selectValue ? (
        <input
          type="number"
          value={numberValue}
          onChange={(e) => onNumberChange(e.target.value)}
          placeholder={numberPlaceholder}
          min="1"
          className="w-full h-7 px-2 text-[13px] rounded border border-[var(--gray-6)] bg-white outline-none focus:border-[var(--accent-7)] transition-colors"
          style={{ color: "var(--gray-12)" }}
        />
      ) : null}
    </div>
  );
}

// ── Main FilterPanel wrapper ────────────────────────────────────────

interface FilterPanelProps {
  activeCount: number;
  onClearAll: () => void;
  children: React.ReactNode;
}

export default function FilterPanel({
  activeCount,
  onClearAll,
  children,
}: FilterPanelProps) {
  const [open, setOpen] = useState(false);

  return (
    <div>
      {/* Toggle bar */}
      <div className="flex items-center gap-2 mb-3">
        <button
          onClick={() => setOpen(!open)}
          className="flex items-center gap-1.5 h-8 px-3 text-[13px] font-medium rounded-md border transition-colors"
          style={{
            borderColor: activeCount > 0 ? "var(--accent-7)" : "var(--gray-6)",
            background: activeCount > 0 ? "var(--accent-2)" : "transparent",
            color: activeCount > 0 ? "var(--accent-11)" : "var(--gray-11)",
          }}
        >
          <FunnelSimple size={15} weight="bold" />
          Filters
          {activeCount > 0 && (
            <Badge size="1" color="jade" variant="solid">
              {activeCount}
            </Badge>
          )}
          {open ? <CaretDown size={12} /> : <CaretRight size={12} />}
        </button>
        {activeCount > 0 && (
          <Button size="1" variant="ghost" color="red" onClick={onClearAll}>
            <X size={12} /> Clear all
          </Button>
        )}
      </div>

      {/* Filter controls */}
      {open && (
        <div
          className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-4 mb-4"
          style={{ background: "var(--gray-1)" }}
        >
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-x-4 gap-y-4">
            {children}
          </div>
        </div>
      )}
    </div>
  );
}
