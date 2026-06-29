import { useState, useEffect, useRef, useCallback } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Heading, Text, Button, Badge } from "@radix-ui/themes";
import { MagnifyingGlass, CaretUp, CaretDown } from "@phosphor-icons/react";
import { fetchApi } from "../api/client";
import { formatCompact, assetClassLabel, titleCase, formatDate } from "../lib/utils";
import { propertyTypeLabel, propertyTypeColor } from "../lib/theme";
import FilterPanel, {
  RangeFilter,
  SelectFilter,
  ComboFilter,
} from "../components/ui/FilterPanel";
import type {
  GroupBrowseItem,
  BrowseResponse,
  GroupFilterOptions,
} from "../types";
import { Reportable } from "../components/issues/IssueReporter";

// ── Tier badge helpers ─────────────────────────────────────────

const TIER_COLOR: Record<string, "jade" | "gray" | "amber" | "blue"> = {
  confirmed: "jade",
  probable: "blue",
  candidate: "amber",
  standalone: "gray",
};

function tierLabel(t: string): string {
  return t.charAt(0).toUpperCase() + t.slice(1);
}

// ── Sortable column header ─────────────────────────────────────

function SortHeader({
  label,
  field,
  currentSort,
  currentOrder,
  onSort,
  align = "left",
}: {
  label: string;
  field: string;
  currentSort: string;
  currentOrder: string;
  onSort: (f: string) => void;
  align?: "left" | "right";
}) {
  const active = currentSort === field;
  return (
    <th
      className={`${align === "right" ? "text-right" : "text-left"} px-4 py-2 text-[12px] font-medium border-b border-[var(--gray-6)] cursor-pointer select-none hover:bg-[var(--gray-3)] transition-colors`}
      style={{ color: active ? "var(--gray-12)" : "var(--gray-9)" }}
      onClick={() => onSort(field)}
    >
      <span className="inline-flex items-center gap-0.5">
        {label}
        {active &&
          (currentOrder === "asc" ? (
            <CaretUp size={11} weight="bold" />
          ) : (
            <CaretDown size={11} weight="bold" />
          ))}
      </span>
    </th>
  );
}

// ── Main page component ────────────────────────────────────────

