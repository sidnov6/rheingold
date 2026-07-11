"""Revenue module (spec §8.3). Hourly shaping over one representative year.

The engine receives a representative hourly price year plus the farm's normalized
hourly generation shape (MarketInputs). Market leg: Σ_h E_h × price_h. EEG premium
leg: eligible energy earns max(0, AW − Marktwert_month) × 10 EUR/MWh on top,
where eligibility removes hours disqualified by the §51 negative-price rule
(consecutive-negative-price streaks ≥ neg_price_rule_hours; 0 = every negative
hour). Marktwert scales with the price-level shock (market values track prices).
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import CT_KWH_TO_EUR_MWH, Assumptions, MarketInputs, Shocks


def negative_streak_mask(prices: list[float], rule_hours: int) -> list[bool]:
    """True where the §51 rule kills the premium.

    rule_hours == 0: every negative hour. rule_hours >= 1: all hours inside a
    maximal run of consecutive negative-price hours whose length >= rule_hours.
    """
    n = len(prices)
    mask = [False] * n
    if rule_hours <= 0:
        for i, p in enumerate(prices):
            if p < 0.0:
                mask[i] = True
        return mask
    i = 0
    while i < n:
        if prices[i] < 0.0:
            j = i
            while j < n and prices[j] < 0.0:
                j += 1
            if j - i >= rule_hours:
                for k in range(i, j):
                    mask[k] = True
            i = j
        else:
            i += 1
    return mask


@dataclass(frozen=True)
class MarketStats:
    """Representative-year aggregates, all pure functions of MarketInputs + rule."""

    wind_weighted_price: float  # EUR/MWh earned per MWh at base price level
    mean_price: float
    capture_rate: float
    month_share: list[float]  # share of annual energy per month, sums to ~1
    month_disq_share: list[float]  # share of annual energy in §51-disqualified hours, per month
    negative_hours: int


def market_stats(market: MarketInputs, rule_hours: int) -> MarketStats:
    prices = market.price_eur_mwh_hourly
    shape = market.cf_shape_hourly
    months = market.hour_month
    mask = negative_streak_mask(prices, rule_hours)

    wwp = 0.0
    month_share = [0.0] * 12
    month_disq = [0.0] * 12
    for h, (p, s, m) in enumerate(zip(prices, shape, months, strict=True)):
        wwp += s * p
        month_share[m] += s
        if mask[h]:
            month_disq[m] += s
    mean_price = sum(prices) / len(prices)
    capture = wwp / mean_price if mean_price > 0 else 1.0
    return MarketStats(
        wind_weighted_price=wwp,
        mean_price=mean_price,
        capture_rate=capture,
        month_share=month_share,
        month_disq_share=month_disq,
        negative_hours=sum(1 for p in prices if p < 0.0),
    )


def price_factor(t: int, shocks: Shocks) -> float:
    """Multiplicative price-level factor for project year t (1-based)."""
    if shocks.price_level != 0.0 and (shocks.price_years is None or t <= shocks.price_years):
        return 1.0 + shocks.price_level
    return 1.0


def premium_per_mwh(
    aw_ct_kwh: float,
    market: MarketInputs,
    stats: MarketStats,
    shocks: Shocks,
    factor: float,
) -> float:
    """EUR per MWh of *total* production earned by the premium leg in a support year.

    Per month: eligible share × max(0, AW − Marktwert_m × factor) × 10.
    The §51-disqualified share is scaled by shocks.negative_hours_multiplier
    (capped so the eligible share never goes below zero).
    """
    total = 0.0
    for m in range(12):
        share = stats.month_share[m]
        if share <= 0.0:
            continue
        disq = min(share, stats.month_disq_share[m] * shocks.negative_hours_multiplier)
        eligible = share - disq
        premium_eur_mwh = max(
            0.0, (aw_ct_kwh - market.marktwert_ct_kwh_by_month[m] * factor) * CT_KWH_TO_EUR_MWH
        )
        total += eligible * premium_eur_mwh
    return total


def annual_revenue(
    annual_mwh: list[float],
    a: Assumptions,
    market: MarketInputs,
    stats: MarketStats,
    shocks: Shocks,
    aw_ct_kwh: float | None,
) -> tuple[list[float], list[float]]:
    """Return (revenue_market, revenue_premium) per project year.

    - eeg_premium: market leg all years; premium leg only during support years
      (needs aw_ct_kwh; None → premium leg is zero).
    - merchant: market leg only.
    - ppa: flat PPA price on all volume, no market/premium legs (price shocks do
      not touch contracted PPA revenue — documented in MODEL_CARD).
    """
    rev_market: list[float] = []
    rev_premium: list[float] = []
    for idx, e_t in enumerate(annual_mwh):
        t = idx + 1
        f = price_factor(t, shocks)
        if a.revenue_mode == "ppa":
            if a.ppa_price_eur_mwh is None:
                raise ValueError("revenue_mode='ppa' requires ppa_price_eur_mwh")
            rev_market.append(e_t * a.ppa_price_eur_mwh)
            rev_premium.append(0.0)
            continue
        market_leg = e_t * stats.wind_weighted_price * f
        premium_leg = 0.0
        if a.revenue_mode == "eeg_premium" and t <= a.eeg_support_years and aw_ct_kwh is not None:
            premium_leg = e_t * premium_per_mwh(aw_ct_kwh, market, stats, shocks, f)
        rev_market.append(market_leg)
        rev_premium.append(premium_leg)
    return rev_market, rev_premium
