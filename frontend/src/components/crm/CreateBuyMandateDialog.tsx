/**
 * CreateBuyMandateDialog — quick dialog to create a buy mandate from a contact/group page.
 */
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button, Heading, Text, TextArea } from "@radix-ui/themes";
import { X } from "@phosphor-icons/react";
import { postApi } from "../../api/client";

interface CreateBuyMandateDialogProps {
  contactId?: string;
  groupId?: string;
  entityName: string;
  onClose: () => void;
}

export default function CreateBuyMandateDialog({
  contactId,
  groupId,
  entityName,
  onClose,
}: CreateBuyMandateDialogProps) {
  const navigate = useNavigate();
  const [notes, setNotes] = useState("");
  const [saving, setSaving] = useState(false);

  async function handleCreate() {
    setSaving(true);
    try {
      const result = await postApi<{ id: string }>("/buy-mandates", {
        contact_id: contactId || null,
        group_id: groupId || null,
        criteria: {},
        notes: notes || null,
      });
      navigate(`/opportunities/buy/${result.id}`);
    } catch {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div
        className="relative bg-white rounded-xl border border-[var(--gray-6)] shadow-xl w-full max-w-md p-6 mx-4"
        style={{ backgroundColor: "var(--color-background)" }}
      >
        <div className="flex items-center justify-between mb-4">
          <Heading size="4">Create Buy Mandate</Heading>
          <button
            onClick={onClose}
            className="p-1 rounded hover:bg-[var(--gray-3)] transition-colors"
          >
            <X size={18} style={{ color: "var(--gray-9)" }} />
          </button>
        </div>

        <Text size="2" className="block mb-4" style={{ color: "var(--gray-11)" }}>
          Buyer: {entityName}
        </Text>

        <Text size="1" className="block mb-4" style={{ color: "var(--gray-9)" }}>
          This creates a mandate with empty criteria. You can refine the search criteria on the mandate detail page.
        </Text>

        <div>
          <Text size="2" weight="medium" className="block mb-1" style={{ color: "var(--gray-11)" }}>
            Notes
          </Text>
          <TextArea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="What are they looking for?"
            rows={3}
          />
        </div>

        <div className="flex justify-end gap-2 mt-6">
          <Button variant="soft" color="gray" onClick={onClose}>Cancel</Button>
          <Button onClick={handleCreate} disabled={saving}>
            {saving ? "Creating..." : "Create Mandate"}
          </Button>
        </div>
      </div>
    </div>
  );
}
