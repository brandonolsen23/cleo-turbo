import { Badge, Heading, Text } from "@radix-ui/themes";
import { CheckCircle, XCircle } from "@phosphor-icons/react";
import type { LabelingCandidate, LabelingVerdict, LabelingPartyView } from "../../types";

interface Props {
  candidates: LabelingCandidate[];
  verdicts: LabelingVerdict[];
  currentRight: LabelingPartyView | null;
  onPick: (c: LabelingCandidate) => void;
}

function verdictFor(v: LabelingVerdict[], c: LabelingCandidate) {
  return v.find((x) => x.source_id === c.source_id && x.side === c.side);
}

export default function CandidateListPanel({ candidates, verdicts, currentRight, onPick }: Props) {
  const sorted = [...candidates].sort((a, b) => {
    const va = verdictFor(verdicts, a);
    const vb = verdictFor(verdicts, b);
    if (!!va === !!vb) return 0;
    return va ? 1 : -1;
  });

  return (
    <div className="p-3 text-[13px]">
      <Heading size="1" mb="2">Candidates ({candidates.length})</Heading>
      <div className="flex flex-col gap-1">
        {sorted.map((c) => {
          const v = verdictFor(verdicts, c);
          const isCurrent = currentRight &&
            currentRight.source_id === c.source_id && currentRight.side === c.side;
          return (
            <button key={`${c.source_id}:${c.side}`}
                    onClick={() => onPick(c)}
                    className="text-left px-2 py-1 rounded hover:bg-[var(--accent-2)]"
                    style={{
                      background: isCurrent ? "var(--accent-2)" : undefined,
                      opacity: v ? 0.6 : 1,
                    }}>
              <div className="flex items-center gap-1">
                {v?.verdict === "confirmed" && (
                  <CheckCircle size={12} weight="fill" style={{ color: "var(--jade-10)" }} />
                )}
                {v?.verdict === "rejected" && (
                  <XCircle size={12} weight="fill" style={{ color: "var(--tomato-10)" }} />
                )}
                <Text size="1">{c.source_id}</Text>
                <Badge size="1" variant="soft" color={c.side === "buyer" ? "jade" : "amber"}>
                  {c.side}
                </Badge>
              </div>
              <Text size="1" style={{ color: "var(--gray-9)" }}>
                {c.match_fields.join(", ")}
              </Text>
            </button>
          );
        })}
      </div>
    </div>
  );
}
