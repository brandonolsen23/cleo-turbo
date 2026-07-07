// Evidence tab for the Group Detail page — doctrine D4's front half.
//
// Shows WHY each member of an auto_group was grouped (shared mailing
// addresses, phones, contact names, SPV-name stems — each with a visible
// source tag per D8) and lets the user record one-tap confirm/reject
// verdicts at group level and per member. Verdicts are append-only history
// keyed to stable IDs; latest wins on read.

import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Badge, Button, Text } from "@radix-ui/themes";
import {
  Anchor,
  CheckCircle,
  Hash,
  MapPin,
  Phone,
  TextT,
  User,
  XCircle,
} from "@phosphor-icons/react";
import { fetchApi, postApi } from "../../api/client";
import { formatDate, formatPhone, titleCase } from "../../lib/utils";
import type {
  GroupEvidenceFact,
  GroupEvidenceMember,
  GroupEvidenceResponse,
  GroupVerdictRow,
} from "../../types";

const FACT_ICON: Record<GroupEvidenceFact["kind"], React.ReactNode> = {
  shared_address: <MapPin size={14} />,
  shared_phone: <Phone size={14} />,
  shared_contact: <User size={14} />,
  name_stem: <TextT size={14} />,
  numbered_corp_name: <Hash size={14} />,
};

function factValue(f: GroupEvidenceFact): string {
  if (f.kind === "shared_phone" && f.value) return formatPhone(f.value);
  if (f.kind === "shared_address" && f.value) return titleCase(f.value);
  if (f.kind === "shared_contact" && f.value) return titleCase(f.value);
  return f.value || "—";
}

function VerdictBadge({ v }: { v: GroupVerdictRow }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <Badge
        size="1"
        variant="solid"
        color={v.verdict === "confirm" ? "jade" : "red"}
      >
        {v.verdict === "confirm" ? "Confirmed" : "Rejected"}
      </Badge>
      <Text size="1" style={{ color: "var(--gray-9)" }}>
        {v.actor} · {formatDate(v.created_at)}
      </Text>
    </span>
  );
}

function VerdictButtons({
  verdict,
  busy,
  onVerdict,
  confirmLabel = "Confirm",
  rejectLabel = "Reject",
}: {
  verdict: GroupVerdictRow | null;
  busy: boolean;
  onVerdict: (v: "confirm" | "reject") => void;
  confirmLabel?: string;
  rejectLabel?: string;
}) {
  return (
    <div className="flex items-center gap-2">
      <Button
        size="1"
        variant={verdict?.verdict === "confirm" ? "solid" : "soft"}
        color="jade"
        disabled={busy}
        onClick={() => onVerdict("confirm")}
      >
        <CheckCircle size={13} weight="bold" />
        {confirmLabel}
      </Button>
      <Button
        size="1"
        variant={verdict?.verdict === "reject" ? "solid" : "soft"}
        color="red"
        disabled={busy}
        onClick={() => onVerdict("reject")}
      >
        <XCircle size={13} weight="bold" />
        {rejectLabel}
      </Button>
    </div>
  );
}

function FactRow({ fact }: { fact: GroupEvidenceFact }) {
  return (
    <div className="flex items-start gap-2 py-1">
      <span className="mt-0.5" style={{ color: "var(--gray-9)" }}>
        {FACT_ICON[fact.kind]}
      </span>
      <div className="flex-1 min-w-0">
        <span className="flex items-center gap-2 flex-wrap">
          <Text size="2" style={{ color: "var(--gray-12)" }}>
            {factValue(fact)}
          </Text>
          <Badge size="1" variant="soft" color="gray">
            {fact.source}
          </Badge>
          {fact.is_anchor && (
            <Badge size="1" variant="soft" color="jade">
              <Anchor size={11} /> anchor
            </Badge>
          )}
        </span>
        <Text size="1" className="block" style={{ color: "var(--gray-9)" }}>
          {fact.detail}
        </Text>
      </div>
    </div>
  );
}

function MemberCard({
  member,
  busy,
  onVerdict,
}: {
  member: GroupEvidenceMember;
  busy: boolean;
  onVerdict: (ref: string, v: "confirm" | "reject") => void;
}) {
  const name =
    member.display_name?.trim() ||
    member.corp_name ||
    (member.source_id ? `${member.source_id} (unnamed party)` : "Unnamed member");

  return (
    <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-4">
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <Text size="2" weight="medium" style={{ color: "var(--gray-12)" }}>
              {titleCase(name)}
            </Text>
            {member.member_type === "numbered_corp" ? (
              <Badge size="1" variant="soft" color="amber">
                numbered corp
              </Badge>
            ) : (
              <Badge
                size="1"
                variant="soft"
                color={member.side === "buyer" ? "blue" : "gray"}
              >
                {member.side}
              </Badge>
            )}
            {member.source_id && (
              <Link
                to={`/transactions/${member.source_id}`}
                className="no-underline text-[12px]"
                style={{ color: "var(--accent-11)" }}
              >
                {member.source_id}
              </Link>
            )}
            {member.sale_date && (
              <Text size="1" style={{ color: "var(--gray-9)" }}>
                {formatDate(member.sale_date)}
              </Text>
            )}
          </div>
          {member.transaction_address && (
            <Text size="1" className="block mt-0.5" style={{ color: "var(--gray-9)" }}>
              Property: {titleCase(member.transaction_address)}
              {member.transaction_city ? `, ${titleCase(member.transaction_city)}` : ""}
            </Text>
          )}
        </div>
        <div className="flex flex-col items-end gap-1.5 shrink-0">
          <VerdictButtons
            verdict={member.verdict}
            busy={busy}
            onVerdict={(v) => onVerdict(member.member_ref, v)}
          />
          {member.verdict && <VerdictBadge v={member.verdict} />}
        </div>
      </div>

      <div className="mt-2 border-t border-[var(--gray-4)] pt-2">
        {member.facts.length === 0 ? (
          <Text size="1" style={{ color: "var(--gray-9)", fontStyle: "italic" }}>
            No shared evidence found for this member.
          </Text>
        ) : (
          member.facts.map((f, i) => <FactRow key={`${f.kind}-${f.raw_value}-${i}`} fact={f} />)
        )}
      </div>
    </div>
  );
}

