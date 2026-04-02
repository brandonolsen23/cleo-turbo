import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Heading, Text, Button, TextField, Badge } from "@radix-ui/themes";
import { fetchApi } from "../api/client";
import { formatCurrency, formatDate } from "../lib/utils";
import { categoryColor } from "../lib/theme";
import type { PropertyBrowseItem, BrowseResponse, SearchResponse, FilterOptions } from "../types";

export default function PropertiesPage() {
  const navigate = useNavigate();
  const [data, setData] = useState<BrowseResponse<PropertyBrowseItem> | null>(null);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [searchResults, setSearchResults] = useState<SearchResponse<PropertyBrowseItem> | null>(null);
  const [filters, setFilters] = useState<FilterOptions | null>(null);
  const [brandFilter, setBrandFilter] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [tenantMap, setTenantMap] = useState<Record<string, string[]>>({});

  useEffect(() => {
    fetchApi<FilterOptions>("/properties/filters").then(setFilters);
    fetchApi<Record<string, string[]>>("/pois/tenant-map").then(setTenantMap);
  }, []);

  useEffect(() => {
    const params: Record<string, string> = { page: String(page), per_page: "25" };
    if (brandFilter) params.brand = brandFilter;
    if (categoryFilter) params.category = categoryFilter;
    fetchApi<BrowseResponse<PropertyBrowseItem>>("/properties", params).then(setData);
  }, [page, brandFilter, categoryFilter]);

  const handleSearch = async () => {
    if (!search.trim()) { setSearchResults(null); return; }
    const results = await fetchApi<SearchResponse<PropertyBrowseItem>>("/properties/search", { q: search, limit: "50" });
    setSearchResults(results);
  };

  const rows = searchResults?.results || data?.results || [];
  const total = searchResults?.total ?? data?.total ?? 0;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <Heading size="5" weight="medium">Properties</Heading>
        <Text size="2" style={{ color: "var(--gray-9)" }}>{total.toLocaleString()} total</Text>
      </div>
      <div className="flex gap-2">
        <TextField.Root
          value={search}
          onChange={(e: any) => setSearch(e.target.value)}
          onKeyDown={(e: any) => e.key === "Enter" && handleSearch()}
          placeholder="Search properties..."
          size="2"
          className="flex-1"
        />
        <Button size="2" onClick={handleSearch}>Search</Button>
        {searchResults && <Button size="2" variant="soft" onClick={() => { setSearchResults(null); setSearch(""); }}>Clear</Button>}
      </div>
      <div className="flex gap-2">
        <select
          value={categoryFilter}
          onChange={(e) => { setCategoryFilter(e.target.value); setPage(1); setSearchResults(null); }}
          className="h-8 px-2 text-[13px] rounded border border-[var(--gray-6)] bg-white"
        >
          <option value="">All Categories</option>
          {(filters?.categories || []).map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
        <select
          value={brandFilter}
          onChange={(e) => { setBrandFilter(e.target.value); setPage(1); setSearchResults(null); }}
          className="h-8 px-2 text-[13px] rounded border border-[var(--gray-6)] bg-white"
        >
          <option value="">All Brands</option>
          {(filters?.brands || []).map((b) => <option key={b} value={b}>{b}</option>)}
        </select>
        {(brandFilter || categoryFilter) && (
          <Button size="1" variant="ghost" onClick={() => { setBrandFilter(""); setCategoryFilter(""); setPage(1); }}>Clear Filters</Button>
        )}
      </div>
      <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] overflow-hidden">
        <table className="w-full text-[14px]">
          <thead>
            <tr style={{ background: "var(--gray-2)" }}>
              <th className="text-left px-4 py-2 text-[12px] font-medium border-b border-[var(--gray-6)]" style={{ color: "var(--gray-9)" }}>Address</th>
              <th className="text-left px-4 py-2 text-[12px] font-medium border-b border-[var(--gray-6)]" style={{ color: "var(--gray-9)" }}>City</th>
              <th className="text-left px-4 py-2 text-[12px] font-medium border-b border-[var(--gray-6)]" style={{ color: "var(--gray-9)" }}>Owner</th>
              <th className="text-left px-4 py-2 text-[12px] font-medium border-b border-[var(--gray-6)]" style={{ color: "var(--gray-9)" }}>Tenants</th>
              <th className="text-right px-4 py-2 text-[12px] font-medium border-b border-[var(--gray-6)]" style={{ color: "var(--gray-9)" }}>Last Sale</th>
              <th className="text-right px-4 py-2 text-[12px] font-medium border-b border-[var(--gray-6)]" style={{ color: "var(--gray-9)" }}>Price</th>
              <th className="text-right px-4 py-2 text-[12px] font-medium border-b border-[var(--gray-6)]" style={{ color: "var(--gray-9)" }}>Txns</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((p) => (
              <tr key={p.id} className="border-b border-[var(--gray-4)] hover:bg-[var(--gray-a2)] cursor-pointer"
                  onClick={() => navigate(`/properties/${p.id}`, { state: { from: "properties" } })}>
                <td className="px-4 py-2">{p.display_address}</td>
                <td className="px-4 py-2">{p.city}</td>
                <td className="px-4 py-2" style={{ color: "var(--gray-11)" }}>{p.current_owner_name || "—"}</td>
                <td className="px-4 py-2">
                  <div className="flex flex-wrap gap-1">
                    {(tenantMap[p.id] || []).slice(0, 3).map((b) => (
                      <Badge key={b} size="1" variant="outline" color="gray">{b}</Badge>
                    ))}
                    {(tenantMap[p.id]?.length ?? 0) > 3 && (
                      <Badge size="1" variant="outline" color="gray">+{tenantMap[p.id].length - 3}</Badge>
                    )}
                  </div>
                </td>
                <td className="px-4 py-2 text-right">{formatDate(p.most_recent_sale_date)}</td>
                <td className="px-4 py-2 text-right">{formatCurrency(p.most_recent_sale_price)}</td>
                <td className="px-4 py-2 text-right">{p.transaction_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!searchResults && data && (
        <div className="flex items-center justify-between">
          <Text size="2" style={{ color: "var(--gray-9)" }}>
            Page {data.page} of {data.pages}
          </Text>
          <div className="flex gap-2">
            <Button size="1" variant="soft" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</Button>
            <Button size="1" variant="soft" disabled={page >= data.pages} onClick={() => setPage(page + 1)}>Next</Button>
          </div>
        </div>
      )}
    </div>
  );
}
