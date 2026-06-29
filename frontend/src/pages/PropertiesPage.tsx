import { useState, useEffect, useRef, useCallback } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Heading, Text, Button, Badge } from "@radix-ui/themes";
import { MagnifyingGlass, CaretUp, CaretDown } from "@phosphor-icons/react";
import { fetchApi } from "../api/client";
import { formatCurrency, formatDate, assetClassLabel, formatOwnership } from "../lib/utils";
import FilterPanel, {
  RangeFilter,
  SelectFilter,
} from "../components/ui/FilterPanel";
import type {
  PropertyBrowseItem,
  BrowseResponse,
  FilterOptions,
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

export default function PropertiesPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  // Derive state from URL params
  const page = Number(searchParams.get("page") || "1");
  const sort = searchParams.get("sort") || "most_recent_sale_date";
  const order = searchParams.get("order") || "desc";
  const q = searchParams.get("q") || "";

  // Filters from URL
  const city = searchParams.get("city") || "";
  const region = searchParams.get("region") || "";
  const assetClass = searchParams.get("asset_class") || "";
  const minPrice = searchParams.get("min_price") || "";
  const maxPrice = searchParams.get("max_price") || "";
  const brand = searchParams.get("brand") || "";
  const category = searchParams.get("category") || "";
  const minOwnership = searchParams.get("min_ownership_years") || "";
  const maxOwnership = searchParams.get("max_ownership_years") || "";
  const minBuildingSize = searchParams.get("building_size_min") || "";
  const maxBuildingSize = searchParams.get("building_size_max") || "";

  // Data state
  const [data, setData] = useState<BrowseResponse<PropertyBrowseItem> | null>(null);
  const [filterOptions, setFilterOptions] = useState<FilterOptions | null>(null);
  const [loading, setLoading] = useState(false);
  const [searchInput, setSearchInput] = useState(q);
  const [tenantMap, setTenantMap] = useState<Record<string, string[]>>({});
  const debounceRef = useRef<ReturnType<typeof setTimeout>>();

  // Load filter options + tenant map once
  useEffect(() => {
    fetchApi<FilterOptions>("/properties/filters").then(setFilterOptions);
    fetchApi<Record<string, string[]>>("/pois/tenant-map").then(setTenantMap);
  }, []);

  // Fetch data whenever URL params change
  const fetchData = useCallback(() => {
    setLoading(true);
    const params: Record<string, string> = {
      page: String(page),
      per_page: "25",
      sort,
      order,
    };
    if (q) params.q = q;
    if (city) params.city = city;
    if (region) params.region = region;
    if (assetClass) params.asset_class = assetClass;
    if (minPrice) params.min_price = minPrice;
    if (maxPrice) params.max_price = maxPrice;
    if (brand) params.brand = brand;
    if (category) params.category = category;
    if (minOwnership) params.min_ownership_years = minOwnership;
    if (maxOwnership) params.max_ownership_years = maxOwnership;
    if (minBuildingSize) params.building_size_min = minBuildingSize;
    if (maxBuildingSize) params.building_size_max = maxBuildingSize;

    fetchApi<BrowseResponse<PropertyBrowseItem>>("/properties", params)
      .then(setData)
      .finally(() => setLoading(false));
  }, [page, sort, order, q, city, region, assetClass, minPrice, maxPrice, brand, category, minOwnership, maxOwnership, minBuildingSize, maxBuildingSize]);

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
    city, region, assetClass, minPrice, maxPrice, brand, category, minOwnership, maxOwnership,
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

  return (
    <div className="flex flex-col gap-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <Heading size="5" weight="medium">
          Properties
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
          placeholder="Search properties..."
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
          label="Asset Class"
          value={assetClass}
          onChange={(v) => setParam("asset_class", v)}
          options={(filterOptions?.asset_classes || []).map((ac) => ({
            value: ac,
            label: assetClassLabel(ac),
          }))}
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
        <SelectFilter
          label="City"
          value={city}
          onChange={(v) => setParam("city", v)}
          options={(filterOptions?.cities || []).map((c) => ({
            value: c,
            label: c,
          }))}
        />
        <RangeFilter
          label="Sale Price"
          minValue={minPrice}
          maxValue={maxPrice}
          onMinChange={(v) => setParam("min_price", v)}
          onMaxChange={(v) => setParam("max_price", v)}
          placeholder={["Min $", "Max $"]}
        />
        <RangeFilter
          label="Ownership (yrs)"
          minValue={minOwnership}
          maxValue={maxOwnership}
          onMinChange={(v) => setParam("min_ownership_years", v)}
          onMaxChange={(v) => setParam("max_ownership_years", v)}
          placeholder={["Min yrs", "Max yrs"]}
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
          label="Tenant Brand"
          value={brand}
          onChange={(v) => setParam("brand", v)}
          options={(filterOptions?.brands || []).map((b) => ({
            value: b,
            label: b,
          }))}
        />
        <SelectFilter
          label="Tenant Category"
          value={category}
          onChange={(v) => setParam("category", v)}
          options={(filterOptions?.categories || []).map((c) => ({
            value: c,
            label: c,
          }))}
        />
      </FilterPanel>

      {/* Table */}
      <div
        className="rounded-[var(--card-radius)] border border-[var(--gray-6)] overflow-hidden transition-opacity"
        style={{ opacity: loading ? 0.6 : 1 }}
      >
        <table className="w-full text-[14px] [&_td]:whitespace-nowrap [&_th]:whitespace-nowrap">
          <thead>
            <tr style={{ background: "var(--gray-2)" }}>
              <SortHeader label="Address" field="display_address" currentSort={sort} currentOrder={order} onSort={handleSort} />
              <SortHeader label="City" field="city" currentSort={sort} currentOrder={order} onSort={handleSort} />
              <th className="text-left px-4 py-2 text-[12px] font-medium border-b border-[var(--gray-6)]" style={{ color: "var(--gray-9)" }}>
                Owner
              </th>
              <th className="text-left px-4 py-2 text-[12px] font-medium border-b border-[var(--gray-6)]" style={{ color: "var(--gray-9)" }}>
                Class
              </th>
              <th className="text-left px-4 py-2 text-[12px] font-medium border-b border-[var(--gray-6)]" style={{ color: "var(--gray-9)" }}>
                Tenants
              </th>
              <SortHeader label="Last Sale" field="most_recent_sale_date" currentSort={sort} currentOrder={order} onSort={handleSort} align="right" />
              <SortHeader label="Price" field="most_recent_sale_price" currentSort={sort} currentOrder={order} onSort={handleSort} align="right" />
              <SortHeader label="Ownership" field="ownership_years" currentSort={sort} currentOrder={order} onSort={handleSort} align="right" />
            </tr>
          </thead>
          <tbody>
            {data?.results.map((p) => (
              <tr
                key={p.id}
                className="border-b border-[var(--gray-4)] hover:bg-[var(--gray-a2)] cursor-pointer"
                onClick={() => navigate(`/properties/${p.id}`, { state: { from: "properties" } })}
              >
                <td className="px-4 py-2 font-medium">{p.display_address}</td>
                <td className="px-4 py-2">{p.city}</td>
                <td className="px-4 py-2" style={{ color: "var(--gray-11)" }}>
                  {p.current_owner_name || "—"}
                </td>
                <td className="px-4 py-2" style={{ color: "var(--gray-11)" }}>
                  {assetClassLabel(p.asset_class) !== "—" ? assetClassLabel(p.asset_class) : "—"}
                </td>
                <td className="px-4 py-2">
                  <div className="flex flex-wrap gap-1">
                    {(tenantMap[p.id] || []).slice(0, 3).map((b) => (
                      <Badge key={b} size="1" variant="outline" color="gray">
                        {b}
                      </Badge>
                    ))}
                    {(tenantMap[p.id]?.length ?? 0) > 3 && (
                      <Badge size="1" variant="outline" color="gray">
                        +{tenantMap[p.id].length - 3}
                      </Badge>
                    )}
                  </div>
                </td>
                <td className="px-4 py-2 text-right">{formatDate(p.most_recent_sale_date)}</td>
                <td className="px-4 py-2 text-right">{formatCurrency(p.most_recent_sale_price)}</td>
                <td className="px-4 py-2 text-right">{formatOwnership(p.ownership_years)}</td>
              </tr>
            ))}
            {data?.results.length === 0 && (
              <tr>
                <td colSpan={8} className="px-4 py-8 text-center" style={{ color: "var(--gray-9)" }}>
                  No properties match your filters.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

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
