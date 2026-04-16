import { useState, useEffect } from "react";
import { useParams, Link } from "react-router-dom";
import { Heading, Text, Badge } from "@radix-ui/themes";
import { ArrowLeft } from "@phosphor-icons/react";
import { fetchApi } from "../api/client";
import type { DiscoveryClusterDetail, DiscoveryEvidence } from "../types";

// ── Signal type display mapping ────────────────────────────────

const SIGNAL_LABELS: Record<string, string> = {
  address: "Shared Addresses",
  contact: "Shared Contacts",
  phone: "Shared Phones",
  trade_name: "Trade Names",
  care_of: "Care-of Entities",
  entity: "Co-occurring Entities",
};

const SIGNAL_COLORS: Record<string, "blue" | "green" | "orange" | "purple" | "red" | "amber"> = {
  address: "blue",
  contact: "green",
  phone: "orange",
  trade_name: "purple",
  care_of: "amber",
  entity: "red",
};

function signalLabel(type: string): string {
  return SIGNAL_LABELS[type] ?? type;
}

function signalColor(type: string): "blue" | "green" | "orange" | "purple" | "red" | "amber" | "gray" {
  return SIGNAL_COLORS[type] ?? "gray";
}

function statusBadge(status: string) {
  if (status === "engaged") {
    return <Badge size="1" color="jade" variant="solid">{status}</Badge>;
  }
  return <Badge size="1" color="gray" variant="soft">{status}</Badge>;
}

function confidencePct(confidence: number): string {
  return `${Math.round(confidence * 100)}%`;
}

// ── Main page ──────────────────────────────────────────────────

