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

export default function BuyMandateDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [mandate, setMandate] = useState<BuyMandateDetail | null>(null);

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
            <div className="flex items-center gap-2 mb-3">
              <MapPin size={18} style={{ color: "var(--gray-9)" }} />
              <Heading size="3">Search Criteria</Heading>
            </div>
            <DataList.Root>
              {criteria.asset_classes && criteria.asset_classes.length > 0 && (
                <DataList.Item>
                  <DataList.Label>Asset Classes</DataList.Label>
                  <DataList.Value>
                    <div className="flex gap-1 flex-wrap">
                      {criteria.asset_classes.map((ac) => (
                        <Badge key={ac} size="1" variant="soft">{ac}</Badge>
                      ))}
                    </div>
                  </DataList.Value>
                </DataList.Item>
              )}
              {criteria.asset_subclasses && criteria.asset_subclasses.length > 0 && (
                <DataList.Item>
                  <DataList.Label>Subclasses</DataList.Label>
                  <DataList.Value>
                    <div className="flex gap-1 flex-wrap">
                      {criteria.asset_subclasses.map((sc) => (
                        <Badge key={sc} size="1" variant="outline">{sc}</Badge>
                      ))}
                    </div>
                  </DataList.Value>
                </DataList.Item>
              )}
              {criteria.regions && criteria.regions.length > 0 && (
                <DataList.Item>
                  <DataList.Label>Regions</DataList.Label>
                  <DataList.Value>{criteria.regions.join(", ")}</DataList.Value>
                </DataList.Item>
              )}
              {criteria.cities && criteria.cities.length > 0 && (
                <DataList.Item>
                  <DataList.Label>Cities</DataList.Label>
                  <DataList.Value>{criteria.cities.join(", ")}</DataList.Value>
                </DataList.Item>
              )}
              {(criteria.price_min || criteria.price_max) && (
                <DataList.Item>
                  <DataList.Label>Price Range</DataList.Label>
                  <DataList.Value>
                    {criteria.price_min ? formatCurrency(criteria.price_min) : "Any"} – {criteria.price_max ? formatCurrency(criteria.price_max) : "Any"}
                  </DataList.Value>
                </DataList.Item>
              )}
              {(criteria.sqft_min || criteria.sqft_max) && (
                <DataList.Item>
                  <DataList.Label>Size (sqft)</DataList.Label>
                  <DataList.Value>
                    {criteria.sqft_min?.toLocaleString() || "Any"} – {criteria.sqft_max?.toLocaleString() || "Any"}
                  </DataList.Value>
                </DataList.Item>
              )}
              {criteria.market_type && (
                <DataList.Item>
                  <DataList.Label>Market Type</DataList.Label>
                  <DataList.Value>{criteria.market_type}</DataList.Value>
                </DataList.Item>
              )}
              {!criteria.asset_classes?.length && !criteria.regions?.length && !criteria.price_min && !criteria.price_max && (
                <DataList.Item>
                  <DataList.Label>Criteria</DataList.Label>
                  <DataList.Value>
                    <Text style={{ color: "var(--gray-9)" }}>No criteria set</Text>
                  </DataList.Value>
                </DataList.Item>
              )}
            </DataList.Root>
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
                <Text size="2" style={{ color: "var(--gray-11)" }}>
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
    </div>
  );
}
