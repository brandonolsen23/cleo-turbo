import { useEffect, useState, useCallback } from "react";
import { Link, useParams, useNavigate } from "react-router-dom";
import { Heading, Text, Button, Badge, Tabs, Callout } from "@radix-ui/themes";
import { MapPin, Buildings, ArrowSquareOut } from "@phosphor-icons/react";
import { fetchApi, postApi } from "../api/client";
import {
  formatCompact,
  formatDate,
  formatPhone,
  titleCase,
} from "../lib/utils";
import { propertyTypeLabel, propertyTypeColor } from "../lib/theme";
import HqPicker from "../components/group/HqPicker";
import { Reportable, useIssueReporter } from "../components/issues/IssueReporter";
import { Info } from "@phosphor-icons/react";
import AttributionStrip from "../components/crm/AttributionStrip";
import ActivityFeed from "../components/crm/ActivityFeed";
import QuickActionBar from "../components/crm/QuickActionBar";
import type { GroupDetail, GroupPropertyRow, BrowseResponse } from "../types";

const TIER_COLOR: Record<string, "jade" | "gray" | "amber" | "blue"> = {
  confirmed: "jade",
  probable: "blue",
  candidate: "amber",
  standalone: "gray",
};

function tierLabel(t: string): string {
  return t.charAt(0).toUpperCase() + t.slice(1);
}

function StatCard({ label, value, sub, statKey }: { label: string; value: string | number | null; sub?: string; statKey?: string }) {
  const card = (
    <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-4">
      <Text size="1" style={{ color: "var(--gray-9)" }}>{label}</Text>
      <Text size="6" weight="bold" className="block mt-1" style={{ color: "var(--gray-12)" }}>
        {value ?? "—"}
      </Text>
      {sub && (
        <Text size="1" style={{ color: "var(--gray-9)" }}>{sub}</Text>
      )}
    </div>
  );
  if (!statKey) return card;
  return (
    <Reportable component={`stats.${statKey}`} data={{ value, sub }}>
      {card}
    </Reportable>
  );
}

// ── Contacts tab with engage/unengage toggle ─────────────────────────

interface GroupContactRow {
  id: string;
  display_name: string;
  phone: string | null;
  email: string | null;
  job_title: string | null;
  status: string;
  transaction_count: number;
  contact_type: string | null;
  first_seen_date: string | null;
  last_seen_date: string | null;
  link_type: "derived" | "manual" | "both";
}

