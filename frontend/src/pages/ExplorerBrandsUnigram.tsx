import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Heading, Text, Badge, Button, TextField, Switch, Checkbox } from "@radix-ui/themes";
import { fetchApi } from "../api/client";
import type { BrandTokenListResponse, BrandTokenSummary } from "../types";
import ExplorerTabs from "../components/explorer/ExplorerTabs";

type SignalToggle = {
  english: boolean;
  place: boolean;
  industry: boolean;
  excluded: boolean;
};

const NO_SIGNAL: SignalToggle = {
  english: false, place: false, industry: false, excluded: false,
};

export default function ExplorerBrandsUnigram() {
  const nav = useNavigate();
  const [data, setData] = useState<BrandTokenListResponse | null>(null);
  const [q, setQ] = useState("");
  const [distinctiveOnly, setDistinctiveOnly] = useState(true);
  const [signals, setSignals] = useState<SignalToggle>(NO_SIGNAL);
  const [page, setPage] = useState(1);
  const perPage = 200;

  const anySignalOn = Object.values(signals).some(Boolean);

  // When a signal toggle is on, fetch the full list (no distinctive_only)
  // and filter client-side — the backend's filter_reason param is
  // precedence-based and would hide tokens caught by a specific signal
  // that's also caught by a higher-precedence one.
  useEffect(() => {
    const effectiveDistinctive = anySignalOn ? false : distinctiveOnly;
    fetchApi<BrandTokenListResponse>("/explorer/brands", {
      q, distinctive_only: effectiveDistinctive, page, per_page: perPage,
    }).then(setData).catch((e) => console.error(e));
  }, [q, distinctiveOnly, signals, page]);

  const filtered: BrandTokenSummary[] = (() => {
    if (!data) return [];
    if (!anySignalOn) return data.results;
    return data.results.filter((t) =>
      (signals.english && t.is_english_common === 1) ||
      (signals.place && t.is_place_name === 1) ||
      (signals.industry && t.is_industry_stopword === 1) ||
      (signals.excluded && t.is_excluded === 1)
    );
  })();

  function reasonBadge(reason: BrandTokenSummary["filter_reason"]) {
    if (reason === null) return <Badge size="1" color="jade">distinctive</Badge>;
    const color =
      reason === "excluded" ? "red" :
      reason === "industry" ? "amber" :
      reason === "place" ? "blue" : "gray";
    return <Badge size="1" variant="soft" color={color}>{reason}</Badge>;
  }

  function flagCell(value: 0 | 1 | null) {
    return value === 1
      ? <span style={{ color: "var(--jade-11)" }}>✓</span>
      : <span style={{ color: "var(--gray-7)" }}>—</span>;
  }

  function toggleSignal(key: keyof SignalToggle) {
    setPage(1);
    setSignals((prev) => ({ ...prev, [key]: !prev[key] }));
  }

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <ExplorerTabs />
      <div className="flex items-baseline gap-4 mb-2">
        <Heading size="6">Brand-Token Explorer</Heading>
        <Text size="2" style={{ color: "var(--gray-9)" }}>
          Layer 1 / Silo A — raw commonalities. No clustering, no anchors.
        </Text>
      </div>
      <Text size="2" style={{ color: "var(--gray-9)" }}>
        Each token is a distinct word appearing in a brand_phrase somewhere in the corpus.
        The columns EN / PL / IND / EX show which filters caught each token. The
        "reason" column shows the precedence-winning filter.
      </Text>

      <div className="flex items-center gap-4 my-5 flex-wrap">
        <TextField.Root size="2" placeholder="Filter token name…"
                        value={q} onChange={(e) => { setPage(1); setQ(e.target.value); }}
                        style={{ width: 280 }} />
        <label className="flex items-center gap-2 text-[13px]">
          <Switch size="2" checked={distinctiveOnly && !anySignalOn}
                  onCheckedChange={(v) => { setPage(1); setDistinctiveOnly(v); setSignals(NO_SIGNAL); }} />
          Distinctive only
        </label>
        {data && (
          <Text size="2" style={{ color: "var(--gray-9)" }}>
            showing {filtered.length.toLocaleString()} of {data.total.toLocaleString()} tokens
          </Text>
        )}
      </div>

      <div className="flex items-center gap-4 mb-5 p-3 rounded-[var(--card-radius)] border border-[var(--gray-6)]"
           style={{ background: "var(--gray-2)" }}>
        <Text size="2" style={{ color: "var(--gray-9)" }}>Show tokens matched by:</Text>
        <label className="flex items-center gap-1 text-[13px]">
          <Checkbox size="1" checked={signals.english}
                    onCheckedChange={() => toggleSignal("english")} />
          English/FR
        </label>
        <label className="flex items-center gap-1 text-[13px]">
          <Checkbox size="1" checked={signals.place}
                    onCheckedChange={() => toggleSignal("place")} />
          Place name
        </label>
        <label className="flex items-center gap-1 text-[13px]">
          <Checkbox size="1" checked={signals.industry}
                    onCheckedChange={() => toggleSignal("industry")} />
          Industry stopword
        </label>
        <label className="flex items-center gap-1 text-[13px]">
          <Checkbox size="1" checked={signals.excluded}
                    onCheckedChange={() => toggleSignal("excluded")} />
          Excluded artifact
        </label>
        <Text size="2" style={{ color: "var(--gray-9)" }}>
          (multi-select; shows union. Zipf threshold = 3.0)
        </Text>
      </div>

      <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] overflow-hidden">
        <table className="w-full text-[13px]">
          <thead className="bg-[var(--gray-2)]">
            <tr style={{ color: "var(--gray-9)" }}>
              <th className="text-left p-2 font-medium">token</th>
              <th className="text-right p-2 font-medium">IDF</th>
              <th className="text-right p-2 font-medium">Zipf</th>
              <th className="text-right p-2 font-medium">n_party_sides</th>
              <th className="text-right p-2 font-medium">n_phrases</th>
              <th className="text-center p-2 font-medium" title="Common English or French (via wordfreq)">EN</th>
              <th className="text-center p-2 font-medium" title="Canadian place name (seed + user-curated)">PL</th>
              <th className="text-center p-2 font-medium" title="Industry stopword (seed + user-curated)">IND</th>
              <th className="text-center p-2 font-medium" title="Categorical exclusion (artifact)">EX</th>
              <th className="text-left p-2 font-medium">reason</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((t: BrandTokenSummary) => (
              <tr key={t.token}
                  className="border-t border-[var(--gray-4)] hover:bg-[var(--gray-2)] cursor-pointer"
                  onClick={() => nav(`/explorer/brands/1gram/${encodeURIComponent(t.token)}`)}>
                <td className="p-2 font-mono">{t.token}</td>
                <td className="p-2 text-right">{t.idf.toFixed(2)}</td>
                <td className="p-2 text-right">
                  {t.wordfreq_zipf !== null ? t.wordfreq_zipf.toFixed(2) : "—"}
                </td>
                <td className="p-2 text-right">{t.n_party_sides.toLocaleString()}</td>
                <td className="p-2 text-right">{t.n_distinct_phrases.toLocaleString()}</td>
                <td className="p-2 text-center">{flagCell(t.is_english_common)}</td>
                <td className="p-2 text-center">{flagCell(t.is_place_name)}</td>
                <td className="p-2 text-center">{flagCell(t.is_industry_stopword)}</td>
                <td className="p-2 text-center">{flagCell(t.is_excluded)}</td>
                <td className="p-2">{reasonBadge(t.filter_reason)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {data && !anySignalOn && data.pages > 1 && (
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
