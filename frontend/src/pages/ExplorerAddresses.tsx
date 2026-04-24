import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Heading, Text, Button, TextField } from "@radix-ui/themes";
import { fetchApi } from "../api/client";
import type { AddressBaseListResponse, AddressBaseSummary } from "../types";
import ExplorerTabs from "../components/explorer/ExplorerTabs";

function formatBase(r: { street_number: string; street_name: string; street_suffix: string }) {
  return [r.street_number, r.street_name, r.street_suffix]
    .filter(Boolean).join(" ");
}

export default function ExplorerAddresses() {
  const nav = useNavigate();
  const [data, setData] = useState<AddressBaseListResponse | null>(null);
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const perPage = 100;

  useEffect(() => {
    fetchApi<AddressBaseListResponse>("/explorer/addresses", {
      q, page, per_page: perPage,
    }).then(setData).catch((e) => console.error(e));
  }, [q, page]);

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <ExplorerTabs />
      <div className="flex items-baseline gap-4 mb-2">
        <Heading size="6">Address Bases</Heading>
        <Text size="2" style={{ color: "var(--gray-9)" }}>
          Base triples (street_number + street_name + street_suffix) from
          party_fingerprints. Suite numbers, postals, and directions are surfaced
          per base on the detail page — useful for telling apart tenants within a
          high-rise office tower.
        </Text>
      </div>

      <div className="flex items-center gap-4 my-5 flex-wrap">
        <TextField.Root size="2" placeholder="Filter by number, name, or suffix…"
                        value={q} onChange={(e) => { setPage(1); setQ(e.target.value); }}
                        style={{ width: 320 }} />
        {data && (
          <Text size="2" style={{ color: "var(--gray-9)" }}>
            {data.total.toLocaleString()} address bases
          </Text>
        )}
      </div>

      <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] overflow-hidden">
        <table className="w-full text-[13px]">
          <thead className="bg-[var(--gray-2)]">
            <tr style={{ color: "var(--gray-9)" }}>
              <th className="text-left p-2 font-medium">base address</th>
              <th className="text-right p-2 font-medium">n_party_sides</th>
              <th className="text-right p-2 font-medium">n_distinct_suites</th>
              <th className="text-right p-2 font-medium">n_distinct_postals</th>
            </tr>
          </thead>
          <tbody>
            {data?.results.map((r: AddressBaseSummary) => (
              <tr key={r.key}
                  className="border-t border-[var(--gray-4)] hover:bg-[var(--gray-2)] cursor-pointer"
                  onClick={() => nav(`/explorer/addresses/${encodeURIComponent(r.key)}`)}>
                <td className="p-2 font-mono">{formatBase(r)}</td>
                <td className="p-2 text-right">{r.n_party_sides.toLocaleString()}</td>
                <td className="p-2 text-right">{r.n_distinct_suites.toLocaleString()}</td>
                <td className="p-2 text-right">{r.n_distinct_postals.toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {data && data.pages > 1 && (
        <div className="flex items-center gap-2 mt-4">
          <Button size="1" variant="soft" disabled={page === 1} onClick={() => setPage(page - 1)}>
            Previous
          </Button>
          <Text size="2" style={{ color: "var(--gray-9)" }}>
            Page {page} of {data.pages}
          </Text>
          <Button size="1" variant="soft" disabled={page === data.pages} onClick={() => setPage(page + 1)}>
            Next
          </Button>
        </div>
      )}
    </div>
  );
}
