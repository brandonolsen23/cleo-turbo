"""Tunable knobs for Layer 2 Plan A. Adjust here and re-run the builder."""
from __future__ import annotations

# ── Stage A1: Stem extraction ──────────────────────────────────────────────
# A candidate stem is promoted to verified only when both thresholds are met.
STEM_PROMOTION_DOMINANCE = 0.6
STEM_PROMOTION_VOLUME    = 5

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
