"""
Single source of truth for all classification dictionaries.

Every keyword list, suffix list, province list, pattern, etc. lives here.
All classifier modules import from this file. When you need to add a keyword,
change it here and nowhere else.

Reference: schema/engine_reference.md
"""

import re

# ---------------------------------------------------------------------------
# CONTACT PREFIXES — titles that precede a person's name
# ---------------------------------------------------------------------------

# Prefixes WITH colon (exact match at start of line, case insensitive)
CONTACT_PREFIXES_WITH_COLON = [
    'Attn:', 'Att:', 'Attan:', 'Atttn:', 'Atth:', 'Atnn:', 'Attm:',
    'Annt:', 'Arttn:', 'Attb:',
    'Pres:', 'Press:', 'Presd:', 'PresL',
    'Pares:', 'Presx:', 'Presw:', 'Prees:', 'Ptres:', 'Prres:',
    'Prews:', 'Peres:', 'Ptes:', 'Presa:',
    'VP:', 'ASO:', 'ASP:', 'AASO:', 'Dir:',
    'Co-Pres:', 'Mayor:', 'Warden:',
    'Treas:', 'Tres:', 'Sec:', 'CFO:', 'CEO:', 'COO:', 'SVP:',
    'Chair:', 'Chairman:', 'Trustee:', 'Executor:', 'Executrix:',
    'Bishop:', 'Pastor:', 'Counsel:', 'Mgr:', 'GM:',
    'Clerk:', 'Reeve:', 'Chief:', 'Principal:',
    'SO:', 'RSO:', 'CP:',
    'AKA:', 'Pres.', 'Pres;', 'Attn;', 'Sttn:',
    'Mr:', 'Mr.', 'Mrs:', 'Mrs.', 'Ms:', 'Ms.', 'Dr:', 'Dr.',
    'Attention',
    'Pre:', 'Pred:', 'Prs:',
]

# Prefixes that can appear WITHOUT colon (e.g., "Attn Robert Perkins")
# Only the most common ones — to avoid false positives
CONTACT_PREFIXES_NO_COLON = [
    'Attn', 'Att', 'Atn', 'Pres', 'ASO',
    'Mr', 'Mrs', 'Ms', 'Dr',
]

# Build regex patterns for prefix matching
_prefix_patterns = []
for p in CONTACT_PREFIXES_WITH_COLON:
    escaped = re.escape(p)
    _prefix_patterns.append(escaped + r'\s*')
for p in CONTACT_PREFIXES_NO_COLON:
    escaped = re.escape(p)
    # Must be followed by space + capital letter (to avoid matching words like "Preston")
    _prefix_patterns.append(escaped + r'\s+(?=[A-Z])')

CONTACT_PREFIX_REGEX = re.compile(
    r'^(' + '|'.join(_prefix_patterns) + r')',
    re.IGNORECASE
)


# ---------------------------------------------------------------------------
# PHONE PATTERNS
# ---------------------------------------------------------------------------

PHONE_REGEX = re.compile(
    r'(\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}|\d{6}-\d{4}|\d{3}-\d{7})'
    r'(\s*(x|ext\.?)\s*\d+)?'
)


# ---------------------------------------------------------------------------
# POSTAL CODE PATTERNS
# ---------------------------------------------------------------------------

# Standard Canadian postal code: A1A 1A1 (case insensitive, optional space)
POSTAL_CODE_REGEX = re.compile(
    r'^[A-Za-z]\d[A-Za-z]\s?\d[A-Za-z]\d$'
)

# US ZIP code (standalone on a line)
US_ZIP_REGEX = re.compile(r'^\d{5}(-\d{4})?$')

# Malformed postal code — 6-8 chars, mix of letters and digits, after stripping junk
MALFORMED_POSTAL_REGEX = re.compile(
    r'^[A-Za-z0-9]{3}\s?[A-Za-z0-9]{3,4}$'
)

