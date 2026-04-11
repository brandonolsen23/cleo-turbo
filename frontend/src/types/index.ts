// ============================================================
// Pipeline Orchestrator
// ============================================================

export interface OrchestratorStatus {
  stages: {
    assembled: number;
    deduped: number;
    classified: number;
    normalized: number;
    resolved: number;
    clean_data: number;
  };
  pending: {
    dedup: number;
    classify: number;
    normalize: number;
    resolve: number;
  };
  resolve_locked: boolean;
  resolve_pid: number | null;
  reprocess: {
    from_stage: string;
    created: string;
    skip_stages: string[];
    progress: Record<string, { completed_at: string; files_processed: number }>;
  } | null;
  running: boolean;
  run_status: {
    running: boolean;
    mode: string;
    pid: number;
    started_at: number;
    command: string;
  } | null;
  log: {
    timestamp: string;
    stage: string;
    mode: string;
    files_processed: number;
    files_skipped: number;
    elapsed_seconds: number;
    errors: number;
  }[];
}

export interface OrchestratorRunResponse {
  success: boolean;
  mode: string;
  pid: number;
  message: string;
}

export interface OrchestratorLogResponse {
  lines: string[];
  message?: string;
}

// ============================================================
// Daily Scraper
// ============================================================

export interface ScraperRunMeta {
  run_dir: string;
  mode: string;
  start_date: string;
  end_date: string;
  lookback_days: number;
  total_found: number;
  new_downloaded: number;
  already_known: number;
  new_rt_ids: string[];
  verification_ok: boolean;
  dry_run: boolean;
  completed_at: string;
}

export interface ScraperStatus {
  running: boolean;
  run_status: {
    running: boolean;
    mode: string;
    dry_run: boolean;
    days: number;
    started_at: number;
    pid: number;
    command: string;
  } | null;
  recent_runs: ScraperRunMeta[];
}

export interface ScraperRunResponse {
  success: boolean;
  mode: string;
  dry_run: boolean;
  pid: number;
  message: string;
}

export interface ReprocessResponse {
  success: boolean;
  rt_ids: string[];
  from_stage: string;
  dry_run: boolean;
  pid: number;
  message: string;
}

export interface ReprocessStatus {
  running: boolean;
  run_status: {
    running: boolean;
    rt_ids: string[];
    from_stage: string;
    dry_run: boolean;
    skip_resolve: boolean;
    started_at: number;
    pid: number;
    command: string;
  } | null;
}

// ============================================================
// API Response Types
// ============================================================

