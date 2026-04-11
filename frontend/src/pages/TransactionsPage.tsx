import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Heading, Text, Button, TextField } from "@radix-ui/themes";
import { fetchApi } from "../api/client";
import { formatCurrency, formatDate } from "../lib/utils";
import type { TransactionBrowseItem, BrowseResponse, SearchResponse } from "../types";

export default function TransactionsPage() {
  const navigate = useNavigate();
  const [data, setData] = useState<BrowseResponse<TransactionBrowseItem> | null>(null);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [searchResults, setSearchResults] = useState<SearchResponse<TransactionBrowseItem> | null>(null);
  const [sort, setSort] = useState("sale_date");
  const [order, setOrder] = useState("desc");

  useEffect(() => {
    fetchApi<BrowseResponse<TransactionBrowseItem>>("/transactions", {
      page: String(page), per_page: "25", sort, order,
    }).then(setData);
  }, [page, sort, order]);

  const handleSearch = async () => {
    if (!search.trim()) { setSearchResults(null); return; }
    const results = await fetchApi<SearchResponse<TransactionBrowseItem>>("/transactions/search", { q: search, limit: "50" });
    setSearchResults(results);
  };

  const handleSort = (col: string) => {
    if (sort === col) {
      setOrder(order === "desc" ? "asc" : "desc");
    } else {
      setSort(col);
      setOrder("desc");
    }
    setPage(1);
  };

  const sortIcon = (col: string) => {
    if (sort !== col) return null;
    return <span className="ml-1 text-[10px]">{order === "asc" ? "▲" : "▼"}</span>;
  };

  const rows = searchResults?.results || data?.results || [];
  const total = searchResults?.total ?? data?.total ?? 0;

  const firstParty = (parties: string[] | null) => {
    if (!parties || parties.length === 0) return "—";
    return parties[0];
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <Heading size="5" weight="medium">Transactions</Heading>
        <Text size="2" style={{ color: "var(--gray-9)" }}>{total.toLocaleString()} total</Text>
      </div>
      <div className="flex gap-2">
        <TextField.Root
          value={search}
          onChange={(e: any) => setSearch(e.target.value)}
          onKeyDown={(e: any) => e.key === "Enter" && handleSearch()}
          placeholder="Search by address..."
          size="2"
          className="flex-1"
        />
        <Button size="2" onClick={handleSearch}>Search</Button>
        {searchResults && (
          <Button size="2" variant="soft" onClick={() => { setSearchResults(null); setSearch(""); }}>Clear</Button>
        )}
      </div>
      <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] overflow-hidden">
        <table className="w-full text-[14px] [&_td]:whitespace-nowrap [&_th]:whitespace-nowrap">
          <thead>
            <tr style={{ background: "var(--gray-2)" }}>
              <th className="text-left px-4 py-2 text-[12px] font-medium border-b border-[var(--gray-6)] cursor-pointer select-none"
                  style={{ color: "var(--gray-9)" }} onClick={() => handleSort("display_address")}>
                Address{sortIcon("display_address")}
              </th>
              <th className="text-left px-4 py-2 text-[12px] font-medium border-b border-[var(--gray-6)] cursor-pointer select-none"
                  style={{ color: "var(--gray-9)" }} onClick={() => handleSort("city")}>
                City{sortIcon("city")}
              </th>
              <th className="text-left px-4 py-2 text-[12px] font-medium border-b border-[var(--gray-6)]" style={{ color: "var(--gray-9)" }}>
                Seller
              </th>
              <th className="text-left px-4 py-2 text-[12px] font-medium border-b border-[var(--gray-6)]" style={{ color: "var(--gray-9)" }}>
                Buyer
              </th>
              <th className="text-right px-4 py-2 text-[12px] font-medium border-b border-[var(--gray-6)] cursor-pointer select-none"
                  style={{ color: "var(--gray-9)" }} onClick={() => handleSort("sale_date")}>
                Date{sortIcon("sale_date")}
              </th>
              <th className="text-right px-4 py-2 text-[12px] font-medium border-b border-[var(--gray-6)] cursor-pointer select-none"
                  style={{ color: "var(--gray-9)" }} onClick={() => handleSort("sale_price")}>
                Price{sortIcon("sale_price")}
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((t) => (
              <tr key={t.source_id}
                  className="border-b border-[var(--gray-4)] hover:bg-[var(--gray-a2)] cursor-pointer"
                  onClick={() => navigate(`/transactions/${t.source_id}`)}>
                <td className="px-4 py-2">{t.display_address}</td>
                <td className="px-4 py-2">{t.city}</td>
                <td className="px-4 py-2" style={{ color: "var(--gray-11)" }}>{firstParty(t.seller_parties)}</td>
                <td className="px-4 py-2" style={{ color: "var(--gray-11)" }}>{firstParty(t.buyer_parties)}</td>
                <td className="px-4 py-2 text-right">{formatDate(t.sale_date)}</td>
                <td className="px-4 py-2 text-right">{formatCurrency(t.sale_price)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!searchResults && data && (
        <div className="flex items-center justify-between">
          <Text size="2" style={{ color: "var(--gray-9)" }}>Page {data.page} of {data.pages}</Text>
          <div className="flex gap-2">
            <Button size="1" variant="soft" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</Button>
            <Button size="1" variant="soft" disabled={page >= data.pages} onClick={() => setPage(page + 1)}>Next</Button>
          </div>
        </div>
      )}
    </div>
  );
}
