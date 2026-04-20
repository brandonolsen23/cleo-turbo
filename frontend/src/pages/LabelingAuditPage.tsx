import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Heading, Text, Badge, Button, TextField, Callout } from "@radix-ui/themes";
import { CaretLeft, Warning } from "@phosphor-icons/react";
import { fetchApi, postApi } from "../api/client";
import type { LabelingAuditParty, LabelingSession } from "../types";

interface AuditPartiesResponse {
  slug: string;
  title: string;
  parties: LabelingAuditParty[];
}

export default function LabelingAuditPage() {
  const { slug } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState<AuditPartiesResponse | null>(null);
  const [name, setName] = useState("");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchApi<AuditPartiesResponse>(`/labeling/audits/${slug}/parties`)
      .then((r) => { setData(r); setName(r.title); });
  }, [slug]);

  async function startSession(p: LabelingAuditParty) {
    setCreating(true);
    setError(null);
    try {
      const s = await postApi<LabelingSession>("/labeling/sessions", {
        anchor_source_id: p.source_id,
        anchor_side: p.side,
        name: name || data?.title || slug,
        audit_slug: slug,
      });
      navigate(`/labeling/sessions/${s.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setCreating(false);
    }
  }

  if (!data) return <div className="p-6"><Text>Loading…</Text></div>;

  return (
    <div className="flex flex-col gap-5 p-6">
      <Link to="/labeling" className="no-underline flex items-center gap-1"
            style={{ color: "var(--accent-11)" }}>
        <CaretLeft size={14} /> Labeling
      </Link>
      <Heading size="6">{data.title}</Heading>

      <div className="flex items-center gap-3">
        <Text size="2" style={{ color: "var(--gray-11)" }}>Session name:</Text>
        <TextField.Root size="2" value={name} onChange={(e) => setName(e.target.value)} />
      </div>

      {error && (
        <Callout.Root color="tomato" size="1">
          <Callout.Icon><Warning size={14} /></Callout.Icon>
          <Callout.Text>Failed to start session: {error}</Callout.Text>
        </Callout.Root>
      )}

      <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] overflow-hidden">
        <table className="w-full">
          <thead>
            <tr style={{ background: "var(--gray-2)" }}>
              {["RT ID", "Side", "Party", "Trade / Care-of", "Mailing", "Phone", ""].map((h) => (
                <th key={h} className="text-left px-3 py-2 text-[12px] font-medium"
                    style={{ color: "var(--gray-9)" }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.parties.map((p, i) => (
              <tr key={i} className="border-t border-[var(--gray-4)]">
                <td className="px-3 py-2 text-[13px]">{p.source_id}</td>
                <td className="px-3 py-2">
                  <Badge size="1" variant="soft" color={p.side === "buyer" ? "jade" : "amber"}>
                    {p.side}
                  </Badge>
                </td>
                <td className="px-3 py-2 text-[13px]">{p.party_name || "—"}</td>
                <td className="px-3 py-2 text-[13px]">{p.trade_name || p.care_of || "—"}</td>
                <td className="px-3 py-2 text-[13px]" style={{ color: "var(--gray-11)" }}>
                  {p.mailing || "—"}
                </td>
                <td className="px-3 py-2 text-[13px]" style={{ color: "var(--gray-11)" }}>
                  {p.phone || "—"}
                </td>
                <td className="px-3 py-2 whitespace-nowrap">
                  <Button size="1" variant="soft" disabled={creating}
                          onClick={() => startSession(p)}>
                    Start as anchor
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