# UK postal code pattern: A9 9AA, A99 9AA, A9A 9AA, AA9 9AA, AA99 9AA, AA9A 9AA
UK_POSTAL_REGEX = re.compile(
    r'^[A-Z]{1,2}\d[A-Z0-9]?\s?\d[A-Z]{2}$',
    re.IGNORECASE
)


# ---------------------------------------------------------------------------
# PROVINCES AND STATES
# ---------------------------------------------------------------------------

CANADIAN_PROVINCES = {
    # Full names
    'Ontario', 'Quebec', 'Québec', 'Alberta', 'British Columbia',
    'Manitoba', 'Saskatchewan', 'Nova Scotia', 'New Brunswick',
    'Newfoundland', 'Prince Edward Island', 'Yukon',
    'Northwest Territories', 'Nunavut',
    # Standard abbreviations
    'ON', 'QC', 'AB', 'BC', 'MB', 'SK', 'NS', 'NB', 'NL',
    'PE', 'PEI', 'YT', 'NT', 'NWT', 'NU',
    # Informal / typo variants found in data
    'Ont', 'OntArio', 'Ontarioi', 'Ontrio', 'Onario', 'OntariG',
}

US_STATES = {
    # Full names
    'Alabama', 'Alaska', 'Arizona', 'Arkansas', 'California', 'Colorado',
    'Connecticut', 'Delaware', 'Florida', 'Georgia', 'Hawaii', 'Idaho',
    'Illinois', 'Indiana', 'Iowa', 'Kansas', 'Kentucky', 'Louisiana',
    'Maine', 'Maryland', 'Massachusetts', 'Michigan', 'Minnesota',
    'Mississippi', 'Missouri', 'Montana', 'Nebraska', 'Nevada',
    'New Hampshire', 'New Jersey', 'New Mexico', 'New York',
    'North Carolina', 'North Dakota', 'Ohio', 'Oklahoma', 'Oregon',
    'Pennsylvania', 'Rhode Island', 'South Carolina', 'South Dakota',
    'Tennessee', 'Texas', 'Utah', 'Vermont', 'Virginia', 'Washington',
    'West Virginia', 'Wisconsin', 'Wyoming', 'District of Columbia',
    # Standard abbreviations
    'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA',
    'HI', 'ID', 'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD',
    'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ',
    'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC',
    'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY', 'DC',
    # Typo variants found in data
    'Illimois', 'Virgina',
}

ALL_PROVINCES_STATES = CANADIAN_PROVINCES | US_STATES


# ---------------------------------------------------------------------------
# COUNTRIES
# ---------------------------------------------------------------------------

COUNTRIES = {
    'USA', 'United States', 'The Netherlands', 'England',
    'United Kingdom', 'UK', 'Bermuda', 'Barbados', 'China',
    'Hong Kong', 'Japan', 'Germany', 'France', 'Australia',
    'Switzerland', 'Israel', 'India', 'Korea', 'South Korea',
    'Singapore', 'Ireland', 'Scotland', 'Wales', 'Italy', 'Spain',
    'Sweden', 'Norway', 'Denmark', 'Belgium', 'Austria', 'Luxembourg',
    'Mexico', 'Brazil', 'South Africa', 'New Zealand',
    'United Arab Emirates', 'UAE', 'Saudi Arabia', 'Qatar',
    'Taiwan', 'Philippines', 'Thailand', 'Malaysia', 'Indonesia',
    'British West Indies', 'Cayman Islands', 'Grand Cayman',
    'Principality of Liechtenstein', 'Lebanon',
}

COUNTRY_REGEX = re.compile(
    r'^USA\s*-?\s*\d{5}(-\d{4})?$'  # USA with ZIP or ZIP+4
)


# ---------------------------------------------------------------------------
# LAW FIRM KEYWORDS
# ---------------------------------------------------------------------------

