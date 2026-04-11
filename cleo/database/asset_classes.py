"""
Asset class taxonomy for Cleo Turbo.

Canonical asset classes and subcategories based on Brandon's HubSpot
`all_real_estate_classes` field. This is the single source of truth for
property classification across the app.

The RT_MAPPING dict maps Realtrack's primary_property_type values to
broad asset classes. Subcategories are always manually assigned — never
auto-inferred from GW property codes.
"""

# ── Taxonomy Definition ──────────────────────────────────────────────
# Each entry: (id, label, parent_id, sort_order)

ASSET_CLASS_SEED = [
    # Broad categories (parent_id=None)
    ("retail",        "Retail",        None, 1),
    ("industrial",    "Industrial",    None, 2),
    ("multifamily",   "Multifamily",   None, 3),
    ("office",        "Office",        None, 4),
    ("land",          "Land",          None, 5),
    ("agricultural",  "Agricultural",  None, 6),
    ("mixed_use",     "Mixed Use",     None, 7),
    ("hospitality",   "Hospitality",   None, 8),

    # Retail subcategories
    ("retail_neighbourhood_plaza",   "Neighbourhood Plaza",   "retail", 1),
    ("retail_grocery_anchored_plaza", "Grocery Anchored Plaza", "retail", 2),
    ("retail_standalone_qsr",        "Stand-Alone QSR",       "retail", 3),
    ("retail_standalone_grocery",    "Stand-Alone Grocery",   "retail", 4),
    ("retail_standalone_box",        "Stand-Alone Box",       "retail", 5),
    ("retail_super_centre",          "Super Centre",          "retail", 6),
    ("retail_mall",                  "Mall",                  "retail", 7),
    ("retail_flex",                  "Flex",                  "retail", 8),
    ("retail_auto_dealership",       "Auto Dealership",       "retail", 9),

    # Industrial subcategories
    ("industrial_small_bay",         "Small Bay",             "industrial", 1),
    ("industrial_warehouse",         "Warehouse",             "industrial", 2),
    ("industrial_manufacturing",     "Manufacturing",         "industrial", 3),
    ("industrial_special_purpose",   "Special Purpose",       "industrial", 4),

    # Multifamily subcategories
    ("multifamily_under_6",          "Under 6 Units",         "multifamily", 1),
    ("multifamily_7_to_14",          "7 to 14 Units",         "multifamily", 2),
    ("multifamily_15_plus",          "15 Units+",             "multifamily", 3),

    # Office subcategories
    ("office_general",               "General",               "office", 1),
    ("office_medical",               "Medical",               "office", 2),

    # Land subcategories
    ("land_car_wash_site",           "Car Wash Site",         "land", 1),
    ("land_light_industrial",        "Light Industrial",      "land", 2),
    ("land_heavy_industrial",        "Heavy Industrial",      "land", 3),
    ("land_retail",                  "Retail",                "land", 4),
    ("land_gas_bar",                 "Gas Bar",               "land", 5),
    ("land_low_density_residential", "Low Density Residential", "land", 6),
    ("land_med_density_residential", "Medium Density Residential", "land", 7),
    ("land_high_density_residential","High Density Residential", "land", 8),

    # Agricultural subcategories
    ("agricultural_cash_crop",       "Cash Crop",             "agricultural", 1),
    ("agricultural_dairy_farm",      "Dairy Farm",            "agricultural", 2),
    ("agricultural_special_purpose", "Special Purpose",       "agricultural", 3),
]


# ── Realtrack primary_property_type → broad asset_class ──────────────
# This mapping covers all values found in the database as of April 2026.

RT_MAPPING = {
    "retail":          "retail",
    "restaurant-bar":  "retail",
    "multifamily":     "multifamily",
    "industrial":      "industrial",
    "comm-ind-land":   "land",
    "res-land":        "land",
    "other-land":      "land",
    "land":            "land",
    "farm":            "agricultural",
    "office":          "office",
    "hotel-motel":     "hospitality",
    "other-bldg":      "mixed_use",
    "commercial":      "retail",       # vague catch-all → retail
    "other non res":   "mixed_use",
    "single_family":   None,           # residential, not CRE
    "other_res":       None,           # residential, not CRE
    "semi_detached":   None,           # residential, not CRE
    "multiplex":       "multifamily",
    "mobile":          None,           # not CRE
    "seasonal":        None,           # not CRE
    "n/a":             None,
    "unavailable":     None,
}


# ── Contact Types ────────────────────────────────────────────────────
# Matches HubSpot type_of_contact values.

CONTACT_TYPES = [
    ("seller",              "Seller"),
    ("buyer_investor",      "Buyer - Investor"),
    ("buyer_developer",     "Buyer - Developer"),
    ("buyer_owner_occupier","Buyer - Owner Occupier"),
    ("national_tenant",     "National Tenant"),
    ("local_tenant",        "Local Tenant"),
    ("landlord",            "Landlord"),
    ("professional",        "Professional Contact"),
    ("personal",            "Personal Contact"),
    ("commercial_realtor",  "Commercial Realtor"),
    ("residential_realtor", "Residential Realtor"),
]

# HubSpot value → Cleo id mapping for sync
HUBSPOT_CONTACT_TYPE_MAP = {
    "Seller":              "seller",
    "Buyer":               "buyer_investor",
    "Buyer - Developer":   "buyer_developer",
    "Buyer - Owner Occupier": "buyer_owner_occupier",
    "Lessee":              "national_tenant",
    "Local Tenant":        "local_tenant",
    "Lessor":              "landlord",
    "Professional Contact":"professional",
    "Personal Contact":    "personal",
    "Commercial Realtor":  "commercial_realtor",
    "Residential Realtor": "residential_realtor",
}


def seed_asset_classes(conn):
    """Insert all asset class records (idempotent via INSERT OR IGNORE)."""
    for ac_id, label, parent_id, sort_order in ASSET_CLASS_SEED:
        conn.execute(
            "INSERT OR IGNORE INTO asset_classes (id, label, parent_id, sort_order) "
            "VALUES (?, ?, ?, ?)",
            (ac_id, label, parent_id, sort_order)
        )
    conn.commit()


def map_property_type_to_asset_class(primary_property_type):
    """Map a Realtrack primary_property_type to a broad asset_class id.

    Returns None if the type is not CRE or not recognized.
    """
    if not primary_property_type:
        return None
    return RT_MAPPING.get(primary_property_type.lower().strip())


def populate_asset_classes(conn):
    """One-time migration: set asset_class on all properties based on
    their primary_property_type. Does NOT overwrite existing values."""
    cursor = conn.execute(
        "SELECT id, primary_property_type FROM properties "
        "WHERE asset_class IS NULL AND primary_property_type IS NOT NULL"
    )
    updates = []
    for row in cursor.fetchall():
        ac = map_property_type_to_asset_class(row[1])
        if ac:
            updates.append((ac, row[0]))

    if updates:
        conn.executemany(
            "UPDATE properties SET asset_class = ? WHERE id = ?",
            updates
        )
        conn.commit()

    return len(updates)
