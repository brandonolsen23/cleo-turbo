import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Heading, Text, TextField } from "@radix-ui/themes";
import { fetchApi } from "../../api/client";
import type { AutoGroupsMissedStemsResponse } from "../../types";


export default function AutoGroupsMissedStems() {
  const [data, setData] = useState<AutoGroupsMissedStemsResponse | null>(null);
  const [minSides, setMinSides] = useState<string>("100");

  useEffect(() => {
    const params: Record<string, string | number> = { min_n_party_sides: parseInt(minSides) || 100 };
    fetchApi<AutoGroupsMissedStemsResponse>(
      "/explorer/auto-groups/tuning/missed-stems", params,
    ).then(setData).catch(console.error);
  }, [minSides]);

  if (!data) {
    return (
      <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
        <Heading size="3">Stems that didn't promote</Heading>
        <Text size="2" style={{ color: "var(--gray-9)" }}>Loading…</Text>
      </div>
    );
  }

  return (
    <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
      <div className="flex items-baseline gap-3 mb-3 flex-wrap">
        <Heading size="3">Stems that didn't promote</Heading>
        <Text size="1" style={{ color: "var(--gray-9)" }}>
          Distinctive or position-anchor 1-grams with ≥ N party-sides that failed verification.
          {data.total.toLocaleString()} total.
        </Text>
      </div>

      <div className="flex items-center gap-3 mb-3">
        <Text size="2">Min party-sides:</Text>
        <TextField.Root size="2" value={minSides}
                        onChange={(e) => setMinSides(e.target.value)}
                        style={{ width: 100 }} />
      </div>

      <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] overflow-hidden">
        <table className="w-full text-[13px]">
          <thead className="bg-[var(--gray-2)]">
            <tr style={{ color: "var(--gray-9)" }}>
              <th className="text-left p-2 font-medium">token</th>
              <th className="text-right p-2 font-medium">party-sides</th>
              <th className="text-left p-2 font-medium">strongest phone</th>
              <th className="text-right p-2 font-medium">sides at anchor</th>
              <th className="text-left p-2 font-medium">winner stem</th>
              <th className="text-right p-2 font-medium">winner dominance</th>
            </tr>
          </thead>
          <tbody>
            {data.results.map((row) => (
              <tr key={row.token} className="border-t border-[var(--gray-4)]">
                <td className="p-2 font-mono">{row.token}</td>
                <td className="p-2 text-right">{row.n_party_sides.toLocaleString()}</td>
                <td className="p-2 font-mono">
                  {row.strongest_phone ? (
                    <Link to={`/explorer/phones/${encodeURIComponent(row.strongest_phone)}`}
                          className="no-underline" style={{ color: "var(--accent-11)" }}>
                      {row.strongest_phone}
                    </Link>
                  ) : <Text size="1" style={{ color: "var(--gray-9)" }}>—</Text>}
                </td>
                <td className="p-2 text-right">
                  {row.token_sides_at_anchor != null ? row.token_sides_at_anchor.toLocaleString() : "—"}
                </td>
                <td className="p-2 font-mono" style={{ color: "var(--gray-11)" }}>
                  {row.winner_stem ?? "—"}
                </td>
                <td className="p-2 text-right">
                  {row.winner_dominance != null ? row.winner_dominance.toFixed(2) : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
