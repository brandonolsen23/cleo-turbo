import { useState, useEffect, useCallback } from "react";
import { Text, Button, Badge, Heading } from "@radix-ui/themes";
import { MagnifyingGlass, X, ArrowRight, Warning } from "@phosphor-icons/react";
import { fetchApi, postApi } from "../../api/client";
import { formatCompact } from "../../lib/utils";
import type { MergeCandidate, MergeCandidatesResponse } from "../../types";

// ── Types ──────────────────────────────────────────────────────

interface MergeGroupsModalProps {
  /** The group the user is currently viewing */
  targetGroup: {
    id: string;
    display_name: string;
    property_count: number;
    transaction_count: number;
    contact_count: number;
  };
  onClose: () => void;
  /** Called after a successful merge. Receives the surviving group's ID so the caller can navigate. */
  onMerged: (survivorId: string) => void;
}

type MergeDirection = "absorb" | "into";

// ── Component ──────────────────────────────────────────────────

export default function MergeGroupsModal({
  targetGroup,
  onClose,
  onMerged,
}: MergeGroupsModalProps) {
  const [candidates, setCandidates] = useState<MergeCandidate[]>([]);
  const [searchResults, setSearchResults] = useState<MergeCandidate[] | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [selected, setSelected] = useState<MergeCandidate[]>([]);
  const [loading, setLoading] = useState(false);
  const [merging, setMerging] = useState(false);
  const [step, setStep] = useState<"select" | "confirm">("select");
  // "absorb" = current group is the target (absorbs others)
  // "into"   = current group merges INTO the selected group
  const [direction, setDirection] = useState<MergeDirection>("absorb");

  // Load suggested candidates on mount
  useEffect(() => {
    setLoading(true);
    fetchApi<MergeCandidatesResponse>(`/group-merges/candidates/${targetGroup.id}`)
      .then((r) => setCandidates(r.candidates))
      .finally(() => setLoading(false));
  }, [targetGroup.id]);

  // When direction changes, reset selection (since "into" only allows one target)
  const handleDirectionChange = (d: MergeDirection) => {
    setDirection(d);
    setSelected([]);
    setSearchResults(null);
    setSearchQuery("");
  };

  // Search groups
  const handleSearch = useCallback(async () => {
    if (!searchQuery.trim()) {
      setSearchResults(null);
      return;
    }
    const res = await fetchApi<{ results: MergeCandidate[] }>("/groups/search", {
      q: searchQuery,
      limit: "25",
    });
    const selectedIds = new Set([targetGroup.id, ...selected.map((s) => s.id)]);
    setSearchResults(
      res.results
        .filter((r) => !selectedIds.has(r.id))
        .map((r) => ({
          ...r,
          normalized_name: "",
          total_assessed_value: null,
          geographic_radius_km: null,
        })),
    );
  }, [searchQuery, targetGroup.id, selected]);

  const toggleSelect = (candidate: MergeCandidate) => {
    if (direction === "into") {
      // "into" mode: only one target allowed, toggle it
      setSelected((prev) =>
        prev.find((s) => s.id === candidate.id) ? [] : [candidate],
      );
    } else {
      setSelected((prev) =>
        prev.find((s) => s.id === candidate.id)
          ? prev.filter((s) => s.id !== candidate.id)
          : [...prev, candidate],
      );
    }
  };

  const isSelected = (id: string) => selected.some((s) => s.id === id);

  // Compute source/target based on direction
  const actualTarget = direction === "absorb" ? targetGroup : selected[0];
  const actualSources =
    direction === "absorb"
      ? selected
      : [{ id: targetGroup.id, display_name: targetGroup.display_name, property_count: targetGroup.property_count, transaction_count: targetGroup.transaction_count, contact_count: targetGroup.contact_count }];

  const combinedProps =
    (actualTarget?.property_count ?? 0) + actualSources.reduce((s, c) => s + c.property_count, 0);
  const combinedTxns =
    (actualTarget?.transaction_count ?? 0) + actualSources.reduce((s, c) => s + c.transaction_count, 0);
  const combinedContacts =
    (actualTarget?.contact_count ?? 0) + actualSources.reduce((s, c) => s + (c.contact_count ?? 0), 0);

  const handleMerge = async () => {
    if (!actualTarget) return;
    setMerging(true);
    try {
      await postApi("/group-merges/merge", {
        source_ids: actualSources.map((s) => s.id),
        target_id: actualTarget.id,
      });
      onMerged(actualTarget!.id);
    } catch (e) {
      console.error("Merge failed:", e);
      alert("Merge failed. Check the console for details.");
    } finally {
      setMerging(false);
    }
  };

  const displayList = searchResults ?? candidates;

  const searchPlaceholder =
    direction === "absorb"
      ? "Search for groups to absorb..."
      : "Search for the parent group to merge into...";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />

      {/* Modal */}
      <div
        className="relative bg-white rounded-xl shadow-xl border border-[var(--gray-6)] w-full max-w-2xl max-h-[80vh] flex flex-col"
        style={{ zIndex: 51 }}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-[var(--gray-6)]">
          <Heading size="4" weight="medium">
            {step === "select" ? "Merge Groups" : "Confirm Merge"}
          </Heading>
          <button
            onClick={onClose}
            className="p-1 rounded hover:bg-[var(--gray-3)] transition-colors"
          >
            <X size={18} style={{ color: "var(--gray-9)" }} />
          </button>
        </div>

        {step === "select" ? (
          <>
            {/* Direction toggle + current group info */}
            <div className="px-5 py-3 border-b border-[var(--gray-4)]" style={{ background: "var(--gray-2)" }}>
              <Text size="1" style={{ color: "var(--gray-9)" }} className="block mb-2">
                {targetGroup.display_name} — {targetGroup.property_count} props, {targetGroup.transaction_count} txns, {targetGroup.contact_count} contacts
              </Text>
              <div className="flex gap-1">
                <button
                  className="px-3 py-1 text-[13px] font-medium rounded-md border transition-colors"
                  style={{
                    borderColor: direction === "absorb" ? "var(--accent-7)" : "var(--gray-6)",
                    background: direction === "absorb" ? "var(--accent-2)" : "transparent",
                    color: direction === "absorb" ? "var(--accent-11)" : "var(--gray-11)",
                  }}
                  onClick={() => handleDirectionChange("absorb")}
                >
                  Absorb other groups into this one
                </button>
                <button
                  className="px-3 py-1 text-[13px] font-medium rounded-md border transition-colors"
                  style={{
                    borderColor: direction === "into" ? "var(--accent-7)" : "var(--gray-6)",
                    background: direction === "into" ? "var(--accent-2)" : "transparent",
                    color: direction === "into" ? "var(--accent-11)" : "var(--gray-11)",
                  }}
                  onClick={() => handleDirectionChange("into")}
                >
                  Merge this group into another
                </button>
              </div>
            </div>

            {/* Search bar */}
            <div className="px-5 py-3 border-b border-[var(--gray-4)]">
              <div className="relative">
                <MagnifyingGlass
                  size={14}
                  className="absolute left-2.5 top-1/2 -translate-y-1/2"
                  style={{ color: "var(--gray-8)" }}
                />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleSearch()}
                  placeholder={searchPlaceholder}
                  className="w-full h-8 pl-8 pr-3 text-[13px] rounded-md border border-[var(--gray-6)] bg-white outline-none focus:border-[var(--accent-7)]"
                  style={{ color: "var(--gray-12)" }}
                />
              </div>
              {searchResults && (
                <button
                  onClick={() => { setSearchResults(null); setSearchQuery(""); }}
                  className="mt-1 text-[12px] hover:underline"
                  style={{ color: "var(--accent-11)" }}
                >
                  Show suggested candidates instead
                </button>
              )}
            </div>

            {/* Selected groups */}
            {selected.length > 0 && (
              <div className="px-5 py-2 border-b border-[var(--gray-4)] flex flex-wrap gap-1.5">
                {selected.map((s) => (
                  <Badge
                    key={s.id}
                    size="1"
                    variant="soft"
                    color="jade"
                    className="cursor-pointer"
                    onClick={() => toggleSelect(s)}
                  >
                    {s.display_name} ({s.property_count} props)
                    <X size={10} className="ml-1" />
                  </Badge>
                ))}
              </div>
            )}

            {/* Candidate list */}
            <div className="flex-1 overflow-y-auto px-5 py-2">
              {loading ? (
                <Text size="2" className="py-4 block text-center" style={{ color: "var(--gray-9)" }}>
                  Finding candidates...
                </Text>
              ) : displayList.length === 0 ? (
                <Text size="2" className="py-4 block text-center" style={{ color: "var(--gray-9)" }}>
                  {searchResults ? "No groups found" : "No suggested candidates"}
                </Text>
              ) : (
                <div className="flex flex-col gap-1">
                  {!searchResults && (
                    <Text size="1" className="mb-1 block" style={{ color: "var(--gray-9)" }}>
                      {direction === "absorb"
                        ? "Suggested candidates (similar name):"
                        : "Suggested parent groups (similar name):"}
                    </Text>
                  )}
                  {displayList.map((c) => (
                    <div
                      key={c.id}
                      className={`flex items-center justify-between px-3 py-2 rounded-md cursor-pointer transition-colors ${
                        isSelected(c.id)
                          ? "bg-[var(--jade-3)] border border-[var(--jade-7)]"
                          : "hover:bg-[var(--gray-3)] border border-transparent"
                      }`}
                      onClick={() => toggleSelect(c)}
                    >
                      <div className="flex-1 min-w-0">
                        <Text size="2" weight="medium" className="block truncate">
                          {c.display_name}
                        </Text>
                        <Text size="1" style={{ color: "var(--gray-9)" }}>
                          {c.property_count} props, {c.transaction_count} txns
                          {c.total_assessed_value ? `, ${formatCompact(c.total_assessed_value)}` : ""}
                        </Text>
                      </div>
                      {isSelected(c.id) && (
                        <Badge size="1" color="jade">Selected</Badge>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Footer */}
            <div className="px-5 py-3 border-t border-[var(--gray-6)] flex items-center justify-between">
              <Text size="2" style={{ color: "var(--gray-9)" }}>
                {selected.length} group{selected.length !== 1 ? "s" : ""} selected
              </Text>
              <div className="flex gap-2">
                <Button size="2" variant="soft" color="gray" onClick={onClose}>
                  Cancel
                </Button>
                <Button
                  size="2"
                  disabled={selected.length === 0}
                  onClick={() => setStep("confirm")}
                >
                  Review Merge
                </Button>
              </div>
            </div>
          </>
        ) : (
          <>
            {/* Confirm step */}
            <div className="flex-1 overflow-y-auto px-5 py-4">
              {/* Warning callout */}
              <div
                className="rounded-lg px-4 py-3 mb-4 flex items-start gap-3"
                style={{ background: "var(--amber-3)", border: "1px solid var(--amber-7)" }}
              >
                <Warning size={18} style={{ color: "var(--amber-11)", marginTop: 2 }} />
                <div>
                  <Text size="2" weight="medium" style={{ color: "var(--amber-11)" }} className="block">
                    {direction === "absorb"
                      ? `This will permanently merge ${selected.length} group${selected.length !== 1 ? "s" : ""} into ${targetGroup.display_name}`
                      : `This will permanently merge ${targetGroup.display_name} into ${selected[0]?.display_name}`}
                  </Text>
                  <Text size="1" style={{ color: "var(--amber-11)" }}>
                    Properties, contacts, transactions, and CRM data will be consolidated. This can be undone.
                  </Text>
                </div>
              </div>

              {/* Merge preview */}
              <div className="flex items-center gap-4 mb-4">
                {/* Source groups */}
                <div className="flex-1">
                  <Text size="1" weight="medium" style={{ color: "var(--gray-9)" }} className="block mb-2">
                    MERGING
                  </Text>
                  {actualSources.map((s) => (
                    <div key={s.id} className="py-1.5 border-b border-[var(--gray-4)] last:border-0">
                      <Text size="2" weight="medium" className="block">{s.display_name}</Text>
                      <Text size="1" style={{ color: "var(--gray-9)" }}>
                        {s.property_count} props, {s.transaction_count} txns
                      </Text>
                    </div>
                  ))}
                </div>

                {/* Arrow */}
                <ArrowRight size={24} style={{ color: "var(--gray-8)" }} />

                {/* Target */}
                <div className="flex-1">
                  <Text size="1" weight="medium" style={{ color: "var(--gray-9)" }} className="block mb-2">
                    INTO
                  </Text>
                  {actualTarget && (
                    <div className="py-1.5">
                      <Text size="2" weight="medium" className="block">{actualTarget.display_name}</Text>
                      <Text size="1" style={{ color: "var(--gray-9)" }}>
                        {actualTarget.property_count} props, {actualTarget.transaction_count} txns
                      </Text>
                    </div>
                  )}
                </div>
              </div>

              {/* Combined totals */}
              <div
                className="rounded-lg px-4 py-3"
                style={{ background: "var(--jade-3)", border: "1px solid var(--jade-7)" }}
              >
                <Text size="2" weight="medium" style={{ color: "var(--jade-11)" }} className="block">
                  Result: {combinedProps} properties, {combinedTxns} transactions, {combinedContacts} contacts
                </Text>
              </div>
            </div>

            {/* Footer */}
            <div className="px-5 py-3 border-t border-[var(--gray-6)] flex items-center justify-end gap-2">
              <Button size="2" variant="soft" color="gray" onClick={() => setStep("select")}>
                Back
              </Button>
              <Button size="2" color="jade" onClick={handleMerge} disabled={merging}>
                {merging ? "Merging..." : direction === "absorb"
                  ? `Merge ${selected.length} Group${selected.length !== 1 ? "s" : ""}`
                  : `Merge into ${selected[0]?.display_name}`}
              </Button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
