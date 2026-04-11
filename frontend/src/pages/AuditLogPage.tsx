import { useState, useEffect } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Heading, Text, Badge } from "@radix-ui/themes";
import { fetchApi } from "../api/client";
import { formatDate } from "../lib/utils";
import type { AuditLogEntry, BrowseResponse } from "../types";

const ACTION_COLORS: Record<string, string> = {
  create: "jade",
  promote: "blue",
  update: "amber",
  delete: "red",
  link: "violet",
  unlink: "orange",
  merge: "iris",
};

function actionColor(action: string): string {
  for (const [key, color] of Object.entries(ACTION_COLORS)) {
    if (action.includes(key)) return color;
  }
  return "gray";
}

function entityLink(type: string, id: string): string {
  switch (type) {
    case "deal": return `/deals/${id}`;
    case "contact": return `/contacts/${id}`;
    case "group": return `/groups/${id}`;
    case "list": return `/lists/${id}`;
    default: return "";
  }
}

export default function AuditLogPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [data, setData] = useState<BrowseResponse<AuditLogEntry> | null>(null);
  const page = parseInt(searchParams.get("page") || "1");
  const entityType = searchParams.get("entity_type") || "";
  const actionFilter = searchParams.get("action") || "";

  useEffect(() => {
    const params: Record<string, string | number> = { page, per_page: 50 };
    if (entityType) params.entity_type = entityType;
    if (actionFilter) params.action = actionFilter;
    fetchApi<BrowseResponse<AuditLogEntry>>("/audit", params).then(setData);
  }, [page, entityType, actionFilter]);

  return (
    <div className="flex flex-col gap-4">
      <Heading size="5" weight="medium">Audit Log</Heading>

      {/* Filters */}
      <div className="flex gap-3 items-center">
        <select
          value={entityType}
          onChange={(e) => {
            const p = new URLSearchParams(searchParams);
            if (e.target.value) p.set("entity_type", e.target.value); else p.delete("entity_type");
            p.set("page", "1");
            setSearchParams(p);
          }}
          className="h-8 px-2 text-[13px] rounded border border-[var(--gray-6)] bg-white"
        >
          <option value="">All Types</option>
          <option value="deal">Deals</option>
          <option value="contact">Contacts</option>
          <option value="group">Groups</option>
          <option value="list">Lists</option>
          <option value="group_merge">Merges</option>
        </select>
        <select
          value={actionFilter}
          onChange={(e) => {
            const p = new URLSearchParams(searchParams);
            if (e.target.value) p.set("action", e.target.value); else p.delete("action");
            p.set("page", "1");
            setSearchParams(p);
          }}
          className="h-8 px-2 text-[13px] rounded border border-[var(--gray-6)] bg-white"
        >
          <option value="">All Actions</option>
          <option value="create">Create</option>
          <option value="update">Update</option>
          <option value="delete">Delete</option>
          <option value="promote">Promote</option>
          <option value="merge">Merge</option>
          <option value="link">Link</option>
          <option value="unlink">Unlink</option>
        </select>
        {data && (
          <Text size="1" style={{ color: "var(--gray-9)" }}>{data.total} entries</Text>
        )}
      </div>

      {/* Table */}
      {data && (
        <>
          <table className="w-full text-[14px] [&_td]:whitespace-nowrap [&_th]:whitespace-nowrap">
            <thead>
              <tr className="bg-[var(--gray-2)] border-b border-[var(--gray-4)]">
                <th className="text-left py-2 px-3 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Time</th>
                <th className="text-left py-2 px-3 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>User</th>
                <th className="text-left py-2 px-3 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Action</th>
                <th className="text-left py-2 px-3 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Entity</th>
                <th className="text-left py-2 px-3 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Details</th>
              </tr>
            </thead>
            <tbody>
              {data.results.map((entry) => {
                const link = entityLink(entry.entity_type, entry.entity_id);
                return (
                  <tr key={entry.id} className="border-b border-[var(--gray-4)] hover:bg-[var(--gray-a2)]">
                    <td className="py-2 px-3" style={{ color: "var(--gray-9)" }}>
                      {formatDate(entry.created_at)}
                    </td>
                    <td className="py-2 px-3">
                      {entry.display_name || entry.username || "System"}
                    </td>
                    <td className="py-2 px-3">
                      <Badge size="1" variant="soft" color={actionColor(entry.action) as any}>
                        {entry.action}
                      </Badge>
                    </td>
                    <td className="py-2 px-3">
                      {link ? (
                        <span
                          className="cursor-pointer no-underline"
                          style={{ color: "var(--accent-11)" }}
                          onClick={() => navigate(link)}
                        >
                          {entry.entity_type}/{entry.entity_id}
                        </span>
                      ) : (
                        <Text size="2">{entry.entity_type}/{entry.entity_id}</Text>
                      )}
                    </td>
                    <td className="py-2 px-3" style={{ color: "var(--gray-9)" }}>
                      {entry.details ? (
                        <Text size="1">
                          {Object.entries(entry.details).map(([k, v]) =>
                            `${k}: ${typeof v === "string" ? v : JSON.stringify(v)}`
                          ).join(", ")}
                        </Text>
                      ) : "—"}
                    </td>
                  </tr>
                );
              })}
              {data.results.length === 0 && (
                <tr>
                  <td colSpan={5} className="py-8 text-center" style={{ color: "var(--gray-9)" }}>
                    No audit log entries found
                  </td>
                </tr>
              )}
            </tbody>
          </table>

          {/* Pagination */}
          {data.pages > 1 && (
            <div className="flex items-center justify-center gap-2 mt-2">
              <button
                disabled={page <= 1}
                onClick={() => { const p = new URLSearchParams(searchParams); p.set("page", String(page - 1)); setSearchParams(p); }}
                className="px-3 py-1 text-[13px] rounded border border-[var(--gray-6)] disabled:opacity-40"
              >
                Previous
              </button>
              <Text size="2" style={{ color: "var(--gray-9)" }}>
                Page {page} of {data.pages}
              </Text>
              <button
                disabled={page >= data.pages}
                onClick={() => { const p = new URLSearchParams(searchParams); p.set("page", String(page + 1)); setSearchParams(p); }}
                className="px-3 py-1 text-[13px] rounded border border-[var(--gray-6)] disabled:opacity-40"
              >
                Next
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
