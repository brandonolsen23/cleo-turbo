import { useState, useEffect, useMemo } from "react";
import { useParams, Link } from "react-router-dom";
import { Heading, Text, Badge } from "@radix-ui/themes";
import { ArrowLeft, CaretDown, CaretRight } from "@phosphor-icons/react";
import { fetchApi } from "../api/client";
import { formatCurrency, formatDate } from "../lib/utils";
import type { DiscoveryClusterDetail, DiscoveryEvidence, DiscoveryMemberTransaction } from "../types";

// ── Signal type display mapping ────────────────────────────────

const SIGNAL_LABELS: Record<string, string> = {
  address: "Address",
  contact: "Contact",
  phone: "Phone",
  trade_name: "Trade Name",
  care_of: "Care-of",
  entity: "Entity",
  management_company: "Mgmt Co",
};

const SIGNAL_COLORS: Record<string, "blue" | "green" | "orange" | "purple" | "red" | "amber"> = {
  address: "blue",
  contact: "green",
  phone: "orange",
  trade_name: "purple",
  care_of: "amber",
  entity: "red",
  management_company: "purple",
};

const RULE_LABELS: Record<string, string> = {
  "4a": "Mgmt Co + Contact",
  "4b": "Contact + Address",
  "4c": "Mgmt Co + Address",
  "4d": "Mgmt Co + Phone",
  "4e": "Distinctive Contact",
  "4f": "Contact + Name",
  "4g": "Phone + Address/Name",
  multi: "Multiple Signals",
  exact_match: "Exact Match",
};

function signalColor(type: string): "blue" | "green" | "orange" | "purple" | "red" | "amber" | "gray" {
  return SIGNAL_COLORS[type] ?? "gray";
}

function confidencePct(confidence: number): string {
  return `${Math.round(confidence * 100)}%`;
}

// ── Per-member evidence summary ────────────────────────────────

interface MemberEvidence {
  member: DiscoveryClusterDetail["members"][0];
  rule: string;
  confidence: number;
  signals: { type: string; value: string }[];
  isAnchor: boolean;
}

function buildMemberEvidence(data: DiscoveryClusterDetail): MemberEvidence[] {
  const anchor = data.anchor;
  if (!anchor) return [];

  // Group evidence by source_group_id
  const evidenceByMember: Record<string, DiscoveryEvidence[]> = {};
  for (const ev of data.evidence) {
    const key = ev.source_group_id;
    if (!evidenceByMember[key]) evidenceByMember[key] = [];
    evidenceByMember[key].push(ev);
  }

  const result: MemberEvidence[] = [];

  for (const member of data.members) {
    const isAnchor = member.id === anchor.id;

    if (isAnchor) {
      result.push({
        member,
        rule: "anchor",
        confidence: 1.0,
        signals: [],
        isAnchor: true,
      });
      continue;
    }

    const evList = evidenceByMember[member.id] || [];
    // Deduplicate signals by type+value
    const seen = new Set<string>();
    const signals: { type: string; value: string }[] = [];
    let bestRule = "";
    let bestConf = 0;

    for (const ev of evList) {
      const key = `${ev.signal_type}|${ev.signal_value}`;
      if (!seen.has(key)) {
        seen.add(key);
        signals.push({ type: ev.signal_type, value: ev.signal_value });
      }
      if (ev.confidence > bestConf) {
        bestConf = ev.confidence;
        bestRule = ev.rule_id;
      }
    }

    result.push({
      member,
      rule: bestRule,
      confidence: bestConf,
      signals,
      isAnchor: false,
    });
  }

  // Sort: anchor first, then by confidence desc
  result.sort((a, b) => {
    if (a.isAnchor) return -1;
    if (b.isAnchor) return 1;
    return b.confidence - a.confidence;
  });

  return result;
}

// ── Expandable row ─────────────────────────────────────────────

