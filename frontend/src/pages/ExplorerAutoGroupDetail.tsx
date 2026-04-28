import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Heading, Text, Badge } from "@radix-ui/themes";
import { fetchApi } from "../api/client";
import type { AutoGroupDetail } from "../types";
import ExplorerTabs from "../components/explorer/ExplorerTabs";


const tierColor: Record<string, "jade" | "amber" | "gray"> = {
  confirmed: "jade",
  probable:  "amber",
  candidate: "gray",
};

export default function ExplorerAutoGroupDetail() {
  const { id } = useParams<{ id: string }>();
  const [data, setData] = useState<AutoGroupDetail | null>(null);
  const [err, setErr]   = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    fetchApi<AutoGroupDetail>(`/explorer/auto-groups/${encodeURIComponent(id)}`)
      .then(setData).catch((e) => setErr(String(e)));
  }, [id]);

  if (err)  return <div className="p-6"><Text color="tomato">{err}</Text></div>;
  if (!data) return <div className="p-6"><Text size="2" style={{ color: "var(--gray-9)" }}>Loading…</Text></div>;

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <ExplorerTabs />
      <Link to="/explorer/auto-groups" className="text-[13px] no-underline"
            style={{ color: "var(--accent-11)" }}>
        ← Auto-Groups
      </Link>

      <div className="flex items-baseline gap-3 mt-2 mb-1 flex-wrap">
        <Heading size="6" className="font-mono">{data.display_name}</Heading>
        <Badge color={tierColor[data.tier]}>{data.tier}</Badge>
        <Text size="2" style={{ color: "var(--gray-9)" }}>
          stem: <span className="font-mono">{data.canonical_stem}</span>
        </Text>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mt-5">
        <StatCard label="Confidence" value={data.confidence.toFixed(2)} />
        <StatCard label="Anchors"    value={data.n_anchors.toLocaleString()} />
        <StatCard label="Members"    value={data.n_members.toLocaleString()} />
        <StatCard label="Distinct contacts" value={data.n_distinct_contacts.toLocaleString()} />
        <StatCard label="Date range"
                  value={data.min_sale_date && data.max_sale_date
                          ? `${data.min_sale_date.slice(0,7)} → ${data.max_sale_date.slice(0,7)}`
                          : "—"} />
      </div>

      {/* Anchors */}
      <Heading size="4" mt="6" mb="2">Anchors ({data.anchors.length})</Heading>
      <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] overflow-hidden">
        <table className="w-full text-[13px]">
          <thead className="bg-[var(--gray-2)]">
            <tr style={{ color: "var(--gray-9)" }}>
              <th className="text-left p-2 font-medium">type</th>
              <th className="text-left p-2 font-medium">value</th>
              <th className="text-right p-2 font-medium">score</th>
            </tr>
          </thead>
          <tbody>
            {data.anchors.map((a, i) => (
              <tr key={i} className="border-t border-[var(--gray-4)]">
                <td className="p-2">{a.anchor_type}</td>
                <td className="p-2 font-mono">{a.anchor_value}</td>
                <td className="p-2 text-right">{a.score.toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

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

      {/* Members (party-sides) */}
      <Heading size="4" mt="6" mb="2">
        Members ({data.n_members.toLocaleString()}{data.members.length < data.n_members ? `, top ${data.members.length} shown` : ''})
      </Heading>
      <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] overflow-hidden">
        <table className="w-full text-[13px]">
          <thead className="bg-[var(--gray-2)]">
            <tr style={{ color: "var(--gray-9)" }}>
              <th className="text-left p-2 font-medium">source_id</th>
              <th className="text-left p-2 font-medium">side</th>
              <th className="text-right p-2 font-medium">match_score</th>
            </tr>
          </thead>
          <tbody>
            {data.members.map((m, i) => (
              <tr key={i} className="border-t border-[var(--gray-4)]">
                <td className="p-2 font-mono">{m.source_id}</td>
                <td className="p-2">{m.side}</td>
                <td className="p-2 text-right">{m.match_score.toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
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