LAW_FIRM_KEYWORDS = [
    'LLP', 'Barristers', 'Solicitors', 'Barrister', 'Solicitor',
    'Law Office', 'Law Firm', 'Notary', 'Notaire', 'Avocats',
    'Attorney', 'Attorneys', 'Professional Corporation',
    'LLB', 'Q.C.',
    # NOTE: bare "QC" removed — conflicts with Quebec province abbreviation.
    # Queen's Counsel always has periods: "Q.C."
]

# " PC" as in "Levy Zavet PC" — needs space before to avoid matching "PC" in other words
LAW_FIRM_PC_REGEX = re.compile(r'\bPC$')


# ---------------------------------------------------------------------------
# CORPORATE SUFFIXES — definitive company identifiers
# ---------------------------------------------------------------------------

CORPORATE_SUFFIXES = [
    'Inc.', 'Inc', 'Corp.', 'Corp', 'Ltd.', 'Ltd', 'Limited',
    'LLC', 'LP', 'Co.', 'Foundation', 'Association', 'Holdings',
    'ULC',
]

# Build regex: match these at or near end of line
_corp_escaped = [re.escape(s.rstrip('.')) for s in CORPORATE_SUFFIXES]
CORPORATE_SUFFIX_REGEX = re.compile(
    r'\b(' + '|'.join(_corp_escaped) + r')\.?\s*$',
    re.IGNORECASE
)

# Also check for corporate suffix mid-line (e.g., "Boyds Inn Ltd")
CORPORATE_SUFFIX_ANYWHERE_REGEX = re.compile(
    r'\b(' + '|'.join(_corp_escaped) + r')\.?(\s|,|$)',
    re.IGNORECASE
)


# ---------------------------------------------------------------------------
# COMPANY KEYWORDS — includes former department keywords (merged)
# ---------------------------------------------------------------------------

COMPANY_KEYWORDS = [
    # Core company indicators
    'Properties', 'Realty', 'Capital', 'REIT',
    'Investments', 'Developments', 'Enterprises',
    'Partners', 'Healthcare', 'Residences',
    'Management', 'Development', 'Investment Trust',
    'Pension', 'Board', 'Corporation',
    'Solutions', 'Homes', 'Construction',
    'Senior Living', 'Health Care', 'Living',
    'Retirement', 'Real Estate', 'Advisors',
    'Services', 'Consulting', 'Financial',
    'Hotel', 'Motel', 'Housing', 'Acquisition',
    'Church', 'Group', 'Companies', 'Station',
    'Outlet', 'Office', 'Postal',
    'Associates', 'Company', 'Authority', 'Parking', 'Bank',
    'Rentals', 'Products', 'Plastics', 'Insurance', 'Assurance',
    'Automotive', 'Transport', 'Catering', 'Winery', 'Brewery',
    'Dispensary', 'Bookstore', 'Builders', 'Inn',
    'Hoist', 'Mirror', 'Glass', 'Pipe', 'Tool', 'Printers',
    'Fitness', 'Sodding', 'Landscaping', 'Plumbing', 'Welding',
    'Paving', 'Aluminium', 'Aluminum', 'Rehab', 'Daycare',
    'Dental', 'Commercial', 'Accounting', 'Accountants',
    'Systems', 'System', 'Wealth', 'Regency',
    'Farms', 'Motor', 'Auto', 'Retail', 'Wholesale',
    'School', 'Lawyers', 'Lawyer', 'International',
    'National', 'Provincial', 'Chartered', 'Certified',
    'Hospitality', 'Conference', 'Equity', 'Mortgages',
    'Nissan', 'Honda', 'Hyundai', 'Kia', 'Ford', 'Benz',
    'Sobeys', 'Loblaws', 'Walmart', 'Costco', 'Shoppers',
    'Receiver', 'Appointed',
    'Infrastructure', 'Lodges', 'Lodge', 'Estates', 'Estate',
    'Hospital', 'Printing', 'Club', 'Golf', 'Topsoil',
    'Storage', 'Wire', 'Packers', 'Express',
    'Volkswagen', 'Volkswagon', 'Audi',
    # Former DEPARTMENT_KEYWORDS — merged into company
    'Department', 'Dept',
    'Division', 'Legal Services', 'Legal Department',
    'Corporate Real Estate', 'Corporate Services',
    'Real Estate Department', 'Real Estate Branch', 'Real Esate Branch',
    'Mail Code', 'REPDO', 'Special Accounts',
    'Head Office', 'RT Office',
    'Marketing Section', 'Development Section',
    'Ministry of', 'Special Loans',
    'University Operations', 'Rental Office',
    'Project Lending', 'NCA Property Transactions',
    'Air & Marine Programs', 'Mail Stop',
    'Facilities and Real Estate',
    'Sales and Acquisitions',
    'Executive Offices', 'Offices',
]

