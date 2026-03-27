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
        DROP TABLE IF EXISTS transaction_parties;
        DROP TABLE IF EXISTS group_names;
        DROP TABLE IF EXISTS transactions;
        DROP TABLE IF EXISTS properties;
        DROP TABLE IF EXISTS contacts;
        DROP TABLE IF EXISTS groups;
        DROP TABLE IF EXISTS properties_fts;
        DROP TABLE IF EXISTS contacts_fts;
        DROP TABLE IF EXISTS groups_fts;
    """)
    conn.commit()
