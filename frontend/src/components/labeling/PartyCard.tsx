import { Heading, Badge, Text } from "@radix-ui/themes";
import { Link as LinkIcon } from "@phosphor-icons/react";
import type { LabelingPartyView, FieldType } from "../../types";

interface Props {
  view: LabelingPartyView;
  side: "left" | "right";
  sharedHighlights: string[];
}

interface Row {
  field_type: FieldType;
  value: string;
  role?: string | null;
}

function buildRows(view: LabelingPartyView): Row[] {
  const rows: Row[] = [];
  for (const p of view.party_rows) {
    if (p.party_name) rows.push({ field_type: "party_name", value: p.party_name });
  }
  if (view.trade_name) rows.push({ field_type: "trade_name", value: view.trade_name });
  if (view.care_of)    rows.push({ field_type: "care_of",    value: view.care_of });
  for (const v of view.companies_other) rows.push({ field_type: "company_other", value: v });
  for (const v of view.law_firms)       rows.push({ field_type: "law_firm", value: v });
  for (const c of view.contacts) if (c.name)
    rows.push({ field_type: "contact_name", value: c.name, role: c.role });
  if (view.mailing?.display) rows.push({ field_type: "address", value: view.mailing.display });
  for (const ph of view.phones) rows.push({ field_type: "phone", value: ph });
  return rows;
}

const FIELD_LABEL: Record<FieldType, string> = {
  party_name: "Party",
  trade_name: "Trade name",
  care_of: "Care of",
  company_other: "Company",
  law_firm: "Law firm",
  contact_name: "Contact",
  address: "Address",
  phone: "Phone",
};

export default function PartyCard({ view, side, sharedHighlights }: Props) {
  const rows = buildRows(view);
  const anchorSide = side === "left" ? "right" : "left"; // dot on the inner edge

  return (
    <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)]"
         style={{ background: "white" }}>
      <div className="px-4 py-2 border-b border-[var(--gray-4)] flex items-center justify-between">
        <Heading size="2">{view.source_id}</Heading>
        <Badge size="1" variant="soft" color={view.side === "buyer" ? "jade" : "amber"}>
          {view.side}
        </Badge>
      </div>
      <div className="flex flex-col">
        {rows.map((r, i) => {
          const key = `${side}:${r.field_type}:${r.value}:${i}`;
          const highlighted = sharedHighlights.includes(r.value);
          return (
            <div key={key}
                 className="relative flex items-center gap-2 px-4 py-2 border-b border-[var(--gray-3)]"
                 style={{ background: highlighted ? "var(--accent-2)" : "transparent" }}>
              <Text size="1" style={{ color: "var(--gray-9)", width: 90, flexShrink: 0 }}>
                {FIELD_LABEL[r.field_type]}
                {r.role ? <> · <i>{r.role}</i></> : null}
              </Text>
              <Text size="2" className="flex-1">{r.value}</Text>
              <button
                data-link-anchor="1"
                data-field-type={r.field_type}
                data-field-value={r.value}
                data-pane={side}
                className="w-3 h-3 rounded-full border border-[var(--accent-9)] hover:bg-[var(--accent-9)]"
                style={{
                  position: "absolute",
                  [anchorSide]: -6,
                  top: "50%",
                  transform: "translateY(-50%)",
                }}
                aria-label={`Link anchor for ${r.field_type}: ${r.value}`}
              >
                <LinkIcon size={8} weight="bold" style={{ opacity: 0 }} />
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}
