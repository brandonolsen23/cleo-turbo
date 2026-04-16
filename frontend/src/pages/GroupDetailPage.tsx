import { useState, useEffect, useMemo } from "react";
import { Link, useParams, useNavigate } from "react-router-dom";
import { Heading, Text, Button, Badge, Callout } from "@radix-ui/themes";
import { GitMerge, UserPlus, X as XIcon, CaretDown, CaretRight, MapPin, CheckCircle, WarningCircle } from "@phosphor-icons/react";
import { PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip as RechartsTooltip } from "recharts";
import { fetchApi, mutateApi } from "../api/client";
import { useCrm } from "../components/crm/CrmContext";
import { formatCurrency, formatCompact, formatDate, formatPhone, computeOwnershipYears, formatOwnership } from "../lib/utils";
import { propertyTypeColor, propertyTypeLabel, categoryColor, getRadixHex } from "../lib/theme";
import PropertyMiniMap from "../components/ui/PropertyMiniMap";
import SourceHtmlButton from "../components/source/SourceHtmlButton";
import MergeGroupsModal from "../components/ui/MergeGroupsModal";
import LinkContactModal from "../components/ui/LinkContactModal";
import CreateBuyMandateDrawer from "../components/crm/CreateBuyMandateDrawer";
import SuggestedLinksCard from "../components/ui/SuggestedLinksCard";
import type { GroupDetail, MiniMapProperty, MergeHistoryResponse, GroupContactLink, GroupContactsResponse } from "../types";

function StatCard({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-4">
      <Text size="1" style={{ color: "var(--gray-9)" }}>{label}</Text>
      <Text size="5" weight="bold" className="block mt-1" style={{ color: "var(--gray-12)" }}>
        {value}
      </Text>
      {sub && <Text size="1" style={{ color: "var(--gray-9)" }}>{sub}</Text>}
    </div>
  );
}

// ── Buy/Sell timeline bar chart (individual transactions) ─────

interface TxnBar {
  idx: number;
  date: string;
  label: string;       // formatted date for tooltip
  address: string;
  buy: number;         // positive value (0 if sell)
  sell: number;        // negative value (0 if buy)
  side: string;
  price: number;       // original positive price
}

function buildTxnBars(transactions: { sale_date: string | null; sale_price: number | null; side: string; display_address?: string }[]): TxnBar[] {
  return transactions
    .filter((t) => t.sale_date)
    .sort((a, b) => (a.sale_date! > b.sale_date! ? 1 : -1))
    .map((t, i) => {
      const price = t.sale_price ?? 0;
      const d = new Date(t.sale_date + "T00:00:00");
      const label = d.toLocaleDateString("en-CA", { month: "short", year: "numeric" });
      return {
        idx: i,
        date: t.sale_date!,
        label,
        address: t.display_address ?? "",
        buy: t.side === "buyer" ? price : 0,
        sell: t.side === "buyer" ? 0 : -price,
        side: t.side,
        price,
      };
    });
}

// Tremor-inspired palette — soft, muted tones
const BUY_COLOR = "#2eb88a";   // soft green (between jade-9 and emerald)
const SELL_COLOR = "#f97066";   // soft coral red

function CustomTooltip({ active, payload }: any) {
  if (!active || !payload?.[0]) return null;
  const d = payload[0].payload as TxnBar;
  return (
    <div className="rounded-lg border border-[var(--gray-5)] bg-white px-3 py-2 shadow-lg" style={{ minWidth: 180 }}>
      <p className="text-[11px] font-medium mb-1" style={{ color: "var(--gray-9)" }}>{d.label}</p>
      <p className="text-[13px] font-semibold" style={{ color: d.side === "buyer" ? BUY_COLOR : SELL_COLOR }}>
        {d.side === "buyer" ? "Acquisition" : "Disposition"} &middot; {formatCurrency(d.price)}
      </p>
      {d.address && (
        <p className="text-[11px] mt-0.5 truncate" style={{ color: "var(--gray-10)", maxWidth: 220 }}>{d.address}</p>
      )}
    </div>
  );
}

