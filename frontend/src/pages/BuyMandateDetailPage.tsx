/**
 * BuyMandateDetailPage — detail view for a buy mandate,
 * showing criteria, buyer info, activities, and matching properties.
 */
import { useState, useEffect } from "react";
import { Link, useParams, useNavigate } from "react-router-dom";
import {
  Heading,
  Text,
  Badge,
  Button,
  Select,
  DataList,
  Separator,
} from "@radix-ui/themes";
import {
  ArrowLeft,
  User,
  Trash,
  Warning,
  Buildings,
  MapPin,
  PencilSimple,
  CurrencyDollar,
  ChartLineUp,
  Clock,
  Users,
  Ruler,
} from "@phosphor-icons/react";
import { fetchApi, mutateApi } from "../api/client";
import { formatCurrency, formatDate } from "../lib/utils";
import {
  buyMandateStatusColor,
  buyMandateStatusLabel,
  sellOppStatusColor,
  sellOppStatusLabel,
} from "../lib/theme";
import type { BuyMandateDetail, MatchingProperty } from "../types";
import ActivityFeed from "../components/crm/ActivityFeed";
import CreateBuyMandateDrawer from "../components/crm/CreateBuyMandateDrawer";

// ── Label maps for display ──

const TENANT_QUALITY_LABELS: Record<string, string> = {
  national_credit: "National Credit (AAA)",
  regional_credit: "Regional Credit",
  local: "Local",
  any: "Any",
};

const OCCUPANCY_LABELS: Record<string, string> = {
  single: "Single Tenant",
  multi: "Multi-Tenant",
  either: "Either",
};

const ANCHORED_LABELS: Record<string, string> = {
  grocery: "Grocery Anchored",
  big_box: "Big Box Anchored",
  none: "No Preference",
};

const MARKET_TIER_LABELS: Record<string, string> = {
  primary: "Primary",
  secondary: "Secondary",
  tertiary: "Tertiary",
};

const STRATEGY_LABELS: Record<string, string> = {
  core: "Core",
  core_plus: "Core-Plus",
  value_add: "Value-Add",
  opportunistic: "Opportunistic",
};

const VACANCY_LABELS: Record<string, string> = {
  fully_leased: "Fully Leased Only",
  some_vacancy: "Some Vacancy OK",
  high_vacancy: "High Vacancy / Value-Add",
};

const PRIORITY_LABELS: Record<string, string> = {
  primary: "Primary",
  secondary: "Secondary",
  exploratory: "Exploratory",
};

const PRIORITY_COLORS: Record<string, "jade" | "blue" | "gray"> = {
  primary: "jade",
  secondary: "blue",
  exploratory: "gray",
};

const TIMELINE_LABELS: Record<string, string> = {
  immediate: "Immediate (0–3 months)",
  near_term: "Near-term (3–6 months)",
  medium: "Medium (6–12 months)",
  long_term: "Long-term (12+ months)",
};

