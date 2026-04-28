import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Heading, Text, Badge } from "@radix-ui/themes";
import { fetchApi } from "../api/client";
import type { AutoGroupDetail } from "../types";
import ExplorerTabs from "../components/explorer/ExplorerTabs";
import AutoGroupTabs from "../components/explorer/AutoGroupTabs";
import AutoGroupTabPlaceholder from "../components/explorer/AutoGroupTabPlaceholder";
import AutoGroupOverviewTab from "../components/explorer/AutoGroupOverviewTab";


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

      <div className="flex items-baseline gap-3 mt-2 mb-5 flex-wrap">
        <Heading size="6" className="font-mono">{data.display_name}</Heading>
        <Badge color={tierColor[data.tier]}>{data.tier}</Badge>
        <Text size="2" style={{ color: "var(--gray-9)" }}>
          stem: <span className="font-mono">{data.canonical_stem}</span>
        </Text>
      </div>

      <AutoGroupTabs>
        {{
          overview: <AutoGroupOverviewTab data={data} />,
          anchors:  <AutoGroupTabPlaceholder planName="Plan D Task 6" />,
          parties:  <AutoGroupTabPlaceholder planName="Plan D Task 7" />,
          graph:    <AutoGroupTabPlaceholder planName="Plan E" />,
          trail:    <AutoGroupTabPlaceholder planName="Plan F" />,
        }}
      </AutoGroupTabs>
    </div>
  );
}
