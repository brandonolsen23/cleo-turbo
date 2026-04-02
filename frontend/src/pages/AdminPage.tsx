import { useState, useEffect, useCallback, useRef } from "react";
import { Heading, Text, Button, Badge } from "@radix-ui/themes";
import { ArrowClockwise, Database, Trash, HardDrives, Info } from "@phosphor-icons/react";
import { postApi, fetchApi } from "../api/client";

interface ActionCard {
  id: string;
  title: string;
  description: string;
  buttonLabel: string;
  icon: React.ReactNode;
  endpoint: string;
  method: "post" | "get";
  confirmMessage?: string;
}

interface ServerStatus {
  db_size_mb: number;
  db_last_modified: number;
  table_counts: Record<string, number | null>;
}

interface RebuildStatus {
  running: boolean;
  phase: string;
  message: string;
  error?: string | null;
  elapsed?: number;
  counts?: Record<string, number>;
  live_counts?: Record<string, number>;
}

const ACTIONS: ActionCard[] = [
  {
    id: "restart-backend",
    title: "Restart Backend",
    description:
      "Restarts the FastAPI server (port 8099). Use after changing Python code. The page will reconnect automatically.",
    buttonLabel: "Restart Backend",
    icon: <ArrowClockwise size={20} weight="bold" />,
    endpoint: "/admin/restart-backend",
    method: "post",
  },
  {
    id: "restart-frontend",
    title: "Restart Frontend",
    description:
      "Reloads the browser and clears the module cache. Use if hot reload stops working or you see stale UI.",
    buttonLabel: "Restart Frontend",
    icon: <ArrowClockwise size={20} weight="bold" />,
    endpoint: "__frontend_reload__",
    method: "post",
  },
  {
    id: "rebuild-db",
    title: "Rebuild Database",
    description:
      "Rebuilds the SQLite database from JSON source files. Runs as a background process (~2–3 minutes). CRM data is preserved.",
    buttonLabel: "Rebuild DB",
    icon: <Database size={20} weight="bold" />,
    endpoint: "/admin/rebuild-db",
    method: "post",
    confirmMessage:
      "This will rebuild the entire database from clean-data/. CRM data (deals, lists, notes) will be preserved. Continue?",
  },
  {
    id: "clear-cache",
    title: "Clear Python Cache",
    description:
      "Deletes all __pycache__ directories and .pyc files. Use after code changes if the backend is serving stale modules.",
    buttonLabel: "Clear Cache",
    icon: <Trash size={20} weight="bold" />,
    endpoint: "/admin/clear-cache",
    method: "post",
  },
];

function formatCount(n: number | undefined | null): string {
  if (n == null) return "—";
  return n.toLocaleString();
}

