import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Heading, Text, Badge, Button, TextField, Switch } from "@radix-ui/themes";
import { fetchApi } from "../api/client";
import type { BrandTokenListResponse, BrandTokenSummary } from "../types";

export default function ExplorerBrands() {
  const nav = useNavigate();
  const [data, setData] = useState<BrandTokenListResponse | null>(null);
  const [q, setQ] = useState("");
  const [distinctiveOnly, setDistinctiveOnly] = useState(true);
  const [filterReason, setFilterReason] = useState<string>("");
  const [page, setPage] = useState(1);
  const perPage = 50;

  useEffect(() => {
    const params: Record<string, any> = {
      q, distinctive_only: distinctiveOnly, page, per_page: perPage,
    };
    if (filterReason) params.filter_reason = filterReason;
    fetchApi<BrandTokenListResponse>("/explorer/brands", params)
      .then(setData).catch((e) => console.error(e));
  }, [q, distinctiveOnly, filterReason, page]);

  function reasonBadge(reason: BrandTokenSummary["filter_reason"]) {
    if (reason === null) return <Badge size="1" color="jade">distinctive</Badge>;
    const color =
      reason === "excluded" ? "red" :
      reason === "industry" ? "amber" :
      reason === "place" ? "blue" : "gray";
    return <Badge size="1" variant="soft" color={color}>{reason}</Badge>;
  }

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <div className="flex items-baseline gap-4 mb-2">
        <Heading size="6">Brand-Token Explorer</Heading>
        <Text size="2" style={{ color: "var(--gray-9)" }}>
          Layer 1 / Silo A — raw commonalities. No clustering, no anchors.
        </Text>
      </div>
      <Text size="2" style={{ color: "var(--gray-9)" }}>
        Each token is a distinct word appearing in a brand_phrase somewhere in the corpus.
        Click a token to see every party-side carrying it and the other atoms on those sides.
      </Text>

      <div className="flex items-center gap-4 my-5 flex-wrap">
        <TextField.Root size="2" placeholder="Filter token name…"
                        value={q} onChange={(e) => { setPage(1); setQ(e.target.value); }}
                        style={{ width: 280 }} />
        <label className="flex items-center gap-2 text-[13px]">
          <Switch size="2" checked={distinctiveOnly}
                  onCheckedChange={(v) => { setPage(1); setDistinctiveOnly(v); setFilterReason(""); }} />
          Distinctive only
        </label>
        <label className="flex items-center gap-2 text-[13px]">
          Show only:
          <select value={filterReason}
                  onChange={(e) => { setPage(1); setFilterReason(e.target.value); if (e.target.value) setDistinctiveOnly(false); }}
                  className="border border-[var(--gray-6)] rounded px-2 py-1 text-[13px]">
            <option value="">(all reasons)</option>
            <option value="english">English common</option>
            <option value="place">Place name</option>
            <option value="industry">Industry stopword</option>
            <option value="excluded">Excluded artifact</option>
          </select>
        </label>
        {data && (
          <Text size="2" style={{ color: "var(--gray-9)" }}>
            {data.total.toLocaleString()} tokens
          </Text>
        )}
      </div>

      <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] overflow-hidden">
        <table className="w-full text-[13px]">
          <thead className="bg-[var(--gray-2)]">
            <tr style={{ color: "var(--gray-9)" }}>
              <th className="text-left p-2 font-medium">token</th>
              <th className="text-right p-2 font-medium">IDF</th>
              <th className="text-right p-2 font-medium">Zipf</th>
              <th className="text-right p-2 font-medium">n_party_sides</th>
              <th className="text-right p-2 font-medium">n_distinct_phrases</th>
              <th className="text-left p-2 font-medium">reason</th>
            </tr>
          </thead>
          <tbody>
            {data?.results.map((t: BrandTokenSummary) => (
              <tr key={t.token}
                  className="border-t border-[var(--gray-4)] hover:bg-[var(--gray-2)] cursor-pointer"
                  onClick={() => nav(`/explorer/brands/${encodeURIComponent(t.token)}`)}>
                <td className="p-2 font-mono">{t.token}</td>
                <td className="p-2 text-right">{t.idf.toFixed(2)}</td>
                <td className="p-2 text-right">
                  {t.wordfreq_zipf !== null ? t.wordfreq_zipf.toFixed(2) : "—"}
                </td>
                <td className="p-2 text-right">{t.n_party_sides.toLocaleString()}</td>
                <td className="p-2 text-right">{t.n_distinct_phrases.toLocaleString()}</td>
                <td className="p-2">{reasonBadge(t.filter_reason)}</td>
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
