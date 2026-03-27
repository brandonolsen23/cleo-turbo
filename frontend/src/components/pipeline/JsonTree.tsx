import { useState } from "react";

interface DiffChange {
  path: string;
  type: "added" | "removed" | "changed";
  value?: unknown;
  old?: unknown;
  new?: unknown;
}

interface JsonTreeProps {
  data: unknown;
  changes?: DiffChange[];
  defaultExpand?: number;
  path?: string;
}

function getChangeForPath(changes: DiffChange[] | undefined, path: string): DiffChange | undefined {
  if (!changes) return undefined;
  return changes.find((c) => c.path === path);
}

function hasChangesUnder(changes: DiffChange[] | undefined, path: string): boolean {
  if (!changes) return false;
  const prefix = path ? `${path}.` : "";
  return changes.some((c) => c.path.startsWith(prefix) || c.path === path);
}

function ValueDisplay({ value }: { value: unknown }) {
  if (value === null) return <span style={{ color: "var(--gray-8)" }}>null</span>;
  if (typeof value === "boolean") return <span style={{ color: "#8b5cf6" }}>{String(value)}</span>;
  if (typeof value === "number") return <span style={{ color: "#0d74ce" }}>{value}</span>;
  if (typeof value === "string") {
    const display = value.length > 120 ? value.slice(0, 120) + "..." : value;
    return <span style={{ color: "#218358" }}>"{display}"</span>;
  }
  return <span>{JSON.stringify(value)}</span>;
}

function JsonNode({ keyName, data, changes, defaultExpand, path, depth }: {
  keyName?: string;
  data: unknown;
  changes?: DiffChange[];
  defaultExpand: number;
  path: string;
  depth: number;
}) {
  const [expanded, setExpanded] = useState(depth < defaultExpand);
  const change = getChangeForPath(changes, path);

  const bgColor = change
    ? change.type === "added" ? "rgba(34, 197, 94, 0.08)"
    : change.type === "removed" ? "rgba(239, 68, 68, 0.08)"
    : change.type === "changed" ? "rgba(251, 191, 36, 0.08)"
    : undefined
    : undefined;

  if (data === null || typeof data !== "object") {
    return (
      <div className="flex items-start gap-1 py-px" style={{ paddingLeft: depth * 16, background: bgColor }}>
        {keyName !== undefined && (
          <span className="font-medium" style={{ color: "var(--gray-12)" }}>{keyName}: </span>
        )}
        {change?.type === "changed" ? (
          <>
            <span style={{ textDecoration: "line-through", color: "var(--red-9)", opacity: 0.7 }}>
              <ValueDisplay value={change.old} />
            </span>
            <span className="mx-1" style={{ color: "var(--gray-8)" }}>→</span>
            <ValueDisplay value={change.new} />
          </>
        ) : (
          <ValueDisplay value={data} />
        )}
      </div>
    );
  }

  const isArray = Array.isArray(data);
  const entries = isArray ? data.map((v, i) => [String(i), v] as const) : Object.entries(data as Record<string, unknown>);
  const count = entries.length;
  const hasChildChanges = hasChangesUnder(changes, path);

  return (
    <div>
      <div
        className="flex items-center gap-1 py-px cursor-pointer select-none"
        style={{ paddingLeft: depth * 16, background: bgColor }}
        onClick={() => setExpanded(!expanded)}
      >
        <span className="text-[11px] w-4 text-center" style={{ color: "var(--gray-8)" }}>
          {expanded ? "▼" : "▶"}
        </span>
        {keyName !== undefined && (
          <span className="font-medium" style={{ color: "var(--gray-12)" }}>{keyName}: </span>
        )}
        <span style={{ color: "var(--gray-8)" }}>
          {isArray ? `[${count}]` : `{${count}}`}
        </span>
        {!expanded && hasChildChanges && (
          <span className="ml-1 text-[10px] px-1 rounded" style={{ background: "var(--amber-3)", color: "var(--amber-11)" }}>
            modified
          </span>
        )}
      </div>
      {expanded && entries.map(([k, v]) => (
        <JsonNode
          key={k}
          keyName={k}
          data={v}
          changes={changes}
          defaultExpand={defaultExpand}
          path={path ? `${path}.${k}` : k}
          depth={depth + 1}
        />
      ))}
    </div>
  );
}

export default function JsonTree({ data, changes, defaultExpand = 2, path = "" }: JsonTreeProps) {
  return (
    <div className="font-mono text-[13px] leading-5 overflow-x-auto">
      <JsonNode data={data} changes={changes} defaultExpand={defaultExpand} path={path} depth={0} />
    </div>
  );
}
