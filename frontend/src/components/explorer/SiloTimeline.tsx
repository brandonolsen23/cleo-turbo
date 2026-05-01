import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Heading, Text, Badge } from "@radix-ui/themes";
import { fetchApi } from "../../api/client";
import { formatDate } from "../../lib/utils";
import type { SiloTimelineResponse, SiloTimelineTenure } from "../../types";


export type SiloAnchorType = 'phone' | 'address_unit' | 'contact';


function endpointFor(anchorType: SiloAnchorType, value: string): string {
  if (anchorType === 'phone') return `/explorer/phones/${encodeURIComponent(value)}/timeline`;
  if (anchorType === 'address_unit') return `/explorer/addresses/units/${encodeURIComponent(value)}/timeline`;
  return `/explorer/contacts/${encodeURIComponent(value)}/timeline`;
}


function tenureLabel(t: SiloTimelineTenure): string {
  return `${t.canonical_stem}: ${t.start_date} → ${t.end_date}`;
}


function TenureBar({ tenure }: { tenure: SiloTimelineTenure }) {
  const color = tenure.is_active ? 'jade' : 'gray';
  return (
    <div className="flex items-center gap-2 mb-1">
      <Badge color={color}>{tenureLabel(tenure)}</Badge>
      <Link to={`/explorer/auto-groups/${encodeURIComponent(tenure.auto_group_id)}`}
            className="text-[12px] no-underline" style={{ color: 'var(--accent-11)' }}>
        {tenure.auto_group_id}
      </Link>
      <Text size="1" style={{ color: 'var(--gray-9)' }}>
        {tenure.n_party_sides_in_window} parties
      </Text>
    </div>
  );
}


export default function SiloTimeline({
  anchorType, value,
}: {
  anchorType: SiloAnchorType;
  value: string;
}) {
  const [data, setData] = useState<SiloTimelineResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchApi<SiloTimelineResponse>(endpointFor(anchorType, value))
      .then((d) => { if (!cancelled) setData(d); })
      .catch((e) => { if (!cancelled) setErr(String(e)); });
    return () => { cancelled = true; };
  }, [anchorType, value]);

  if (err) return <Text color="tomato">{err}</Text>;
  if (!data) return <Text size="2" style={{ color: 'var(--gray-9)' }}>Loading timeline…</Text>;

  return (
    <div className="mt-6">
      <Heading size="3" mb="2">Timeline ({data.events.length.toLocaleString()} events)</Heading>

      {data.tenures.length === 0 ? (
        <Text size="2" style={{ color: 'var(--gray-9)' }} className="block mb-3">
          No tenures recorded — this anchor isn't yet attributed to any group.
        </Text>
      ) : (
        <div className="mb-3">
          {data.tenures.map((t, i) => <TenureBar key={i} tenure={t} />)}
        </div>
      )}

      {data.events.length === 0 ? (
        <Text size="2" style={{ color: 'var(--gray-9)' }}>No dated events.</Text>
      ) : (
        <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] overflow-hidden">
          <table className="w-full text-[13px]">
            <thead className="bg-[var(--gray-2)]">
              <tr style={{ color: 'var(--gray-9)' }}>
                <th className="text-left p-2 font-medium">date</th>
                <th className="text-left p-2 font-medium">source</th>
                <th className="text-left p-2 font-medium">side</th>
                <th className="text-left p-2 font-medium">brand phrase</th>
                <th className="text-left p-2 font-medium">attached to</th>
              </tr>
            </thead>
            <tbody>
              {data.events.map((e, i) => (
                <tr key={i} className="border-t border-[var(--gray-4)] hover:bg-[var(--gray-2)]">
                  <td className="p-2 font-mono">{formatDate(e.sale_date)}</td>
                  <td className="p-2 font-mono">{e.source_id}</td>
                  <td className="p-2">{e.side}</td>
                  <td className="p-2 font-mono">{e.party_phrase || '—'}</td>
                  <td className="p-2">
                    {e.auto_group_id ? (
                      <Link to={`/explorer/auto-groups/${encodeURIComponent(e.auto_group_id)}`}
                            className="no-underline" style={{ color: 'var(--accent-11)' }}>
                        {e.auto_group_id}
                      </Link>
                    ) : (
                      <Text size="1" style={{ color: 'var(--gray-9)' }}>orphan</Text>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
