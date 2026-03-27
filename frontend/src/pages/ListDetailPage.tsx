import { useState, useEffect } from "react";
import { Link, useParams } from "react-router-dom";
import { Heading, Text, Badge } from "@radix-ui/themes";
import { Trash } from "@phosphor-icons/react";
import { fetchApi, mutateApi } from "../api/client";
import { formatDate } from "../lib/utils";

interface ListMember {
  member_type: string;
  member_id: string;
  added_at: string;
  name?: string;
  detail?: string;
}

interface ListDetail {
  id: string;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
  members: ListMember[];
}

export default function ListDetailPage() {
  const { id } = useParams();
  const [list, setList] = useState<ListDetail | null>(null);

  const load = () => {
    if (id) fetchApi<ListDetail>(`/lists/${id}`).then(setList);
  };

  useEffect(load, [id]);

  const removeMember = async (memberType: string, memberId: string) => {
    await mutateApi(`/lists/${id}/members/${memberType}/${memberId}`, "DELETE");
    load();
  };

  if (!list) return <Text>Loading...</Text>;

  const typeColor = (t: string) => {
    switch (t) {
      case "property": return "jade" as const;
      case "contact": return "blue" as const;
      case "group": return "amber" as const;
      default: return "gray" as const;
    }
  };

  const entityLink = (type: string, id: string) => {
    switch (type) {
      case "property": return `/properties/${id}`;
      case "contact": return `/contacts/${id}`;
      case "group": return `/groups/${id}`;
      case "transaction": return `/transactions/${id}`;
      default: return "#";
    }
  };

  return (
    <div className="flex flex-col gap-6">
      <div>
        <Link to="/lists" className="text-[14px] no-underline" style={{ color: "var(--accent-11)" }}>
          &larr; Lists
        </Link>
        <Heading size="5" weight="medium" className="mt-2">{list.name}</Heading>
        {list.description && (
          <Text size="2" className="mt-1 block" style={{ color: "var(--gray-9)" }}>{list.description}</Text>
        )}
      </div>

      <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
        <Text size="3" weight="medium" className="mb-3 block">Members ({list.members.length})</Text>
        {list.members.length === 0 ? (
          <Text size="2" style={{ color: "var(--gray-9)" }}>No members yet. Add items from property, contact, or group pages.</Text>
        ) : (
          <table className="w-full text-[14px]">
            <thead>
              <tr className="border-b border-[var(--gray-4)]">
                <th className="text-left py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Type</th>
                <th className="text-left py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Name</th>
                <th className="text-left py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Detail</th>
                <th className="text-left py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Added</th>
                <th className="w-8"></th>
              </tr>
            </thead>
            <tbody>
              {list.members.map((m) => (
                <tr key={`${m.member_type}-${m.member_id}`} className="border-b border-[var(--gray-4)] hover:bg-[var(--gray-a2)]">
                  <td className="py-2">
                    <Badge size="1" variant="soft" color={typeColor(m.member_type)}>{m.member_type}</Badge>
                  </td>
                  <td className="py-2">
                    <Link
                      to={entityLink(m.member_type, m.member_id)}
                      className="no-underline font-medium"
                      style={{ color: "var(--accent-11)" }}
                    >
                      {m.name || m.member_id}
                    </Link>
                  </td>
                  <td className="py-2" style={{ color: "var(--gray-11)" }}>{m.detail || "—"}</td>
                  <td className="py-2" style={{ color: "var(--gray-9)" }}>{formatDate(m.added_at)}</td>
                  <td className="py-2">
                    <button
                      onClick={() => removeMember(m.member_type, m.member_id)}
                      className="p-1 rounded hover:bg-red-50"
                    >
                      <Trash size={14} style={{ color: "var(--red-9)" }} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
