import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Heading, Text } from "@radix-ui/themes";
import { fetchApi } from "../api/client";
import type { AddressBaseDetail, AddressSuiteVariant } from "../types";
import PartySideCard from "../components/explorer/PartySideCard";
import ExplorerTabs from "../components/explorer/ExplorerTabs";
import AddressTabs from "../components/explorer/AddressTabs";

function formatBase(r: { street_number: string; street_name: string; street_suffix: string }) {
  return [r.street_number, r.street_name, r.street_suffix]
    .filter(Boolean).join(" ");
}

export default function ExplorerAddressDetail() {
  const { key } = useParams<{ key: string }>();
  const [data, setData] = useState<AddressBaseDetail | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!key) return;
    fetchApi<AddressBaseDetail>(`/explorer/addresses/${encodeURIComponent(key)}`)
      .then(setData).catch((e) => setErr(String(e)));
  }, [key]);

  if (err) {
    return (
      <div className="p-6 max-w-6xl mx-auto">
        <ExplorerTabs />
        <AddressTabs />
        <Text color="tomato">{err}</Text>
      </div>
    );
  }
  if (!data) {
    return (
      <div className="p-6 max-w-6xl mx-auto">
        <ExplorerTabs />
        <AddressTabs />
        <Text size="2" style={{ color: "var(--gray-9)" }}>Loading…</Text>
      </div>
    );
  }

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <ExplorerTabs />
      <AddressTabs />
      <Link to="/explorer/addresses/bases" className="text-[13px] no-underline"
            style={{ color: "var(--accent-11)" }}>
        ← Address Bases
      </Link>

      <div className="flex items-baseline gap-3 mt-2 mb-1 flex-wrap">
        <Heading size="6" className="font-mono">{formatBase(data)}</Heading>
      </div>

      <div className="grid grid-cols-3 gap-4 mt-5">
        <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
          <Text size="1" style={{ color: "var(--gray-9)" }}>Party-sides</Text>
          <Heading size="5" mt="2">{data.n_party_sides.toLocaleString()}</Heading>
        </div>
        <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
          <Text size="1" style={{ color: "var(--gray-9)" }}>Distinct suites</Text>
          <Heading size="5" mt="2">{data.n_distinct_suites.toLocaleString()}</Heading>
        </div>
        <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
          <Text size="1" style={{ color: "var(--gray-9)" }}>Distinct postals</Text>
          <Heading size="5" mt="2">{data.n_distinct_postals.toLocaleString()}</Heading>
        </div>
      </div>

      <Heading size="4" mt="6" mb="2">
        Suite variants ({data.suite_variants.length.toLocaleString()})
      </Heading>
      <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] overflow-hidden">
        <table className="w-full text-[13px]">
          <thead className="bg-[var(--gray-2)]">
            <tr style={{ color: "var(--gray-9)" }}>
              <th className="text-left p-2 font-medium">suite_type</th>
              <th className="text-left p-2 font-medium">suite_number</th>
              <th className="text-left p-2 font-medium">postal</th>
              <th className="text-right p-2 font-medium">n_party_sides</th>
            </tr>
          </thead>
          <tbody>
            {data.suite_variants.map((v: AddressSuiteVariant, i) => (
              <tr key={i} className="border-t border-[var(--gray-4)]">
                <td className="p-2">
                  {v.suite_type || <Text size="1" style={{ color: "var(--gray-9)" }}>—</Text>}
                </td>
                <td className="p-2">
                  {v.suite_number || <Text size="1" style={{ color: "var(--gray-9)" }}>—</Text>}
                </td>
                <td className="p-2 font-mono">
                  {v.postal || <Text size="1" style={{ color: "var(--gray-9)" }}>—</Text>}
                </td>
                <td className="p-2 text-right">{v.n_party_sides.toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Heading size="4" mt="6" mb="2">
        Party-sides ({data.party_sides.length.toLocaleString()})
      </Heading>
      <div className="flex flex-col gap-3">
        {data.party_sides.map((p) => (
          <PartySideCard key={`${p.source_id}-${p.side}`} partySide={p} />
        ))}
      </div>
    </div>
  );
}
