import { useState, useEffect } from "react";
import { Link, useParams, useNavigate } from "react-router-dom";
import { Heading, Text, Button, Badge, TextField, Callout } from "@radix-ui/themes";
import { CaretDown, User, Lightning, CheckCircle, WarningCircle } from "@phosphor-icons/react";
import { fetchApi, mutateApi } from "../api/client";
import { useCrm } from "../components/crm/CrmContext";
import { formatCurrency, formatDate, formatPhone, computeOwnershipYears, formatOwnership } from "../lib/utils";
import { categoryColor } from "../lib/theme";
import PropertyMiniMap from "../components/ui/PropertyMiniMap";
import ConsolidateGroupsModal from "../components/ui/ConsolidateGroupsModal";
import SourceHtmlButton from "../components/source/SourceHtmlButton";
import CreateBuyMandateDrawer from "../components/crm/CreateBuyMandateDrawer";
import LinkedInButton from "../components/ui/LinkedInButton";
import CurrentEmployerPill from "../components/contact/CurrentEmployerPill";
import CareerHistoryTile from "../components/contact/CareerHistoryTile";
import TenureDetailDrawer from "../components/contact/TenureDetailDrawer";
import PortfolioFootprintMap from "../components/contact/PortfolioFootprintMap";
import TenuredPropertyFootprintMap from "../components/contact/TenuredPropertyFootprintMap";
import type { ContactDetail, MiniMapProperty, ContactPropertyHistoryResponse, AffiliatedGroup, AffiliatedGroupsResponse } from "../types";

