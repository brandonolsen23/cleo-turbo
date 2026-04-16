import { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { Text, Badge, Button } from "@radix-ui/themes";
import {
  Lightning, MapPin, User, Phone, ArrowSquareOut, GitMerge,
  CheckSquare, Square, CheckSquareOffset,
} from "@phosphor-icons/react";
import { fetchApi, postApi } from "../../api/client";
import { formatPhone } from "../../lib/utils";
import LinkedInButton from "./LinkedInButton";
import type { AddressSuggestionsResponse, AddressSuggestion } from "../../types";

function formatYearRange(earliest: string | null, latest: string | null): string | null {
  if (!earliest && !latest) return null;
  const startYear = earliest ? earliest.substring(0, 4) : "?";
  const endYear = latest ? latest.substring(0, 4) : "?";
  if (startYear === endYear) return startYear;
  return `${startYear}–${endYear}`;
}

const TIER_COLORS: Record<number, "green" | "blue" | "amber" | "gray"> = {
  1: "green",
  2: "blue",
  3: "amber",
  4: "gray",
};

const TIER_LABELS: Record<number, string> = {
  1: "Near-certain",
  2: "Strong",
  3: "Moderate",
  4: "Weak",
};

function SuggestionRow({
  suggestion,
  groupId,
  isSelected,
  onToggle,
}: {
  suggestion: AddressSuggestion;
  groupId: string;
  isSelected: boolean;
  onToggle: (id: string) => void;
}) {
  const navigate = useNavigate();
  const tierColor = TIER_COLORS[suggestion.match_tier] || "gray";
  const CheckIcon = isSelected ? CheckSquare : Square;

  return (
    <div
      className={`flex items-center gap-3 py-2.5 border-b border-[var(--gray-4)] last:border-0 ${
        isSelected ? "bg-[var(--jade-2)] -mx-2 px-2 rounded" : ""
      }`}
    >
      {/* Checkbox */}
      <button
        className="flex-shrink-0 p-0.5 rounded hover:bg-[var(--gray-3)] transition-colors"
        onClick={(e) => {
          e.stopPropagation();
          onToggle(suggestion.group_id);
        }}
      >
        <CheckIcon
          size={18}
          weight={isSelected ? "fill" : "regular"}
          style={{ color: isSelected ? "var(--jade-9)" : "var(--gray-8)" }}
        />
      </button>

      {/* Content */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-0.5">
          <Text size="2" weight="medium" className="truncate">{suggestion.display_name}</Text>
          <Badge size="1" color={tierColor} variant="soft">{TIER_LABELS[suggestion.match_tier]}</Badge>
        </div>
        <div className="flex items-center gap-3 text-[12px]" style={{ color: "var(--gray-9)" }}>
          <span>{suggestion.property_count} props</span>
          <span>{suggestion.transaction_count} txns</span>
          {suggestion.shared_addresses.length > 0 && (
            <span className="flex items-center gap-0.5">
              <MapPin size={11} />
              {suggestion.shared_addresses[0].address}
              {suggestion.shared_addresses[0].city ? `, ${suggestion.shared_addresses[0].city}` : ""}
            </span>
          )}
          {suggestion.shared_contacts.length > 0 && (
            <span className="flex items-center gap-0.5">
              <User size={11} />
              {suggestion.shared_contacts[0].name}
              {(() => {
                const yr = formatYearRange(suggestion.shared_contacts[0].earliest_date, suggestion.shared_contacts[0].latest_date);
                return yr ? <span style={{ color: "var(--gray-8)" }}> · {yr}</span> : null;
              })()}
              <LinkedInButton
                contactId={suggestion.shared_contacts[0].contact_id}
                contactName={suggestion.shared_contacts[0].name}
                linkedinUrl={suggestion.shared_contacts[0].linkedin_url}
                size="sm"
              />
            </span>
          )}
          {suggestion.shared_phones.length > 0 && !suggestion.shared_contacts.length && (
            <span className="flex items-center gap-0.5">
              <Phone size={11} />
              {formatPhone(suggestion.shared_phones[0].phone)}
            </span>
          )}
        </div>
      </div>

      {/* Compare button */}
      <Button
        size="1"
        variant="soft"
        onClick={() => navigate(`/groups/compare?ids=${groupId},${suggestion.group_id}`)}
      >
        <ArrowSquareOut size={13} />
        Compare
      </Button>
    </div>
  );
}

export default function SuggestedLinksCard({
  groupId,
  onMerged,
}: {
  groupId: string;
  onMerged?: () => void;
}) {
  const [data, setData] = useState<AddressSuggestionsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [merging, setMerging] = useState(false);
  const [mergeResult, setMergeResult] = useState<string | null>(null);

  const loadSuggestions = useCallback(() => {
    setLoading(true);
    setError(null);
    fetchApi<AddressSuggestionsResponse>("/group-merges/address-suggestions", {
      group_id: groupId,
      min_tier: 3,
      limit: 50,
    })
      .then((d) => {
        setData(d);
        setSelected(new Set());
        setMergeResult(null);
      })
      .catch((e) => {
        console.error("SuggestedLinks error:", e);
        setError(e?.message || "Failed to load suggestions");
        setData(null);
      })
      .finally(() => setLoading(false));
  }, [groupId]);

  useEffect(loadSuggestions, [loadSuggestions]);

  const toggleSelect = useCallback((id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const toggleSelectAll = useCallback(() => {
    if (!data) return;
    const shown = expanded ? data.suggestions : data.suggestions.slice(0, 5);
    const allShownIds = shown.map((s) => s.group_id);
    const allSelected = allShownIds.every((id) => selected.has(id));

    if (allSelected) {
      // Deselect all shown
      setSelected((prev) => {
        const next = new Set(prev);
        allShownIds.forEach((id) => next.delete(id));
        return next;
      });
    } else {
      // Select all shown
      setSelected((prev) => {
        const next = new Set(prev);
        allShownIds.forEach((id) => next.add(id));
        return next;
      });
    }
  }, [data, expanded, selected]);

  const handleMerge = async () => {
    if (selected.size === 0) return;
    setMerging(true);
    setMergeResult(null);
    try {
      const sourceIds = Array.from(selected);
      await postApi("/group-merges/merge", {
        source_ids: sourceIds,
        target_id: groupId,
      });
      const count = sourceIds.length;
      setMergeResult(`${count} group${count !== 1 ? "s" : ""} merged successfully`);
      // Remove merged groups from the list
      setData((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          suggestions: prev.suggestions.filter((s) => !selected.has(s.group_id)),
          total: prev.total - selected.size,
        };
      });
      setSelected(new Set());
      // Notify parent to refresh
      onMerged?.();
    } catch (e: any) {
      setMergeResult(`Merge failed: ${e?.message || "unknown error"}`);
    } finally {
      setMerging(false);
    }
  };

  // Show nothing while loading or if genuinely no suggestions
  if (loading || (!data && !error) || (data && data.suggestions.length === 0)) return null;

  // If there was an error, show a small debug hint in dev
  if (error && !data) {
    if (import.meta.env.DEV) {
      return (
        <div className="rounded-[var(--card-radius)] border border-[var(--red-6)] bg-[var(--red-1)] p-3">
          <Text size="1" style={{ color: "var(--red-11)" }}>
            Suggested Links failed to load: {error}
          </Text>
        </div>
      );
    }
    return null;
  }

  if (!data) return null;

  const shown = expanded ? data.suggestions : data.suggestions.slice(0, 5);
  const allShownSelected = shown.length > 0 && shown.every((s) => selected.has(s.group_id));
  const someSelected = shown.some((s) => selected.has(s.group_id));
  const SelectAllIcon = allShownSelected ? CheckSquare : someSelected ? CheckSquareOffset : Square;

  return (
    <div className="rounded-[var(--card-radius)] border border-[var(--amber-6)] bg-[var(--amber-1)] p-5">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Lightning size={16} weight="fill" style={{ color: "var(--amber-9)" }} />
          <Text size="3" weight="medium">
            Suggested Links ({data.total})
          </Text>
          <Text size="1" style={{ color: "var(--gray-9)" }}>
            Groups connected by shared addresses, contacts, or phones
          </Text>
        </div>

        {/* Select All toggle */}
        <button
          className="flex items-center gap-1.5 px-2 py-1 rounded hover:bg-[var(--gray-3)] transition-colors text-[12px] font-medium"
          style={{ color: "var(--gray-10)" }}
          onClick={toggleSelectAll}
        >
          <SelectAllIcon
            size={16}
            weight={allShownSelected ? "fill" : "regular"}
            style={{ color: allShownSelected ? "var(--jade-9)" : "var(--gray-8)" }}
          />
          {allShownSelected ? "Deselect all" : "Select all"}
        </button>
      </div>

      {/* Suggestion rows */}
      <div className="flex flex-col">
        {shown.map((s) => (
          <SuggestionRow
            key={s.group_id}
            suggestion={s}
            groupId={groupId}
            isSelected={selected.has(s.group_id)}
            onToggle={toggleSelect}
          />
        ))}
      </div>

      {/* Expand/collapse */}
      {data.suggestions.length > 5 && (
        <button
          onClick={() => setExpanded(!expanded)}
          className="mt-2 text-[13px] font-medium hover:underline"
          style={{ color: "var(--accent-11)" }}
        >
          {expanded ? "Show less" : `Show all ${data.suggestions.length} suggestions`}
        </button>
      )}

      {/* Merge result toast */}
      {mergeResult && (
        <div
          className={`mt-3 px-3 py-2 rounded text-[13px] font-medium ${
            mergeResult.includes("failed")
              ? "bg-[var(--red-3)] border border-[var(--red-7)]"
              : "bg-[var(--jade-3)] border border-[var(--jade-7)]"
          }`}
          style={{
            color: mergeResult.includes("failed") ? "var(--red-11)" : "var(--jade-11)",
          }}
        >
          {mergeResult}
        </div>
      )}

      {/* Sticky merge action bar */}
      {selected.size > 0 && (
        <div className="mt-4 flex items-center justify-between rounded-lg border border-[var(--jade-7)] bg-[var(--jade-2)] px-4 py-3">
          <Text size="2" style={{ color: "var(--jade-11)" }}>
            <span className="font-semibold">{selected.size}</span>{" "}
            group{selected.size !== 1 ? "s" : ""} selected
          </Text>
          <div className="flex items-center gap-2">
            <Button
              size="2"
              variant="soft"
              color="gray"
              onClick={() => setSelected(new Set())}
            >
              Clear
            </Button>
            <Button
              size="2"
              color="jade"
              disabled={merging}
              onClick={handleMerge}
            >
              <GitMerge size={15} />
              {merging ? "Merging..." : `Merge ${selected.size} into this group`}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
