import { useEffect, useState } from "react";
import { Text, Button, TextField, Select, Badge } from "@radix-ui/themes";
import { fetchApi } from "../../api/client";
import { useSourceViewer } from "../source/SourceViewerContext";
import type {
  AutoGroupPartiesResponse,
  AutoGroupParty,
  AutoGroupAnchorsWithCoverageResponse,
} from "../../types";


function formatAddress(p: AutoGroupParty): string {
  return [p.street_number, p.street_name, p.street_suffix, p.suite_type, p.suite_number]
    .filter(Boolean).join(" ");
}

function formatCurrency(n: number | null): string {
  if (n == null) return "—";
  return `$${(n / 1_000_000).toFixed(2)}M`;
}


export default function AutoGroupPartiesTab({ autoGroupId }: { autoGroupId: string }) {
  const { openSource } = useSourceViewer();
  const [data, setData] = useState<AutoGroupPartiesResponse | null>(null);

  // Filters / sort state
  const [page, setPage] = useState(1);
  const [perPage] = useState(100);
  const [minMatchScore, setMinMatchScore] = useState<string>("");
  const [side, setSide] = useState<"all" | "buyer" | "seller">("all");
  const [q, setQ] = useState("");
  const [sort, setSort] = useState<"date" | "match_score" | "sale_price">("date");
  const [order, setOrder] = useState<"asc" | "desc">("desc");

  // Anchor filter (populated from anchors-with-coverage)
  const [anchorPick, setAnchorPick] = useState<string>("");  // serialized as "type|value"
  const [allAnchors, setAllAnchors] = useState<{ type: string; value: string; label: string }[]>([]);

  useEffect(() => {
    fetchApi<AutoGroupAnchorsWithCoverageResponse>(
      `/explorer/auto-groups/${encodeURIComponent(autoGroupId)}/anchors-with-coverage`,
    ).then((res) => {
      setAllAnchors(res.anchors.map((a) => ({
        type: a.anchor_type,
        value: a.anchor_value,
        label: `${a.anchor_type}: ${a.anchor_value}`,
      })));
    }).catch(console.error);
  }, [autoGroupId]);

  useEffect(() => {
    const params: Record<string, string | number> = {
      page, per_page: perPage, sort, order,
    };
    if (minMatchScore) params.min_match_score = parseFloat(minMatchScore);
    if (side !== "all") params.side = side;
    if (q) params.q = q;
    if (anchorPick) {
      const [t, v] = anchorPick.split("|", 2);
      params.anchor_type = t;
      params.anchor_value = v;
    }
    fetchApi<AutoGroupPartiesResponse>(
      `/explorer/auto-groups/${encodeURIComponent(autoGroupId)}/parties`, params,
    ).then(setData).catch(console.error);
  }, [autoGroupId, page, perPage, minMatchScore, side, q, anchorPick, sort, order]);

  return (
    <>
      <div className="flex items-center gap-3 mb-4 flex-wrap">
        <TextField.Root size="2" placeholder="brand phrase substring…"
                        value={q}
                        onChange={(e) => { setPage(1); setQ(e.target.value); }}
                        style={{ width: 200 }} />

        <Select.Root value={side} onValueChange={(v) => { setPage(1); setSide(v as "all" | "buyer" | "seller"); }}>
          <Select.Trigger placeholder="Side" />
          <Select.Content>
            <Select.Item value="all">All sides</Select.Item>
            <Select.Item value="buyer">Buyer</Select.Item>
            <Select.Item value="seller">Seller</Select.Item>
          </Select.Content>
        </Select.Root>

        <TextField.Root size="2" placeholder="min match score…"
                        value={minMatchScore}
                        onChange={(e) => { setPage(1); setMinMatchScore(e.target.value); }}
                        style={{ width: 120 }} />

        <Select.Root value={anchorPick || "ALL"}
                     onValueChange={(v) => { setPage(1); setAnchorPick(v === "ALL" ? "" : v); }}>
          <Select.Trigger placeholder="Anchor filter" />
          <Select.Content>
            <Select.Item value="ALL">All anchors</Select.Item>
            {allAnchors.map((a) => (
              <Select.Item key={`${a.type}|${a.value}`} value={`${a.type}|${a.value}`}>
                {a.label}
              </Select.Item>
            ))}
          </Select.Content>
        </Select.Root>

        <Select.Root value={`${sort}:${order}`}
                     onValueChange={(v) => {
                       const [s, o] = v.split(":");
                       setSort(s as "date" | "match_score" | "sale_price");
                       setOrder(o as "asc" | "desc");
                     }}>
          <Select.Trigger placeholder="Sort" />
          <Select.Content>
            <Select.Item value="date:desc">Newest first</Select.Item>
            <Select.Item value="date:asc">Oldest first</Select.Item>
            <Select.Item value="match_score:desc">Match score (high → low)</Select.Item>
            <Select.Item value="match_score:asc">Match score (low → high)</Select.Item>
            <Select.Item value="sale_price:desc">Sale price (high → low)</Select.Item>
            <Select.Item value="sale_price:asc">Sale price (low → high)</Select.Item>
          </Select.Content>
        </Select.Root>

        {data && (
          <Text size="2" style={{ color: "var(--gray-9)" }}>
            {data.total.toLocaleString()} parties
          </Text>
        )}
      </div>

      <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] overflow-hidden">
        <table className="w-full text-[13px]">
          <thead className="bg-[var(--gray-2)]">
            <tr style={{ color: "var(--gray-9)" }}>
              <th className="text-left p-2 font-medium">date</th>
              <th className="text-left p-2 font-medium">side</th>
              <th className="text-left p-2 font-medium">brand phrase</th>
              <th className="text-left p-2 font-medium">address</th>
              <th className="text-left p-2 font-medium">contact</th>
              <th className="text-left p-2 font-medium">phone</th>
              <th className="text-right p-2 font-medium">price</th>
              <th className="text-left p-2 font-medium">signature</th>
              <th className="text-right p-2 font-medium">score</th>
            </tr>
          </thead>
          <tbody>
            {data?.results.map((p) => (
              <tr key={`${p.source_id}|${p.side}`}
                  className="border-t border-[var(--gray-4)] hover:bg-[var(--gray-2)] cursor-pointer"
                  onClick={() => openSource(p.source_id)}>
                <td className="p-2">{p.sale_date?.slice(0, 10) || "—"}</td>
                <td className="p-2">{p.side}</td>
                <td className="p-2 font-mono">{p.top_brand_phrase || "—"}</td>
                <td className="p-2">{formatAddress(p) || "—"}</td>
                <td className="p-2">{p.contact || "—"}</td>
                <td className="p-2 font-mono">{p.phone || "—"}</td>
                <td className="p-2 text-right">{formatCurrency(p.sale_price)}</td>
                <td className="p-2">
                  {p.anchor_signature.length === 0
                    ? <Text size="1" style={{ color: "var(--gray-9)" }}>—</Text>
                    : p.anchor_signature.map((s, i) => (
                        <Badge key={i} color="jade" className="mr-1">{s.category}</Badge>
                      ))
                  }
                </td>
                <td className="p-2 text-right">{p.match_score.toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {data && data.pages > 1 && (
        <div className="flex items-center gap-2 mt-4">
          <Button size="1" variant="soft" disabled={page === 1}
                  onClick={() => setPage(page - 1)}>Previous</Button>
          <Text size="2" style={{ color: "var(--gray-9)" }}>
            Page {page} of {data.pages}
          </Text>
          <Button size="1" variant="soft" disabled={page === data.pages}
                  onClick={() => setPage(page + 1)}>Next</Button>
        </div>
      )}
    </>
  );
}
