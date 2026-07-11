"""EEG §51 negative-price rule cohort mapping (docs/MODEL_CARD.md, §51 table).

One config int per commissioning-year cohort, consumed by the engine as
Assumptions.neg_price_rule_hours (premium lost during negative-price streaks of
at least N consecutive hours; 8760 = rule never triggers; 0 = every negative hour).

Documented simplification (MODEL_CARD): cohorts are keyed on commissioning year
only, not tender-award date; the 2023+ event-year stepdown is collapsed to its
steady state (1h), and the post-Solarspitzengesetz quarter-hour rule (≥ 2025)
is approximated at hourly resolution as 0.
"""

from __future__ import annotations


def neg_price_rule_hours(commissioning_year: int) -> int:
    """Return the §51 streak threshold (hours) for a commissioning-year cohort."""
    if commissioning_year <= 2015:
        return 8760  # sentinel: pre-2016 plants have no negative-price rule
    if commissioning_year <= 2020:
        return 6  # EEG 2017 §51: ≥ 6 consecutive negative hours
    if commissioning_year <= 2022:
        return 4  # EEG 2021 §51: ≥ 4 consecutive hours
    if commissioning_year <= 2024:
        return 1  # 2023+ stepdown, collapsed to steady state (MODEL_CARD deviation note)
    return 0  # ≥ 2025 (Solarspitzengesetz): premium = 0 in every negative interval
