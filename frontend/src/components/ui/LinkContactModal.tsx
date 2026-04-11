import { useState, useEffect } from "react";
import { Heading, Text, Button, TextField, Badge } from "@radix-ui/themes";
import { MagnifyingGlass, X, UserPlus } from "@phosphor-icons/react";
import { fetchApi, postApi } from "../../api/client";
import type { SearchResponse, ContactBrowseItem } from "../../types";

interface Props {
  groupId: string;
  groupName: string;
  existingContactIds: Set<string>;
  onClose: () => void;
  onLinked: () => void;
}

export default function LinkContactModal({ groupId, groupName, existingContactIds, onClose, onLinked }: Props) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<ContactBrowseItem[]>([]);
  const [searching, setSearching] = useState(false);
  const [linking, setLinking] = useState<string | null>(null);
  const [role, setRole] = useState("");

  useEffect(() => {
    if (query.trim().length < 2) {
      setResults([]);
      return;
    }
    const timer = setTimeout(() => {
      setSearching(true);
      fetchApi<SearchResponse<ContactBrowseItem>>("/contacts/search", { q: query.trim(), limit: 20 })
        .then((r) => setResults(r.results))
        .finally(() => setSearching(false));
    }, 300);
    return () => clearTimeout(timer);
  }, [query]);

  const handleLink = async (contactId: string) => {
    setLinking(contactId);
    try {
      await postApi(`/groups/${groupId}/contacts`, {
        contact_id: contactId,
        role: role || null,
        is_current: true,
      });
      onLinked();
    } catch {
      // silently fail (likely already linked)
    }
    setLinking(null);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center" style={{ background: "rgba(0,0,0,0.15)" }}>
      <div className="w-[520px] max-h-[600px] flex flex-col rounded-[var(--card-radius)] border border-[var(--gray-6)] bg-white" style={{ boxShadow: "var(--elevation-4)" }}>
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-[var(--gray-4)]">
          <div>
            <Heading size="4" weight="medium">Link Contact</Heading>
            <Text size="1" style={{ color: "var(--gray-9)" }}>Add a contact to {groupName}</Text>
          </div>
          <button onClick={onClose} className="p-1 rounded hover:bg-gray-100">
            <X size={16} />
          </button>
        </div>

        {/* Search */}
        <div className="px-5 py-3 border-b border-[var(--gray-4)]">
          <TextField.Root
            size="2"
            placeholder="Search contacts by name..."
            value={query}
            onChange={(e: any) => setQuery(e.target.value)}
          >
            <TextField.Slot>
              <MagnifyingGlass size={14} />
            </TextField.Slot>
          </TextField.Root>
          <div className="mt-2">
            <Text size="1" weight="medium" style={{ color: "var(--gray-9)" }}>Role (optional)</Text>
            <TextField.Root
              size="1"
              placeholder="e.g. VP Acquisitions, Counsel..."
              value={role}
              onChange={(e: any) => setRole(e.target.value)}
              className="mt-1"
            />
          </div>
        </div>

        {/* Results */}
        <div className="flex-1 overflow-y-auto px-5 py-3">
          {searching && <Text size="2" style={{ color: "var(--gray-9)" }}>Searching...</Text>}
          {!searching && query.trim().length >= 2 && results.length === 0 && (
            <Text size="2" style={{ color: "var(--gray-9)" }}>No contacts found</Text>
          )}
          {results.map((c) => {
            const alreadyLinked = existingContactIds.has(c.id);
            return (
              <div
                key={c.id}
                className="flex items-center justify-between py-2.5 border-b border-[var(--gray-4)] last:border-0"
              >
                <div>
                  <Text size="2" weight="medium">{c.display_name}</Text>
                  <div className="flex gap-2 mt-0.5">
                    {c.company_name && <Text size="1" style={{ color: "var(--gray-9)" }}>{c.company_name}</Text>}
                    <Text size="1" style={{ color: "var(--gray-9)" }}>{c.transaction_count} txns</Text>
                    <Badge size="1" variant="soft" color={c.status === "engaged" ? "jade" : "gray"}>{c.status}</Badge>
                  </div>
                </div>
                {alreadyLinked ? (
                  <Badge size="1" variant="soft">Already linked</Badge>
                ) : (
                  <Button size="1" variant="soft" onClick={() => handleLink(c.id)} disabled={linking === c.id}>
                    <UserPlus size={12} />
                    {linking === c.id ? "Linking..." : "Link"}
                  </Button>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
