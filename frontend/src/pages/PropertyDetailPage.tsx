/**
 * PropertyDetailPage V2 — Redesigned with workflow-driven hierarchy
 *
 * Layout:
 *   1. Header: Address + key stats (price, date, txn count) + brand badges
 *   2. Two columns: Owner card (left) + Satellite map with parcel (right)
 *   3. Photo gallery (if available)
 *   4. Transaction history (collapsible rows)
 *   5. Tabbed section: Site Details | Assessment | Tenants
 */

import { useState, useEffect, useMemo, lazy, Suspense } from "react";
import { Link, useParams, useNavigate, useLocation } from "react-router-dom";
import {
  Heading, Text, Badge, Button, Separator, Tabs,
  DataList, Callout,
} from "@radix-ui/themes";
import CreateSellOppDialog from "../components/crm/CreateSellOppDialog";
import {
  Copy, Phone, EnvelopeSimple, Buildings, CaretDown, CaretUp,
  MapPin, ArrowSquareOut, User, Tag, ChartBar, Image as ImageIcon, LinkedinLogo,
} from "@phosphor-icons/react";
import { fetchApi } from "../api/client";
import { formatCurrency, formatDate, formatPhone, computeOwnershipYears, formatOwnership, formatMailingAddress } from "../lib/utils";
import { categoryColor, propertyTypeColor, propertyTypeLabel, getRadixHex } from "../lib/theme";
import SourceHtmlButton from "../components/source/SourceHtmlButton";
import type { PropertyDetail, PropertyTransaction, GwSaleHistory } from "../types";

const MAPBOX_TOKEN = import.meta.env.VITE_MAPBOX_TOKEN;
const SATELLITE_STYLE = "mapbox://styles/mapbox/satellite-streets-v12";

// Lazy-load the satellite map so mapbox-gl doesn't block the page
const PropertySatelliteMap = lazy(() => import("../components/PropertySatelliteMap"));

// ============================================================
// Photo Gallery — hero + thumbnail strip with keyboard nav
// ============================================================

interface PhotoItem {
  url: string;
  sourceId: string;
  date: string | null;
  type: "street" | "aerial" | "standalone";
}