function ContactsTab({ groupId, onEngagementChange }: {
  groupId: string;
  onEngagementChange: () => void;
}) {
  const [contacts, setContacts] = useState<GroupContactRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);

  const reload = useCallback(() => {
    setLoading(true);
    fetchApi<{ contacts: GroupContactRow[] }>(`/groups/${groupId}/contacts`)
      .then((r) => setContacts(r.contacts))
      .finally(() => setLoading(false));
  }, [groupId]);

  useEffect(() => { reload(); }, [reload]);

  const toggleEngagement = async (contactId: string, current: string) => {
    setBusyId(contactId);
    try {
      const path = current === "engaged"
        ? `/contacts/${contactId}/unengage`
        : `/contacts/${contactId}/engage`;
      await postApi(path, {});
      reload();
      onEngagementChange();
    } finally {
      setBusyId(null);
    }
  };

  if (loading) return <Text size="2" style={{ color: "var(--gray-9)" }}>Loading…</Text>;
  if (contacts.length === 0) {
    return <Text size="2" style={{ color: "var(--gray-9)" }}>No contacts.</Text>;
  }

  return (
    <Reportable component="contacts_tab.table" data={{ count: contacts.length }}>
    <table className="w-full text-[14px]">
      <thead>
        <tr style={{ background: "var(--gray-2)" }}>
          <th className="text-left px-3 py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Name</th>
          <th className="text-left px-3 py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Title</th>
          <th className="text-left px-3 py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Phone</th>
          <th className="text-right px-3 py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Txns</th>
          <th className="text-left px-3 py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Status</th>
          <th className="text-right px-3 py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}></th>
        </tr>
      </thead>
      <tbody>
        {contacts.map((c) => (
          <tr key={c.id} className="border-b border-[var(--gray-4)] hover:bg-[var(--gray-a2)]">
            <td className="px-3 py-2">
              <Link to={`/contacts/${c.id}`} className="no-underline" style={{ color: "var(--accent-11)" }}>
                {c.display_name}
              </Link>
            </td>
            <td className="px-3 py-2" style={{ color: "var(--gray-11)" }}>{c.job_title || "—"}</td>
            <td className="px-3 py-2" style={{ color: "var(--gray-11)" }}>{c.phone ? formatPhone(c.phone) : "—"}</td>
            <td className="px-3 py-2 text-right">{c.transaction_count}</td>
            <td className="px-3 py-2">
              <Badge size="1" color={c.status === "engaged" ? "jade" : "gray"} variant={c.status === "engaged" ? "solid" : "soft"}>
                {c.status}
              </Badge>
            </td>
            <td className="px-3 py-2 text-right">
              <Button
                size="1"
                variant="soft"
                color={c.status === "engaged" ? "gray" : "jade"}
                disabled={busyId === c.id}
                onClick={() => toggleEngagement(c.id, c.status)}
              >
                {c.status === "engaged" ? "Unengage" : "Engage"}
              </Button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
    </Reportable>
  );
}

// ── Properties tab (unified — resolved + unresolved, with Owned/Sold filter) ──

type PropFilter = "all" | "owned" | "sold";

/** Hover-revealed `i` button rendered inside a table cell. Uses the
 *  IssueReporter context directly so it can be embedded inline in a row
 *  without invalidating the table's `<tr>/<td>` structure. */
function RowReportButton({ component, data, label }: {
  component: string; data: Record<string, unknown>; label?: string;
}) {
  const { open } = useIssueReporter();
  return (
    <button
      type="button"
      onClick={(e) => { e.stopPropagation(); open({ component, component_data: data, contextLabel: label }); }}
      className="opacity-0 group-hover/row:opacity-100 transition-opacity rounded p-1 hover:bg-[var(--gray-3)]"
      title="Report issue with this row"
      style={{ color: "var(--gray-9)" }}
    >
      <Info size={13} weight="bold" />
    </button>
  );
}


function PropertiesTab({ groupId }: { groupId: string }) {
  const [data, setData] = useState<BrowseResponse<GroupPropertyRow> | null>(null);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [filter, setFilter] = useState<PropFilter>("all");

  useEffect(() => {
    setLoading(true);
    fetchApi<BrowseResponse<GroupPropertyRow>>(`/groups/${groupId}/properties`, {
      page: String(page),
      per_page: "50",
      filter,
    })
      .then(setData)
      .finally(() => setLoading(false));
  }, [groupId, page, filter]);

  const setFilterAndReset = (f: PropFilter) => {
    setFilter(f);
    setPage(1);
  };

  if (loading && !data) return <Text size="2" style={{ color: "var(--gray-9)" }}>Loading…</Text>;

  return (
    <div className="flex flex-col gap-3" style={{ opacity: loading ? 0.6 : 1 }}>
      {/* Filter chip + result count */}
      <div className="flex items-center justify-between">
        <div className="inline-flex rounded-md border border-[var(--gray-6)] overflow-hidden">
          {(["all", "owned", "sold"] as PropFilter[]).map((f) => (
            <button
              key={f}
              onClick={() => setFilterAndReset(f)}
              className={`px-3 py-1 text-[13px] transition-colors ${
                filter === f
                  ? "bg-[var(--accent-3)] text-[var(--accent-11)] font-medium"
                  : "bg-white hover:bg-[var(--gray-2)]"
              }`}
              style={{ color: filter === f ? "var(--accent-11)" : "var(--gray-11)" }}
            >
              {f === "all" ? "All" : f === "owned" ? "Owned" : "Sold"}
            </button>
          ))}
        </div>
        <Text size="1" style={{ color: "var(--gray-9)" }}>
          {(data?.total || 0).toLocaleString()} properties
        </Text>
      </div>

      {!data || data.results.length === 0 ? (
        <Text size="2" style={{ color: "var(--gray-9)" }}>
          {filter === "owned"
            ? "No properties currently owned."
            : filter === "sold"
              ? "No properties sold."
              : "No properties."}
        </Text>
      ) : (
        <>
          <Reportable component="properties_tab.table" data={{ filter, total: data.total }}>
          <table className="w-full text-[14px]">
            <thead>
              <tr style={{ background: "var(--gray-2)" }}>
                <th className="text-left px-3 py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Address</th>
                <th className="text-left px-3 py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>City</th>
                <th className="text-left px-3 py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Type</th>
                <th className="text-left px-3 py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Side</th>
                <th className="text-right px-3 py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Last Date</th>
                <th className="text-right px-3 py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Last Price</th>
                <th className="text-right px-3 py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Txns</th>
                <th style={{ width: 24 }}></th>
              </tr>
            </thead>
            <tbody>
              {data.results.map((p) => {
                const key = p.property_id || p.canonical_address || p.display_address || "";
                const addrText = titleCase(p.display_address || "") || p.display_address || "—";
                return (
                  <tr key={key} className="group/row border-b border-[var(--gray-4)] hover:bg-[var(--gray-a2)]">
                    <td className="px-3 py-2">
                      {p.resolved && p.property_id ? (
                        <Link to={`/properties/${p.property_id}`} className="no-underline" style={{ color: "var(--accent-11)" }}>
                          {addrText}
                        </Link>
                      ) : (
                        <span style={{ color: "var(--gray-12)" }}>{addrText}</span>
                      )}
                    </td>
                    <td className="px-3 py-2" style={{ color: "var(--gray-11)" }}>{p.city || "—"}</td>
                    <td className="px-3 py-2">
                      {p.asset_class ? (
                        <Badge size="1" color={propertyTypeColor(p.asset_class)} variant="soft">
                          {propertyTypeLabel(p.asset_class)}
                        </Badge>
                      ) : <Text size="1" style={{ color: "var(--gray-8)" }}>—</Text>}
                    </td>
                    <td className="px-3 py-2">
                      <Badge size="1" color={p.is_owned ? "jade" : "gray"} variant="soft">
                        {p.is_owned ? "Owned" : "Sold"}
                      </Badge>
                    </td>
                    <td className="px-3 py-2 text-right" style={{ color: "var(--gray-11)" }}>
                      {p.last_date ? formatDate(p.last_date) : "—"}
                    </td>
                    <td className="px-3 py-2 text-right" style={{ color: "var(--gray-11)" }}>
                      {p.last_price ? formatCompact(p.last_price) : "—"}
                    </td>
                    <td className="px-3 py-2 text-right" style={{ color: "var(--gray-11)" }}>
                      {p.n_transactions}
                    </td>
                    <td className="px-1 py-2 text-right">
                      <RowReportButton
                        component="properties_tab.row"
                        data={{
                          property_id: p.property_id,
                          canonical_address: p.canonical_address,
                          display_address: p.display_address,
                          city: p.city,
                          asset_class: p.asset_class,
                          last_side: p.last_side,
                          last_date: p.last_date,
                          last_price: p.last_price,
                          is_owned: p.is_owned,
                          resolved: p.resolved,
                        }}
                        label={`Property row: ${addrText}`}
                      />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          </Reportable>
          {data.pages > 1 && (
            <div className="flex items-center justify-between mt-2">
              <Text size="1" style={{ color: "var(--gray-9)" }}>Page {data.page} of {data.pages}</Text>
              <div className="flex gap-2">
                <Button size="1" variant="soft" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</Button>
                <Button size="1" variant="soft" disabled={page >= data.pages} onClick={() => setPage(page + 1)}>Next</Button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ── Constituent SPVs tab ─────────────────────────────────────────────

function SpvsTab({ group }: { group: GroupDetail }) {
  if (group.constituent_legacy_groups.length === 0) {
    return <Text size="2" style={{ color: "var(--gray-9)" }}>No constituent SPVs.</Text>;
  }

  return (
    <div className="flex flex-col gap-2">
      <Text size="1" style={{ color: "var(--gray-9)" }}>
        {group.constituent_legacy_groups.length.toLocaleString()} legacy SPVs rolled up into this group.
      </Text>
      <Reportable component="spvs_tab.table" data={{ count: group.constituent_legacy_groups.length }}>
      <table className="w-full text-[14px]">
        <thead>
          <tr style={{ background: "var(--gray-2)" }}>
            <th className="text-left px-3 py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>SPV</th>
            <th className="text-right px-3 py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Properties</th>
            <th className="text-right px-3 py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Transactions</th>
            <th className="text-left px-3 py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Coverage</th>
          </tr>
        </thead>
        <tbody>
          {group.constituent_legacy_groups.map((s) => (
            <tr key={s.id} className="border-b border-[var(--gray-4)] hover:bg-[var(--gray-a2)]">
              <td className="px-3 py-2">
                <Text size="2">{titleCase(s.display_name)}</Text>
                <Text size="1" className="block" style={{ color: "var(--gray-9)" }}>{s.id}</Text>
              </td>
              <td className="px-3 py-2 text-right">{s.property_count.toLocaleString()}</td>
              <td className="px-3 py-2 text-right">{s.transaction_count.toLocaleString()}</td>
              <td className="px-3 py-2">
                <Badge size="1" variant="soft" color={s.coverage_pct >= 0.8 ? "jade" : s.coverage_pct >= 0.5 ? "amber" : "gray"}>
                  {Math.round(s.coverage_pct * 100)}%
                </Badge>
                <Text size="1" className="ml-2" style={{ color: "var(--gray-9)" }}>{s.source}</Text>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      </Reportable>
    </div>
  );
}

// ── Main page ────────────────────────────────────────────────────────

export default function GroupDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [group, setGroup] = useState<GroupDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshTick, setRefreshTick] = useState(0);

  useEffect(() => {
    if (!id) return;
    setError(null);
    fetchApi<GroupDetail>(`/groups/${id}`)
      .then((g) => {
        setGroup(g);
        if (id !== g.id) {
          navigate(`/groups/${g.id}`, { replace: true });
        }
      })
      .catch((e) => setError(e?.message || "Failed to load group"));
  }, [id, refreshTick, navigate]);

  if (error) {
    return (
      <Callout.Root color="red">
        <Callout.Text>Group not found.</Callout.Text>
      </Callout.Root>
    );
  }
  if (!group) {
    return <Text size="2" style={{ color: "var(--gray-9)" }}>Loading…</Text>;
  }

  const a = group.analytics;
  const totalTxns = (a?.total_buys ?? 0) + (a?.total_sells ?? 0);

  const sortedMix = ((): [string, number][] => {
    const mix = a?.transacted_type_mix || a?.property_type_mix || {};
    return (Object.entries(mix) as [string, number][])
      .filter(([k]) => k !== "unknown")
      .sort((x, y) => y[1] - x[1]);
  })();
  const dominant = sortedMix[0]?.[0] ?? null;
  const secondary = sortedMix[1]?.[0] ?? null;

  return (
    <div className="flex flex-col gap-6">
      {/* Back link */}
      <Link to="/groups" className="text-[14px] no-underline" style={{ color: "var(--accent-11)" }}>
        ← Groups
      </Link>

      {/* Header */}
      <div className="flex flex-col gap-3">
        <div className="flex items-start justify-between gap-4">
          <div className="flex-1">
            <Heading size="6" weight="medium">{titleCase(group.display_name)}</Heading>
            <div className="flex items-center gap-2 mt-2 flex-wrap">
              <Badge size="2" color={TIER_COLOR[group.tier] || "gray"} variant="soft">
                {tierLabel(group.tier)}
              </Badge>
              <Text size="2" style={{ color: "var(--gray-9)" }}>
                {group.n_members.toLocaleString()} members
              </Text>
              <Text size="2" style={{ color: "var(--gray-9)" }}>·</Text>
              <Text size="2" style={{ color: "var(--gray-9)" }}>
                {group.constituent_legacy_groups.length.toLocaleString()} SPVs
              </Text>
              {dominant && (
                <>
                  <Text size="2" style={{ color: "var(--gray-9)" }}>·</Text>
                  <Badge size="1" color={propertyTypeColor(dominant)} variant="soft">
                    {propertyTypeLabel(dominant)}
                  </Badge>
                  {secondary && (
                    <Badge size="1" color={propertyTypeColor(secondary)} variant="soft">
                      {propertyTypeLabel(secondary)}
                    </Badge>
                  )}
                </>
              )}
            </div>
          </div>
          <QuickActionBar
            entityType="group"
            entityId={group.id}
            entityName={titleCase(group.display_name)}
          />
        </div>
        <AttributionStrip entityType="group" entityId={group.id} />
      </div>

      {/* Stats — unified Property model */}
      {(() => {
        const propsTotal = a?.properties_total ?? a?.transacted_property_count ?? 0;
        const propsOwned = a?.properties_owned ?? a?.property_count ?? 0;
        const propsResolved = a?.transacted_property_count ?? 0;
        const propsUnresolved = Math.max(0, propsTotal - propsResolved);
        return (
          <div className="grid grid-cols-6 gap-4">
            <StatCard
              statKey="properties_count"
              label="Properties"
              value={propsTotal.toLocaleString()}
              sub={
                propsTotal > 0
                  ? `${propsResolved.toLocaleString()} parcel-matched · ${propsUnresolved.toLocaleString()} by address`
                  : undefined
              }
            />
            <StatCard
              statKey="properties_owned"
              label="Owned"
              value={propsTotal > 0 ? `${propsOwned.toLocaleString()} of ${propsTotal.toLocaleString()}` : "—"}
              sub={`${group.engaged_contact_count} of ${group.total_contact_count} contacts engaged`}
            />
            <StatCard
              statKey="transactions"
              label="Transactions"
              value={totalTxns.toLocaleString()}
              sub={a?.total_buys != null && a?.total_sells != null
                ? `${a.total_buys.toLocaleString()} buys · ${a.total_sells.toLocaleString()} sells`
                : undefined}
            />
            <StatCard
              statKey="buy_value"
              label="Buy Value"
              value={a?.total_buy_value ? formatCompact(a.total_buy_value) : "—"}
              sub={a?.n_buys_priced ? `${a.n_buys_priced.toLocaleString()} priced txns` : undefined}
            />
            <StatCard
              statKey="sell_value"
              label="Sell Value"
              value={a?.total_sell_value ? formatCompact(a.total_sell_value) : "—"}
              sub={a?.n_sells_priced ? `${a.n_sells_priced.toLocaleString()} priced txns` : undefined}
            />
            <StatCard
              statKey="last_txn"
              label="Last Txn"
              value={a?.last_transaction_date ? formatDate(a.last_transaction_date) : "—"}
              sub={a?.first_transaction_date ? `Active since ${a.first_transaction_date.slice(0, 4)}` : undefined}
            />
          </div>
        );
      })()}

      {/* HQ Address card */}
      <Reportable
        component="hq_address_card"
        data={{
          primary_address: group.primary_address,
          primary_address_source: group.primary_address_source,
          website: group.website,
          primary_phone: group.primary_phone,
        }}
      >
      <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
        <div className="flex items-start justify-between gap-4">
          <div className="flex-1">
            <Text size="1" style={{ color: "var(--gray-9)" }}>HQ Address</Text>
            <div className="mt-1 flex items-start gap-2">
              <MapPin size={16} className="mt-1" style={{ color: "var(--gray-9)" }} />
              <div>
                <Text size="3" style={{ color: "var(--gray-12)" }}>
                  {group.primary_address ? titleCase(group.primary_address) : "—"}
                </Text>
                {group.primary_address_source && (
                  <Text size="1" className="block mt-0.5" style={{ color: "var(--gray-9)" }}>
                    source: {group.primary_address_source}
                  </Text>
                )}
              </div>
            </div>
            {(group.website || group.primary_phone) && (
              <div className="mt-3 flex gap-4 flex-wrap">
                {group.website && (
                  <a
                    href={group.website}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1 text-[14px] no-underline"
                    style={{ color: "var(--accent-11)" }}
                  >
                    {group.website} <ArrowSquareOut size={12} />
                  </a>
                )}
                {group.primary_phone && (
                  <Text size="2" style={{ color: "var(--gray-11)" }}>
                    {formatPhone(group.primary_phone)}
                  </Text>
                )}
              </div>
            )}
          </div>
          <HqPicker
            autoGroupId={group.id}
            currentAddress={group.primary_address}
            currentSource={group.primary_address_source}
            onUpdated={() => setRefreshTick((t) => t + 1)}
          />
        </div>
      </div>
      </Reportable>

      {/* Tabs */}
      <Tabs.Root defaultValue="properties">
        <Tabs.List>
          <Tabs.Trigger value="properties">
            <Buildings size={14} className="mr-1" />
            Properties ({(a?.properties_total ?? a?.transacted_property_count ?? 0).toLocaleString()})
          </Tabs.Trigger>
          <Tabs.Trigger value="contacts">Contacts ({group.total_contact_count})</Tabs.Trigger>
          <Tabs.Trigger value="spvs">SPVs ({group.constituent_legacy_groups.length})</Tabs.Trigger>
          <Tabs.Trigger value="activity">Activity</Tabs.Trigger>
        </Tabs.List>

        <div className="mt-4">
          <Tabs.Content value="properties">
            <PropertiesTab groupId={group.id} />
          </Tabs.Content>
          <Tabs.Content value="contacts">
            <ContactsTab groupId={group.id} onEngagementChange={() => setRefreshTick((t) => t + 1)} />
          </Tabs.Content>
          <Tabs.Content value="spvs">
            <SpvsTab group={group} />
          </Tabs.Content>
          <Tabs.Content value="activity">
            <ActivityFeed entityType="group" entityId={group.id} />
          </Tabs.Content>
        </div>
      </Tabs.Root>
    </div>
  );
}
