import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Heading, Text, Badge } from "@radix-ui/themes";
import { Tag, CaretRight } from "@phosphor-icons/react";
import { fetchApi } from "../api/client";
import { formatDate } from "../lib/utils";
import type { LabelingAuditSummary, LabelingSession } from "../types";

export default function LabelingPage() {
  const [audits, setAudits] = useState<LabelingAuditSummary[]>([]);
  const [sessions, setSessions] = useState<LabelingSession[]>([]);

  useEffect(() => {
    fetchApi<{ audits: LabelingAuditSummary[] }>("/labeling/audits")
      .then((r) => setAudits(r.audits));
    fetchApi<{ sessions: LabelingSession[] }>("/labeling/sessions")
      .then((r) => setSessions(r.sessions));
  }, []);

  return (
    <div className="flex flex-col gap-6 p-6">
      <div className="flex items-center gap-2">
        <Tag size={20} weight="fill" style={{ color: "var(--accent-11)" }} />
        <Heading size="6">Portfolio Labeling</Heading>
      </div>
      <Text size="2" style={{ color: "var(--gray-11)" }}>
        Pick an audit to start labeling — each session captures field-level links between parties.
      </Text>

      <div>
        <Heading size="3" mb="2">Audits</Heading>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {audits.map((a) => (
            <Link
              key={a.slug}
              to={`/labeling/audits/${a.slug}`}
              className="no-underline rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5 hover:border-[var(--accent-8)]"
              style={{ color: "inherit" }}
            >
              <div className="flex items-start justify-between mb-2">
                <Heading size="3">{a.title}</Heading>
                <CaretRight size={16} style={{ color: "var(--gray-9)" }} />
              </div>
              <Text size="1" style={{ color: "var(--gray-9)" }}>
                {a.row_count} rows · {a.distinct_groups} groups · {a.distinct_parties} parties
              </Text>
              <div className="mt-2 flex flex-wrap gap-1">
                {a.sessions.map((s) => (
                  <Badge key={s.id} size="1" variant="soft" color={s.status === "done" ? "green" : "jade"}>
                    {s.name} · {s.status}
                  </Badge>
                ))}
                {a.sessions.length === 0 && (
                  <Badge size="1" variant="soft" color="gray">No sessions yet</Badge>
                )}
              </div>
            </Link>
          ))}
        </div>
      </div>

      <div>
        <Heading size="3" mb="2">Your sessions</Heading>
        {sessions.length === 0 && <Text size="2" style={{ color: "var(--gray-9)" }}>None yet.</Text>}
        <div className="flex flex-col gap-2">
          {sessions.map((s) => (
            <Link
              key={s.id}
              to={`/labeling/sessions/${s.id}`}
              className="no-underline rounded-[var(--card-radius)] border border-[var(--gray-6)] px-4 py-3 hover:border-[var(--accent-8)]"
              style={{ color: "inherit" }}
            >
              <div className="flex items-center justify-between">
                <div>
                  <Text size="3" weight="medium">{s.name}</Text>
                  <Text size="1" ml="2" style={{ color: "var(--gray-9)" }}>
                    {s.display_id} · {s.anchor_source_id}/{s.anchor_side}
                  </Text>
                </div>
                <div className="flex items-center gap-3">
                  <Badge size="1" variant="soft" color={s.status === "done" ? "green" : "jade"}>
                    {s.status}
                  </Badge>
                  <Text size="1" style={{ color: "var(--gray-9)" }}>
                    {s.confirmed_count}✓ / {s.rejected_count}✗
                  </Text>
                  <Text size="1" style={{ color: "var(--gray-9)" }}>
                    {formatDate(s.updated_at)}
                  </Text>
                </div>
              </div>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
