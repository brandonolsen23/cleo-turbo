import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Heading, Text, Badge, Button } from "@radix-ui/themes";
import { fetchApi } from "../../api/client";
import type {
  BrandFamilyResponse, BrandFamilyEntry, BrandFamilyLooseFullResponse,
} from "../../types";

interface BrandFamilyProps {
  seed_value: string;
  seed_level: BrandFamilyResponse["seed_level"];
}

function detailHref(entry: BrandFamilyEntry): string {
  const path = entry.level === "long-form" ? "long-form" : entry.level;
  return `/explorer/brands/${path}/${encodeURIComponent(entry.value)}`;
}

function levelLabel(level: BrandFamilyEntry["level"]): string {
  return ({
    "1gram": "1g", "2gram": "2g", "3gram": "3g",
    "4gram": "4g", "5gram": "5g", "long-form": "6+",
  } as const)[level];
}

function EntryRow({ entry }: { entry: BrandFamilyEntry }) {
  return (
    <Link to={detailHref(entry)} className="no-underline">
      <div className="flex items-center gap-2 px-3 py-2 hover:bg-[var(--gray-2)] rounded text-[13px]">
        <Badge size="1" variant="soft" color="gray" style={{ minWidth: 32, justifyContent: "center" }}>
          {levelLabel(entry.level)}
        </Badge>
        <span className="font-mono" style={{ color: "var(--accent-11)" }}>
          {entry.value}
        </span>
        <div className="flex-1" />
        <Text size="1" style={{ color: "var(--gray-9)" }}>
          {entry.n_party_sides.toLocaleString()} sides
        </Text>
      </div>
    </Link>
  );
}

function LooseSection({ token, n_total, preview }: { token: string; n_total: number; preview: BrandFamilyEntry[] }) {
  const [expanded, setExpanded] = useState(false);
  const [full, setFull] = useState<BrandFamilyEntry[] | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [page, setPage] = useState(1);
  const [pages, setPages] = useState(1);

  async function loadFull(targetPage = 1) {
    setLoadingMore(true);
    try {
      const data = await fetchApi<BrandFamilyLooseFullResponse>(
        "/explorer/brands/family/loose",
        { token, page: targetPage, per_page: 100 },
      );
      setFull(data.results);
      setPage(data.page);
      setPages(data.pages);
    } finally {
      setLoadingMore(false);
    }
  }

  function handleToggle() {
    if (!expanded && full === null) loadFull(1);
    setExpanded((e) => !e);
  }

  const entries = full ?? preview;

  return (
    <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] overflow-hidden">
      <button onClick={handleToggle}
              className="w-full text-left px-3 py-2 border-b border-[var(--gray-4)] cursor-pointer hover:bg-[var(--gray-3)]"
              style={{ background: "var(--gray-2)" }}>
        <div className="flex items-center gap-2">
          <Text size="2">{expanded ? "▼" : "▶"} via <span className="font-mono font-semibold">{token}</span></Text>
          <Text size="1" style={{ color: "var(--gray-9)" }}>
            ({n_total.toLocaleString()} total{full === null ? `, showing ${preview.length} preview` : ""})
          </Text>
        </div>
      </button>
      {expanded && (
        <div className="flex flex-col py-1 max-h-[28rem] overflow-y-auto">
          {entries.map((e, i) => <EntryRow key={`${e.level}-${e.value}-${i}`} entry={e} />)}
          {full !== null && pages > 1 && (
            <div className="flex items-center gap-2 px-3 py-2">
              <Button size="1" variant="soft" disabled={page === 1 || loadingMore}
                      onClick={() => loadFull(page - 1)}>
                Previous
              </Button>
              <Text size="1" style={{ color: "var(--gray-9)" }}>
                Page {page} of {pages}
              </Text>
              <Button size="1" variant="soft" disabled={page === pages || loadingMore}
                      onClick={() => loadFull(page + 1)}>
                Next
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function BrandFamily({ seed_value, seed_level }: BrandFamilyProps) {
  const [data, setData] = useState<BrandFamilyResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    fetchApi<BrandFamilyResponse>("/explorer/brands/family", {
      seed_value, seed_level,
    }).then(setData).catch((e) => setErr(String(e)));
  }, [seed_value, seed_level]);

  if (err) return <Text color="tomato">Family load error: {err}</Text>;
  if (!data) return <Text size="2" style={{ color: "var(--gray-9)" }}>Loading family…</Text>;

  return (
    <>
      <Heading size="4" mt="6" mb="2">Family — Tight</Heading>
      <Text size="2" style={{ color: "var(--gray-9)" }}>
        n-grams across all 6 silos that contain this seed as a contiguous word run
      </Text>
      <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] overflow-hidden mt-2 max-h-[24rem] overflow-y-auto">
        <div className="flex flex-col py-1">
          {data.tight.length === 0 ? (
            <div className="px-3 py-3 text-[13px]" style={{ color: "var(--gray-9)" }}>
              (no descendants)
            </div>
          ) : data.tight.map((e, i) => <EntryRow key={`${e.level}-${e.value}-${i}`} entry={e} />)}
        </div>
      </div>

      <Heading size="4" mt="6" mb="2">Family — Loose</Heading>
      <Text size="2" style={{ color: "var(--gray-9)" }}>
        n-grams across all 6 silos containing one of this seed's constituent tokens
      </Text>
      <div className="flex flex-col gap-2 mt-2">
        {data.loose_sections.map((s, i) => (
          <LooseSection key={i} token={s.token} n_total={s.n_total} preview={s.preview} />
        ))}
      </div>
    </>
  );
}
