import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { TextField, Heading, Text, Badge } from "@radix-ui/themes";
import { fetchApi } from "../../api/client";
import type { BrandSearchResponse, BrandSearchEntry } from "../../types";

const LEVELS = [
  { key: "1gram",     label: "1-gram",       pathSeg: "1gram" },
  { key: "2gram",     label: "2-gram",       pathSeg: "2gram" },
  { key: "3gram",     label: "3-gram",       pathSeg: "3gram" },
  { key: "4gram",     label: "4-gram",       pathSeg: "4gram" },
  { key: "5gram",     label: "5-gram",       pathSeg: "5gram" },
  { key: "long-form", label: "6+ long-form", pathSeg: "long-form" },
] as const;

type LevelKey = (typeof LEVELS)[number]["key"];

function detailHref(levelKey: LevelKey, value: string): string {
  const seg = LEVELS.find((l) => l.key === levelKey)?.pathSeg ?? levelKey;
  return `/explorer/brands/${seg}/${encodeURIComponent(value)}`;
}

function ResultRow({ entry, levelKey }: { entry: BrandSearchEntry; levelKey: LevelKey }) {
  return (
    <Link to={detailHref(levelKey, entry.value)} className="no-underline">
      <div className="flex items-center gap-2 px-3 py-1.5 hover:bg-[var(--gray-3)] rounded text-[13px]">
        <span className="font-mono" style={{ color: "var(--accent-11)" }}>
          {entry.value}
        </span>
        {entry.is_distinctive ? (
          <Badge size="1" color="jade" variant="soft">distinctive</Badge>
        ) : null}
        {entry.is_position_anchor ? (
          <Badge size="1" color="amber" variant="soft">PA</Badge>
        ) : null}
        <div className="flex-1" />
        <Text size="1" style={{ color: "var(--gray-9)" }}>
          {entry.n_party_sides.toLocaleString()} sides
        </Text>
      </div>
    </Link>
  );
}

export default function BrandSearchBar() {
  const [q, setQ] = useState("");
  const [data, setData] = useState<BrandSearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const debounceTimer = useRef<number | null>(null);

  useEffect(() => {
    if (debounceTimer.current) {
      window.clearTimeout(debounceTimer.current);
      debounceTimer.current = null;
    }
    if (!q.trim()) {
      setData(null);
      return;
    }
    debounceTimer.current = window.setTimeout(() => {
      setLoading(true);
      fetchApi<BrandSearchResponse>("/explorer/brands/search", {
        q: q.trim(), per_level: 25,
      })
        .then(setData)
        .catch((e) => console.error(e))
        .finally(() => setLoading(false));
    }, 250);
    return () => {
      if (debounceTimer.current) {
        window.clearTimeout(debounceTimer.current);
      }
    };
  }, [q]);

  const totalResults = data
    ? LEVELS.reduce((sum, l) => sum + (data.results_by_level[l.key]?.length ?? 0), 0)
    : 0;

  return (
    <div
      className="rounded-[var(--card-radius)] border border-[var(--gray-6)] mb-5"
      style={{ background: "var(--gray-2)" }}
    >
      <div className="px-4 py-3 flex items-center gap-3 flex-wrap">
        <Heading size="3">Search brands</Heading>
        <Text size="1" style={{ color: "var(--gray-9)" }}>
          across all 6 silos
        </Text>
        <div className="flex-1 max-w-md">
          <TextField.Root
            size="2"
            placeholder="kingsett, dh management, regional group, …"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>
        {loading && (
          <Text size="1" style={{ color: "var(--gray-9)" }}>Searching…</Text>
        )}
        {data && !loading && (
          <Text size="1" style={{ color: "var(--gray-9)" }}>
            {totalResults} results
          </Text>
        )}
      </div>
      {data && (
        <div className="border-t border-[var(--gray-4)] p-3 flex flex-col gap-3">
          {LEVELS.map((lvl) => {
            const rows = data.results_by_level[lvl.key] ?? [];
            if (rows.length === 0) return null;
            return (
              <div key={lvl.key}>
                <Text size="2" weight="medium" style={{ color: "var(--gray-11)" }}>
                  {lvl.label} ({rows.length})
                </Text>
                <div className="flex flex-col mt-1">
                  {rows.map((r, i) => (
                    <ResultRow key={`${lvl.key}-${r.value}-${i}`} entry={r} levelKey={lvl.key} />
                  ))}
                </div>
              </div>
            );
          })}
          {totalResults === 0 && (
            <Text size="2" style={{ color: "var(--gray-9)" }}>
              No matches.
            </Text>
          )}
        </div>
      )}
    </div>
  );
}
