import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Heading, Text, Badge, Select } from "@radix-ui/themes";
import { fetchApi } from "../api/client";
import ExplorerTabs from "../components/explorer/ExplorerTabs";
import ConflictDetailDrawer from "../components/explorer/ConflictDetailDrawer";
import type { ConflictsListResponse, ConflictType } from "../types";


const CONFLICT_TYPES: ConflictType[] = [
  'anchor_reassignment', 'contact_overlap', 'transient_tenure', 'expansion_conflict',
];


export default function ExplorerConflicts() {
  const [params, setParams] = useSearchParams();
  const type = params.get('type') ?? '';
  const page = parseInt(params.get('page') ?? '1', 10);
  const [data, setData] = useState<ConflictsListResponse | null>(null);
  const [openId, setOpenId] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    const qs = new URLSearchParams();
    if (type) qs.set('type', type);
    qs.set('page', String(page));
    qs.set('per_page', '100');
    fetchApi<ConflictsListResponse>(`/explorer/conflicts?${qs.toString()}`)
      .then((d) => { if (!cancelled) setData(d); })
      .catch(console.error);
    return () => { cancelled = true; };
  }, [type, page]);

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <ExplorerTabs />
      <div className="flex items-baseline gap-3 mt-2 mb-4">
        <Heading size="6">Conflicts</Heading>
        <Text size="2" style={{ color: 'var(--gray-9)' }}>
          {data ? `${data.total.toLocaleString()} flagged` : 'Loading…'}
        </Text>
      </div>

      <div className="mb-3 flex gap-3 items-center">
        <Text size="2">Filter:</Text>
        <Select.Root value={type || 'all'} onValueChange={(v) => {
          const next = new URLSearchParams(params);
          if (v === 'all') next.delete('type'); else next.set('type', v);
          next.delete('page');
          setParams(next);
        }}>
          <Select.Trigger />
          <Select.Content>
            <Select.Item value="all">All types</Select.Item>
            {CONFLICT_TYPES.map((t) => (
              <Select.Item key={t} value={t}>{t}</Select.Item>
            ))}
          </Select.Content>
        </Select.Root>
      </div>

      {data && (
        <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] overflow-hidden">
          <table className="w-full text-[13px]">
            <thead className="bg-[var(--gray-2)]">
              <tr style={{ color: 'var(--gray-9)' }}>
                <th className="text-left p-2 font-medium">type</th>
                <th className="text-left p-2 font-medium">entity</th>
                <th className="text-left p-2 font-medium">group_a</th>
                <th className="text-left p-2 font-medium">group_b</th>
                <th className="text-left p-2 font-medium">observed</th>
                <th className="text-left p-2 font-medium">description</th>
              </tr>
            </thead>
            <tbody>
              {data.results.map((c) => (
                <tr key={c.id} className="border-t border-[var(--gray-4)] hover:bg-[var(--gray-2)] cursor-pointer"
                    onClick={() => setOpenId(c.id)}>
                  <td className="p-2"><Badge>{c.conflict_type}</Badge></td>
                  <td className="p-2 font-mono break-all">{c.entity_value}</td>
                  <td className="p-2 font-mono">{c.group_a || '—'}</td>
                  <td className="p-2 font-mono">{c.group_b || '—'}</td>
                  <td className="p-2 font-mono">{c.date_observed || '—'}</td>
                  <td className="p-2" style={{ color: 'var(--gray-11)' }}>
                    {c.description.slice(0, 80)}{c.description.length > 80 ? '…' : ''}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {openId !== null && (
        <ConflictDetailDrawer conflictId={openId} onClose={() => setOpenId(null)} />
      )}
    </div>
  );
}