function PropertyPhotoGallery({ photos }: { photos: PhotoItem[] }) {
  const [selectedIdx, setSelectedIdx] = useState(0);
  const selected = photos[selectedIdx];

  // Keyboard navigation
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "ArrowRight") setSelectedIdx(i => Math.min(i + 1, photos.length - 1));
      if (e.key === "ArrowLeft") setSelectedIdx(i => Math.max(i - 1, 0));
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [photos.length]);

  // Group photos by transaction date for labelling
  const dateGroups = photos.reduce<Record<string, number>>((acc, p) => {
    const key = p.date || "Unknown";
    acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, {});
  const hasMultipleDates = Object.keys(dateGroups).length > 1;

  return (
    <div>
      <div className="flex items-center gap-2 mb-3">
        <ImageIcon size={16} style={{ color: "var(--gray-9)" }} />
        <Text size="2" weight="medium">Property Photos</Text>
        <Text size="1" style={{ color: "var(--gray-9)" }}>({photos.length})</Text>
        {hasMultipleDates && (
          <Text size="1" style={{ color: "var(--gray-9)" }}>
            from {Object.keys(dateGroups).length} transactions
          </Text>
        )}
      </div>

      {/* Compact gallery: selected image + thumbnail strip side by side */}
      <div className="flex gap-2 items-start">
        {/* Selected image */}
        <a href={selected.url} target="_blank" rel="noopener noreferrer" className="flex-shrink-0 relative rounded-lg overflow-hidden border border-[var(--gray-5)] bg-black">
          <img
            src={selected.url}
            alt={`Property photo ${selectedIdx + 1}`}
            className="object-cover"
            style={{ width: 280, height: 180 }}
          />
          <div className="absolute bottom-0 left-0 right-0 px-2 py-1" style={{ background: "linear-gradient(transparent, rgba(0,0,0,0.6))" }}>
            <Text style={{ color: "rgba(255,255,255,0.8)", fontSize: 10 }}>
              {selected.sourceId}{selected.date ? ` · ${formatDate(selected.date)}` : ""} — {selectedIdx + 1}/{photos.length}
            </Text>
          </div>
        </a>

        {/* Thumbnail grid */}
        {photos.length > 1 && (
          <div className="flex flex-wrap gap-1.5 overflow-hidden" style={{ maxHeight: 180 }}>
            {photos.map((p, i) => {
              const isActive = i === selectedIdx;
              return (
                <button
                  key={i}
                  onClick={() => setSelectedIdx(i)}
                  className="border-2 rounded overflow-hidden p-0 bg-transparent cursor-pointer transition-all flex-shrink-0"
                  style={{
                    borderColor: isActive ? "var(--jade-9)" : "transparent",
                    opacity: isActive ? 1 : 0.6,
                  }}
                >
                  <img
                    src={p.url}
                    alt={`Thumbnail ${i + 1}`}
                    className="object-cover"
                    style={{ width: 72, height: 52 }}
                    loading="lazy"
                  />
                </button>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

// ============================================================
// Collapsible Transaction Row
// ============================================================

function TransactionRow({ t, isLatest }: { t: PropertyTransaction; isLatest: boolean }) {
  const [open, setOpen] = useState(isLatest);
  const navigate = useNavigate();

  // Photos (already parsed by API)
  const photos = t.photos_json?.street_photo_urls || [];

  // Consideration (inline columns) and charges
  const hasConsideration = t.cash != null || t.debt != null || t.chattels != null || t.other_consideration != null;
  const charges = t.charges_json || [];

  // Contacts from transaction_parties
  const buyerContacts = (t.parties || []).filter(p => p.side === "buyer" && p.contact_name);
  const sellerContacts = (t.parties || []).filter(p => p.side === "seller" && p.contact_name);

  return (
    <div className="border border-[var(--gray-5)] rounded-lg overflow-hidden">
      {/* Summary row — always visible */}
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-[var(--gray-a2)] transition-colors text-left bg-transparent border-0 cursor-pointer"
      >
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-1.5">
            {open ? <CaretUp size={14} style={{ color: "var(--gray-9)" }} /> : <CaretDown size={14} style={{ color: "var(--gray-9)" }} />}
            <Text size="2" weight="medium">{formatDate(t.sale_date)}</Text>
          </div>
          <Text size="3" weight="bold" style={{ color: "var(--jade-11)" }}>
            {formatCurrency(t.sale_price)}
          </Text>
          <Badge size="1" variant="outline" color="blue">RT</Badge>
          {isLatest && <Badge size="1" color="jade">Latest</Badge>}
        </div>
        <div className="flex items-center gap-6 text-[13px]">
          <div className="text-right">
            <Text size="1" style={{ color: "var(--gray-9)" }}>Seller</Text>
            <Text size="2" className="block">{t.seller_parties?.[0] || "—"}</Text>
          </div>
          <Text size="2" style={{ color: "var(--gray-8)" }}>→</Text>
          <div className="text-left">
            <Text size="1" style={{ color: "var(--gray-9)" }}>Buyer</Text>
            <Text size="2" weight="medium" className="block">{t.buyer_parties?.[0] || "—"}</Text>
          </div>
        </div>
      </button>

      {/* Expanded details */}
      {open && (
        <div className="border-t border-[var(--gray-4)] px-4 py-4 bg-[var(--gray-a1)]">
          <div className="grid grid-cols-2 gap-6">
            {/* Seller details */}
            <div>
              <Text size="1" weight="medium" style={{ color: "var(--gray-9)" }} className="uppercase tracking-wider block mb-2">
                Seller
              </Text>
              <div className="flex flex-col gap-1">
                {t.seller_parties?.map((s, i) => (
                  <Text key={i} size="2">{s}</Text>
                )) || <Text size="2">—</Text>}
                {sellerContacts.map((c) => (
                  <div key={c.contact_id} className="mt-1.5 pl-3 border-l-2 border-[var(--gray-5)]">
                    <span className="inline-flex items-center gap-1">
                      <Link to={`/contacts/${c.contact_id}`} className="no-underline text-[13px] font-medium" style={{ color: "var(--accent-11)" }}>
                        {c.contact_name}
                      </Link>
                      <Link to={`/contacts/${c.contact_id}`} className="inline-flex items-center" style={{ color: "var(--gray-9)" }} title="View contact">
                        <ArrowSquareOut size={11} />
                      </Link>
                      {c.contact_name && (
                        <a href={`https://www.linkedin.com/search/results/all/?keywords=${encodeURIComponent(c.contact_name)}`} target="_blank" rel="noopener noreferrer" className="inline-flex items-center" style={{ color: "var(--gray-9)" }} title="Search LinkedIn">
                          <LinkedinLogo size={12} weight="bold" />
                        </a>
                      )}
                    </span>
                    {c.contact_title && <Text size="1" className="ml-1" style={{ color: "var(--gray-9)" }}>({c.contact_title})</Text>}
                    {(c.phone || c.contact_phone) && (
                      <a href={`tel:${c.phone || c.contact_phone}`} className="no-underline text-[12px] flex items-center gap-1 mt-0.5"
                         style={{ color: "var(--accent-11)" }}>
                        <Phone size={11} /> {formatPhone(c.phone || c.contact_phone)}
                      </a>
                    )}
                  </div>
                ))}
                {sellerContacts.length === 0 && t.seller_phone && (
                  <a href={`tel:${t.seller_phone}`} className="no-underline text-[13px] flex items-center gap-1.5 mt-1"
                     style={{ color: "var(--accent-11)" }}>
                    <Phone size={12} /> {formatPhone(t.seller_phone)}
                  </a>
                )}
                {formatMailingAddress(t.seller_mailing_address) && (
                  <div className="text-[12px] mt-2 pt-1.5 border-t border-[var(--gray-4)]" style={{ color: "var(--gray-9)" }}>
                    ✉ {formatMailingAddress(t.seller_mailing_address)}
                  </div>
                )}
              </div>
            </div>

            {/* Buyer details */}
            <div>
              <Text size="1" weight="medium" style={{ color: "var(--gray-9)" }} className="uppercase tracking-wider block mb-2">
                Buyer
              </Text>
              <div className="flex flex-col gap-1">
                {t.buyer_parties?.map((b, i) => (
                  <Text key={i} size="2" weight="medium">{b}</Text>
                )) || <Text size="2">—</Text>}
                {buyerContacts.map((c) => (
                  <div key={c.contact_id} className="mt-1.5 pl-3 border-l-2 border-[var(--jade-6)]">
                    <span className="inline-flex items-center gap-1">
                      <Link to={`/contacts/${c.contact_id}`} className="no-underline text-[13px] font-medium" style={{ color: "var(--accent-11)" }}>
                        {c.contact_name}
                      </Link>
                      <Link to={`/contacts/${c.contact_id}`} className="inline-flex items-center" style={{ color: "var(--gray-9)" }} title="View contact">
                        <ArrowSquareOut size={11} />
                      </Link>
                      {c.contact_name && (
                        <a href={`https://www.linkedin.com/search/results/all/?keywords=${encodeURIComponent(c.contact_name)}`} target="_blank" rel="noopener noreferrer" className="inline-flex items-center" style={{ color: "var(--gray-9)" }} title="Search LinkedIn">
                          <LinkedinLogo size={12} weight="bold" />
                        </a>
                      )}
                    </span>
                    {c.contact_title && <Text size="1" className="ml-1" style={{ color: "var(--gray-9)" }}>({c.contact_title})</Text>}
                    {(c.phone || c.contact_phone) && (
                      <a href={`tel:${c.phone || c.contact_phone}`} className="no-underline text-[12px] flex items-center gap-1 mt-0.5"
                         style={{ color: "var(--accent-11)" }}>
                        <Phone size={11} /> {formatPhone(c.phone || c.contact_phone)}
                      </a>
                    )}
                    {c.contact_email && (
                      <a href={`mailto:${c.contact_email}`} className="no-underline text-[12px] flex items-center gap-1 mt-0.5"
                         style={{ color: "var(--accent-11)" }}>
                        <EnvelopeSimple size={11} /> {c.contact_email}
                      </a>
                    )}
                  </div>
                ))}
                {buyerContacts.length === 0 && t.buyer_phone && (
                  <a href={`tel:${t.buyer_phone}`} className="no-underline text-[13px] flex items-center gap-1.5 mt-1"
                     style={{ color: "var(--accent-11)" }}>
                    <Phone size={12} /> {formatPhone(t.buyer_phone)}
                  </a>
                )}
                {formatMailingAddress(t.buyer_mailing_address) && (
                  <div className="text-[12px] mt-2 pt-1.5 border-t border-[var(--gray-4)]" style={{ color: "var(--gray-9)" }}>
                    ✉ {formatMailingAddress(t.buyer_mailing_address)}
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Consideration breakdown */}
          {hasConsideration && (
            <div className="mt-4">
              <Text size="1" weight="medium" style={{ color: "var(--gray-9)" }} className="uppercase tracking-wider block mb-2">
                Consideration
              </Text>
              <div className="flex gap-4 text-[13px]">
                {t.cash != null ? <div><Text size="1" style={{ color: "var(--gray-9)" }}>Cash</Text><Text size="2" className="block">{formatCurrency(t.cash)}</Text></div> : null}
                {t.debt != null ? <div><Text size="1" style={{ color: "var(--gray-9)" }}>Assumed Debt</Text><Text size="2" className="block">{formatCurrency(t.debt)}</Text></div> : null}
                {t.chattels != null ? <div><Text size="1" style={{ color: "var(--gray-9)" }}>Chattels</Text><Text size="2" className="block">{formatCurrency(t.chattels)}</Text></div> : null}
                {t.other_consideration != null ? <div><Text size="1" style={{ color: "var(--gray-9)" }}>Other</Text><Text size="2" className="block">{formatCurrency(t.other_consideration)}</Text></div> : null}
              </div>
              {charges.length > 0 && (
                <Text size="1" className="mt-1 block" style={{ color: "var(--gray-9)" }}>
                  Charges: {charges.join(", ")}
                </Text>
              )}
            </div>
          )}

          {/* Broker info is on the full transaction detail page */}

          {/* Transaction note */}
          {t.transaction_note && (
            <div className="mt-3 p-3 rounded bg-[var(--gray-a2)]">
              <Text size="1" style={{ color: "var(--gray-11)" }}>{t.transaction_note}</Text>
            </div>
          )}

          {/* Photos inline */}
          {photos.length > 0 && (
            <div className="mt-4">
              <Text size="1" weight="medium" style={{ color: "var(--gray-9)" }} className="uppercase tracking-wider block mb-2">
                Photos
              </Text>
              <div className="flex gap-2 overflow-x-auto pb-2">
                {photos.slice(0, 6).map((url, i) => (
                  <a key={i} href={url} target="_blank" rel="noopener noreferrer">
                    <img
                      src={url}
                      alt={`Property photo ${i + 1}`}
                      className="h-20 w-28 object-cover rounded border border-[var(--gray-5)] hover:border-[var(--gray-8)] transition-colors"
                      loading="lazy"
                    />
                  </a>
                ))}
                {photos.length > 6 && (
                  <div className="h-20 w-28 rounded border border-[var(--gray-5)] flex items-center justify-center bg-[var(--gray-2)]">
                    <Text size="1" style={{ color: "var(--gray-9)" }}>+{photos.length - 6} more</Text>
                  </div>
                )}
              </div>
            </div>
          )}

          <div className="mt-3 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Badge size="1" variant="outline" color="gray">{t.source_id}</Badge>
              {t.source_id?.startsWith("RT") && <SourceHtmlButton sourceId={t.source_id} />}
            </div>
            <Button size="1" variant="ghost" onClick={() => navigate(`/transactions/${t.source_id}`)}>
              View Full Record <ArrowSquareOut size={12} className="ml-1" />
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

// ============================================================
// GW Sale Row — lighter-weight row for GeoWarehouse sales history
// ============================================================

function GwSaleRow({ sale, isLatest }: { sale: GwSaleHistory; isLatest: boolean }) {
  return (
    <div className="border border-[var(--gray-5)] rounded-lg overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-1.5">
            <div style={{ width: 14 }} /> {/* Spacer to align with RT caret */}
            <Text size="2" weight="medium">{formatDate(sale.sale_date)}</Text>
          </div>
          <Text size="3" weight="bold" style={{ color: "var(--jade-11)" }}>
            {formatCurrency(sale.amount)}
          </Text>
          <Badge size="1" variant="outline" color="amber">GW</Badge>
          {sale.sale_type && (
            <Badge size="1" variant="soft" color="gray">{sale.sale_type}</Badge>
          )}
          {isLatest && <Badge size="1" color="jade">Latest</Badge>}
        </div>
        <div className="text-right">
          {sale.party_to && (
            <div>
              <Text size="1" style={{ color: "var(--gray-9)" }}>Transferred to</Text>
              <Text size="2" weight="medium" className="block">{sale.party_to}</Text>
            </div>
          )}
        </div>
      </div>
      {sale.notes && (
        <div className="border-t border-[var(--gray-4)] px-4 py-2 bg-[var(--gray-a1)]">
          <Text size="1" style={{ color: "var(--gray-11)" }}>{sale.notes}</Text>
        </div>
      )}
    </div>
  );
}

// ============================================================
// Merged timeline entry — discriminated union for RT and GW
// ============================================================

interface TimelineEntryRT {
  _source: "RT";
  date: string;
  transaction: PropertyTransaction;
}

interface TimelineEntryGW {
  _source: "GW";
  date: string;
  sale: GwSaleHistory;
}

type TimelineEntry = TimelineEntryRT | TimelineEntryGW;

// ============================================================
// Error Boundary
// ============================================================

import React from "react";

class PropertyErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { error: Error | null }
> {
  state = { error: null as Error | null };
  static getDerivedStateFromError(error: Error) { return { error }; }
  render() {
    if (this.state.error) {
      return (
        <div className="p-8">
          <Heading size="4" color="red">Page Error</Heading>
          <pre className="mt-4 p-4 bg-red-50 rounded text-sm overflow-auto" style={{ color: "var(--red-11)", background: "var(--red-2)" }}>
            {this.state.error.message}{"\n"}{this.state.error.stack}
          </pre>
        </div>
      );
    }
    return this.props.children;
  }
}

// ============================================================
// Main Page
// ============================================================

function PropertyDetailPageInner() {
  const { id } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const [prop, setProp] = useState<PropertyDetail | null>(null);
  const [copied, setCopied] = useState(false);
  const [showSellOppDialog, setShowSellOppDialog] = useState(false);

  // Determine where the user came from for the back link
  const cameFrom = (location.state as { from?: string } | null)?.from;

  useEffect(() => {
    if (id) fetchApi<PropertyDetail>(`/properties/${id}`).then(setProp).catch(e => console.error("Failed to load property:", e));
  }, [id]);

  // Build parcel GeoJSON FeatureCollection for Mapbox
  // MUST be before early return to satisfy React's rules of hooks
  const parcelFC = useMemo(() => {
    if (!prop?.parcel_geojson) return null;
    return {
      type: "FeatureCollection",
      features: [{
        type: "Feature",
        properties: {},
        geometry: prop.parcel_geojson,
      }],
    } as unknown as GeoJSON.FeatureCollection;
  }, [prop?.parcel_geojson]);

  if (!prop) {
    return (
      <div className="flex items-center justify-center h-64">
        <Text size="3" style={{ color: "var(--gray-9)" }}>Loading...</Text>
      </div>
    );
  }

  const copyArn = () => {
    navigator.clipboard.writeText(prop.arn);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  // Collect all photos from all transactions — grouped by transaction for timeline context
  // Only include full URLs (skip relative paths like /assets/files/...) and upgrade HTTP to HTTPS
  const allPhotos: { url: string; sourceId: string; date: string | null; type: "street" | "aerial" | "standalone" }[] = [];
  const normalizeUrl = (url: string) => url.startsWith("http://") ? url.replace("http://", "https://") : url;
  const isFullUrl = (url: string) => url.startsWith("http://") || url.startsWith("https://");
  prop.transactions?.forEach((t) => {
    const street = (t.photos_json?.street_photo_urls || []).filter(isFullUrl);
    const aerial = (t.photos_json?.aerial_photo_urls || []).filter(isFullUrl);
    const standalone = t.photos_json?.standalone_photo_url;
    street.forEach((url) => allPhotos.push({ url: normalizeUrl(url), sourceId: t.source_id, date: t.sale_date, type: "street" }));
    aerial.forEach((url) => allPhotos.push({ url: normalizeUrl(url), sourceId: t.source_id, date: t.sale_date, type: "aerial" }));
    if (standalone && isFullUrl(standalone)) allPhotos.push({ url: normalizeUrl(standalone), sourceId: t.source_id, date: t.sale_date, type: "standalone" });
  });

  const latestGw = prop.gw_assessments?.[0];

  // Resolve owner: pull the primary contact from the latest transaction's buyer side
  const latestBuyerParties = (prop.transactions?.[0]?.parties || []).filter(p => p.side === "buyer");
  const primaryContact = latestBuyerParties.find(p => p.contact_name) || null;
  const ownerIsBlank = !prop.current_owner_name || prop.current_owner_name === "N/A" || prop.current_owner_name === "Named Individual(s)";
  const resolvedOwnerName = ownerIsBlank
    ? (latestBuyerParties[0]?.party_name || prop.transactions?.[0]?.buyer_parties?.[0] || "Unknown Owner")
    : prop.current_owner_name;

  return (
    <div className="flex flex-col gap-6">
      {/* ============================================================ */}
      {/* HEADER ZONE */}
      {/* ============================================================ */}
      <div>
        {cameFrom === "map" ? (
          <button
            onClick={() => navigate(-1)}
            className="text-[14px] no-underline bg-transparent border-none cursor-pointer p-0"
            style={{ color: "var(--accent-11)" }}
          >
            &larr; Map
          </button>
        ) : (
          <Link to="/properties" className="text-[14px] no-underline" style={{ color: "var(--accent-11)" }}>
            &larr; Properties
          </Link>
        )}

        <div className="flex items-start justify-between mt-2">
          <div>
            <Heading size="6" weight="bold">{prop.display_address}</Heading>
            <div className="flex items-center gap-2 mt-1">
              <Text size="2" style={{ color: "var(--gray-9)" }}>{prop.city}{prop.region ? `, ${prop.region}` : ""}</Text>
              {prop.primary_property_type && (
                <Badge size="1" variant="soft" color={propertyTypeColor(prop.primary_property_type) as any}>
                  {propertyTypeLabel(prop.primary_property_type)}
                </Badge>
              )}
            </div>
          </div>

          {/* Quick actions */}
          <div className="flex gap-2">
            <Button size="2" variant="soft">Add to List</Button>
            <Button size="2" variant="soft" onClick={() => setShowSellOppDialog(true)}>Sell Opportunity</Button>
            <Button size="2" variant="soft">Create Deal</Button>
          </div>
        </div>
      </div>

      {/* ============================================================ */}
      {/* STAT CARDS + BRAND BADGES */}
      {/* ============================================================ */}
      <div className="grid grid-cols-4 gap-4">
        <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-4">
          <div className="flex items-center gap-2">
            <Text size="1" style={{ color: "var(--gray-9)" }}>Last Sale Price</Text>
            {prop.most_recent_sale_source && (
              <Badge size="1" variant="soft" color={prop.most_recent_sale_source === "RT" ? "blue" : "amber"}>
                {prop.most_recent_sale_source}
              </Badge>
            )}
          </div>
          <Text size="6" weight="bold" className="block mt-1" style={{ color: "var(--gray-12)" }}>
            {formatCurrency(prop.most_recent_sale_price)}
          </Text>
        </div>

        <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-4">
          <Text size="1" style={{ color: "var(--gray-9)" }}>Last Sale Date</Text>
          <Text size="6" weight="bold" className="block mt-1" style={{ color: "var(--gray-12)" }}>
            {prop.most_recent_sale_date ? formatDate(prop.most_recent_sale_date) : "—"}
          </Text>
          {prop.most_recent_sale_source && (
            <Text size="1" style={{ color: "var(--gray-9)" }}>
              Source: {prop.most_recent_sale_source === "RT" ? "Realtrack" : "GeoWarehouse"}
            </Text>
          )}
        </div>

        <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-4">
          <Text size="1" style={{ color: "var(--gray-9)" }}>Ownership</Text>
          <Text size="6" weight="bold" className="block mt-1" style={{ color: "var(--gray-12)" }}>
            {formatOwnership(computeOwnershipYears(prop.most_recent_sale_date))}
          </Text>
          <Text size="1" style={{ color: "var(--gray-9)" }}>
            since last sale
          </Text>
        </div>

        <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-4">
          <Text size="1" style={{ color: "var(--gray-9)" }}>Site</Text>
          <Text size="6" weight="bold" className="block mt-1" style={{ color: "var(--gray-12)" }}>
            {prop.acreage ? `${prop.acreage} ac` : latestGw?.acreage ? `${latestGw.acreage} ac` : "—"}
          </Text>
          <Text size="1" style={{ color: "var(--gray-9)" }}>
            {latestGw?.zoning ? `Zoned: ${latestGw.zoning}` : ""}
          </Text>
        </div>
      </div>

      {/* Brand badges row */}
      {prop.pois && prop.pois.length > 0 && (
        <div className="flex items-center gap-2 flex-wrap">
          <Tag size={14} style={{ color: "var(--gray-9)" }} />
          <Text size="1" weight="medium" style={{ color: "var(--gray-9)" }}>Tenants:</Text>
          {prop.pois.map((poi) => (
            <Badge key={poi.id} size="2" variant="soft" color={categoryColor(poi.category) as any}>
              {poi.brand}
            </Badge>
          ))}
        </div>
      )}

      {/* ============================================================ */}
      {/* TWO COLUMN: OWNER + MAP */}
      {/* ============================================================ */}
      <div className="grid grid-cols-5 gap-6">
        {/* Owner Card — the action center */}
        <div className="col-span-2 rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
          <div className="flex items-center gap-2 mb-4">
            <Buildings size={18} style={{ color: "var(--gray-9)" }} />
            <Text size="3" weight="medium">Owner</Text>
          </div>

          {/* Company / party name */}
          <Text size="4" weight="bold" className="block">
            {resolvedOwnerName}
          </Text>

          {prop.current_owner_group_id && (
            <Link
              to={`/groups/${prop.current_owner_group_id}`}
              className="text-[13px] no-underline mt-1 inline-flex items-center gap-1"
              style={{ color: "var(--accent-11)" }}
            >
              View Portfolio <ArrowSquareOut size={12} />
            </Link>
          )}

          {prop.owner_hq_address && (
            <a
              href={`https://www.google.com/search?q=${encodeURIComponent(prop.owner_hq_address)}`}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-start gap-1.5 mt-2 no-underline group"
            >
              <MapPin size={14} weight="fill" className="mt-0.5 shrink-0" style={{ color: "var(--gray-9)" }} />
              <Text size="2" className="group-hover:underline" style={{ color: "var(--gray-11)" }}>{prop.owner_hq_address}</Text>
              <ArrowSquareOut size={11} className="mt-1 shrink-0" style={{ color: "var(--gray-9)" }} />
            </a>
          )}

          {/* Primary contact person — the person you actually call */}
          {primaryContact ? (
            <>
              <Separator size="4" className="my-4" />
              <div className="flex flex-col gap-2">
                <div className="flex items-center gap-2">
                  <User size={16} style={{ color: "var(--gray-9)" }} />
                  <div className="flex items-center gap-1.5">
                    <Text size="3" weight="medium">{primaryContact.contact_name}</Text>
                    {primaryContact.contact_id && (
                      <Link to={`/contacts/${primaryContact.contact_id}`} className="inline-flex items-center" style={{ color: "var(--gray-9)" }} title="View contact">
                        <ArrowSquareOut size={13} />
                      </Link>
                    )}
                    {primaryContact.contact_name && (
                      <a
                        href={`https://www.linkedin.com/search/results/all/?keywords=${encodeURIComponent(primaryContact.contact_name)}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center"
                        style={{ color: "var(--gray-9)" }}
                        title="Search LinkedIn"
                      >
                        <LinkedinLogo size={14} weight="bold" />
                      </a>
                    )}
                  </div>
                  {primaryContact.contact_title && (
                    <Text size="1" style={{ color: "var(--gray-9)" }}>({primaryContact.contact_title})</Text>
                  )}
                </div>

                {(primaryContact.contact_phone || primaryContact.phone) && (
                  <a
                    href={`tel:${primaryContact.contact_phone || primaryContact.phone}`}
                    className="no-underline flex items-center gap-2 text-[14px] font-medium"
                    style={{ color: "var(--accent-11)" }}
                  >
                    <Phone size={16} weight="fill" />
                    {formatPhone((primaryContact.contact_phone || primaryContact.phone)!)}
                  </a>
                )}

                {primaryContact.contact_email && (
                  <a
                    href={`mailto:${primaryContact.contact_email}`}
                    className="no-underline flex items-center gap-2 text-[14px]"
                    style={{ color: "var(--accent-11)" }}
                  >
                    <EnvelopeSimple size={16} />
                    {primaryContact.contact_email}
                  </a>
                )}

                {primaryContact.last_engaged_date && (
                  <Text size="1" style={{ color: "var(--gray-9)" }}>
                    Last Engaged: {formatDate(primaryContact.last_engaged_date)}
                  </Text>
                )}

                <Text size="1" style={{ color: "var(--gray-9)" }}>
                  From {prop.transactions?.[0]?.source_id} ({formatDate(prop.transactions?.[0]?.sale_date)})
                </Text>
              </div>
            </>
          ) : prop.transactions?.[0]?.buyer_phone ? (
            <>
              <Separator size="4" className="my-4" />
              <div className="flex flex-col gap-2">
                <a
                  href={`tel:${prop.transactions[0].buyer_phone}`}
                  className="no-underline flex items-center gap-2 text-[14px] font-medium"
                  style={{ color: "var(--accent-11)" }}
                >
                  <Phone size={16} weight="fill" />
                  {formatPhone(prop.transactions[0].buyer_phone)}
                </a>
                <Text size="1" style={{ color: "var(--gray-9)" }}>
                  From {prop.transactions[0].source_id} ({formatDate(prop.transactions[0].sale_date)})
                </Text>
              </div>
            </>
          ) : (
            <>
              <Separator size="4" className="my-4" />
              <Callout.Root size="1" color="amber" variant="surface">
                <Callout.Text>No contact on file for this property</Callout.Text>
              </Callout.Root>
            </>
          )}

          <Separator size="4" className="my-4" />

          {/* CRM quick actions */}
          <div className="flex flex-col gap-2">
            <Button size="2" variant="outline" className="justify-start">
              <Phone size={14} /> Log Call
            </Button>
            <Button size="2" variant="outline" className="justify-start">
              <EnvelopeSimple size={14} /> Send Email
            </Button>
          </div>
        </div>

        {/* Satellite map with parcel boundary */}
        <div className="col-span-3 rounded-[var(--card-radius)] border border-[var(--gray-6)] overflow-hidden">
          {prop.lat && prop.lng && MAPBOX_TOKEN ? (
            <Suspense fallback={
              <div className="w-full h-[340px] bg-[var(--gray-3)] flex items-center justify-center">
                <Text size="2" style={{ color: "var(--gray-9)" }}>Loading map...</Text>
              </div>
            }>
              <PropertySatelliteMap
                lat={prop.lat}
                lng={prop.lng}
                parcelFC={parcelFC}
                parcelColor={getRadixHex(propertyTypeColor(prop.primary_property_type || ""), 9)}
                parcelOutlineColor={getRadixHex(propertyTypeColor(prop.primary_property_type || ""), 11)}
                token={MAPBOX_TOKEN}
                mapStyle={SATELLITE_STYLE}
                hqLat={prop.owner_hq_lat ?? undefined}
                hqLng={prop.owner_hq_lng ?? undefined}
                hqLabel={prop.owner_hq_address ?? undefined}
              />
            </Suspense>
          ) : prop.lat && prop.lng ? (
            <div className="w-full h-[340px] bg-[var(--gray-3)] flex items-center justify-center flex-col gap-2">
              <MapPin size={32} style={{ color: "var(--jade-9)" }} />
              <Text size="2" weight="medium">Map unavailable</Text>
              <Text size="1" style={{ color: "var(--gray-9)" }}>
                {prop.lat.toFixed(4)}, {prop.lng.toFixed(4)}
              </Text>
              <Text size="1" style={{ color: "var(--gray-9)" }}>Set VITE_MAPBOX_TOKEN to enable</Text>
            </div>
          ) : (
            <div className="w-full h-[340px] bg-[var(--gray-2)] flex items-center justify-center">
              <Text size="2" style={{ color: "var(--gray-9)" }}>No location data</Text>
            </div>
          )}
        </div>
      </div>

      {/* ============================================================ */}
      {/* PHOTO GALLERY (if any transaction has photos) */}
      {/* ============================================================ */}
      {allPhotos.length > 0 && (
        <PropertyPhotoGallery photos={allPhotos} />
      )}

      {/* ============================================================ */}
      {/* TRANSACTION HISTORY — Merged RT + GW timeline */}
      {/* ============================================================ */}
      {(() => {
        // Build merged timeline from RT transactions + GW sales history
        const timeline: TimelineEntry[] = [];
        for (const t of (prop.transactions || [])) {
          timeline.push({ _source: "RT", date: t.sale_date || "", transaction: t });
        }
        for (const s of (prop.gw_sales_history || [])) {
          timeline.push({ _source: "GW", date: s.sale_date || "", sale: s });
        }
        // Sort by date descending (newest first)
        timeline.sort((a, b) => (b.date || "").localeCompare(a.date || ""));

        const totalCount = timeline.length;

        return (
          <div>
            <div className="flex items-center gap-2 mb-3">
              <ChartBar size={16} style={{ color: "var(--gray-9)" }} />
              <Text size="3" weight="medium">Transaction History</Text>
              <Badge size="1" variant="outline" color="gray">{totalCount}</Badge>
            </div>

            {totalCount === 0 ? (
              <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-8 text-center">
                <Text size="2" style={{ color: "var(--gray-9)" }}>No transaction history available</Text>
              </div>
            ) : (
              <div className="flex flex-col gap-2">
                {timeline.map((entry, i) => {
                  if (entry._source === "RT") {
                    return (
                      <TransactionRow
                        key={entry.transaction.source_id}
                        t={entry.transaction as any}
                        isLatest={i === 0}
                      />
                    );
                  } else {
                    return (
                      <GwSaleRow
                        key={`gw-${entry.date}-${entry.sale.amount}`}
                        sale={entry.sale}
                        isLatest={i === 0}
                      />
                    );
                  }
                })}
              </div>
            )}
          </div>
        );
      })()}

      {/* ============================================================ */}
      {/* TABBED SECTION: Site Details | Assessment | Tenants */}
      {/* ============================================================ */}
      <Tabs.Root defaultValue="site">
        <Tabs.List>
          <Tabs.Trigger value="site">Site Details</Tabs.Trigger>
          {prop.gw_assessments && prop.gw_assessments.length > 0 && (
            <Tabs.Trigger value="assessment">
              Assessment ({prop.gw_assessments.length})
            </Tabs.Trigger>
          )}
          {prop.pois && prop.pois.length > 0 && (
            <Tabs.Trigger value="tenants">
              Tenants ({prop.pois.length})
            </Tabs.Trigger>
          )}
        </Tabs.List>

        {/* Site Details Tab */}
        <Tabs.Content value="site">
          <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5 mt-4">
            <DataList.Root>
              {prop.acreage && (
                <DataList.Item>
                  <DataList.Label>Acreage</DataList.Label>
                  <DataList.Value>{prop.acreage} acres</DataList.Value>
                </DataList.Item>
              )}
              {latestGw?.frontage_ft && (
                <DataList.Item>
                  <DataList.Label>Frontage</DataList.Label>
                  <DataList.Value>{latestGw.frontage_ft} ft</DataList.Value>
                </DataList.Item>
              )}
              {latestGw?.depth_ft && (
                <DataList.Item>
                  <DataList.Label>Depth</DataList.Label>
                  <DataList.Value>{latestGw.depth_ft} ft</DataList.Value>
                </DataList.Item>
              )}
              {latestGw?.zoning && (
                <DataList.Item>
                  <DataList.Label>Zoning</DataList.Label>
                  <DataList.Value><Badge variant="outline" color="gray">{latestGw.zoning}</Badge></DataList.Value>
                </DataList.Item>
              )}
              {latestGw?.ownership_type && (
                <DataList.Item>
                  <DataList.Label>Ownership Type</DataList.Label>
                  <DataList.Value>{latestGw.ownership_type}</DataList.Value>
                </DataList.Item>
              )}
              {prop.postal && (
                <DataList.Item>
                  <DataList.Label>Postal Code</DataList.Label>
                  <DataList.Value>{prop.postal}</DataList.Value>
                </DataList.Item>
              )}
              <DataList.Item>
                <DataList.Label>ARN</DataList.Label>
                <DataList.Value>
                  <div className="flex items-center gap-2">
                    <code className="text-[13px]">{prop.arn}</code>
                    <button onClick={copyArn} className="p-0.5 rounded hover:bg-[var(--gray-a3)] transition-colors border-0 bg-transparent cursor-pointer" title="Copy ARN">
                      <Copy size={12} style={{ color: copied ? "var(--jade-9)" : "var(--gray-9)" }} />
                    </button>
                  </div>
                </DataList.Value>
              </DataList.Item>
              {prop.legal_description && (
                <DataList.Item>
                  <DataList.Label>Legal Description</DataList.Label>
                  <DataList.Value>
                    <Text size="1" style={{ color: "var(--gray-11)", whiteSpace: "pre-line" }}>
                      {prop.legal_description}
                    </Text>
                  </DataList.Value>
                </DataList.Item>
              )}
            </DataList.Root>
          </div>
        </Tabs.Content>

        {/* Assessment Tab */}
        {prop.gw_assessments && prop.gw_assessments.length > 0 && (
          <Tabs.Content value="assessment">
            <div className="flex flex-col gap-4 mt-4">
              {prop.gw_assessments.map((gw) => (
                <div key={gw.id} className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
                  <div className="flex items-center justify-between mb-3">
                    <Text size="2" weight="medium">Assessment Record</Text>
                    <div className="flex gap-1">
                      <Badge size="1" variant="outline" color="gray">{gw.gw_id}</Badge>
                      {gw.property_code && <Badge size="1" variant="outline" color="gray">Code: {gw.property_code}</Badge>}
                    </div>
                  </div>
                  <DataList.Root>
                    <DataList.Item>
                      <DataList.Label>Assessed Value</DataList.Label>
                      <DataList.Value><Text weight="bold">{formatCurrency(gw.assessed_value)}</Text></DataList.Value>
                    </DataList.Item>
                    {gw.valuation_date && (
                      <DataList.Item>
                        <DataList.Label>Valuation Date</DataList.Label>
                        <DataList.Value>{gw.valuation_date}</DataList.Value>
                      </DataList.Item>
                    )}
                    {gw.zoning && (
                      <DataList.Item>
                        <DataList.Label>Zoning</DataList.Label>
                        <DataList.Value><Badge variant="outline" color="gray">{gw.zoning}</Badge></DataList.Value>
                      </DataList.Item>
                    )}
                    {gw.ownership_type && (
                      <DataList.Item>
                        <DataList.Label>Ownership</DataList.Label>
                        <DataList.Value>{gw.ownership_type}</DataList.Value>
                      </DataList.Item>
                    )}
                    {gw.owner_name && (
                      <DataList.Item>
                        <DataList.Label>Owner (MPAC)</DataList.Label>
                        <DataList.Value><Text weight="medium">{gw.owner_name}</Text></DataList.Value>
                      </DataList.Item>
                    )}
                    {gw.owner_mailing && (
                      <DataList.Item>
                        <DataList.Label>Mailing Address</DataList.Label>
                        <DataList.Value>{gw.owner_mailing}</DataList.Value>
                      </DataList.Item>
                    )}
                    {gw.property_description && (
                      <DataList.Item>
                        <DataList.Label>Description</DataList.Label>
                        <DataList.Value>{gw.property_description}</DataList.Value>
                      </DataList.Item>
                    )}
                    {(gw.frontage_ft || gw.depth_ft) && (
                      <DataList.Item>
                        <DataList.Label>Dimensions</DataList.Label>
                        <DataList.Value>
                          {gw.frontage_ft ? `${gw.frontage_ft} ft frontage` : ""}
                          {gw.frontage_ft && gw.depth_ft ? " × " : ""}
                          {gw.depth_ft ? `${gw.depth_ft} ft depth` : ""}
                        </DataList.Value>
                      </DataList.Item>
                    )}
                    {gw.acreage && (
                      <DataList.Item>
                        <DataList.Label>Site Area</DataList.Label>
                        <DataList.Value>{gw.acreage} acres</DataList.Value>
                      </DataList.Item>
                    )}
                    {gw.legal_description && (
                      <DataList.Item>
                        <DataList.Label>Legal Description</DataList.Label>
                        <DataList.Value>
                          <Text size="1" style={{ whiteSpace: "pre-line" }}>{gw.legal_description}</Text>
                        </DataList.Value>
                      </DataList.Item>
                    )}
                  </DataList.Root>
                </div>
              ))}
            </div>
          </Tabs.Content>
        )}

        {/* Tenants Tab */}
        {prop.pois && prop.pois.length > 0 && (
          <Tabs.Content value="tenants">
            <div className="grid grid-cols-3 gap-4 mt-4">
              {prop.pois.map((poi) => (
                <div key={poi.id} className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-4">
                  <div className="flex items-center gap-2 mb-2">
                    <Text size="3" weight="medium">{poi.brand}</Text>
                    <Badge size="1" variant="soft" color={categoryColor(poi.category) as any}>
                      {poi.category}
                    </Badge>
                  </div>
                  {poi.address && (
                    <Text size="1" className="block" style={{ color: "var(--gray-11)" }}>{poi.address}</Text>
                  )}
                  <div className="flex gap-3 mt-2">
                    {poi.phone && (
                      <a href={`tel:${poi.phone}`} className="no-underline text-[12px] flex items-center gap-1"
                         style={{ color: "var(--accent-11)" }}>
                        <Phone size={11} /> {formatPhone(poi.phone)}
                      </a>
                    )}
                    {poi.website && (
                      <a href={poi.website} target="_blank" rel="noopener noreferrer"
                         className="no-underline text-[12px] flex items-center gap-1"
                         style={{ color: "var(--accent-11)" }}>
                        <ArrowSquareOut size={11} /> Website
                      </a>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </Tabs.Content>
        )}
      </Tabs.Root>

      {showSellOppDialog && (
        <CreateSellOppDialog
          propertyId={prop.id}
          propertyAddress={prop.display_address}
          onClose={() => setShowSellOppDialog(false)}
        />
      )}
    </div>
  );
}

export default function PropertyDetailPageV2() {
  return (
    <PropertyErrorBoundary>
      <PropertyDetailPageInner />
    </PropertyErrorBoundary>
  );
}
