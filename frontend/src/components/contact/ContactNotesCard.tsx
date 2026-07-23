import { useEffect, useState } from "react";
import { Text, Badge, Button, TextArea } from "@radix-ui/themes";
import { fetchApi, postApi } from "../../api/client";
import { formatDate } from "../../lib/utils";
import type { ContactNote } from "../../types";

/** Notes / dossier section — renders existing contact_notes with an add box.
 *  Every note carries a source badge; in Phase 1 step 1 all notes are manual
 *  (the HubSpot import that adds source=hubspot notes is step 2). */
export default function ContactNotesCard({ contactId }: { contactId: string }) {
  const [notes, setNotes] = useState<ContactNote[] | null>(null);
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);

  const load = () => {
    fetchApi<ContactNote[]>(`/notes/contacts/${contactId}/notes`)
      .then(setNotes)
      .catch(() => setNotes([]));
  };
  useEffect(load, [contactId]);

  const addNote = async () => {
    const note = draft.trim();
    if (!note) return;
    setSaving(true);
    try {
      await postApi(`/notes/contacts/${contactId}/notes`, { note });
      setDraft("");
      load();
    } finally {
      setSaving(false);
    }
  };

  if (!notes) return null;

  return (
    <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
      <Text size="3" weight="medium" className="mb-3 block">Notes</Text>

      <div className="flex flex-col gap-2">
        <TextArea
          size="1"
          placeholder="Add a note…"
          value={draft}
          onChange={(e: any) => setDraft(e.target.value)}
        />
        <div className="flex justify-end">
          <Button size="1" onClick={addNote} disabled={saving || !draft.trim()}>Add note</Button>
        </div>
      </div>

      {notes.length === 0 ? (
        <Text size="2" className="block mt-3" style={{ color: "var(--gray-9)" }}>No notes yet.</Text>
      ) : (
        <div className="flex flex-col gap-3 mt-3">
          {notes.map((n) => (
            <div key={n.id} className="border-t border-[var(--gray-4)] pt-3 first:border-t-0 first:pt-0">
              <div className="flex items-center gap-2 mb-1">
                <Badge size="1" variant="soft" color="gray">manual</Badge>
                <Text size="1" style={{ color: "var(--gray-9)" }}>
                  {n.created_by ? `${n.created_by} · ` : ""}{formatDate(n.created_at)}
                </Text>
              </div>
              <Text size="2" className="block whitespace-pre-wrap">{n.note}</Text>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
