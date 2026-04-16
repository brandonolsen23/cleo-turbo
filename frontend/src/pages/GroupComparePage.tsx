import { useState, useEffect, useMemo } from "react";
import { Link, useSearchParams, useNavigate } from "react-router-dom";
import { Heading, Text, Badge, Button, Callout } from "@radix-ui/themes";
import {
  GitMerge, Phone, MapPin, User, ArrowRight, Buildings,
  CheckCircle, Warning, Info, CaretDown, CaretRight,
} from "@phosphor-icons/react";
import { fetchApi } from "../api/client";
import { formatCurrency, formatDate, formatPhone } from "../lib/utils";
import MergeGroupsModal from "../components/ui/MergeGroupsModal";
import LinkedInButton from "../components/ui/LinkedInButton";
import type {
  GroupCompareResponse, CompareGroupData, CompareGroupContact,
  CompareGroupMailingAddress, SharedAddress, SharedContact, SharedPhone,
} from "../types";

function formatYearRange(earliest: string | null, latest: string | null): string | null {
  if (!earliest && !latest) return null;
  const startYear = earliest ? earliest.substring(0, 4) : "?";
  const endYear = latest ? latest.substring(0, 4) : "?";
  if (startYear === endYear) return startYear;
  return `${startYear}\u2013${endYear}`;
}

// ── Tier styling ──

const TIER_CONFIG: Record<number, { label: string; color: "green" | "blue" | "amber" | "gray"; icon: typeof CheckCircle }> = {
  1: { label: "Near-certain", color: "green", icon: CheckCircle },
  2: { label: "Strong", color: "blue", icon: CheckCircle },
  3: { label: "Moderate", color: "amber", icon: Warning },
  4: { label: "Weak", color: "gray", icon: Info },
  0: { label: "No shared signals", color: "gray", icon: Info },
};

function TierBadge({ tier }: { tier: number }) {
  const cfg = TIER_CONFIG[tier] || TIER_CONFIG[0];
  return (
    <Badge size="2" color={cfg.color} variant="soft">
      <cfg.icon size={14} weight="bold" />
      Tier {tier}: {cfg.label}
    </Badge>
  );
}

// ── Group Evidence Card ──

