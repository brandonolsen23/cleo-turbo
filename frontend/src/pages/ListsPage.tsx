import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Heading, Text, Button, Badge, TextField, TextArea } from "@radix-ui/themes";
import { Plus, X } from "@phosphor-icons/react";
import { fetchApi, postApi } from "../api/client";
import { formatDate } from "../lib/utils";

interface ListItem {
  id: string;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
  total_members: number;
  member_counts: Record<string, number>;
}

export default function ListsPage() {
  const navigate = useNavigate();
  const [lists, setLists] = useState<ListItem[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ name: "", description: "" });

  const load = () => {
    fetchApi<ListItem[]>("/lists").then(setLists);
  };

  useEffect(load, []);

  const handleCreate = async () => {
    if (!form.name.trim()) return;
    await postApi<{ id: string }>("/lists", {
      name: form.name,
      description: form.description || null,
    });
    setForm({ name: "", description: "" });
    setShowForm(false);
    load();
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <Heading size="5" weight="medium">Lists</Heading>
        <Button size="2" onClick={() => setShowForm(true)}>
          <Plus size={14} />
          New List
        </Button>
      </div>

      {lists.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16">
          <Text size="3" weight="medium" style={{ color: "var(--gray-9)" }}>No lists yet</Text>
          <Text size="2" className="mt-1" style={{ color: "var(--gray-8)" }}>
            Create a list to organize properties, contacts, and groups for prospecting.
          </Text>
        </div>
      ) : (
        <div className="grid grid-cols-3 gap-4">
          {lists.map((l) => (
            <div
              key={l.id}
              className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5 cursor-pointer hover:border-[var(--gray-8)] transition-colors"
              onClick={() => navigate(`/lists/${l.id}`)}
            >
              <Text size="3" weight="medium" className="block">{l.name}</Text>
              {l.description && (
                <Text size="2" className="block mt-1 line-clamp-2" style={{ color: "var(--gray-11)" }}>
                  {l.description}
                </Text>
              )}
              <div className="flex gap-2 mt-3">
                {Object.entries(l.member_counts).map(([type, count]) => (
                  <Badge key={type} size="1" variant="soft">
                    {count} {type}{count !== 1 ? "s" : ""}
                  </Badge>
                ))}
                {l.total_members === 0 && (
                  <Text size="1" style={{ color: "var(--gray-8)" }}>Empty</Text>
                )}
              </div>
              <Text size="1" className="block mt-2" style={{ color: "var(--gray-9)" }}>
                Updated {formatDate(l.updated_at)}
              </Text>
            </div>
          ))}
        </div>
      )}

      {/* New List Modal */}
      {showForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center" style={{ background: "rgba(0,0,0,0.15)" }}>
          <div className="w-[400px] rounded-[var(--card-radius)] border border-[var(--gray-6)] bg-white p-6" style={{ boxShadow: "var(--elevation-4)" }}>
            <div className="flex items-center justify-between mb-4">
              <Heading size="4" weight="medium">New List</Heading>
              <button onClick={() => setShowForm(false)} className="p-1 rounded hover:bg-gray-100">
                <X size={16} />
              </button>
            </div>
            <div className="flex flex-col gap-3">
              <div>
                <Text size="1" weight="medium" className="mb-1 block" style={{ color: "var(--gray-9)" }}>Name</Text>
                <TextField.Root value={form.name} onChange={(e: any) => setForm({ ...form, name: e.target.value })} size="2" placeholder="List name" />
              </div>
              <div>
                <Text size="1" weight="medium" className="mb-1 block" style={{ color: "var(--gray-9)" }}>Description</Text>
                <TextArea value={form.description} onChange={(e: any) => setForm({ ...form, description: e.target.value })} size="2" placeholder="Optional" />
              </div>
              <div className="flex justify-end gap-2 mt-2">
                <Button variant="soft" size="2" onClick={() => setShowForm(false)}>Cancel</Button>
                <Button size="2" onClick={handleCreate} disabled={!form.name.trim()}>Create List</Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
