"""
Reconciler — generates and persists stable IDs for properties, contacts, and groups.

IDs are sequential (PRO_00001, CON_00001, GRP_00001) and persist across
Compiler re-runs via the app_meta table. Once an ARN gets a PRO_ ID, it
keeps that ID forever.

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


def make_name_fingerprint(name):
    """Create a stable fingerprint for a contact name.
    UPPERCASE, trimmed, whitespace collapsed.
    'Lee Greenwood' -> 'LEE GREENWOOD'
    """
    if not name:
        return ''
    return ' '.join(name.upper().split())


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
    """Manages stable ID assignment backed by SQLite app_meta."""

    def __init__(self, conn):
        self.conn = conn
        self._counters = {}
        self._maps = {
            'property': {},   # arn -> PRO_NNNNN
            'contact': {},    # fingerprint -> CON_NNNNN
            'group': {},      # normalized_name -> GRP_NNNNN
        }

    def load(self):
        """Load existing ID mappings from the database."""
        # Load counters from app_meta
        for prefix in ['PRO', 'CON', 'GRP']:
            row = self.conn.execute(
                "SELECT value FROM app_meta WHERE key = ?",
                (f'next_{prefix.lower()}_id',)
            ).fetchone()
            self._counters[prefix] = int(row[0]) if row else 1

        # Load existing mappings from tables
        for row in self.conn.execute("SELECT arn, id FROM properties"):
            self._maps['property'][row[0]] = row[1]
        for row in self.conn.execute("SELECT name_fingerprint, id FROM contacts"):
            self._maps['contact'][row[0]] = row[1]
        for row in self.conn.execute("SELECT normalized_name, id FROM groups"):
            self._maps['group'][row[0]] = row[1]

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
        return new_id

    def get_or_create_contact_id(self, fingerprint):
        """Get existing or create new CON_ ID for a name fingerprint."""
        if fingerprint in self._maps['contact']:
            return self._maps['contact'][fingerprint]
        new_id = self._next_id('CON')
        self._maps['contact'][fingerprint] = new_id
        return new_id

    def get_or_create_group_id(self, normalized_name):
        """Get existing or create new GRP_ ID for a normalized group name."""
        if normalized_name in self._maps['group']:
            return self._maps['group'][normalized_name]
        new_id = self._next_id('GRP')
        self._maps['group'][normalized_name] = new_id
        return new_id