function MemberRow({ item, transactions }: { item: MemberEvidence; transactions: DiscoveryMemberTransaction[] }) {
  const [expanded, setExpanded] = useState(false);
  const canExpand = !item.isAnchor || transactions.length > 0;

  return (
    <>
      <tr
        className="border-b border-[var(--gray-4)] cursor-pointer hover:bg-[var(--gray-2)] transition-colors"
        onClick={() => canExpand && setExpanded(!expanded)}
      >
        {/* Expand toggle */}
        <td className="pl-3 pr-1 py-2.5 w-6">
          {canExpand ? (
            expanded ? <CaretDown size={14} style={{ color: "var(--gray-9)" }} /> : <CaretRight size={14} style={{ color: "var(--gray-9)" }} />
          ) : null}
        </td>

        {/* Group name */}
        <td className="px-3 py-2.5">
          <Link
            to={`/groups/${item.member.id}`}
            className="no-underline font-medium"
            style={{ color: "var(--accent-11)" }}
            onClick={(e) => e.stopPropagation()}
          >
            {item.member.display_name}
          </Link>
          {item.isAnchor && (
            <Badge size="1" color="jade" variant="soft" className="ml-2">anchor</Badge>
          )}
        </td>

        {/* Why linked */}
        <td className="px-3 py-2.5">
          {item.isAnchor ? (
            <Text size="2" style={{ color: "var(--gray-9)" }}>—</Text>
          ) : (
            <div className="flex flex-wrap gap-1">
              {item.signals.slice(0, 4).map((s, i) => (
                <Badge key={i} size="1" color={signalColor(s.type)} variant="soft">
                  {SIGNAL_LABELS[s.type] || s.type}
                </Badge>
              ))}
              {item.signals.length > 4 && (
                <Badge size="1" color="gray" variant="soft">+{item.signals.length - 4}</Badge>
              )}
            </div>
          )}
        </td>

        {/* Rule */}
        <td className="px-3 py-2.5">
          {item.isAnchor ? null : (
            <Text size="2" style={{ color: "var(--gray-9)" }}>
              {RULE_LABELS[item.rule] || item.rule}
            </Text>
          )}
        </td>

        {/* Confidence */}
        <td className="px-3 py-2.5 text-right">
          {item.isAnchor ? null : (
            <Text size="2" style={{ color: "var(--gray-11)" }}>
              {confidencePct(item.confidence)}
            </Text>
          )}
        </td>

        {/* Txns */}
        <td className="px-3 py-2.5 text-right" style={{ color: "var(--gray-11)" }}>
          {item.member.transaction_count.toLocaleString()}
        </td>
      </tr>

      {/* Expanded detail: signals + source transactions */}
      {expanded && (
        <tr className="border-b border-[var(--gray-4)]">
          <td></td>
          <td colSpan={5} className="px-3 py-3" style={{ background: "var(--gray-2)" }}>
            <div className="flex flex-col gap-4">
              {/* Linking signals */}
              {item.signals.length > 0 && (
                <div>
                  <Text size="1" weight="medium" className="block mb-2" style={{ color: "var(--gray-9)" }}>
                    Linking Signals
                  </Text>
                  <div className="flex flex-col gap-1.5">
                    {item.signals.map((s, i) => (
                      <div key={i} className="flex items-center gap-2">
                        <Badge size="1" color={signalColor(s.type)} variant="soft" style={{ minWidth: 70, justifyContent: "center" }}>
                          {SIGNAL_LABELS[s.type] || s.type}
                        </Badge>
                        <Text size="2" style={{ color: "var(--gray-12)" }}>{s.value}</Text>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Source transactions */}
              {transactions.length > 0 && (
                <div>
                  <Text size="1" weight="medium" className="block mb-2" style={{ color: "var(--gray-9)" }}>
                    Transactions ({transactions.length})
                  </Text>
                  <div className="flex flex-col gap-1">
                    {transactions.map((txn) => (
                      <div key={txn.source_id} className="flex items-center gap-3 text-[13px]">
                        <Link
                          to={`/pipeline/trace/${txn.source_id}`}
                          className="no-underline font-mono"
                          style={{ color: "var(--accent-11)", minWidth: 80 }}
                          onClick={(e) => e.stopPropagation()}
                        >
                          {txn.source_id}
                        </Link>
                        <span style={{ color: "var(--gray-9)", minWidth: 50 }}>
                          {txn.side === "buyer" ? "Buy" : "Sell"}
                        </span>
                        <span style={{ color: "var(--gray-11)" }}>
                          {txn.display_address}{txn.city ? `, ${txn.city}` : ""}
                        </span>
                        <span style={{ color: "var(--gray-9)" }}>
                          {txn.sale_date ? formatDate(txn.sale_date) : ""}
                        </span>
                        {txn.sale_price ? (
                          <span style={{ color: "var(--gray-11)" }}>
                            {formatCurrency(txn.sale_price)}
                          </span>
                        ) : null}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  );
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

  const memberEvidence = useMemo(() => {
    if (!data) return [];
    return buildMemberEvidence(data);
  }, [data]);

  // Count signal types for summary
  const signalTypeCounts = useMemo(() => {
    if (!data) return {};
    const counts: Record<string, number> = {};
    for (const [type, values] of Object.entries(data.signal_summary)) {
      counts[type] = values.length;
    }
    return counts;
  }, [data]);

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

  return (
    <div className="flex flex-col gap-5">
      {/* Back link */}
      <Link to="/discovery" className="inline-flex items-center gap-1.5 no-underline text-[13px]" style={{ color: "var(--accent-11)" }}>
        <ArrowLeft size={14} />
        Discovery
      </Link>

      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <Heading size="5" weight="medium">
            {anchor?.display_name ?? clusterId}
          </Heading>
          <Text size="2" style={{ color: "var(--gray-9)" }}>
            {data.member_count} member group{data.member_count !== 1 ? "s" : ""}
          </Text>
        </div>

        {/* Signal summary as compact badges */}
        <div className="flex flex-wrap gap-2">
          {Object.entries(signalTypeCounts).map(([type, count]) => (
            <div key={type} className="flex items-center gap-1.5 rounded-full px-3 py-1 border border-[var(--gray-5)]" style={{ background: "var(--gray-2)" }}>
              <Badge size="1" color={signalColor(type)} variant="soft">
                {SIGNAL_LABELS[type] || type}
              </Badge>
              <Text size="1" style={{ color: "var(--gray-9)" }}>{count}</Text>
            </div>
          ))}
        </div>
      </div>

      {/* Members table — each row shows WHY that group is in the cluster */}
      <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] overflow-hidden">
        <table className="w-full text-[14px]">
          <thead>
            <tr style={{ background: "var(--gray-2)" }}>
              <th className="w-6 border-b border-[var(--gray-6)]"></th>
              <th className="text-left px-3 py-2.5 text-[12px] font-medium border-b border-[var(--gray-6)]" style={{ color: "var(--gray-9)" }}>
                Group
              </th>
              <th className="text-left px-3 py-2.5 text-[12px] font-medium border-b border-[var(--gray-6)]" style={{ color: "var(--gray-9)" }}>
                Linked By
              </th>
              <th className="text-left px-3 py-2.5 text-[12px] font-medium border-b border-[var(--gray-6)]" style={{ color: "var(--gray-9)" }}>
                Rule
              </th>
              <th className="text-right px-3 py-2.5 text-[12px] font-medium border-b border-[var(--gray-6)]" style={{ color: "var(--gray-9)" }}>
                Confidence
              </th>
              <th className="text-right px-3 py-2.5 text-[12px] font-medium border-b border-[var(--gray-6)]" style={{ color: "var(--gray-9)" }}>
                Txns
              </th>
            </tr>
          </thead>
          <tbody>
            {memberEvidence.map((item) => (
              <MemberRow
                key={item.member.id}
                item={item}
                transactions={data.member_transactions?.[item.member.id] || []}
              />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
