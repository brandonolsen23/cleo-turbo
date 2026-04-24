import { Text, Badge } from "@radix-ui/themes";
import { formatDate } from "../../lib/utils";
import type { ExplorerPartySide } from "../../types";

interface PartySideCardProps {
  partySide: ExplorerPartySide;
  /**
   * Token being explored (used to label the "contains" note next to highlighted phrases).
   * When omitted, no contains-note is rendered and highlighting is still driven by
   * `brand_phrases[i].contains_token` from the backend.
   */
  highlightToken?: string;
}

export default function PartySideCard({ partySide: p, highlightToken }: PartySideCardProps) {
  const addrParts = [p.street_number, p.street_name, p.street_suffix].filter(Boolean);
  const addr = addrParts.length > 0 ? addrParts.join(" ") : "—";

  return (
    <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-4">
      <div className="flex items-baseline gap-3 flex-wrap mb-2">
        <Text size="2" className="font-mono" weight="medium">{p.source_id}</Text>
        <Badge size="1" variant="soft" color={p.side === "buyer" ? "jade" : "blue"}>
          {p.side}
        </Badge>
        <Text size="2" style={{ color: "var(--gray-9)" }}>
          {p.sale_date ? formatDate(p.sale_date) : "—"}
        </Text>
        <div className="flex-1" />
        <Text size="2" style={{ color: "var(--gray-9)" }}>
          {addr}
          {p.postal ? ` · ${p.postal}` : ""}
          {p.phone ? ` · ${p.phone}` : ""}
          {p.contact_fingerprint ? ` · ${p.contact_fingerprint}` : ""}
        </Text>
      </div>
      <div className="flex flex-col gap-1">
        {p.brand_phrases.length === 0 ? (
          <Text size="2" style={{ color: "var(--gray-9)" }}>
            (no brand phrases on this party-side)
          </Text>
        ) : p.brand_phrases.map((entry, i) => (
          <div key={i} className="flex items-center gap-2 text-[13px]">
            <Badge size="1" variant="soft" color="gray"
                   style={{ minWidth: 110, justifyContent: "center" }}>
              {entry.source_field}
            </Badge>
            <span className={entry.contains_token ? "font-mono font-semibold" : "font-mono"}
                  style={{
                    color: entry.contains_token ? "var(--jade-11)" : "var(--gray-12)",
                    background: entry.contains_token ? "var(--jade-3)" : "transparent",
                    padding: entry.contains_token ? "2px 6px" : undefined,
                    borderRadius: entry.contains_token ? 4 : undefined,
                  }}>
              {entry.phrase}
            </span>
            {entry.contains_token && highlightToken && (
              <Text size="1" style={{ color: "var(--jade-11)" }}>
                ← contains "{highlightToken}"
              </Text>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
