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
  seller_mailing_address?: { display: string | null; city: string | null; province: string | null; postal: string | null } | null;
  buyer_mailing_address?: { display: string | null; city: string | null; province: string | null; postal: string | null } | null;
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
  has_source_html?: boolean;
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
  has_source_html?: boolean;
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
  mailing_city: string | null;
  dominant_type: string | null;
  secondary_type: string | null;
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
  brands: TransactionBrand[];
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
  linkedin_url: string | null;
  linkedin_headline: string | null;
  linkedin_photo_url: string | null;
  linkedin_enriched_at: string | null;
  datanyze_contacts: {
    emails: { value: string; type: string; source: string }[];
    phones: { value: string; type: string; source: string }[];
  } | null;
  work_history: WorkHistoryPosition[];
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
  dominant_type: string | null;
  secondary_type: string | null;
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

export interface TransactionBrand {
  brand: string;
  category: string;
}

export interface GroupTransaction {
  source_id: string;
  sale_date: string | null;
  sale_price: number | null;
  display_address: string;
  city: string;
  side: string;
  party_name: string | null;
  brands: TransactionBrand[];
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
  brands: TransactionBrand[];
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
  corporate_address: string | null;
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

export interface GroupSearchResult {
  id: string;
  display_name: string;
  status: string;
  property_count: number;
  transaction_count: number;
  contact_count: number;
}

export interface GroupSearchResponse {
  results: GroupSearchResult[];
  total: number;
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
  noi: number | null;
  expected_cap_rate: number | null;
  expected_price: number | null;
  commission_pct: number | null;
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

export type TenantQuality = "national_credit" | "regional_credit" | "local" | "any";
export type OccupancyType = "single" | "multi" | "either";
export type AnchoredPreference = "grocery" | "big_box" | "none";
export type MarketTier = "primary" | "secondary" | "tertiary";
export type InvestmentStrategy = "core" | "core_plus" | "value_add" | "opportunistic";
export type VacancyTolerance = "fully_leased" | "some_vacancy" | "high_vacancy";
export type MandatePriority = "primary" | "secondary" | "exploratory";
export type MandateTimeline = "immediate" | "near_term" | "medium" | "long_term";

export interface BuyMandateCriteria {
  // Property type
  asset_classes?: string[];
  asset_subclasses?: string[];
  zoning_notes?: string;

  // Tenant preferences
  tenant_quality?: TenantQuality;
  tenant_categories?: string[];
  occupancy_type?: OccupancyType;
  anchored_preference?: AnchoredPreference;

  // Location
  regions?: string[];
  cities?: string[];
  market_tiers?: MarketTier[];

  // Financial
  price_min?: number;
  price_max?: number;
  cap_rate_min?: number;
  cap_rate_max?: number;
  noi_min?: number;
  noi_max?: number;

  // Size & physical
  sqft_min?: number;
  sqft_max?: number;
  acreage_min?: number;
  acreage_max?: number;
  unit_count_min?: number;
  unit_count_max?: number;

  // Investment profile
  investment_strategy?: InvestmentStrategy;
  vacancy_tolerance?: VacancyTolerance;

