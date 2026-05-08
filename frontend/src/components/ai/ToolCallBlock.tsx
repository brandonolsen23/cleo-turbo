import React, { useState } from "react";
import { Text, Badge } from "@radix-ui/themes";
import { CaretRight, CaretDown, Database, MagnifyingGlass, Link as LinkIcon } from "@phosphor-icons/react";
import type { AIToolPart } from "../../types";

const ICON: Record<AIToolPart["name"], React.JSX.Element> = {
  run_sql:         <Database size={14} />,
  describe_schema: <MagnifyingGlass size={14} />,
  get_entity_url:  <LinkIcon size={14} />,
};

function summarize(part: AIToolPart): string {
  if (part.error) return part.error;
  if (part.ok === undefined) return "running…";
  if (part.name === "run_sql") {
    const n = part.rowCount ?? 0;
    return `${n} ${n === 1 ? "row" : "rows"}${part.truncated ? " (truncated)" : ""}`;
  }
  if (part.name === "describe_schema") {
    const t = (part.input as { table?: string }).table;
    return t ? `described ${t}` : "listed tables";
  }
  return "ok";
}

function highlightSQL(sql: string): React.JSX.Element {
  const KEYWORDS = /\b(SELECT|FROM|WHERE|JOIN|LEFT|RIGHT|INNER|OUTER|ON|GROUP BY|ORDER BY|HAVING|LIMIT|OFFSET|WITH|AS|AND|OR|NOT|IN|IS|NULL|LIKE|EXISTS|CASE|WHEN|THEN|ELSE|END|UNION|ALL|DISTINCT|EXPLAIN)\b/gi;
  const parts = sql.split(KEYWORDS);
  return (
    <pre className="text-[12px] whitespace-pre-wrap break-words p-2 rounded bg-[var(--gray-3)]">
      {parts.map((seg, i) =>
        i % 2 === 1 ? (
          <span key={i} style={{ color: "var(--accent-11)", fontWeight: 600 }}>{seg}</span>
        ) : (
          <span key={i}>{seg}</span>
        )
      )}
    </pre>
  );
}

export default function ToolCallBlock({ part }: { part: AIToolPart }) {
  const [open, setOpen] = useState(false);
  const summary = summarize(part);
  const isError = part.ok === false || !!part.error;

  return (
    <div className="my-2 rounded border border-[var(--gray-6)] overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-[var(--gray-2)]"
      >
        {open ? <CaretDown size={12} /> : <CaretRight size={12} />}
        {ICON[part.name]}
        <Text size="2" weight="medium">{part.name}</Text>
        <Text size="1" style={{ color: isError ? "var(--red-11)" : "var(--gray-9)" }}>
          · {summary}
        </Text>
        {part.elapsedMs !== undefined && (
          <Badge size="1" variant="soft" color="gray">{part.elapsedMs}ms</Badge>
        )}
      </button>
      {open && (
        <div className="px-3 pb-3 border-t border-[var(--gray-4)]">
          {part.name === "run_sql" && (
            <>
              <Text size="1" weight="medium" className="block mt-2 mb-1" style={{ color: "var(--gray-11)" }}>Query</Text>
              {highlightSQL((part.input as { query?: string }).query ?? "")}
            </>
          )}
          {part.name === "describe_schema" && (part.input as { table?: string }).table && (
            <Text size="2">Table: <code>{(part.input as { table: string }).table}</code></Text>
          )}
          {part.name === "get_entity_url" && (
            <Text size="2">
              {(part.input as { entity_type: string; id: string }).entity_type}{" "}
              <code>{(part.input as { entity_type: string; id: string }).id}</code>
            </Text>
          )}
          {isError && (
            <Text size="2" style={{ color: "var(--red-11)" }} className="block mt-2">
              {part.error}
            </Text>
          )}
        </div>
      )}
    </div>
  );
}
