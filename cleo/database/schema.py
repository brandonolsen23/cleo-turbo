"""
SQLite schema — all CREATE TABLE statements for Cleo Turbo.

Two categories:
  - Derived tables: rebuilt by the Compiler from clean-data/
  - CRM tables: persistent, user-curated, never rebuilt

Usage:
    from cleo.database.schema import create_all_tables, drop_derived_tables
    from cleo.database.connection import get_connection

    conn = get_connection()
    create_all_tables(conn)
"""

DERIVED_TABLES = """
-- ============================================================
-- DERIVED TABLES (rebuilt by Compiler, IDs persist via reconciliation)
-- ============================================================

CREATE TABLE IF NOT EXISTS properties (
    id              TEXT PRIMARY KEY,
    arn             TEXT UNIQUE NOT NULL,
    display_address TEXT,
    city            TEXT,
    region          TEXT,
    postal          TEXT,
    acreage         REAL,
    building_size_raw   TEXT,
    building_size_value REAL,
    building_size_unit  TEXT,
    legal_description TEXT,
    current_owner_name TEXT,
    current_owner_group_id TEXT,
    most_recent_source_id TEXT,
    most_recent_sale_date TEXT,
    most_recent_sale_price INTEGER,
    most_recent_sale_source TEXT,
    transaction_count INTEGER DEFAULT 0,
    primary_property_type TEXT,
    asset_class      TEXT,
    asset_subclass   TEXT,
    gw_municipality  TEXT,
    lat             REAL,
    lng             REAL,
    parcel_geojson  TEXT,
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS transactions (
    source_id       TEXT PRIMARY KEY,
    property_id     TEXT REFERENCES properties(id),
    arn             TEXT,
    sale_date       TEXT,
    sale_price      INTEGER,
    transaction_note TEXT,
    display_address TEXT,
    city            TEXT,
    region          TEXT,
    postal          TEXT,
    seller_parties  TEXT,
    buyer_parties   TEXT,
    seller_phone    TEXT,
    buyer_phone     TEXT,
    description     TEXT,
    acreage         REAL,
    building_size_raw   TEXT,
    building_size_value REAL,
    building_size_unit  TEXT,
    pin             TEXT,
    legal_description TEXT,
    pin_display      TEXT,
    arn_display      TEXT,
    pin_multiple     INTEGER DEFAULT 0,
    parcel_method    TEXT,
    parcel_loc_name      TEXT,
    parcel_addr_type     TEXT,
    parcel_geocode_score REAL,
    parcel_field_match   INTEGER,
    parcel_containment   TEXT,
    parcel_confidence    REAL,
    pip_verified         INTEGER,
    parcel_tier          TEXT,
    location         TEXT,
    surface_rights_only INTEGER DEFAULT 0,
    more_info_url    TEXT,
    cash             INTEGER,
    debt             INTEGER,
    chattels         INTEGER,
    other_consideration INTEGER,
    charges_json     TEXT,
    seller_trade_name TEXT,
    seller_care_of   TEXT,
    seller_law_firms_json TEXT,
    seller_companies_json TEXT,
    buyer_trade_name TEXT,
    buyer_care_of    TEXT,
    buyer_law_firms_json TEXT,
    buyer_companies_json TEXT,
    photos_json     TEXT,
    source_folder   TEXT,
    source_position INTEGER,
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS contacts (
    id              TEXT PRIMARY KEY,
    name_fingerprint TEXT UNIQUE NOT NULL,
    first_name      TEXT,
    last_name       TEXT,
    display_name    TEXT,
    phone           TEXT,
    email           TEXT,
    mobile          TEXT,
    job_title       TEXT,
    company_name    TEXT,
    current_group_id TEXT,
    current_auto_group_id TEXT,
    contact_type    TEXT,
    status          TEXT NOT NULL DEFAULT 'pool',
    source          TEXT DEFAULT 'transaction',
    transaction_count INTEGER DEFAULT 0,
    first_seen_date TEXT,
    last_seen_date  TEXT,
    hubspot_id      TEXT,
    last_engaged_date TEXT,
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS groups (
    id              TEXT PRIMARY KEY,
    display_name    TEXT NOT NULL,
    normalized_name TEXT UNIQUE NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pool',
    property_count  INTEGER DEFAULT 0,
    transaction_count INTEGER DEFAULT 0,
    contact_count   INTEGER DEFAULT 0,
    hq_address      TEXT,
    website         TEXT,
    hubspot_id      TEXT,
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS group_names (
    group_id        TEXT NOT NULL REFERENCES groups(id),
    name            TEXT NOT NULL,
    normalized      TEXT NOT NULL,
    source_id       TEXT,
    PRIMARY KEY (group_id, normalized)
);

CREATE TABLE IF NOT EXISTS transaction_parties (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id       TEXT NOT NULL REFERENCES transactions(source_id),
    contact_id      TEXT REFERENCES contacts(id),
    group_id        TEXT REFERENCES groups(id),
    side            TEXT NOT NULL,
    party_name      TEXT,
    contact_title   TEXT,
    phone           TEXT
);

CREATE TABLE IF NOT EXISTS transaction_mailing_addresses (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id       TEXT NOT NULL REFERENCES transactions(source_id),
    side            TEXT NOT NULL,
    display         TEXT,
    street_number   TEXT,
    street_name     TEXT,
    street_suffix   TEXT,
    street_direction TEXT,
    suite_type      TEXT,
    suite_number    TEXT,
    city            TEXT,
    province        TEXT,
    postal          TEXT,
    country         TEXT,
    geocode_string  TEXT,
    UNIQUE(source_id, side)
);


CREATE TABLE IF NOT EXISTS transaction_brokers (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id       TEXT NOT NULL REFERENCES transactions(source_id),
    broker_name     TEXT,
    phone           TEXT,
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS transaction_broker_agents (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    broker_id       INTEGER NOT NULL REFERENCES transaction_brokers(id),
    agent_name      TEXT,
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS pois (
    id              TEXT PRIMARY KEY,
    source          TEXT NOT NULL,
    brand           TEXT NOT NULL,
    category        TEXT,
    name            TEXT,
    lat             REAL NOT NULL,
    lng             REAL NOT NULL,
    address         TEXT,
    city            TEXT,
    phone           TEXT,
    website         TEXT,
    property_id     TEXT REFERENCES properties(id),
    arn             TEXT,
    cuisine         TEXT,
    operator        TEXT,
    facebook        TEXT,
    instagram       TEXT,
    drive_through   TEXT,
    osm_id          TEXT,
    building_geojson TEXT,
    approx_sqft     INTEGER,
    address_source  TEXT,
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS brand_registry (
    brand           TEXT PRIMARY KEY,
    category        TEXT,
    poi_count       INTEGER DEFAULT 0,
    is_curated      INTEGER DEFAULT 0,
    sample_osm_tags TEXT,
    created_at      TEXT DEFAULT (datetime('now'))
);

-- ============================================================
-- PARTY FINGERPRINTS (atom-based portfolio discovery foundation)
-- ============================================================

CREATE TABLE IF NOT EXISTS party_fingerprints (
    source_id           TEXT NOT NULL,
    side                TEXT NOT NULL CHECK (side IN ('buyer','seller')),
    -- address atoms (canonical forms from cleo.atoms.normalize)
    street_number       TEXT,
    street_name         TEXT,
    street_suffix       TEXT,
    street_direction    TEXT,
    suite_type          TEXT,
    suite_number        TEXT,
    city                TEXT,
    province            TEXT,
    postal              TEXT,
    postal_raw          TEXT,
    country             TEXT,
    -- phone (digits only, country code stripped)
    phone               TEXT,
    -- contact (first+last canonical)
    contact_fingerprint TEXT,
    -- temporal context (for later tenure reasoning)
    sale_date           TEXT,
    -- canonical address and property identity (populated by compiler fingerprint pass)
    property_canonical_id   TEXT,
    party_address_canonical TEXT,
    -- bookkeeping
    computed_at         TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (source_id, side)
);

CREATE TABLE IF NOT EXISTS party_atoms (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id    TEXT NOT NULL,
    side         TEXT NOT NULL CHECK (side IN ('buyer','seller')),
    atom_type    TEXT NOT NULL,     -- 'brand_phrase' | 'brand_token' | 'law_firm_phrase' | 'law_firm_token'
    atom_value   TEXT NOT NULL,     -- canonical form from cleo.atoms.normalize
    source_field TEXT NOT NULL      -- 'party_name' | 'trade_name' | 'care_of' | 'companies_json' | 'law_firms_json'
);

CREATE TABLE IF NOT EXISTS gw_assessments (
    id              TEXT PRIMARY KEY,
    gw_id           TEXT NOT NULL,
    property_id     TEXT REFERENCES properties(id),
    arn             TEXT,
    pin             TEXT,
    assessed_value  INTEGER,
    valuation_date  TEXT,
    zoning          TEXT,
    property_code   TEXT,
    property_description TEXT,
    ownership_type  TEXT,
    frontage_ft     REAL,
    depth_ft        REAL,
    site_area_sqft  REAL,
    acreage         REAL,
    owner_name      TEXT,
    owner_mailing   TEXT,
    legal_description TEXT,
    source_file     TEXT,
    land_registry_status TEXT,
    registration_type TEXT,
    lro              TEXT,
    municipality     TEXT,
    has_mpac_data    INTEGER DEFAULT 0,
    is_active        INTEGER DEFAULT 0,
    address_parsed   INTEGER DEFAULT 0,
    parcel_resolved  INTEGER DEFAULT 0,
    created_at      TEXT DEFAULT (datetime('now'))
);
"""

