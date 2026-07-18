/**
 * Ownership Intelligence M1 — Story + Facts + GW Worklist for a group page.
 *
 * Renders group_profile.narrative_md as markdown ("Story"), the committed
 * group_facts grouped by field with source badges / confidence / effective
 * dates (doctrine D8: provenance always displayed), and gw_worklist_item
 * facts as their own ranked list.
 */
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Heading, Text, Badge } from "@radix-ui/themes";
import { ArrowSquareOut, BookOpenText, ListChecks } from "@phosphor-icons/react";
import type { GroupFact } from "../../types";

const SOURCE_COLOR: Record<
  GroupFact["source"],
  "jade" | "blue" | "cyan" | "purple" | "amber" | "gray"
> = {
  human: "jade",
  rt: "blue",
  gw: "purple",
  web: "cyan",
  site_scrape: "cyan",
  inference: "amber",
};

const FIELD_LABEL: Record<GroupFact["field"], string> = {
  hq_address: "HQ Address",
  phone: "Phone",
  principal: "Principals",
  entity_alias: "Entity Aliases",
  founded: "Founded",
  aum_estimate: "AUM Estimate",
  behavior: "Behavior",
  origin_story: "Origin Story",
  website: "Website",
  sector_focus: "Sector Focus",
  gw_worklist_item: "GW Worklist",
  other: "Other",
};

const FIELD_ORDER: GroupFact["field"][] = [
  "hq_address", "phone", "website", "founded", "principal", "entity_alias",
  "aum_estimate", "sector_focus", "behavior", "origin_story", "other",
];

function effectiveRange(f: GroupFact): string | null {
  const from = f.effective_from ? f.effective_from.slice(0, 4) : null;
  const to = f.effective_to ? f.effective_to.slice(0, 4) : null;
  if (!from && !to) return null;
  return `${from ?? "…"}–${to ?? "present"}`;
}

function SourceBadge({ fact }: { fact: GroupFact }) {
  const badge = (
    <Badge size="1" color={SOURCE_COLOR[fact.source] || "gray"} variant="soft">
      {fact.source}
    </Badge>
  );
  if (!fact.source_url) return badge;
  const href = fact.source_url.startsWith("http")
    ? fact.source_url
    : `https://${fact.source_url}`;
  return (
    <a href={href} target="_blank" rel="noreferrer" className="no-underline inline-flex items-center gap-0.5">
      {badge}
      <ArrowSquareOut size={11} style={{ color: "var(--gray-9)" }} />
    </a>
  );
}

function FactRow({ fact }: { fact: GroupFact }) {
  const range = effectiveRange(fact);
  const vj = (typeof fact.value_json === "object" && fact.value_json) || null;
  const role = vj && typeof vj["role"] === "string" ? (vj["role"] as string) : null;
  return (
    <div className="flex items-start justify-between gap-3 py-1.5">
      <div className="flex-1 min-w-0">
        <Text size="2" style={{ color: "var(--gray-12)" }}>
          {fact.value}
          {role && (
            <Text size="1" style={{ color: "var(--gray-9)" }}> — {role}</Text>
          )}
        </Text>
        {range && (
          <Text size="1" className="block" style={{ color: "var(--gray-9)" }}>
            {range}
          </Text>
        )}
      </div>
      <div className="flex items-center gap-1.5 shrink-0">
        {fact.confidence != null && (
          <Text size="1" style={{ color: "var(--gray-9)" }}>
            {Math.round(fact.confidence * 100)}%
          </Text>
        )}
        <SourceBadge fact={fact} />
      </div>
    </div>
  );
}

export function FactsPanel({ facts }: { facts: GroupFact[] }) {
  const nonWorklist = facts.filter((f) => f.field !== "gw_worklist_item");
  if (nonWorklist.length === 0) return null;
  const grouped = FIELD_ORDER
    .map((field) => ({ field, rows: nonWorklist.filter((f) => f.field === field) }))
    .filter((g) => g.rows.length > 0);
  return (
    <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
      <Heading size="4" weight="medium">Facts</Heading>
      <div className="mt-2 flex flex-col gap-3">
        {grouped.map(({ field, rows }) => (
          <div key={field}>
            <Text size="1" weight="medium" className="uppercase tracking-wide" style={{ color: "var(--gray-9)" }}>
              {FIELD_LABEL[field]}
            </Text>
            <div className="divide-y divide-[var(--gray-4)]">
              {rows.map((f) => <FactRow key={f.id} fact={f} />)}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function StoryCard({ narrativeMd }: { narrativeMd: string }) {
  return (
    <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
      <div className="flex items-center gap-2">
        <BookOpenText size={16} style={{ color: "var(--gray-9)" }} />
        <Heading size="4" weight="medium">Story</Heading>
      </div>
      <div className="mt-2 text-[14px] leading-relaxed [&_h1]:text-[16px] [&_h2]:text-[15px] [&_h2]:font-medium [&_h2]:mt-3 [&_h2]:mb-1 [&_h3]:text-[14px] [&_h3]:font-medium [&_h3]:mt-2 [&_p]:my-1.5 [&_ul]:list-disc [&_ul]:pl-5 [&_li]:my-0.5" style={{ color: "var(--gray-12)" }}>
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            a: ({ href = "", children, ...rest }) => (
              <a
                href={href.startsWith("http") ? href : `https://${href}`}
                target="_blank"
                rel="noopener noreferrer"
                style={{ color: "var(--accent-11)" }}
                className="no-underline hover:underline"
                {...rest}
              >
                {children}
              </a>
            ),
            code: ({ children }) => (
              <code className="px-1 py-0.5 rounded bg-[var(--gray-3)] text-[12px]">{children}</code>
            ),
          }}
        >
          {narrativeMd}
        </ReactMarkdown>
      </div>
    </div>
  );
}

interface WorklistJson {
  address?: string;
  city?: string;
  arn?: string | null;
  why?: string;
  expected_yield?: number;
  status?: string;
}

export function GwWorklistCard({ facts }: { facts: GroupFact[] }) {
  const items = facts.filter((f) => f.field === "gw_worklist_item");
  if (items.length === 0) return null;
  return (
    <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
      <div className="flex items-center gap-2">
        <ListChecks size={16} style={{ color: "var(--gray-9)" }} />
        <Heading size="4" weight="medium">GW Worklist</Heading>
        <Badge size="1" color="amber" variant="soft">{items.length} pulls</Badge>
      </div>
      <Text size="1" className="block mt-1" style={{ color: "var(--gray-9)" }}>
        GeoWarehouse pulls the adjudicator expects to pay off, highest yield first.
      </Text>
      <div className="mt-2 divide-y divide-[var(--gray-4)]">
        {items.map((f) => {
          const vj = ((typeof f.value_json === "object" && f.value_json) || {}) as WorklistJson;
          const open = (vj.status ?? "open") === "open";
          return (
            <div key={f.id} className="flex items-start justify-between gap-3 py-2">
              <div className="flex-1 min-w-0">
                <Text size="2" style={{ color: "var(--gray-12)" }}>{f.value}</Text>
                {vj.why && (
                  <Text size="1" className="block" style={{ color: "var(--gray-9)" }}>
                    {vj.why}
                  </Text>
                )}
              </div>
              <div className="flex items-center gap-1.5 shrink-0">
                <Badge size="1" color={open ? "amber" : "jade"} variant="soft">
                  {vj.status ?? "open"}
                </Badge>
                <SourceBadge fact={f} />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
