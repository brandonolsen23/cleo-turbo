import { useEffect, useState, useCallback, useRef } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Heading, Text, Button, Badge } from "@radix-ui/themes";
import { MagnifyingGlass } from "@phosphor-icons/react";
import { fetchApi } from "../api/client";
import { formatDate } from "../lib/utils";
import FilterPanel, { SelectFilter } from "../components/ui/FilterPanel";
import type {
  Issue, IssueStatus, IssueSeverity, IssueCategory,
  IssueEntityType, BrowseResponse,
} from "../types";

const SEVERITY_COLOR: Record<IssueSeverity, "red" | "orange" | "amber" | "gray"> = {
  critical: "red",
  high: "orange",
  medium: "amber",
  low: "gray",
};

const STATUS_COLOR: Record<IssueStatus, "amber" | "blue" | "jade" | "gray"> = {
  open: "amber",
  in_progress: "blue",
  resolved: "jade",
  wontfix: "gray",
  duplicate: "gray",
};

const CATEGORY_LABELS: Record<IssueCategory, string> = {
  rt_property_mismatch:   "RT↔Property mismatch",
  parcel_geometry_wrong:  "Parcel geometry wrong",
  wrong_owner:            "Wrong owner",
  group_clustering_issue: "Group clustering",
  parsing_error:          "Parsing error",
  missing_data:           "Missing data",
  duplicate_entity:       "Duplicate entity",
  formatting_issue:       "Formatting",
  layout_issue:           "Layout",
  wrong_calculation:      "Wrong calculation",
  other:                  "Other",
};

const STATUS_OPTIONS: IssueStatus[] = ["open", "in_progress", "resolved", "wontfix", "duplicate"];
const SEVERITY_OPTIONS: IssueSeverity[] = ["critical", "high", "medium", "low"];
const ENTITY_OPTIONS: IssueEntityType[] = ["property", "contact", "group", "transaction", "auto_group", "general"];

