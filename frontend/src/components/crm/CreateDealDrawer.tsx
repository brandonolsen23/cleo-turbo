import { useState } from "react";
import { Button, Heading, Select, Text, TextArea, TextField } from "@radix-ui/themes";
import { X } from "@phosphor-icons/react";
import { useNavigate } from "react-router-dom";
import { postApi } from "../../api/client";
import type { CrmEntityType } from "../../types";

interface CreateDealDrawerProps {
  entityType: CrmEntityType;
  entityId: string;
  entityName: string;
  ownerName?: string;
  onClose: () => void;
}

const STAGES = [
  "long_shot", "priority_deal", "mandate", "viable_deal",
  "in_negotiation", "under_contract", "firm",
];

export default function CreateDealDrawer({
  entityType,
  entityId,
  entityName,
  ownerName,
  onClose,
}: CreateDealDrawerProps) {
  const navigate = useNavigate();
  const [name, setName] = useState(`${entityName} — Deal`);
  const [stage, setStage] = useState("long_shot");
  const [amount, setAmount] = useState("");
  const [closeDate, setCloseDate] = useState("");
  const [priority, setPriority] = useState("");
  const [description, setDescription] = useState("");
  const [nextStep, setNextStep] = useState("");
  const [saving, setSaving] = useState(false);

  async function handleCreate() {
    if (!name.trim()) return;
    setSaving(true);
    try {
      const body: Record<string, unknown> = {
        name: name.trim(),
        stage,
        deal_owner: ownerName || null,
        amount: amount ? parseInt(amount, 10) : null,
        close_date: closeDate || null,
        priority: priority || null,
        description: description.trim() || null,
        next_step: nextStep.trim() || null,
      };
      if (entityType === "property") body.property_id = entityId;
      else if (entityType === "group") body.group_id = entityId;
      // Deals have no contact_id today; logging from a contact starts a deal without entity link
      const res = await postApi<{ id: string }>("/deals", body);
      navigate(`/deals/${res.id}`);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="relative ml-auto w-full max-w-md h-full overflow-y-auto bg-[var(--color-background)] border-l border-[var(--gray-6)] p-6">
        <div className="flex items-center justify-between mb-4">
          <Heading size="4">Create deal</Heading>
          <button onClick={onClose} className="p-1 rounded hover:bg-[var(--gray-3)]">
            <X size={18} />
          </button>
        </div>

        <div className="space-y-3">
          <Field label="Name">
            <TextField.Root value={name} onChange={(e) => setName(e.target.value)} />
          </Field>

          <Field label="Stage">
            <Select.Root value={stage} onValueChange={setStage}>
              <Select.Trigger className="w-full" />
              <Select.Content>
                {STAGES.map((s) => (
                  <Select.Item key={s} value={s}>{s.replace(/_/g, " ")}</Select.Item>
                ))}
              </Select.Content>
            </Select.Root>
          </Field>

          <Field label="Amount (CAD)">
            <TextField.Root
              type="number"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              placeholder="optional"
            />
          </Field>

          <Field label="Close date">
            <TextField.Root type="date" value={closeDate} onChange={(e) => setCloseDate(e.target.value)} />
          </Field>

          <Field label="Priority">
            <Select.Root value={priority || "none"} onValueChange={(v) => setPriority(v === "none" ? "" : v)}>
              <Select.Trigger className="w-full" placeholder="none" />
              <Select.Content>
                <Select.Item value="none">none</Select.Item>
                <Select.Item value="low">low</Select.Item>
                <Select.Item value="medium">medium</Select.Item>
                <Select.Item value="high">high</Select.Item>
              </Select.Content>
            </Select.Root>
          </Field>

          <Field label="Description">
            <TextArea value={description} onChange={(e) => setDescription(e.target.value)} rows={3} />
          </Field>

          <Field label="Next step">
            <TextField.Root value={nextStep} onChange={(e) => setNextStep(e.target.value)} />
          </Field>
        </div>

        <div className="flex justify-end gap-2 mt-6">
          <Button variant="soft" color="gray" onClick={onClose}>Cancel</Button>
          <Button onClick={handleCreate} disabled={saving || !name.trim()}>
            {saving ? "Creating..." : "Create deal"}
          </Button>
        </div>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <Text size="2" weight="medium" className="block mb-1" style={{ color: "var(--gray-11)" }}>
        {label}
      </Text>
      {children}
    </div>
  );
}