TRUST_REFERENCE_REGEX = re.compile(
    r'^(as trustee?e? for|in trust for|in it.?s capacity as)\s',
    re.IGNORECASE
)


# ---------------------------------------------------------------------------
# BUILDING KEYWORDS
# ---------------------------------------------------------------------------

BUILDING_KEYWORDS = [
    'Tower', 'Centre', 'Center', 'Place', 'Plaza',
    'Building', 'Bldg', 'Hall', 'House', 'Campus',
    'Complex', 'Mall', 'Podium', 'Edifice',
    'Industrial Park', 'Nursing Home', 'Corporate Office',
    'Ctr',  # abbreviation for Centre/Center
    'Blk',  # abbreviation for Block
]

# Keywords that indicate a building ONLY when no digit + street suffix present
BUILDING_CONTEXT_KEYWORDS = ['Court', 'Square']


# ---------------------------------------------------------------------------
# STREET SUFFIXES (English + French)
# ---------------------------------------------------------------------------

STREET_SUFFIXES = [
    # English
    'St', 'Ave', 'Rd', 'Dr', 'Blvd', 'Cres', 'Way', 'Ct', 'Pl',
    'Lane', 'Line', 'Pkwy', 'Hwy', 'Circle', 'Gate', 'Trail',
    'Walk', 'Grove', 'Terr', 'Terrace', 'Crt', 'Court', 'Close',
    'Path', 'Run', 'Rise', 'Glen', 'Park', 'Square', 'Green',
    'Quay', 'Landing', 'Manor', 'Route', 'Road', 'Highway',
    'Concession', 'Conc', 'Sideroad', 'Queensway', 'Donway',
    'Esplanade',
    # French
    'rue', 'boulevard', 'bld', 'chemin', 'ch', 'promenade',
    'autoroute', 'montée', 'montee', 'côte', 'cote',
]

STREET_SUFFIX_REGEX = re.compile(
    r'\b(' + '|'.join(re.escape(s) for s in STREET_SUFFIXES) + r')\b',
    re.IGNORECASE
)


# ---------------------------------------------------------------------------
# FLOOR / SUITE / ADDRESS MODIFIER PATTERNS
# ---------------------------------------------------------------------------

FLOOR_MODIFIER_REGEX = re.compile(
    r'^(Suite|Ste|Suites|Units?|Floor|Flr|Level|Bureau|'
    r'Mezzanine|Penthouse|Basement|Side Unit|Apartment|Apt|'
    r'Entrance|Stn)\b|'
    r'^(First|Second|Third|Fourth|Fifth|Sixth|Seventh|Eighth|Ninth|Tenth|'
    r'Ground|Lower|Upper|Main|Top|Rear)\s+(Floor|Level|Unit)|'
    r'^(1st|2nd|3rd|4th|5th|6th|7th|8th|9th|10th)\s+Floor|'
    r'^East\s+Podium|^West\s+Podium|'
    r'^#\d',
    re.IGNORECASE
)

STATION_MODIFIER_REGEX = re.compile(
    r'^(Station|Terminal|Postal\s+Outlet|Succursale|RPO|'
    r'PO\s+Station|RS,\s+Station|Direct\s+Bag|Group\s+Box|'
    r'Postal\s+Bag|PMB)\b',
    re.IGNORECASE
)


