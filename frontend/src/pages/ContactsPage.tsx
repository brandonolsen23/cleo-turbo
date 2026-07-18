import { useState, useEffect, useRef, useCallback } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Heading, Text, Button, Badge } from "@radix-ui/themes";
import { MagnifyingGlass, CaretUp, CaretDown, Phone } from "@phosphor-icons/react";
import { fetchApi } from "../api/client";
import { formatPhone, formatCompact, assetClassLabel, titleCase } from "../lib/utils";
import { getContactTypeLabel } from "../types";
import { Reportable } from "../components/issues/IssueReporter";
import { propertyTypeLabel, propertyTypeColor } from "../lib/theme";
import FilterPanel, {
  RangeFilter,
  SelectFilter,
  ComboFilter,
} from "../components/ui/FilterPanel";
import type {
  ContactBrowseItem,
  BrowseResponse,
  ContactFilterOptions,
} from "../types";

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

export default function ContactsPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  // Derive state from URL params
  const page = Number(searchParams.get("page") || "1");
  const sort = searchParams.get("sort") || "last_seen_date";
  const order = searchParams.get("order") || "desc";
  const q = searchParams.get("q") || "";

  // Filters from URL
  const status = searchParams.get("status") || "";
  const contactType = searchParams.get("contact_type") || "";
  const minTransactions = searchParams.get("min_transactions") || "";
  const maxTransactions = searchParams.get("max_transactions") || "";
  const minBuyValue = searchParams.get("min_buy_value") || "";
  const maxBuyValue = searchParams.get("max_buy_value") || "";
  const minBuildingSize = searchParams.get("building_size_min") || "";
  const maxBuildingSize = searchParams.get("building_size_max") || "";
  const region = searchParams.get("region") || "";
  const assetClass = searchParams.get("asset_class") || "";
  const minAssetClassCount = searchParams.get("min_asset_class_count") || "";
  const maxAssetClassCount = searchParams.get("max_asset_class_count") || "";

  // Data state
  const [data, setData] = useState<BrowseResponse<ContactBrowseItem> | null>(null);
  const [filterOptions, setFilterOptions] = useState<ContactFilterOptions | null>(null);
  const [loading, setLoading] = useState(false);
  const [searchInput, setSearchInput] = useState(q);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>();
  const fetchIdRef = useRef(0);

  // Load filter options once
  useEffect(() => {
    fetchApi<ContactFilterOptions>("/contacts/filters").then(setFilterOptions);
  }, []);

  // Fetch data whenever URL params change (stale-response safe)
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
    if (status) params.status = status;
    if (contactType) params.contact_type = contactType;
    if (minTransactions) params.min_transactions = minTransactions;
    if (maxTransactions) params.max_transactions = maxTransactions;
    if (minBuyValue) params.min_buy_value = minBuyValue;
    if (maxBuyValue) params.max_buy_value = maxBuyValue;
    if (minBuildingSize) params.building_size_min = minBuildingSize;
    if (maxBuildingSize) params.building_size_max = maxBuildingSize;
    if (region) params.region = region;
    if (assetClass) params.asset_class = assetClass;
    if (minAssetClassCount) params.min_asset_class_count = minAssetClassCount;
    if (maxAssetClassCount) params.max_asset_class_count = maxAssetClassCount;

    fetchApi<BrowseResponse<ContactBrowseItem>>("/contacts", params)
      .then((res) => {
        // Only apply if this is still the latest request
        if (currentFetchId === fetchIdRef.current) setData(res);
      })
      .finally(() => {
        if (currentFetchId === fetchIdRef.current) setLoading(false);
      });
  }, [page, sort, order, q, status, contactType, minTransactions, maxTransactions, minBuyValue, maxBuyValue, minBuildingSize, maxBuildingSize, region, assetClass, minAssetClassCount, maxAssetClassCount]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // URL update helper
  const setParam = useCallback(
    (key: string, value: string) => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        if (value) {
          next.set(key, value);
        } else {
          next.delete(key);
        }
        if (key !== "page") next.set("page", "1");
        return next;
      });
    },
    [setSearchParams],
  );

  // Debounced search
  const handleSearchChange = (value: string) => {
    setSearchInput(value);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => setParam("q", value), 300);
  };

  // Sort toggling
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

  // Active filter count
  const activeFilterCount = [
    status, contactType, minTransactions, maxTransactions, minBuyValue, maxBuyValue, region, assetClass,
  ].filter(Boolean).length;

  const clearAllFilters = () => {
    setSearchParams((prev) => {
      const next = new URLSearchParams();
      const s = prev.get("sort");
      const o = prev.get("order");
      const qVal = prev.get("q");
      if (s) next.set("sort", s);
      if (o) next.set("order", o);
      if (qVal) next.set("q", qVal);
      next.set("page", "1");
      return next;
    });
  };

  // Contact type options from the CONTACT_TYPES constant
  const contactTypeOptions = (filterOptions?.contact_types || []).map((ct) => ({
    value: ct,
    label: getContactTypeLabel(ct),
  }));

  // Asset class options — we fetch from group filter options since they share the same set
  const [assetClassOptions, setAssetClassOptions] = useState<string[]>([]);
  useEffect(() => {
    fetchApi<{ asset_classes: string[] }>("/properties/filters").then((f) =>
      setAssetClassOptions(f.asset_classes || []),
    );
  }, []);

  return (
    <div className="flex flex-col gap-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <Heading size="5" weight="medium">
          Contacts
        </Heading>
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
          placeholder="Search contacts..."
          className="w-full h-8 pl-8 pr-3 text-[13px] rounded-md border border-[var(--gray-6)] bg-white outline-none focus:border-[var(--accent-7)] transition-colors"
          style={{ color: "var(--gray-12)" }}
        />
      </div>

      {/* Filter panel */}
      <FilterPanel
        activeCount={activeFilterCount}
        onClearAll={clearAllFilters}
      >
        <SelectFilter
          label="Status"
          value={status}
          onChange={(v) => setParam("status", v)}
          options={[
            { value: "pool", label: "Pool" },
            { value: "engaged", label: "Engaged" },
          ]}
        />
        <SelectFilter
          label="Contact Type"
          value={contactType}
          onChange={(v) => setParam("contact_type", v)}
          options={contactTypeOptions}
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
          label="Buy Value"
          minValue={minBuyValue}
          maxValue={maxBuyValue}
          onMinChange={(v) => setParam("min_buy_value", v)}
          onMaxChange={(v) => setParam("max_buy_value", v)}
          placeholder={["Min $", "Max $"]}
        />
        <RangeFilter
          label="Building Size (sf)"
          minValue={minBuildingSize}
          maxValue={maxBuildingSize}
          onMinChange={(v) => setParam("building_size_min", v)}
          onMaxChange={(v) => setParam("building_size_max", v)}
          placeholder={["Min sf", "Max sf"]}
        />
        <SelectFilter
          label="Region"
          value={region}
          onChange={(v) => setParam("region", v)}
          options={(filterOptions?.regions || []).map((r) => ({
            value: r,
            label: r,
          }))}
        />
        <ComboFilter
          label="Asset Class (owned)"
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
          options={assetClassOptions.map((ac) => ({
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
        component="contacts_list.table"
        data={{ sort, order, total_in_filter: data?.total ?? null }}
        entity_type="general"
      >
      <div
        className="rounded-[var(--card-radius)] border border-[var(--gray-6)] overflow-hidden transition-opacity"
        style={{ opacity: loading ? 0.6 : 1 }}
      >
        <table className="w-full table-fixed text-[14px] [&_td]:whitespace-nowrap [&_th]:whitespace-nowrap">
          <colgroup>
            <col />
            <col />
            <col style={{ width: 130 }} />
            <col style={{ width: 44 }} />
            <col style={{ width: 120 }} />
            <col style={{ width: 80 }} />
            <col style={{ width: 110 }} />
            <col style={{ width: 90 }} />
          </colgroup>
          <thead>
            <tr style={{ background: "var(--gray-2)" }}>
              <SortHeader label="Name" field="display_name" currentSort={sort} currentOrder={order} onSort={handleSort} />
              <th className="text-left px-4 py-2 text-[12px] font-medium border-b border-[var(--gray-6)]" style={{ color: "var(--gray-9)" }}>
                Group
              </th>
              <th className="text-left px-4 py-2 text-[12px] font-medium border-b border-[var(--gray-6)]" style={{ color: "var(--gray-9)" }}>
                City
              </th>
              <th className="text-center px-2 py-2 text-[12px] font-medium border-b border-[var(--gray-6)]" style={{ color: "var(--gray-9)", width: 40 }}>
                <Phone size={13} style={{ color: "var(--gray-9)", margin: "0 auto" }} />
              </th>
              <th className="text-left px-4 py-2 text-[12px] font-medium border-b border-[var(--gray-6)]" style={{ color: "var(--gray-9)" }}>
                Type
              </th>
              <SortHeader label="Txns" field="transaction_count" currentSort={sort} currentOrder={order} onSort={handleSort} align="right" />
              <SortHeader label="Buy Value" field="total_buy_value" currentSort={sort} currentOrder={order} onSort={handleSort} align="right" />
              <th className="text-left px-4 py-2 text-[12px] font-medium border-b border-[var(--gray-6)]" style={{ color: "var(--gray-9)" }}>
                Status
              </th>
            </tr>
          </thead>
          <tbody>
            {data?.results.map((c) => (
              <tr
                key={c.id}
                className="border-b border-[var(--gray-4)] hover:bg-[var(--gray-a2)] cursor-pointer"
                onClick={() => navigate(`/contacts/${c.id}`)}
              >
                <td className="px-4 py-2 font-medium max-w-[200px] truncate" title={c.display_name || undefined}>{c.display_name}</td>
                <td className="px-4 py-2 max-w-[260px] truncate" style={{ color: "var(--gray-11)" }}
                    title={c.auto_group_name ? titleCase(c.auto_group_name) : (c.company_name || undefined)}>
                  {c.auto_group_stem === "_anonymized_individuals"
                    ? "—"
                    : c.auto_group_name
                      ? titleCase(c.auto_group_name)
                      : (c.company_name || "—")}
                </td>
                <td className="px-4 py-2 max-w-[140px] truncate" style={{ color: "var(--gray-11)" }} title={c.mailing_city || undefined}>
                  {c.mailing_city || "—"}
                </td>
                <td className="px-2 py-2 text-center" style={{ width: 40 }}>
                  {c.phone ? (
                    <span className="inline-flex items-center justify-center" title={formatPhone(c.phone)}>
                      <Phone size={14} style={{ color: "var(--gray-9)" }} />
                    </span>
                  ) : null}
                </td>
                <td className="px-4 py-2">
                  {c.dominant_type ? (
                    <Badge size="1" color={propertyTypeColor(c.dominant_type)} variant="soft">
                      {propertyTypeLabel(c.dominant_type)}
                    </Badge>
                  ) : "—"}
                </td>
                <td className="px-4 py-2 text-right">{c.transaction_count}</td>
                <td className="px-4 py-2 text-right" style={{ color: c.total_buy_value ? "var(--gray-12)" : "var(--gray-8)" }}>
                  {c.total_buy_value ? formatCompact(c.total_buy_value) : "—"}
                </td>
                <td className="px-4 py-2">
                  <Badge
                    size="1"
                    color={c.status === "engaged" ? "jade" : "gray"}
                    variant={c.status === "engaged" ? "solid" : "soft"}
                  >
                    {c.status}
                  </Badge>
                </td>
              </tr>
            ))}
            {data?.results.length === 0 && (
              <tr>
                <td colSpan={8} className="px-4 py-12 text-center" style={{ color: "var(--gray-9)" }}>
                  {status === "engaged" ? (
                    <div className="flex flex-col items-center gap-1.5">
                      <Text size="2" weight="medium" style={{ color: "var(--gray-11)" }}>No engaged contacts yet</Text>
                      <Text size="2" style={{ color: "var(--gray-9)" }}>
                        Open a contact and click "Promote to Engaged" to track them here.
                      </Text>
                    </div>
                  ) : (
                    "No contacts match your filters."
                  )}
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
            <Button
              size="1"
              variant="soft"
              disabled={page <= 1}
              onClick={() => setParam("page", String(page - 1))}
            >
              Previous
            </Button>
            <Button
              size="1"
              variant="soft"
              disabled={page >= data.pages}
              onClick={() => setParam("page", String(page + 1))}
            >
              Next
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