function GroupEvidenceCard({
  group,
  sharedContactIds,
  sharedAddressSet,
  sharedPhoneSet,
  otherGroupId,
}: {
  group: CompareGroupData;
  sharedContactIds: Set<string>;
  sharedAddressSet: Set<string>;
  sharedPhoneSet: Set<string>;
  otherGroupId: string;
}) {
  const navigate = useNavigate();
  const [txnsExpanded, setTxnsExpanded] = useState(false);
  const [addrsExpanded, setAddrsExpanded] = useState(false);

  return (
    <div className="flex flex-col gap-4">
      {/* Group header */}
      <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-4">
        <div className="flex items-center justify-between mb-2">
          <Link
            to={`/groups/${group.id}`}
            className="no-underline hover:underline"
            style={{ color: "var(--accent-11)" }}
          >
            <Heading size="4">{group.display_name}</Heading>
          </Link>
          <Badge size="1" variant="soft" color={group.status === "engaged" ? "green" : "gray"}>
            {group.status}
          </Badge>
        </div>
        <div className="flex gap-4 mt-1">
          <Text size="2" style={{ color: "var(--gray-9)" }}>
            <Buildings size={14} className="inline mr-1" style={{ verticalAlign: "text-bottom" }} />
            {group.property_count} properties
          </Text>
          <Text size="2" style={{ color: "var(--gray-9)" }}>
            {group.transaction_count} transactions
          </Text>
          <Text size="2" style={{ color: "var(--gray-9)" }}>
            {group.contact_count} contacts
          </Text>
        </div>
        {group.hq_address && (
          <Text size="1" className="mt-1 block" style={{ color: "var(--gray-9)" }}>
            HQ: {group.hq_address}
          </Text>
        )}
      </div>

      {/* Contacts */}
      <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-4">
        <Text size="2" weight="medium" className="mb-2 block">
          <User size={14} className="inline mr-1" style={{ verticalAlign: "text-bottom" }} />
          Contacts ({group.contacts.length})
        </Text>
        {group.contacts.length === 0 ? (
          <Text size="2" style={{ color: "var(--gray-9)" }}>No contacts</Text>
        ) : (
          <table className="w-full text-[13px]">
            <thead>
              <tr className="border-b border-[var(--gray-4)]">
                <th className="text-left py-1.5 text-[11px] font-medium" style={{ color: "var(--gray-9)" }}>Name</th>
                <th className="text-left py-1.5 text-[11px] font-medium" style={{ color: "var(--gray-9)" }}>Phone</th>
                <th className="text-left py-1.5 text-[11px] font-medium" style={{ color: "var(--gray-9)" }}>Title</th>
                <th className="text-left py-1.5 text-[11px] font-medium" style={{ color: "var(--gray-9)" }}>Active</th>
                <th className="text-right py-1.5 text-[11px] font-medium" style={{ color: "var(--gray-9)" }}>Txns</th>
              </tr>
            </thead>
            <tbody>
              {group.contacts.map((c) => {
                const isShared = sharedContactIds.has(c.id);
                const phoneShared = c.phone ? sharedPhoneSet.has(c.phone) : false;
                return (
                  <tr
                    key={c.id}
                    className={`border-b border-[var(--gray-4)] hover:bg-[var(--gray-a2)] cursor-pointer ${
                      isShared ? "bg-[var(--jade-2)]" : ""
                    }`}
                    onClick={() => navigate(`/contacts/${c.id}`)}
                  >
                    <td className="py-1.5 font-medium">
                      <span className="inline-flex items-center gap-1 group">
                        {c.display_name}
                        <LinkedInButton
                          contactId={c.id}
                          contactName={c.display_name}
                          linkedinUrl={c.linkedin_url}
                          headline={c.linkedin_headline}
                          size="sm"
                        />
                      </span>
                      {isShared && (
                        <Badge size="1" color="jade" variant="soft" className="ml-1.5">shared</Badge>
                      )}
                    </td>
                    <td className="py-1.5">
                      {c.phone ? (
                        <span className={phoneShared ? "font-medium" : ""} style={phoneShared ? { color: "var(--amber-11)" } : { color: "var(--gray-11)" }}>
                          {formatPhone(c.phone)}
                          {phoneShared && <Badge size="1" color="amber" variant="soft" className="ml-1">shared</Badge>}
                        </span>
                      ) : (
                        <span style={{ color: "var(--gray-8)" }}>—</span>
                      )}
                    </td>
                    <td className="py-1.5" style={{ color: "var(--gray-11)" }}>{c.job_title || c.contact_type || "—"}</td>
                    <td className="py-1.5" style={{ color: "var(--gray-9)" }}>{formatYearRange(c.first_seen_date, c.last_seen_date) || "—"}</td>
                    <td className="py-1.5 text-right">{c.transaction_count}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {/* Mailing Addresses */}
      <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-4">
        <Text size="2" weight="medium" className="mb-2 block">
          <MapPin size={14} className="inline mr-1" style={{ verticalAlign: "text-bottom" }} />
          Mailing Addresses ({group.mailing_addresses.length})
        </Text>
        {group.mailing_addresses.length === 0 ? (
          <Text size="2" style={{ color: "var(--gray-9)" }}>No addresses</Text>
        ) : (
          <div className="flex flex-col gap-1">
            {(addrsExpanded ? group.mailing_addresses : group.mailing_addresses.slice(0, 8)).map((a, i) => {
              const isShared = sharedAddressSet.has(a.display);
              return (
                <div
                  key={i}
                  className={`flex items-center justify-between py-1.5 px-2 rounded text-[13px] ${
                    isShared ? "bg-[var(--jade-2)] border border-[var(--jade-6)]" : ""
                  }`}
                >
                  <div className="flex items-center gap-2">
                    <span>{a.display}</span>
                    {a.city && <span style={{ color: "var(--gray-9)" }}>{a.city}</span>}
                    {isShared && <Badge size="1" color="jade" variant="soft">shared</Badge>}
                  </div>
                  <Text size="1" style={{ color: "var(--gray-9)" }}>{a.usage_count} txn{a.usage_count !== 1 ? "s" : ""}</Text>
                </div>
              );
            })}
            {group.mailing_addresses.length > 8 && (
              <button
                onClick={() => setAddrsExpanded(!addrsExpanded)}
                className="mt-1 flex items-center gap-1 text-[12px] font-medium hover:underline"
                style={{ color: "var(--accent-11)" }}
              >
                <CaretDown size={10} style={{ transform: addrsExpanded ? "rotate(180deg)" : undefined, transition: "transform 0.15s" }} />
                {addrsExpanded ? "Show less" : `Show all ${group.mailing_addresses.length}`}
              </button>
            )}
          </div>
        )}
      </div>

      {/* Recent Transactions */}
      <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-4">
        <Text size="2" weight="medium" className="mb-2 block">
          Recent Transactions ({group.recent_transactions.length})
        </Text>
        {group.recent_transactions.length === 0 ? (
          <Text size="2" style={{ color: "var(--gray-9)" }}>No transactions</Text>
        ) : (
          <>
            <table className="w-full text-[13px]">
              <thead>
                <tr className="border-b border-[var(--gray-4)]">
                  <th className="text-left py-1.5 text-[11px] font-medium" style={{ color: "var(--gray-9)" }}>Date</th>
                  <th className="text-left py-1.5 text-[11px] font-medium" style={{ color: "var(--gray-9)" }}>Property</th>
                  <th className="text-left py-1.5 text-[11px] font-medium" style={{ color: "var(--gray-9)" }}>Side</th>
                  <th className="text-right py-1.5 text-[11px] font-medium" style={{ color: "var(--gray-9)" }}>Price</th>
                </tr>
              </thead>
              <tbody>
                {(txnsExpanded ? group.recent_transactions : group.recent_transactions.slice(0, 8)).map((t, i) => (
                  <tr
                    key={`${t.source_id}-${i}`}
                    className="border-b border-[var(--gray-4)] hover:bg-[var(--gray-a2)] cursor-pointer"
                    onClick={() => navigate(`/transactions/${t.source_id}`)}
                  >
                    <td className="py-1.5">{formatDate(t.sale_date)}</td>
                    <td className="py-1.5 truncate" style={{ maxWidth: 200 }}>
                      {t.display_address}, {t.city}
                    </td>
                    <td className="py-1.5">
                      <Badge size="1" variant="soft" color={t.side === "buyer" ? "blue" : "orange"}>
                        {t.side}
                      </Badge>
                    </td>
                    <td className="py-1.5 text-right">{formatCurrency(t.sale_price)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {group.recent_transactions.length > 8 && (
              <button
                onClick={() => setTxnsExpanded(!txnsExpanded)}
                className="mt-1 flex items-center gap-1 text-[12px] font-medium hover:underline"
                style={{ color: "var(--accent-11)" }}
              >
                <CaretDown size={10} style={{ transform: txnsExpanded ? "rotate(180deg)" : undefined, transition: "transform 0.15s" }} />
                {txnsExpanded ? "Show less" : `Show all ${group.recent_transactions.length}`}
              </button>
            )}
          </>
        )}
      </div>

      {/* Known Names */}
      {group.known_names.length > 1 && (
        <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-4">
          <Text size="2" weight="medium" className="mb-2 block">
            Known Names ({group.known_names.length})
          </Text>
          <div className="flex flex-wrap gap-1.5">
            {group.known_names.map((n, i) => (
              <Badge key={i} size="1" variant="soft">{n.name}</Badge>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Shared Evidence Panel ──

function SharedEvidencePanel({
  sharedAddresses,
  sharedContacts,
  sharedPhones,
  groups,
}: {
  sharedAddresses: SharedAddress[];
  sharedContacts: SharedContact[];
  sharedPhones: SharedPhone[];
  groups: Record<string, CompareGroupData>;
}) {
  const hasEvidence = sharedAddresses.length > 0 || sharedContacts.length > 0 || sharedPhones.length > 0;

  if (!hasEvidence) return null;

  return (
    <div className="rounded-[var(--card-radius)] border-2 border-[var(--jade-7)] bg-[var(--jade-1)] p-5">
      <Heading size="3" className="mb-3" style={{ color: "var(--jade-11)" }}>
        Shared Evidence
      </Heading>

      {sharedAddresses.length > 0 && (
        <div className="mb-4">
          <Text size="2" weight="medium" className="mb-2 block">
            <MapPin size={14} className="inline mr-1" weight="bold" style={{ verticalAlign: "text-bottom", color: "var(--jade-9)" }} />
            Shared Addresses ({sharedAddresses.length})
          </Text>
          <div className="flex flex-col gap-1.5">
            {sharedAddresses.slice(0, 10).map((a, i) => (
              <div key={i} className="flex items-center justify-between bg-white rounded px-3 py-2 border border-[var(--jade-5)]">
                <div>
                  <Text size="2" weight="medium">{a.display}</Text>
                  {a.city && <Text size="1" style={{ color: "var(--gray-9)" }}> — {a.city}</Text>}
                </div>
                <div className="flex items-center gap-2">
                  <Badge size="1" variant="outline">{a.group_count} groups</Badge>
                  <Text size="1" style={{ color: "var(--gray-9)" }}>{a.total_txns} txns</Text>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {sharedContacts.length > 0 && (
        <div className="mb-4">
          <Text size="2" weight="medium" className="mb-2 block">
            <User size={14} className="inline mr-1" weight="bold" style={{ verticalAlign: "text-bottom", color: "var(--jade-9)" }} />
            Shared Contacts ({sharedContacts.length})
          </Text>
          <div className="flex flex-col gap-1.5">
            {sharedContacts.slice(0, 10).map((c, i) => (
              <div key={i} className="flex items-center justify-between bg-white rounded px-3 py-2 border border-[var(--jade-5)]">
                <div className="flex items-center gap-2">
                  <span className="inline-flex items-center gap-1 group">
                    <Text size="2" weight="medium">{c.display_name}</Text>
                    <LinkedInButton
                      contactId={c.id}
                      contactName={c.display_name}
                      linkedinUrl={c.linkedin_url}
                      size="sm"
                    />
                  </span>
                  {c.job_title && <Text size="1" style={{ color: "var(--gray-9)" }}>({c.job_title})</Text>}
                  {c.phone && (
                    <Text size="1" style={{ color: "var(--gray-10)" }}>
                      <Phone size={12} className="inline mr-0.5" style={{ verticalAlign: "text-bottom" }} />
                      {formatPhone(c.phone)}
                    </Text>
                  )}
                  {(() => {
                    const yr = formatYearRange(c.earliest_date, c.latest_date);
                    return yr ? <Text size="1" style={{ color: "var(--gray-8)" }}>{yr}</Text> : null;
                  })()}
                </div>
                <Badge size="1" variant="outline">{c.group_count} groups</Badge>
              </div>
            ))}
          </div>
        </div>
      )}

      {sharedPhones.length > 0 && (
        <div>
          <Text size="2" weight="medium" className="mb-2 block">
            <Phone size={14} className="inline mr-1" weight="bold" style={{ verticalAlign: "text-bottom", color: "var(--jade-9)" }} />
            Shared Phone Numbers ({sharedPhones.length})
          </Text>
          <div className="flex flex-col gap-1.5">
            {sharedPhones.slice(0, 10).map((p, i) => (
              <div key={i} className="flex items-center justify-between bg-white rounded px-3 py-2 border border-[var(--jade-5)]">
                <div className="flex items-center gap-2">
                  <Text size="2" weight="medium">{formatPhone(p.phone)}</Text>
                  <Text size="1" style={{ color: "var(--gray-9)" }}>
                    ({p.contacts.map((c) => c.display_name).join(", ")})
                  </Text>
                </div>
                <Badge size="1" variant="outline">{p.group_count} groups</Badge>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Main Page ──

export default function GroupComparePage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [data, setData] = useState<GroupCompareResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showMergeModal, setShowMergeModal] = useState(false);

  const groupIds = searchParams.get("ids") || "";

  useEffect(() => {
    if (!groupIds) {
      setError("No group IDs provided");
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    fetchApi<GroupCompareResponse>("/group-merges/compare", { group_ids: groupIds })
      .then(setData)
      .catch((e) => setError(e.message || "Failed to load comparison"))
      .finally(() => setLoading(false));
  }, [groupIds]);

  // Pre-compute shared sets for highlighting
  const sharedContactIds = useMemo(() => {
    if (!data) return new Set<string>();
    return new Set(data.shared_contacts.map((c) => c.id));
  }, [data]);

  const sharedAddressSet = useMemo(() => {
    if (!data) return new Set<string>();
    return new Set(data.shared_addresses.map((a) => a.display));
  }, [data]);

  const sharedPhoneSet = useMemo(() => {
    if (!data) return new Set<string>();
    const phones = new Set<string>();
    data.shared_phones.forEach((p) => phones.add(p.phone));
    return phones;
  }, [data]);

  if (loading) return <div className="p-6"><Text>Loading comparison...</Text></div>;
  if (error) return <div className="p-6"><Callout.Root color="red"><Callout.Text>{error}</Callout.Text></Callout.Root></div>;
  if (!data) return null;

  const groupEntries = Object.entries(data.groups);
  const ids = groupIds.split(",");
  const tierCfg = TIER_CONFIG[data.match_tier] || TIER_CONFIG[0];

  // For merge modal: pick the group with most properties as default target
  const sortedByProps = [...groupEntries].sort((a, b) => b[1].property_count - a[1].property_count);
  const defaultTarget = sortedByProps[0]?.[1];

  return (
    <div className="flex flex-col gap-5">
      {/* Back link */}
      <div>
        <Link
          to={`/groups/${ids[0]}`}
          className="text-[14px] no-underline"
          style={{ color: "var(--accent-11)" }}
        >
          &larr; Back to {data.groups[ids[0]]?.display_name || "Group"}
        </Link>
      </div>

      {/* Match Summary Bar */}
      <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] bg-[var(--gray-1)] p-5">
        <div className="flex items-start justify-between">
          <div>
            <div className="flex items-center gap-3 mb-2">
              <Heading size="5">Group Comparison</Heading>
              <TierBadge tier={data.match_tier} />
            </div>
            {data.match_reasons.length > 0 ? (
              <div className="flex flex-col gap-1">
                {data.match_reasons.map((reason, i) => (
                  <Text key={i} size="2" style={{ color: "var(--gray-11)" }}>
                    {reason}
                  </Text>
                ))}
              </div>
            ) : (
              <Text size="2" style={{ color: "var(--gray-9)" }}>
                No shared signals detected between these groups.
              </Text>
            )}
          </div>
          <div className="flex items-center gap-2">
            {data.match_tier > 0 && (
              <Button
                size="2"
                color="jade"
                onClick={() => setShowMergeModal(true)}
              >
                <GitMerge size={16} />
                Merge These Groups
              </Button>
            )}
          </div>
        </div>
      </div>

      {/* Shared Evidence */}
      <SharedEvidencePanel
        sharedAddresses={data.shared_addresses}
        sharedContacts={data.shared_contacts}
        sharedPhones={data.shared_phones}
        groups={data.groups}
      />

      {/* Side-by-side Group Cards */}
      <div className={`grid gap-5 ${groupEntries.length === 2 ? "grid-cols-2" : "grid-cols-1 lg:grid-cols-2"}`}>
        {groupEntries.map(([gid, group]) => {
          const otherGid = groupEntries.find(([id]) => id !== gid)?.[0] || gid;
          return (
            <GroupEvidenceCard
              key={gid}
              group={group}
              sharedContactIds={sharedContactIds}
              sharedAddressSet={sharedAddressSet}
              sharedPhoneSet={sharedPhoneSet}
              otherGroupId={otherGid}
            />
          );
        })}
      </div>

      {/* Merge Modal */}
      {showMergeModal && defaultTarget && (
        <MergeGroupsModal
          targetGroup={{
            id: defaultTarget.id,
            display_name: defaultTarget.display_name,
            property_count: defaultTarget.property_count,
            transaction_count: defaultTarget.transaction_count,
            contact_count: defaultTarget.contact_count,
          }}
          initialSourceIds={groupEntries.filter(([gid]) => gid !== defaultTarget.id).map(([gid]) => gid)}
          onClose={() => setShowMergeModal(false)}
          onMerged={(survivorId) => {
            setShowMergeModal(false);
            navigate(`/groups/${survivorId}`);
          }}
        />
      )}
    </div>
  );
}
