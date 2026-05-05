import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Text, Heading, Badge, Button } from "@radix-ui/themes";
import { X } from "@phosphor-icons/react";
import { fetchApi } from "../../api/client";
import { formatCurrency, formatDate } from "../../lib/utils";
import type { TenureDetail } from "../../types";

interface Props {
  contactId: string;
  stem: string | null;
  onClose: () => void;
}

export default function TenureDetailDrawer({ contactId, stem, onClose }: Props) {
  const [data, setData] = useState<TenureDetail | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!stem) return;
    setLoading(true);
    setData(null);
    fetchApi<TenureDetail>(`/contacts/${contactId}/tenures/${encodeURIComponent(stem)}`)
      .then((d) => setData(d))
      .finally(() => setLoading(false));
  }, [contactId, stem]);

  if (!stem) return null;

  return (
    <>
      <div
        className="fixed inset-0 z-40 bg-black/30"
        onClick={onClose}
      />
      <div
        className="fixed top-0 right-0 z-50 w-[560px] max-w-[90vw] h-screen bg-white shadow-xl border-l border-[var(--gray-6)] flex flex-col"
      >
        <div className="flex items-center justify-between p-4 border-b border-[var(--gray-6)]">
          <Heading size="3" weight="medium">
            {data?.display_name ?? stem}
          </Heading>
          <Button size="1" variant="ghost" onClick={onClose}>
            <X size={16} />
          </Button>
        </div>
        <div className="flex-1 overflow-y-auto p-5 flex flex-col gap-5">
          {loading && <Text size="2">Loading...</Text>}
          {data && (
            <>
              <div>
                <Text size="2" style={{ color: "var(--gray-9)" }}>
                  {formatDate(data.inferred_start_date)} – {formatDate(data.inferred_end_date)}
                  {" "}· {data.credited_transactions.length} deals credited (Realtrack)
                </Text>
              </div>

              {/* Why we named this tenure */}
              <section>
                <Text size="2" weight="medium" className="block mb-2">Why we named this tenure</Text>
                <Text size="1" style={{ color: "var(--gray-9)" }} className="block mb-1">Top phrases:</Text>
                <ul className="text-[13px] mb-3">
                  {data.top_phrases.map((tp, i) => (
                    <li key={i} className="flex justify-between">
                      <span>{tp.phrase}</span>
                      <span style={{ color: "var(--gray-9)" }}>{tp.n}×</span>
                    </li>
                  ))}
                </ul>
                <Text size="1" style={{ color: "var(--gray-9)" }} className="block mb-1">Source field breakdown:</Text>
                <ul className="text-[13px]">
                  {Object.entries(data.source_field_breakdown).map(([k, v]) => (
                    <li key={k} className="flex justify-between">
                      <span>{k}</span>
                      <span style={{ color: "var(--gray-9)" }}>{v}</span>
                    </li>
                  ))}
                </ul>
              </section>

              {/* Window */}
              <section>
                <Text size="2" weight="medium" className="block mb-2">Window</Text>
                <div className="text-[13px] flex flex-col gap-1">
                  <div className="flex justify-between">
                    <span>Earliest explicit mention:</span>
                    <span>{formatDate(data.strict_start_date)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Inferred start (via address):</span>
                    <span>{formatDate(data.inferred_start_date)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Latest:</span>
                    <span>{formatDate(data.inferred_end_date)}</span>
                  </div>
                  {data.dominant_address_unit && (
                    <div className="flex justify-between">
                      <span>Dominant address:</span>
                      <span style={{ color: "var(--gray-9)" }}>
                        {data.dominant_address_unit.split("|").slice(1, 5).filter(Boolean).join(" ")}
                      </span>
                    </div>
                  )}
                </div>
              </section>

              {/* Linked auto_group */}
              {data.auto_group_id && (
                <section>
                  <Text size="2" weight="medium" className="block mb-2">Linked auto_group</Text>
                  <Link
                    to={`/explorer/auto-groups/${data.auto_group_id}`}
                    className="no-underline"
                    style={{ color: "var(--accent-11)" }}
                  >
                    {data.auto_group_id} — {data.auto_group_display_name ?? "(unnamed)"}
                  </Link>
                </section>
              )}

              {/* Credited transactions */}
              <section>
                <Text size="2" weight="medium" className="block mb-2">
                  Credited transactions ({data.credited_transactions.length})
                </Text>
                <table className="w-full text-[13px]">
                  <thead>
                    <tr className="border-b border-[var(--gray-4)]">
                      <th className="text-left py-1 text-[11px] font-medium" style={{ color: "var(--gray-9)" }}>Date</th>
                      <th className="text-left py-1 text-[11px] font-medium" style={{ color: "var(--gray-9)" }}>Address</th>
                      <th className="text-right py-1 text-[11px] font-medium" style={{ color: "var(--gray-9)" }}>Price</th>
                      <th className="text-left py-1 text-[11px] font-medium" style={{ color: "var(--gray-9)" }}>Source</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.credited_transactions.map((t) => (
                      <tr key={t.source_id} className="border-b border-[var(--gray-4)]">
                        <td className="py-1">{formatDate(t.sale_date)}</td>
                        <td className="py-1">{t.display_address}</td>
                        <td className="py-1 text-right">{formatCurrency(t.sale_price)}</td>
                        <td className="py-1">
                          {t.inferred ? (
                            <Badge size="1" color="amber" variant="soft">via address</Badge>
                          ) : (
                            <Badge size="1" color="jade" variant="soft">{t.source_field}</Badge>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </section>
            </>
          )}
        </div>
      </div>
    </>
  );
}
