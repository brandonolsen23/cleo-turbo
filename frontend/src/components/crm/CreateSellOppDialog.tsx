/**
 * CreateSellOppDialog — quick dialog to create a sell opportunity from a property page.
 */
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button, Heading, Text, TextField, TextArea } from "@radix-ui/themes";
import { X } from "@phosphor-icons/react";
import { postApi } from "../../api/client";

interface CreateSellOppDialogProps {
  propertyId: string;
  propertyAddress: string;
  onClose: () => void;
}

export default function CreateSellOppDialog({
  propertyId,
  propertyAddress,
  onClose,
}: CreateSellOppDialogProps) {
  const navigate = useNavigate();
  const [dealValue, setDealValue] = useState("");
  const [notes, setNotes] = useState("");
  const [saving, setSaving] = useState(false);

  async function handleCreate() {
    setSaving(true);
    try {
      const result = await postApi<{ id: string }>("/sell-opportunities", {
        property_id: propertyId,
        deal_value: dealValue ? parseInt(dealValue) : null,
        notes: notes || null,
      });
      navigate(`/opportunities/sell/${result.id}`);
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
          <Heading size="4">Create Sell Opportunity</Heading>
          <button
            onClick={onClose}
            className="p-1 rounded hover:bg-[var(--gray-3)] transition-colors"
          >
            <X size={18} style={{ color: "var(--gray-9)" }} />
          </button>
        </div>

        <Text size="2" className="block mb-4" style={{ color: "var(--gray-11)" }}>
          {propertyAddress}
        </Text>

        <div className="space-y-4">
          <div>
            <Text size="2" weight="medium" className="block mb-1" style={{ color: "var(--gray-11)" }}>
              Deal Value (CAD)
            </Text>
            <TextField.Root
              value={dealValue}
              onChange={(e) => setDealValue(e.target.value)}
              placeholder="e.g. 5000000"
              type="number"
            />
          </div>
          <div>
            <Text size="2" weight="medium" className="block mb-1" style={{ color: "var(--gray-11)" }}>
              Notes
            </Text>
            <TextArea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Any notes about this opportunity..."
              rows={3}
            />
          </div>
        </div>

        <div className="flex justify-end gap-2 mt-6">
          <Button variant="soft" color="gray" onClick={onClose}>Cancel</Button>
          <Button onClick={handleCreate} disabled={saving}>
            {saving ? "Creating..." : "Create"}
          </Button>
        </div>
      </div>
    </div>
  );
}
