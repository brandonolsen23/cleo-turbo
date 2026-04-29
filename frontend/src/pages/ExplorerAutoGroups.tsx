import { useEffect, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { Heading, Text, Button, TextField, Badge, SegmentedControl } from "@radix-ui/themes";
import { fetchApi } from "../api/client";
import type { AutoGroupListResponse, AutoGroupSummary } from "../types";
import ExplorerTabs from "../components/explorer/ExplorerTabs";


type Tier = 'confirmed' | 'probable' | 'candidate';

const tierColor: Record<Tier, "jade" | "amber" | "gray"> = {
  confirmed: "jade",
  probable:  "amber",
  candidate: "gray",
};

export default function ExplorerAutoGroups() {
  const nav = useNavigate();
  const [data, setData] = useState<AutoGroupListResponse | null>(null);
  const [tier, setTier] = useState<Tier>('confirmed');
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [closeToPromotion, setCloseToPromotion] = useState(false);
  const perPage = 100;

  useEffect(() => {
    const params: Record<string, string | number | boolean> = {
      tier, q, page, per_page: perPage,
    };
    if (closeToPromotion) params.close_to_promotion = "true";
    fetchApi<AutoGroupListResponse>("/explorer/auto-groups", params)
      .then(setData).catch((e) => console.error(e));
  }, [tier, q, page, closeToPromotion]);

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <ExplorerTabs />
      <div className="flex items-baseline gap-3 mb-2 flex-wrap">
        <Heading size="6">Auto-Groups</Heading>
        <Text size="2" style={{ color: "var(--gray-9)" }}>
          Operator portfolios discovered by triangulating Layer 1 anchors.
          Read-only — actions land in Plan C.
        </Text>
        <Link to="/explorer/auto-groups/tuning" className="text-[13px] no-underline ml-auto"
              style={{ color: "var(--accent-11)" }}>
          Tuning →
        </Link>
      </div>
      <div className="flex items-center gap-4 my-5 flex-wrap">
        <SegmentedControl.Root value={tier}
            onValueChange={(v) => { setPage(1); setTier(v as Tier); }}>
          <SegmentedControl.Item value="confirmed">Confirmed</SegmentedControl.Item>
          <SegmentedControl.Item value="probable">Probable</SegmentedControl.Item>
          <SegmentedControl.Item value="candidate">Candidate</SegmentedControl.Item>
        </SegmentedControl.Root>
        <TextField.Root size="2" placeholder="Filter by stem or display name…"
            value={q} onChange={(e) => { setPage(1); setQ(e.target.value); }}
            style={{ width: 280 }} />
        <label className="flex items-center gap-2 text-[13px]">
          <input type="checkbox" checked={closeToPromotion}
                 onChange={(e) => { setPage(1); setCloseToPromotion(e.target.checked); }} />
          <Text size="2">Close to promotion (0.70–0.75)</Text>
        </label>
        {data && (
          <Text size="2" style={{ color: "var(--gray-9)" }}>
            {data.total.toLocaleString()} groups
          </Text>
        )}
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
              <th className="text-right p-2 font-medium">distinct contacts</th>
              <th className="text-right p-2 font-medium">anchor diversity</th>
            </tr>
          </thead>
          <tbody>
            {data?.results.map((g: AutoGroupSummary) => (
              <tr key={g.auto_group_id}
                  className="border-t border-[var(--gray-4)] hover:bg-[var(--gray-2)] cursor-pointer"
                  onClick={() => nav(`/explorer/auto-groups/${encodeURIComponent(g.auto_group_id)}`)}>
                <td className="p-2 font-mono">{g.display_name}</td>
                <td className="p-2 font-mono" style={{ color: "var(--gray-11)" }}>{g.canonical_stem}</td>
                <td className="p-2"><Badge color={tierColor[g.tier]}>{g.tier}</Badge></td>
                <td className="p-2 text-right">{g.confidence.toFixed(2)}</td>
                <td className="p-2 text-right">{g.n_anchors.toLocaleString()}</td>
                <td className="p-2 text-right">{g.n_members.toLocaleString()}</td>
                <td className="p-2 text-right">{g.n_distinct_contacts != null ? g.n_distinct_contacts.toLocaleString() : "—"}</td>
                <td className="p-2 text-right">{g.anchor_diversity != null ? g.anchor_diversity : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {data && data.pages > 1 && (
        <div className="flex items-center gap-2 mt-4">
          <Button size="1" variant="soft" disabled={page === 1} onClick={() => setPage(page - 1)}>
            Previous
          </Button>
          <Text size="2" style={{ color: "var(--gray-9)" }}>
            Page {page} of {data.pages}
          </Text>
          <Button size="1" variant="soft" disabled={page === data.pages} onClick={() => setPage(page + 1)}>
            Next
          </Button>
        </div>
      )}
    </div>
  );
}
