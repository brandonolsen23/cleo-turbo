"""
Tenant category taxonomy for Cleo Turbo.

A hierarchical system for classifying commercial tenants and retail categories.
Parent categories represent broad tenant types, and subcategories provide
granular classification for prospecting and portfolio analysis.

The TENANT_CATEGORY_SEED is the single source of truth for all tenant
categories across the app.
"""

# ── Taxonomy Definition ──────────────────────────────────────────────
# Each entry: (id, label, parent_id, sort_order)

TENANT_CATEGORY_SEED = [
    # Parent categories (parent_id=None)
    ("grocery",             "Grocery",                      None, 1),
    ("qsr",                 "Quick Service Restaurant",     None, 2),
    ("restaurant",          "Casual / Full Service Restaurant", None, 3),
    ("medical",             "Medical & Health",             None, 4),
    ("financial",           "Financial Services",           None, 5),
    ("government",          "Government & Institutional",   None, 6),
    ("bigbox",              "Big-Box & Anchor Retail",      None, 7),
    ("specialty_retail",    "Specialty Retail",             None, 8),
    ("fitness",             "Fitness & Recreation",         None, 9),
    ("personal_services",   "Personal Services",            None, 10),
    ("professional",        "Professional Services",        None, 11),
    ("automotive",          "Automotive",                   None, 12),

    # Grocery subcategories
    ("grocery_full_size",       "Full-Size Grocery",            "grocery", 1),
    ("grocery_specialty",       "Specialty / Ethnic Grocery",    "grocery", 2),
    ("grocery_discount",        "Discount Grocery",             "grocery", 3),

    # QSR subcategories
    ("qsr_burger",              "Burger / Sandwich",            "qsr", 1),
    ("qsr_coffee",              "Coffee / Café",                "qsr", 2),
    ("qsr_chicken",             "Chicken / Wings",              "qsr", 3),
    ("qsr_pizza_sub",           "Pizza / Sub",                  "qsr", 4),
    ("qsr_other",               "Other QSR",                    "qsr", 5),

    # Restaurant subcategories
    ("restaurant_casual",       "Casual Dining",                "restaurant", 1),
    ("restaurant_full",         "Full Service",                 "restaurant", 2),
    ("restaurant_fast_casual",  "Fast Casual",                  "restaurant", 3),

    # Medical subcategories
    ("medical_dental",          "Dental",                       "medical", 1),
    ("medical_optometry",       "Optometry",                    "medical", 2),
    ("medical_chiropractic",    "Chiropractic",                 "medical", 3),
    ("medical_audiology",       "Audiology / Hearing",          "medical", 4),
    ("medical_physiotherapy",   "Physiotherapy / Rehab",        "medical", 5),
    ("medical_walk_in",         "Walk-In Clinic / Family Medicine", "medical", 6),
    ("medical_pharmacy",        "Pharmacy",                     "medical", 7),
    ("medical_veterinary",      "Veterinary",                   "medical", 8),
    ("medical_specialist",      "Specialist / Lab",             "medical", 9),

    # Financial subcategories
    ("financial_bank",          "Bank (Big 5 / National)",       "financial", 1),
    ("financial_credit_union",  "Credit Union",                 "financial", 2),
    ("financial_insurance",     "Insurance",                    "financial", 3),
    ("financial_investment",    "Investment / Advisory",        "financial", 4),
    ("financial_lending",       "Lending / Consumer Finance",   "financial", 5),

    # Government subcategories
    ("gov_federal",             "Federal Government",           "government", 1),
    ("gov_provincial",          "Provincial Government",        "government", 2),
    ("gov_municipal",           "Municipal Government",         "government", 3),
    ("gov_post",                "Post Office / Courier",        "government", 4),
    ("gov_education",           "Education / Childcare",        "government", 5),

    # Big-Box subcategories
    ("bigbox_general",          "General Merchandise",          "bigbox", 1),
    ("bigbox_home",             "Home Improvement",             "bigbox", 2),
    ("bigbox_electronics",      "Electronics",                  "bigbox", 3),
    ("bigbox_discount",         "Discount / Dollar",            "bigbox", 4),

    # Specialty Retail subcategories
    ("retail_clothing",         "Clothing & Apparel",           "specialty_retail", 1),
    ("retail_pet",              "Pet Supply",                   "specialty_retail", 2),
    ("retail_liquor",           "Liquor / Beer / Cannabis",     "specialty_retail", 3),
    ("retail_sporting",         "Sporting Goods",               "specialty_retail", 4),
    ("retail_auto_parts",       "Auto Parts / Service",         "specialty_retail", 5),
    ("retail_furniture",        "Furniture / Home Decor",       "specialty_retail", 6),
    ("retail_beauty",           "Beauty / Personal Care",       "specialty_retail", 7),
    ("retail_mobile",           "Mobile / Telecom",             "specialty_retail", 8),
    ("retail_optical",          "Optical Retail",               "specialty_retail", 9),
    ("retail_convenience",      "Convenience / Gas",            "specialty_retail", 10),

    # Fitness subcategories
    ("fitness_gym",             "Gym / Fitness Centre",         "fitness", 1),
    ("fitness_yoga",            "Yoga / Pilates / Barre",       "fitness", 2),
    ("fitness_martial",         "Martial Arts / Boxing",        "fitness", 3),
    ("fitness_recreation",      "Recreation / Entertainment",   "fitness", 4),

    # Personal Services subcategories
    ("services_hair",           "Hair / Beauty Salon",          "personal_services", 1),
    ("services_spa",            "Spa / Aesthetics",             "personal_services", 2),
    ("services_dry_clean",      "Dry Cleaner / Laundry",        "personal_services", 3),
    ("services_tailor",         "Tailor / Alterations",         "personal_services", 4),

    # Professional subcategories
    ("professional_legal",      "Law Office",                   "professional", 1),
    ("professional_accounting", "Accounting / Tax",             "professional", 2),
    ("professional_real_estate","Real Estate Office",           "professional", 3),
    ("professional_staffing",   "Staffing / Recruitment",       "professional", 4),

    # Automotive subcategories
    ("auto_dealership",         "Auto Dealership",              "automotive", 1),
    ("auto_service",            "Auto Service / Repair",        "automotive", 2),
    ("auto_rental",             "Car Rental",                   "automotive", 3),
    ("auto_wash",               "Car Wash",                     "automotive", 4),
]


def seed_tenant_categories(conn):
    """Insert all tenant category records (idempotent via INSERT OR IGNORE)."""
    for tc_id, label, parent_id, sort_order in TENANT_CATEGORY_SEED:
        conn.execute(
            "INSERT OR IGNORE INTO tenant_categories (id, label, parent_id, sort_order) "
            "VALUES (?, ?, ?, ?)",
            (tc_id, label, parent_id, sort_order)
        )
    conn.commit()
