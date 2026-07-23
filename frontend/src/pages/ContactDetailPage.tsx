import { useState, useEffect } from "react";
import { Link, useParams, useNavigate } from "react-router-dom";
import { Heading, Text, Button, Badge, TextField, Callout, DropdownMenu, Tabs } from "@radix-ui/themes";
import { CaretDown, User, Lightning, CheckCircle, WarningCircle, DotsThree } from "@phosphor-icons/react";
import { fetchApi, mutateApi } from "../api/client";
import { useCrm } from "../components/crm/CrmContext";
import { formatCurrency, formatDate, formatPhone, formatSf, formatPortfolioUnit, computeOwnershipYears, formatOwnership, titleCase, formatCanonicalAddress as formatCanonicalAddressUtil } from "../lib/utils";
import { categoryColor } from "../lib/theme";
import ConsolidateGroupsModal from "../components/ui/ConsolidateGroupsModal";
import SourceHtmlButton from "../components/source/SourceHtmlButton";
import CreateBuyMandateDrawer from "../components/crm/CreateBuyMandateDrawer";
import QuickActionBar from "../components/crm/QuickActionBar";
import AttributionStrip from "../components/crm/AttributionStrip";
import ActivityFeed from "../components/crm/ActivityFeed";
import LinkedInButton from "../components/ui/LinkedInButton";
import CurrentEmployerPill from "../components/contact/CurrentEmployerPill";
import CareerHistoryTile from "../components/contact/CareerHistoryTile";
import ContactChannelsCard from "../components/contact/ContactChannelsCard";
import ContactNotesCard from "../components/contact/ContactNotesCard";
import TenureDetailDrawer from "../components/contact/TenureDetailDrawer";
import PortfolioFootprintMap from "../components/contact/PortfolioFootprintMap";
import TenuredPropertyFootprintMap from "../components/contact/TenuredPropertyFootprintMap";
import HqPicker from "../components/group/HqPicker";
import type { ContactDetail, AffiliatedGroup, AffiliatedGroupsResponse } from "../types";
import { Reportable, useIssueReporter } from "../components/issues/IssueReporter";
import { Info } from "@phosphor-icons/react";

const formatCanonicalAddress = formatCanonicalAddressUtil;

/** One row in the contact's transactions table. Has a hover-revealed `i` button
 *  in its own cell that opens the issue reporter pre-filled with the row's
 *  source_id + side + price etc. — useful for filing "RT196173 is on the wrong
 *  parcel" without leaving the contact page. */
function TxnRow({ t, onNav }: {
  t: ContactDetail["transactions"][number];
  onNav: () => void;
}) {
  const { open: openIssue } = useIssueReporter();
  return (
    <tr className="group/row border-b border-[var(--gray-4)] hover:bg-[var(--gray-a2)] cursor-pointer"
        onClick={onNav}>
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
      <td className="py-2">
        {t.tenure ? (
          <Badge size="1" variant="soft" color="jade">
            {t.tenure.brand_stem}
            {t.tenure.inferred && " (i)"}
          </Badge>
        ) : null}
      </td>
      <td className="py-2 text-right">{formatCurrency(t.sale_price)}</td>
      <td className="py-2 text-right">{formatOwnership(computeOwnershipYears(t.sale_date))}</td>
      <td className="py-2 text-center">
        {t.source_id?.startsWith("RT") && <SourceHtmlButton sourceId={t.source_id} />}
      </td>
      <td className="px-1 py-2 text-right">
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            openIssue({
              component: "contact_transactions.row",
              component_data: {
                source_id: t.source_id,
                side: t.side,
                sale_date: t.sale_date,
                sale_price: t.sale_price,
                display_address: t.display_address,
                city: t.city,
              },
              contextLabel: `Transaction ${t.source_id} on contact's history`,
            });
          }}
          className="opacity-0 group-hover/row:opacity-100 transition-opacity rounded p-1 hover:bg-[var(--gray-3)]"
          title="Report issue with this transaction"
          style={{ color: "var(--gray-9)" }}
        >
          <Info size={13} weight="bold" />
        </button>
      </td>
    </tr>
  );
}


