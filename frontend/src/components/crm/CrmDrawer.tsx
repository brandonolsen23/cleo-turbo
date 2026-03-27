import { useState, useEffect } from "react";
import { Text, Badge, Button, TextArea } from "@radix-ui/themes";
import { X, PencilSimple } from "@phosphor-icons/react";
import { useCrm } from "./CrmContext";
import { fetchApi, postApi } from "../../api/client";
import { formatDate } from "../../lib/utils";
import type { CrmNote } from "../../types";

export default function CrmDrawer() {
  const { isOpen, entity, closeDrawer, refreshKey, triggerRefresh } = useCrm();
  const [notes, setNotes] = useState<CrmNote[]>([]);
  const [newNote, setNewNote] = useState("");
  const [submitting, setSubmitting] = useState(false);

  // Load notes when entity changes
  useEffect(() => {
    if (!entity || !isOpen) return;
    if (entity.type === "contact" || entity.type === "group") {
      fetchApi<CrmNote[]>(`/notes/${entity.type}s/${entity.id}/notes`).then(setNotes);
    } else {
      setNotes([]);
    }
  }, [entity, isOpen, refreshKey]);

  const handleSubmit = async () => {
    if (!newNote.trim() || !entity) return;
    setSubmitting(true);
    try {
      await postApi(`/notes/${entity.type}s/${entity.id}/notes`, { note: newNote.trim() });
      setNewNote("");
      triggerRefresh();
    } finally {
      setSubmitting(false);
    }
  };

  const supportsNotes = entity?.type === "contact" || entity?.type === "group";

  return (
    <>
      {/* Backdrop */}
      <div
        className={`crm-drawer-backdrop ${isOpen ? "crm-drawer-backdrop--open" : ""}`}
        onClick={closeDrawer}
      />

      {/* Drawer */}
      <div className={`crm-drawer ${isOpen ? "crm-drawer--open" : ""}`}>
        {entity && (
          <>
            {/* Header */}
            <div className="flex items-center justify-between px-5 py-4 border-b" style={{ borderColor: "var(--gray-4)" }}>
              <div className="flex items-center gap-2 min-w-0">
                <Badge size="1" variant="soft" color={
                  entity.type === "contact" ? "blue" :
                  entity.type === "group" ? "jade" :
                  entity.type === "deal" ? "amber" : "gray"
                }>
                  {entity.type}
                </Badge>
                <Text size="3" weight="medium" className="truncate">{entity.name}</Text>
              </div>
              <button onClick={closeDrawer} className="p-1.5 rounded hover:bg-gray-100">
                <X size={16} style={{ color: "var(--gray-9)" }} />
              </button>
            </div>

            {/* Notes section */}
            {supportsNotes ? (
              <div className="flex-1 flex flex-col overflow-hidden">
                {/* Add note form */}
                <div className="px-5 py-3 border-b" style={{ borderColor: "var(--gray-4)" }}>
                  <div className="flex gap-2">
                    <TextArea
                      value={newNote}
                      onChange={(e: any) => setNewNote(e.target.value)}
                      placeholder="Add a note..."
                      size="2"
                      className="flex-1"
                      style={{ minHeight: 60 }}
                      onKeyDown={(e: any) => {
                        if (e.key === "Enter" && !e.shiftKey) {
                          e.preventDefault();
                          handleSubmit();
                        }
                      }}
                    />
                  </div>
                  <div className="flex justify-end mt-2">
                    <Button size="1" onClick={handleSubmit} disabled={!newNote.trim() || submitting}>
                      <PencilSimple size={14} />
                      Save Note
                    </Button>
                  </div>
                </div>

                {/* Notes timeline */}
                <div className="flex-1 overflow-y-auto px-5 py-3">
                  {notes.length === 0 ? (
                    <div className="flex items-center justify-center h-24">
                      <Text size="2" style={{ color: "var(--gray-9)" }}>No notes yet</Text>
                    </div>
                  ) : (
                    <div className="flex flex-col gap-3">
                      {notes.map((n) => (
                        <div key={n.id} className="rounded-lg border p-3" style={{ borderColor: "var(--gray-4)" }}>
                          <Text size="2" style={{ whiteSpace: "pre-line" }}>{n.note}</Text>
                          <div className="flex items-center gap-2 mt-2">
                            <Text size="1" style={{ color: "var(--gray-9)" }}>{n.created_by || "System"}</Text>
                            <Text size="1" style={{ color: "var(--gray-8)" }}>&middot;</Text>
                            <Text size="1" style={{ color: "var(--gray-9)" }}>{formatDate(n.created_at)}</Text>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ) : (
              <div className="flex-1 flex items-center justify-center">
                <Text size="2" style={{ color: "var(--gray-9)" }}>Notes not available for this entity type</Text>
              </div>
            )}
          </>
        )}
      </div>
    </>
  );
}
