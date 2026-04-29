import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Heading, Text, Badge } from "@radix-ui/themes";
import { fetchApi } from "../api/client";
import type { AddressUnitSummary } from "../types";
import { UNIQUELY_TENANTED_DOMINANCE_THRESHOLD } from "../lib/explorerConstants";
import ExplorerTabs from "../components/explorer/ExplorerTabs";
import AddressTabs from "../components/explorer/AddressTabs";


function unitTitle(u: AddressUnitSummary): string {
  const parts = [
    u.street_number,
    u.street_name,
    u.street_suffix,
    u.street_direction,
    u.suite_type,
    u.suite_number,
  ].filter(Boolean);
  return parts.join(' ');
}


export default function ExplorerAddressUnitDetail() {
  const { key } = useParams<{ key: string }>();
  const [data, setData] = useState<AddressUnitSummary | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!key) return;
    fetchApi<AddressUnitSummary>(`/explorer/addresses/units/${encodeURIComponent(key)}`)
      .then(setData).catch((e) => setErr(String(e)));
  }, [key]);

  if (err) return <div className="p-6"><Text color="tomato">{err}</Text></div>;
  if (!data) return <div className="p-6"><Text size="2" style={{ color: "var(--gray-9)" }}>Loading…</Text></div>;

  // Reconstruct the root key for the back link
  const rootKey = `${data.street_number}|${data.street_name}`;
  const rootHref = `/explorer/addresses/roots/${encodeURIComponent(rootKey)}?city=${encodeURIComponent(data.city)}`;

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <ExplorerTabs />
      <AddressTabs />
      <Link to={rootHref} className="text-[13px] no-underline"
            style={{ color: "var(--accent-11)" }}>
        ← Address Root: {data.street_number} {data.street_name}
      </Link>

      <div className="flex items-baseline gap-3 mt-2 mb-5 flex-wrap">
        <Heading size="6" className="font-mono">{unitTitle(data)}</Heading>
        <Text size="2" style={{ color: "var(--gray-9)" }}>{data.city}</Text>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Parties" value={data.n_party_sides.toLocaleString()} />
        <StatCard label="Distinct stems" value={data.n_distinct_brand_stems.toLocaleString()} />
        <StatCard label="Dominant stem"
                  value={data.dominant_stem ? data.dominant_stem : '—'} />
        <StatCard label="Dominance share"
                  value={data.dominance_share != null
                    ? `${(data.dominance_share * 100).toFixed(0)}%`
                    : '—'} />
      </div>

      {data.dominant_stem && data.dominance_share != null && data.dominance_share >= UNIQUELY_TENANTED_DOMINANCE_THRESHOLD && (
        <div className="mt-4">
          <Badge color="jade">
            uniquely tenanted → {data.dominant_stem}
          </Badge>
        </div>
      )}
    </div>
  );
}


function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
      <Text size="1" style={{ color: "var(--gray-9)" }}>{label}</Text>
      <Heading size="5" mt="2">{value}</Heading>
    </div>
  );
}