DERIVED_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_properties_city ON properties(city);
CREATE INDEX IF NOT EXISTS idx_properties_region ON properties(region);
CREATE INDEX IF NOT EXISTS idx_properties_owner ON properties(current_owner_group_id);
CREATE INDEX IF NOT EXISTS idx_properties_sale_date ON properties(most_recent_sale_date);
CREATE INDEX IF NOT EXISTS idx_properties_sale_price ON properties(most_recent_sale_price);
CREATE INDEX IF NOT EXISTS idx_properties_asset_class ON properties(asset_class);
CREATE INDEX IF NOT EXISTS idx_properties_asset_subclass ON properties(asset_subclass);
CREATE INDEX IF NOT EXISTS idx_properties_building_size ON properties(building_size_unit, building_size_value);
CREATE INDEX IF NOT EXISTS idx_transactions_property ON transactions(property_id);
CREATE INDEX IF NOT EXISTS idx_transactions_arn ON transactions(arn);
CREATE INDEX IF NOT EXISTS idx_transactions_sale_date ON transactions(sale_date);
CREATE INDEX IF NOT EXISTS idx_transactions_city ON transactions(city);
CREATE INDEX IF NOT EXISTS idx_contacts_contact_type ON contacts(contact_type);
CREATE INDEX IF NOT EXISTS idx_contacts_status ON contacts(status);
CREATE INDEX IF NOT EXISTS idx_contacts_fingerprint ON contacts(name_fingerprint);
CREATE INDEX IF NOT EXISTS idx_contacts_group ON contacts(current_group_id);
CREATE INDEX IF NOT EXISTS idx_groups_status ON groups(status);
CREATE INDEX IF NOT EXISTS idx_groups_normalized ON groups(normalized_name);
CREATE INDEX IF NOT EXISTS idx_group_names_normalized ON group_names(normalized);
CREATE INDEX IF NOT EXISTS idx_transaction_parties_source ON transaction_parties(source_id);
CREATE INDEX IF NOT EXISTS idx_transaction_parties_contact ON transaction_parties(contact_id);
CREATE INDEX IF NOT EXISTS idx_transaction_parties_group ON transaction_parties(group_id);
CREATE INDEX IF NOT EXISTS idx_tx_addr_source ON transaction_mailing_addresses(source_id);
CREATE INDEX IF NOT EXISTS idx_tx_addr_city ON transaction_mailing_addresses(city);
CREATE INDEX IF NOT EXISTS idx_tx_cash ON transactions(cash);
CREATE INDEX IF NOT EXISTS idx_tx_broker_source ON transaction_brokers(source_id);
CREATE INDEX IF NOT EXISTS idx_tx_agent_broker ON transaction_broker_agents(broker_id);
CREATE INDEX IF NOT EXISTS idx_pois_property ON pois(property_id);
CREATE INDEX IF NOT EXISTS idx_pois_brand ON pois(brand);
CREATE INDEX IF NOT EXISTS idx_pois_category ON pois(category);
CREATE INDEX IF NOT EXISTS idx_pois_arn ON pois(arn);
CREATE INDEX IF NOT EXISTS idx_brand_registry_category ON brand_registry(category);
CREATE INDEX IF NOT EXISTS idx_brand_registry_curated ON brand_registry(is_curated);
CREATE TABLE IF NOT EXISTS gw_sales_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    gw_id           TEXT NOT NULL,
    property_id     TEXT,
    arn             TEXT,
    sale_date       TEXT,
    amount          INTEGER,
    sale_type       TEXT,
    party_to        TEXT,
    notes           TEXT,
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_gw_sales_gw_id ON gw_sales_history(gw_id);
CREATE INDEX IF NOT EXISTS idx_gw_sales_date ON gw_sales_history(sale_date);
CREATE INDEX IF NOT EXISTS idx_gw_sales_amount ON gw_sales_history(amount);
CREATE INDEX IF NOT EXISTS idx_gw_sales_property ON gw_sales_history(property_id);
CREATE INDEX IF NOT EXISTS idx_gw_property ON gw_assessments(property_id);
CREATE INDEX IF NOT EXISTS idx_gw_arn ON gw_assessments(arn);
CREATE INDEX IF NOT EXISTS idx_gw_gw_id ON gw_assessments(gw_id);
CREATE INDEX IF NOT EXISTS idx_pfp_street_key ON party_fingerprints(street_number, street_name, street_suffix);
CREATE INDEX IF NOT EXISTS idx_pfp_postal ON party_fingerprints(postal);
CREATE INDEX IF NOT EXISTS idx_pfp_phone ON party_fingerprints(phone);
CREATE INDEX IF NOT EXISTS idx_pfp_contact ON party_fingerprints(contact_fingerprint);
CREATE INDEX IF NOT EXISTS idx_pf_property_canonical ON party_fingerprints(property_canonical_id);
CREATE INDEX IF NOT EXISTS idx_pf_party_addr_canonical ON party_fingerprints(party_address_canonical);
CREATE INDEX IF NOT EXISTS idx_pa_lookup ON party_atoms(atom_type, atom_value);
CREATE INDEX IF NOT EXISTS idx_pa_party ON party_atoms(source_id, side);
"""

FTS_TABLES = """
CREATE VIRTUAL TABLE IF NOT EXISTS properties_fts USING fts5(
    id, display_address, city, region, current_owner_name,
    content='properties', content_rowid='rowid',
    tokenize='unicode61'
);

