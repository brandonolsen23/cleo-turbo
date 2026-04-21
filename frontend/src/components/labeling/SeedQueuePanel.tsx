import { Badge, Heading, TextField, Button } from "@radix-ui/themes";
import { useState } from "react";
import { MagnifyingGlass, CheckCircle, XCircle } from "@phosphor-icons/react";
import { postApi } from "../../api/client";
import type { LabelingSeed, LabelingVerdict, FieldType } from "../../types";

interface Props {
  sessionId: string;
  seeds: LabelingSeed[];
  verdicts: LabelingVerdict[];
  currentSeedId?: number;
  onRunSeed: (s: LabelingSeed) => void;
  onReopenVerdict?: (v: LabelingVerdict) => void;
}

const FIELD_COLORS: Record<FieldType, string> = {
  party_name: "jade", trade_name: "blue", care_of: "cyan",
  company_other: "indigo", law_firm: "plum", contact_name: "orange",
  address: "amber", phone: "tomato",
};

export default function SeedQueuePanel({
  sessionId, seeds, verdicts, currentSeedId, onRunSeed, onReopenVerdict,
}: Props) {
  const [newTerm, setNewTerm] = useState("");
  const [newType, setNewType] = useState<FieldType>("party_name");

  const pending = seeds.filter((s) => s.state === "pending");
  const inProgress = seeds.filter((s) => s.state === "in_progress");
  const done = seeds.filter((s) => s.state === "done");
  const skipped = seeds.filter((s) => s.state === "skipped");

  const confirmedParties = verdicts.filter((v) => v.verdict === "confirmed");
  const rejectedParties = verdicts.filter((v) => v.verdict === "rejected");

  async function addSeed() {
    if (!newTerm.trim()) return;
    await postApi(`/labeling/sessions/${sessionId}/seeds`,
                  { term: newTerm, field_type: newType });
    setNewTerm("");
    // Parent will reload on next loop.
  }

  return (
    <div className="p-3 flex flex-col gap-4 text-[13px]">
      <div>
        <Heading size="1" mb="1">Ad-hoc search</Heading>
        <div className="flex flex-col gap-1">
          <TextField.Root size="1" placeholder="Search term"
                          value={newTerm} onChange={(e) => setNewTerm(e.target.value)}>
            <TextField.Slot><MagnifyingGlass size={12} /></TextField.Slot>
          </TextField.Root>
          <select value={newType} onChange={(e) => setNewType(e.target.value as FieldType)}
                  className="px-2 py-1 text-[12px] rounded border border-[var(--gray-6)]">
            {Object.keys(FIELD_COLORS).map((ft) => <option key={ft} value={ft}>{ft}</option>)}
          </select>
          <Button size="1" variant="soft" onClick={addSeed}>Add seed</Button>
        </div>
      </div>

      <SeedGroup label={`Pending (${pending.length})`} seeds={pending}
                 currentSeedId={currentSeedId} onRunSeed={onRunSeed} />
      {inProgress.length > 0 && (
        <SeedGroup label={`In progress (${inProgress.length})`} seeds={inProgress}
                   currentSeedId={currentSeedId} onRunSeed={onRunSeed} />
      )}
      {done.length > 0 && (
        <SeedGroup label={`Done (${done.length})`} seeds={done}
                   currentSeedId={currentSeedId} onRunSeed={onRunSeed} />
      )}
      {skipped.length > 0 && (
        <SeedGroup label={`Skipped (${skipped.length})`} seeds={skipped}
                   currentSeedId={currentSeedId} onRunSeed={onRunSeed} />
      )}

      <div>
        <Heading size="1" mb="1">Confirmed ({confirmedParties.length})</Heading>
        <div className="flex flex-col gap-1">
          {confirmedParties.map((v) => (
            <button
              key={v.id}
              onClick={() => onReopenVerdict?.(v)}
              disabled={!onReopenVerdict}
              title={onReopenVerdict ? "Click to reopen — deletes the verdict and reloads the pair for re-review" : undefined}
              className={`flex items-center gap-1 text-[12px] text-left px-1 py-0.5 rounded ${
                onReopenVerdict ? "hover:bg-[var(--accent-2)] cursor-pointer" : "cursor-default"
              }`}
            >
              <CheckCircle size={12} weight="fill" style={{ color: "var(--jade-10)" }} />
              {v.source_id}/{v.side}
            </button>
          ))}
        </div>
      </div>

      {rejectedParties.length > 0 && (
        <div>
          <Heading size="1" mb="1">Rejected ({rejectedParties.length})</Heading>
          <div className="flex flex-col gap-1">
            {rejectedParties.map((v) => (
              <button
                key={v.id}
                onClick={() => onReopenVerdict?.(v)}
                disabled={!onReopenVerdict}
                title={onReopenVerdict ? "Click to reopen — deletes the verdict and reloads the pair for re-review" : undefined}
                className={`flex items-center gap-1 text-[12px] text-left px-1 py-0.5 rounded ${
                  onReopenVerdict ? "hover:bg-[var(--accent-2)] cursor-pointer" : "cursor-default"
                }`}
              >
                <XCircle size={12} weight="fill" style={{ color: "var(--tomato-10)" }} />
                {v.source_id}/{v.side}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function SeedGroup({ label, seeds, currentSeedId, onRunSeed }: {
  label: string; seeds: LabelingSeed[]; currentSeedId?: number;
  onRunSeed: (s: LabelingSeed) => void;
}) {
  return (
    <div>
      <Heading size="1" mb="1">{label}</Heading>
      <div className="flex flex-col gap-1">
        {seeds.map((s) => (
          <button key={s.id}
                  onClick={() => onRunSeed(s)}
                  className="text-left px-2 py-1 rounded hover:bg-[var(--accent-2)] border border-transparent"
                  style={{
                    borderColor: currentSeedId === s.id ? "var(--accent-9)" : "transparent",
                    background: currentSeedId === s.id ? "var(--accent-2)" : undefined,
                  }}>
            <Badge size="1" variant="soft" color={FIELD_COLORS[s.field_type] as any}>
              {s.field_type}
            </Badge>{" "}
            <span className="text-[12px]">{s.term}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
