import { useState, useEffect } from "react";
import { Link, useParams, useNavigate } from "react-router-dom";
import { Heading, Text, Badge } from "@radix-ui/themes";
import { fetchApi } from "../api/client";
import { formatCurrency, formatDate, formatPhone } from "../lib/utils";
import type { TransactionDetail } from "../types";

export default function TransactionDetailPage() {
  const { sourceId } = useParams();
  const navigate = useNavigate();
  const [txn, setTxn] = useState<TransactionDetail | null>(null);

  useEffect(() => {
    if (sourceId) fetchApi<TransactionDetail>(`/transactions/${sourceId}`).then(setTxn);
  }, [sourceId]);

  if (!txn) return <Text>Loading...</Text>;

  const sellers = txn.parties?.filter((p) => p.side === "seller") ?? [];
  const buyers = txn.parties?.filter((p) => p.side === "buyer") ?? [];

  return (
    <div className="flex flex-col gap-6">
      <div>
        <Link to="/transactions" className="text-[14px] no-underline" style={{ color: "var(--accent-11)" }}>
          &larr; Transactions
        </Link>
        <Heading size="5" weight="medium" className="mt-2">{txn.display_address}</Heading>
        <div className="flex items-center gap-3 mt-1">
          <Text size="2" style={{ color: "var(--gray-9)" }}>{txn.city}, {txn.region}</Text>
          <Text size="2" style={{ color: "var(--gray-9)" }}>{txn.source_id}</Text>
        </div>
      </div>

      {/* Key Facts */}
      <div className="grid grid-cols-4 gap-4">
        <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
          <Text size="1" style={{ color: "var(--gray-9)" }}>Sale Price</Text>
          <Text size="4" weight="medium" className="mt-1 block">{formatCurrency(txn.sale_price)}</Text>
        </div>
        <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
          <Text size="1" style={{ color: "var(--gray-9)" }}>Sale Date</Text>
          <Text size="4" weight="medium" className="mt-1 block">{formatDate(txn.sale_date)}</Text>
        </div>
        <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
          <Text size="1" style={{ color: "var(--gray-9)" }}>ARN</Text>
          <Text size="3" weight="medium" className="mt-1 block">{txn.arn || "—"}</Text>
        </div>
        <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
          <Text size="1" style={{ color: "var(--gray-9)" }}>Property</Text>
          {txn.property_id ? (
            <Link to={`/properties/${txn.property_id}`} className="text-[14px] font-medium mt-1 block no-underline" style={{ color: "var(--accent-11)" }}>
              View Property
            </Link>
          ) : (
            <Text size="3" weight="medium" className="mt-1 block">—</Text>
          )}
        </div>
      </div>

      {/* Parties */}
      <div className="grid grid-cols-2 gap-4">
        <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
          <Text size="3" weight="medium" className="mb-3 block">Sellers</Text>
          {sellers.length === 0 ? (
            <Text size="2" style={{ color: "var(--gray-9)" }}>—</Text>
          ) : (
            <div className="flex flex-col gap-3">
              {sellers.map((p, i) => (
                <div key={i} className="flex flex-col gap-0.5">
                  <div className="flex items-center gap-2">
                    <Text size="2" weight="medium">{p.party_name || "Unknown"}</Text>
                    {p.contact_title && (
                      <Text size="1" style={{ color: "var(--gray-9)" }}>{p.contact_title}</Text>
                    )}
                  </div>
                  {p.phone && (
                    <a href={`tel:${p.phone}`} className="text-[13px] no-underline" style={{ color: "var(--accent-11)" }}>
                      {formatPhone(p.phone)}
                    </a>
                  )}
                  <div className="flex gap-2 mt-1">
                    {p.contact_id && (
                      <Badge size="1" variant="soft" className="cursor-pointer" onClick={() => navigate(`/contacts/${p.contact_id}`)}>
                        {p.contact_name}
                      </Badge>
                    )}
                    {p.group_id && (
                      <Badge size="1" variant="soft" color="jade" className="cursor-pointer" onClick={() => navigate(`/groups/${p.group_id}`)}>
                        {p.group_name}
                      </Badge>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
          <Text size="3" weight="medium" className="mb-3 block">Buyers</Text>
          {buyers.length === 0 ? (
            <Text size="2" style={{ color: "var(--gray-9)" }}>—</Text>
          ) : (
            <div className="flex flex-col gap-3">
              {buyers.map((p, i) => (
                <div key={i} className="flex flex-col gap-0.5">
                  <div className="flex items-center gap-2">
                    <Text size="2" weight="medium">{p.party_name || "Unknown"}</Text>
                    {p.contact_title && (
                      <Text size="1" style={{ color: "var(--gray-9)" }}>{p.contact_title}</Text>
                    )}
                  </div>
                  {p.phone && (
                    <a href={`tel:${p.phone}`} className="text-[13px] no-underline" style={{ color: "var(--accent-11)" }}>
                      {formatPhone(p.phone)}
                    </a>
                  )}
                  <div className="flex gap-2 mt-1">
                    {p.contact_id && (
                      <Badge size="1" variant="soft" className="cursor-pointer" onClick={() => navigate(`/contacts/${p.contact_id}`)}>
                        {p.contact_name}
                      </Badge>
                    )}
                    {p.group_id && (
                      <Badge size="1" variant="soft" color="jade" className="cursor-pointer" onClick={() => navigate(`/groups/${p.group_id}`)}>
                        {p.group_name}
                      </Badge>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Consideration */}
      {txn.consideration && (txn.consideration.cash != null || txn.consideration.debt != null || txn.consideration.chattels != null || txn.consideration.other != null) && (
        <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
          <Text size="3" weight="medium" className="mb-3 block">Consideration</Text>
          <div className="grid grid-cols-4 gap-4 text-[14px]">
            {txn.consideration.cash != null && (
              <div>
                <Text size="1" style={{ color: "var(--gray-9)" }}>Cash</Text>
                <Text size="2" weight="medium" className="block">{formatCurrency(txn.consideration.cash)}</Text>
              </div>
            )}
            {txn.consideration.debt != null && (
              <div>
                <Text size="1" style={{ color: "var(--gray-9)" }}>Assumed Debt</Text>
                <Text size="2" weight="medium" className="block">{formatCurrency(txn.consideration.debt)}</Text>
              </div>
            )}
            {txn.consideration.chattels != null && (
              <div>
                <Text size="1" style={{ color: "var(--gray-9)" }}>Chattels</Text>
                <Text size="2" weight="medium" className="block">{formatCurrency(txn.consideration.chattels)}</Text>
              </div>
            )}
            {txn.consideration.other != null && (
              <div>
                <Text size="1" style={{ color: "var(--gray-9)" }}>Other</Text>
                <Text size="2" weight="medium" className="block">{formatCurrency(txn.consideration.other)}</Text>
              </div>
            )}
          </div>
          {txn.consideration.charges.length > 0 && (
            <Text size="2" className="mt-3 block" style={{ color: "var(--gray-9)" }}>
              Charges: {txn.consideration.charges.join(", ")}
            </Text>
          )}
        </div>
      )}

      {/* Brokers */}
      {txn.brokers && txn.brokers.length > 0 && (
        <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
          <Text size="3" weight="medium" className="mb-2 block">Brokers</Text>
          <div className="flex flex-col gap-2">
            {txn.brokers.map((b, i) => (
              <div key={i}>
                {b.broker_name && <Text size="2" weight="medium" className="block">{b.broker_name}</Text>}
                {b.phone && (
                  <a href={`tel:${b.phone}`} className="text-[13px] no-underline" style={{ color: "var(--accent-11)" }}>
                    {formatPhone(b.phone)}
                  </a>
                )}
                {b.agents.length > 0 && (
                  <Text size="1" className="block mt-0.5" style={{ color: "var(--gray-9)" }}>
                    Agents: {b.agents.join(", ")}
                  </Text>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Description / Notes */}
      {(txn.description || txn.transaction_note) && (
        <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
          <Text size="3" weight="medium" className="mb-2 block">Description</Text>
          <Text size="2" style={{ color: "var(--gray-11)", whiteSpace: "pre-line" }}>
            {txn.description || txn.transaction_note}
          </Text>
        </div>
      )}

      {/* Legal Description */}
      {txn.legal_description && (
        <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
          <Text size="3" weight="medium" className="mb-2 block">Legal Description</Text>
          <Text size="2" style={{ color: "var(--gray-11)", whiteSpace: "pre-line" }}>{txn.legal_description}</Text>
        </div>
      )}

      {/* Photos */}
      {txn.photos_json && (() => {
        const photos = txn.photos_json as { street_photo_urls?: string[]; aerial_photo_urls?: string[] };
        const allPhotos = [...(photos.street_photo_urls || []), ...(photos.aerial_photo_urls || [])];
        return allPhotos.length > 0 ? (
          <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
            <Text size="3" weight="medium" className="mb-3 block">Photos</Text>
            <div className="grid grid-cols-3 gap-3">
              {allPhotos.map((url, i) => (
                <img key={i} src={url} alt={`Photo ${i + 1}`} className="rounded-lg w-full object-cover aspect-[4/3]" />
              ))}
            </div>
          </div>
        ) : null;
      })()}
    </div>
  );
}