export default function ContactDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { openDrawer } = useCrm();
  const [contact, setContact] = useState<ContactDetail | null>(null);
  const [editing, setEditing] = useState(false);
  const [editFields, setEditFields] = useState({ email: "", mobile: "", phone: "", job_title: "" });
  const [propertyHistory, setPropertyHistory] = useState<MiniMapProperty[]>([]);
  const [txnsExpanded, setTxnsExpanded] = useState(false);
  const [affiliatedGroups, setAffiliatedGroups] = useState<AffiliatedGroup[]>([]);
  const [showConsolidate, setShowConsolidate] = useState(false);
  const [showBuyMandateDialog, setShowBuyMandateDialog] = useState(false);
  const [promoteStatus, setPromoteStatus] = useState<{ type: "success" | "error"; message: string } | null>(null);
  const [drawerStem, setDrawerStem] = useState<string | null>(null);

  const load = () => {
    if (id) {
      fetchApi<ContactDetail>(`/contacts/${id}`).then((c) => {
        setContact(c);
        setEditFields({ email: c.email || "", mobile: c.mobile || "", phone: c.phone || "", job_title: c.job_title || "" });
      });
      fetchApi<ContactPropertyHistoryResponse>(`/contacts/${id}/properties`).then((r) =>
        setPropertyHistory(r.properties),
      );
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
      {/* Header */}
      <div>
        <Link to="/contacts" className="text-[14px] no-underline" style={{ color: "var(--accent-11)" }}>
          &larr; Contacts
        </Link>
        <div className="flex items-center gap-3 mt-2">
          {contact.linkedin_photo_url ? (
            <img
              src={contact.linkedin_photo_url}
              alt={contact.display_name}
              className="w-10 h-10 rounded-full object-cover border border-[var(--gray-6)]"
              referrerPolicy="no-referrer"
            />
          ) : (
            <div
              className="w-10 h-10 rounded-full flex items-center justify-center border border-[var(--gray-6)]"
              style={{ backgroundColor: "var(--gray-3)" }}
            >
              <User size={20} style={{ color: "var(--gray-8)" }} />
            </div>
          )}
          <Heading size="5" weight="medium">{contact.display_name}</Heading>
          <LinkedInButton
            contactId={contact.id}
            contactName={contact.display_name}
            linkedinUrl={contact.linkedin_url}
            headline={contact.linkedin_headline}
            onSaved={() => load()}
            size="md"
          />
          <span className={`inline-block px-2 py-0.5 rounded text-[12px] ${contact.status === 'engaged' ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-600'}`}>
            {contact.status}
          </span>
          {contact.status !== "engaged" && (
            <Button size="1" variant="soft" onClick={handlePromote}>Promote to Engaged</Button>
          )}
          <Button size="1" variant="outline" onClick={() => openDrawer({ type: "contact", id: contact.id, name: contact.display_name })}>
            Notes
          </Button>
          <Button size="1" variant="soft" onClick={() => setShowBuyMandateDialog(true)}>
            Buy Mandate
          </Button>
        </div>
        {contact.current_employer ? (
          <div className="mt-1">
            <CurrentEmployerPill employer={contact.current_employer} />
          </div>
        ) : contact.company_name ? (
          <Text size="2" style={{ color: "var(--gray-9)" }}>{contact.company_name}</Text>
        ) : null}
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

      <div className="grid grid-cols-3 gap-6">
        {/* Left: Info */}
        <div className="col-span-1 flex flex-col gap-4">
          {/* Contact Info Card */}
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
            <div className="flex flex-col gap-3 text-[14px]">
              <div>
                <Text size="1" style={{ color: "var(--gray-9)" }}>Phone</Text>
                {editing ? (
                  <TextField.Root size="1" value={editFields.phone} onChange={(e: any) => setEditFields({ ...editFields, phone: e.target.value })} />
                ) : (
                  contact.phone ? (
                    <div className="flex items-center gap-2 flex-wrap">
                      <a href={`tel:${contact.phone}`} className="no-underline" style={{ color: "var(--accent-11)" }}>
                        {formatPhone(contact.phone)}
                      </a>
                      {contact.phone_tenure_tag && (
                        <Badge
                          size="1"
                          color={contact.phone_tenure_tag.state === "active" ? "jade" : "gray"}
                          variant="soft"
                        >
                          {contact.phone_tenure_tag.state === "active"
                            ? `Active · ${contact.phone_tenure_tag.display_name} since ${(contact.phone_tenure_tag.since || "").slice(0, 4)}`
                            : `Last seen ${(contact.phone_tenure_tag.last_seen || "").slice(0, 10)}${contact.phone_tenure_tag.display_name ? ` · ${contact.phone_tenure_tag.display_name} era` : ""}`}
                        </Badge>
                      )}
                    </div>
                  ) : <Text size="2" className="block">—</Text>
                )}
              </div>
              <div>
                <Text size="1" style={{ color: "var(--gray-9)" }}>Email</Text>
                {editing ? (
                  <TextField.Root size="1" value={editFields.email} onChange={(e: any) => setEditFields({ ...editFields, email: e.target.value })} />
                ) : (
                  contact.email ? (
                    <a href={`mailto:${contact.email}`} className="block no-underline" style={{ color: "var(--accent-11)" }}>
                      {contact.email}
                    </a>
                  ) : <Text size="2" className="block">—</Text>
                )}
              </div>
              <div>
                <Text size="1" style={{ color: "var(--gray-9)" }}>Mobile</Text>
                {editing ? (
                  <TextField.Root size="1" value={editFields.mobile} onChange={(e: any) => setEditFields({ ...editFields, mobile: e.target.value })} />
                ) : <Text size="2" className="block">{formatPhone(contact.mobile)}</Text>}
              </div>
              <div>
                <Text size="1" style={{ color: "var(--gray-9)" }}>Job Title</Text>
                {editing ? (
                  <TextField.Root size="1" value={editFields.job_title} onChange={(e: any) => setEditFields({ ...editFields, job_title: e.target.value })} />
                ) : <Text size="2" className="block">{contact.job_title || "—"}</Text>}
              </div>
              {contact.address_tenure_tags && contact.address_tenure_tags.length > 0 && (
                <div>
                  <Text size="1" style={{ color: "var(--gray-9)" }}>Mailing Addresses</Text>
                  <div className="flex flex-col gap-1.5 mt-1">
                    {contact.address_tenure_tags.map((a, i) => (
                      <div key={i} className="flex items-center justify-between gap-2 text-[13px]">
                        <span>{a.address_unit.split("|").slice(1, 5).filter(Boolean).join(" ")}</span>
                        {a.tag && (
                          <Badge
                            size="1"
                            color={a.tag.state === "active" ? "jade" : "gray"}
                            variant="soft"
                          >
                            {a.tag.state === "active"
                              ? `Active · ${a.tag.display_name}`
                              : `Last seen ${a.last_seen.slice(0, 10)}`}
                          </Badge>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Datanyze Contact Details */}
          {contact.datanyze_contacts && (contact.datanyze_contacts.emails?.length > 0 || contact.datanyze_contacts.phones?.length > 0) && (
            <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
              <div className="flex items-center gap-1.5 mb-3">
                <Lightning size={14} weight="fill" style={{ color: "var(--amber-9)" }} />
                <Text size="3" weight="medium">Datanyze</Text>
              </div>
              <div className="flex flex-col gap-3 text-[14px]">
                {contact.datanyze_contacts.emails?.map((e, i) => (
                  <div key={`dn-email-${i}`}>
                    <Text size="1" style={{ color: "var(--gray-9)" }}>Email{contact.datanyze_contacts!.emails.length > 1 ? ` ${i + 1}` : ""} ({e.type})</Text>
                    <a href={`mailto:${e.value}`} className="block no-underline" style={{ color: "var(--accent-11)" }}>
                      {e.value}
                    </a>
                  </div>
                ))}
                {contact.datanyze_contacts.phones?.map((p, i) => (
                  <div key={`dn-phone-${i}`}>
                    <Text size="1" style={{ color: "var(--gray-9)" }}>Phone{contact.datanyze_contacts!.phones.length > 1 ? ` ${i + 1}` : ""} ({p.type})</Text>
                    <a href={`tel:${p.value}`} className="block no-underline" style={{ color: "var(--accent-11)" }}>
                      {formatPhone(p.value)}
                    </a>
                  </div>
                ))}
              </div>
            </div>
          )}

          <CareerHistoryTile
            realtrack={contact.career_history}
            linkedIn={contact.work_history}
            totalSpvCount={affiliatedGroups.length}
            onRowClick={(stem) => setDrawerStem(stem)}
            onViewSpvs={() => setShowConsolidate(true)}
          />

          {/* Stats */}
          <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
            <Text size="3" weight="medium" className="mb-3 block">Activity</Text>
            <div className="flex flex-col gap-2 text-[14px]">
              <div className="flex justify-between">
                <Text size="2" style={{ color: "var(--gray-9)" }}>Transactions</Text>
                <Text size="2" weight="medium">{contact.transaction_count}</Text>
              </div>
              <div className="flex justify-between">
                <Text size="2" style={{ color: "var(--gray-9)" }}>First Seen</Text>
                <Text size="2">{formatDate(contact.first_seen_date)}</Text>
              </div>
              <div className="flex justify-between">
                <Text size="2" style={{ color: "var(--gray-9)" }}>Last Seen</Text>
                <Text size="2">{formatDate(contact.last_seen_date)}</Text>
              </div>
              {contact.last_engaged_date && (
                <div className="flex justify-between">
                  <Text size="2" style={{ color: "var(--gray-9)" }}>Last Engaged</Text>
                  <Text size="2" style={{ color: "var(--accent-11)" }}>{formatDate(contact.last_engaged_date)}</Text>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Right: Hero map + Property Footprint + Transactions */}
        <div className="col-span-2 flex flex-col gap-6">
          {contact.current_employer && contact.current_employer.brand_stem ? (
            <>
              <PortfolioFootprintMap
                stem={contact.current_employer.brand_stem}
                displayName={contact.current_employer.display_name || contact.current_employer.brand_stem}
                height={380}
              />
              <TenuredPropertyFootprintMap
                contactId={contact.id}
                height={260}
              />
            </>
          ) : (
            propertyHistory.length > 0 && (
              <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
                <Text size="3" weight="medium" className="mb-3 block">
                  Property Footprint ({propertyHistory.length})
                </Text>
                <PropertyMiniMap
                  properties={propertyHistory}
                  height={300}
                  onPropertyClick={(pid) => navigate(`/properties/${pid}`)}
                />
              </div>
            )
          )}

          <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
            <Text size="3" weight="medium" className="mb-3 block">Transaction History ({contact.transactions.length})</Text>
            {contact.transactions.length === 0 ? (
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
                      <th className="text-left py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Tenure</th>
                      <th className="text-right py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Price</th>
                      <th className="text-right py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Ownership</th>
                      <th className="w-8 py-2" />
                    </tr>
                  </thead>
                  <tbody>
                    {(txnsExpanded ? contact.transactions : contact.transactions.slice(0, 5)).map((t) => (
                      <tr key={t.source_id} className="border-b border-[var(--gray-4)] hover:bg-[var(--gray-a2)] cursor-pointer"
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
                      </tr>
                    ))}
                  </tbody>
                </table>
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
