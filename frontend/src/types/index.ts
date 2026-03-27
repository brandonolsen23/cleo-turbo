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
  current_owner_name: string | null;
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
  transaction_count: number;
  lat: number | null;
  lng: number | null;
  parcel_geojson: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
  transactions: PropertyTransaction[];
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
  consideration_json: ConsiderationData | null;
  broker_json: BrokerData | null;
  photos_json: string[] | null;
  source_folder: string | null;
  created_at: string;
  parties: TransactionParty[];
}

export interface ConsiderationData {
  cash?: number;
  assumed_debt?: number;
  chattels?: number;
  verbatim?: string;
  chargees?: string[];
}

export interface BrokerData {
  name?: string;
  phone?: string;
}

// ============================================================
// Contacts
// ============================================================

export interface ContactBrowseItem {
  id: string;
  display_name: string;
  phone: string | null;
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
  recent_transactions: {
    source_id: string;
    display_address: string;
    city: string;
    sale_date: string | null;
    sale_price: number | null;
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
// Filters
// ============================================================

export interface FilterOptions {
  cities: string[];
  regions: string[];
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
  };
}

export interface GeoResponse {
  type: "FeatureCollection";
  features: GeoPropertyFeature[];
  total: number;
}