export interface BrowseResponse<T> {
  results: T[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
}

export interface SearchResponse<T> {
  results: T[];
  total: number;
}

// ============================================================
// Properties
// ============================================================

export interface PropertyBrowseItem {
  id: string;
  arn: string;
  display_address: string;
  city: string;
  region: string;
  most_recent_sale_date: string | null;
  most_recent_sale_price: number | null;
  most_recent_sale_source: string | null;
  current_owner_name: string | null;
  current_owner_group_id: string | null;
  transaction_count: number;
  ownership_years: number | null;
  lat: number | null;
  lng: number | null;
  asset_class: string | null;
  asset_subclass: string | null;
}

export interface PropertyDetail {
  id: string;
  arn: string;
  display_address: string;
  city: string;
  region: string;
  postal: string | null;
  acreage: number | null;
  legal_description: string | null;
  current_owner_name: string | null;
  current_owner_group_id: string | null;
  most_recent_source_id: string | null;
  most_recent_sale_date: string | null;
  most_recent_sale_price: number | null;
  most_recent_sale_source: string | null;
  transaction_count: number;
  primary_property_type: string | null;
  asset_class: string | null;
  asset_subclass: string | null;
  gw_municipality: string | null;
  lat: number | null;
  lng: number | null;
  parcel_geojson: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
  transactions: PropertyTransaction[];
  pois: PoiOnProperty[];
  gw_assessments: GwAssessment[];
  gw_sales_history: GwSaleHistory[];
  owner_hq_address: string | null;
  owner_hq_lat: number | null;
  owner_hq_lng: number | null;
}

export interface PropertyTransactionParty {
  side: "buyer" | "seller";
  party_name: string | null;
  contact_title: string | null;
  phone: string | null;
  contact_id: string | null;
  group_id: string | null;
  contact_name: string | null;
  contact_phone: string | null;
  contact_email: string | null;
  status: string | null;
  last_engaged_date: string | null;
}

export interface PropertyTransaction {
  source_id: string;
  sale_date: string | null;
  sale_price: number | null;
  display_address: string;
  transaction_note: string | null;
  seller_parties: string[] | null;
  buyer_parties: string[] | null;
  seller_phone: string | null;
  buyer_phone: string | null;
  cash: number | null;
  debt: number | null;
  chattels: number | null;
  other_consideration: number | null;
  charges_json: string[] | null;
  photos_json: { street_photo_urls?: string[]; aerial_photo_urls?: string[]; standalone_photo_url?: string } | null;
  parties: PropertyTransactionParty[];
}

// ============================================================
// Transactions
// ============================================================

export interface TransactionBrowseItem {
  source_id: string;
  property_id: string;
  sale_date: string | null;
  sale_price: number | null;
  display_address: string;
  city: string;
  region: string;
  seller_parties: string[] | null;
  buyer_parties: string[] | null;
  transaction_note: string | null;
}

export interface TransactionParty {
  side: "buyer" | "seller";
  party_name: string | null;
  contact_title: string | null;
  phone: string | null;
  contact_id: string | null;
  contact_name: string | null;
  group_id: string | null;
  group_name: string | null;
}

export interface TransactionDetail {
  source_id: string;
  property_id: string;
  arn: string;
  sale_date: string | null;
  sale_price: number | null;
  transaction_note: string | null;
  display_address: string;
  city: string;
  region: string;
  postal: string | null;
  seller_parties: string[] | null;
  buyer_parties: string[] | null;
  seller_phone: string | null;
  buyer_phone: string | null;
  description: string | null;
  acreage: number | null;
  pin: string | null;
  legal_description: string | null;
  pin_display: string | null;
  arn_display: string | null;
  pin_multiple: boolean;
  parcel_method: string | null;
  location: string | null;
  surface_rights_only: boolean;
  more_info_url: string | null;
  cash: number | null;
  debt: number | null;
  chattels: number | null;
  other_consideration: number | null;
  charges_json: string[] | null;
  seller_trade_name: string | null;
  seller_care_of: string | null;
  seller_law_firms_json: string[] | null;
  seller_companies_json: string[] | null;
  buyer_trade_name: string | null;
  buyer_care_of: string | null;
  buyer_law_firms_json: string[] | null;
  buyer_companies_json: string[] | null;
  photos_json: Record<string, unknown> | null;
  source_folder: string | null;
  created_at: string;
  parties: TransactionParty[];
  consideration: {
    cash: number | null;
    debt: number | null;
    chattels: number | null;
    other: number | null;
    charges: string[];
  } | null;
  brokers: {
    broker_name: string | null;
    phone: string | null;
    agents: string[];
  }[];
  seller_mailing_address: MailingAddress | null;
  buyer_mailing_address: MailingAddress | null;
  seller_party_metadata: PartyMetadata | null;
  buyer_party_metadata: PartyMetadata | null;
}

export interface MailingAddress {
  display: string | null;
  street_number: string | null;
  street_name: string | null;
  street_suffix: string | null;
  street_direction: string | null;
  suite_type: string | null;
  suite_number: string | null;
  city: string | null;
  province: string | null;
  postal: string | null;
  country: string | null;
  geocode_string: string | null;
}

export interface PartyMetadata {
  trade_name: string | null;
  care_of: string | null;
  law_firms: string[];
  companies: string[];
}


// ============================================================
// Contacts
// ============================================================

export interface ContactBrowseItem {
  id: string;
  display_name: string;
  phone: string | null;
  email: string | null;
  mobile: string | null;
  company_name: string | null;
  status: string;
  contact_type: string | null;
  transaction_count: number;
  total_buy_value: number | null;
  first_seen_date: string | null;
  last_seen_date: string | null;
  job_title: string | null;
}

export interface ContactTransaction {
  source_id: string;
  side: "buyer" | "seller";
  party_name: string | null;
  contact_title: string | null;
  phone: string | null;
  sale_date: string | null;
  sale_price: number | null;
  display_address: string;
  city: string;
}

export interface ContactDetail {
  id: string;
  name_fingerprint: string;
  first_name: string | null;
  last_name: string | null;
  display_name: string;
  phone: string | null;
  email: string | null;
  mobile: string | null;
  job_title: string | null;
  company_name: string | null;
  current_group_id: string | null;
  contact_type: string | null;
  status: string;
  source: string | null;
  transaction_count: number;
  first_seen_date: string | null;
  last_seen_date: string | null;
  hubspot_id: string | null;
  last_engaged_date: string | null;
  created_at: string;
  updated_at: string;
  transactions: ContactTransaction[];
  current_group: { id: string; display_name: string; status: string; hq_address: string | null } | null;
}

// ============================================================
// Groups
// ============================================================

export interface GroupBrowseItem {
  id: string;
  display_name: string;
  status: string;
  property_count: number;
  transaction_count: number;
  contact_count: number;
  // Analytics (from join)
  total_assessed_value: number | null;
  total_buys: number | null;
  total_sells: number | null;
  avg_buy_price: number | null;
  net_acquisitions: number | null;
  txns_per_year: number | null;
  buys_last_12m: number | null;
  sells_last_12m: number | null;
  geographic_radius_km: number | null;
  region_count: number | null;
  max_distance_from_hq_km: number | null;
}

export interface GroupFilterOptions {
  asset_classes: string[];
  regions: string[];
  brands: string[];
}

export interface ContactFilterOptions {
  contact_types: string[];
  regions: string[];
}

export interface GroupContact {
  id: string;
  display_name: string;
  phone: string | null;
  job_title: string | null;
  status: string;
  transaction_count: number;
}

export interface GroupTransaction {
  source_id: string;
  sale_date: string | null;
  sale_price: number | null;
  display_address: string;
  city: string;
  side: string;
  party_name: string | null;
}

export interface GroupProperty {
  id: string;
  display_address: string;
  city: string;
  most_recent_sale_date: string | null;
  most_recent_sale_price: number | null;
  most_recent_sale_source: string | null;
  lat: number | null;
  lng: number | null;
  asset_class: string | null;
}

// ── Mini-map types ──

export interface MiniMapProperty {
  id: string;
  display_address: string;
  city: string;
  lat: number;
  lng: number;
  asset_class: string | null;
  most_recent_sale_price?: number | null;
  current_owner_name?: string | null;
}

export interface ContactPropertyHistoryResponse {
  properties: MiniMapProperty[];
}

export interface GroupKnownName {
  name: string;
  normalized: string;
  source_id: string;
}

export interface GroupAnalytics {
  group_id: string;
  // Portfolio
  property_count: number;
  total_assessed_value: number | null;
  property_type_mix: Record<string, number> | null;
  regions: string[] | null;
  region_count: number;
  // Transactions
  total_buys: number;
  total_sells: number;
  avg_buy_price: number | null;
  median_buy_price: number | null;
  avg_sell_price: number | null;
  median_sell_price: number | null;
  first_transaction_date: string | null;
  last_transaction_date: string | null;
  net_acquisitions: number;
  avg_hold_period_days: number | null;
  // Velocity
  txns_per_year: number | null;
  buys_last_12m: number;
  sells_last_12m: number;
  buys_last_36m: number;
  sells_last_36m: number;
  // Geographic
  hq_lat: number | null;
  hq_lng: number | null;
  avg_distance_from_hq_km: number | null;
  max_distance_from_hq_km: number | null;
  geographic_radius_km: number | null;
  centroid_lat: number | null;
  centroid_lng: number | null;
  refreshed_at: string;
}

export interface GroupDetail {
  id: string;
  display_name: string;
  normalized_name: string;
  status: string;
  property_count: number;
  transaction_count: number;
  contact_count: number;
  hq_address: string | null;
  website: string | null;
  hubspot_id: string | null;
  created_at: string;
  updated_at: string;
  analytics: GroupAnalytics | null;
  known_names: GroupKnownName[];
  contacts: GroupContact[];
  transactions: GroupTransaction[];
  properties: GroupProperty[];
}

// ============================================================
// Dashboard / Stats
// ============================================================

export interface DashboardStats {
  total_properties: number;
  total_transactions: number;
  total_contacts: number;
  total_groups: number;
  engaged_contacts: number;
  engaged_groups: number;
  top_cities: { city: string; count: number }[];
  recent_records: {
    source_id: string;
    source: "rt" | "gw";
    property_id: string | null;
    display_address: string;
    city: string;
    added_at: string | null;
    value: number | null;
  }[];
}

// ============================================================
// CRM: Deals
// ============================================================

export interface CrmDeal {
  id: string;
  name: string;
  stage: string;
  amount: number | null;
  close_date: string | null;
  property_id: string | null;
  group_id: string | null;
  deal_owner: string | null;
  description: string | null;
  next_step: string | null;
  priority: string | null;
  lost_reason: string | null;
  hubspot_id: string | null;
  created_at: string;
  updated_at: string;
}

// ============================================================
// CRM: Lists
// ============================================================

export interface CrmList {
  id: string;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
  item_count?: number;
}

export interface CrmListMember {
  id: number;
  entity_type: "property" | "contact" | "group" | "transaction";
  entity_id: string;
  entity_name?: string;
  added_at: string;
}

// ============================================================
// CRM: Notes
// ============================================================

export interface CrmNote {
  id: number;
  note: string;
  created_by: string | null;
  created_at: string;
}

// ============================================================
// Search
// ============================================================

export interface OmnisearchResult {
  type: "property" | "contact" | "group";
  id: string;
  title: string;
  subtitle: string | null;
  score: number;
}

// ============================================================
// POIs
// ============================================================

export interface PoiBrowseItem {
  id: string;
  source: string;
  brand: string;
  category: string;
  name: string;
  lat: number | null;
  lng: number | null;
  address: string;
  city: string;
  phone: string | null;
  website: string | null;
  property_id: string | null;
  arn: string | null;
}

export interface GwSaleHistory {
  sale_date: string | null;
  amount: number | null;
  sale_type: string | null;
  party_to: string | null;
  notes: string | null;
}

export interface GwAssessment {
  id: string;
  gw_id: string;
  property_id: string | null;
  arn: string;
  pin: string;
  assessed_value: number | null;
  valuation_date: string | null;
  zoning: string | null;
  property_code: string | null;
  property_description: string | null;
  ownership_type: string | null;
  frontage_ft: number | null;
  depth_ft: number | null;
  site_area_sqft: number | null;
  acreage: number | null;
  owner_name: string | null;
  owner_mailing: string | null;
  legal_description: string | null;
  land_registry_status: string | null;
  registration_type: string | null;
  lro: string | null;
  municipality: string | null;
  has_mpac_data: boolean;
  is_active: boolean;
  address_parsed: boolean;
  parcel_resolved: boolean;
  sales_history?: GwSaleHistory[];
}

export interface PoiOnProperty {
  id: string;
  source: string;
  brand: string;
  category: string;
  name: string;
  lat: number;
  lng: number;
  address: string;
  city: string;
  phone: string | null;
  website: string | null;
}

// ============================================================
// Filters
// ============================================================

export interface FilterOptions {
  cities: string[];
  regions: string[];
  brands: string[];
  categories: string[];
  asset_classes: string[];
}

// ============================================================
// Asset Classes
// ============================================================

export interface AssetSubclass {
  id: string;
  label: string;
}

export interface AssetClass {
  id: string;
  label: string;
  subcategories: AssetSubclass[];
}

export interface AssetClassResponse {
  classes: AssetClass[];
}

// ============================================================
// Contact Types
// ============================================================

export const CONTACT_TYPES = [
  { id: "seller", label: "Seller" },
  { id: "buyer_investor", label: "Buyer - Investor" },
  { id: "buyer_developer", label: "Buyer - Developer" },
  { id: "buyer_owner_occupier", label: "Buyer - Owner Occupier" },
  { id: "national_tenant", label: "National Tenant" },
  { id: "local_tenant", label: "Local Tenant" },
  { id: "landlord", label: "Landlord" },
  { id: "professional", label: "Professional Contact" },
  { id: "personal", label: "Personal Contact" },
  { id: "commercial_realtor", label: "Commercial Realtor" },
  { id: "residential_realtor", label: "Residential Realtor" },
] as const;

export type ContactTypeId = (typeof CONTACT_TYPES)[number]["id"];

export function getContactTypeLabel(id: string | null): string {
  if (!id) return "";
  const ct = CONTACT_TYPES.find((t) => t.id === id);
  return ct ? ct.label : id;
}

// ============================================================
// Group Merges
// ============================================================

export interface MergeCandidate {
  id: string;
  display_name: string;
  normalized_name: string;
  status: string;
  property_count: number;
  transaction_count: number;
  contact_count: number;
  total_assessed_value: number | null;
  geographic_radius_km: number | null;
}

export interface MergeCandidatesResponse {
  group: { id: string; normalized_name: string; display_name: string };
  candidates: MergeCandidate[];
}

export interface MergeHistoryItem {
  id: number;
  source_group_id?: string;
  source_name?: string;
  target_group_id?: string;
  target_name?: string;
  merged_by: string | null;
  merged_at: string;
  unmerged_at: string | null;
  unmerged_by: string | null;
}

export interface MergeHistoryResponse {
  absorbed: MergeHistoryItem[];
  merged_into: MergeHistoryItem[];
}

// ============================================================
// CRM: Deal Detail (enriched)
// ============================================================

export interface CrmDealDetail extends CrmDeal {
  property_address?: string;
  property_city?: string;
  group_name?: string;
}

// ============================================================
// CRM: Group Contact Links
// ============================================================

export interface GroupContactLink {
  id: string;
  display_name: string;
  phone: string | null;
  email: string | null;
  job_title: string | null;
  status: string;
  transaction_count: number;
  contact_type: string | null;
  link_type: "derived" | "manual" | "both";
  is_current: boolean;
  role: string | null;
  link_notes: string | null;
}

export interface GroupContactsResponse {
  contacts: GroupContactLink[];
  total: number;
}

// ============================================================
// Audit Log
// ============================================================

export interface AuditLogEntry {
  id: number;
  user_id: number | null;
  action: string;
  entity_type: string;
  entity_id: string;
  details: Record<string, unknown> | null;
  created_at: string;
  username: string | null;
  display_name: string | null;
}

// ============================================================
// GeoJSON (for map)
// ============================================================

export interface GeoPropertyFeature {
  type: "Feature";
  geometry: { type: "Point"; coordinates: [number, number] };
  properties: {
    id: string;
    address: string;
    city: string;
    owner: string | null;
    latest_price: number | null;
    latest_date: string | null;
    transaction_count: number;
    primary_property_type?: string;
    tenant_brands: string[];
    tenant_categories: string[];
  };
}

export interface GeoResponse {
  type: "FeatureCollection";
  features: GeoPropertyFeature[];
  total: number;
}

// ============================================================
// Group Consolidation (contact-centric merge workflow)
// ============================================================

export interface AffiliatedGroup {
  id: string;
  display_name: string;
  normalized_name: string;
  status: string;
  property_count: number;
  transaction_count: number;
  contact_count: number;
  is_current_group: number;
  shared_transactions: number;
}

export interface AffiliatedGroupsResponse {
  contact: { id: string; display_name: string };
  affiliated_groups: AffiliatedGroup[];
}

export interface CreateGroupResponse {
  id: string;
  display_name: string;
  normalized_name: string;
}

export interface MergePreviewResponse {
  source_count: number;
  target_id: string;
  affected_contacts: { id: string; name: string }[];
  affected_properties: number;
  affected_transactions: number;
}

// ============================================================
// Brand Registry
// ============================================================

export interface BrandItem {
  brand: string;
  category: string | null;
  poi_count: number;
  is_curated: boolean;
  is_favorite: boolean;
}

export interface BrandBrowseResponse {
  brands: BrandItem[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
}

export interface BrandFavorite {
  brand: string;
  category: string | null;
  poi_count: number;
  is_curated: boolean;
}

export interface BrandFavoritesResponse {
  favorites: BrandFavorite[];
}

export interface BrandCategory {
  id: string;
  color: string;
}

export interface BrandCategoriesResponse {
  categories: BrandCategory[];
}

// ── Sell Opportunities ──

export type SellOppStatus = "active" | "on_hold" | "stale" | "matched" | "closed_won" | "closed_lost";

export interface SellOpportunity {
  id: string;
  property_id: string;
  seller_contact_id: string | null;
  seller_group_id: string | null;
  deal_value: number | null;
  status: SellOppStatus;
  owner: string | null;
  notes: string | null;
  last_activity_at: string;
  decay_days: number;
  created_at: string;
  updated_at: string;
  // Joined fields
  display_address: string;
  city: string | null;
  region: string | null;
  asset_class: string | null;
  lat: number | null;
  lng: number | null;
  most_recent_sale_price: number | null;
  most_recent_sale_date: string | null;
  seller_contact_name: string | null;
  seller_group_name: string | null;
  is_stale: number;
  days_since_activity: number;
}

export interface SellOpportunityDetail extends SellOpportunity {
  acreage: number | null;
  current_owner_name: string | null;
  current_owner_group_id: string | null;
  seller_contact_phone: string | null;
  seller_contact_email: string | null;
  activities: Activity[];
  matching_mandates: MatchingMandate[];
}

export interface MatchingMandate {
  id: string;
  contact_id: string | null;
  group_id: string | null;
  criteria_json: string | null;
  status: string;
  owner: string | null;
  contact_name: string | null;
  group_name: string | null;
  match_score: number;
}

// ── Buy Mandates ──

export type BuyMandateStatus = "active" | "on_hold" | "stale" | "fulfilled";

export interface BuyMandateCriteria {
  asset_classes?: string[];
  asset_subclasses?: string[];
  regions?: string[];
  cities?: string[];
  price_min?: number;
  price_max?: number;
  sqft_min?: number;
  sqft_max?: number;
  market_type?: string;
  max_distance_from_city_km?: number;
}

export interface BuyMandate {
  id: string;
  contact_id: string | null;
  group_id: string | null;
  criteria_json: string | null;
  criteria: BuyMandateCriteria;
  status: BuyMandateStatus;
  owner: string | null;
  notes: string | null;
  last_activity_at: string;
  decay_days: number;
  created_at: string;
  updated_at: string;
  // Joined fields
  contact_name: string | null;
  group_name: string | null;
  is_stale: number;
  days_since_activity: number;
}

export interface BuyMandateDetail extends BuyMandate {
  contact_phone: string | null;
  contact_email: string | null;
  activities: Activity[];
  matching_properties: MatchingProperty[];
}

export interface MatchingProperty {
  id: string;
  display_address: string;
  city: string | null;
  region: string | null;
  asset_class: string | null;
  most_recent_sale_price: number | null;
  most_recent_sale_date: string | null;
  lat: number | null;
  lng: number | null;
  current_owner_name: string | null;
  current_owner_group_id: string | null;
  sell_opportunity_id: string | null;
  sell_opportunity_status: string | null;
  deal_value: number | null;
}

// ── Activities ──

export type ActivityType = "call" | "email" | "meeting" | "note";
export type ActivityEntityType = "sell_opportunity" | "buy_mandate" | "deal" | "contact" | "group";

export interface Activity {
  id: number;
  entity_type: ActivityEntityType;
  entity_id: string;
  activity_type: ActivityType;
  outcome: string | null;
  summary: string | null;
  next_step: string | null;
  created_by: string | null;
  created_at: string;
}

// ── Stale Entities ──

export interface StaleEntitiesResponse {
  sell_opportunities: SellOpportunity[];
  buy_mandates: BuyMandate[];
  total_stale: number;
}

// ── Filter Responses ──

export interface SellOppFilters {
  regions: string[];
  asset_classes: string[];
  owners: string[];
}

export interface BuyMandateFilters {
  owners: string[];
}