export default function AdminPage() {
  const [loading, setLoading] = useState<Record<string, boolean>>({});
  const [results, setResults] = useState<Record<string, { success: boolean; message: string } | null>>({});
  const [status, setStatus] = useState<ServerStatus | null>(null);
  const [rebuildStatus, setRebuildStatus] = useState<RebuildStatus | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadStatus = useCallback(async () => {
    try {
      const data = await fetchApi<ServerStatus>("/admin/status");
      setStatus(data);
    } catch {
      // silently fail — status is optional
    }
  }, []);

  // Poll rebuild status
  const pollRebuildStatus = useCallback(async () => {
    try {
      const data = await fetchApi<RebuildStatus>("/admin/rebuild-status");
      setRebuildStatus(data);

      // Stop polling when done
      if (!data.running && pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;

        // Update loading state
        setLoading((prev) => ({ ...prev, "rebuild-db": false }));

        if (data.phase === "done") {
          const countSummary = data.counts
            ? `${formatCount(data.counts.properties)} properties, ${formatCount(data.counts.transactions)} txns, ${formatCount(data.counts.contacts)} contacts`
            : "";
          setResults((prev) => ({
            ...prev,
            "rebuild-db": {
              success: true,
              message: `${data.message}${countSummary ? ` — ${countSummary}` : ""}`,
            },
          }));
          // Refresh server status
          setTimeout(loadStatus, 1000);
        } else if (data.phase === "error") {
          setResults((prev) => ({
            ...prev,
            "rebuild-db": {
              success: false,
              message: data.message || "Rebuild failed",
            },
          }));
        }
      }
    } catch {
      // Backend might be restarting — keep polling
    }
  }, [loadStatus]);

  const startPolling = useCallback(() => {
    if (pollRef.current) return; // Already polling
    pollRef.current = setInterval(pollRebuildStatus, 3000);
    pollRebuildStatus(); // Immediate first poll
  }, [pollRebuildStatus]);

  // Check rebuild status on mount (in case one is already running)
  useEffect(() => {
    loadStatus();
    fetchApi<RebuildStatus>("/admin/rebuild-status")
      .then((data) => {
        setRebuildStatus(data);
        if (data.running) {
          setLoading((prev) => ({ ...prev, "rebuild-db": true }));
          startPolling();
        }
      })
      .catch(() => {});
  }, [loadStatus, startPolling]);

  // Cleanup polling on unmount
  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  const runAction = async (action: ActionCard) => {
    // Frontend reload is special — no API call
    if (action.endpoint === "__frontend_reload__") {
      window.location.reload();
      return;
    }

    if (action.confirmMessage && !window.confirm(action.confirmMessage)) return;

    setLoading((prev) => ({ ...prev, [action.id]: true }));
    setResults((prev) => ({ ...prev, [action.id]: null }));

    try {
      const data = await postApi<Record<string, unknown>>(action.endpoint, {});
      const success = data.success !== false;

      if (action.id === "rebuild-db") {
        // Rebuild now runs in background — start polling
        setRebuildStatus({ running: true, phase: "starting", message: "Rebuild starting..." });
        startPolling();
        return; // Don't clear loading — polling handles that
      }

      let message = success ? "Completed successfully" : "Failed";
      if (action.id === "clear-cache" && data.removed_count !== undefined) {
        message = `Cleared ${data.removed_count} cache director${data.removed_count === 1 ? "y" : "ies"}`;
      }
      if (action.id === "restart-backend") {
        message = "Backend restart triggered — server will reload momentarily";
      }

      setResults((prev) => ({ ...prev, [action.id]: { success, message } }));
    } catch (err: unknown) {
      const errMsg = err instanceof Error ? err.message : "Unknown error";
      setResults((prev) => ({ ...prev, [action.id]: { success: false, message: errMsg } }));
    } finally {
      if (action.id !== "rebuild-db") {
        setLoading((prev) => ({ ...prev, [action.id]: false }));
      }
    }
  };

  const formatBytes = (mb: number) => {
    if (mb >= 1000) return `${(mb / 1000).toFixed(1)} GB`;
    return `${mb} MB`;
  };

  const formatTimestamp = (ts: number) => {
    if (!ts) return "Unknown";
    return new Date(ts * 1000).toLocaleString();
  };

  // Build the rebuild progress display
  const isRebuilding = loading["rebuild-db"] && rebuildStatus?.running;
  const liveCounts = rebuildStatus?.live_counts;

  return (
    <div className="max-w-3xl mx-auto">
      <div className="mb-6">
        <Heading size="6" weight="medium">
          Settings
        </Heading>
        <Text size="2" style={{ color: "var(--gray-9)" }} className="mt-1 block">
          Server management and system configuration.
        </Text>
      </div>

      {/* Status bar */}
      {status && (
        <div
          className="flex items-center gap-4 mb-6 px-4 py-3 rounded-[var(--radius-3)] border border-[var(--gray-5)]"
          style={{ background: "var(--gray-2)" }}
        >
          <HardDrives size={18} style={{ color: "var(--gray-9)" }} />
          <div className="flex items-center gap-4 text-[13px]" style={{ color: "var(--gray-11)" }}>
            <span>
              DB Size: <strong>{formatBytes(status.db_size_mb)}</strong>
            </span>
            <span style={{ color: "var(--gray-6)" }}>|</span>
            <span>
              Last rebuilt: <strong>{formatTimestamp(status.db_last_modified)}</strong>
            </span>
            {status.table_counts.properties != null && (
              <>
                <span style={{ color: "var(--gray-6)" }}>|</span>
                <span>
                  {status.table_counts.properties?.toLocaleString()} properties, {status.table_counts.transactions?.toLocaleString()} txns
                </span>
              </>
            )}
          </div>
        </div>
      )}

      {/* Action cards */}
      <div className="flex flex-col gap-4">
        {ACTIONS.map((action) => {
          const isLoading = loading[action.id];
          const result = results[action.id];
          const isRebuildCard = action.id === "rebuild-db";

          return (
            <div
              key={action.id}
              className="px-5 py-4 rounded-[var(--card-radius)] border border-[var(--gray-6)]"
              style={{ background: "white" }}
            >
              <div className="flex items-center justify-between">
                <div className="flex-1 mr-4">
                  <div className="flex items-center gap-2">
                    <Text size="3" weight="medium">
                      {action.title}
                    </Text>
                  </div>
                  <Text size="2" className="mt-1 block" style={{ color: "var(--gray-9)" }}>
                    {action.description}
                  </Text>
                </div>
                <Button
                  variant="soft"
                  color="jade"
                  size="2"
                  onClick={() => runAction(action)}
                  disabled={isLoading}
                  style={{ minWidth: 140, cursor: isLoading ? "wait" : "pointer" }}
                >
                  {isLoading
                    ? isRebuildCard
                      ? "Rebuilding..."
                      : "Running..."
                    : action.buttonLabel}
                </Button>
              </div>

              {/* Rebuild progress indicator */}
              {isRebuildCard && isRebuilding && liveCounts && (
                <div
                  className="mt-3 px-3 py-2 rounded-[var(--radius-2)] border border-[var(--gray-4)]"
                  style={{ background: "var(--gray-2)" }}
                >
                  <div className="flex items-center gap-2 mb-2">
                    <div
                      className="w-2 h-2 rounded-full animate-pulse"
                      style={{ background: "var(--jade-9)" }}
                    />
                    <Text size="1" weight="medium" style={{ color: "var(--gray-11)" }}>
                      {rebuildStatus?.phase === "compiling" ? "Compiling..." : rebuildStatus?.message}
                    </Text>
                  </div>
                  <div className="grid grid-cols-3 gap-x-4 gap-y-1 text-[12px]" style={{ color: "var(--gray-9)" }}>
                    <span>Groups: <strong style={{ color: "var(--gray-11)" }}>{formatCount(liveCounts.groups)}</strong></span>
                    <span>Contacts: <strong style={{ color: "var(--gray-11)" }}>{formatCount(liveCounts.contacts)}</strong></span>
                    <span>Transactions: <strong style={{ color: "var(--gray-11)" }}>{formatCount(liveCounts.transactions)}</strong></span>
                    <span>Properties: <strong style={{ color: "var(--gray-11)" }}>{formatCount(liveCounts.properties)}</strong></span>
                    <span>POIs: <strong style={{ color: "var(--gray-11)" }}>{formatCount(liveCounts.pois)}</strong></span>
                    <span>GW: <strong style={{ color: "var(--gray-11)" }}>{formatCount(liveCounts.gw_assessments)}</strong></span>
                  </div>
                </div>
              )}

              {/* Result badge */}
              {result && (
                <div className="mt-2 flex items-center gap-2">
                  <Badge color={result.success ? "green" : "red"} variant="soft" size="1">
                    {result.success ? "Success" : "Error"}
                  </Badge>
                  <Text size="1" style={{ color: result.success ? "var(--gray-9)" : "var(--red-11)" }}>
                    {result.message}
                  </Text>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Info note */}
      <div
        className="flex items-start gap-3 mt-6 px-4 py-3 rounded-[var(--radius-3)] border border-[var(--gray-5)]"
        style={{ background: "var(--gray-2)" }}
      >
        <Info size={16} className="mt-0.5 shrink-0" style={{ color: "var(--gray-9)" }} />
        <Text size="1" style={{ color: "var(--gray-9)" }}>
          Backend restart requires uvicorn to be running with <code>--reload</code>. Frontend restart does a full
          page reload. Database rebuild runs as a background process and won't be interrupted if you navigate away.
        </Text>
      </div>
    </div>
  );
}
