import { useEffect, useState } from "react";
import { Button, Heading, Text, TextField, Switch, Badge } from "@radix-ui/themes";
import { X, Plus } from "@phosphor-icons/react";
import { fetchApi, postApi, mutateApi } from "../../api/client";
import type { ListSummary, ListMembership } from "../../types";

interface AddToListDrawerProps {
  memberType: "contact" | "property" | "group";
  memberId: string;
  onClose: () => void;
}

export default function AddToListDrawer({ memberType, memberId, onClose }: AddToListDrawerProps) {
  const [lists, setLists] = useState<ListSummary[]>([]);
  const [memberOf, setMemberOf] = useState<Set<string>>(new Set());
  const [pending, setPending] = useState<Set<string>>(new Set());
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [newShared, setNewShared] = useState(false);
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    fetchApi<ListSummary[]>("/lists").then(setLists);
    fetchApi<ListMembership[]>(
      `/lists/membership?member_type=${memberType}&member_id=${encodeURIComponent(memberId)}`
    ).then((r) => setMemberOf(new Set(r.map((m) => m.list_id))));
  }, [memberType, memberId]);

  async function toggleMember(listId: string) {
    if (pending.has(listId)) return;
    const isMember = memberOf.has(listId);
    setPending((p) => new Set(p).add(listId));
    const next = new Set(memberOf);
    if (isMember) next.delete(listId);
    else next.add(listId);
    setMemberOf(next);
    try {
      if (isMember) {
        await mutateApi(
          `/lists/${listId}/members/${memberType}/${encodeURIComponent(memberId)}`,
          "DELETE"
        );
      } else {
        await postApi(`/lists/${listId}/members`, { member_type: memberType, member_id: memberId });
      }
    } catch {
      // revert
      const reverted = new Set(memberOf);
      if (isMember) reverted.add(listId);
      else reverted.delete(listId);
      setMemberOf(reverted);
    } finally {
      setPending((p) => {
        const n = new Set(p);
        n.delete(listId);
        return n;
      });
    }
  }

  async function createAndAdd() {
    if (!newName.trim()) return;
    setCreating(true);
    try {
      const res = await postApi<{ id: string }>("/lists", {
        name: newName.trim(),
        description: newDesc.trim() || null,
        scope: newShared ? "shared" : "personal",
      });
      await postApi(`/lists/${res.id}/members`, { member_type: memberType, member_id: memberId });
      const refreshed = await fetchApi<ListSummary[]>("/lists");
      setLists(refreshed);
      setMemberOf((prev) => new Set(prev).add(res.id));
      setShowCreate(false);
      setNewName("");
      setNewDesc("");
      setNewShared(false);
    } finally {
      setCreating(false);
    }
  }

  const personal = lists.filter((l) => l.scope === "personal");
  const shared = lists.filter((l) => l.scope === "shared");

  return (
    <div className="fixed inset-0 z-50 flex">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="relative ml-auto w-full max-w-md h-full overflow-y-auto bg-[var(--color-background)] border-l border-[var(--gray-6)] p-6">
        <div className="flex items-center justify-between mb-4">
          <Heading size="4">Add to list</Heading>
          <button onClick={onClose} className="p-1 rounded hover:bg-[var(--gray-3)]">
            <X size={18} />
          </button>
        </div>

        {personal.length > 0 && (
          <div className="mb-6">
            <Text size="2" weight="medium" style={{ color: "var(--gray-11)" }} className="block mb-2">
              My personal lists
            </Text>
            <div className="flex flex-col gap-1">
              {personal.map((l) => (
                <ListRow
                  key={l.id}
                  list={l}
                  checked={memberOf.has(l.id)}
                  onToggle={() => toggleMember(l.id)}
                />
              ))}
            </div>
          </div>
        )}

        {shared.length > 0 && (
          <div className="mb-6">
            <Text size="2" weight="medium" style={{ color: "var(--gray-11)" }} className="block mb-2">
              Shared lists
            </Text>
            <div className="flex flex-col gap-1">
              {shared.map((l) => (
                <ListRow
                  key={l.id}
                  list={l}
                  checked={memberOf.has(l.id)}
                  onToggle={() => toggleMember(l.id)}
                />
              ))}
            </div>
          </div>
        )}

        {!showCreate ? (
          <Button variant="soft" onClick={() => setShowCreate(true)}>
            <Plus size={14} /> New list
          </Button>
        ) : (
          <div className="flex flex-col gap-2 p-3 border border-[var(--gray-6)] rounded-md">
            <TextField.Root value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="List name" />
            <TextField.Root value={newDesc} onChange={(e) => setNewDesc(e.target.value)} placeholder="Description (optional)" />
            <label className="flex items-center gap-2">
              <Switch checked={newShared} onCheckedChange={setNewShared} />
              <Text size="2">Shared with team</Text>
            </label>
            <div className="flex justify-end gap-2 mt-2">
              <Button variant="soft" color="gray" onClick={() => setShowCreate(false)}>Cancel</Button>
              <Button onClick={createAndAdd} disabled={creating || !newName.trim()}>
                {creating ? "Creating..." : "Create + add"}
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function ListRow({
  list,
  checked,
  onToggle,
}: {
  list: ListSummary;
  checked: boolean;
  onToggle: () => void;
}) {
  return (
    <label className="flex items-center justify-between gap-2 p-2 rounded hover:bg-[var(--gray-2)] cursor-pointer">
      <div className="flex items-center gap-2">
        <input type="checkbox" checked={checked} onChange={onToggle} />
        <Text size="2">{list.name}</Text>
        {list.scope === "shared" && (
          <Badge size="1" variant="soft" color="jade">shared</Badge>
        )}
      </div>
      <Text size="1" style={{ color: "var(--gray-9)" }}>
        {list.total_members} members
      </Text>
    </label>
  );
}
