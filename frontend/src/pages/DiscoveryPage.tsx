import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Heading, Text, Badge, Button } from "@radix-ui/themes";
import { MagnifyingGlass, CaretUp, CaretDown } from "@phosphor-icons/react";
import { fetchApi } from "../api/client";
import { formatCurrency, formatDate } from "../lib/utils";
import type { DiscoveryBrowseResponse, DiscoveryClusterSummary } from "../types";

// ── Helpers ────────────────────────────────────────────────────

function statusBadge(status: string) {
  if (status === "auto_confirmed") {
    return <Badge size="1" color="green" variant="soft">Auto Confirmed</Badge>;
  }
  if (status === "confirmed") {
    return <Badge size="1" color="jade" variant="soft">Confirmed</Badge>;
  }
  if (status === "excluded") {
    return <Badge size="1" color="gray" variant="soft">Excluded</Badge>;
  }
  return <Badge size="1" color="amber" variant="soft">Needs Review</Badge>;
}

function confidencePct(confidence: number): string {
  return `${Math.round(confidence * 100)}%`;
}

type SortField = "member_count" | "portfolio_value" | "confidence" | "anchor_name";
type SortOrder = "asc" | "desc";

function SortHeader({ label, field, currentSort, currentOrder, onSort }: {
  label: string;
  field: SortField;
  currentSort: SortField;
  currentOrder: SortOrder;
  onSort: (field: SortField) => void;
}) {
  const active = currentSort === field;
  return (
    <button
      onClick={() => onSort(field)}
      className="inline-flex items-center gap-0.5 text-[12px] font-medium bg-transparent border-none cursor-pointer p-0"
      style={{ color: active ? "var(--gray-12)" : "var(--gray-9)" }}
    >
      {label}
      {active && (
        currentOrder === "desc"
          ? <CaretDown size={12} weight="bold" />
          : <CaretUp size={12} weight="bold" />
      )}
    </button>
  );
}

// ── Main page ──────────────────────────────────────────────────