export default function DiscoveryClusterPage() {
  const { clusterId } = useParams<{ clusterId: string }>();
  const [data, setData] = useState<DiscoveryClusterDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!clusterId) return;
    setLoading(true);
    setError(null);
    fetchApi<DiscoveryClusterDetail>(`/discovery/clusters/${clusterId}`)
      .then(setData)
      .catch(() => setError("Cluster not found."))
      .finally(() => setLoading(false));
  }, [clusterId]);

  if (loading) {
    return (
      <div className="flex flex-col gap-4">
        <Text size="2" style={{ color: "var(--gray-9)" }}>Loading...</Text>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="flex flex-col gap-4">
        <Link to="/discovery" className="inline-flex items-center gap-1.5 no-underline text-[13px]" style={{ color: "var(--accent-11)" }}>
          <ArrowLeft size={14} />
          Discovery
        </Link>
        <Text size="2" style={{ color: "var(--gray-9)" }}>{error ?? "Cluster not found."}</Text>
      </div>
    );
  }

  const anchor = data.anchor;
  const signalTypes = Object.keys(data.signal_summary);

  return (
    <div className="flex flex-col gap-5">
      {/* Back link */}
      <Link to="/discovery" className="inline-flex items-center gap-1.5 no-underline text-[13px]" style={{ color: "var(--accent-11)" }}>
        <ArrowLeft size={14} />
        Discovery
      </Link>

      {/* Page title */}
      <div>
        <Heading size="5" weight="medium">
          {anchor?.display_name ?? clusterId}
        </Heading>
        <Text size="2" style={{ color: "var(--gray-9)" }}>
          {data.member_count} member{data.member_count !== 1 ? "s" : ""} &middot; {data.evidence.length} evidence record{data.evidence.length !== 1 ? "s" : ""}
        </Text>
      </div>

      {/* Two-column layout: Signal Summary + Members */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">

        {/* Signal Summary card (left column) */}
        <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
          <Heading size="3" weight="medium" className="mb-4">Signal Summary</Heading>
          {signalTypes.length === 0 ? (
            <Text size="2" style={{ color: "var(--gray-9)" }}>No signals recorded.</Text>
          ) : (
            <div className="flex flex-col gap-4">
              {signalTypes.map((type) => (
                <div key={type}>
                  <Text size="1" weight="medium" className="block mb-1.5" style={{ color: "var(--gray-9)" }}>
                    {signalLabel(type)}
                  </Text>
                  <div className="flex flex-wrap gap-1.5">
                    {data.signal_summary[type].map((value, i) => (
                      <Badge key={i} size="1" color={signalColor(type)} variant="soft">
                        {value}
                      </Badge>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Member Groups table (right 2 columns) */}
        <div className="lg:col-span-2 rounded-[var(--card-radius)] border border-[var(--gray-6)] overflow-hidden">
          <div className="px-5 py-3.5 border-b border-[var(--gray-6)]" style={{ background: "var(--gray-2)" }}>
            <Heading size="3" weight="medium">Member Groups</Heading>
          </div>
          <table className="w-full text-[14px] [&_td]:whitespace-nowrap [&_th]:whitespace-nowrap">
            <thead>
              <tr style={{ background: "var(--gray-2)" }}>
                <th className="text-left px-4 py-2 text-[12px] font-medium border-b border-[var(--gray-6)]" style={{ color: "var(--gray-9)" }}>
                  Group
                </th>
                <th className="text-right px-4 py-2 text-[12px] font-medium border-b border-[var(--gray-6)]" style={{ color: "var(--gray-9)" }}>
                  Txns
                </th>
                <th className="text-right px-4 py-2 text-[12px] font-medium border-b border-[var(--gray-6)]" style={{ color: "var(--gray-9)" }}>
                  Props
                </th>
                <th className="text-left px-4 py-2 text-[12px] font-medium border-b border-[var(--gray-6)]" style={{ color: "var(--gray-9)" }}>
                  Status
                </th>
              </tr>
            </thead>
            <tbody>
              {data.members.map((member) => (
                <tr key={member.id} className="border-b border-[var(--gray-4)]">
                  <td className="px-4 py-2">
                    <Link
                      to={`/groups/${member.id}`}
                      className="no-underline font-medium"
                      style={{ color: "var(--accent-11)" }}
                      onClick={(e) => e.stopPropagation()}
                    >
                      {member.display_name}
                    </Link>
                    <div className="text-[11px] mt-0.5" style={{ color: "var(--gray-9)" }}>
                      {member.id}
                    </div>
                  </td>
                  <td className="px-4 py-2 text-right" style={{ color: "var(--gray-11)" }}>
                    {member.transaction_count.toLocaleString()}
                  </td>
                  <td className="px-4 py-2 text-right" style={{ color: "var(--gray-11)" }}>
                    {member.property_count.toLocaleString()}
                  </td>
                  <td className="px-4 py-2">
                    {statusBadge(member.status)}
                  </td>
                </tr>
              ))}
              {data.members.length === 0 && (
                <tr>
                  <td colSpan={4} className="px-4 py-8 text-center" style={{ color: "var(--gray-9)" }}>
                    No members in this cluster.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Evidence Chain (full width) */}
      <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] overflow-hidden">
        <div className="px-5 py-3.5 border-b border-[var(--gray-6)]" style={{ background: "var(--gray-2)" }}>
          <Heading size="3" weight="medium">Evidence Chain</Heading>
        </div>
        <table className="w-full text-[14px] [&_td]:whitespace-nowrap [&_th]:whitespace-nowrap">
          <thead>
            <tr style={{ background: "var(--gray-2)" }}>
              <th className="text-left px-4 py-2 text-[12px] font-medium border-b border-[var(--gray-6)]" style={{ color: "var(--gray-9)" }}>
                Signal
              </th>
              <th className="text-left px-4 py-2 text-[12px] font-medium border-b border-[var(--gray-6)]" style={{ color: "var(--gray-9)" }}>
                Value
              </th>
              <th className="text-left px-4 py-2 text-[12px] font-medium border-b border-[var(--gray-6)]" style={{ color: "var(--gray-9)" }}>
                Source Group
              </th>
              <th className="text-left px-4 py-2 text-[12px] font-medium border-b border-[var(--gray-6)]" style={{ color: "var(--gray-9)" }}>
                Rule
              </th>
              <th className="text-right px-4 py-2 text-[12px] font-medium border-b border-[var(--gray-6)]" style={{ color: "var(--gray-9)" }}>
                Confidence
              </th>
            </tr>
          </thead>
          <tbody>
            {data.evidence.map((ev: DiscoveryEvidence, i: number) => (
              <tr key={i} className="border-b border-[var(--gray-4)]">
                <td className="px-4 py-2">
                  <Badge size="1" color={signalColor(ev.signal_type)} variant="soft">
                    {signalLabel(ev.signal_type)}
                  </Badge>
                </td>
                <td className="px-4 py-2" style={{ color: "var(--gray-12)" }}>
                  {ev.signal_value}
                </td>
                <td className="px-4 py-2">
                  <Link
                    to={`/groups/${ev.source_group_id}`}
                    className="no-underline text-[13px]"
                    style={{ color: "var(--accent-11)" }}
                  >
                    {ev.source_group_id}
                  </Link>
                </td>
                <td className="px-4 py-2 text-[12px]" style={{ color: "var(--gray-9)" }}>
                  {ev.rule_id}
                </td>
                <td className="px-4 py-2 text-right" style={{ color: "var(--gray-11)" }}>
                  {confidencePct(ev.confidence)}
                </td>
              </tr>
            ))}
            {data.evidence.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center" style={{ color: "var(--gray-9)" }}>
                  No evidence records for this cluster.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
