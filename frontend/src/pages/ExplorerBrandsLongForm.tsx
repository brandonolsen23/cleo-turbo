import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Heading, Text, Button, TextField, Switch } from "@radix-ui/themes";
import { fetchApi } from "../api/client";
import type { BrandLongPhraseListResponse, BrandLongPhraseSummary } from "../types";
import ExplorerTabs from "../components/explorer/ExplorerTabs";
import BrandSearchBar from "../components/explorer/BrandSearchBar";

export default function ExplorerBrandsLongForm() {
  const nav = useNavigate();
  const [data, setData] = useState<BrandLongPhraseListResponse | null>(null);
  const [q, setQ] = useState("");
  const [distinctiveOnly, setDistinctiveOnly] = useState(true);
  const [page, setPage] = useState(1);
  const perPage = 100;

  useEffect(() => {
    fetchApi<BrandLongPhraseListResponse>("/explorer/brands/long-phrases", {
      q, distinctive_only: distinctiveOnly, page, per_page: perPage,
    }).then(setData).catch((e) => console.error(e));
  }, [q, distinctiveOnly, page]);

  function flagCell(v: 0 | 1) {
    return v === 1
      ? <span style={{ color: "var(--jade-11)" }}>✓</span>
      : <span style={{ color: "var(--gray-7)" }}>—</span>;
  }

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <ExplorerTabs />
      <BrandSearchBar />
      <div className="flex items-baseline gap-4 mb-2">
        <Heading size="6">Brand 6+ long-form</Heading>
        <Text size="2" style={{ color: "var(--gray-9)" }}>
          Full normalized brand_phrases with 6 or more tokens after stopword
          stripping. Catches the long tail — institutional entities, sovereign
          and government names, school boards, court phrases — that don't fit
          in any fixed n-gram window.
        </Text>
      </div>

      <div className="flex items-center gap-4 my-5 flex-wrap">
        <TextField.Root size="2" placeholder="Filter long-form phrase…"
                        value={q} onChange={(e) => { setPage(1); setQ(e.target.value); }}
                        style={{ width: 320 }} />
        <label className="flex items-center gap-2 text-[13px]">
          <Switch size="2" checked={distinctiveOnly}
                  onCheckedChange={(v) => { setPage(1); setDistinctiveOnly(v); }} />
          Distinctive only
        </label>
        {data && (
          <Text size="2" style={{ color: "var(--gray-9)" }}>
            {data.total.toLocaleString()} long-form phrases
          </Text>
        )}
      </div>

      <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] overflow-hidden">
        <table className="w-full text-[13px]">
          <thead className="bg-[var(--gray-2)]">
            <tr style={{ color: "var(--gray-9)" }}>
              <th className="text-left p-2 font-medium">phrase</th>
              <th className="text-right p-2 font-medium">n_tokens</th>
              <th className="text-right p-2 font-medium">IDF</th>
              <th className="text-right p-2 font-medium">n_party_sides</th>
              <th className="text-right p-2 font-medium">n_source_phrases</th>
              <th className="text-center p-2 font-medium" title="At least one constituent token is_distinctive=1">any-tok-dist</th>
            </tr>
          </thead>
          <tbody>
            {data?.results.map((t: BrandLongPhraseSummary) => (
              <tr key={t.phrase}
                  className="border-t border-[var(--gray-4)] hover:bg-[var(--gray-2)] cursor-pointer"
                  onClick={() => nav(`/explorer/brands/long-form/${encodeURIComponent(t.phrase)}`)}>
                <td className="p-2 font-mono">{t.phrase}</td>
                <td className="p-2 text-right">{t.n_tokens}</td>
                <td className="p-2 text-right">{t.idf.toFixed(2)}</td>
                <td className="p-2 text-right">{t.n_party_sides.toLocaleString()}</td>
                <td className="p-2 text-right">{t.n_distinct_source_phrases.toLocaleString()}</td>
                <td className="p-2 text-center">{flagCell(t.any_token_distinctive)}</td>
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
