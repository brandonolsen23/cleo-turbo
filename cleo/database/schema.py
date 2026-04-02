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
    legal_description TEXT,
    current_owner_name TEXT,
    current_owner_group_id TEXT,
    most_recent_source_id TEXT,
    most_recent_sale_date TEXT,
    most_recent_sale_price INTEGER,
    transaction_count INTEGER DEFAULT 0,
    primary_property_type TEXT,
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
    pin             TEXT,
    legal_description TEXT,
    pin_display      TEXT,
    arn_display      TEXT,
    pin_multiple     INTEGER DEFAULT 0,
    parcel_method    TEXT,
    location         TEXT,
    surface_rights_only INTEGER DEFAULT 0,
    more_info_url    TEXT,
    consideration_json TEXT,
    broker_json     TEXT,
    photos_json     TEXT,
    source_folder   TEXT,
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
    status          TEXT NOT NULL DEFAULT 'pool',
    source          TEXT DEFAULT 'transaction',
    transaction_count INTEGER DEFAULT 0,
    first_seen_date TEXT,
    last_seen_date  TEXT,
    hubspot_id      TEXT,
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

CREATE TABLE IF NOT EXISTS transaction_party_metadata (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id       TEXT NOT NULL REFERENCES transactions(source_id),
    side            TEXT NOT NULL,
    trade_name      TEXT,
    care_of         TEXT,
    law_firms_json  TEXT,
    companies_json  TEXT,
    UNIQUE(source_id, side)
);

CREATE TABLE IF NOT EXISTS transaction_consideration (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id       TEXT NOT NULL UNIQUE REFERENCES transactions(source_id),
    cash            INTEGER,
    debt            INTEGER,
    chattels        INTEGER,
    other           INTEGER,
    charges_json    TEXT,
    created_at      TEXT DEFAULT (datetime('now'))
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
    created_at      TEXT DEFAULT (datetime('now'))
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
CREATE INDEX IF NOT EXISTS idx_transactions_property ON transactions(property_id);
CREATE INDEX IF NOT EXISTS idx_transactions_arn ON transactions(arn);
CREATE INDEX IF NOT EXISTS idx_transactions_sale_date ON transactions(sale_date);
CREATE INDEX IF NOT EXISTS idx_transactions_city ON transactions(city);
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
CREATE INDEX IF NOT EXISTS idx_tx_meta_source ON transaction_party_metadata(source_id);
CREATE INDEX IF NOT EXISTS idx_tx_cons_source ON transaction_consideration(source_id);
CREATE INDEX IF NOT EXISTS idx_tx_cons_cash ON transaction_consideration(cash);
CREATE INDEX IF NOT EXISTS idx_tx_broker_source ON transaction_brokers(source_id);
CREATE INDEX IF NOT EXISTS idx_tx_agent_broker ON transaction_broker_agents(broker_id);
CREATE INDEX IF NOT EXISTS idx_pois_property ON pois(property_id);
CREATE INDEX IF NOT EXISTS idx_pois_brand ON pois(brand);
CREATE INDEX IF NOT EXISTS idx_pois_category ON pois(category);
CREATE INDEX IF NOT EXISTS idx_pois_arn ON pois(arn);
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
"""

FTS_TABLES = """
CREATE VIRTUAL TABLE IF NOT EXISTS properties_fts USING fts5(
    id, display_address, city, region, current_owner_name,
    content='properties', content_rowid='rowid',
    tokenize='porter unicode61'
);

CREATE VIRTUAL TABLE IF NOT EXISTS contacts_fts USING fts5(
    id, display_name, first_name, last_name, phone, company_name,
    content='contacts', content_rowid='rowid',
    tokenize='porter unicode61'
);

CREATE VIRTUAL TABLE IF NOT EXISTS groups_fts USING fts5(
    id, display_name,
    content='groups', content_rowid='rowid',
    tokenize='porter unicode61'
);

CREATE VIRTUAL TABLE IF NOT EXISTS transactions_fts USING fts5(
    source_id, display_address, city, region, seller_parties, buyer_parties,
    content='transactions', content_rowid='rowid',
    tokenize='porter unicode61'
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
"""

SYSTEM_TABLES = """
-- ============================================================
-- SYSTEM TABLES
-- ============================================================

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
        DROP TABLE IF EXISTS gw_sales_history;
        DROP TABLE IF EXISTS gw_assessments;
        DROP TABLE IF EXISTS pois;
        DROP TABLE IF EXISTS transaction_broker_agents;
        DROP TABLE IF EXISTS transaction_brokers;
        DROP TABLE IF EXISTS transaction_consideration;
        DROP TABLE IF EXISTS transaction_mailing_addresses;
        DROP TABLE IF EXISTS transaction_party_metadata;
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