export default function ContactDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { openDrawer } = useCrm();
  const [contact, setContact] = useState<ContactDetail | null>(null);
  const [editing, setEditing] = useState(false);
  const [editFields, setEditFields] = useState({ email: "", mobile: "", phone: "", job_title: "" });
  const [txnsExpanded, setTxnsExpanded] = useState(false);
  const [affiliatedGroups, setAffiliatedGroups] = useState<AffiliatedGroup[]>([]);
  const [showConsolidate, setShowConsolidate] = useState(false);
  const [showBuyMandateDialog, setShowBuyMandateDialog] = useState(false);
  const [promoteStatus, setPromoteStatus] = useState<{ type: "success" | "error"; message: string } | null>(null);
  const [drawerStem, setDrawerStem] = useState<string | null>(null);
  const [mapMode, setMapMode] = useState<"group" | "signed">("group");

  // Tab state synced to URL hash so deep links survive (Wave 4)
  const VALID_TABS = ["map", "transactions", "career", "activity"] as const;
  const [activeTab, setActiveTab] = useState<string>(() => {
    if (typeof window === "undefined") return "map";
    const h = window.location.hash.replace("#", "");
    return (VALID_TABS as readonly string[]).includes(h) ? h : "map";
  });
  useEffect(() => {
    if (typeof window === "undefined") return;
    const newHash = activeTab === "map" ? "" : `#${activeTab}`;
    if (window.location.hash !== newHash) {
      window.history.replaceState(null, "", `${window.location.pathname}${newHash}`);
    }
  }, [activeTab]);

  const load = () => {
    if (id) {
      fetchApi<ContactDetail>(`/contacts/${id}`).then((c) => {
        setContact(c);
        setEditFields({ email: c.email || "", mobile: c.mobile || "", phone: c.phone || "", job_title: c.job_title || "" });
      });
      fetchApi<AffiliatedGroupsResponse>(`/contacts/${id}/affiliated-groups`).then((r) =>
        setAffiliatedGroups(r.affiliated_groups),
      );
    }
  };

  useEffect(load, [id]);

  if (!contact) return <Text>Loading...</Text>;

  const handlePromote = async () => {
    setPromoteStatus(null);
    try {
      await mutateApi(`/contacts/${id}/promote`, "POST");
      setPromoteStatus({ type: "success", message: "Contact promoted to Engaged." });
      load();
    } catch {
      setPromoteStatus({ type: "error", message: "Failed to promote contact. Please try again." });
    }
  };

  const handleSave = async () => {
    const updates: Record<string, string> = {};
    if (editFields.email !== (contact.email || "")) updates.email = editFields.email;
    if (editFields.mobile !== (contact.mobile || "")) updates.mobile = editFields.mobile;
    if (editFields.phone !== (contact.phone || "")) updates.phone = editFields.phone;
    if (editFields.job_title !== (contact.job_title || "")) updates.job_title = editFields.job_title;
    if (Object.keys(updates).length > 0) {
      await mutateApi(`/contacts/${id}`, "PATCH", updates);
      load();
    }
    setEditing(false);
  };

  return (
    <div className="flex flex-col gap-6">
      {/* Header — Wave 1 redesign: identity left, actions right, overflow menu */}
      <div>
        <Link to="/contacts" className="text-[14px] no-underline" style={{ color: "var(--accent-11)" }}>
          &larr; Contacts
        </Link>
        <div className="flex items-start justify-between gap-4 mt-2">
          {/* Identity column */}
          <div className="flex items-start gap-3 min-w-0 flex-1">
            {contact.linkedin_photo_url ? (
              <img
                src={contact.linkedin_photo_url}
                alt={contact.display_name}
                className="w-12 h-12 rounded-full object-cover border border-[var(--gray-6)] mt-1"
                referrerPolicy="no-referrer"
              />
            ) : (
              <div
                className="w-12 h-12 rounded-full flex items-center justify-center border border-[var(--gray-6)] mt-1"
                style={{ backgroundColor: "var(--gray-3)" }}
              >
                <User size={22} style={{ color: "var(--gray-8)" }} />
              </div>
            )}
            <div className="min-w-0 flex-1">
              {/* Name + LinkedIn icon */}
              <div className="flex items-center gap-2 flex-wrap">
                <Heading size="6" weight="medium">{contact.display_name}</Heading>
                <LinkedInButton
                  contactId={contact.id}
                  contactName={contact.display_name}
                  linkedinUrl={contact.linkedin_url}
                  headline={contact.linkedin_headline}
                  onSaved={() => load()}
                  size="md"
                />
              </div>

              {/* Subtitle: Title · Group (proper-cased, linked) */}
              {(() => {
                const jobTitle = contact.job_title ? titleCase(contact.job_title) : null;
                const ag = contact.current_auto_group;
                const isAnonBucket = ag?.canonical_stem === "_anonymized_individuals";
                const showGroup = ag && !isAnonBucket;
                if (!jobTitle && !showGroup) return null;
                return (
                  <div className="mt-1 flex items-center gap-2 text-[15px] flex-wrap">
                    {jobTitle && (
                      <span style={{ color: "var(--gray-12)" }}>{jobTitle}</span>
                    )}
                    {jobTitle && showGroup && (
                      <span style={{ color: "var(--gray-8)" }}>·</span>
                    )}
                    {showGroup && (
                      <Link
                        to={`/groups/${ag!.auto_group_id}`}
                        className="no-underline font-medium"
                        style={{ color: "var(--accent-11)" }}
                      >
                        {titleCase(ag!.display_name)}
                      </Link>
                    )}
                  </div>
                );
              })()}

              {/* Status line: lifecycle stage · last contacted */}
              <div className="mt-1.5 flex items-center gap-2 text-[13px]" style={{ color: "var(--gray-9)" }}>
                <span className={`inline-block px-2 py-0.5 rounded text-[12px] ${contact.status === 'engaged' ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-600'}`}>
                  {contact.status}
                </span>
                <span>
                  {contact.last_engaged_date
                    ? `Last engaged ${formatDate(contact.last_engaged_date)}`
                    : "Never contacted"}
                </span>
              </div>
            </div>
          </div>

          {/* Actions column */}
          <div className="flex items-center gap-2 shrink-0 mt-1">
            <QuickActionBar
              entityType="contact"
              entityId={contact.id}
              entityName={contact.display_name}
              onCreateBuyMandate={() => setShowBuyMandateDialog(true)}
            />
            <DropdownMenu.Root>
              <DropdownMenu.Trigger>
                <Button size="2" variant="soft" aria-label="More actions">
                  <DotsThree size={18} weight="bold" />
                </Button>
              </DropdownMenu.Trigger>
              <DropdownMenu.Content>
                <DropdownMenu.Item
                  onClick={() => openDrawer({ type: "contact", id: contact.id, name: contact.display_name })}
                >
                  Notes
                </DropdownMenu.Item>
                {contact.status !== "engaged" && (
                  <DropdownMenu.Item onClick={handlePromote}>
                    Promote to Engaged
                  </DropdownMenu.Item>
                )}
              </DropdownMenu.Content>
            </DropdownMenu.Root>
          </div>
        </div>

        <div className="mt-3">
          <AttributionStrip entityType="contact" entityId={contact.id} hideWhenEmpty />
        </div>
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

      {/* Wave 2 — Stats cards row */}
      {(() => {
        const activeTenure = (contact.career_history || []).find((t: any) => t.is_active === 1);
        const derivedTenure = contact.derived_tenure;
        const tenureStart = activeTenure?.inferred_start_date || derivedTenure?.first_date || null;
        const tenureYears = tenureStart
          ? Math.max(0, Math.floor((Date.now() - new Date(tenureStart).getTime()) / (1000 * 60 * 60 * 24 * 365.25)))
          : null;
        const tenureGroup = activeTenure?.display_name
          ? titleCase(activeTenure.display_name)
          : derivedTenure
            ? titleCase(derivedTenure.display_name)
            : (contact.current_auto_group?.canonical_stem !== "_anonymized_individuals"
              ? (contact.current_auto_group ? titleCase(contact.current_auto_group.display_name) : null)
              : null);
        const tenureSince = tenureStart ? tenureStart.slice(0, 4) : null;
        const psize = contact.portfolio_size;
        const punified = contact.properties_unified;
        const primaryUnit = psize?.totals_by_unit?.[0];
        const secondaryUnits = psize?.totals_by_unit?.slice(1) ?? [];
        // Unified Property denominator: every distinct property this contact
        // has been on (resolved parcels + by-address from unresolved txns).
        // Falls back to the resolved-only count if the new field isn't present.
        const propsTotal = punified?.total ?? psize?.total_properties ?? 0;
        const propsOwned = punified?.owned ?? null;
        const sizedReported = psize ? (psize.total_properties - psize.no_size_count) : 0;
        return (
          <div className="grid grid-cols-4 gap-4">
            <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-4">
              <Text size="1" style={{ color: "var(--gray-9)" }}>Transactions</Text>
              <Text size="6" weight="bold" className="block mt-1" style={{ color: "var(--gray-12)" }}>
                {contact.transaction_count.toLocaleString()}
              </Text>
            </div>
            <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-4">
              <Text size="1" style={{ color: "var(--gray-9)" }}>Portfolio Size</Text>
              <Text size="6" weight="bold" className="block mt-1" style={{ color: "var(--gray-12)" }}>
                {primaryUnit
                  ? formatPortfolioUnit(primaryUnit.unit, primaryUnit.total)
                  : propsTotal > 0
                    ? `${propsTotal.toLocaleString()} ${propsTotal === 1 ? "property" : "properties"}`
                    : "—"}
              </Text>
              {primaryUnit ? (
                <Text size="1" style={{ color: "var(--gray-9)" }}>
                  {secondaryUnits.length > 0 && (
                    <span>{secondaryUnits.map(u => `+ ${formatPortfolioUnit(u.unit, u.total)}`).join(" ")}<br /></span>
                  )}
                  {sizedReported.toLocaleString()} sized · {propsOwned != null ? `${propsOwned.toLocaleString()} owned · ` : ""}{propsTotal.toLocaleString()} total
                </Text>
              ) : propsTotal > 0 ? (
                <Text size="1" style={{ color: "var(--gray-9)" }}>
                  {propsOwned != null ? `${propsOwned.toLocaleString()} owned · size not reported` : "size not reported"}
                </Text>
              ) : null}
            </div>
            <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-4">
              <Text size="1" style={{ color: "var(--gray-9)" }}>Tenure</Text>
              <Text size="6" weight="bold" className="block mt-1" style={{ color: "var(--gray-12)" }}>
                {tenureYears != null ? `${tenureYears} yr${tenureYears === 1 ? "" : "s"}` : "—"}
              </Text>
              {tenureGroup && (
                <Text size="1" style={{ color: "var(--gray-9)" }}>
                  at {tenureGroup}{tenureSince ? ` · since ${tenureSince}` : ""}
                </Text>
              )}
            </div>
            <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-4">
              <Text size="1" style={{ color: "var(--gray-9)" }}>Last Seen</Text>
              <Text size="6" weight="bold" className="block mt-1" style={{ color: "var(--gray-12)" }}>
                {contact.last_seen_date ? formatDate(contact.last_seen_date) : "—"}
              </Text>
              <Text size="1" style={{ color: "var(--gray-9)" }}>
                {contact.first_seen_date ? `First seen ${formatDate(contact.first_seen_date)}` : ""}
              </Text>
            </div>
          </div>
        );
      })()}

      <div className="grid grid-cols-3 gap-6">
        {/* Left: Info */}
        <div className="col-span-1 flex flex-col gap-4">
          {/* Group / Employer Card (Wave 3) — primary affiliation */}
          {(() => {
            const ag = contact.current_auto_group;
            if (!ag || ag.canonical_stem === "_anonymized_individuals") return null;
            return (
              <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
                <Text size="1" style={{ color: "var(--gray-9)" }}>Group</Text>
                <Link
                  to={`/groups/${ag.auto_group_id}`}
                  className="block mt-1 no-underline"
                  style={{ color: "var(--gray-12)" }}
                >
                  <Heading size="4" weight="medium">{titleCase(ag.display_name)}</Heading>
                </Link>
                <div className="mt-2 flex items-center gap-2 flex-wrap">
                  <Badge size="1" variant="soft" color={ag.tier === "confirmed" ? "jade" : ag.tier === "probable" ? "gray" : "amber"}>
                    {ag.tier}
                  </Badge>
                  <Text size="1" style={{ color: "var(--gray-9)" }}>
                    {ag.n_members.toLocaleString()} members
                  </Text>
                </div>
                {/* HQ address (Wave 5: algorithmic / manual / AI-enriched) */}
                <div className="mt-3">
                  <div className="flex items-center gap-2">
                    <Text size="1" style={{ color: "var(--gray-9)" }}>
                      HQ {ag.primary_address_source === "algorithmic" ? "(probable)" :
                          ag.primary_address_source === "ai_enriched" ? "(AI-verified)" : ""}
                    </Text>
                    <HqPicker
                      autoGroupId={ag.auto_group_id}
                      currentAddress={ag.primary_address ?? null}
                      currentSource={ag.primary_address_source ?? null}
                      onUpdated={() => load()}
                    />
                  </div>
                  <Text size="2" className="block">
                    {ag.primary_address ? formatCanonicalAddress(ag.primary_address) : "—"}
                  </Text>
                </div>
                {ag.primary_phone && (
                  <div className="mt-2">
                    <Text size="1" style={{ color: "var(--gray-9)" }}>HQ Phone</Text>
                    <a
                      href={`tel:${ag.primary_phone}`}
                      className="block no-underline text-[14px]"
                      style={{ color: "var(--accent-11)" }}
                    >
                      {formatPhone(ag.primary_phone)}
                    </a>
                  </div>
                )}
                {ag.website && (
                  <div className="mt-2">
                    <Text size="1" style={{ color: "var(--gray-9)" }}>Website</Text>
                    <a
                      href={ag.website.startsWith("http") ? ag.website : `https://${ag.website}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="block text-[14px] no-underline"
                      style={{ color: "var(--accent-11)" }}
                    >
                      {ag.website.replace(/^https?:\/\//, "")}
                    </a>
                  </div>
                )}
                <div className="mt-3">
                  <Link
                    to={`/groups/${ag.auto_group_id}`}
                    className="text-[13px] no-underline"
                    style={{ color: "var(--accent-11)" }}
                  >
                    View Group →
                  </Link>
                </div>
              </div>
            );
          })()}

          {/* Contact Info Card — Wave 4: Datanyze merged in, source badges, mailing addresses moved to Career tab */}
          <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
            <div className="flex items-center justify-between mb-3">
              <Text size="3" weight="medium">Contact Info</Text>
              {!editing ? (
                <Button size="1" variant="ghost" onClick={() => setEditing(true)}>Edit</Button>
              ) : (
                <div className="flex gap-1">
                  <Button size="1" variant="ghost" onClick={() => setEditing(false)}>Cancel</Button>
                  <Button size="1" onClick={handleSave}>Save</Button>
                </div>
              )}
            </div>
            {editing ? (
              <div className="flex flex-col gap-3 text-[14px]">
                <div>
                  <Text size="1" style={{ color: "var(--gray-9)" }}>Phone</Text>
                  <TextField.Root size="1" value={editFields.phone} onChange={(e: any) => setEditFields({ ...editFields, phone: e.target.value })} />
                </div>
                <div>
                  <Text size="1" style={{ color: "var(--gray-9)" }}>Email</Text>
                  <TextField.Root size="1" value={editFields.email} onChange={(e: any) => setEditFields({ ...editFields, email: e.target.value })} />
                </div>
                <div>
                  <Text size="1" style={{ color: "var(--gray-9)" }}>Mobile</Text>
                  <TextField.Root size="1" value={editFields.mobile} onChange={(e: any) => setEditFields({ ...editFields, mobile: e.target.value })} />
                </div>
                <div>
                  <Text size="1" style={{ color: "var(--gray-9)" }}>Job Title</Text>
                  <TextField.Root size="1" value={editFields.job_title} onChange={(e: any) => setEditFields({ ...editFields, job_title: e.target.value })} />
                </div>
              </div>
            ) : (() => {
              // HQ phone from the contact's auto_group — used to label a
              // contact phone row that happens to match the switchboard.
              const hqPhoneDigits = (contact.current_auto_group?.primary_phone || "").replace(/\D/g, "");
              const hqGroupName = contact.current_auto_group
                ? titleCase(contact.current_auto_group.display_name)
                : "";

              // Collect all phones (RT + Datanyze) with source badges, deduped by digits
              type Row = { value: string; source: "Realtrack" | "Datanyze" | "LinkedIn"; label?: string };
              const phones: Row[] = [];
              if (contact.phone) phones.push({ value: contact.phone, source: "Realtrack" });
              if (contact.mobile) phones.push({ value: contact.mobile, source: "Realtrack", label: "mobile" });
              contact.datanyze_contacts?.phones?.forEach((p) => {
                phones.push({ value: p.value, source: "Datanyze", label: p.type });
              });
              const seenPhones = new Set<string>();
              const phoneRows = phones.filter((p) => {
                const key = p.value.replace(/\D/g, "");
                if (!key || seenPhones.has(key)) return false;
                seenPhones.add(key);
                return true;
              });

              const emails: Row[] = [];
              if (contact.email) emails.push({ value: contact.email, source: "Realtrack" });
              contact.datanyze_contacts?.emails?.forEach((e) => {
                emails.push({ value: e.value, source: "Datanyze", label: e.type });
              });
              const seenEmails = new Set<string>();
              const emailRows = emails.filter((e) => {
                const key = e.value.toLowerCase().trim();
                if (!key || seenEmails.has(key)) return false;
                seenEmails.add(key);
                return true;
              });

              const sourceBadgeColor = (src: Row["source"]) =>
                src === "Datanyze" ? "amber" : src === "LinkedIn" ? "blue" : "gray";

              return (
                <div className="flex flex-col gap-4 text-[14px]">
                  {/* Job Title */}
                  {contact.job_title && (
                    <div>
                      <Text size="1" style={{ color: "var(--gray-9)" }}>Job Title</Text>
                      <Text size="2" className="block">{titleCase(contact.job_title)}</Text>
                    </div>
                  )}

                  {/* Phone */}
                  <div>
                    <Text size="1" style={{ color: "var(--gray-9)" }}>Phone</Text>
                    {phoneRows.length === 0 ? (
                      <Text size="2" className="block">—</Text>
                    ) : (
                      <div className="flex flex-col gap-1 mt-1">
                        {phoneRows.map((p, i) => {
                          const isHq = hqPhoneDigits && p.value.replace(/\D/g, "") === hqPhoneDigits;
                          return (
                            <div key={`ph-${i}`} className="flex items-center gap-2 flex-wrap">
                              <a href={`tel:${p.value}`} className="no-underline" style={{ color: "var(--accent-11)" }}>
                                {formatPhone(p.value)}
                              </a>
                              {p.label && (
                                <Text size="1" style={{ color: "var(--gray-9)" }}>· {p.label}</Text>
                              )}
                              {isHq ? (
                                <Badge size="1" variant="soft" color="amber" title="This number matches the group's HQ switchboard, not a direct line.">
                                  HQ line{hqGroupName ? ` · ${hqGroupName}` : ""}
                                </Badge>
                              ) : (
                                <Badge size="1" variant="soft" color={sourceBadgeColor(p.source) as any}>
                                  {p.source === "Datanyze" && <Lightning size={10} weight="fill" />}
                                  {p.source}
                                </Badge>
                              )}
                            </div>
                          );
                        })}
                        {contact.phone_tenure_tag && (
                          <Badge
                            size="1"
                            color={contact.phone_tenure_tag.state === "active" ? "jade" : "gray"}
                            variant="soft"
                            className="self-start"
                          >
                            {contact.phone_tenure_tag.state === "active"
                              ? `Active · ${contact.phone_tenure_tag.display_name} since ${(contact.phone_tenure_tag.since || "").slice(0, 4)}`
                              : `Last seen ${(contact.phone_tenure_tag.last_seen || "").slice(0, 10)}${contact.phone_tenure_tag.display_name ? ` · ${contact.phone_tenure_tag.display_name} era` : ""}`}
                          </Badge>
                        )}
                      </div>
                    )}
                  </div>

                  {/* Email */}
                  <div>
                    <Text size="1" style={{ color: "var(--gray-9)" }}>Email</Text>
                    {emailRows.length === 0 ? (
                      <Text size="2" className="block">—</Text>
                    ) : (
                      <div className="flex flex-col gap-1 mt-1">
                        {emailRows.map((e, i) => (
                          <div key={`em-${i}`} className="flex items-center gap-2 flex-wrap">
                            <a href={`mailto:${e.value}`} className="no-underline" style={{ color: "var(--accent-11)" }}>
                              {e.value}
                            </a>
                            {e.label && (
                              <Text size="1" style={{ color: "var(--gray-9)" }}>· {e.label}</Text>
                            )}
                            <Badge size="1" variant="soft" color={sourceBadgeColor(e.source) as any}>
                              {e.source === "Datanyze" && <Lightning size={10} weight="fill" />}
                              {e.source}
                            </Badge>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Social */}
                  {contact.linkedin_url && (
                    <div>
                      <Text size="1" style={{ color: "var(--gray-9)" }}>Social</Text>
                      <div className="flex items-center gap-2 flex-wrap mt-1">
                        <a
                          href={contact.linkedin_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="no-underline"
                          style={{ color: "var(--accent-11)" }}
                        >
                          LinkedIn profile
                        </a>
                        <Badge size="1" variant="soft" color="blue">LinkedIn</Badge>
                      </div>
                    </div>
                  )}
                </div>
              );
            })()}
          </div>

          {/* Channels — phones/emails as a collection with dial verdicts (Phase 1) */}
          <ContactChannelsCard contactId={contact.id} />

          {/* Notes / dossier */}
          <ContactNotesCard contactId={contact.id} />
        </div>

        {/* Right: Tabbed main pane (Wave 4) */}
        <div className="col-span-2">
          <Tabs.Root value={activeTab} onValueChange={setActiveTab}>
            <Tabs.List>
              <Tabs.Trigger value="map">Map</Tabs.Trigger>
              <Tabs.Trigger value="transactions">Transactions ({contact.transactions.length})</Tabs.Trigger>
              <Tabs.Trigger value="career">Career</Tabs.Trigger>
              <Tabs.Trigger value="activity">Activity</Tabs.Trigger>
            </Tabs.List>

            {/* MAP TAB — unified group portfolio + contact's signed transactions */}
            <Tabs.Content value="map" className="mt-4">
              {/* Note: map can only plot resolved (parcel-matched) properties.
                  Unresolved transactions don't have lat/lng so they're absent.
                  Surface the gap so users know the count mismatch. */}
              {contact.properties_unified && contact.properties_unified.unresolved > 0 && (
                <div className="mb-3">
                  <Text size="1" style={{ color: "var(--gray-9)" }}>
                    Showing {contact.properties_unified.resolved.toLocaleString()} of {contact.properties_unified.total.toLocaleString()} properties with mapped parcels.
                    {" "}{contact.properties_unified.unresolved.toLocaleString()} unresolved address{contact.properties_unified.unresolved === 1 ? "" : "es"} not plotted.
                  </Text>
                </div>
              )}
              {(() => {
                const stem = contact.current_employer?.brand_stem;
                if (!stem) {
                  return <TenuredPropertyFootprintMap contactId={contact.id} height={460} />;
                }
                return (
                  <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-3">
                    <div className="flex items-center justify-end mb-3 px-2 pt-1">
                      <div className="flex items-center gap-1 rounded-md border border-[var(--gray-6)] p-0.5 text-[12px]">
                        <button
                          onClick={() => setMapMode("group")}
                          className={`px-2.5 py-1 rounded transition-colors`}
                          style={{
                            backgroundColor: mapMode === "group" ? "var(--accent-3)" : "transparent",
                            color: mapMode === "group" ? "var(--accent-11)" : "var(--gray-11)",
                            fontWeight: mapMode === "group" ? 500 : 400,
                          }}
                        >
                          Group portfolio
                        </button>
                        <button
                          onClick={() => setMapMode("signed")}
                          className={`px-2.5 py-1 rounded transition-colors`}
                          style={{
                            backgroundColor: mapMode === "signed" ? "var(--accent-3)" : "transparent",
                            color: mapMode === "signed" ? "var(--accent-11)" : "var(--gray-11)",
                            fontWeight: mapMode === "signed" ? 500 : 400,
                          }}
                        >
                          Signed by {contact.display_name.split(" ")[0]}
                        </button>
                      </div>
                    </div>
                    {mapMode === "group" ? (
                      <PortfolioFootprintMap
                        stem={stem}
                        displayName={contact.current_employer!.display_name || stem}
                        height={440}
                      />
                    ) : (
                      <TenuredPropertyFootprintMap contactId={contact.id} height={440} />
                    )}
                  </div>
                );
              })()}
            </Tabs.Content>

            {/* TRANSACTIONS TAB — full transaction history */}
            <Tabs.Content value="transactions" className="mt-4">
              <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
                <Text size="3" weight="medium" className="mb-3 block">Transaction History ({contact.transactions.length})</Text>
            {contact.transactions.length === 0 ? (
              <Text size="2" style={{ color: "var(--gray-9)" }}>No transactions</Text>
            ) : (
              <>
                <Reportable component="contact_transactions.table" data={{ total: contact.transactions.length }}>
                <table className="w-full text-[14px] [&_td]:whitespace-nowrap [&_th]:whitespace-nowrap">
                  <thead>
                    <tr className="border-b border-[var(--gray-4)]">
                      <th className="text-left py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Date</th>
                      <th className="text-left py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Address</th>
                      <th className="text-left py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>City</th>
                      <th className="text-left py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Side</th>
                      <th className="text-left py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Tenure</th>
                      <th className="text-right py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Price</th>
                      <th className="text-right py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Ownership</th>
                      <th className="w-8 py-2" />
                      <th className="w-8 py-2" />
                    </tr>
                  </thead>
                  <tbody>
                    {(txnsExpanded ? contact.transactions : contact.transactions.slice(0, 5)).map((t) => (
                      <TxnRow key={t.source_id} t={t} onNav={() => navigate(`/transactions/${t.source_id}`)} />
                    ))}
                  </tbody>
                </table>
                </Reportable>
                {contact.transactions.length > 5 && (
                  <button
                    onClick={() => setTxnsExpanded(!txnsExpanded)}
                    className="mt-2 flex items-center gap-1 text-[13px] font-medium hover:underline"
                    style={{ color: "var(--accent-11)" }}
                  >
                    <CaretDown size={12} style={{ transform: txnsExpanded ? "rotate(180deg)" : undefined, transition: "transform 0.15s" }} />
                    {txnsExpanded ? "Show less" : `See all ${contact.transactions.length} transactions`}
                  </button>
                )}
              </>
            )}
              </div>
            </Tabs.Content>

            {/* CAREER TAB — career history with per-tenure primary address */}
            <Tabs.Content value="career" className="mt-4">
              <CareerHistoryTile
                realtrack={contact.career_history}
                linkedIn={contact.work_history}
                totalSpvCount={affiliatedGroups.length}
                onRowClick={(stem) => setDrawerStem(stem)}
                onViewSpvs={() => setShowConsolidate(true)}
              />
            </Tabs.Content>

            {/* ACTIVITY TAB — communications log (HubSpot sync deferred) */}
            <Tabs.Content value="activity" className="mt-4">
              <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
                <Text size="3" weight="medium" className="mb-3 block">Activity log</Text>
                <ActivityFeed entityType="contact" entityId={contact.id} />
                <Text size="1" className="block mt-4" style={{ color: "var(--gray-9)" }}>
                  Email and call history will appear here once HubSpot sync is enabled.
                </Text>
              </div>
            </Tabs.Content>
          </Tabs.Root>
        </div>
      </div>

      {/* Consolidate Groups Modal */}
      {showConsolidate && contact && (
        <ConsolidateGroupsModal
          contactId={contact.id}
          contactName={contact.display_name}
          onClose={() => setShowConsolidate(false)}
          onConsolidated={() => {
            setShowConsolidate(false);
            load();
          }}
        />
      )}

      {/* Buy Mandate Drawer */}
      {showBuyMandateDialog && contact && (
        <CreateBuyMandateDrawer
          contactId={contact.id}
          entityName={contact.display_name}
          onClose={() => setShowBuyMandateDialog(false)}
        />
      )}

      <TenureDetailDrawer
        contactId={contact.id}
        stem={drawerStem}
        onClose={() => setDrawerStem(null)}
      />
    </div>
  );
}
