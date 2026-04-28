import { Heading, Text } from "@radix-ui/themes";
import type { AutoGroupDetail } from "../../types";
import AutoGroupWhyTierPanel from "./AutoGroupWhyTierPanel";


export default function AutoGroupOverviewTab({ data }: { data: AutoGroupDetail }) {
  return (
    <>
      {/* Stat cards */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <StatCard label="Confidence" value={data.confidence.toFixed(2)} />
        <StatCard label="Anchors"    value={data.n_anchors.toLocaleString()} />
        <StatCard label="Parties"    value={data.n_members.toLocaleString()} />
        <StatCard label="Distinct contacts" value={data.n_distinct_contacts.toLocaleString()} />
        <StatCard label="Date range"
                  value={data.min_sale_date && data.max_sale_date
                          ? `${data.min_sale_date.slice(0,7)} → ${data.max_sale_date.slice(0,7)}`
                          : "—"} />
      </div>

      {/* Why this tier */}
      <AutoGroupWhyTierPanel autoGroupId={data.auto_group_id} />

      {/* Top phrases */}
      <Heading size="4" mt="6" mb="2">Top phrases ({data.top_phrases.length})</Heading>
      <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] overflow-hidden">
        <table className="w-full text-[13px]">
          <thead className="bg-[var(--gray-2)]">
            <tr style={{ color: "var(--gray-9)" }}>
              <th className="text-left p-2 font-medium">phrase</th>
              <th className="text-right p-2 font-medium">n</th>
            </tr>
          </thead>
          <tbody>
            {data.top_phrases.map((p, i) => (
              <tr key={i} className="border-t border-[var(--gray-4)]">
                <td className="p-2 font-mono">{p.phrase}</td>
                <td className="p-2 text-right">{p.n.toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Numbered corps */}
      {data.numbered_corps.length > 0 && (
        <>
          <Heading size="4" mt="6" mb="2">Numbered corps owned ({data.numbered_corps.length})</Heading>
          <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-3 text-[13px]"
               style={{ background: "var(--gray-2)" }}>
            {data.numbered_corps.map((c, i) => (
              <span key={i} className="inline-block mr-3 mb-2 font-mono">{c.corp_name}</span>
            ))}
          </div>
        </>
      )}
    </>
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
