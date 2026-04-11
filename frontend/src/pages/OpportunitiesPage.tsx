/**
 * OpportunitiesPage — tabbed view of Sell Opportunities and Buy Mandates.
 */
import { useState, useEffect } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Heading, Text, Badge, Tabs, Select } from "@radix-ui/themes";
import {
  Storefront,
  ShoppingCart,
  Warning,
} from "@phosphor-icons/react";
import { fetchApi } from "../api/client";
import { formatCurrency, formatDate } from "../lib/utils";
import {
  sellOppStatusColor,
  sellOppStatusLabel,
  buyMandateStatusColor,
  buyMandateStatusLabel,
} from "../lib/theme";
import type {
  SellOpportunity,
  BuyMandate,
  BrowseResponse,
  SellOppFilters,
  BuyMandateFilters,
} from "../types";

// ── Sell Opportunities Tab ──

function SellOpportunitiesTab() {
  const navigate = useNavigate();
  const [data, setData] = useState<BrowseResponse<SellOpportunity> | null>(null);
  const [filters, setFilters] = useState<SellOppFilters | null>(null);
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");
  const [owner, setOwner] = useState("");
  const [region, setRegion] = useState("");
  const [staleOnly, setStaleOnly] = useState(false);

  useEffect(() => {
    fetchApi<SellOppFilters>("/sell-opportunities/filters").then(setFilters);
  }, []);

  useEffect(() => {
    const params: Record<string, string> = {
      page: String(page),
      per_page: "25",
    };
    if (status) params.status = status;
    if (owner) params.owner = owner;
    if (region) params.region = region;
    if (staleOnly) params.stale_only = "true";

    fetchApi<BrowseResponse<SellOpportunity>>("/sell-opportunities", params).then(setData);
  }, [page, status, owner, region, staleOnly]);

  return (
    <div>
      {/* Filters */}
      <div className="flex items-center gap-3 mb-4 flex-wrap">
        <Select.Root value={status} onValueChange={(v) => { setStatus(v === "all" ? "" : v); setPage(1); }}>
          <Select.Trigger placeholder="Status" variant="soft" />
          <Select.Content>
            <Select.Item value="all">All Statuses</Select.Item>
            <Select.Item value="active">Active</Select.Item>
            <Select.Item value="on_hold">On Hold</Select.Item>
            <Select.Item value="matched">Matched</Select.Item>
            <Select.Item value="closed_won">Closed Won</Select.Item>
            <Select.Item value="closed_lost">Closed Lost</Select.Item>
          </Select.Content>
        </Select.Root>

        {filters?.regions && filters.regions.length > 0 && (
          <Select.Root value={region} onValueChange={(v) => { setRegion(v === "all" ? "" : v); setPage(1); }}>
            <Select.Trigger placeholder="Region" variant="soft" />
            <Select.Content>
              <Select.Item value="all">All Regions</Select.Item>
              {filters.regions.map((r) => (
                <Select.Item key={r} value={r}>{r}</Select.Item>
              ))}
            </Select.Content>
          </Select.Root>
        )}

        {filters?.owners && filters.owners.length > 0 && (
          <Select.Root value={owner} onValueChange={(v) => { setOwner(v === "all" ? "" : v); setPage(1); }}>
            <Select.Trigger placeholder="Owner" variant="soft" />
            <Select.Content>
              <Select.Item value="all">All Owners</Select.Item>
              {filters.owners.map((o) => (
                <Select.Item key={o} value={o}>{o}</Select.Item>
              ))}
            </Select.Content>
          </Select.Root>
        )}

        <label className="flex items-center gap-1.5 cursor-pointer">
          <input
            type="checkbox"
            checked={staleOnly}
            onChange={(e) => { setStaleOnly(e.target.checked); setPage(1); }}
            className="accent-[var(--jade-9)]"
          />
          <Text size="2" style={{ color: "var(--gray-11)" }}>Stale only</Text>
        </label>

        {data && (
          <Text size="2" style={{ color: "var(--gray-9)" }} className="ml-auto">
            {data.total} {data.total === 1 ? "opportunity" : "opportunities"}
          </Text>
        )}
      </div>

      {/* Table */}
      <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="bg-[var(--gray-2)]">
              <th className="text-left px-4 py-2.5 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Property</th>
              <th className="text-left px-4 py-2.5 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Region</th>
              <th className="text-left px-4 py-2.5 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Seller</th>
              <th className="text-right px-4 py-2.5 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Deal Value</th>
              <th className="text-left px-4 py-2.5 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Status</th>
              <th className="text-left px-4 py-2.5 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Owner</th>
              <th className="text-right px-4 py-2.5 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Last Activity</th>
            </tr>
          </thead>
          <tbody>
            {data?.results.map((opp) => (
              <tr
                key={opp.id}
                onClick={() => navigate(`/opportunities/sell/${opp.id}`)}
                className="cursor-pointer hover:bg-[var(--gray-2)] border-t border-[var(--gray-4)]"
              >
                <td className="px-4 py-3">
                  <Text size="2" weight="medium">{opp.display_address}</Text>
                  {opp.city && (
                    <Text size="1" className="block" style={{ color: "var(--gray-9)" }}>{opp.city}</Text>
                  )}
                </td>
                <td className="px-4 py-3">
                  <Text size="2" style={{ color: "var(--gray-11)" }}>{opp.region || "—"}</Text>
                </td>
                <td className="px-4 py-3">
                  <Text size="2" style={{ color: "var(--gray-11)" }}>
                    {opp.seller_contact_name || opp.seller_group_name || "—"}
                  </Text>
                </td>
                <td className="px-4 py-3 text-right">
                  <Text size="2" weight="medium">{formatCurrency(opp.deal_value)}</Text>
                </td>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-1.5">
                    <Badge size="1" color={sellOppStatusColor(opp.status)} variant="soft">
                      {sellOppStatusLabel(opp.status)}
                    </Badge>
                    {opp.is_stale === 1 && (
                      <Warning size={14} weight="fill" style={{ color: "var(--tomato-9)" }} />
                    )}
                  </div>
                </td>
                <td className="px-4 py-3">
                  <Text size="2" style={{ color: "var(--gray-11)" }}>{opp.owner || "—"}</Text>
                </td>
                <td className="px-4 py-3 text-right">
                  <Text size="2" style={{ color: opp.is_stale ? "var(--tomato-11)" : "var(--gray-9)" }}>
                    {opp.days_since_activity}d ago
                  </Text>
                </td>
              </tr>
            ))}
            {data && data.results.length === 0 && (
              <tr>
                <td colSpan={7} className="px-4 py-8 text-center">
                  <Text size="2" style={{ color: "var(--gray-9)" }}>No sell opportunities found.</Text>
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {data && data.pages > 1 && (
        <div className="flex items-center justify-between mt-4">
          <Text size="2" style={{ color: "var(--gray-9)" }}>
            Page {data.page} of {data.pages}
          </Text>
          <div className="flex gap-2">
            <button
              disabled={page <= 1}
              onClick={() => setPage((p) => p - 1)}
              className="px-3 py-1 text-sm rounded border border-[var(--gray-6)] disabled:opacity-40 hover:bg-[var(--gray-2)]"
              style={{ color: "var(--gray-11)" }}
            >
              Previous
            </button>
            <button
              disabled={page >= (data?.pages || 1)}
              onClick={() => setPage((p) => p + 1)}
              className="px-3 py-1 text-sm rounded border border-[var(--gray-6)] disabled:opacity-40 hover:bg-[var(--gray-2)]"
              style={{ color: "var(--gray-11)" }}
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Buy Mandates Tab ──

function BuyMandatesTab() {
  const navigate = useNavigate();
  const [data, setData] = useState<BrowseResponse<BuyMandate> | null>(null);
  const [filters, setFilters] = useState<BuyMandateFilters | null>(null);
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");
  const [owner, setOwner] = useState("");
  const [staleOnly, setStaleOnly] = useState(false);

  useEffect(() => {
    fetchApi<BuyMandateFilters>("/buy-mandates/filters").then(setFilters);
  }, []);

  useEffect(() => {
    const params: Record<string, string> = {
      page: String(page),
      per_page: "25",
    };
    if (status) params.status = status;
    if (owner) params.owner = owner;
    if (staleOnly) params.stale_only = "true";

    fetchApi<BrowseResponse<BuyMandate>>("/buy-mandates", params).then(setData);
  }, [page, status, owner, staleOnly]);

  function formatCriteriaSummary(criteria: BuyMandate["criteria"]): string {
    const parts: string[] = [];
    if (criteria?.asset_classes?.length) parts.push(criteria.asset_classes.join(", "));
    if (criteria?.regions?.length) parts.push(criteria.regions.join(", "));
    if (criteria?.cities?.length) parts.push(criteria.cities.join(", "));
    if (criteria?.price_min || criteria?.price_max) {
      const min = criteria.price_min ? formatCurrency(criteria.price_min) : "any";
      const max = criteria.price_max ? formatCurrency(criteria.price_max) : "any";
      parts.push(`${min}–${max}`);
    }
    return parts.length > 0 ? parts.join(" · ") : "No criteria set";
  }

  return (
    <div>
      {/* Filters */}
      <div className="flex items-center gap-3 mb-4 flex-wrap">
        <Select.Root value={status} onValueChange={(v) => { setStatus(v === "all" ? "" : v); setPage(1); }}>
          <Select.Trigger placeholder="Status" variant="soft" />
          <Select.Content>
            <Select.Item value="all">All Statuses</Select.Item>
            <Select.Item value="active">Active</Select.Item>
            <Select.Item value="on_hold">On Hold</Select.Item>
            <Select.Item value="fulfilled">Fulfilled</Select.Item>
          </Select.Content>
        </Select.Root>

        {filters?.owners && filters.owners.length > 0 && (
          <Select.Root value={owner} onValueChange={(v) => { setOwner(v === "all" ? "" : v); setPage(1); }}>
            <Select.Trigger placeholder="Owner" variant="soft" />
            <Select.Content>
              <Select.Item value="all">All Owners</Select.Item>
              {filters.owners.map((o) => (
                <Select.Item key={o} value={o}>{o}</Select.Item>
              ))}
            </Select.Content>
          </Select.Root>
        )}

        <label className="flex items-center gap-1.5 cursor-pointer">
          <input
            type="checkbox"
            checked={staleOnly}
            onChange={(e) => { setStaleOnly(e.target.checked); setPage(1); }}
            className="accent-[var(--jade-9)]"
          />
          <Text size="2" style={{ color: "var(--gray-11)" }}>Stale only</Text>
        </label>

        {data && (
          <Text size="2" style={{ color: "var(--gray-9)" }} className="ml-auto">
            {data.total} {data.total === 1 ? "mandate" : "mandates"}
          </Text>
        )}
      </div>

      {/* Table */}
      <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="bg-[var(--gray-2)]">
              <th className="text-left px-4 py-2.5 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Buyer</th>
              <th className="text-left px-4 py-2.5 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Criteria</th>
              <th className="text-left px-4 py-2.5 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Status</th>
              <th className="text-left px-4 py-2.5 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Owner</th>
              <th className="text-right px-4 py-2.5 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Last Activity</th>
            </tr>
          </thead>
          <tbody>
            {data?.results.map((mandate) => (
              <tr
                key={mandate.id}
                onClick={() => navigate(`/opportunities/buy/${mandate.id}`)}
                className="cursor-pointer hover:bg-[var(--gray-2)] border-t border-[var(--gray-4)]"
              >
                <td className="px-4 py-3">
                  <Text size="2" weight="medium">
                    {mandate.contact_name || mandate.group_name || "—"}
                  </Text>
                  <Text size="1" className="block" style={{ color: "var(--gray-9)" }}>
                    {mandate.id}
                  </Text>
                </td>
                <td className="px-4 py-3">
                  <Text size="2" style={{ color: "var(--gray-11)" }}>
                    {formatCriteriaSummary(mandate.criteria)}
                  </Text>
                </td>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-1.5">
                    <Badge size="1" color={buyMandateStatusColor(mandate.status)} variant="soft">
                      {buyMandateStatusLabel(mandate.status)}
                    </Badge>
                    {mandate.is_stale === 1 && (
                      <Warning size={14} weight="fill" style={{ color: "var(--tomato-9)" }} />
                    )}
                  </div>
                </td>
                <td className="px-4 py-3">
                  <Text size="2" style={{ color: "var(--gray-11)" }}>{mandate.owner || "—"}</Text>
                </td>
                <td className="px-4 py-3 text-right">
                  <Text size="2" style={{ color: mandate.is_stale ? "var(--tomato-11)" : "var(--gray-9)" }}>
                    {mandate.days_since_activity}d ago
                  </Text>
                </td>
              </tr>
            ))}
            {data && data.results.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center">
                  <Text size="2" style={{ color: "var(--gray-9)" }}>No buy mandates found.</Text>
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {data && data.pages > 1 && (
        <div className="flex items-center justify-between mt-4">
          <Text size="2" style={{ color: "var(--gray-9)" }}>
            Page {data.page} of {data.pages}
          </Text>
          <div className="flex gap-2">
            <button
              disabled={page <= 1}
              onClick={() => setPage((p) => p - 1)}
              className="px-3 py-1 text-sm rounded border border-[var(--gray-6)] disabled:opacity-40 hover:bg-[var(--gray-2)]"
              style={{ color: "var(--gray-11)" }}
            >
              Previous
            </button>
            <button
              disabled={page >= (data?.pages || 1)}
              onClick={() => setPage((p) => p + 1)}
              className="px-3 py-1 text-sm rounded border border-[var(--gray-6)] disabled:opacity-40 hover:bg-[var(--gray-2)]"
              style={{ color: "var(--gray-11)" }}
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Main Page ──

export default function OpportunitiesPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const tab = searchParams.get("tab") || "sell";

  return (
    <div className="p-6">
      <div className="flex items-center gap-3 mb-6">
        <Heading size="6">Opportunities</Heading>
      </div>

      <Tabs.Root
        value={tab}
        onValueChange={(v) => setSearchParams({ tab: v })}
      >
        <Tabs.List>
          <Tabs.Trigger value="sell">
            <Storefront size={16} className="mr-1.5" />
            Sell Opportunities
          </Tabs.Trigger>
          <Tabs.Trigger value="buy">
            <ShoppingCart size={16} className="mr-1.5" />
            Buy Mandates
          </Tabs.Trigger>
        </Tabs.List>

        <div className="mt-4">
          <Tabs.Content value="sell">
            <SellOpportunitiesTab />
          </Tabs.Content>
          <Tabs.Content value="buy">
            <BuyMandatesTab />
          </Tabs.Content>
        </div>
      </Tabs.Root>
    </div>
  );
}
