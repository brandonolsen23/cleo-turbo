import { Link } from "react-router-dom";
import { Heading, Text, Badge } from "@radix-ui/themes";
import type { NgramContainmentEntry } from "../../types";

interface NgramContainmentProps {
  contains: NgramContainmentEntry[];
  extended_by: NgramContainmentEntry[];
}

function detailHref(entry: NgramContainmentEntry): string {
  // 1gram → /explorer/brands/1gram/:token
  // 2gram → /explorer/brands/2gram/:bigram (etc.)
  // long-form → /explorer/brands/long-form/:phrase
  const path = entry.level === "long-form" ? "long-form" : entry.level;
  return `/explorer/brands/${path}/${encodeURIComponent(entry.value)}`;
}

function levelLabel(level: NgramContainmentEntry["level"]): string {
  const map: Record<typeof level, string> = {
    "1gram": "1g",
    "2gram": "2g",
    "3gram": "3g",
    "4gram": "4g",
    "5gram": "5g",
    "long-form": "6+",
  };
  return map[level];
}

function EntryRow({ entry }: { entry: NgramContainmentEntry }) {
  return (
    <Link to={detailHref(entry)} className="no-underline">
      <div className="flex items-center gap-2 px-3 py-2 hover:bg-[var(--gray-2)] rounded text-[13px]">
        <Badge size="1" variant="soft" color="gray" style={{ minWidth: 32, justifyContent: "center" }}>
          {levelLabel(entry.level)}
        </Badge>
        <span className="font-mono" style={{ color: "var(--accent-11)" }}>
          {entry.value}
        </span>
        <div className="flex-1" />
        <Text size="1" style={{ color: "var(--gray-9)" }}>
          {entry.n_party_sides.toLocaleString()} sides
        </Text>
      </div>
    </Link>
  );
}

export default function NgramContainment({ contains, extended_by }: NgramContainmentProps) {
  // Render nothing if both arrays are empty (e.g., a hypothetical isolated row)
  if (contains.length === 0 && extended_by.length === 0) return null;

  return (
    <div className="grid grid-cols-2 gap-4 mt-6">
      <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] overflow-hidden">
        <div className="px-3 py-2 border-b border-[var(--gray-4)]"
             style={{ background: "var(--gray-2)" }}>
          <Heading size="3">Contains</Heading>
          <Text size="1" style={{ color: "var(--gray-9)" }}>
            shorter n-grams that make up this one
          </Text>
        </div>
        <div className="flex flex-col py-1">
          {contains.length === 0 ? (
            <div className="px-3 py-3 text-[13px]" style={{ color: "var(--gray-9)" }}>
              (no shorter level)
            </div>
          ) : contains.map((e, i) => <EntryRow key={`${e.level}-${e.value}-${i}`} entry={e} />)}
        </div>
      </div>

      <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] overflow-hidden">
        <div className="px-3 py-2 border-b border-[var(--gray-4)]"
             style={{ background: "var(--gray-2)" }}>
          <Heading size="3">Extended by</Heading>
          <Text size="1" style={{ color: "var(--gray-9)" }}>
            longer n-grams that contain this one
          </Text>
        </div>
        <div className="flex flex-col py-1 max-h-96 overflow-y-auto">
          {extended_by.length === 0 ? (
            <div className="px-3 py-3 text-[13px]" style={{ color: "var(--gray-9)" }}>
              (no longer level)
            </div>
          ) : extended_by.map((e, i) => <EntryRow key={`${e.level}-${e.value}-${i}`} entry={e} />)}
        </div>
      </div>
    </div>
  );
}
