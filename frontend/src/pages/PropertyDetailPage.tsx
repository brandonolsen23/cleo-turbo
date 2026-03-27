import { useState, useEffect } from "react";
import { Link, useParams, useNavigate } from "react-router-dom";
import { Heading, Text, Badge } from "@radix-ui/themes";
import { Copy } from "@phosphor-icons/react";
import { fetchApi } from "../api/client";
import { formatCurrency, formatDate, formatPhone } from "../lib/utils";
import type { PropertyDetail } from "../types";

export default function PropertyDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [prop, setProp] = useState<PropertyDetail | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (id) fetchApi<PropertyDetail>(`/properties/${id}`).then(setProp);
  }, [id]);

  if (!prop) return <Text>Loading...</Text>;

  const copyArn = () => {
    navigator.clipboard.writeText(prop.arn);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div className="flex flex-col gap-6">
      {/* Header */}
      <div>
        <Link to="/properties" className="text-[14px] no-underline" style={{ color: "var(--accent-11)" }}>
          &larr; Properties
        </Link>
        <Heading size="5" weight="medium" className="mt-2">{prop.display_address}</Heading>
        <Text size="2" style={{ color: "var(--gray-9)" }}>{prop.city}, {prop.region}</Text>
      </div>

      {/* Two-column layout */}
      <div className="grid grid-cols-3 gap-6">
        {/* Left column */}
        <div className="col-span-1 flex flex-col gap-4">
          {/* ARN */}
          <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
            <Text size="1" style={{ color: "var(--gray-9)" }}>ARN</Text>
            <div className="flex items-center gap-2 mt-1">
              <Text size="2" weight="medium" className="font-mono">{prop.arn}</Text>
              <button onClick={copyArn} className="p-1 rounded hover:bg-gray-100 transition-colors" title="Copy ARN">
                <Copy size={14} style={{ color: copied ? "var(--jade-9)" : "var(--gray-9)" }} />
              </button>
            </div>
          </div>

          {/* Owner */}
          <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
            <Text size="3" weight="medium" className="mb-3 block">Owner</Text>
            <Text size="2" weight="medium" className="block">{prop.current_owner_name || "—"}</Text>
            {prop.current_owner_group_id && (
              <Link to={`/groups/${prop.current_owner_group_id}`} className="text-[13px] no-underline mt-1 block" style={{ color: "var(--accent-11)" }}>
                View Group
              </Link>
            )}
          </div>

          {/* Property Details */}
          <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
            <Text size="3" weight="medium" className="mb-3 block">Details</Text>
            <div className="flex flex-col gap-2 text-[14px]">
              <div className="flex justify-between">
                <Text size="2" style={{ color: "var(--gray-9)" }}>Latest Sale</Text>
                <Text size="2" weight="medium">{formatCurrency(prop.most_recent_sale_price)}</Text>
              </div>
              <div className="flex justify-between">
                <Text size="2" style={{ color: "var(--gray-9)" }}>Sale Date</Text>
                <Text size="2">{formatDate(prop.most_recent_sale_date)}</Text>
              </div>
              <div className="flex justify-between">
                <Text size="2" style={{ color: "var(--gray-9)" }}>Transactions</Text>
                <Text size="2" weight="medium">{prop.transaction_count}</Text>
              </div>
              {prop.acreage && (
                <div className="flex justify-between">
                  <Text size="2" style={{ color: "var(--gray-9)" }}>Acreage</Text>
                  <Text size="2">{prop.acreage} acres</Text>
                </div>
              )}
              <div className="flex justify-between">
                <Text size="2" style={{ color: "var(--gray-9)" }}>Postal</Text>
                <Text size="2">{prop.postal || "—"}</Text>
              </div>
            </div>
          </div>

          {/* Legal Description */}
          {prop.legal_description && (
            <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
              <Text size="3" weight="medium" className="mb-2 block">Legal Description</Text>
              <Text size="1" style={{ color: "var(--gray-11)", whiteSpace: "pre-line" }}>{prop.legal_description}</Text>
            </div>
          )}
        </div>

        {/* Right column: Transaction History */}
        <div className="col-span-2">
          <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
            <Text size="3" weight="medium" className="mb-3 block">Transaction History ({prop.transactions?.length ?? 0})</Text>
            {(!prop.transactions || prop.transactions.length === 0) ? (
              <Text size="2" style={{ color: "var(--gray-9)" }}>No transactions</Text>
            ) : (
              <div className="flex flex-col gap-4">
                {prop.transactions.map((t) => (
                  <div key={t.source_id}
                       className="border border-[var(--gray-4)] rounded-lg p-4 hover:border-[var(--gray-6)] cursor-pointer transition-colors"
                       onClick={() => navigate(`/transactions/${t.source_id}`)}>
                    <div className="flex items-center justify-between mb-2">
                      <Text size="2" weight="medium">{formatDate(t.sale_date)}</Text>
                      <Text size="3" weight="medium">{formatCurrency(t.sale_price)}</Text>
                    </div>
                    <div className="grid grid-cols-2 gap-3 text-[13px]">
                      <div>
                        <Text size="1" style={{ color: "var(--gray-9)" }}>Seller</Text>
                        <div className="flex flex-col gap-0.5 mt-0.5">
                          {t.seller_parties?.map((s, i) => (
                            <Text key={i} size="2">{s}</Text>
                          )) || <Text size="2">—</Text>}
                          {t.seller_phone && (
                            <a href={`tel:${t.seller_phone}`} className="no-underline text-[12px]" style={{ color: "var(--accent-11)" }}
                               onClick={(e) => e.stopPropagation()}>
                              {formatPhone(t.seller_phone)}
                            </a>
                          )}
                        </div>
                      </div>
                      <div>
                        <Text size="1" style={{ color: "var(--gray-9)" }}>Buyer</Text>
                        <div className="flex flex-col gap-0.5 mt-0.5">
                          {t.buyer_parties?.map((b, i) => (
                            <Text key={i} size="2">{b}</Text>
                          )) || <Text size="2">—</Text>}
                          {t.buyer_phone && (
                            <a href={`tel:${t.buyer_phone}`} className="no-underline text-[12px]" style={{ color: "var(--accent-11)" }}
                               onClick={(e) => e.stopPropagation()}>
                              {formatPhone(t.buyer_phone)}
                            </a>
                          )}
                        </div>
                      </div>
                    </div>
                    {t.transaction_note && (
                      <Text size="1" className="mt-2 block" style={{ color: "var(--gray-9)" }}>{t.transaction_note}</Text>
                    )}
                    <div className="mt-2">
                      <Badge size="1" variant="outline" color="gray">RT {t.source_id}</Badge>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
