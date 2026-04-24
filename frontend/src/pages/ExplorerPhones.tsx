import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Heading, Text, Button, TextField } from "@radix-ui/themes";
import { fetchApi } from "../api/client";
import { formatPhone } from "../lib/utils";
import type { PhoneListResponse, PhoneSummary } from "../types";
import ExplorerTabs from "../components/explorer/ExplorerTabs";

export default function ExplorerPhones() {
  const nav = useNavigate();
  const [data, setData] = useState<PhoneListResponse | null>(null);
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const perPage = 100;

  useEffect(() => {
    fetchApi<PhoneListResponse>("/explorer/phones", {
      q,
      page,
      per_page: perPage,
    })
      .then(setData)
      .catch((e) => console.error(e));
  }, [q, page]);

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <ExplorerTabs />
      <div className="flex items-baseline gap-4 mb-2">
        <Heading size="6">Phones</Heading>
        <Text size="2" style={{ color: "var(--gray-9)" }}>
          Digit-only normalized phones from party_fingerprints. Each row
          surfaces one distinct phone and how many party-sides carry it.
        </Text>
      </div>

      <div className="flex items-center gap-4 my-5 flex-wrap">
        <TextField.Root
          size="2"
          placeholder="Filter phone (digits or partial)…"
          value={q}
          onChange={(e) => {
            setPage(1);
            setQ(e.target.value);
          }}
          style={{ width: 280 }}
        />
        {data && (
          <Text size="2" style={{ color: "var(--gray-9)" }}>
            {data.total.toLocaleString()} phones
          </Text>
        )}
      </div>

      <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] overflow-hidden">
        <table className="w-full text-[13px]">
          <thead className="bg-[var(--gray-2)]">
            <tr style={{ color: "var(--gray-9)" }}>
              <th className="text-left p-2 font-medium">phone (raw)</th>
              <th className="text-left p-2 font-medium">phone (formatted)</th>
              <th className="text-right p-2 font-medium">n_party_sides</th>
            </tr>
          </thead>
          <tbody>
            {data?.results.map((t: PhoneSummary) => (
              <tr
                key={t.phone}
                className="border-t border-[var(--gray-4)] hover:bg-[var(--gray-2)] cursor-pointer"
                onClick={() =>
                  nav(`/explorer/phones/${encodeURIComponent(t.phone)}`)
                }
              >
                <td className="p-2 font-mono">{t.phone}</td>
                <td className="p-2">{formatPhone(t.phone)}</td>
                <td className="p-2 text-right">
                  {t.n_party_sides.toLocaleString()}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {data && data.pages > 1 && (
        <div className="flex items-center gap-2 mt-4">
          <Button
            size="1"
            variant="soft"
            disabled={page === 1}
            onClick={() => setPage(page - 1)}
          >
            Previous
          </Button>
          <Text size="2" style={{ color: "var(--gray-9)" }}>
            Page {page} of {data.pages}
          </Text>
          <Button
            size="1"
            variant="soft"
            disabled={page === data.pages}
            onClick={() => setPage(page + 1)}
          >
            Next
          </Button>
        </div>
      )}
    </div>
  );
}