export default function DiscoveryPage() {
  const navigate = useNavigate();
  const [data, setData] = useState<DiscoveryBrowseResponse | null>(null);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [sort, setSort] = useState<SortField>("member_count");
  const [order, setOrder] = useState<SortOrder>("desc");

  useEffect(() => {
    setLoading(true);
    const params: Record<string, string> = {
      page: String(page),
      per_page: "50",
      sort,
      order,
    };
    if (search) params.q = search;

    fetchApi<DiscoveryBrowseResponse>("/discovery", params)
      .then(setData)
      .finally(() => setLoading(false));
  }, [page, search, sort, order]);

  // Debounced search
  useEffect(() => {
    const t = setTimeout(() => {
      setSearch(searchInput);
      setPage(1);
    }, 300);
    return () => clearTimeout(t);
  }, [searchInput]);

  const handleSort = (field: SortField) => {
    if (sort === field) {
      // Toggle order
      setOrder(order === "desc" ? "asc" : "desc");
    } else {
      setSort(field);
      setOrder("desc");
    }
    setPage(1);
  };

  const run = data?.run ?? null;

  return (
    <div className="flex flex-col gap-4">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <Heading size="5" weight="medium">Discovery</Heading>
          <Text size="2" style={{ color: "var(--gray-9)" }}>
            Probable portfolio clusters detected from shared signals
          </Text>
        </div>

        {/* Run metadata */}
        {run && (
          <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] px-4 py-2.5 text-right" style={{ minWidth: 220 }}>
            <Text size="1" style={{ color: "var(--gray-9)" }} className="block">
              Last run: {formatDate(run.started_at)} &middot; <span style={{ textTransform: "capitalize" }}>{run.mode}</span>
            </Text>
            {run.stats && (
              <Text size="1" style={{ color: "var(--gray-11)" }} className="block mt-0.5">
                {run.stats.clusters_found.toLocaleString()} clusters &middot; {run.stats.groups_processed.toLocaleString()} groups scanned
              </Text>
            )}
          </div>
        )}
      </div>

      {/* Search */}
      <div className="relative">
        <MagnifyingGlass
          size={15}
          className="absolute left-2.5 top-1/2 -translate-y-1/2"
          style={{ color: "var(--gray-8)" }}
        />
        <input
          type="text"
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          placeholder="Search clusters..."
          className="w-full h-8 pl-8 pr-3 text-[13px] rounded-md border border-[var(--gray-6)] bg-white outline-none focus:border-[var(--accent-7)] transition-colors"
          style={{ color: "var(--gray-12)" }}
        />
      </div>

      {/* Table */}
      <div
        className="rounded-[var(--card-radius)] border border-[var(--gray-6)] overflow-hidden transition-opacity"
        style={{ opacity: loading ? 0.6 : 1 }}
      >
        <table className="w-full text-[14px] [&_td]:whitespace-nowrap [&_th]:whitespace-nowrap">
          <thead>
            <tr style={{ background: "var(--gray-2)" }}>
              <th className="text-left px-4 py-2 border-b border-[var(--gray-6)]">
                <SortHeader label="Portfolio" field="anchor_name" currentSort={sort} currentOrder={order} onSort={handleSort} />
              </th>
              <th className="text-right px-4 py-2 border-b border-[var(--gray-6)]">
                <SortHeader label="Members" field="member_count" currentSort={sort} currentOrder={order} onSort={handleSort} />
              </th>
              <th className="text-right px-4 py-2 border-b border-[var(--gray-6)]">
                <SortHeader label="Portfolio Value" field="portfolio_value" currentSort={sort} currentOrder={order} onSort={handleSort} />
              </th>
              <th className="text-right px-4 py-2 border-b border-[var(--gray-6)]">
                <SortHeader label="Confidence" field="confidence" currentSort={sort} currentOrder={order} onSort={handleSort} />
              </th>
              <th className="text-right px-4 py-2 text-[12px] font-medium border-b border-[var(--gray-6)]" style={{ color: "var(--gray-9)" }}>
                Signals
              </th>
              <th className="text-left px-4 py-2 text-[12px] font-medium border-b border-[var(--gray-6)]" style={{ color: "var(--gray-9)" }}>
                Status
              </th>
            </tr>
          </thead>
          <tbody>
            {data?.results.map((cluster: DiscoveryClusterSummary) => (
              <tr
                key={cluster.anchor_group_id}
                className="border-b border-[var(--gray-4)] hover:bg-[var(--gray-a2)] cursor-pointer"
                onClick={() => navigate(`/discovery/${cluster.anchor_group_id}`)}
              >
                <td className="px-4 py-2 font-medium">{cluster.anchor_name}</td>
                <td className="px-4 py-2 text-right" style={{ color: "var(--gray-11)" }}>
                  {cluster.member_count.toLocaleString()}
                </td>
                <td className="px-4 py-2 text-right" style={{ color: "var(--gray-11)" }}>
                  {cluster.portfolio_value > 0 ? formatCurrency(cluster.portfolio_value) : "—"}
                </td>
                <td className="px-4 py-2 text-right" style={{ color: "var(--gray-11)" }}>
                  {confidencePct(cluster.confidence)}
                </td>
                <td className="px-4 py-2 text-right" style={{ color: "var(--gray-11)" }}>
                  {cluster.signal_count.toLocaleString()}
                </td>
                <td className="px-4 py-2">
                  {statusBadge(cluster.status)}
                </td>
              </tr>
            ))}

            {data?.results.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-16 text-center">
                  <div className="flex flex-col items-center gap-2">
                    <Text size="3" weight="medium" style={{ color: "var(--gray-11)" }}>
                      No clusters found
                    </Text>
                    {search ? (
                      <Text size="2" style={{ color: "var(--gray-9)" }}>
                        No clusters match your search.
                      </Text>
                    ) : (
                      <Text size="2" style={{ color: "var(--gray-9)" }}>
                        Run the discovery engine to detect portfolio clusters:
                        <br />
                        <code className="text-[12px] bg-[var(--gray-3)] px-1.5 py-0.5 rounded mt-1.5 inline-block">
                          python -m cleo.discovery run --validate
                        </code>
                      </Text>
                    )}
                  </div>
                </td>
              </tr>
            )}

            {!data && !loading && (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center" style={{ color: "var(--gray-9)" }}>
                  Loading...
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {data && data.pages > 1 && (
        <div className="flex items-center justify-between">
          <Text size="2" style={{ color: "var(--gray-9)" }}>
            Page {data.page} of {data.pages} &middot; {data.total.toLocaleString()} clusters
          </Text>
          <div className="flex gap-2">
            <Button
              size="1"
              variant="soft"
              disabled={page <= 1}
              onClick={() => setPage(page - 1)}
            >
              Previous
            </Button>
            <Button
              size="1"
              variant="soft"
              disabled={page >= data.pages}
              onClick={() => setPage(page + 1)}
            >
              Next
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
