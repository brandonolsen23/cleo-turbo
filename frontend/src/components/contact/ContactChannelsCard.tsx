import { useEffect, useState } from "react";
import { Text, Badge, Button, TextField } from "@radix-ui/themes";
import { Plus, Lightning } from "@phosphor-icons/react";
import { fetchApi, postApi, mutateApi } from "../../api/client";
import { formatPhone } from "../../lib/utils";
import type { ContactChannel, ContactChannels, TenureTag } from "../../types";

/** Channels card — a contact's phones + emails as a collection with verdicts.
 *  Best-ranked value is bolded; wrong_number/bounced/dead stay visible (so a
 *  burned number isn't re-dialed) but never rank best. Clicking a status pill
 *  cycles the verdict (Cleo-mastered). Manual add appends source=manual rows. */

type Kind = "phone" | "email";

// Verdict cycle order per kind (clicking the pill advances to the next).
const CYCLE: Record<Kind, ContactChannel["status"][]> = {
  phone: ["unverified", "verified_good", "wrong_number", "dead"],
  email: ["unverified", "verified_good", "bounced", "dead"],
};

const STATUS_LABEL: Record<ContactChannel["status"], string> = {
  unverified: "Unverified",
  verified_good: "Verified",
  wrong_number: "Wrong #",
  bounced: "Bounced",
  dead: "Dead",
};

const STATUS_COLOR: Record<ContactChannel["status"], "jade" | "gray" | "orange" | "red"> = {
  unverified: "gray",
  verified_good: "jade",
  wrong_number: "orange",
  bounced: "orange",
  dead: "red",
};

function nextStatus(kind: Kind, current: ContactChannel["status"]): ContactChannel["status"] {
  const cycle = CYCLE[kind];
  const i = cycle.indexOf(current);
  return cycle[(i + 1) % cycle.length];
}

// Source badge — Datanyze keeps its amber + lightning cue from the old card.
const SOURCE_COLOR: Record<string, "gray" | "amber" | "blue"> = {
  datanyze: "amber",
  hubspot: "blue",
};

export default function ContactChannelsCard({ contactId, tenureTag }: {
  contactId: string;
  /** RT phone tenure context ("Active · GroupName since 2019"), shown under phones. */
  tenureTag?: TenureTag | null;
}) {
  const [channels, setChannels] = useState<ContactChannels | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [addKind, setAddKind] = useState<Kind | null>(null);
  const [addValue, setAddValue] = useState("");
  const [addError, setAddError] = useState<string | null>(null);

  const load = () => {
    fetchApi<ContactChannels>(`/contacts/${contactId}/channels`)
      .then(setChannels)
      .catch(() => setChannels({ phones: [], emails: [] }));
  };
  useEffect(load, [contactId]);

  const cycleStatus = async (kind: Kind, ch: ContactChannel) => {
    setBusyId(ch.id);
    try {
      await mutateApi(`/contacts/${contactId}/channels/${ch.id}`, "PATCH", {
        kind,
        status: nextStatus(kind, ch.status),
      });
      load();
    } finally {
      setBusyId(null);
    }
  };

  const submitAdd = async (kind: Kind) => {
    const value = addValue.trim();
    if (!value) return;
    setAddError(null);
    try {
      await postApi(`/contacts/${contactId}/channels`, { kind, value });
      setAddValue("");
      setAddKind(null);
      load();
    } catch {
      setAddError(`Not a usable ${kind}`);
    }
  };

  if (!channels) return null;

  const renderRow = (kind: Kind, ch: ContactChannel) => {
    const display = ch.value_raw || ch.value;
    const href = kind === "phone" ? `tel:${ch.value}` : `mailto:${ch.value}`;
    const shown = kind === "phone" ? formatPhone(display) : display;
    return (
      <div key={ch.id} className="flex items-center gap-2 flex-wrap">
        <a
          href={href}
          className="no-underline"
          style={{
            color: "var(--accent-11)",
            fontWeight: ch.is_best ? 700 : 400,
          }}
        >
          {shown}
        </a>
        {ch.label && (
          <Text size="1" style={{ color: "var(--gray-9)" }}>· {ch.label}</Text>
        )}
        <Badge size="1" variant="soft" color={SOURCE_COLOR[ch.source] ?? "gray"}>
          {ch.source === "datanyze" && <Lightning size={10} weight="fill" />}
          {ch.source}
        </Badge>
        <button
          type="button"
          onClick={() => cycleStatus(kind, ch)}
          disabled={busyId === ch.id}
          title="Click to change verdict"
          className="cursor-pointer bg-transparent border-0 p-0"
        >
          <Badge size="1" variant="soft" color={STATUS_COLOR[ch.status]}>
            {STATUS_LABEL[ch.status]}
          </Badge>
        </button>
      </div>
    );
  };

  const section = (kind: Kind, label: string, rows: ContactChannel[]) => (
    <div>
      <div className="flex items-center justify-between">
        <Text size="1" style={{ color: "var(--gray-9)" }}>{label}</Text>
        <Button
          size="1"
          variant="ghost"
          onClick={() => { setAddKind(addKind === kind ? null : kind); setAddValue(""); setAddError(null); }}
        >
          <Plus size={12} /> Add
        </Button>
      </div>
      {rows.length === 0 ? (
        <Text size="2" className="block">—</Text>
      ) : (
        <div className="flex flex-col gap-1 mt-1">{rows.map((r) => renderRow(kind, r))}</div>
      )}
      {kind === "phone" && tenureTag && (
        <Badge
          size="1"
          variant="soft"
          color={tenureTag.state === "active" ? "jade" : "gray"}
          className="self-start mt-1"
        >
          {tenureTag.state === "active"
            ? `Active · ${tenureTag.display_name} since ${(tenureTag.since || "").slice(0, 4)}`
            : `Last seen ${(tenureTag.last_seen || "").slice(0, 10)}${tenureTag.display_name ? ` · ${tenureTag.display_name} era` : ""}`}
        </Badge>
      )}
      {addKind === kind && (
        <div className="mt-2 flex items-center gap-2">
          <TextField.Root
            size="1"
            className="flex-1"
            placeholder={kind === "phone" ? "Add phone number" : "Add email address"}
            value={addValue}
            onChange={(e: any) => setAddValue(e.target.value)}
            onKeyDown={(e: any) => { if (e.key === "Enter") submitAdd(kind); }}
            autoFocus
          />
          <Button size="1" onClick={() => submitAdd(kind)}>Add</Button>
        </div>
      )}
      {addKind === kind && addError && (
        <Text size="1" className="block mt-1" style={{ color: "var(--red-11)" }}>{addError}</Text>
      )}
    </div>
  );

  return (
    <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
      <Text size="3" weight="medium" className="mb-3 block">Channels</Text>
      <div className="flex flex-col gap-4 text-[14px]">
        {section("phone", "Phones", channels.phones)}
        {section("email", "Emails", channels.emails)}
      </div>
    </div>
  );
}
