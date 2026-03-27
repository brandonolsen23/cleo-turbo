import { useState, useEffect } from "react";
import { Link, useParams, useNavigate } from "react-router-dom";
import { Heading, Text, Button, Badge } from "@radix-ui/themes";
import { fetchApi, mutateApi } from "../api/client";
import { useCrm } from "../components/crm/CrmContext";
import { formatCurrency, formatDate, formatPhone } from "../lib/utils";
import type { GroupDetail } from "../types";

export default function GroupDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { openDrawer } = useCrm();
  const [group, setGroup] = useState<GroupDetail | null>(null);

  const load = () => {
    if (id) fetchApi<GroupDetail>(`/groups/${id}`).then(setGroup);
  };

  useEffect(load, [id]);

  if (!group) return <Text>Loading...</Text>;

  const handlePromote = async () => {
    await mutateApi(`/groups/${id}/promote`, "POST");
    load();
  };

  return (
    <div className="flex flex-col gap-6">
      {/* Header */}
      <div>
        <Link to="/groups" className="text-[14px] no-underline" style={{ color: "var(--accent-11)" }}>
          &larr; Groups
        </Link>
        <div className="flex items-center gap-3 mt-2">
          <Heading size="5" weight="medium">{group.display_name}</Heading>
          <span className={`inline-block px-2 py-0.5 rounded text-[12px] ${group.status === 'engaged' ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-600'}`}>
            {group.status}
          </span>
          {group.status !== "engaged" && (
            <Button size="1" variant="soft" onClick={handlePromote}>Promote to Engaged</Button>
          )}
          <Button size="1" variant="outline" onClick={() => openDrawer({ type: "group", id: group.id, name: group.display_name })}>
            Notes
          </Button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-4">
        <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
          <Text size="1" style={{ color: "var(--gray-9)" }}>Properties</Text>
          <Heading size="5" weight="medium" className="mt-1">{group.property_count}</Heading>
        </div>
        <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
          <Text size="1" style={{ color: "var(--gray-9)" }}>Transactions</Text>
          <Heading size="5" weight="medium" className="mt-1">{group.transaction_count}</Heading>
        </div>
        <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
          <Text size="1" style={{ color: "var(--gray-9)" }}>Contacts</Text>
          <Heading size="5" weight="medium" className="mt-1">{group.contact_count}</Heading>
        </div>
      </div>

      {/* Known Names */}
      {group.known_names.length > 1 && (
        <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
          <Text size="3" weight="medium" className="mb-3 block">Known Names</Text>
          <div className="flex flex-wrap gap-2">
            {group.known_names.map((n) => (
              <Badge key={n.normalized} size="1" variant="soft">{n.name}</Badge>
            ))}
          </div>
        </div>
      )}

      {/* Contacts */}
      <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
        <Text size="3" weight="medium" className="mb-3 block">Contacts ({group.contacts.length})</Text>
        {group.contacts.length === 0 ? (
          <Text size="2" style={{ color: "var(--gray-9)" }}>No contacts</Text>
        ) : (
          <table className="w-full text-[14px]">
            <thead>
              <tr className="border-b border-[var(--gray-4)]">
                <th className="text-left py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Name</th>
                <th className="text-left py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Phone</th>
                <th className="text-left py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Job Title</th>
                <th className="text-left py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Status</th>
                <th className="text-right py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Txns</th>
              </tr>
            </thead>
            <tbody>
              {group.contacts.map((c) => (
                <tr key={c.id} className="border-b border-[var(--gray-4)] hover:bg-[var(--gray-a2)] cursor-pointer"
                    onClick={() => navigate(`/contacts/${c.id}`)}>
                  <td className="py-2 font-medium">{c.display_name}</td>
                  <td className="py-2">
                    {c.phone ? (
                      <a href={`tel:${c.phone}`} className="no-underline" style={{ color: "var(--accent-11)" }}
                         onClick={(e) => e.stopPropagation()}>
                        {formatPhone(c.phone)}
                      </a>
                    ) : "—"}
                  </td>
                  <td className="py-2" style={{ color: "var(--gray-11)" }}>{c.job_title || "—"}</td>
                  <td className="py-2">
                    <span className={`inline-block px-2 py-0.5 rounded text-[12px] ${c.status === 'engaged' ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-600'}`}>
                      {c.status}
                    </span>
                  </td>
                  <td className="py-2 text-right">{c.transaction_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Properties */}
      <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
        <Text size="3" weight="medium" className="mb-3 block">Properties ({group.properties.length})</Text>
        {group.properties.length === 0 ? (
          <Text size="2" style={{ color: "var(--gray-9)" }}>No properties</Text>
        ) : (
          <table className="w-full text-[14px]">
            <thead>
              <tr className="border-b border-[var(--gray-4)]">
                <th className="text-left py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Address</th>
                <th className="text-left py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>City</th>
                <th className="text-right py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Last Sale</th>
                <th className="text-right py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Price</th>
              </tr>
            </thead>
            <tbody>
              {group.properties.map((p) => (
                <tr key={p.id} className="border-b border-[var(--gray-4)] hover:bg-[var(--gray-a2)] cursor-pointer"
                    onClick={() => navigate(`/properties/${p.id}`)}>
                  <td className="py-2">{p.display_address}</td>
                  <td className="py-2">{p.city}</td>
                  <td className="py-2 text-right">{formatDate(p.most_recent_sale_date)}</td>
                  <td className="py-2 text-right">{formatCurrency(p.most_recent_sale_price)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Transaction History */}
      <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
        <Text size="3" weight="medium" className="mb-3 block">Transaction History</Text>
        {group.transactions.length === 0 ? (
          <Text size="2" style={{ color: "var(--gray-9)" }}>No transactions</Text>
        ) : (
          <table className="w-full text-[14px]">
            <thead>
              <tr className="border-b border-[var(--gray-4)]">
                <th className="text-left py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Date</th>
                <th className="text-left py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Address</th>
                <th className="text-left py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>City</th>
                <th className="text-left py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Side</th>
                <th className="text-right py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Price</th>
              </tr>
            </thead>
            <tbody>
              {group.transactions.map((t, i) => (
                <tr key={`${t.source_id}-${i}`} className="border-b border-[var(--gray-4)] hover:bg-[var(--gray-a2)] cursor-pointer"
                    onClick={() => navigate(`/transactions/${t.source_id}`)}>
                  <td className="py-2">{formatDate(t.sale_date)}</td>
                  <td className="py-2">{t.display_address}</td>
                  <td className="py-2">{t.city}</td>
                  <td className="py-2">
                    <Badge size="1" variant="soft" color={t.side === "buyer" ? "blue" : "orange"}>
                      {t.side}
                    </Badge>
                  </td>
                  <td className="py-2 text-right">{formatCurrency(t.sale_price)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
