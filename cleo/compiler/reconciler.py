"""
Reconciler — generates and persists stable IDs for properties, contacts, and groups.

IDs are sequential (PRO_00001, CON_00001, GRP_00001) and persist across
Compiler re-runs via the id_mappings table (a system table that is never
dropped). Once an ARN gets a PRO_ ID, it keeps that ID forever.

Stable anchors:
  - Properties: 20-digit ARN
  - Contacts: name fingerprint (UPPERCASE first+last, whitespace collapsed)
  - Groups: normalized party name (UPPERCASE, legal suffixes stripped)
"""


LEGAL_SUFFIXES = [
    'INCORPORATED', 'INC.', 'INC',
    'CORPORATION', 'CORP.', 'CORP',
    'LIMITED', 'LTD.', 'LTD',
    'LLC', 'LP', 'LLP',
    'CO.', 'CO',
]


# "HON" is intentionally excluded — it appears as a Chinese given name (e.g.,
# "Hon Lam", "Hon Lee") and stripping it would mangle those records. The
# explicit "HON." / "HONOURABLE" forms remain since they're unambiguous.
LEADING_HONORIFICS = {
    'DR', 'DR.', 'MR', 'MR.', 'MRS', 'MRS.',
    'MS', 'MS.', 'MISS',
    'PROF', 'PROF.', 'PROFESSOR',
    'HON.', 'HONOURABLE',
    'SIR', 'MADAM', 'MADAME', 'DAME',
    'REV', 'REV.', 'REVEREND', 'FATHER', 'FR', 'FR.',
    'LORD', 'LADY', 'MX', 'MX.',
}


def strip_leading_honorifics(tokens):
    """Drop any leading honorific tokens (Dr, Mr, Rev, Father, etc.).
    Operates on already-uppercased tokens and returns a list."""
    out = list(tokens)
    while out and out[0] in LEADING_HONORIFICS:
        out = out[1:]
    return out


def make_name_fingerprint(name):
    """Create a stable fingerprint for a contact name.
    UPPERCASE, trim, collapse whitespace, strip leading honorifics.
    'Lee Greenwood'        -> 'LEE GREENWOOD'
    'Dr Harry Aronowicz'   -> 'HARRY ARONOWICZ'
    'Father John Boutros'  -> 'JOHN BOUTROS'
    """
    if not name:
        return ''
    tokens = strip_leading_honorifics(name.upper().split())
    return ' '.join(tokens)


def normalize_group_name(name):
    """Normalize a party/company name for group matching.
    UPPERCASE, strip legal suffixes, collapse whitespace.
    'Springerhill Farms Inc' -> 'SPRINGERHILL FARMS'
    """
    if not name:
        return ''
    name = name.upper().strip()
    for suffix in LEGAL_SUFFIXES:
        if name.endswith(' ' + suffix):
            name = name[:-len(suffix) - 1].strip()
    return ' '.join(name.split())


class IDRegistry:
    """Manages stable ID assignment backed by SQLite id_mappings table.

    The id_mappings table is a SYSTEM table (never dropped by the compiler),
    which means anchor→ID mappings persist across full recompiles. This ensures
    that CRM data (deals, group_contacts, notes, etc.) always references valid,
    stable entity IDs.
    """

    def __init__(self, conn):
        self.conn = conn
        self._counters = {}
        self._maps = {
            'property': {},   # arn -> PRO_NNNNN
            'contact': {},    # fingerprint -> CON_NNNNN
            'group': {},      # normalized_name -> GRP_NNNNN
        }

    def load(self):
        """Load existing ID mappings from the id_mappings system table."""
        # Load counters from app_meta
        for prefix in ['PRO', 'CON', 'GRP']:
            row = self.conn.execute(
                "SELECT value FROM app_meta WHERE key = ?",
                (f'next_{prefix.lower()}_id',)
            ).fetchone()
            self._counters[prefix] = int(row[0]) if row else 1

        # Load mappings from id_mappings (SYSTEM table — survives drops)
        for row in self.conn.execute(
            "SELECT anchor_key, entity_id FROM id_mappings WHERE entity_type = 'property'"
        ):
            self._maps['property'][row[0]] = row[1]
        for row in self.conn.execute(
            "SELECT anchor_key, entity_id FROM id_mappings WHERE entity_type = 'contact'"
        ):
            self._maps['contact'][row[0]] = row[1]
        for row in self.conn.execute(
            "SELECT anchor_key, entity_id FROM id_mappings WHERE entity_type = 'group'"
        ):
            self._maps['group'][row[0]] = row[1]

        print(f'  ID Registry: {len(self._maps["property"]):,} properties, '
              f'{len(self._maps["contact"]):,} contacts, '
              f'{len(self._maps["group"]):,} groups')

    def save_counters(self):
        """Persist current counters to app_meta."""
        for prefix in ['PRO', 'CON', 'GRP']:
            self.conn.execute(
                "INSERT OR REPLACE INTO app_meta (key, value, updated_at) VALUES (?, ?, datetime('now'))",
                (f'next_{prefix.lower()}_id', str(self._counters[prefix]))
            )
        self.conn.commit()

    def _next_id(self, prefix):
        """Generate the next sequential ID for a prefix."""
        n = self._counters.get(prefix, 1)
        self._counters[prefix] = n + 1
        return f'{prefix}_{n:05d}'

    def get_or_create_property_id(self, arn):
        """Get existing or create new PRO_ ID for an ARN."""
        if arn in self._maps['property']:
            return self._maps['property'][arn]
        new_id = self._next_id('PRO')
        self._maps['property'][arn] = new_id
        self.conn.execute(
            "INSERT OR IGNORE INTO id_mappings (entity_type, anchor_key, entity_id) VALUES (?, ?, ?)",
            ('property', arn, new_id)
        )
        return new_id

    def get_or_create_contact_id(self, fingerprint):
        """Get existing or create new CON_ ID for a name fingerprint."""
        if fingerprint in self._maps['contact']:
            return self._maps['contact'][fingerprint]
        new_id = self._next_id('CON')
        self._maps['contact'][fingerprint] = new_id
        self.conn.execute(
            "INSERT OR IGNORE INTO id_mappings (entity_type, anchor_key, entity_id) VALUES (?, ?, ?)",
            ('contact', fingerprint, new_id)
        )
        return new_id

    def get_or_create_group_id(self, normalized_name):
        """Get existing or create new GRP_ ID for a normalized group name."""
        if normalized_name in self._maps['group']:
            return self._maps['group'][normalized_name]
        new_id = self._next_id('GRP')
        self._maps['group'][normalized_name] = new_id
        self.conn.execute(
            "INSERT OR IGNORE INTO id_mappings (entity_type, anchor_key, entity_id) VALUES (?, ?, ?)",
            ('group', normalized_name, new_id)
        )
        return new_id
