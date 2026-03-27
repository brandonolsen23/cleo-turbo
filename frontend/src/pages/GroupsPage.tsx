import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Heading, Text, Button } from "@radix-ui/themes";
import { fetchApi } from "../api/client";
import type { GroupBrowseItem, BrowseResponse } from "../types";

export default function GroupsPage() {
  const navigate = useNavigate();
  const [data, setData] = useState<BrowseResponse<GroupBrowseItem> | null>(null);
  const [page, setPage] = useState(1);

  useEffect(() => {
    fetchApi<BrowseResponse<GroupBrowseItem>>("/groups", { page: String(page), per_page: "25" }).then(setData);
  }, [page]);

  if (!data) return <Text>Loading...</Text>;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <Heading size="5" weight="medium">Groups</Heading>
        <Text size="2" style={{ color: "var(--gray-9)" }}>{data.total.toLocaleString()} total</Text>
      </div>
      <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] overflow-hidden">
        <table className="w-full text-[14px]">
          <thead>
            <tr style={{ background: "var(--gray-2)" }}>
              <th className="text-left px-4 py-2 text-[12px] font-medium border-b border-[var(--gray-6)]" style={{ color: "var(--gray-9)" }}>Name</th>
              <th className="text-left px-4 py-2 text-[12px] font-medium border-b border-[var(--gray-6)]" style={{ color: "var(--gray-9)" }}>Status</th>
              <th className="text-right px-4 py-2 text-[12px] font-medium border-b border-[var(--gray-6)]" style={{ color: "var(--gray-9)" }}>Properties</th>
              <th className="text-right px-4 py-2 text-[12px] font-medium border-b border-[var(--gray-6)]" style={{ color: "var(--gray-9)" }}>Contacts</th>
              <th className="text-right px-4 py-2 text-[12px] font-medium border-b border-[var(--gray-6)]" style={{ color: "var(--gray-9)" }}>Txns</th>
            </tr>
          </thead>
          <tbody>
            {data.results.map((g) => (
              <tr key={g.id} className="border-b border-[var(--gray-4)] hover:bg-[var(--gray-a2)] cursor-pointer"
                  onClick={() => navigate(`/groups/${g.id}`)}>
                <td className="px-4 py-2 font-medium">{g.display_name}</td>
                <td className="px-4 py-2">
                  <span className={`inline-block px-2 py-0.5 rounded text-[12px] ${g.status === 'engaged' ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-600'}`}>
                    {g.status}
                  </span>
                </td>
                <td className="px-4 py-2 text-right">{g.property_count}</td>
                <td className="px-4 py-2 text-right">{g.contact_count}</td>
                <td className="px-4 py-2 text-right">{g.transaction_count}</td>
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
