import { useEffect, useState } from "react";
import { Heading, Text, Badge } from "@radix-ui/themes";
import { fetchApi } from "../../api/client";
import type { AutoGroupWhyTierResponse } from "../../types";


export default function AutoGroupWhyTierPanel({ autoGroupId }: { autoGroupId: string }) {
  const [data, setData] = useState<AutoGroupWhyTierResponse | null>(null);

  useEffect(() => {
    fetchApi<AutoGroupWhyTierResponse>(`/explorer/auto-groups/${encodeURIComponent(autoGroupId)}/why-tier`)
      .then(setData).catch(console.error);
  }, [autoGroupId]);

  if (!data) return null;

  return (
    <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5 mt-5">
      <div className="flex items-baseline gap-2 mb-3 flex-wrap">
        <Heading size="3">Why this tier</Heading>
        <Text size="1" style={{ color: "var(--gray-9)" }}>
          (seeding threshold: score ≥ {data.seeding_threshold})
        </Text>
      </div>
      <table className="w-full text-[13px]">
        <thead className="bg-[var(--gray-2)]">
          <tr style={{ color: "var(--gray-9)" }}>
            <th className="text-left p-2 font-medium">category</th>
            <th className="text-left p-2 font-medium">strongest anchor</th>
            <th className="text-right p-2 font-medium">score</th>
            <th className="text-left p-2 font-medium">status</th>
          </tr>
        </thead>
        <tbody>
          {data.categories.map((c) => (
            <tr key={c.category} className="border-t border-[var(--gray-4)]">
              <td className="p-2 font-medium">{c.category}</td>
              <td className="p-2 font-mono">
                {c.strongest_anchor
                  ? `${c.strongest_anchor.anchor_type}: ${c.strongest_anchor.anchor_value}`
                  : c.near_miss_anchor
                  ? `${c.near_miss_anchor.anchor_type}: ${c.near_miss_anchor.anchor_value} (near-miss)`
                  : "—"}
              </td>
              <td className="p-2 text-right">
                {c.strongest_anchor
                  ? c.strongest_anchor.score.toFixed(2)
                  : c.near_miss_anchor
                  ? c.near_miss_anchor.score.toFixed(2)
                  : "—"}
              </td>
              <td className="p-2">
                {c.passes_threshold
                  ? <Badge color="jade">passes</Badge>
                  : <Badge color="gray">missing</Badge>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