# ---------------------------------------------------------------------------
# RURAL ROUTE / PO BOX PATTERNS
# ---------------------------------------------------------------------------

RURAL_ROUTE_REGEX = re.compile(
    r'^R\.?R\.?\s*#?\d',
    re.IGNORECASE
)

# Expanded PO Box — catches P O Box, PO Box without space, location + PO Box
# NOTE: CP requires space + digit to avoid matching "CP Tower", "CPP", "CPI"
PO_BOX_REGEX = re.compile(
    r'^(P\s?\.?\s?O\s?\.?\s?Box|Box|FGPO Box|FG PO Box|F\.\s?G\.\s?PO Box)\s*\S|^CP\s+\d',
    re.IGNORECASE
)

# PO Box anywhere in line (not just at start)
PO_BOX_ANYWHERE_REGEX = re.compile(
    r'\bP\s?\.?\s?O\s?\.?\s?Box\b',
    re.IGNORECASE
)


# ---------------------------------------------------------------------------
# NEGATIVE RULES — "it's definitely NOT this"
# ---------------------------------------------------------------------------

# Words that NEVER appear in a person's name
NOT_A_PERSON_WORDS = [
    'Inc.', 'Inc', 'Corp.', 'Corp', 'Ltd.', 'Ltd', 'Limited',
    'LLC', 'LLP', 'Co.', 'LP', 'Holdings', 'Properties', 'Realty',
    'Department', 'Dept', 'Deptartment',
    'Division', 'Services', 'Management', 'REIT',
    'Trust', 'Board', 'Pension', 'ULC',
]

NOT_A_PERSON_REGEX = re.compile(
    r'\b(' + '|'.join(re.escape(w.rstrip('.')) for w in NOT_A_PERSON_WORDS) + r')\.?\b',
    re.IGNORECASE
)


# ---------------------------------------------------------------------------
# HEADER ADDRESS LINE PATTERNS
# ---------------------------------------------------------------------------

LEGAL_DESC_START_REGEX = re.compile(
    r'^(PLAN|Plan|PT |PART |LOT |LOTS |CONC |CON |BLK |BLOCK |BEING )',
    re.IGNORECASE
)

UNIT_SUITE_START_REGEX = re.compile(
    r'^(UNIT|UNITS|SUITE|STE|APT|LEVEL)\s',
    re.IGNORECASE
)

HIGHWAY_START_REGEX = re.compile(
    r'^(HIGHWAY|HWY|COUNTY RD|REGIONAL RD)\s',
    re.IGNORECASE
)


# ---------------------------------------------------------------------------
# COMMON FIRST NAMES — used to detect person names in ambiguous contexts
# ---------------------------------------------------------------------------

