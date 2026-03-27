import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Heading, Text, Button, TextField } from "@radix-ui/themes";
import { fetchApi } from "../api/client";
import { formatCurrency, formatDate } from "../lib/utils";
import type { PropertyBrowseItem, BrowseResponse, SearchResponse } from "../types";

export default function PropertiesPage() {
  const navigate = useNavigate();
  const [data, setData] = useState<BrowseResponse<PropertyBrowseItem> | null>(null);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [searchResults, setSearchResults] = useState<SearchResponse<PropertyBrowseItem> | null>(null);

  useEffect(() => {
    fetchApi<BrowseResponse<PropertyBrowseItem>>("/properties", { page: String(page), per_page: "25" }).then(setData);
  }, [page]);

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
      <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] overflow-hidden">
        <table className="w-full text-[14px]">
          <thead>
            <tr style={{ background: "var(--gray-2)" }}>
              <th className="text-left px-4 py-2 text-[12px] font-medium border-b border-[var(--gray-6)]" style={{ color: "var(--gray-9)" }}>Address</th>
              <th className="text-left px-4 py-2 text-[12px] font-medium border-b border-[var(--gray-6)]" style={{ color: "var(--gray-9)" }}>City</th>
              <th className="text-left px-4 py-2 text-[12px] font-medium border-b border-[var(--gray-6)]" style={{ color: "var(--gray-9)" }}>Owner</th>
              <th className="text-right px-4 py-2 text-[12px] font-medium border-b border-[var(--gray-6)]" style={{ color: "var(--gray-9)" }}>Last Sale</th>
              <th className="text-right px-4 py-2 text-[12px] font-medium border-b border-[var(--gray-6)]" style={{ color: "var(--gray-9)" }}>Price</th>
              <th className="text-right px-4 py-2 text-[12px] font-medium border-b border-[var(--gray-6)]" style={{ color: "var(--gray-9)" }}>Txns</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((p) => (
              <tr key={p.id} className="border-b border-[var(--gray-4)] hover:bg-[var(--gray-a2)] cursor-pointer"
                  onClick={() => navigate(`/properties/${p.id}`)}>
                <td className="px-4 py-2">{p.display_address}</td>
                <td className="px-4 py-2">{p.city}</td>
                <td className="px-4 py-2" style={{ color: "var(--gray-11)" }}>{p.current_owner_name || "—"}</td>
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