export default function BuyMandateDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [mandate, setMandate] = useState<BuyMandateDetail | null>(null);
  const [editDrawerOpen, setEditDrawerOpen] = useState(false);

  const load = () => {
    if (!id) return;
    fetchApi<BuyMandateDetail>(`/buy-mandates/${id}`).then(setMandate);
  };

  useEffect(load, [id]);

  const handleStatusChange = async (newStatus: string) => {
    if (!id) return;
    await mutateApi(`/buy-mandates/${id}`, "PATCH", { status: newStatus });
    load();
  };

  const handleDelete = async () => {
    if (!id || !confirm("Delete this buy mandate?")) return;
    await mutateApi(`/buy-mandates/${id}`, "DELETE");
    navigate("/opportunities?tab=buy");
  };

  if (!mandate) {
    return (
      <div className="p-6">
        <Text size="2" style={{ color: "var(--gray-9)" }}>Loading...</Text>
      </div>
    );
  }

  const criteria = mandate.criteria || {};
  const hasCriteria = Object.keys(criteria).length > 0;

  return (
    <div className="p-6 max-w-[1200px]">
      {/* Back link */}
      <Link
        to="/opportunities?tab=buy"
        className="inline-flex items-center gap-1 mb-4 text-sm no-underline"
        style={{ color: "var(--accent-11)" }}
      >
        <ArrowLeft size={14} />
        Buy Mandates
      </Link>

      {/* Header */}
      <div className="flex items-start justify-between mb-6">
        <div>
          <div className="flex items-center gap-3 mb-1">
            <Heading size="6">
              {mandate.contact_name || mandate.group_name || "Buy Mandate"}
            </Heading>
            <Badge size="2" color={buyMandateStatusColor(mandate.status)} variant="soft">
              {buyMandateStatusLabel(mandate.status)}
            </Badge>
            {criteria.priority && (
              <Badge size="1" color={PRIORITY_COLORS[criteria.priority] || "gray"} variant="outline">
                {PRIORITY_LABELS[criteria.priority] || criteria.priority}
              </Badge>
            )}
            {mandate.is_stale === 1 && (
              <Badge size="1" color="tomato" variant="soft">
                <Warning size={12} weight="fill" className="mr-0.5" />
                Stale ({mandate.days_since_activity}d)
              </Badge>
            )}
          </div>
          <Text size="2" style={{ color: "var(--gray-9)" }}>
            {mandate.id}
          </Text>
        </div>

        <div className="flex items-center gap-2">
          <Button variant="soft" size="2" onClick={() => setEditDrawerOpen(true)}>
            <PencilSimple size={14} />
            Edit Criteria
          </Button>
          <Select.Root value={mandate.status} onValueChange={handleStatusChange}>
            <Select.Trigger variant="soft" />
            <Select.Content>
              <Select.Item value="active">Active</Select.Item>
              <Select.Item value="on_hold">On Hold</Select.Item>
              <Select.Item value="fulfilled">Fulfilled</Select.Item>
            </Select.Content>
          </Select.Root>
          <Button variant="soft" color="red" size="2" onClick={handleDelete}>
            <Trash size={14} />
          </Button>
        </div>
      </div>

      {/* Main grid */}
      <div className="grid grid-cols-3 gap-5">
        {/* Left column — Criteria, Buyer, Matches */}
        <div className="col-span-2 space-y-5">
          {/* Criteria card */}
          <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <MapPin size={18} style={{ color: "var(--gray-9)" }} />
                <Heading size="3">Search Criteria</Heading>
              </div>
            </div>

            {!hasCriteria ? (
              <div className="py-4 text-center">
                <Text size="2" style={{ color: "var(--gray-9)" }}>
                  No criteria set.{" "}
                </Text>
                <button
                  className="text-sm no-underline"
                  style={{ color: "var(--accent-11)" }}
                  onClick={() => setEditDrawerOpen(true)}
                >
                  Add criteria
                </button>
              </div>
            ) : (
              <div className="space-y-4">
                {/* Property Type */}
                {(criteria.asset_classes?.length || criteria.asset_subclasses?.length || criteria.zoning_notes) && (
                  <div>
                    <Text size="1" weight="medium" className="block mb-2" style={{ color: "var(--gray-9)" }}>
                      <Buildings size={12} className="inline mr-1" style={{ verticalAlign: "text-bottom" }} />
                      Property Type
                    </Text>
                    <DataList.Root size="2">
                      {criteria.asset_classes && criteria.asset_classes.length > 0 && (
                        <DataList.Item>
                          <DataList.Label minWidth="120px">Asset Classes</DataList.Label>
                          <DataList.Value>
                            <div className="flex gap-1 flex-wrap">
                              {criteria.asset_classes.map((ac) => (
                                <Badge key={ac} size="1" variant="soft" color="jade">{ac}</Badge>
                              ))}
                            </div>
                          </DataList.Value>
                        </DataList.Item>
                      )}
                      {criteria.asset_subclasses && criteria.asset_subclasses.length > 0 && (
                        <DataList.Item>
                          <DataList.Label minWidth="120px">Subclasses</DataList.Label>
                          <DataList.Value>
                            <div className="flex gap-1 flex-wrap">
                              {criteria.asset_subclasses.map((sc) => (
                                <Badge key={sc} size="1" variant="outline">{sc.replace(/_/g, " ")}</Badge>
                              ))}
                            </div>
                          </DataList.Value>
                        </DataList.Item>
                      )}
                      {criteria.zoning_notes && (
                        <DataList.Item>
                          <DataList.Label minWidth="120px">Zoning</DataList.Label>
                          <DataList.Value>{criteria.zoning_notes}</DataList.Value>
                        </DataList.Item>
                      )}
                    </DataList.Root>
                  </div>
                )}

                {/* Tenant Preferences */}
                {(criteria.tenant_quality || criteria.tenant_categories?.length || criteria.occupancy_type || criteria.anchored_preference) && (
                  <div>
                    <Text size="1" weight="medium" className="block mb-2" style={{ color: "var(--gray-9)" }}>
                      <Users size={12} className="inline mr-1" style={{ verticalAlign: "text-bottom" }} />
                      Tenant Preferences
                    </Text>
                    <DataList.Root size="2">
                      {criteria.tenant_quality && (
                        <DataList.Item>
                          <DataList.Label minWidth="120px">Quality</DataList.Label>
                          <DataList.Value>{TENANT_QUALITY_LABELS[criteria.tenant_quality] || criteria.tenant_quality}</DataList.Value>
                        </DataList.Item>
                      )}
                      {criteria.tenant_categories && criteria.tenant_categories.length > 0 && (
                        <DataList.Item>
                          <DataList.Label minWidth="120px">Categories</DataList.Label>
                          <DataList.Value>
                            <div className="flex gap-1 flex-wrap">
                              {criteria.tenant_categories.map((tc) => (
                                <Badge key={tc} size="1" variant="outline">{tc.replace(/_/g, " ")}</Badge>
                              ))}
                            </div>
                          </DataList.Value>
                        </DataList.Item>
                      )}
                      {criteria.occupancy_type && (
                        <DataList.Item>
                          <DataList.Label minWidth="120px">Occupancy</DataList.Label>
                          <DataList.Value>{OCCUPANCY_LABELS[criteria.occupancy_type] || criteria.occupancy_type}</DataList.Value>
                        </DataList.Item>
                      )}
                      {criteria.anchored_preference && (
                        <DataList.Item>
                          <DataList.Label minWidth="120px">Anchored</DataList.Label>
                          <DataList.Value>{ANCHORED_LABELS[criteria.anchored_preference] || criteria.anchored_preference}</DataList.Value>
                        </DataList.Item>
                      )}
                    </DataList.Root>
                  </div>
                )}

                {/* Location */}
                {(criteria.regions?.length || criteria.cities?.length || criteria.market_tiers?.length) && (
                  <div>
                    <Text size="1" weight="medium" className="block mb-2" style={{ color: "var(--gray-9)" }}>
                      <MapPin size={12} className="inline mr-1" style={{ verticalAlign: "text-bottom" }} />
                      Location
                    </Text>
                    <DataList.Root size="2">
                      {criteria.market_tiers && criteria.market_tiers.length > 0 && (
                        <DataList.Item>
                          <DataList.Label minWidth="120px">Market Tiers</DataList.Label>
                          <DataList.Value>
                            <div className="flex gap-1">
                              {criteria.market_tiers.map((t) => (
                                <Badge key={t} size="1" variant="soft">{MARKET_TIER_LABELS[t] || t}</Badge>
                              ))}
                            </div>
                          </DataList.Value>
                        </DataList.Item>
                      )}
                      {criteria.regions && criteria.regions.length > 0 && (
                        <DataList.Item>
                          <DataList.Label minWidth="120px">Regions</DataList.Label>
                          <DataList.Value>{criteria.regions.join(", ")}</DataList.Value>
                        </DataList.Item>
                      )}
                      {criteria.cities && criteria.cities.length > 0 && (
                        <DataList.Item>
                          <DataList.Label minWidth="120px">Cities</DataList.Label>
                          <DataList.Value>{criteria.cities.join(", ")}</DataList.Value>
                        </DataList.Item>
                      )}
                    </DataList.Root>
                  </div>
                )}

                {/* Financial */}
                {(criteria.price_min || criteria.price_max || criteria.cap_rate_min || criteria.cap_rate_max || criteria.noi_min || criteria.noi_max) && (
                  <div>
                    <Text size="1" weight="medium" className="block mb-2" style={{ color: "var(--gray-9)" }}>
                      <CurrencyDollar size={12} className="inline mr-1" style={{ verticalAlign: "text-bottom" }} />
                      Financial
                    </Text>
                    <DataList.Root size="2">
                      {(criteria.price_min || criteria.price_max) && (
                        <DataList.Item>
                          <DataList.Label minWidth="120px">Price Range</DataList.Label>
                          <DataList.Value>
                            {criteria.price_min ? formatCurrency(criteria.price_min) : "Any"} – {criteria.price_max ? formatCurrency(criteria.price_max) : "Any"}
                          </DataList.Value>
                        </DataList.Item>
                      )}
                      {(criteria.cap_rate_min || criteria.cap_rate_max) && (
                        <DataList.Item>
                          <DataList.Label minWidth="120px">Cap Rate</DataList.Label>
                          <DataList.Value>
                            {criteria.cap_rate_min ?? "Any"}% – {criteria.cap_rate_max ?? "Any"}%
                          </DataList.Value>
                        </DataList.Item>
                      )}
                      {(criteria.noi_min || criteria.noi_max) && (
                        <DataList.Item>
                          <DataList.Label minWidth="120px">NOI Range</DataList.Label>
                          <DataList.Value>
                            {criteria.noi_min ? formatCurrency(criteria.noi_min) : "Any"} – {criteria.noi_max ? formatCurrency(criteria.noi_max) : "Any"}
                          </DataList.Value>
                        </DataList.Item>
                      )}
                    </DataList.Root>
                  </div>
                )}

                {/* Size */}
                {(criteria.sqft_min || criteria.sqft_max || criteria.acreage_min || criteria.acreage_max || criteria.unit_count_min || criteria.unit_count_max) && (
                  <div>
                    <Text size="1" weight="medium" className="block mb-2" style={{ color: "var(--gray-9)" }}>
                      <Ruler size={12} className="inline mr-1" style={{ verticalAlign: "text-bottom" }} />
                      Size
                    </Text>
                    <DataList.Root size="2">
                      {(criteria.sqft_min || criteria.sqft_max) && (
                        <DataList.Item>
                          <DataList.Label minWidth="120px">Building Size</DataList.Label>
                          <DataList.Value>
                            {criteria.sqft_min?.toLocaleString() || "Any"} – {criteria.sqft_max?.toLocaleString() || "Any"} sqft
                          </DataList.Value>
                        </DataList.Item>
                      )}
                      {(criteria.acreage_min || criteria.acreage_max) && (
                        <DataList.Item>
                          <DataList.Label minWidth="120px">Acreage</DataList.Label>
                          <DataList.Value>
                            {criteria.acreage_min || "Any"} – {criteria.acreage_max || "Any"} acres
                          </DataList.Value>
                        </DataList.Item>
                      )}
                      {(criteria.unit_count_min || criteria.unit_count_max) && (
                        <DataList.Item>
                          <DataList.Label minWidth="120px">Units</DataList.Label>
                          <DataList.Value>
                            {criteria.unit_count_min || "Any"} – {criteria.unit_count_max || "Any"} units
                          </DataList.Value>
                        </DataList.Item>
                      )}
                    </DataList.Root>
                  </div>
                )}

                {/* Investment Profile */}
                {(criteria.investment_strategy || criteria.vacancy_tolerance) && (
                  <div>
                    <Text size="1" weight="medium" className="block mb-2" style={{ color: "var(--gray-9)" }}>
                      <ChartLineUp size={12} className="inline mr-1" style={{ verticalAlign: "text-bottom" }} />
                      Investment Profile
                    </Text>
                    <DataList.Root size="2">
                      {criteria.investment_strategy && (
                        <DataList.Item>
                          <DataList.Label minWidth="120px">Strategy</DataList.Label>
                          <DataList.Value>{STRATEGY_LABELS[criteria.investment_strategy] || criteria.investment_strategy}</DataList.Value>
                        </DataList.Item>
                      )}
                      {criteria.vacancy_tolerance && (
                        <DataList.Item>
                          <DataList.Label minWidth="120px">Vacancy</DataList.Label>
                          <DataList.Value>{VACANCY_LABELS[criteria.vacancy_tolerance] || criteria.vacancy_tolerance}</DataList.Value>
                        </DataList.Item>
                      )}
                    </DataList.Root>
                  </div>
                )}

                {/* Timeline */}
                {criteria.timeline && (
                  <div>
                    <Text size="1" weight="medium" className="block mb-2" style={{ color: "var(--gray-9)" }}>
                      <Clock size={12} className="inline mr-1" style={{ verticalAlign: "text-bottom" }} />
                      Timeline
                    </Text>
                    <DataList.Root size="2">
                      <DataList.Item>
                        <DataList.Label minWidth="120px">Timeline</DataList.Label>
                        <DataList.Value>{TIMELINE_LABELS[criteria.timeline] || criteria.timeline}</DataList.Value>
                      </DataList.Item>
                    </DataList.Root>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Buyer card */}
          <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
            <div className="flex items-center gap-2 mb-3">
              <User size={18} style={{ color: "var(--gray-9)" }} />
              <Heading size="3">Buyer</Heading>
            </div>
            <DataList.Root>
              {mandate.contact_name && (
                <>
                  <DataList.Item>
                    <DataList.Label>Contact</DataList.Label>
                    <DataList.Value>
                      <Link
                        to={`/contacts/${mandate.contact_id}`}
                        className="no-underline"
                        style={{ color: "var(--accent-11)" }}
                      >
                        {mandate.contact_name}
                      </Link>
                    </DataList.Value>
                  </DataList.Item>
                  {mandate.contact_phone && (
                    <DataList.Item>
                      <DataList.Label>Phone</DataList.Label>
                      <DataList.Value>{mandate.contact_phone}</DataList.Value>
                    </DataList.Item>
                  )}
                  {mandate.contact_email && (
                    <DataList.Item>
                      <DataList.Label>Email</DataList.Label>
                      <DataList.Value>{mandate.contact_email}</DataList.Value>
                    </DataList.Item>
                  )}
                </>
              )}
              {mandate.group_name && (
                <DataList.Item>
                  <DataList.Label>Group</DataList.Label>
                  <DataList.Value>
                    <Link
                      to={`/groups/${mandate.group_id}`}
                      className="no-underline"
                      style={{ color: "var(--accent-11)" }}
                    >
                      {mandate.group_name}
                    </Link>
                  </DataList.Value>
                </DataList.Item>
              )}
            </DataList.Root>
          </div>

          {/* Matching Properties */}
          {mandate.matching_properties && mandate.matching_properties.length > 0 && (
            <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
              <div className="flex items-center gap-2 mb-3">
                <Buildings size={18} style={{ color: "var(--jade-9)" }} />
                <Heading size="3">Matching Properties</Heading>
                <Badge size="1" variant="soft" color="jade">{mandate.matching_properties.length}</Badge>
              </div>
              <div className="rounded-lg border border-[var(--gray-4)] overflow-hidden">
                <table className="w-full">
                  <thead>
                    <tr className="bg-[var(--gray-2)]">
                      <th className="text-left px-3 py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Property</th>
                      <th className="text-left px-3 py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Region</th>
                      <th className="text-left px-3 py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Asset Class</th>
                      <th className="text-right px-3 py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Price</th>
                      <th className="text-right px-3 py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>NOI</th>
                      <th className="text-right px-3 py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Cap Rate</th>
                      <th className="text-left px-3 py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Sell Opp</th>
                    </tr>
                  </thead>
                  <tbody>
                    {mandate.matching_properties.map((p: MatchingProperty) => (
                      <tr
                        key={p.id}
                        onClick={() => navigate(`/properties/${p.id}`)}
                        className="cursor-pointer hover:bg-[var(--gray-2)] border-t border-[var(--gray-4)]"
                      >
                        <td className="px-3 py-2">
                          <Text size="2" weight="medium">{p.display_address}</Text>
                          {p.city && (
                            <Text size="1" className="block" style={{ color: "var(--gray-9)" }}>{p.city}</Text>
                          )}
                        </td>
                        <td className="px-3 py-2">
                          <Text size="2" style={{ color: "var(--gray-11)" }}>{p.region || "—"}</Text>
                        </td>
                        <td className="px-3 py-2">
                          <Text size="2" style={{ color: "var(--gray-11)" }}>{p.asset_class || "—"}</Text>
                        </td>
                        <td className="px-3 py-2 text-right">
                          <Text size="2">{formatCurrency(p.most_recent_sale_price)}</Text>
                        </td>
                        <td className="px-3 py-2 text-right">
                          <Text size="2" style={{ color: p.noi ? "var(--gray-12)" : "var(--gray-8)" }}>
                            {p.noi ? formatCurrency(p.noi) : "—"}
                          </Text>
                        </td>
                        <td className="px-3 py-2 text-right">
                          <Text size="2" style={{ color: p.implied_cap_rate ? "var(--gray-12)" : "var(--gray-8)" }}>
                            {p.implied_cap_rate ? `${p.implied_cap_rate}%` : "—"}
                          </Text>
                        </td>
                        <td className="px-3 py-2">
                          {p.sell_opportunity_id ? (
                            <Badge size="1" color={sellOppStatusColor(p.sell_opportunity_status || "active")} variant="soft">
                              {sellOppStatusLabel(p.sell_opportunity_status || "active")}
                            </Badge>
                          ) : (
                            <Text size="1" style={{ color: "var(--gray-9)" }}>—</Text>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>

        {/* Right column — Meta & Activities */}
        <div className="space-y-5">
          {/* Details card */}
          <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
            <Heading size="3" className="mb-3">Details</Heading>
            <DataList.Root>
              <DataList.Item>
                <DataList.Label>Owner</DataList.Label>
                <DataList.Value>{mandate.owner || "—"}</DataList.Value>
              </DataList.Item>
              <DataList.Item>
                <DataList.Label>Decay Window</DataList.Label>
                <DataList.Value>{mandate.decay_days} days</DataList.Value>
              </DataList.Item>
              <DataList.Item>
                <DataList.Label>Last Activity</DataList.Label>
                <DataList.Value>
                  <Text style={{ color: mandate.is_stale ? "var(--tomato-11)" : undefined }}>
                    {mandate.days_since_activity}d ago
                  </Text>
                </DataList.Value>
              </DataList.Item>
              <DataList.Item>
                <DataList.Label>Created</DataList.Label>
                <DataList.Value>{formatDate(mandate.created_at)}</DataList.Value>
              </DataList.Item>
            </DataList.Root>
            {mandate.notes && (
              <>
                <Separator className="my-3" />
                <Text size="2" style={{ color: "var(--gray-11)", whiteSpace: "pre-line" }}>
                  {mandate.notes}
                </Text>
              </>
            )}
          </div>

          {/* Activity Feed */}
          <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
            <ActivityFeed
              activities={mandate.activities || []}
              entityType="buy_mandate"
              entityId={mandate.id}
              onActivityLogged={load}
            />
          </div>
        </div>
      </div>

      {/* Edit drawer */}
      {editDrawerOpen && (
        <CreateBuyMandateDrawer
          contactId={mandate.contact_id || undefined}
          groupId={mandate.group_id || undefined}
          entityName={mandate.contact_name || mandate.group_name || ""}
          editMandateId={mandate.id}
          editCriteria={criteria}
          editNotes={mandate.notes || ""}
          onClose={() => {
            setEditDrawerOpen(false);
            load(); // Refresh after edit
          }}
        />
      )}
    </div>
  );
}