COMMON_FIRST_NAMES = {
    # Male — English
    'Adam', 'Alan', 'Albert', 'Alex', 'Alexander', 'Allan', 'Allen', 'Andrew',
    'Anthony', 'Arthur', 'Barry', 'Ben', 'Benjamin', 'Bernard', 'Bill', 'Bob',
    'Brad', 'Brandon', 'Brian', 'Bruce', 'Carl', 'Charles', 'Chris',
    'Christopher', 'Colin', 'Craig', 'Dan', 'Daniel', 'Dave', 'David',
    'Dennis', 'Derek', 'Don', 'Donald', 'Doug', 'Douglas', 'Dwight',
    'Ed', 'Edward', 'Eric', 'Ernst', 'Frank', 'Fred', 'Frederick',
    'Gary', 'George', 'Gerald', 'Glen', 'Gordon', 'Graham', 'Greg',
    'Gregory', 'Harold', 'Harry', 'Harvey', 'Henry', 'Howard', 'Ian',
    'Jack', 'James', 'Jason', 'Jeff', 'Jeffrey', 'Jerome', 'Jim',
    'Joe', 'Joel', 'John', 'Jon', 'Jonathan', 'Joseph', 'Keith',
    'Ken', 'Kenneth', 'Kevin', 'Kyle', 'Larry', 'Lawrence', 'Leo',
    'Louis', 'Mark', 'Martin', 'Matt', 'Matthew', 'Max', 'Mel',
    'Melvyn', 'Michael', 'Mike', 'Morris', 'Murray', 'Neil', 'Nick',
    'Norman', 'Patrick', 'Paul', 'Perry', 'Pete', 'Peter', 'Phil',
    'Philip', 'Ralph', 'Randall', 'Randolph', 'Raymond', 'Richard',
    'Rob', 'Robert', 'Rod', 'Roger', 'Ron', 'Ronald', 'Ross',
    'Roy', 'Russell', 'Ryan', 'Sam', 'Samuel', 'Scott', 'Sean',
    'Sheldon', 'Simon', 'Stephen', 'Steve', 'Steven', 'Stewart',
    'Stuart', 'Ted', 'Terry', 'Thomas', 'Tim', 'Timothy', 'Todd',
    'Tom', 'Tony', 'Trevor', 'Victor', 'Walter', 'Warren', 'Wayne',
    'William',
    # Female — English
    'Alice', 'Amanda', 'Amy', 'Andrea', 'Angela', 'Ann', 'Anna',
    'Anne', 'Barbara', 'Betty', 'Beverly', 'Brenda', 'Carol',
    'Catherine', 'Christine', 'Cynthia', 'Deborah', 'Diane', 'Diana',
    'Donna', 'Dorothy', 'Elizabeth', 'Ellen', 'Emily', 'Frances',
    'Gloria', 'Grace', 'Helen', 'Irene', 'Jane', 'Janet', 'Jean',
    'Jennifer', 'Jessica', 'Joan', 'Joyce', 'Judith', 'Judy', 'Julie',
    'Karen', 'Katherine', 'Kathleen', 'Kathy', 'Kelly', 'Kim',
    'Laura', 'Linda', 'Lisa', 'Lois', 'Lorraine', 'Louise', 'Lynn',
    'Margaret', 'Maria', 'Marie', 'Marilyn', 'Marion', 'Martha',
    'Mary', 'Nancy', 'Nicole', 'Norma', 'Pamela', 'Patricia', 'Paula',
    'Phyllis', 'Rebecca', 'Rita', 'Rose', 'Ruth', 'Sandra', 'Sarah',
    'Sharon', 'Shirley', 'Stacey', 'Stephanie', 'Susan', 'Sylvia',
    'Tanya', 'Teresa', 'Theresa', 'Tina', 'Tracy', 'Valerie',
    'Victoria', 'Virginia', 'Vivian', 'Wendy', 'Yvonne',
    # International — common in Ontario CRE
    'Aldo', 'Anil', 'Armen', 'Andre', 'Alexandre', 'Afzal',
    'Dong', 'Ehsan', 'Gianfranco', 'Irina', 'Jasvinder',
    'Johannes', 'Jonah', 'Karanpaul', 'Liviu', 'Michel',
    'Micheline', 'Mocelle', 'Nasser', 'Osama', 'Rejean',
    'Selva', 'Sepid', 'Stefan', 'Surinder', 'Talal', 'Tanweer',
    'Wolfgang', 'Armen', 'Vito', 'Albrecht', 'Jonathane', 'Jonah',
    'Stacey', 'Mocelle', 'Dwight', 'Oksana', 'Weixiang',
    'Evangelos', 'Karanpaul', 'Liviu', 'Rejean', 'Ehsan',
    'Skip', 'Bev',
    # From other_lines data
    'Angelo', 'Gabriel', 'Hana', 'June', 'Cindy', 'Rudolph',
    'Pasquale', 'Foungmai', 'Sergi', 'Ashish', 'Halim',
    'Stanislaw', 'Aleck', 'Frances', 'Mu',
}


# ---------------------------------------------------------------------------
# MONTH PARSING
# ---------------------------------------------------------------------------

MONTH_MAP = {
    'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04',
    'May': '05', 'Jun': '06', 'Jul': '07', 'Aug': '08',
    'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12',
}