function TransactionTimelineChart({ transactions }: { transactions: { sale_date: string | null; sale_price: number | null; side: string; display_address?: string }[] }) {
  const data = useMemo(() => buildTxnBars(transactions), [transactions]);

  if (data.length === 0) return null;

  // Compute year labels for the X axis — show the year at first transaction of each year
  const yearTicks = useMemo(() => {
    const seen = new Set<number>();
    return data.reduce<number[]>((acc, d) => {
      const y = new Date(d.date + "T00:00:00").getFullYear();
      if (!seen.has(y)) { seen.add(y); acc.push(d.idx); }
      return acc;
    }, []);
  }, [data]);

  const totalBuys = data.filter((d) => d.side === "buyer").length;
  const totalSells = data.length - totalBuys;

  return (
    <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
      <div className="flex items-center justify-between mb-4">
        <Text size="2" weight="medium">Transaction Activity</Text>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-1.5">
            <div className="w-2.5 h-2.5 rounded-sm" style={{ backgroundColor: BUY_COLOR }} />
            <span className="text-[11px] font-medium" style={{ color: "var(--gray-9)" }}>Buys ({totalBuys})</span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-2.5 h-2.5 rounded-sm" style={{ backgroundColor: SELL_COLOR }} />
            <span className="text-[11px] font-medium" style={{ color: "var(--gray-9)" }}>Sells ({totalSells})</span>
          </div>
        </div>
      </div>
      <ResponsiveContainer width="100%" height={240}>
        <BarChart data={data} margin={{ top: 8, right: 4, bottom: 0, left: 0 }} barCategoryGap={1}>
          <CartesianGrid vertical={false} strokeDasharray="3 3" stroke="var(--gray-4)" />
          <XAxis
            dataKey="idx"
            tickLine={false}
            axisLine={false}
            tick={{ fontSize: 11, fill: "var(--gray-8)" }}
            ticks={yearTicks}
            tickFormatter={(idx: number) => {
              const d = data[idx];
              return d ? String(new Date(d.date + "T00:00:00").getFullYear()) : "";
            }}
          />
          <YAxis
            tickLine={false}
            axisLine={false}
            tick={{ fontSize: 11, fill: "var(--gray-8)" }}
            tickFormatter={(v: number) => {
              if (v === 0) return "$0";
              return formatCompact(Math.abs(v));
            }}
            width={56}
          />
          <ReferenceLine y={0} stroke="var(--gray-6)" strokeWidth={1} />
          <RechartsTooltip
            content={<CustomTooltip />}
            cursor={{ fill: "var(--gray-a3)" }}
          />
          <Bar dataKey="buy" fill={BUY_COLOR} radius={[2, 2, 0, 0]} />
          <Bar dataKey="sell" fill={SELL_COLOR} radius={[0, 0, 2, 2]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

// ── Main page component ───────────────────────────────────────

export default function GroupDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { openDrawer } = useCrm();
  const [group, setGroup] = useState<GroupDetail | null>(null);
  const [mergeHistory, setMergeHistory] = useState<MergeHistoryResponse | null>(null);
  const [showMergeModal, setShowMergeModal] = useState(false);
  const [showLinkContact, setShowLinkContact] = useState(false);
  const [groupContacts, setGroupContacts] = useState<GroupContactLink[]>([]);
  const [knownNamesOpen, setKnownNamesOpen] = useState(false);
  const [propsExpanded, setPropsExpanded] = useState(false);
  const [txnsExpanded, setTxnsExpanded] = useState(false);
  const [showBuyMandateDialog, setShowBuyMandateDialog] = useState(false);
  const [promoteStatus, setPromoteStatus] = useState<{ type: "success" | "error"; message: string } | null>(null);

  const load = () => {
    if (id) {
      fetchApi<GroupDetail>(`/groups/${id}`).then(setGroup);
      fetchApi<MergeHistoryResponse>(`/group-merges/history/${id}`).then(setMergeHistory);
      fetchApi<GroupContactsResponse>(`/groups/${id}/contacts`).then((r) => setGroupContacts(r.contacts));
    }
  };

  useEffect(load, [id]);

  // useMemo MUST be called before any early return (Rules of Hooks)
  const mappable: MiniMapProperty[] = useMemo(() => {
    if (!group?.properties) return [];
    return group.properties
      .filter((p): p is typeof p & { lat: number; lng: number } => p.lat != null && p.lng != null)
      .map((p) => ({
        id: p.id,
        display_address: p.display_address,
        city: p.city,
        lat: p.lat,
        lng: p.lng,
        asset_class: p.asset_class ?? null,
        most_recent_sale_price: p.most_recent_sale_price,
      }));
  }, [group?.properties]);

  if (!group) return <Text>Loading...</Text>;

  const a = group.analytics;

  const handlePromote = async () => {
    setPromoteStatus(null);
    try {
      await mutateApi(`/groups/${id}/promote`, "POST");
      setPromoteStatus({ type: "success", message: "Group promoted to Engaged." });
      load();
    } catch {
      setPromoteStatus({ type: "error", message: "Failed to promote group. Please try again." });
    }
  };

  // Property type mix chart data — use the canonical color palette from theme.ts
  const typeData = a?.property_type_mix
    ? Object.entries(a.property_type_mix).map(([name, value]) => ({
        name,
        value,
        label: propertyTypeLabel(name),
        color: getRadixHex(propertyTypeColor(name), 9),
      }))
    : [];

  const hqData = a?.hq_lat != null && a?.hq_lng != null
    ? { lat: a.hq_lat, lng: a.hq_lng, label: "HQ" }
    : null;

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
          <Button size="1" variant="outline" onClick={() => setShowMergeModal(true)}>
            <GitMerge size={14} />
            Merge
          </Button>
          <Button size="1" variant="soft" onClick={() => setShowBuyMandateDialog(true)}>
            Buy Mandate
          </Button>
        </div>
        {(group.corporate_address || group.hq_address) && (
          <div className="flex items-center gap-1.5 mt-1.5">
            <MapPin size={14} style={{ color: "var(--gray-9)", flexShrink: 0 }} />
            <Text size="2" style={{ color: "var(--gray-9)" }}>
              {group.corporate_address || group.hq_address}
            </Text>
          </div>
        )}
      </div>

      {promoteStatus && (
        <Callout.Root
          color={promoteStatus.type === "success" ? "jade" : "red"}
          size="1"
          variant="soft"
        >
          <Callout.Icon>
            {promoteStatus.type === "success" ? <CheckCircle size={16} /> : <WarningCircle size={16} />}
          </Callout.Icon>
          <Callout.Text>{promoteStatus.message}</Callout.Text>
        </Callout.Root>
      )}

      {/* Top row: Chart (left) + Stat cards stacked (right) */}
      {a ? (
        <div className="grid grid-cols-2 gap-4">
          <div className="flex flex-col gap-4">
            <StatCard
              label="Portfolio"
              value={`${a.property_count} Properties`}
              sub={(() => {
                const totalPurchaseValue = group.properties.reduce((sum, p) => sum + (p.most_recent_sale_price ?? 0), 0);
                if (totalPurchaseValue > 0) return `${formatCompact(totalPurchaseValue)} portfolio value`;
                return `${a.region_count} region${a.region_count !== 1 ? 's' : ''}`;
              })()}
            />
            <StatCard
              label="Trading Activity"
              value={`${a.total_buys} buys / ${a.total_sells} sells`}
              sub={a.net_acquisitions > 0 ? `Net +${a.net_acquisitions} (accumulating)` : a.net_acquisitions < 0 ? `Net ${a.net_acquisitions} (divesting)` : "Net 0 (balanced)"}
            />
          </div>
          {group.transactions.length > 0 ? (
            <TransactionTimelineChart transactions={group.transactions} />
          ) : (
            <div />
          )}
        </div>
      ) : (
        <div className="grid grid-cols-3 gap-4">
          <StatCard label="Properties" value={group.property_count} />
          <StatCard label="Transactions" value={group.transaction_count} />
          <StatCard label="Contacts" value={group.contact_count} />
        </div>
      )}

      {/* Property Types (left) + Portfolio Map (right) — side by side */}
      {(typeData.length > 0 || mappable.length > 0) && (
        <div className="grid grid-cols-2 gap-4">
          {/* Property Types */}
          {typeData.length > 0 ? (
            <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
              <Text size="2" weight="medium" className="mb-2 block">Property Types</Text>
              <div className="flex items-center gap-4">
                <div style={{ width: 140, height: 140 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie data={typeData} dataKey="value" nameKey="label" cx="50%" cy="50%"
                           innerRadius={35} outerRadius={65} paddingAngle={2}>
                        {typeData.map((entry) => (
                          <Cell key={entry.name} fill={entry.color} />
                        ))}
                      </Pie>
                      <RechartsTooltip formatter={(value: number) => [value, "properties"]} />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
                <div className="flex flex-col gap-1">
                  {typeData.map((d) => (
                    <div key={d.name} className="flex items-center gap-2">
                      <div className="w-3 h-3 rounded-sm" style={{ backgroundColor: d.color }} />
                      <Text size="1" style={{ color: "var(--gray-11)" }}>
                        {d.label} ({d.value})
                      </Text>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            <div />
          )}

          {/* Portfolio Map */}
          {mappable.length > 0 ? (
            <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
              <Text size="2" weight="medium" className="mb-3 block">
                Portfolio Map ({mappable.length} properties)
              </Text>
              <PropertyMiniMap
                properties={mappable}
                hq={hqData}
                height={260}
                onPropertyClick={(pid) => navigate(`/properties/${pid}`)}
              />
            </div>
          ) : (
            <div />
          )}
        </div>
      )}

      {/* Known Names — collapsible */}
      {group.known_names.length > 1 && (
        <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)]">
          <button
            className="w-full flex items-center gap-2 px-5 py-3 text-left"
            onClick={() => setKnownNamesOpen(!knownNamesOpen)}
          >
            {knownNamesOpen
              ? <CaretDown size={14} style={{ color: "var(--gray-9)" }} />
              : <CaretRight size={14} style={{ color: "var(--gray-9)" }} />}
            <Text size="2" weight="medium">Known Names ({group.known_names.length})</Text>
          </button>
          {knownNamesOpen && (
            <div className="px-5 pb-4 flex flex-wrap gap-2">
              {group.known_names.map((n) => (
                <Badge key={n.normalized} size="1" variant="soft">{n.name}</Badge>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Suggested Links (address/contact/phone based) */}
      {id && <SuggestedLinksCard groupId={id} onMerged={load} />}

      {/* Contacts */}
      <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
        <div className="flex items-center justify-between mb-3">
          <Text size="3" weight="medium">Contacts ({groupContacts.length || group.contacts.length})</Text>
          <Button size="1" variant="soft" onClick={() => setShowLinkContact(true)}>
            <UserPlus size={14} />
            Link Contact
          </Button>
        </div>
        {(groupContacts.length > 0 ? groupContacts : group.contacts).length === 0 ? (
          <Text size="2" style={{ color: "var(--gray-9)" }}>No contacts</Text>
        ) : (
          <table className="w-full text-[14px] [&_td]:whitespace-nowrap [&_th]:whitespace-nowrap">
            <thead>
              <tr className="border-b border-[var(--gray-4)]">
                <th className="text-left py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Name</th>
                <th className="text-left py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Phone</th>
                <th className="text-left py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Role</th>
                <th className="text-left py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Status</th>
                <th className="text-left py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Link</th>
                <th className="text-right py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Txns</th>
                <th className="text-right py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}></th>
              </tr>
            </thead>
            <tbody>
              {(groupContacts.length > 0 ? groupContacts : group.contacts.map((c) => ({
                ...c, email: null, contact_type: null, link_type: "derived" as const, is_current: true, role: null, link_notes: null,
              }))).map((c) => (
                <tr key={c.id} className="border-b border-[var(--gray-4)] hover:bg-[var(--gray-a2)] cursor-pointer"
                    onClick={() => navigate(`/contacts/${c.id}`)}>
                  <td className="py-2 font-medium">
                    {c.display_name}
                    {!c.is_current && (
                      <Badge size="1" variant="soft" color="gray" className="ml-2">Former</Badge>
                    )}
                  </td>
                  <td className="py-2">
                    {c.phone ? (
                      <a href={`tel:${c.phone}`} className="no-underline" style={{ color: "var(--accent-11)" }}
                         onClick={(e) => e.stopPropagation()}>
                        {formatPhone(c.phone)}
                      </a>
                    ) : "—"}
                  </td>
                  <td className="py-2" style={{ color: "var(--gray-11)" }}>{c.role || c.job_title || "—"}</td>
                  <td className="py-2">
                    <span className={`inline-block px-2 py-0.5 rounded text-[12px] ${c.status === 'engaged' ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-600'}`}>
                      {c.status}
                    </span>
                  </td>
                  <td className="py-2">
                    <Badge size="1" variant="outline" color={c.link_type === "manual" ? "violet" : c.link_type === "both" ? "blue" : "gray"}>
                      {c.link_type === "derived" ? "auto" : c.link_type === "manual" ? "manual" : "auto+manual"}
                    </Badge>
                  </td>
                  <td className="py-2 text-right">{c.transaction_count}</td>
                  <td className="py-2 text-right">
                    {(c.link_type === "manual" || c.link_type === "both") && (
                      <button
                        className="p-1 rounded hover:bg-red-50 text-[var(--gray-8)] hover:text-red-600 transition-colors"
                        title="Unlink contact"
                        onClick={async (e) => {
                          e.stopPropagation();
                          await mutateApi(`/groups/${id}/contacts/${c.id}`, "DELETE");
                          load();
                        }}
                      >
                        <XIcon size={14} />
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Properties */}
      <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5 overflow-x-auto">
        <Text size="3" weight="medium" className="mb-3 block">Properties ({group.properties.length})</Text>
        {group.properties.length === 0 ? (
          <Text size="2" style={{ color: "var(--gray-9)" }}>No properties</Text>
        ) : (
          <>
            <table className="w-full text-[14px] [&_td]:whitespace-nowrap [&_th]:whitespace-nowrap">
              <thead>
                <tr className="border-b border-[var(--gray-4)]">
                  <th className="text-left py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Address</th>
                  <th className="text-left py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>City</th>
                  <th className="text-right py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Last Sale</th>
                  <th className="text-right py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Price</th>
                  <th className="text-right py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Ownership</th>
                </tr>
              </thead>
              <tbody>
                {(propsExpanded ? group.properties : group.properties.slice(0, 5)).map((p) => (
                  <tr key={p.id} className="border-b border-[var(--gray-4)] hover:bg-[var(--gray-a2)] cursor-pointer"
                      onClick={() => navigate(`/properties/${p.id}`)}>
                    <td className="py-2 !whitespace-normal">
                      <div className="whitespace-nowrap">{p.display_address}</div>
                      {p.brands && p.brands.length > 0 && (
                        <div className="flex flex-wrap gap-1 mt-1">
                          {p.brands.map((b, j) => (
                            <Badge key={j} size="1" variant="soft" color={categoryColor(b.category)}>
                              {b.brand}
                            </Badge>
                          ))}
                        </div>
                      )}
                    </td>
                    <td className="py-2">{p.city}</td>
                    <td className="py-2 text-right">{formatDate(p.most_recent_sale_date)}</td>
                    <td className="py-2 text-right">{formatCurrency(p.most_recent_sale_price)}</td>
                    <td className="py-2 text-right">{formatOwnership(computeOwnershipYears(p.most_recent_sale_date))}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {group.properties.length > 5 && (
              <button
                onClick={() => setPropsExpanded(!propsExpanded)}
                className="mt-2 flex items-center gap-1 text-[13px] font-medium hover:underline"
                style={{ color: "var(--accent-11)" }}
              >
                <CaretDown size={12} style={{ transform: propsExpanded ? "rotate(180deg)" : undefined, transition: "transform 0.15s" }} />
                {propsExpanded ? "Show less" : `See all ${group.properties.length} properties`}
              </button>
            )}
          </>
        )}
      </div>

      {/* Transaction History */}
      <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
        <Text size="3" weight="medium" className="mb-3 block">Transaction History ({group.transactions.length})</Text>
        {group.transactions.length === 0 ? (
          <Text size="2" style={{ color: "var(--gray-9)" }}>No transactions</Text>
        ) : (
          <>
            <table className="w-full text-[14px] [&_td]:whitespace-nowrap [&_th]:whitespace-nowrap">
              <thead>
                <tr className="border-b border-[var(--gray-4)]">
                  <th className="text-left py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Date</th>
                  <th className="text-left py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Address</th>
                  <th className="text-left py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>City</th>
                  <th className="text-left py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Side</th>
                  <th className="text-right py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Price</th>
                  <th className="w-8 py-2" />
                </tr>
              </thead>
              <tbody>
                {(txnsExpanded ? group.transactions : group.transactions.slice(0, 5)).map((t, i) => (
                  <tr key={`${t.source_id}-${i}`} className="border-b border-[var(--gray-4)] hover:bg-[var(--gray-a2)] cursor-pointer"
                      onClick={() => navigate(`/transactions/${t.source_id}`)}>
                    <td className="py-2">{formatDate(t.sale_date)}</td>
                    <td className="py-2 !whitespace-normal">
                      <div className="whitespace-nowrap">{t.display_address}</div>
                      {t.brands && t.brands.length > 0 && (
                        <div className="flex flex-wrap gap-1 mt-1">
                          {t.brands.map((b, j) => (
                            <Badge key={j} size="1" variant="soft" color={categoryColor(b.category)}>
                              {b.brand}
                            </Badge>
                          ))}
                        </div>
                      )}
                    </td>
                    <td className="py-2">{t.city}</td>
                    <td className="py-2">
                      <Badge size="1" variant="soft" color={t.side === "buyer" ? "blue" : "orange"}>
                        {t.side}
                      </Badge>
                    </td>
                    <td className="py-2 text-right">{formatCurrency(t.sale_price)}</td>
                    <td className="py-2 text-center">
                      {t.source_id?.startsWith("RT") && <SourceHtmlButton sourceId={t.source_id} />}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {group.transactions.length > 5 && (
              <button
                onClick={() => setTxnsExpanded(!txnsExpanded)}
                className="mt-2 flex items-center gap-1 text-[13px] font-medium hover:underline"
                style={{ color: "var(--accent-11)" }}
              >
                <CaretDown size={12} style={{ transform: txnsExpanded ? "rotate(180deg)" : undefined, transition: "transform 0.15s" }} />
                {txnsExpanded ? "Show less" : `See all ${group.transactions.length} transactions`}
              </button>
            )}
          </>
        )}
      </div>

      {/* Merge History */}
      {mergeHistory && mergeHistory.absorbed.length > 0 && (
        <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
          <Text size="3" weight="medium" className="mb-3 block">
            <GitMerge size={16} className="inline mr-1" style={{ verticalAlign: "text-bottom" }} />
            Merged Groups ({mergeHistory.absorbed.length})
          </Text>
          <div className="flex flex-col gap-2">
            {mergeHistory.absorbed.map((m) => (
              <div key={m.id} className="flex items-center justify-between py-1.5 border-b border-[var(--gray-4)] last:border-0">
                <div>
                  <Text size="2" weight="medium">{m.source_name}</Text>
                  <Text size="1" className="block" style={{ color: "var(--gray-9)" }}>
                    Merged {formatDate(m.merged_at)}{m.merged_by ? ` by ${m.merged_by}` : ""}
                  </Text>
                </div>
                {!m.unmerged_at && (
                  <Badge size="1" color="jade" variant="soft">Active</Badge>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Link Contact Modal */}
      {showLinkContact && group && (
        <LinkContactModal
          groupId={group.id}
          groupName={group.display_name}
          existingContactIds={new Set(groupContacts.map((c) => c.id))}
          onClose={() => setShowLinkContact(false)}
          onLinked={() => {
            setShowLinkContact(false);
            load();
          }}
        />
      )}

      {/* Merge Modal */}
      {showMergeModal && group && (
        <MergeGroupsModal
          targetGroup={{
            id: group.id,
            display_name: group.display_name,
            property_count: group.property_count,
            transaction_count: group.transaction_count,
            contact_count: group.contact_count,
          }}
          onClose={() => setShowMergeModal(false)}
          onMerged={(survivorId) => {
            setShowMergeModal(false);
            if (survivorId === id) {
              // Absorbed others into this group — just refresh
              load();
            } else {
              // Merged this group into another — navigate to the survivor
              navigate(`/groups/${survivorId}`);
            }
          }}
        />
      )}

      {/* Buy Mandate Drawer */}
      {showBuyMandateDialog && group && (
        <CreateBuyMandateDrawer
          groupId={group.id}
          entityName={group.display_name}
          onClose={() => setShowBuyMandateDialog(false)}
        />
      )}
    </div>
  );
}
