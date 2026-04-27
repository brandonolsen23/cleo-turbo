import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Heading, Text, Button, TextField } from "@radix-ui/themes";
import { fetchApi } from "../api/client";
import type { AddressRootListResponse, AddressRootSummary } from "../types";
import ExplorerTabs from "../components/explorer/ExplorerTabs";
import AddressTabs from "../components/explorer/AddressTabs";

function formatRoot(r: { street_number: string; street_name: string }) {
  return [r.street_number, r.street_name].filter(Boolean).join(" ");
}

export default function ExplorerAddressRoots() {
  const nav = useNavigate();
  const [data, setData] = useState<AddressRootListResponse | null>(null);
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const perPage = 100;

  useEffect(() => {
    fetchApi<AddressRootListResponse>("/explorer/addresses/roots", {
      q, page, per_page: perPage,
    }).then(setData).catch((e) => console.error(e));
  }, [q, page]);

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <ExplorerTabs />
      <AddressTabs />
      <div className="flex items-baseline gap-4 mb-2">
        <Heading size="6">Address Roots</Heading>
        <Text size="2" style={{ color: "var(--gray-9)" }}>
          Root pairs (street_number + street_name) from party_fingerprints. Click
          a root to see how it splits across suffixes, suites, and postals.
        </Text>
      </div>

      <div className="flex items-center gap-4 my-5 flex-wrap">
        <TextField.Root size="2" placeholder="Filter by number or name…"
                        value={q} onChange={(e) => { setPage(1); setQ(e.target.value); }}
                        style={{ width: 320 }} />
        {data && (
          <Text size="2" style={{ color: "var(--gray-9)" }}>
            {data.total.toLocaleString()} address roots
          </Text>
        )}
      </div>

      <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] overflow-hidden">
        <table className="w-full text-[13px]">
          <thead className="bg-[var(--gray-2)]">
            <tr style={{ color: "var(--gray-9)" }}>
              <th className="text-left p-2 font-medium">root address</th>
              <th className="text-right p-2 font-medium">n_party_sides</th>
              <th className="text-right p-2 font-medium">n_distinct_suffixes</th>
              <th className="text-right p-2 font-medium">n_distinct_suites</th>
              <th className="text-right p-2 font-medium">n_distinct_postals</th>
            </tr>
          </thead>
          <tbody>
            {data?.results.map((r: AddressRootSummary) => (
              <tr key={r.key}
                  className="border-t border-[var(--gray-4)] hover:bg-[var(--gray-2)] cursor-pointer"
                  onClick={() => nav(`/explorer/addresses/roots/${encodeURIComponent(r.key)}`)}>
                <td className="p-2 font-mono">{formatRoot(r)}</td>
                <td className="p-2 text-right">{r.n_party_sides.toLocaleString()}</td>
                <td className="p-2 text-right">{r.n_distinct_suffixes.toLocaleString()}</td>
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
