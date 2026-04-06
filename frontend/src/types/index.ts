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
  lat: number | null;
  lng: number | null;
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
  transaction_count: number;
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
  status: string;
  source: string | null;
  transaction_count: number;
  first_seen_date: string | null;
  last_seen_date: string | null;
  hubspot_id: string | null;
  created_at: string;
  updated_at: string;
  transactions: ContactTransaction[];
  current_group: { id: string; display_name: string; status: string } | null;
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
}

export interface GroupKnownName {
  name: string;
  normalized: string;
  source_id: string;
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
