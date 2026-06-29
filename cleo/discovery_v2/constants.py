"""Tunable knobs for Layer 2 Plan A. Adjust here and re-run the builder."""
from __future__ import annotations

# ── Stage A1: Stem extraction ──────────────────────────────────────────────
# A candidate stem is promoted to verified only when both thresholds are met.
STEM_PROMOTION_DOMINANCE = 0.6
STEM_PROMOTION_VOLUME    = 5

# Multi-level n-gram distinctiveness for stem picking.
#
# When no 1-gram in a brand_phrase is distinctive (every token filtered as
# english_common, place_name, or industry_stopword), the stem builder walks up
# to 2-grams and 3-grams looking for a phrase that's specific to a real brand.
# An n-gram at level N is treated as distinctive iff it appears in fewer than
# N_GRAM_GENERIC_THRESHOLD[N] distinct brand_phrases corpus-wide.
#
# Rationale: "real estate" 2-gram appears in 963 phrases → generic.
# "sun life" 2-gram appears in 9 → specific (brand identifier).
# "real estate services" 3-gram appears in 20 → generic.
# "sun life assurance" 3-gram appears in 4 → specific.
N_GRAM_GENERIC_THRESHOLD = {
    2: 10,
    3: 5,
}

# ── Stage A2: Anchor uniqueness scoring ────────────────────────────────────
# score = dominance_share * log(volume + 1).
# An anchor must clear this score to participate in seeding.
ANCHOR_SEEDING_SCORE_THRESHOLD = 1.5

# A "corroborating" anchor needs a lower bar (used in candidate-tier rule).
ANCHOR_CORROBORATION_SCORE_THRESHOLD = 0.5

# ── Stage A3: Group seeding & tiering ──────────────────────────────────────
TIER_CONFIRMED_MIN_CONFIDENCE = 0.75
TIER_PROBABLE_MIN_CONFIDENCE  = 0.4
# Anything below TIER_PROBABLE_MIN_CONFIDENCE is candidate.

# Confidence formula reference ceiling — keeps confidence stable across runs.
ANCHOR_SCORE_CEILING = 5.0

# ── Stage A4: Group expansion ──────────────────────────────────────────────
# Match scores for attaching a party-side to a seeded group.
MATCH_SCORE_DIRECT_STEM_HIT             = 1.0
MATCH_SCORE_PHONE_MATCH                 = 0.7
MATCH_SCORE_ADDRESS_PLUS_CONTACT        = 0.7
MATCH_SCORE_ADDRESS_UNIT_ALONE          = 0.7
MATCH_SCORE_PHONE_BRAND_CONTRADICTION   = -0.5  # explicitly do-not-attach
MATCH_SCORE_SINGLE_WEAK_SIGNAL          = 0.3

# Threshold for actually attaching a party-side (Stage A4).
EXPANSION_ATTACH_THRESHOLD = 0.5

# ── Plan H2: Tenure shape thresholds ──────────────────────────────────────
# Tenures are observed first→last per (anchor, stem). The conflict detector
# uses these thresholds to flag suspicious shape (low volume, short span).

# A tenure with fewer party-sides than this AND duration < MIN_PERMANENT_TENURE_DAYS
# gets a 'transient_tenure' flag (e.g. one-off transactions at multi-tenant
# buildings).
MIN_TENURE_PARTY_COUNT = 3
MIN_PERMANENT_TENURE_DAYS = 365  # 1 year
