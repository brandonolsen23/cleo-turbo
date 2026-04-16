import { useState, useEffect, useRef, useCallback } from "react";
import { Text, Button, Badge, Heading, TextField } from "@radix-ui/themes";
import { X, ArrowRight, Warning, Plus, Buildings, MagnifyingGlass } from "@phosphor-icons/react";
import { fetchApi, postApi } from "../../api/client";
import type {
  AffiliatedGroup,
  AffiliatedGroupsResponse,
  MergePreviewResponse,
  CreateGroupResponse,
  GroupSearchResult,
  GroupSearchResponse,
} from "../../types";

// ── Types ──────────────────────────────────────────────────────

interface ConsolidateGroupsModalProps {
  contactId: string;
  contactName: string;
  onClose: () => void;
  onConsolidated: () => void;
}

type Step = "select" | "target" | "preview";

// ── Component ──────────────────────────────────────────────────

export default function ConsolidateGroupsModal({
  contactId,
  contactName,
  onClose,
  onConsolidated,
}: ConsolidateGroupsModalProps) {
  const [groups, setGroups] = useState<AffiliatedGroup[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [step, setStep] = useState<Step>("select");

  // Target selection
  const [targetMode, setTargetMode] = useState<"existing" | "search" | "new">("existing");
  const [targetGroupId, setTargetGroupId] = useState<string | null>(null);
  const [newGroupName, setNewGroupName] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState("");

  // Search mode
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<GroupSearchResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [searchedGroup, setSearchedGroup] = useState<GroupSearchResult | null>(null);
  const searchTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Preview
  const [preview, setPreview] = useState<MergePreviewResponse | null>(null);
  const [merging, setMerging] = useState(false);

  // Load affiliated groups
  useEffect(() => {
    setLoading(true);
    fetchApi<AffiliatedGroupsResponse>(`/contacts/${contactId}/affiliated-groups`)
      .then((r) => {
        setGroups(r.affiliated_groups);
        // Pre-select all by default
        setSelected(new Set(r.affiliated_groups.map((g) => g.id)));
      })
      .finally(() => setLoading(false));
  }, [contactId]);

  // Debounced group search
  const handleSearch = useCallback((q: string) => {
    setSearchQuery(q);
    if (searchTimeout.current) clearTimeout(searchTimeout.current);
    if (!q.trim()) {
      setSearchResults([]);
      setSearching(false);
      return;
    }
    setSearching(true);
    searchTimeout.current = setTimeout(() => {
      fetchApi<GroupSearchResponse>("/groups/search", { q: q.trim(), limit: 10 })
        .then((r) => {
          // Exclude groups that are already selected in step 1
          setSearchResults(r.results.filter((g) => !selected.has(g.id)));
          setSearching(false);
        })
        .catch(() => setSearching(false));
    }, 250);
  }, [selected]);

  const toggleSelect = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const selectedGroups = groups.filter((g) => selected.has(g.id));
  const totalProps = selectedGroups.reduce((s, g) => s + g.property_count, 0);
  const totalTxns = selectedGroups.reduce((s, g) => s + g.transaction_count, 0);

  // Get the target display name for rendering
  const targetGroup = targetMode === "existing"
    ? groups.find((g) => g.id === targetGroupId)
    : targetMode === "search"
    ? searchedGroup
    : null;
  const targetDisplayName = targetMode === "existing"
    ? (groups.find((g) => g.id === targetGroupId)?.display_name ?? "")
    : targetMode === "search"
    ? (searchedGroup?.display_name ?? "")
    : newGroupName;

  // Source groups = all selected minus the target (if target is existing and selected)
  const sourceGroups = selectedGroups.filter((g) => g.id !== targetGroupId);

  const handleProceedToTarget = () => {
    // Default target to the group with most properties
    if (selectedGroups.length > 0) {
      const best = [...selectedGroups].sort(
        (a, b) => b.property_count - a.property_count
      )[0];
      setTargetGroupId(best.id);
    }
    setStep("target");
  };

  const handleProceedToPreview = async () => {
    let actualTargetId = targetGroupId;

    // If creating a new group, do it first
    if (targetMode === "new") {
      if (!newGroupName.trim()) return;
      setCreating(true);
      setCreateError("");
      try {
        const res = await postApi<CreateGroupResponse>("/groups", {
          display_name: newGroupName.trim(),
        });
        actualTargetId = res.id;
        setTargetGroupId(res.id);
      } catch (e: unknown) {
        const msg = e instanceof Error ? e.message : "Failed to create group";
        setCreateError(msg);
        setCreating(false);
        return;
      }
      setCreating(false);
    }

    if (!actualTargetId) return;

    // Get the source IDs (everything selected that isn't the target)
    const sourceIds = selectedGroups
      .map((g) => g.id)
      .filter((id) => id !== actualTargetId);

    if (sourceIds.length === 0) return;

    // Fetch preview
    try {
      const prev = await postApi<MergePreviewResponse>("/group-merges/preview", {
        source_ids: sourceIds,
        target_id: actualTargetId,
      });
      setPreview(prev);
      setStep("preview");
    } catch (e) {
      console.error("Preview failed:", e);
    }
  };

  const handleMerge = async () => {
    if (!targetGroupId) return;
    const sourceIds = selectedGroups
      .map((g) => g.id)
      .filter((id) => id !== targetGroupId);
    if (sourceIds.length === 0) return;

    setMerging(true);
    try {
      await postApi("/group-merges/merge", {
        source_ids: sourceIds,
        target_id: targetGroupId,
      });
      onConsolidated();
    } catch (e) {
      console.error("Merge failed:", e);
      alert("Merge failed. Check the console for details.");
    } finally {
      setMerging(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />

      <div
        className="relative bg-white rounded-xl shadow-xl border border-[var(--gray-6)] w-full max-w-2xl max-h-[80vh] flex flex-col"
        style={{ zIndex: 51 }}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-[var(--gray-6)]">
          <div>
            <Heading size="4" weight="medium">
              {step === "select"
                ? "Consolidate Groups"
                : step === "target"
                ? "Choose Target Group"
                : "Confirm Consolidation"}
            </Heading>
            <Text size="1" style={{ color: "var(--gray-9)" }}>
              {contactName}
            </Text>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded hover:bg-[var(--gray-3)] transition-colors"
          >
            <X size={18} style={{ color: "var(--gray-9)" }} />
          </button>
        </div>

        {/* Step 1: Select groups */}
        {step === "select" && (
          <>
            <div
              className="px-5 py-2 border-b border-[var(--gray-4)]"
              style={{ background: "var(--gray-2)" }}
            >
              <Text size="1" style={{ color: "var(--gray-9)" }}>
                Select which groups to consolidate. These are all groups{" "}
                {contactName} has transacted under.
              </Text>
            </div>

            <div className="flex-1 overflow-y-auto px-5 py-2">
              {loading ? (
                <Text
                  size="2"
                  className="py-4 block text-center"
                  style={{ color: "var(--gray-9)" }}
                >
                  Loading affiliated groups...
                </Text>
              ) : groups.length === 0 ? (
                <Text
                  size="2"
                  className="py-4 block text-center"
                  style={{ color: "var(--gray-9)" }}
                >
                  No affiliated groups found
                </Text>
              ) : (
                <div className="flex flex-col gap-1">
                  {groups.map((g) => (
                    <div
                      key={g.id}
                      className={`flex items-center justify-between px-3 py-2.5 rounded-md cursor-pointer transition-colors ${
                        selected.has(g.id)
                          ? "bg-[var(--jade-3)] border border-[var(--jade-7)]"
                          : "hover:bg-[var(--gray-3)] border border-transparent"
                      }`}
                      onClick={() => toggleSelect(g.id)}
                    >
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <Text
                            size="2"
                            weight="medium"
                            className="block truncate"
                          >
                            {g.display_name}
                          </Text>
                          {g.is_current_group === 1 && (
                            <Badge size="1" color="jade" variant="soft">
                              Current
                            </Badge>
                          )}
                        </div>
                        <Text size="1" style={{ color: "var(--gray-9)" }}>
                          {g.property_count} properties, {g.transaction_count}{" "}
                          txns, {g.shared_transactions} with {contactName.split(" ")[0]}
                        </Text>
                      </div>
                      <div className="flex items-center gap-2">
                        <div
                          className={`w-4 h-4 rounded border-2 flex items-center justify-center ${
                            selected.has(g.id)
                              ? "border-[var(--jade-9)] bg-[var(--jade-9)]"
                              : "border-[var(--gray-7)]"
                          }`}
                        >
                          {selected.has(g.id) && (
                            <svg
                              width="10"
                              height="8"
                              viewBox="0 0 10 8"
                              fill="none"
                            >
                              <path
                                d="M1 4L3.5 6.5L9 1"
                                stroke="white"
                                strokeWidth="2"
                                strokeLinecap="round"
                                strokeLinejoin="round"
                              />
                            </svg>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="px-5 py-3 border-t border-[var(--gray-6)] flex items-center justify-between">
              <Text size="2" style={{ color: "var(--gray-9)" }}>
                {selected.size} of {groups.length} selected — {totalProps}{" "}
                properties, {totalTxns} transactions
              </Text>
              <div className="flex gap-2">
                <Button size="2" variant="soft" color="gray" onClick={onClose}>
                  Cancel
                </Button>
                <Button
                  size="2"
                  disabled={selected.size < 2}
                  onClick={handleProceedToTarget}
                >
                  Next: Choose Target
                </Button>
              </div>
            </div>
          </>
        )}

        {/* Step 2: Choose target */}
        {step === "target" && (
          <>
            <div className="flex-1 overflow-y-auto px-5 py-4">
              <Text size="2" className="block mb-4">
                Choose which group everything should be consolidated under —
                pick from selected groups, search for any group, or create a new one.
              </Text>

              {/* Toggle: existing vs search vs new */}
              <div className="flex gap-1 mb-4">
                {([
                  { mode: "existing" as const, icon: <Buildings size={14} className="inline mr-1.5" style={{ marginTop: -2 }} />, label: "Use selected group" },
                  { mode: "search" as const, icon: <MagnifyingGlass size={14} className="inline mr-1.5" style={{ marginTop: -2 }} />, label: "Search all groups" },
                  { mode: "new" as const, icon: <Plus size={14} className="inline mr-1.5" style={{ marginTop: -2 }} />, label: "Create new group" },
                ]).map(({ mode, icon, label }) => (
                  <button
                    key={mode}
                    className="px-3 py-1.5 text-[13px] font-medium rounded-md border transition-colors"
                    style={{
                      borderColor:
                        targetMode === mode
                          ? "var(--accent-7)"
                          : "var(--gray-6)",
                      background:
                        targetMode === mode
                          ? "var(--accent-2)"
                          : "transparent",
                      color:
                        targetMode === mode
                          ? "var(--accent-11)"
                          : "var(--gray-11)",
                    }}
                    onClick={() => setTargetMode(mode)}
                  >
                    {icon}
                    {label}
                  </button>
                ))}
              </div>

              {targetMode === "existing" ? (
                <div className="flex flex-col gap-1">
                  {selectedGroups.map((g) => (
                    <div
                      key={g.id}
                      className={`flex items-center justify-between px-3 py-2.5 rounded-md cursor-pointer transition-colors ${
                        targetGroupId === g.id
                          ? "bg-[var(--jade-3)] border border-[var(--jade-7)]"
                          : "hover:bg-[var(--gray-3)] border border-transparent"
                      }`}
                      onClick={() => setTargetGroupId(g.id)}
                    >
                      <div>
                        <Text size="2" weight="medium" className="block">
                          {g.display_name}
                        </Text>
                        <Text size="1" style={{ color: "var(--gray-9)" }}>
                          {g.property_count} properties,{" "}
                          {g.transaction_count} txns
                        </Text>
                      </div>
                      {targetGroupId === g.id && (
                        <Badge size="1" color="jade">
                          Target
                        </Badge>
                      )}
                    </div>
                  ))}
                </div>
              ) : targetMode === "search" ? (
                <div className="space-y-3">
                  <TextField.Root
                    size="2"
                    placeholder="Search by group name..."
                    value={searchQuery}
                    onChange={(e) => handleSearch(e.target.value)}
                  >
                    <TextField.Slot>
                      <MagnifyingGlass size={14} style={{ color: "var(--gray-9)" }} />
                    </TextField.Slot>
                  </TextField.Root>

                  {/* Selected search result */}
                  {searchedGroup && (
                    <div
                      className="flex items-center justify-between px-3 py-2.5 rounded-md bg-[var(--jade-3)] border border-[var(--jade-7)]"
                    >
                      <div>
                        <Text size="2" weight="medium" className="block">
                          {searchedGroup.display_name}
                        </Text>
                        <Text size="1" style={{ color: "var(--gray-9)" }}>
                          {searchedGroup.property_count} properties,{" "}
                          {searchedGroup.transaction_count} txns,{" "}
                          {searchedGroup.contact_count} contacts
                        </Text>
                      </div>
                      <div className="flex items-center gap-2">
                        <Badge size="1" color="jade">Target</Badge>
                        <button
                          className="p-0.5 rounded hover:bg-[var(--jade-5)] transition-colors"
                          onClick={() => {
                            setSearchedGroup(null);
                            setTargetGroupId(null);
                          }}
                        >
                          <X size={14} style={{ color: "var(--jade-11)" }} />
                        </button>
                      </div>
                    </div>
                  )}

                  {/* Search results */}
                  {!searchedGroup && searching && (
                    <Text size="1" style={{ color: "var(--gray-9)" }} className="block py-2 text-center">
                      Searching...
                    </Text>
                  )}
                  {!searchedGroup && !searching && searchQuery.trim() && searchResults.length === 0 && (
                    <Text size="1" style={{ color: "var(--gray-9)" }} className="block py-2 text-center">
                      No groups found matching "{searchQuery}"
                    </Text>
                  )}
                  {!searchedGroup && searchResults.length > 0 && (
                    <div className="flex flex-col gap-1">
                      {searchResults.map((g) => (
                        <div
                          key={g.id}
                          className="flex items-center justify-between px-3 py-2.5 rounded-md cursor-pointer hover:bg-[var(--gray-3)] border border-transparent transition-colors"
                          onClick={() => {
                            setSearchedGroup(g);
                            setTargetGroupId(g.id);
                            setSearchResults([]);
                          }}
                        >
                          <div>
                            <Text size="2" weight="medium" className="block">
                              {g.display_name}
                            </Text>
                            <Text size="1" style={{ color: "var(--gray-9)" }}>
                              {g.property_count} properties,{" "}
                              {g.transaction_count} txns,{" "}
                              {g.contact_count} contacts
                            </Text>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                  {!searchedGroup && !searchQuery.trim() && (
                    <Text size="1" style={{ color: "var(--gray-9)" }}>
                      Search for any group in the system to use as the consolidation target.
                    </Text>
                  )}
                </div>
              ) : (
                <div className="space-y-3">
                  <div>
                    <Text
                      size="1"
                      weight="medium"
                      className="block mb-1.5"
                      style={{ color: "var(--gray-9)" }}
                    >
                      New group name
                    </Text>
                    <TextField.Root
                      size="2"
                      placeholder="e.g. DH Property Management Inc."
                      value={newGroupName}
                      onChange={(e) => setNewGroupName(e.target.value)}
                    />
                  </div>
                  {createError && (
                    <Text size="1" style={{ color: "var(--red-11)" }}>
                      {createError}
                    </Text>
                  )}
                  <Text size="1" style={{ color: "var(--gray-9)" }}>
                    This group will be created as a permanent entry that
                    survives database recompiles.
                  </Text>
                </div>
              )}
            </div>

            <div className="px-5 py-3 border-t border-[var(--gray-6)] flex items-center justify-end gap-2">
              <Button
                size="2"
                variant="soft"
                color="gray"
                onClick={() => setStep("select")}
              >
                Back
              </Button>
              <Button
                size="2"
                disabled={
                  (targetMode === "existing" && !targetGroupId) ||
                  (targetMode === "search" && !searchedGroup) ||
                  (targetMode === "new" && !newGroupName.trim()) ||
                  creating
                }
                onClick={handleProceedToPreview}
              >
                {creating ? "Creating..." : "Review"}
              </Button>
            </div>
          </>
        )}

        {/* Step 3: Preview and confirm */}
        {step === "preview" && preview && (
          <>
            <div className="flex-1 overflow-y-auto px-5 py-4">
              {/* Warning */}
              <div
                className="rounded-lg px-4 py-3 mb-4 flex items-start gap-3"
                style={{
                  background: "var(--amber-3)",
                  border: "1px solid var(--amber-7)",
                }}
              >
                <Warning
                  size={18}
                  style={{ color: "var(--amber-11)", marginTop: 2 }}
                />
                <div>
                  <Text
                    size="2"
                    weight="medium"
                    style={{ color: "var(--amber-11)" }}
                    className="block"
                  >
                    This will merge {sourceGroups.length} group
                    {sourceGroups.length !== 1 ? "s" : ""} into{" "}
                    {targetDisplayName}
                  </Text>
                  <Text size="1" style={{ color: "var(--amber-11)" }}>
                    Properties, contacts, transactions, and CRM data will be
                    consolidated. This can be undone.
                  </Text>
                </div>
              </div>

              {/* Merge diagram */}
              <div className="flex items-center gap-4 mb-4">
                <div className="flex-1">
                  <Text
                    size="1"
                    weight="medium"
                    style={{ color: "var(--gray-9)" }}
                    className="block mb-2"
                  >
                    MERGING
                  </Text>
                  {sourceGroups.map((g) => (
                    <div
                      key={g.id}
                      className="py-1.5 border-b border-[var(--gray-4)] last:border-0"
                    >
                      <Text size="2" weight="medium" className="block">
                        {g.display_name}
                      </Text>
                      <Text size="1" style={{ color: "var(--gray-9)" }}>
                        {g.property_count} props, {g.transaction_count} txns
                      </Text>
                    </div>
                  ))}
                </div>

                <ArrowRight size={24} style={{ color: "var(--gray-8)" }} />

                <div className="flex-1">
                  <Text
                    size="1"
                    weight="medium"
                    style={{ color: "var(--gray-9)" }}
                    className="block mb-2"
                  >
                    INTO
                  </Text>
                  <div className="py-1.5">
                    <Text size="2" weight="medium" className="block">
                      {targetDisplayName}
                    </Text>
                    {targetGroup && (
                      <Text size="1" style={{ color: "var(--gray-9)" }}>
                        {targetGroup.property_count} props,{" "}
                        {targetGroup.transaction_count} txns
                      </Text>
                    )}
                    {targetMode === "new" && (
                      <Badge size="1" color="jade" variant="soft" className="mt-1">
                        New group
                      </Badge>
                    )}
                  </div>
                </div>
              </div>

              {/* Impact summary */}
              <div
                className="rounded-lg px-4 py-3 mb-3"
                style={{
                  background: "var(--jade-3)",
                  border: "1px solid var(--jade-7)",
                }}
              >
                <Text
                  size="2"
                  weight="medium"
                  style={{ color: "var(--jade-11)" }}
                >
                  {preview.affected_properties} properties,{" "}
                  {preview.affected_transactions} transactions,{" "}
                  {preview.affected_contacts.length} contacts affected
                </Text>
              </div>

              {/* Affected contacts */}
              {preview.affected_contacts.length > 0 && (
                <div>
                  <Text
                    size="1"
                    weight="medium"
                    style={{ color: "var(--gray-9)" }}
                    className="block mb-1.5"
                  >
                    Other contacts affected:
                  </Text>
                  <div className="flex flex-wrap gap-1">
                    {preview.affected_contacts.slice(0, 20).map((c) => (
                      <Badge key={c.id} size="1" variant="soft" color="gray">
                        {c.name}
                      </Badge>
                    ))}
                    {preview.affected_contacts.length > 20 && (
                      <Badge size="1" variant="soft" color="gray">
                        +{preview.affected_contacts.length - 20} more
                      </Badge>
                    )}
                  </div>
                </div>
              )}
            </div>

            <div className="px-5 py-3 border-t border-[var(--gray-6)] flex items-center justify-end gap-2">
              <Button
                size="2"
                variant="soft"
                color="gray"
                onClick={() => setStep("target")}
              >
                Back
              </Button>
              <Button
                size="2"
                color="jade"
                onClick={handleMerge}
                disabled={merging}
              >
                {merging
                  ? "Merging..."
                  : `Consolidate ${sourceGroups.length} Group${
                      sourceGroups.length !== 1 ? "s" : ""
                    }`}
              </Button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
