/**
 * SellOpportunityDetailPage — detail view for a sell opportunity,
 * showing property info, seller info, activities, and matching buy mandates.
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
  Buildings,
  User,
  Trash,
  Warning,
  Handshake,
} from "@phosphor-icons/react";
import { fetchApi, mutateApi } from "../api/client";
import { formatCurrency, formatDate } from "../lib/utils";
import {
  sellOppStatusColor,
  sellOppStatusLabel,
  buyMandateStatusColor,
  buyMandateStatusLabel,
} from "../lib/theme";
import type { SellOpportunityDetail, MatchingMandate } from "../types";
import ActivityFeed from "../components/crm/ActivityFeed";

export default function SellOpportunityDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [opp, setOpp] = useState<SellOpportunityDetail | null>(null);

  const load = () => {
    if (!id) return;
    fetchApi<SellOpportunityDetail>(`/sell-opportunities/${id}`).then(setOpp);
  };

  useEffect(load, [id]);

  const handleStatusChange = async (newStatus: string) => {
    if (!id) return;
    await mutateApi(`/sell-opportunities/${id}`, "PATCH", { status: newStatus });
    load();
  };

  const handleDelete = async () => {
    if (!id || !confirm("Delete this sell opportunity?")) return;
    await mutateApi(`/sell-opportunities/${id}`, "DELETE");
    navigate("/opportunities?tab=sell");
  };

  if (!opp) {
    return (
      <div className="p-6">
        <Text size="2" style={{ color: "var(--gray-9)" }}>Loading...</Text>
      </div>
    );
  }

  return (
    <div className="p-6 max-w-[1200px]">
      {/* Back link */}
      <Link
        to="/opportunities?tab=sell"
        className="inline-flex items-center gap-1 mb-4 text-sm no-underline"
        style={{ color: "var(--accent-11)" }}
      >
        <ArrowLeft size={14} />
        Sell Opportunities
      </Link>

      {/* Header */}
      <div className="flex items-start justify-between mb-6">
        <div>
          <div className="flex items-center gap-3 mb-1">
            <Heading size="6">{opp.display_address}</Heading>
            <Badge size="2" color={sellOppStatusColor(opp.status)} variant="soft">
              {sellOppStatusLabel(opp.status)}
            </Badge>
            {opp.is_stale === 1 && (
              <Badge size="1" color="tomato" variant="soft">
                <Warning size={12} weight="fill" className="mr-0.5" />
                Stale ({opp.days_since_activity}d)
              </Badge>
            )}
          </div>
          <Text size="2" style={{ color: "var(--gray-9)" }}>
            {opp.id} · {opp.city}{opp.region ? `, ${opp.region}` : ""}
          </Text>
        </div>

        <div className="flex items-center gap-2">
          <Select.Root value={opp.status} onValueChange={handleStatusChange}>
            <Select.Trigger variant="soft" />
            <Select.Content>
              <Select.Item value="active">Active</Select.Item>
              <Select.Item value="on_hold">On Hold</Select.Item>
              <Select.Item value="matched">Matched</Select.Item>
              <Select.Item value="closed_won">Closed Won</Select.Item>
              <Select.Item value="closed_lost">Closed Lost</Select.Item>
            </Select.Content>
          </Select.Root>
          <Button variant="soft" color="red" size="2" onClick={handleDelete}>
            <Trash size={14} />
          </Button>
        </div>
      </div>

      {/* Main grid */}
      <div className="grid grid-cols-3 gap-5">
        {/* Left column — Property & Seller Info */}
        <div className="col-span-2 space-y-5">
          {/* Property card */}
          <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
            <div className="flex items-center gap-2 mb-3">
              <Buildings size={18} style={{ color: "var(--gray-9)" }} />
              <Heading size="3">Property</Heading>
            </div>
            <DataList.Root>
              <DataList.Item>
                <DataList.Label>Address</DataList.Label>
                <DataList.Value>
                  <Link
                    to={`/properties/${opp.property_id}`}
                    className="no-underline"
                    style={{ color: "var(--accent-11)" }}
                  >
                    {opp.display_address}
                  </Link>
                </DataList.Value>
              </DataList.Item>
              <DataList.Item>
                <DataList.Label>City</DataList.Label>
                <DataList.Value>{opp.city || "—"}</DataList.Value>
              </DataList.Item>
              <DataList.Item>
                <DataList.Label>Region</DataList.Label>
                <DataList.Value>{opp.region || "—"}</DataList.Value>
              </DataList.Item>
              <DataList.Item>
                <DataList.Label>Asset Class</DataList.Label>
                <DataList.Value>{opp.asset_class || "—"}</DataList.Value>
              </DataList.Item>
              <DataList.Item>
                <DataList.Label>Last Sale Price</DataList.Label>
                <DataList.Value>{formatCurrency(opp.most_recent_sale_price)}</DataList.Value>
              </DataList.Item>
              <DataList.Item>
                <DataList.Label>Deal Value</DataList.Label>
                <DataList.Value>
                  <Text weight="bold">{formatCurrency(opp.deal_value)}</Text>
                </DataList.Value>
              </DataList.Item>
            </DataList.Root>
          </div>

          {/* Seller card */}
          <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
            <div className="flex items-center gap-2 mb-3">
              <User size={18} style={{ color: "var(--gray-9)" }} />
              <Heading size="3">Seller</Heading>
            </div>
            <DataList.Root>
              {opp.seller_contact_name && (
                <>
                  <DataList.Item>
                    <DataList.Label>Contact</DataList.Label>
                    <DataList.Value>
                      <Link
                        to={`/contacts/${opp.seller_contact_id}`}
                        className="no-underline"
                        style={{ color: "var(--accent-11)" }}
                      >
                        {opp.seller_contact_name}
                      </Link>
                    </DataList.Value>
                  </DataList.Item>
                  {opp.seller_contact_phone && (
                    <DataList.Item>
                      <DataList.Label>Phone</DataList.Label>
                      <DataList.Value>{opp.seller_contact_phone}</DataList.Value>
                    </DataList.Item>
                  )}
                  {opp.seller_contact_email && (
                    <DataList.Item>
                      <DataList.Label>Email</DataList.Label>
                      <DataList.Value>{opp.seller_contact_email}</DataList.Value>
                    </DataList.Item>
                  )}
                </>
              )}
              {opp.seller_group_name && (
                <DataList.Item>
                  <DataList.Label>Group</DataList.Label>
                  <DataList.Value>
                    <Link
                      to={`/groups/${opp.seller_group_id}`}
                      className="no-underline"
                      style={{ color: "var(--accent-11)" }}
                    >
                      {opp.seller_group_name}
                    </Link>
                  </DataList.Value>
                </DataList.Item>
              )}
              {!opp.seller_contact_name && !opp.seller_group_name && (
                <DataList.Item>
                  <DataList.Label>Seller</DataList.Label>
                  <DataList.Value>
                    <Text style={{ color: "var(--gray-9)" }}>No seller assigned</Text>
                  </DataList.Value>
                </DataList.Item>
              )}
            </DataList.Root>
          </div>

          {/* Matching Buy Mandates */}
          {opp.matching_mandates && opp.matching_mandates.length > 0 && (
            <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
              <div className="flex items-center gap-2 mb-3">
                <Handshake size={18} style={{ color: "var(--jade-9)" }} />
                <Heading size="3">Matching Buy Mandates</Heading>
                <Badge size="1" variant="soft" color="jade">{opp.matching_mandates.length}</Badge>
              </div>
              <div className="space-y-2">
                {opp.matching_mandates.map((m: MatchingMandate) => (
                  <div
                    key={m.id}
                    onClick={() => navigate(`/opportunities/buy/${m.id}`)}
                    className="flex items-center justify-between p-3 rounded-lg border border-[var(--gray-4)] cursor-pointer hover:bg-[var(--gray-2)] transition-colors"
                  >
                    <div>
                      <Text size="2" weight="medium">
                        {m.contact_name || m.group_name || m.id}
                      </Text>
                      <Text size="1" className="block" style={{ color: "var(--gray-9)" }}>
                        {m.id}
                      </Text>
                    </div>
                    <div className="flex items-center gap-2">
                      <Badge size="1" color={buyMandateStatusColor(m.status)} variant="soft">
                        {buyMandateStatusLabel(m.status)}
                      </Badge>
                      <Badge size="1" color="jade" variant="outline">
                        {Math.round(m.match_score * 100)}% match
                      </Badge>
                    </div>
                  </div>
                ))}
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
                <DataList.Value>{opp.owner || "—"}</DataList.Value>
              </DataList.Item>
              <DataList.Item>
                <DataList.Label>Decay Window</DataList.Label>
                <DataList.Value>{opp.decay_days} days</DataList.Value>
              </DataList.Item>
              <DataList.Item>
                <DataList.Label>Last Activity</DataList.Label>
                <DataList.Value>
                  <Text style={{ color: opp.is_stale ? "var(--tomato-11)" : undefined }}>
                    {opp.days_since_activity}d ago
                  </Text>
                </DataList.Value>
              </DataList.Item>
              <DataList.Item>
                <DataList.Label>Created</DataList.Label>
                <DataList.Value>{formatDate(opp.created_at)}</DataList.Value>
              </DataList.Item>
            </DataList.Root>
            {opp.notes && (
              <>
                <Separator className="my-3" />
                <Text size="2" style={{ color: "var(--gray-11)" }}>
                  {opp.notes}
                </Text>
              </>
            )}
          </div>

          {/* Activity Feed */}
          <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
            <ActivityFeed
              activities={opp.activities || []}
              entityType="sell_opportunity"
              entityId={opp.id}
              onActivityLogged={load}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
