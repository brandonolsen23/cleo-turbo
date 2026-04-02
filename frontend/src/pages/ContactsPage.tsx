import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Heading, Text, Button, Badge } from "@radix-ui/themes";
import { fetchApi } from "../api/client";
import { formatPhone } from "../lib/utils";
import type { ContactBrowseItem, BrowseResponse } from "../types";

export default function ContactsPage() {
  const navigate = useNavigate();
  const [data, setData] = useState<BrowseResponse<ContactBrowseItem> | null>(null);
  const [page, setPage] = useState(1);

  useEffect(() => {
    fetchApi<BrowseResponse<ContactBrowseItem>>("/contacts", { page: String(page), per_page: "25" }).then(setData);
  }, [page]);

  if (!data) return <Text>Loading...</Text>;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <Heading size="5" weight="medium">Contacts</Heading>
        <Text size="2" style={{ color: "var(--gray-9)" }}>{data.total.toLocaleString()} total</Text>
      </div>
      <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] overflow-hidden">
        <table className="w-full text-[14px]">
          <thead>
            <tr style={{ background: "var(--gray-2)" }}>
              <th className="text-left px-4 py-2 text-[12px] font-medium border-b border-[var(--gray-6)]" style={{ color: "var(--gray-9)" }}>Name</th>
              <th className="text-left px-4 py-2 text-[12px] font-medium border-b border-[var(--gray-6)]" style={{ color: "var(--gray-9)" }}>Company</th>
              <th className="text-left px-4 py-2 text-[12px] font-medium border-b border-[var(--gray-6)]" style={{ color: "var(--gray-9)" }}>Phone</th>
              <th className="text-left px-4 py-2 text-[12px] font-medium border-b border-[var(--gray-6)]" style={{ color: "var(--gray-9)" }}>Status</th>
              <th className="text-right px-4 py-2 text-[12px] font-medium border-b border-[var(--gray-6)]" style={{ color: "var(--gray-9)" }}>Txns</th>
            </tr>
          </thead>
          <tbody>
            {data.results.map((c) => (
              <tr key={c.id} className="border-b border-[var(--gray-4)] hover:bg-[var(--gray-a2)] cursor-pointer"
                  onClick={() => navigate(`/contacts/${c.id}`)}>
                <td className="px-4 py-2 font-medium">{c.display_name}</td>
                <td className="px-4 py-2" style={{ color: "var(--gray-11)" }}>{c.company_name || "—"}</td>
                <td className="px-4 py-2">{formatPhone(c.phone)}</td>
                <td className="px-4 py-2">
                  <Badge size="1" variant="soft" color={c.status === 'engaged' ? 'jade' : 'gray'}>
                    {c.status}
                  </Badge>
                </td>
                <td className="px-4 py-2 text-right">{c.transaction_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex items-center justify-between">
        <Text size="2" style={{ color: "var(--gray-9)" }}>Page {data.page} of {data.pages}</Text>
        <div className="flex gap-2">
          <Button size="1" variant="soft" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</Button>
          <Button size="1" variant="soft" disabled={page >= data.pages} onClick={() => setPage(page + 1)}>Next</Button>
        </div>
      </div>
    </div>
  );
}
