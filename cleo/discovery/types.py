"""
Data types for the discovery algorithm.

Signal: a single piece of evidence linking two groups (shared address, contact, etc.)
Cluster: a set of groups believed to belong to the same portfolio
Evidence: a confirmed signal with rule attribution
RunConfig: parameters for a discovery run
RunResult: output of a complete run
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Signal:
    """A raw signal extracted from the database."""
    signal_type: str       # 'address', 'contact', 'phone', 'trade_name', 'care_of', 'entity', 'name_fragment'
    signal_value: str      # normalized value
    group_id: str          # GRP_ ID
    source_id: str         # transaction source_id where this signal was found
    side: str              # 'seller' or 'buyer'
    raw_value: str = ''    # original value before normalization


@dataclass
class Evidence:
    """A confirmed link between two groups with rule attribution."""
    signal_type: str
    signal_value: str
    source_group_id: str
    target_group_id: str
    source_id: str
    rule_id: str           # '4a', '4b', etc.
    confidence: float      # 0.0 - 1.0
    iteration: int = 0


@dataclass
class Cluster:
    """A discovered portfolio cluster."""
    cluster_id: str         # generated UUID or sequential ID
    anchor_group_id: str    # the "parent" group (highest tx count)
    anchor_name: str        # display name of anchor
    member_group_ids: set = field(default_factory=set)
    confirmed_addresses: set = field(default_factory=set)
    confirmed_contacts: set = field(default_factory=set)
    confirmed_phones: set = field(default_factory=set)
    confirmed_entities: set = field(default_factory=set)
    confirmed_name_fragments: set = field(default_factory=set)
    evidence: list = field(default_factory=list)  # list of Evidence
    confidence: float = 0.0
    status: str = 'pending'  # 'pending', 'auto_confirmed', 'needs_review', 'rejected'

    @property
    def member_count(self) -> int:
        return len(self.member_group_ids)


@dataclass
class ContactTenure:
    """A contact's tenure at a specific group/cluster."""
    contact_id: str
    contact_name: str
    group_id: str
    first_seen: str        # ISO date
    last_seen: str         # ISO date
    transaction_count: int
    is_distinctive: bool = False  # all appearances in one cluster?


@dataclass
class RunConfig:
    """Configuration for a discovery run."""
    mode: str = 'validate'  # 'validate', 'execute', 'incremental', 'dry_run'
    max_iterations: int = 5
    min_confidence_auto: float = 0.90   # auto-confirm threshold
    min_confidence_suggest: float = 0.50  # suggestion threshold


@dataclass
class RunResult:
    """Output of a complete discovery run."""
    run_id: str
    mode: str
    clusters_found: int = 0
    merges_executed: int = 0
    suggestions_created: int = 0
    groups_processed: int = 0
    iterations: int = 0
    ground_truth_results: Optional[dict] = None  # {portfolio_name: {precision, recall, missing, unexpected}}
