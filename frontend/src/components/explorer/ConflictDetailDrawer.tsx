import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Dialog, Heading, Text, Badge } from "@radix-ui/themes";
import { fetchApi } from "../../api/client";
import type { ConflictDetailResponse } from "../../types";


export default function ConflictDetailDrawer({
  conflictId, onClose,
}: {
  conflictId: number;
  onClose: () => void;
}) {
  const [data, setData] = useState<ConflictDetailResponse | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchApi<ConflictDetailResponse>(`/explorer/conflicts/${conflictId}`)
      .then((d) => { if (!cancelled) setData(d); })
      .catch(console.error);
    return () => { cancelled = true; };
  }, [conflictId]);

  return (
    <Dialog.Root open={true} onOpenChange={(o) => { if (!o) onClose(); }}>
      <Dialog.Content style={{ maxWidth: 900 }}>
        {!data ? (
          <Text>Loading…</Text>
        ) : (
          <>
            <Dialog.Title>
              <Badge>{data.conflict.conflict_type}</Badge>{' '}
              <span className="font-mono">{data.conflict.entity_value}</span>
            </Dialog.Title>
            <Text size="2" style={{ color: 'var(--gray-9)' }} className="block mb-4">
              {data.conflict.description}
            </Text>

            <div className="grid grid-cols-2 gap-4">
              {Object.entries(data.timelines).map(([gid, events]) => (
                <div key={gid}>
                  <Heading size="3" mb="2">
                    <Link to={`/explorer/auto-groups/${encodeURIComponent(gid)}`}
                          style={{ color: 'var(--accent-11)' }} className="no-underline">
                      {gid}
                    </Link>
                  </Heading>
                  <div className="text-[12px] font-mono">
                    {events.length === 0 ? (
                      <Text size="1" style={{ color: 'var(--gray-9)' }}>No events.</Text>
                    ) : (
                      events.map((e, i) => (
                        <div key={i} className="border-t border-[var(--gray-4)] py-1">
                          {e.sale_date} | {e.source_id} | {e.side}
                        </div>
                      ))
                    )}
                  </div>
                </div>
              ))}
            </div>
          </>
        )}
      </Dialog.Content>
    </Dialog.Root>
  );
}
