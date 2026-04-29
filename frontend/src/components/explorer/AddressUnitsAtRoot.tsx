import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Heading, Text } from "@radix-ui/themes";
import { fetchApi } from "../../api/client";
import type { AddressUnitsAtRootResponse, AddressUnitSummary } from "../../types";


function unitKey(u: AddressUnitSummary): string {
  return [u.city, u.street_number, u.street_name, u.street_suffix,
          u.street_direction, u.suite_type, u.suite_number].join('|');
}

function unitLabel(u: AddressUnitSummary): string {
  const suite = [u.suite_type, u.suite_number].filter(Boolean).join(' ');
  const dir = u.street_direction;
  if (!suite && !dir) return '(no unit)';
  return [suite, dir].filter(Boolean).join(' ');
}


export default function AddressUnitsAtRoot({ rootKey }: { rootKey: string }) {
  const [data, setData] = useState<AddressUnitsAtRootResponse | null>(null);

  useEffect(() => {
    fetchApi<AddressUnitsAtRootResponse>(
      `/explorer/addresses/roots/${encodeURIComponent(rootKey)}/units`,
    ).then(setData).catch(console.error);
  }, [rootKey]);

  if (!data) return null;
  if (data.results.length === 0) {
    return (
      <div className="mt-6">
        <Heading size="3" mb="2">Units at this root</Heading>
        <Text size="2" style={{ color: "var(--gray-9)" }}>No units recorded.</Text>
      </div>
    );
  }

  return (
    <div className="mt-6">
      <Heading size="3" mb="2">Units at this root ({data.results.length})</Heading>
      <Text size="1" style={{ color: "var(--gray-9)" }} className="block mb-2">
        Each row is a distinct physical unit (suite/floor/PO box). Click to drill into a unit's detail.
      </Text>
      <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] overflow-hidden">
        <table className="w-full text-[13px]">
          <thead className="bg-[var(--gray-2)]">
            <tr style={{ color: "var(--gray-9)" }}>
              <th className="text-left p-2 font-medium">unit</th>
              <th className="text-right p-2 font-medium">parties</th>
              <th className="text-left p-2 font-medium">dominant stem</th>
              <th className="text-right p-2 font-medium">dominance</th>
              <th className="text-right p-2 font-medium">distinct stems</th>
            </tr>
          </thead>
          <tbody>
            {data.results.map((u, i) => (
              <tr key={i} className="border-t border-[var(--gray-4)] hover:bg-[var(--gray-2)]">
                <td className="p-2">
                  <Link to={`/explorer/addresses/units/${encodeURIComponent(unitKey(u))}`}
                        className="no-underline" style={{ color: "var(--accent-11)" }}>
                    {unitLabel(u)}
                  </Link>
                </td>
                <td className="p-2 text-right">{u.n_party_sides.toLocaleString()}</td>
                <td className="p-2 font-mono">
                  {u.dominant_stem || <Text size="1" style={{ color: "var(--gray-9)" }}>—</Text>}
                </td>
                <td className="p-2 text-right">
                  {u.dominance_share != null ? `${(u.dominance_share * 100).toFixed(0)}%` : '—'}
                </td>
                <td className="p-2 text-right">{u.n_distinct_brand_stems}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