export default function EvidenceTab({ groupId }: { groupId: string }) {
  const [data, setData] = useState<GroupEvidenceResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyRef, setBusyRef] = useState<string | null>(null);

  const reload = useCallback(() => {
    setError(null);
    fetchApi<GroupEvidenceResponse>(`/groups/${groupId}/evidence`)
      .then(setData)
      .catch((e) => setError(e?.message || "Failed to load evidence"));
  }, [groupId]);

  useEffect(() => {
    reload();
  }, [reload]);

  const submitVerdict = async (
    scope: "group" | "member",
    memberRef: string | null,
    verdict: "confirm" | "reject",
  ) => {
    const busyKey = scope === "group" ? "__group__" : memberRef!;
    setBusyRef(busyKey);
    try {
      const row = await postApi<GroupVerdictRow>(`/groups/${groupId}/verdict`, {
        scope,
        member_ref: memberRef,
        verdict,
      });
      setData((prev) => {
        if (!prev) return prev;
        if (scope === "group") return { ...prev, group_verdict: row };
        return {
          ...prev,
          members: prev.members.map((m) =>
            m.member_ref === memberRef ? { ...m, verdict: row } : m,
          ),
        };
      });
    } catch (e) {
      setError((e as Error)?.message || "Failed to record verdict");
    } finally {
      setBusyRef(null);
    }
  };

  if (error && !data) {
    return <Text size="2" style={{ color: "var(--red-11)" }}>{error}</Text>;
  }
  if (!data) {
    return <Text size="2" style={{ color: "var(--gray-9)" }}>Loading…</Text>;
  }

  return (
    <div className="flex flex-col gap-4">
      {/* Group-level verdict control */}
      <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-4 flex items-start justify-between gap-4">
        <div>
          <Text size="2" weight="medium" style={{ color: "var(--gray-12)" }}>
            Is this grouping right?
          </Text>
          <Text size="1" className="block mt-0.5" style={{ color: "var(--gray-9)" }}>
            Grouped on stem &lsquo;{data.canonical_stem}&rsquo; · {data.anchors.length} seeding
            anchor{data.anchors.length !== 1 ? "s" : ""} · verdicts accumulate as ground
            truth for algorithm scoring
          </Text>
          {data.anchors.length > 0 && (
            <div className="flex items-center gap-1.5 flex-wrap mt-2">
              {data.anchors.map((a) => (
                <Badge key={`${a.anchor_type}:${a.anchor_value}`} size="1" variant="soft" color="jade">
                  <Anchor size={11} />
                  {a.anchor_type === "phone" ? formatPhone(a.display_value) : titleCase(a.display_value)}
                </Badge>
              ))}
            </div>
          )}
        </div>
        <div className="flex flex-col items-end gap-1.5 shrink-0">
          <VerdictButtons
            verdict={data.group_verdict}
            busy={busyRef === "__group__"}
            onVerdict={(v) => submitVerdict("group", null, v)}
            confirmLabel="Grouping looks right"
            rejectLabel="Grouping looks wrong"
          />
          {data.group_verdict && <VerdictBadge v={data.group_verdict} />}
        </div>
      </div>

      {error && (
        <Text size="1" style={{ color: "var(--red-11)" }}>{error}</Text>
      )}

      {/* Member list */}
      <div className="flex items-center justify-between">
        <Text size="1" style={{ color: "var(--gray-9)" }}>
          {data.shown_members === data.total_members
            ? `${data.total_members.toLocaleString()} members`
            : `Showing ${data.shown_members.toLocaleString()} of ${data.total_members.toLocaleString()} members`}
        </Text>
      </div>
      {data.members.length === 0 ? (
        <Text size="2" style={{ color: "var(--gray-9)" }}>No members.</Text>
      ) : (
        <div className="flex flex-col gap-3">
          {data.members.map((m) => (
            <MemberCard
              key={m.member_ref}
              member={m}
              busy={busyRef === m.member_ref}
              onVerdict={(ref, v) => submitVerdict("member", ref, v)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