CREATE VIRTUAL TABLE IF NOT EXISTS contacts_fts USING fts5(
    id, display_name, first_name, last_name, phone, company_name,
    content='contacts', content_rowid='rowid',
    tokenize='unicode61'
);

CREATE VIRTUAL TABLE IF NOT EXISTS groups_fts USING fts5(
    id, display_name,
    content='groups', content_rowid='rowid',
    tokenize='unicode61'
);

CREATE VIRTUAL TABLE IF NOT EXISTS transactions_fts USING fts5(
    source_id, display_address, city, region, seller_parties, buyer_parties,
    content='transactions', content_rowid='rowid',
    tokenize='unicode61'
);
"""

CRM_TABLES = """
-- ============================================================
-- CRM TABLES (persistent, never rebuilt by Compiler)
-- ============================================================

CREATE TABLE IF NOT EXISTS deals (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    stage           TEXT NOT NULL DEFAULT 'prospecting',
    amount          INTEGER,
    close_date      TEXT,
    property_id     TEXT REFERENCES properties(id),
    group_id        TEXT REFERENCES groups(id),
    deal_owner      TEXT,
    description     TEXT,
    next_step       TEXT,
    priority        TEXT,
    lost_reason     TEXT,
    hubspot_id      TEXT,
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS lists (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    description     TEXT,
    owner_user_id   INTEGER REFERENCES users(id),
    scope           TEXT NOT NULL DEFAULT 'personal',
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS list_members (
    list_id         TEXT NOT NULL REFERENCES lists(id),
    member_type     TEXT NOT NULL,
    member_id       TEXT NOT NULL,
    added_at        TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (list_id, member_type, member_id)
);

CREATE TABLE IF NOT EXISTS user_stars (
    user_id      INTEGER NOT NULL REFERENCES users(id),
    entity_type  TEXT    NOT NULL CHECK(entity_type IN ('contact','property','group')),
    entity_id    TEXT    NOT NULL,
    starred_at   TEXT    DEFAULT (datetime('now')),
    PRIMARY KEY (user_id, entity_type, entity_id)
);
CREATE INDEX IF NOT EXISTS idx_user_stars_user   ON user_stars(user_id);
CREATE INDEX IF NOT EXISTS idx_user_stars_entity ON user_stars(entity_type, entity_id);

CREATE TABLE IF NOT EXISTS group_contacts (
    group_id        TEXT NOT NULL REFERENCES groups(id),
    contact_id      TEXT NOT NULL REFERENCES contacts(id),
    is_current      INTEGER DEFAULT 1,
    role            TEXT,
    notes           TEXT,
    linked_at       TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (group_id, contact_id)
);

CREATE TABLE IF NOT EXISTS contact_notes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_id      TEXT NOT NULL REFERENCES contacts(id),
    note            TEXT NOT NULL,
    created_by      TEXT,
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS group_notes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id        TEXT NOT NULL REFERENCES groups(id),
    note            TEXT NOT NULL,
    created_by      TEXT,
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS group_merges (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source_group_id TEXT NOT NULL,
    target_group_id TEXT NOT NULL,
    merged_by       TEXT,
    merged_at       TEXT DEFAULT (datetime('now')),
    unmerged_at     TEXT,
    unmerged_by     TEXT
);

CREATE INDEX IF NOT EXISTS idx_group_merges_source ON group_merges(source_group_id);
CREATE INDEX IF NOT EXISTS idx_group_merges_target ON group_merges(target_group_id);
CREATE INDEX IF NOT EXISTS idx_group_merges_active ON group_merges(source_group_id) WHERE unmerged_at IS NULL;

CREATE TABLE IF NOT EXISTS brand_overrides (
    brand           TEXT PRIMARY KEY,
    category        TEXT NOT NULL,
    updated_by      TEXT,
    updated_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS user_brand_favorites (
    user_id         INTEGER NOT NULL REFERENCES users(id),
    brand           TEXT NOT NULL,
    created_at      TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (user_id, brand)
);

CREATE INDEX IF NOT EXISTS idx_user_brand_favorites_user ON user_brand_favorites(user_id);

CREATE TABLE IF NOT EXISTS group_overrides (
    group_id         TEXT PRIMARY KEY,
    display_name     TEXT NOT NULL,
    normalized_name  TEXT NOT NULL UNIQUE,
    created_by       TEXT,
    created_at       TEXT DEFAULT (datetime('now')),
    notes            TEXT
);

CREATE TABLE IF NOT EXISTS group_field_overrides (
    group_id    TEXT PRIMARY KEY,
    status      TEXT,
    hq_address  TEXT,
    website     TEXT,
    hubspot_id  TEXT,
    updated_by  TEXT,
    updated_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS contact_field_overrides (
    contact_id  TEXT PRIMARY KEY,
    email       TEXT,
    mobile      TEXT,
    phone       TEXT,
    job_title   TEXT,
    contact_type TEXT,
    status      TEXT,
    linkedin_url TEXT,
    linkedin_headline TEXT,
    linkedin_enriched_at TEXT,
    linkedin_photo_url TEXT,
    datanyze_raw TEXT,
    updated_by  TEXT,
    updated_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS contact_work_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_id  TEXT NOT NULL,
    company     TEXT NOT NULL,
    title       TEXT,
    start_date  TEXT,
    end_date    TEXT,
    is_current  INTEGER DEFAULT 0,
    location    TEXT,
    company_logo_url TEXT,
    created_at  TEXT DEFAULT (datetime('now'))
);

-- ── Sell Opportunities ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS sell_opportunities (
    id                  TEXT PRIMARY KEY,
    property_id         TEXT NOT NULL REFERENCES properties(id),
    seller_contact_id   TEXT REFERENCES contacts(id),
    seller_group_id     TEXT REFERENCES groups(id),
    noi                 INTEGER,
    expected_cap_rate   REAL,
    expected_price      INTEGER,
    commission_pct      REAL,
    deal_value          INTEGER,
    status              TEXT NOT NULL DEFAULT 'active',
    owner               TEXT,
    notes               TEXT,
    last_activity_at    TEXT DEFAULT (datetime('now')),
    decay_days          INTEGER DEFAULT 14,
    created_at          TEXT DEFAULT (datetime('now')),
    updated_at          TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_sell_opps_property ON sell_opportunities(property_id);
CREATE INDEX IF NOT EXISTS idx_sell_opps_status ON sell_opportunities(status);
CREATE INDEX IF NOT EXISTS idx_sell_opps_seller_contact ON sell_opportunities(seller_contact_id);
CREATE INDEX IF NOT EXISTS idx_sell_opps_seller_group ON sell_opportunities(seller_group_id);

-- ── Buy Mandates ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS buy_mandates (
    id                  TEXT PRIMARY KEY,
    contact_id          TEXT REFERENCES contacts(id),
    group_id            TEXT REFERENCES groups(id),
    criteria_json       TEXT,
    status              TEXT NOT NULL DEFAULT 'active',
    owner               TEXT,
    notes               TEXT,
    last_activity_at    TEXT DEFAULT (datetime('now')),
    decay_days          INTEGER DEFAULT 14,
    created_at          TEXT DEFAULT (datetime('now')),
    updated_at          TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_buy_mandates_contact ON buy_mandates(contact_id);
CREATE INDEX IF NOT EXISTS idx_buy_mandates_group ON buy_mandates(group_id);
CREATE INDEX IF NOT EXISTS idx_buy_mandates_status ON buy_mandates(status);

CREATE TABLE IF NOT EXISTS property_enrichment (
    property_id     TEXT PRIMARY KEY REFERENCES properties(id),
    noi             REAL,
    noi_source      TEXT,
    noi_as_of       TEXT,
    unit_count      INTEGER,
    vacancy_pct     REAL,
    updated_at      TEXT DEFAULT (datetime('now'))
);

-- ── Activities ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS activities (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type         TEXT NOT NULL,
    entity_id           TEXT NOT NULL,
    activity_type       TEXT NOT NULL,
    outcome             TEXT,
    summary             TEXT,
    next_step           TEXT,
    created_by          TEXT,
    created_by_user_id  INTEGER REFERENCES users(id),
    source              TEXT NOT NULL DEFAULT 'manual',
    external_id         TEXT,
    happened_at         TEXT,
    contact_id          TEXT REFERENCES contacts(id),
    property_id         TEXT REFERENCES properties(id),
    group_id            TEXT REFERENCES groups(id),
    created_at          TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_activities_entity ON activities(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_activities_created ON activities(created_at);
CREATE INDEX IF NOT EXISTS idx_activities_type ON activities(activity_type);
CREATE INDEX IF NOT EXISTS idx_activities_contact  ON activities(contact_id);
CREATE INDEX IF NOT EXISTS idx_activities_property ON activities(property_id);
CREATE INDEX IF NOT EXISTS idx_activities_group    ON activities(group_id);
CREATE INDEX IF NOT EXISTS idx_activities_user     ON activities(created_by_user_id);
CREATE INDEX IF NOT EXISTS idx_activities_dedupe   ON activities(source, external_id);

-- ============================================================
-- PORTFOLIO CAPTURE (persistent CRM — survives compiler rebuild)
-- Milestone 1. Per-row provenance: source + confidence + web_asserted/
-- registry_confirmed. These tables are NOT in drop_derived_tables(),
-- so captured ownership survives a full compile.
-- ============================================================

CREATE TABLE IF NOT EXISTS group_profile (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id           TEXT REFERENCES groups(id),
    canonical_name     TEXT,
    summary            TEXT,
    business_lines     TEXT,          -- JSON array: owner|developer|property_manager|brokerage
    corp_address       TEXT,
    corp_phone         TEXT,
    fax                TEXT,
    domain             TEXT,
    website            TEXT,
    emails             TEXT,          -- JSON array
    socials            TEXT,          -- JSON array
    partners           TEXT,          -- JSON array
    source_url         TEXT,
    source             TEXT DEFAULT 'web_capture',
    confidence         REAL,
    web_asserted       INTEGER DEFAULT 1,
    registry_confirmed INTEGER DEFAULT 0,
    captured_at        TEXT DEFAULT (datetime('now')),
    captured_by        TEXT,
    updated_at         TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_group_profile_group ON group_profile(group_id);

CREATE TABLE IF NOT EXISTS group_aliases (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id        TEXT NOT NULL REFERENCES groups(id),
    alias           TEXT NOT NULL,
    normalized      TEXT,
    source          TEXT DEFAULT 'web_capture',
    source_url      TEXT,
    confidence      REAL,
    captured_at     TEXT DEFAULT (datetime('now')),
    captured_by     TEXT,
    UNIQUE(group_id, alias)
);

CREATE INDEX IF NOT EXISTS idx_group_aliases_group ON group_aliases(group_id);
CREATE INDEX IF NOT EXISTS idx_group_aliases_norm ON group_aliases(normalized);

CREATE TABLE IF NOT EXISTS group_match_keys (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id        TEXT NOT NULL REFERENCES groups(id),
    key_type        TEXT NOT NULL,   -- address|phone|domain|alias|person|spv_name
    value           TEXT NOT NULL,   -- normalized form (drives the M4 sweep)
    value_raw       TEXT,            -- original as captured
    source          TEXT DEFAULT 'web_capture',
    source_url      TEXT,
    confidence      REAL,
    sweepable       INTEGER DEFAULT 1,  -- 0 = failed the M4 specificity guard; identity only
    captured_at     TEXT DEFAULT (datetime('now')),
    captured_by     TEXT,
    UNIQUE(group_id, key_type, value)
);

CREATE INDEX IF NOT EXISTS idx_group_match_keys_lookup ON group_match_keys(key_type, value);
CREATE INDEX IF NOT EXISTS idx_group_match_keys_group ON group_match_keys(group_id);

-- Source of truth for owner overrides. The compiler re-applies every
-- active row as a final pass on each rebuild (see compiler/owner_overrides.py).
CREATE TABLE IF NOT EXISTS manual_owner_links (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    arn                TEXT NOT NULL,           -- reconciliation key (not address)
    property_id        TEXT,                    -- resolved cache, reconciled on ARN
    group_id           TEXT NOT NULL REFERENCES groups(id),
    relationship       TEXT NOT NULL DEFAULT 'owns',   -- owns|manages|lists
    status             TEXT NOT NULL DEFAULT 'active',  -- active|conflict|superseded
    source             TEXT DEFAULT 'web_capture',
    source_url         TEXT,
    confidence         REAL,
    web_asserted       INTEGER DEFAULT 1,
    registry_confirmed INTEGER DEFAULT 0,
    conflict_note      TEXT,
    captured_at        TEXT DEFAULT (datetime('now')),
    captured_by        TEXT,
    approved_at        TEXT,
    approved_by        TEXT,
    UNIQUE(arn, group_id, relationship)
);

CREATE INDEX IF NOT EXISTS idx_manual_owner_links_arn ON manual_owner_links(arn);
CREATE INDEX IF NOT EXISTS idx_manual_owner_links_group ON manual_owner_links(group_id);
CREATE INDEX IF NOT EXISTS idx_manual_owner_links_status ON manual_owner_links(status);

CREATE TABLE IF NOT EXISTS property_capture (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    arn                TEXT NOT NULL,
    property_id        TEXT,
    property_name      TEXT,
    retail_subtype     TEXT,
    total_sqft         REAL,
    units              INTEGER,
    parking            TEXT,
    floors             INTEGER,
    acreage            REAL,
    vacancy            TEXT,
    asking_rate        TEXT,
    pdf_links          TEXT,         -- JSON array
    source_url         TEXT,
    source             TEXT DEFAULT 'web_capture',
    confidence         REAL,
    web_asserted       INTEGER DEFAULT 1,
    registry_confirmed INTEGER DEFAULT 0,
    captured_at        TEXT DEFAULT (datetime('now')),
    captured_by        TEXT,
    updated_at         TEXT DEFAULT (datetime('now')),
    UNIQUE(arn, source_url)
);

CREATE INDEX IF NOT EXISTS idx_property_capture_arn ON property_capture(arn);

CREATE TABLE IF NOT EXISTS property_tenants (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    arn             TEXT NOT NULL,
    property_id     TEXT,
    unit            TEXT,
    tenant_name     TEXT NOT NULL,
    sqft            REAL,
    is_anchor       INTEGER DEFAULT 0,
    source          TEXT DEFAULT 'web_capture',
    source_url      TEXT,
    confidence      REAL,
    captured_at     TEXT DEFAULT (datetime('now')),
    captured_by     TEXT
);

CREATE INDEX IF NOT EXISTS idx_property_tenants_arn ON property_tenants(arn);

-- Stub home for site-listed assets not yet in Cleo (no RT/GW row).
-- Keyed by resolved ARN; resolved_pid is set when the compiler later
-- builds a real PRO_ row for the same ARN (reconcile on ARN).
CREATE TABLE IF NOT EXISTS manual_properties (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    arn             TEXT NOT NULL UNIQUE,
    display_address TEXT,
    city            TEXT,
    province        TEXT,
    postal          TEXT,
    resolved_pid    TEXT,
    source          TEXT DEFAULT 'web_capture',
    source_url      TEXT,
    confidence      REAL,
    captured_at     TEXT DEFAULT (datetime('now')),
    captured_by     TEXT
);

CREATE INDEX IF NOT EXISTS idx_manual_properties_arn ON manual_properties(arn);
CREATE INDEX IF NOT EXISTS idx_manual_properties_resolved ON manual_properties(resolved_pid);
"""

SYSTEM_TABLES = """
-- ============================================================
-- SYSTEM TABLES
-- ============================================================

CREATE TABLE IF NOT EXISTS id_mappings (
    entity_type TEXT NOT NULL,
    anchor_key  TEXT NOT NULL,
    entity_id   TEXT NOT NULL,
    created_at  TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (entity_type, anchor_key)
);
CREATE INDEX IF NOT EXISTS idx_id_mappings_entity ON id_mappings(entity_id);

CREATE TABLE IF NOT EXISTS ai_usage (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id            INTEGER REFERENCES users(id),
    created_at         TEXT DEFAULT (datetime('now')),
    input_tokens       INTEGER NOT NULL DEFAULT 0,
    output_tokens      INTEGER NOT NULL DEFAULT 0,
    cached_tokens      INTEGER NOT NULL DEFAULT 0,
    tool_calls         INTEGER NOT NULL DEFAULT 0,
    model              TEXT,
    route_at_open      TEXT,
    first_user_message TEXT
);
CREATE INDEX IF NOT EXISTS idx_ai_usage_user ON ai_usage(user_id);
CREATE INDEX IF NOT EXISTS idx_ai_usage_created_at ON ai_usage(created_at);

CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    username        TEXT UNIQUE NOT NULL,
    password_hash   TEXT NOT NULL,
    display_name    TEXT NOT NULL,
    role            TEXT NOT NULL DEFAULT 'editor',
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS audit_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER REFERENCES users(id),
    action          TEXT NOT NULL,
    entity_type     TEXT,
    entity_id       TEXT,
    details_json    TEXT,
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS app_meta (
    key             TEXT PRIMARY KEY,
    value           TEXT,
    updated_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS asset_classes (
    id              TEXT PRIMARY KEY,
    label           TEXT NOT NULL,
    parent_id       TEXT,
    sort_order      INTEGER DEFAULT 0,
    FOREIGN KEY (parent_id) REFERENCES asset_classes(id)
);

CREATE TABLE IF NOT EXISTS tenant_categories (
    id              TEXT PRIMARY KEY,
    label           TEXT NOT NULL,
    parent_id       TEXT,
    sort_order      INTEGER DEFAULT 0,
    FOREIGN KEY (parent_id) REFERENCES tenant_categories(id)
);

CREATE TABLE IF NOT EXISTS group_analytics (
    group_id            TEXT PRIMARY KEY REFERENCES groups(id),
    -- Portfolio
    property_count      INTEGER DEFAULT 0,
    total_assessed_value INTEGER,
    property_type_mix   TEXT,
    regions             TEXT,
    region_count        INTEGER DEFAULT 0,
    -- Transactions
    total_buys          INTEGER DEFAULT 0,
    total_sells         INTEGER DEFAULT 0,
    avg_buy_price       INTEGER,
    median_buy_price    INTEGER,
    avg_sell_price      INTEGER,
    median_sell_price   INTEGER,
    first_transaction_date TEXT,
    last_transaction_date  TEXT,
    net_acquisitions    INTEGER DEFAULT 0,
    avg_hold_period_days INTEGER,
    -- Velocity
    txns_per_year       REAL,
    buys_last_12m       INTEGER DEFAULT 0,
    sells_last_12m      INTEGER DEFAULT 0,
    buys_last_36m       INTEGER DEFAULT 0,
    sells_last_36m      INTEGER DEFAULT 0,
    -- Geographic
    hq_lat              REAL,
    hq_lng              REAL,
    avg_distance_from_hq_km REAL,
    max_distance_from_hq_km REAL,
    geographic_radius_km REAL,
    centroid_lat        REAL,
    centroid_lng        REAL,
    -- Meta
    refreshed_at        TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS data_issues (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id       TEXT NOT NULL,
    rule            TEXT NOT NULL,
    severity        TEXT NOT NULL,
    field_path      TEXT NOT NULL,
    actual_value    TEXT,
    message         TEXT NOT NULL,
    introduced_at   TEXT,
    origin_field    TEXT,
    source_field    TEXT,
    explanation     TEXT,
    code_location   TEXT,
    status          TEXT NOT NULL DEFAULT 'open',
    resolved_by     TEXT,
    resolved_at     TEXT,
    notes           TEXT,
    scan_run_id     TEXT,
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_data_issues_source ON data_issues(source_id);
CREATE INDEX IF NOT EXISTS idx_data_issues_rule ON data_issues(rule);
CREATE INDEX IF NOT EXISTS idx_data_issues_status ON data_issues(status);
CREATE INDEX IF NOT EXISTS idx_data_issues_severity ON data_issues(severity);
CREATE INDEX IF NOT EXISTS idx_data_issues_introduced ON data_issues(introduced_at);

-- ── Discovery tables ──

CREATE TABLE IF NOT EXISTS discovery_evidence (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          TEXT NOT NULL,
    signal_type     TEXT NOT NULL,
    signal_value    TEXT NOT NULL,
    source_group_id TEXT NOT NULL,
    target_group_id TEXT NOT NULL,
    source_id       TEXT,
    rule_id         TEXT,
    confidence      REAL,
    iteration       INTEGER DEFAULT 0,
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_disc_evidence_run ON discovery_evidence(run_id);
CREATE INDEX IF NOT EXISTS idx_disc_evidence_source ON discovery_evidence(source_group_id);
CREATE INDEX IF NOT EXISTS idx_disc_evidence_target ON discovery_evidence(target_group_id);
CREATE INDEX IF NOT EXISTS idx_disc_evidence_type ON discovery_evidence(signal_type);

CREATE TABLE IF NOT EXISTS discovery_runs (
    run_id          TEXT PRIMARY KEY,
    mode            TEXT NOT NULL,
    started_at      TEXT NOT NULL,
    completed_at    TEXT,
    stats_json      TEXT,
    diff_json       TEXT,
    config_json     TEXT
);

CREATE TABLE IF NOT EXISTS discovery_exclusions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    exclusion_type  TEXT NOT NULL,
    exclusion_value TEXT NOT NULL,
    reason          TEXT,
    created_by      TEXT,
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_disc_exclusions_type ON discovery_exclusions(exclusion_type);

CREATE TABLE IF NOT EXISTS discovery_ground_truth (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    portfolio_name  TEXT NOT NULL,
    anchor_group_id TEXT NOT NULL,
    member_group_ids_json TEXT NOT NULL,
    notes           TEXT,
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS discovery_cluster_names (
    run_id          TEXT NOT NULL,
    anchor_group_id TEXT NOT NULL,
    cluster_name    TEXT NOT NULL,
    PRIMARY KEY (run_id, anchor_group_id)
);

-- ============================================================
-- LABELING TABLES (party link labeling tool — migration 006)
-- ============================================================

CREATE TABLE IF NOT EXISTS labeling_sessions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    name                TEXT NOT NULL,
    audit_slug          TEXT,
    anchor_source_id    TEXT NOT NULL,
    anchor_side         TEXT NOT NULL CHECK (anchor_side IN ('buyer','seller')),
    status              TEXT NOT NULL DEFAULT 'active'
                          CHECK (status IN ('active','paused','done')),
    created_by          TEXT NOT NULL,
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at        TEXT
);

CREATE INDEX IF NOT EXISTS idx_labeling_sessions_status ON labeling_sessions(status);
CREATE INDEX IF NOT EXISTS idx_labeling_sessions_audit ON labeling_sessions(audit_slug);

CREATE TABLE IF NOT EXISTS labeling_verdicts (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id          INTEGER NOT NULL REFERENCES labeling_sessions(id) ON DELETE CASCADE,
    source_id           TEXT NOT NULL,
    side                TEXT NOT NULL CHECK (side IN ('buyer','seller')),
    verdict             TEXT NOT NULL CHECK (verdict IN ('confirmed','rejected')),
    left_source_id      TEXT NOT NULL,
    left_side           TEXT NOT NULL CHECK (left_side IN ('buyer','seller')),
    seed_id             INTEGER REFERENCES labeling_seeds(id) ON DELETE SET NULL,
    rationale           TEXT,
    created_by          TEXT NOT NULL,
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (session_id, source_id, side)
);

CREATE INDEX IF NOT EXISTS idx_labeling_verdicts_session ON labeling_verdicts(session_id);
CREATE INDEX IF NOT EXISTS idx_labeling_verdicts_verdict ON labeling_verdicts(verdict);

CREATE TABLE IF NOT EXISTS labeling_links (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    verdict_id          INTEGER NOT NULL REFERENCES labeling_verdicts(id) ON DELETE CASCADE,
    from_field_type     TEXT NOT NULL,
    from_field_value    TEXT NOT NULL,
    to_field_type       TEXT NOT NULL,
    to_field_value      TEXT NOT NULL,
    kind                TEXT NOT NULL CHECK (kind IN ('exact','implied')),
    created_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_labeling_links_verdict ON labeling_links(verdict_id);

CREATE TABLE IF NOT EXISTS labeling_seeds (
    id                              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id                      INTEGER NOT NULL REFERENCES labeling_sessions(id) ON DELETE CASCADE,
    term                            TEXT NOT NULL,
    field_type                      TEXT NOT NULL,
    state                           TEXT NOT NULL DEFAULT 'pending'
                                      CHECK (state IN ('pending','in_progress','done','skipped')),
    first_contributed_by_source_id  TEXT NOT NULL,
    first_contributed_by_side       TEXT NOT NULL CHECK (first_contributed_by_side IN ('buyer','seller')),
    completed_at                    TEXT,
    created_at                      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (session_id, term, field_type)
);

CREATE INDEX IF NOT EXISTS idx_labeling_seeds_session_state ON labeling_seeds(session_id, state);

CREATE TABLE IF NOT EXISTS labeling_reviewed_index (
    session_id          INTEGER NOT NULL REFERENCES labeling_sessions(id) ON DELETE CASCADE,
    source_id           TEXT NOT NULL,
    side                TEXT NOT NULL CHECK (side IN ('buyer','seller')),
    reviewed_at         TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (session_id, source_id, side)
);
"""


def create_all_tables(conn):
    """Create all tables (safe to call repeatedly — uses IF NOT EXISTS)."""
    conn.executescript(DERIVED_TABLES)
    conn.executescript(DERIVED_INDEXES)
    conn.executescript(FTS_TABLES)
    conn.executescript(CRM_TABLES)
    conn.executescript(SYSTEM_TABLES)
    conn.commit()


def drop_derived_tables(conn):
    """Drop derived tables only. CRM and system tables are preserved."""
    conn.executescript("""
        DROP TABLE IF EXISTS party_atoms;
        DROP TABLE IF EXISTS party_fingerprints;
        DROP TABLE IF EXISTS brand_registry;
        DROP TABLE IF EXISTS gw_sales_history;
        DROP TABLE IF EXISTS gw_assessments;
        DROP TABLE IF EXISTS pois;
        DROP TABLE IF EXISTS transaction_broker_agents;
        DROP TABLE IF EXISTS transaction_brokers;
        DROP TABLE IF EXISTS transaction_mailing_addresses;
        DROP TABLE IF EXISTS transaction_parties;
        DROP TABLE IF EXISTS group_names;
        DROP TABLE IF EXISTS transactions;
        DROP TABLE IF EXISTS properties;
        DROP TABLE IF EXISTS contacts;
        DROP TABLE IF EXISTS groups;
        DROP TABLE IF EXISTS properties_fts;
        DROP TABLE IF EXISTS contacts_fts;
        DROP TABLE IF EXISTS groups_fts;
        DROP TABLE IF EXISTS transactions_fts;
    """)
    conn.commit()