  // Timing & priority
  priority?: MandatePriority;
  timeline?: MandateTimeline;
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
  asset_subclass: string | null;
  acreage: number | null;
  most_recent_sale_price: number | null;
  most_recent_sale_date: string | null;
  lat: number | null;
  lng: number | null;
  current_owner_name: string | null;
  current_owner_group_id: string | null;
  sell_opportunity_id: string | null;
  sell_opportunity_status: string | null;
  deal_value: number | null;
  noi: number | null;
  implied_cap_rate: number | null;
  unit_count: number | null;
  vacancy_pct: number | null;
}

// ── Tenant Categories ──

export interface TenantSubcategory {
  id: string;
  label: string;
}

export interface TenantCategory {
  id: string;
  label: string;
  subcategories: TenantSubcategory[];
}

export interface TenantCategoriesResponse {
  categories: TenantCategory[];
}

// ── Asset Classes ──

export interface AssetSubclass {
  id: string;
  label: string;
}

export interface AssetClass {
  id: string;
  label: string;
  subcategories: AssetSubclass[];
}

export interface AssetClassesResponse {
  classes: AssetClass[];
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

// ============================================================
// Group Comparison (evidence-based merge verification)
// ============================================================

export interface CompareGroupMailingAddress {
  display: string;
  city: string | null;
  province: string | null;
  postal: string | null;
  usage_count: number;
}

export interface CompareGroupTransaction {
  source_id: string;
  sale_date: string | null;
  sale_price: number | null;
  display_address: string;
  city: string;
  side: string;
  party_name: string | null;
  party_phone: string | null;
}

export interface CompareGroupContact {
  id: string;
  display_name: string;
  phone: string | null;
  job_title: string | null;
  contact_type: string | null;
  transaction_count: number;
  first_seen_date: string | null;
  last_seen_date: string | null;
  linkedin_url: string | null;
  linkedin_headline: string | null;
}

export interface WorkHistoryPosition {
  id: number;
  company: string;
  title: string | null;
  start_date: string | null;
  end_date: string | null;
  is_current: boolean;
  location: string | null;
  company_logo_url: string | null;
}

export interface ContactWorkHistoryResponse {
  contact_id: string;
  linkedin_url: string | null;
  linkedin_headline: string | null;
  linkedin_photo_url: string | null;
  linkedin_enriched_at: string | null;
  positions: WorkHistoryPosition[];
}

export interface CompareGroupData {
  id: string;
  display_name: string;
  normalized_name: string;
  status: string;
  property_count: number;
  transaction_count: number;
  contact_count: number;
  hq_address: string | null;
  contacts: CompareGroupContact[];
  known_names: { name: string; normalized: string }[];
  mailing_addresses: CompareGroupMailingAddress[];
  recent_transactions: CompareGroupTransaction[];
}

export interface SharedAddress {
  display: string;
  city: string | null;
  postal: string | null;
  group_ids: string;
  group_count: number;
  total_txns: number;
}

export interface SharedContact {
  id: string;
  display_name: string;
  phone: string | null;
  job_title: string | null;
  group_ids: string[];
  group_count: number;
  earliest_date: string | null;
  latest_date: string | null;
  linkedin_url: string | null;
}

export interface SharedPhone {
  phone: string;
  group_count: number;
  contacts: { contact_id: string; display_name: string; group_id: string }[];
}

export interface GroupCompareResponse {
  groups: Record<string, CompareGroupData>;
  shared_addresses: SharedAddress[];
  shared_contacts: SharedContact[];
  shared_phones: SharedPhone[];
  match_tier: number;
  match_reasons: string[];
}

// ── Address-Based Suggestions ──

export interface AddressSuggestion {
  group_id: string;
  display_name: string;
  property_count: number;
  transaction_count: number;
  contact_count: number;
  shared_addresses: { address: string; city: string | null; usage_count: number }[];
  shared_contacts: { contact_id: string; name: string; phone: string | null; earliest_date: string | null; latest_date: string | null; linkedin_url: string | null }[];
  shared_phones: { phone: string; other_contact: string }[];
  match_tier: number;
}

export interface AddressSuggestionsResponse {
  group_id: string;
  suggestions: AddressSuggestion[];
  total: number;
}

// ── Discovery ──────────────────────────────────────────────

export interface DiscoveryClusterSummary {
  anchor_group_id: string;
  anchor_name: string;
  member_count: number;
  portfolio_value: number;
  confidence: number;
  signal_count: number;
  status: string;
}

export interface DiscoveryRun {
  run_id: string;
  mode: string;
  started_at: string;
  completed_at: string | null;
  stats: {
    clusters_found: number;
    groups_processed: number;
    evidence_written: number;
    signal_counts: Record<string, number>;
    ground_truth?: Record<string, { precision: number; recall: number; missing: string[]; unexpected: string[] }>;
  } | null;
}

export interface DiscoveryBrowseResponse {
  results: DiscoveryClusterSummary[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
  run: DiscoveryRun | null;
}

export interface DiscoveryEvidence {
  source_group_id: string;
  target_group_id: string;
  signal_type: string;
  signal_value: string;
  source_id: string;
  rule_id: string;
  confidence: number;
  iteration: number;
}

export interface DiscoveryMemberTransaction {
  source_id: string;
  sale_date: string | null;
  sale_price: number | null;
  display_address: string;
  city: string;
  side: string;
  party_name: string | null;
}

export interface DiscoveryClusterDetail {
  anchor: {
    id: string;
    display_name: string;
    normalized_name: string;
    status: string;
    transaction_count: number;
    property_count: number;
  } | null;
  members: {
    id: string;
    display_name: string;
    normalized_name: string;
    status: string;
    transaction_count: number;
    property_count: number;
  }[];
  member_count: number;
  evidence: DiscoveryEvidence[];
  signal_summary: Record<string, string[]>;
  member_transactions: Record<string, DiscoveryMemberTransaction[]>;
}

// ── Labeling ─────────────────────────────────────────────────

export type FieldType =
  | "party_name" | "trade_name" | "care_of" | "company_other"
  | "law_firm" | "contact_name" | "address" | "phone";

export type LinkKind = "exact" | "implied";

export interface LabelingSession {
  id: number;
  display_id: string; // e.g. "LBL_00001"
  name: string;
  audit_slug: string | null;
  anchor_source_id: string;
  anchor_side: "buyer" | "seller";
  status: "active" | "paused" | "done";
  created_by: string;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
  confirmed_count: number;
  rejected_count: number;
  seeds_by_state: Record<string, number>;
}

export interface LabelingSeed {
  id: number;
  session_id: number;
  term: string;
  field_type: FieldType;
  state: "pending" | "in_progress" | "done" | "skipped";
  first_contributed_by_source_id: string;
  first_contributed_by_side: "buyer" | "seller";
  completed_at: string | null;
  created_at: string;
}

export interface LabelingCandidate {
  source_id: string;
  side: "buyer" | "seller";
  match_fields: string[];
}

export interface LabelingLinkInput {
  from_field_type: FieldType;
  from_field_value: string;
  to_field_type: FieldType;
  to_field_value: string;
  kind: LinkKind;
}

export interface LabelingLink extends LabelingLinkInput {
  id: number;
  verdict_id: number;
  created_at: string;
}

export interface LabelingVerdict {
  id: number;
  session_id: number;
  source_id: string;
  side: "buyer" | "seller";
  verdict: "confirmed" | "rejected";
  left_source_id: string;
  left_side: "buyer" | "seller";
  seed_id: number | null;
  rationale: string | null;
  created_by: string;
  created_at: string;
  links?: LabelingLink[];
}

export interface LabelingPartyView {
  source_id: string;
  side: "buyer" | "seller";
  sale_date: string | null;
  party_rows: { id: number; party_name: string | null; phone: string | null; contact_id: string | null }[];
  trade_name: string | null;
  care_of: string | null;
  companies_other: string[];
  law_firms: string[];
  contacts: { id: string; name: string; role: string | null; phone: string | null; job_title: string | null }[];
  mailing: { display: string; city: string; province: string; postal: string } | null;
  phones: string[];
}

export interface LabelingAuditSummary {
  slug: string;
  title: string;
  date_folder: string;
  row_count: number;
  distinct_groups: number;
  distinct_parties: number;
  sessions: { id: number; name: string; status: string; created_at: string }[];
}

export interface LabelingAuditParty {
  source_id: string;
  side: "buyer" | "seller";
  group_id: string;
  party_name: string;
  trade_name: string;
  care_of: string;
  mailing: string;
  phone: string;
}

// ============================================================
// Brand-Token Explorer
// ============================================================

export interface BrandTokenSummary {
  token: string;
  idf: number;
  n_party_sides: number;
  n_distinct_phrases: number;
  is_distinctive: 0 | 1;
  is_excluded: 0 | 1;
  wordfreq_zipf: number | null;
  is_english_common: 0 | 1 | null;
  is_place_name: 0 | 1 | null;
  is_industry_stopword: 0 | 1 | null;
  filter_reason: "excluded" | "industry" | "place" | "english" | null;
}

export interface BrandTokenListResponse {
  results: BrandTokenSummary[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
}

export interface ExplorerBrandPhraseEntry {
  phrase: string;
  source_field: "party_name" | "trade_name" | "care_of" | "companies_json" | "law_firms_json";
  contains_token: boolean;
}

export interface ExplorerPartySide {
  source_id: string;
  side: "buyer" | "seller";
  sale_date: string | null;
  postal: string | null;
  street_number: string | null;
  street_name: string | null;
  street_suffix: string | null;
  phone: string | null;
  contact_fingerprint: string | null;
  brand_phrases: ExplorerBrandPhraseEntry[];
}

export interface BrandTokenDetail extends BrandTokenSummary {
  phrases: string[];
  party_sides: ExplorerPartySide[];
}

// ============================================================
// Brand N-gram Explorer (bigrams + trigrams)
// ============================================================

export interface BrandBigramSummary {
  bigram: string;
  token_a: string;
  token_b: string;
  idf: number;
  n_party_sides: number;
  n_distinct_phrases: number;
  any_token_distinctive: 0 | 1;
  any_token_excluded: 0 | 1;
  all_english: 0 | 1;
  all_place: 0 | 1;
  all_industry: 0 | 1;
  is_distinctive: 0 | 1;
}

export interface BrandBigramListResponse {
  results: BrandBigramSummary[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
}

export interface BrandBigramDetail extends BrandBigramSummary {
  phrases: string[];
  party_sides: ExplorerPartySide[];
}

export interface BrandTrigramSummary extends Omit<BrandBigramSummary, "bigram"> {
  trigram: string;
  token_c: string;
}

export interface BrandTrigramListResponse {
  results: BrandTrigramSummary[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
}

export interface BrandTrigramDetail extends BrandTrigramSummary {
  phrases: string[];
  party_sides: ExplorerPartySide[];
}

// ============================================================
// Explorer — Phones
// ============================================================

export interface PhoneSummary {
  phone: string;
  n_party_sides: number;
}

export interface PhoneListResponse {
  results: PhoneSummary[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
}

export interface PhoneDetail {
  phone: string;
  n_party_sides: number;
  party_sides: ExplorerPartySide[];
}

// ============================================================
// Explorer — Addresses
// ============================================================

export interface AddressBaseSummary {
  street_number: string;
  street_name: string;
  street_suffix: string;
  n_party_sides: number;
  n_distinct_suites: number;
  n_distinct_postals: number;
  key: string;  // "num|name|suffix" for URL path
}

export interface AddressBaseListResponse {
  results: AddressBaseSummary[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
}

export interface AddressSuiteVariant {
  suite_type: string | null;
  suite_number: string | null;
  postal: string | null;
  n_party_sides: number;
}

export interface AddressBaseDetail extends AddressBaseSummary {
  suite_variants: AddressSuiteVariant[];
  party_sides: ExplorerPartySide[];
}