export default function GroupsPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  // URL state
  const page = Number(searchParams.get("page") || "1");
  const sort = searchParams.get("sort") || "n_members";
  const order = searchParams.get("order") || "desc";
  const q = searchParams.get("q") || "";

  // Filters
  const tier = searchParams.get("tier") || "";
  const minMembers = searchParams.get("min_members") || "";
  const minProperties = searchParams.get("min_properties") || "";
  const maxProperties = searchParams.get("max_properties") || "";
  const minTransactions = searchParams.get("min_transactions") || "";
  const maxTransactions = searchParams.get("max_transactions") || "";
  const minPortfolioValue = searchParams.get("min_portfolio_value") || "";
  const maxPortfolioValue = searchParams.get("max_portfolio_value") || "";
  const minVelocity = searchParams.get("min_velocity") || "";
  const maxVelocity = searchParams.get("max_velocity") || "";
  const minNetAcquisitions = searchParams.get("min_net_acquisitions") || "";
  const maxNetAcquisitions = searchParams.get("max_net_acquisitions") || "";
  const assetClass = searchParams.get("asset_class") || "";
  const minAssetClassCount = searchParams.get("min_asset_class_count") || "";
  const maxAssetClassCount = searchParams.get("max_asset_class_count") || "";
  const region = searchParams.get("region") || "";

  // Data state
  const [data, setData] = useState<BrowseResponse<GroupBrowseItem> | null>(null);
  const [filterOptions, setFilterOptions] = useState<GroupFilterOptions | null>(null);
  const [loading, setLoading] = useState(false);
  const [searchInput, setSearchInput] = useState(q);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>();
  const fetchIdRef = useRef(0);

  // Load filter options once
  useEffect(() => {
    fetchApi<GroupFilterOptions>("/groups/filters").then(setFilterOptions);
  }, []);

  // Fetch data whenever URL params change
  const fetchData = useCallback(() => {
    setLoading(true);
    const currentFetchId = ++fetchIdRef.current;
    const params: Record<string, string> = {
      page: String(page),
      per_page: "100",
      sort,
      order,
    };
    if (q) params.q = q;
    if (tier) params.tier = tier;
    if (minMembers) params.min_members = minMembers;
    if (minProperties) params.min_properties = minProperties;
    if (maxProperties) params.max_properties = maxProperties;
    if (minTransactions) params.min_transactions = minTransactions;
    if (maxTransactions) params.max_transactions = maxTransactions;
    if (minPortfolioValue) params.min_portfolio_value = minPortfolioValue;
    if (maxPortfolioValue) params.max_portfolio_value = maxPortfolioValue;
    if (minVelocity) params.min_velocity = minVelocity;
    if (maxVelocity) params.max_velocity = maxVelocity;
    if (minNetAcquisitions) params.min_net_acquisitions = minNetAcquisitions;
    if (maxNetAcquisitions) params.max_net_acquisitions = maxNetAcquisitions;
    if (assetClass) params.asset_class = assetClass;
    if (minAssetClassCount) params.min_asset_class_count = minAssetClassCount;
    if (maxAssetClassCount) params.max_asset_class_count = maxAssetClassCount;
    if (region) params.region = region;

    fetchApi<BrowseResponse<GroupBrowseItem>>("/groups", params)
      .then((res) => {
        if (currentFetchId === fetchIdRef.current) setData(res);
      })
      .finally(() => {
        if (currentFetchId === fetchIdRef.current) setLoading(false);
      });
  }, [
    page, sort, order, q, tier, minMembers,
    minProperties, maxProperties,
    minTransactions, maxTransactions,
    minPortfolioValue, maxPortfolioValue,
    minVelocity, maxVelocity,
    minNetAcquisitions, maxNetAcquisitions,
    assetClass, minAssetClassCount, maxAssetClassCount, region,
  ]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const setParam = useCallback(
    (key: string, value: string) => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        if (value) next.set(key, value);
        else next.delete(key);
        if (key !== "page") next.set("page", "1");
        return next;
      });
    },
    [setSearchParams],
  );

  const handleSearchChange = (value: string) => {
    setSearchInput(value);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => setParam("q", value), 300);
  };

  const handleSort = (field: string) => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      if (sort === field) {
        next.set("order", order === "asc" ? "desc" : "asc");
      } else {
        next.set("sort", field);
        next.set("order", "desc");
      }
      next.set("page", "1");
      return next;
    });
  };

  const activeFilterCount = [
    tier, minMembers,
    minProperties, maxProperties,
    minTransactions, maxTransactions,
    minPortfolioValue, maxPortfolioValue,
    minVelocity, maxVelocity,
    minNetAcquisitions, maxNetAcquisitions,
    assetClass, region,
  ].filter(Boolean).length;

  const clearAllFilters = () => {
    setSearchParams((prev) => {
      const next = new URLSearchParams();
      const s = prev.get("sort"); const o = prev.get("order"); const qVal = prev.get("q");
      if (s) next.set("sort", s);
      if (o) next.set("order", o);
      if (qVal) next.set("q", qVal);
      next.set("page", "1");
      return next;
    });
  };

  return (
    <div className="flex flex-col gap-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <Heading size="5" weight="medium">Groups</Heading>
        <Text size="2" style={{ color: "var(--gray-9)" }}>
          {data ? `${data.total.toLocaleString()} results` : "Loading..."}
        </Text>
      </div>

      {/* Search bar */}
      <div className="relative">
        <MagnifyingGlass
          size={15}
          className="absolute left-2.5 top-1/2 -translate-y-1/2"
          style={{ color: "var(--gray-8)" }}
        />
        <input
          type="text"
          value={searchInput}
          onChange={(e) => handleSearchChange(e.target.value)}
          placeholder="Search groups..."
          className="w-full h-8 pl-8 pr-3 text-[13px] rounded-md border border-[var(--gray-6)] bg-white outline-none focus:border-[var(--accent-7)] transition-colors"
          style={{ color: "var(--gray-12)" }}
        />
      </div>

      {/* Filter panel */}
      <FilterPanel activeCount={activeFilterCount} onClearAll={clearAllFilters}>
        <SelectFilter
          label="Tier"
          value={tier}
          onChange={(v) => setParam("tier", v)}
          options={(filterOptions?.tiers || []).map((t) => ({ value: t, label: tierLabel(t) }))}
        />
        <RangeFilter
          label="Members"
          minValue={minMembers}
          maxValue=""
          onMinChange={(v) => setParam("min_members", v)}
          onMaxChange={() => {}}
          placeholder={["Min", ""]}
        />
        <RangeFilter
          label="Properties"
          minValue={minProperties}
          maxValue={maxProperties}
          onMinChange={(v) => setParam("min_properties", v)}
          onMaxChange={(v) => setParam("max_properties", v)}
          placeholder={["Min", "Max"]}
        />
        <RangeFilter
          label="Transactions"
          minValue={minTransactions}
          maxValue={maxTransactions}
          onMinChange={(v) => setParam("min_transactions", v)}
          onMaxChange={(v) => setParam("max_transactions", v)}
          placeholder={["Min", "Max"]}
        />
        <RangeFilter
          label="Portfolio Value"
          minValue={minPortfolioValue}
          maxValue={maxPortfolioValue}
          onMinChange={(v) => setParam("min_portfolio_value", v)}
          onMaxChange={(v) => setParam("max_portfolio_value", v)}
          placeholder={["Min $", "Max $"]}
        />
        <RangeFilter
          label="Net Acquisitions"
          minValue={minNetAcquisitions}
          maxValue={maxNetAcquisitions}
          onMinChange={(v) => setParam("min_net_acquisitions", v)}
          onMaxChange={(v) => setParam("max_net_acquisitions", v)}
          placeholder={["Min", "Max"]}
        />
        <RangeFilter
          label="Txns / Year"
          minValue={minVelocity}
          maxValue={maxVelocity}
          onMinChange={(v) => setParam("min_velocity", v)}
          onMaxChange={(v) => setParam("max_velocity", v)}
          placeholder={["Min", "Max"]}
        />
        <SelectFilter
          label="Region"
          value={region}
          onChange={(v) => setParam("region", v)}
          options={(filterOptions?.regions || []).map((r) => ({ value: r, label: r }))}
        />
        <ComboFilter
          label="Asset Class"
          selectValue={assetClass}
          numberValue={minAssetClassCount}
          maxNumberValue={maxAssetClassCount}
          onSelectChange={(v) => {
            setParam("asset_class", v);
            if (!v) {
              setParam("min_asset_class_count", "");
              setParam("max_asset_class_count", "");
            }
          }}
          onNumberChange={(v) => setParam("min_asset_class_count", v)}
          onMaxNumberChange={(v) => setParam("max_asset_class_count", v)}
          options={(filterOptions?.asset_classes || []).map((ac) => ({
            value: ac,
            label: assetClassLabel(ac),
          }))}
          selectPlaceholder="Any class"
          numberPlaceholder="Min"
          maxNumberPlaceholder="Max"
        />
      </FilterPanel>

      {/* Table */}
      <Reportable
        component="groups_list.table"
        data={{ sort, order, tier, total_in_filter: data?.total ?? null }}
        entity_type="general"
      >
      <div
        className="rounded-[var(--card-radius)] border border-[var(--gray-6)] overflow-hidden transition-opacity"
        style={{ opacity: loading ? 0.6 : 1 }}
      >
        <table className="w-full text-[14px] [&_td]:whitespace-nowrap [&_th]:whitespace-nowrap">
          <thead>
            <tr style={{ background: "var(--gray-2)" }}>
              <SortHeader label="Name" field="display_name" currentSort={sort} currentOrder={order} onSort={handleSort} />
              <SortHeader label="Tier" field="tier" currentSort={sort} currentOrder={order} onSort={handleSort} />
              <SortHeader label="SPVs" field="n_members" currentSort={sort} currentOrder={order} onSort={handleSort} align="right" />
              <SortHeader label="Props" field="property_count" currentSort={sort} currentOrder={order} onSort={handleSort} align="right" />
              <SortHeader label="Txns" field="transaction_count" currentSort={sort} currentOrder={order} onSort={handleSort} align="right" />
              <SortHeader label="Buy Value" field="total_buy_value" currentSort={sort} currentOrder={order} onSort={handleSort} align="right" />
              <SortHeader label="Sell Value" field="total_sell_value" currentSort={sort} currentOrder={order} onSort={handleSort} align="right" />
              <th className="text-left px-4 py-2 text-[12px] font-medium border-b border-[var(--gray-6)]" style={{ color: "var(--gray-9)" }}>
                Primary Type
              </th>
              <th className="text-left px-4 py-2 text-[12px] font-medium border-b border-[var(--gray-6)]" style={{ color: "var(--gray-9)" }}>
                Secondary Type
              </th>
              <th className="text-right px-4 py-2 text-[12px] font-medium border-b border-[var(--gray-6)]" style={{ color: "var(--gray-9)" }}>
                Engaged
              </th>
              <SortHeader label="Last Txn" field="last_transaction_date" currentSort={sort} currentOrder={order} onSort={handleSort} align="right" />
            </tr>
          </thead>
          <tbody>
            {data?.results.map((g) => (
              <tr
                key={g.id}
                className="border-b border-[var(--gray-4)] hover:bg-[var(--gray-a2)] cursor-pointer"
                onClick={() => navigate(`/groups/${g.id}`)}
              >
                <td className="px-4 py-2 font-medium" style={{ color: "var(--gray-12)" }}>
                  {titleCase(g.display_name)}
                </td>
                <td className="px-4 py-2">
                  <Badge size="1" color={TIER_COLOR[g.tier] || "gray"} variant="soft">
                    {tierLabel(g.tier)}
                  </Badge>
                </td>
                <td className="px-4 py-2 text-right">{g.n_members.toLocaleString()}</td>
                <td className="px-4 py-2 text-right">{g.property_count?.toLocaleString() ?? "—"}</td>
                <td className="px-4 py-2 text-right">{g.transaction_count?.toLocaleString() ?? "—"}</td>
                <td className="px-4 py-2 text-right" style={{ color: g.total_buy_value ? "var(--gray-11)" : "var(--gray-8)" }}>
                  {g.total_buy_value ? formatCompact(g.total_buy_value) : "—"}
                </td>
                <td className="px-4 py-2 text-right" style={{ color: g.total_sell_value ? "var(--gray-11)" : "var(--gray-8)" }}>
                  {g.total_sell_value ? formatCompact(g.total_sell_value) : "—"}
                </td>
                <td className="px-4 py-2">
                  {g.dominant_type ? (
                    <Badge size="1" color={propertyTypeColor(g.dominant_type)} variant="soft">
                      {propertyTypeLabel(g.dominant_type)}
                    </Badge>
                  ) : "—"}
                </td>
                <td className="px-4 py-2">
                  {g.secondary_type ? (
                    <Badge size="1" color={propertyTypeColor(g.secondary_type)} variant="soft">
                      {propertyTypeLabel(g.secondary_type)}
                    </Badge>
                  ) : "—"}
                </td>
                <td className="px-4 py-2 text-right">
                  {g.engaged_contact_count > 0 ? (
                    <Badge size="1" color="jade" variant="soft">
                      {g.engaged_contact_count} of {g.contact_count}
                    </Badge>
                  ) : (
                    <Text size="1" style={{ color: "var(--gray-8)" }}>—</Text>
                  )}
                </td>
                <td className="px-4 py-2 text-right" style={{ color: "var(--gray-11)" }}>
                  {g.last_transaction_date ? formatDate(g.last_transaction_date) : "—"}
                </td>
              </tr>
            ))}
            {data?.results.length === 0 && (
              <tr>
                <td colSpan={11} className="px-4 py-12 text-center" style={{ color: "var(--gray-9)" }}>
                  No groups match your filters.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      </Reportable>

      {/* Pagination */}
      {data && (
        <div className="flex items-center justify-between">
          <Text size="2" style={{ color: "var(--gray-9)" }}>
            Page {data.page} of {data.pages}
          </Text>
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
