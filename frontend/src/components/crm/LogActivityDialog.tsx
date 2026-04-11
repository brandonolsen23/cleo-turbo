/**
 * LogActivityDialog — modal form for logging a new activity on any entity.
 */
import { useState } from "react";
import { Button, Heading, Text, TextArea, TextField, Select } from "@radix-ui/themes";
import { X } from "@phosphor-icons/react";
import { postApi } from "../../api/client";
import type { ActivityEntityType } from "../../types";

const ACTIVITY_TYPES = [
  { value: "call", label: "Call" },
  { value: "email", label: "Email" },
  { value: "meeting", label: "Meeting" },
  { value: "note", label: "Note" },
];

const OUTCOMES: Record<string, { value: string; label: string }[]> = {
  call: [
    { value: "connected", label: "Connected" },
    { value: "voicemail", label: "Voicemail" },
    { value: "no_answer", label: "No Answer" },
  ],
  email: [{ value: "email_sent", label: "Email Sent" }],
  meeting: [{ value: "meeting_held", label: "Meeting Held" }],
  note: [],
};

interface LogActivityDialogProps {
  entityType: ActivityEntityType;
  entityId: string;
  onClose: () => void;
  onSaved: () => void;
}

export default function LogActivityDialog({
  entityType,
  entityId,
  onClose,
  onSaved,
}: LogActivityDialogProps) {
  const [activityType, setActivityType] = useState("call");
  const [outcome, setOutcome] = useState("");
  const [summary, setSummary] = useState("");
  const [nextStep, setNextStep] = useState("");
  const [saving, setSaving] = useState(false);

  const outcomes = OUTCOMES[activityType] || [];

  async function handleSave() {
    setSaving(true);
    try {
      await postApi("/activities", {
        entity_type: entityType,
        entity_id: entityId,
        activity_type: activityType,
        outcome: outcome || null,
        summary: summary || null,
        next_step: nextStep || null,
      });
      onSaved();
    } catch {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* backdrop */}
      <div
        className="absolute inset-0 bg-black/40"
        onClick={onClose}
      />
      {/* dialog */}
      <div
        className="relative bg-white rounded-xl border border-[var(--gray-6)] shadow-xl w-full max-w-md p-6 mx-4"
        style={{ backgroundColor: "var(--color-background)" }}
      >
        <div className="flex items-center justify-between mb-4">
          <Heading size="4">Log Activity</Heading>
          <button
            onClick={onClose}
            className="p-1 rounded hover:bg-[var(--gray-3)] transition-colors"
          >
            <X size={18} style={{ color: "var(--gray-9)" }} />
          </button>
        </div>

        <div className="space-y-4">
          {/* Activity Type */}
          <div>
            <Text size="2" weight="medium" className="block mb-1" style={{ color: "var(--gray-11)" }}>
              Type
            </Text>
            <Select.Root value={activityType} onValueChange={(v) => { setActivityType(v); setOutcome(""); }}>
              <Select.Trigger className="w-full" />
              <Select.Content>
                {ACTIVITY_TYPES.map((t) => (
                  <Select.Item key={t.value} value={t.value}>
                    {t.label}
                  </Select.Item>
                ))}
              </Select.Content>
            </Select.Root>
          </div>

          {/* Outcome */}
          {outcomes.length > 0 && (
            <div>
              <Text size="2" weight="medium" className="block mb-1" style={{ color: "var(--gray-11)" }}>
                Outcome
              </Text>
              <Select.Root value={outcome} onValueChange={setOutcome}>
                <Select.Trigger className="w-full" placeholder="Select outcome..." />
                <Select.Content>
                  {outcomes.map((o) => (
                    <Select.Item key={o.value} value={o.value}>
                      {o.label}
                    </Select.Item>
                  ))}
                </Select.Content>
              </Select.Root>
            </div>
          )}

          {/* Summary */}
          <div>
            <Text size="2" weight="medium" className="block mb-1" style={{ color: "var(--gray-11)" }}>
              Summary
            </Text>
            <TextArea
              value={summary}
              onChange={(e) => setSummary(e.target.value)}
              placeholder="What happened?"
              rows={3}
            />
          </div>

          {/* Next Step */}
          <div>
            <Text size="2" weight="medium" className="block mb-1" style={{ color: "var(--gray-11)" }}>
              Next Step
            </Text>
            <TextField.Root
              value={nextStep}
              onChange={(e) => setNextStep(e.target.value)}
              placeholder="Follow-up action..."
            />
          </div>
        </div>

        <div className="flex justify-end gap-2 mt-6">
          <Button variant="soft" color="gray" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={handleSave} disabled={saving}>
            {saving ? "Saving..." : "Log Activity"}
          </Button>
        </div>
      </div>
    </div>
  );
}