export default function IssuesPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const page = Number(searchParams.get("page") || "1");
  const status = searchParams.get("status") || "open";
  const severity = searchParams.get("severity") || "";
  const category = searchParams.get("category") || "";
  const entityType = searchParams.get("entity_type") || "";
  const q = searchParams.get("q") || "";

  const [data, setData] = useState<BrowseResponse<Issue> | null>(null);
  const [loading, setLoading] = useState(false);
  const [searchInput, setSearchInput] = useState(q);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>();
  const fetchIdRef = useRef(0);

  const fetchData = useCallback(() => {
    setLoading(true);
    const id = ++fetchIdRef.current;
    const params: Record<string, string> = {
      page: String(page),
      per_page: "100",
      sort: "reported_at",
      order: "desc",
    };
    if (status) params.status = status;
    if (severity) params.severity = severity;
    if (category) params.category = category;
    if (entityType) params.entity_type = entityType;
    if (q) params.q = q;
    fetchApi<BrowseResponse<Issue>>("/issues", params)
      .then((res) => { if (id === fetchIdRef.current) setData(res); })
      .finally(() => { if (id === fetchIdRef.current) setLoading(false); });
  }, [page, status, severity, category, entityType, q]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const setParam = useCallback((key: string, value: string) => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      if (value) next.set(key, value);
      else next.delete(key);
      if (key !== "page") next.set("page", "1");
      return next;
    });
  }, [setSearchParams]);

  const onSearch = (v: string) => {
    setSearchInput(v);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => setParam("q", v), 300);
  };

  const activeFilterCount = [severity, category, entityType].filter(Boolean).length
    + (status && status !== "open" ? 1 : 0);

  const clearAll = () => {
    setSearchParams((prev) => {
      const next = new URLSearchParams();
      const qv = prev.get("q");
      if (qv) next.set("q", qv);
      next.set("page", "1");
      return next;
    });
  };

  const entityHref = (it: Issue): string | null => {
    if (!it.entity_id) return null;
    switch (it.entity_type) {
      case "property":    return `/properties/${it.entity_id}`;
      case "contact":     return `/contacts/${it.entity_id}`;
      case "group":
      case "auto_group":  return `/groups/${it.entity_id}`;
      case "transaction": return `/transactions/${it.entity_id}`;
      default:            return null;
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <Heading size="5" weight="medium">Issues</Heading>
        <Text size="2" style={{ color: "var(--gray-9)" }}>
          {data ? `${data.total.toLocaleString()} ${data.total === 1 ? "issue" : "issues"}` : "Loading..."}
        </Text>
      </div>

      {/* Search */}
      <div className="relative">
        <MagnifyingGlass size={15} className="absolute left-2.5 top-1/2 -translate-y-1/2"
                          style={{ color: "var(--gray-8)" }} />
        <input
          type="text"
          value={searchInput}
          onChange={(e) => onSearch(e.target.value)}
          placeholder="Search title or description..."
          className="w-full h-8 pl-8 pr-3 text-[13px] rounded-md border border-[var(--gray-6)] bg-white outline-none focus:border-[var(--accent-7)] transition-colors"
          style={{ color: "var(--gray-12)" }}
        />
      </div>

      {/* Filters */}
      <FilterPanel activeCount={activeFilterCount} onClearAll={clearAll}>
        <SelectFilter
          label="Status"
          value={status === "open" ? "" : status}
          onChange={(v) => setParam("status", v || "open")}
          options={STATUS_OPTIONS.map((s) => ({ value: s, label: s.replace("_", " ") }))}
        />
        <SelectFilter
          label="Severity"
          value={severity}
          onChange={(v) => setParam("severity", v)}
          options={SEVERITY_OPTIONS.map((s) => ({ value: s, label: s }))}
        />
        <SelectFilter
          label="Category"
          value={category}
          onChange={(v) => setParam("category", v)}
          options={(Object.keys(CATEGORY_LABELS) as IssueCategory[]).map((c) => ({
            value: c, label: CATEGORY_LABELS[c],
          }))}
        />
        <SelectFilter
          label="Entity Type"
          value={entityType}
          onChange={(v) => setParam("entity_type", v)}
          options={ENTITY_OPTIONS.map((e) => ({ value: e, label: e.replace("_", " ") }))}
        />
      </FilterPanel>

      {/* Table */}
      <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] overflow-hidden transition-opacity"
           style={{ opacity: loading ? 0.6 : 1 }}>
        <table className="w-full text-[14px] [&_td]:whitespace-nowrap [&_th]:whitespace-nowrap">
          <thead>
            <tr style={{ background: "var(--gray-2)" }}>
              <th className="text-left px-3 py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>#</th>
              <th className="text-left px-3 py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Title</th>
              <th className="text-left px-3 py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Entity</th>
              <th className="text-left px-3 py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Component</th>
              <th className="text-left px-3 py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Categories</th>
              <th className="text-left px-3 py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Severity</th>
              <th className="text-left px-3 py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Status</th>
              <th className="text-left px-3 py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Reported</th>
            </tr>
          </thead>
          <tbody>
            {data?.results.map((it) => {
              const ent = entityHref(it);
              return (
                <tr key={it.id}
                    className="border-b border-[var(--gray-4)] hover:bg-[var(--gray-a2)] cursor-pointer"
                    onClick={() => navigate(`/issues/${it.id}`)}>
                  <td className="px-3 py-2" style={{ color: "var(--gray-9)" }}>#{it.id}</td>
                  <td className="px-3 py-2 font-medium" style={{ color: "var(--gray-12)" }}>{it.title}</td>
                  <td className="px-3 py-2" style={{ color: "var(--gray-11)" }}>
                    {ent ? (
                      <Link to={ent} onClick={(e) => e.stopPropagation()} className="no-underline"
                            style={{ color: "var(--accent-11)" }}>
                        {it.entity_type}:{it.entity_id}
                      </Link>
                    ) : (
                      <Text size="2" style={{ color: "var(--gray-9)" }}>{it.entity_type}</Text>
                    )}
                  </td>
                  <td className="px-3 py-2" style={{ color: "var(--gray-11)" }}>
                    {it.component ? <code style={{ fontSize: 11 }}>{it.component}</code> : "—"}
                  </td>
                  <td className="px-3 py-2">
                    <div className="flex gap-1 flex-wrap">
                      {it.categories.slice(0, 2).map((c) => (
                        <Badge key={c} size="1" variant="soft" color="gray">{CATEGORY_LABELS[c]}</Badge>
                      ))}
                      {it.categories.length > 2 && (
                        <Badge size="1" variant="soft" color="gray">+{it.categories.length - 2}</Badge>
                      )}
                    </div>
                  </td>
                  <td className="px-3 py-2">
                    <Badge size="1" variant="soft" color={SEVERITY_COLOR[it.severity]}>{it.severity}</Badge>
                  </td>
                  <td className="px-3 py-2">
                    <Badge size="1" variant={it.status === "open" ? "solid" : "soft"} color={STATUS_COLOR[it.status]}>
                      {it.status.replace("_", " ")}
                    </Badge>
                  </td>
                  <td className="px-3 py-2" style={{ color: "var(--gray-11)" }}>{formatDate(it.reported_at)}</td>
                </tr>
              );
            })}
            {data?.results.length === 0 && (
              <tr>
                <td colSpan={8} className="px-3 py-12 text-center" style={{ color: "var(--gray-9)" }}>
                  No issues match.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {data && data.pages > 1 && (
        <div className="flex items-center justify-between">
          <Text size="2" style={{ color: "var(--gray-9)" }}>Page {data.page} of {data.pages}</Text>
          <div className="flex gap-2">
            <Button size="1" variant="soft" disabled={page <= 1} onClick={() => setParam("page", String(page - 1))}>
              Previous
            </Button>
            <Button size="1" variant="soft" disabled={page >= data.pages} onClick={() => setParam("page", String(page + 1))}>
              Next
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
