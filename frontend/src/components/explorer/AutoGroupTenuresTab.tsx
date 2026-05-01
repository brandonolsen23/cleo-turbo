import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Heading, Text, Badge } from "@radix-ui/themes";
import { fetchApi } from "../../api/client";
import type { AutoGroupAnchorTenuresResponse, AutoGroupAnchorTenure } from "../../types";


function siloLinkFor(t: AutoGroupAnchorTenure): string {
  if (t.anchor_type === 'phone') return `/explorer/phones/${encodeURIComponent(t.anchor_value)}`;
  if (t.anchor_type === 'address_unit') return `/explorer/addresses/units/${encodeURIComponent(t.anchor_value)}`;
  return `/explorer/contacts/${encodeURIComponent(t.anchor_value)}`;
}


export default function AutoGroupTenuresTab({ autoGroupId }: { autoGroupId: string }) {
  const [data, setData] = useState<AutoGroupAnchorTenuresResponse | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchApi<AutoGroupAnchorTenuresResponse>(
      `/explorer/auto-groups/${encodeURIComponent(autoGroupId)}/anchor-tenures`,
    ).then((d) => { if (!cancelled) setData(d); })
     .catch(console.error);
    return () => { cancelled = true; };
  }, [autoGroupId]);

  if (!data) return <Text size="2" style={{ color: 'var(--gray-9)' }}>Loading…</Text>;

  return (
    <>
      <Heading size="4" mb="2">Anchor Tenures ({data.tenures.length})</Heading>
      <Text size="1" style={{ color: 'var(--gray-9)' }} className="block mb-2">
        Each row is one tenure window. The "active" badge means the tenure has been seen within the last year.
      </Text>
      <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] overflow-hidden">
        <table className="w-full text-[13px]">
          <thead className="bg-[var(--gray-2)]">
            <tr style={{ color: 'var(--gray-9)' }}>
              <th className="text-left p-2 font-medium">anchor</th>
              <th className="text-left p-2 font-medium">value</th>
              <th className="text-left p-2 font-medium">tenure</th>
              <th className="text-right p-2 font-medium">parties</th>
              <th className="text-right p-2 font-medium">coverage</th>
              <th className="text-right p-2 font-medium">score</th>
              <th className="text-left p-2 font-medium"></th>
            </tr>
          </thead>
          <tbody>
            {data.tenures.map((t, i) => (
              <tr key={i} className="border-t border-[var(--gray-4)] hover:bg-[var(--gray-2)]">
                <td className="p-2">{t.anchor_type}</td>
                <td className="p-2 font-mono break-all">
                  <Link to={siloLinkFor(t)} className="no-underline"
                        style={{ color: 'var(--accent-11)' }}>
                    {t.anchor_value}
                  </Link>
                </td>
                <td className="p-2 font-mono whitespace-nowrap">
                  {t.start_date} → {t.end_date}{' '}
                  {t.is_active === 1 && <Badge color="jade" size="1">active</Badge>}
                </td>
                <td className="p-2 text-right">{t.n_party_sides_in_window.toLocaleString()}</td>
                <td className="p-2 text-right">{t.coverage_pct.toFixed(0)}%</td>
                <td className="p-2 text-right">{t.score.toFixed(2)}</td>
                <td className="p-2"></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
