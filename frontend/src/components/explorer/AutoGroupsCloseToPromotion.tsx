import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Heading, Text, Badge } from "@radix-ui/themes";
import { fetchApi } from "../../api/client";
import type { AutoGroupsCloseToPromotionResponse } from "../../types";


export default function AutoGroupsCloseToPromotion() {
  const nav = useNavigate();
  const [data, setData] = useState<AutoGroupsCloseToPromotionResponse | null>(null);

  useEffect(() => {
    fetchApi<AutoGroupsCloseToPromotionResponse>(
      "/explorer/auto-groups/tuning/close-to-promotion",
    ).then(setData).catch(console.error);
  }, []);

  if (!data) {
    return (
      <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
        <Heading size="3">Close to promotion</Heading>
        <Text size="2" style={{ color: "var(--gray-9)" }}>Loading…</Text>
      </div>
    );
  }

  return (
    <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
      <div className="flex items-baseline gap-3 mb-3 flex-wrap">
        <Heading size="3">Close to promotion</Heading>
        <Text size="1" style={{ color: "var(--gray-9)" }}>
          Probable groups in confidence [{data.from_confidence.toFixed(2)}, {data.to_confidence.toFixed(2)}). {data.total.toLocaleString()} total.
        </Text>
      </div>

      <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] overflow-hidden">
        <table className="w-full text-[13px]">
          <thead className="bg-[var(--gray-2)]">
            <tr style={{ color: "var(--gray-9)" }}>
              <th className="text-left p-2 font-medium">display name</th>
              <th className="text-left p-2 font-medium">stem</th>
              <th className="text-left p-2 font-medium">tier</th>
              <th className="text-right p-2 font-medium">confidence</th>
              <th className="text-right p-2 font-medium">anchors</th>
              <th className="text-right p-2 font-medium">members</th>
            </tr>
          </thead>
          <tbody>
            {data.results.map((g) => (
              <tr key={g.auto_group_id}
                  className="border-t border-[var(--gray-4)] hover:bg-[var(--gray-2)] cursor-pointer"
                  onClick={() => nav(`/explorer/auto-groups/${encodeURIComponent(g.auto_group_id)}`)}>
                <td className="p-2 font-mono">{g.display_name}</td>
                <td className="p-2 font-mono" style={{ color: "var(--gray-11)" }}>{g.canonical_stem}</td>
                <td className="p-2"><Badge color="amber">{g.tier}</Badge></td>
                <td className="p-2 text-right">{g.confidence.toFixed(2)}</td>
                <td className="p-2 text-right">{g.n_anchors.toLocaleString()}</td>
                <td className="p-2 text-right">{g.n_members.toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
