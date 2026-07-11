"""Revenue module unit tests (spec §8.3) + underwrite effective-life truncation.

All market data below is SYNTHETIC — clearly-labeled test artifacts. Every expected
value is hand-derived from the §8.3 formulas, independent of revenue.py.

Streak-market fixture (flat shape 1/8760, price 50 EUR/MWh except):
    hours 100–105  (6h, month 0):  −10   → disqualified at rule 4
    hours 200–202  (3h, month 0):   −5   → BELOW the 4h threshold, keeps premium
    hours 8756–8759 (4h, month 11): −20  → streak ending exactly at the array end
negative_hours = 13; rule-4 masked hours = 10; rule-0 masked = 13; rule-8760 = 0.
Σ price = 8747×50 − 60 − 15 − 80 = 437_195 → mean = wwp = 437_195/8760 ≈ 49.908
(flat shape ⇒ capture = 1); the negative hours stay IN the market leg.

Premium (§8.3.2): per month, eligible_share × max(0, AW − MW_m × factor) × 10.
Flat MW 5.0, AW 6.0 → 10 EUR per eligible MWh:
    rule 4:    (1 − 10/8760) × 10        rule 0: (1 − 13/8760) × 10
    rule 8760: 10 exactly (sentinel disables §51)
Engine convention (revenue.py docstring, MODEL_CARD): the Marktwert scales with
the price-level shock factor — market values track prices.

Non-flat Marktwert case: MW_m = [4.0, 4.5, 5.0, 5.5, 6.0, 6.5, 7.0, 6.5, 6.0,
5.5, 5.0, 4.5] ct/kWh, flat shape (each month share exactly 730/8760 = 1/12),
AW 5.8 → Σ_m max(0, 5.8 − MW_m) = 1.8+1.3+0.8+0.3+0+0+0+0+0+0.3+0.8+1.3 = 6.6
→ premium = 6.6 × 10 / 12 = 5.5 EUR/MWh exactly.

Capture-rate fixture: 4380 h at 20 EUR/MWh with shape weight 3, 4380 h at
60 EUR/MWh with weight 1 → wwp = (3×20 + 60)/4 = 30, mean = 40, capture = 0.75.
"""

from itertools import groupby

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from rheingold_engine.models import Assumptions, FarmInput, MarketInputs, Shocks
from rheingold_engine.revenue import (
    annual_revenue,
    market_stats,
    negative_streak_mask,
    premium_per_mwh,
    price_factor,
)
from rheingold_engine.underwrite import _effective_life, underwrite

EXACT = 1e-9
HOURS = 8760
HPM = 730  # 12 months × 730 h — same month grid as MarketInputs.flat


def _hour_month() -> list[int]:
    return [min(h // HPM, 11) for h in range(HOURS)]


def _streak_prices() -> list[float]:
    prices = [50.0] * HOURS
    for h in range(100, 106):  # 6h streak, month 0
        prices[h] = -10.0
    for h in range(200, 203):  # 3h streak, month 0 — below rule 4
        prices[h] = -5.0
    for h in range(8756, 8760):  # 4h streak ending at the array end, month 11
        prices[h] = -20.0
    return prices


STREAK_WWP = 437_195.0 / 8760.0  # hand sum, see module docstring


@pytest.fixture(scope="module")
def streak_market() -> MarketInputs:
    return MarketInputs(
        price_eur_mwh_hourly=_streak_prices(),
        cf_shape_hourly=[1.0 / HOURS] * HOURS,
        hour_month=_hour_month(),
        marktwert_ct_kwh_by_month=[5.0] * 12,
        source_note="synthetic streak-market test artifact",
    )


@pytest.fixture(scope="module")
def streak_stats4(streak_market) -> object:
    return market_stats(streak_market, rule_hours=4)


# ------------------------------------------------------- §51 streak detector


def test_streak_exactly_at_threshold_is_masked():
    prices = [50.0, -1.0, -1.0, -1.0, -1.0, 50.0]
    assert negative_streak_mask(prices, 4) == [False, True, True, True, True, False]


def test_streak_below_threshold_keeps_premium():
    prices = [50.0, -1.0, -1.0, -1.0, 50.0]
    assert negative_streak_mask(prices, 4) == [False] * 5


def test_streak_running_into_array_end_is_masked():
    prices = [50.0, 50.0, -1.0, -1.0, -1.0, -1.0]
    assert negative_streak_mask(prices, 4) == [False, False, True, True, True, True]


def test_rule_zero_masks_every_negative_hour():
    prices = [50.0, -0.01, 50.0, -5.0, -5.0, 50.0]
    assert negative_streak_mask(prices, 0) == [False, True, False, True, True, False]


def test_rule_one_equals_rule_zero():
    prices = [50.0, -0.01, 50.0, -5.0, -5.0, 0.0, -3.0]
    assert negative_streak_mask(prices, 1) == negative_streak_mask(prices, 0)


def test_zero_price_is_not_negative():
    prices = [0.0, -1.0, -1.0, 0.0, -1.0, -1.0]
    # zero splits the run: two 2h streaks, so rule 4 masks nothing
    assert negative_streak_mask(prices, 4) == [False] * 6
    assert negative_streak_mask(prices, 2) == [False, True, True, False, True, True]


def test_rule_8760_sentinel_disables_rule(streak_market):
    assert negative_streak_mask(streak_market.price_eur_mwh_hourly, 8760) == [False] * HOURS


def _reference_mask(prices: list[float], rule: int) -> list[bool]:
    """Independent §51 reference: groupby runs of negative prices."""
    if rule <= 0:
        return [p < 0 for p in prices]
    mask = [False] * len(prices)
    idx = 0
    for negative, group in groupby(prices, key=lambda p: p < 0):
        run = len(list(group))
        if negative and run >= rule:
            mask[idx : idx + run] = [True] * run
        idx += run
    return mask


@settings(max_examples=200, derandomize=True, deadline=None)
@given(
    prices=st.lists(st.sampled_from([-30.0, -1.0, -0.5, 0.0, 0.01, 45.0]), min_size=1, max_size=80),
    rule=st.integers(min_value=0, max_value=6),
)
def test_streak_mask_matches_independent_reference(prices, rule):
    assert negative_streak_mask(prices, rule) == _reference_mask(prices, rule)


# ----------------------------------------------------------- market stats


def test_streak_market_stats_hand_derived(streak_market, streak_stats4):
    s = streak_stats4
    assert s.wind_weighted_price == pytest.approx(STREAK_WWP, rel=EXACT)
    assert s.mean_price == pytest.approx(STREAK_WWP, rel=EXACT)
    assert s.capture_rate == pytest.approx(1.0, rel=EXACT)  # flat shape
    assert s.negative_hours == 13
    # rule 4 disqualifies 6h in month 0 and the 4h end streak in month 11 — not the 3h streak
    assert s.month_disq_share[0] == pytest.approx(6.0 / HOURS, rel=EXACT)
    assert s.month_disq_share[11] == pytest.approx(4.0 / HOURS, rel=EXACT)
    assert sum(s.month_disq_share) == pytest.approx(10.0 / HOURS, rel=EXACT)
    assert sum(s.month_share) == pytest.approx(1.0, rel=EXACT)
    for m in range(12):
        assert s.month_share[m] == pytest.approx(HPM / HOURS, rel=EXACT)


def test_rule_zero_also_disqualifies_short_streaks(streak_market):
    s0 = market_stats(streak_market, rule_hours=0)
    assert sum(s0.month_disq_share) == pytest.approx(13.0 / HOURS, rel=EXACT)
    assert s0.month_disq_share[0] == pytest.approx(9.0 / HOURS, rel=EXACT)


def test_capture_rate_peaky_year_hand_computed():
    """Wind concentrated in cheap hours → capture 0.75 = 30/40 exactly."""
    half = HOURS // 2
    prices = [20.0] * half + [60.0] * half
    weights = [3.0] * half + [1.0] * half
    total = sum(weights)
    market = MarketInputs(
        price_eur_mwh_hourly=prices,
        cf_shape_hourly=[w / total for w in weights],
        hour_month=_hour_month(),
        marktwert_ct_kwh_by_month=[5.0] * 12,
        source_note="synthetic capture-rate test artifact",
    )
    s = market_stats(market, rule_hours=4)
    assert s.wind_weighted_price == pytest.approx(30.0, rel=EXACT)
    assert s.mean_price == pytest.approx(40.0, rel=EXACT)
    assert s.capture_rate == pytest.approx(0.75, rel=EXACT)
    assert s.negative_hours == 0


# ------------------------------------------------------------- premium leg


def test_premium_monthly_max_with_nonflat_marktwert():
    """Σ_m share × max(0, AW − MW_m) × 10 with per-month flooring → 5.5 EUR/MWh."""
    mw_by_month = [4.0, 4.5, 5.0, 5.5, 6.0, 6.5, 7.0, 6.5, 6.0, 5.5, 5.0, 4.5]
    market = MarketInputs(
        price_eur_mwh_hourly=[50.0] * HOURS,
        cf_shape_hourly=[1.0 / HOURS] * HOURS,
        hour_month=_hour_month(),
        marktwert_ct_kwh_by_month=mw_by_month,
        source_note="synthetic non-flat-marktwert test artifact",
    )
    stats = market_stats(market, rule_hours=4)
    got = premium_per_mwh(5.8, market, stats, Shocks(), factor=1.0)
    assert got == pytest.approx(5.5, rel=EXACT)
    # AW at/below every month's Marktwert → premium is 0, never negative
    assert premium_per_mwh(4.0, market, stats, Shocks(), factor=1.0) == pytest.approx(
        0.0, abs=1e-12
    )
    assert premium_per_mwh(3.0, market, stats, Shocks(), factor=1.0) == pytest.approx(
        0.0, abs=1e-12
    )


def test_premium_excludes_rule4_streak_hours(streak_market, streak_stats4):
    got = premium_per_mwh(6.0, streak_market, streak_stats4, Shocks(), factor=1.0)
    assert got == pytest.approx((1.0 - 10.0 / HOURS) * 10.0, rel=EXACT)


def test_premium_rule0_excludes_all_negative_hours(streak_market):
    stats0 = market_stats(streak_market, rule_hours=0)
    got = premium_per_mwh(6.0, streak_market, stats0, Shocks(), factor=1.0)
    assert got == pytest.approx((1.0 - 13.0 / HOURS) * 10.0, rel=EXACT)


def test_premium_rule_sentinel_no_51_losses(streak_market):
    stats_off = market_stats(streak_market, rule_hours=8760)
    got = premium_per_mwh(6.0, streak_market, stats_off, Shocks(), factor=1.0)
    assert got == pytest.approx(10.0, rel=EXACT)


def test_negative_hours_multiplier_scales_disqualified_share(streak_market, streak_stats4):
    got0 = premium_per_mwh(
        6.0, streak_market, streak_stats4, Shocks(negative_hours_multiplier=0.0), 1.0
    )
    got3 = premium_per_mwh(
        6.0, streak_market, streak_stats4, Shocks(negative_hours_multiplier=3.0), 1.0
    )
    assert got0 == pytest.approx(10.0, rel=EXACT)  # ×0 → no §51 losses at all
    assert got3 == pytest.approx((1.0 - 30.0 / HOURS) * 10.0, rel=EXACT)


def test_negative_hours_multiplier_caps_eligible_share_at_zero(streak_market, streak_stats4):
    """Huge multiplier: months 0 and 11 go fully ineligible (share floor at 0),
    the ten clean months keep the full 10 EUR/MWh → 10 × 10/12."""
    got = premium_per_mwh(
        6.0, streak_market, streak_stats4, Shocks(negative_hours_multiplier=1e9), 1.0
    )
    assert got == pytest.approx(10.0 * 10.0 / 12.0, rel=EXACT)


# -------------------------------------------------- annual revenue by mode


@pytest.fixture(scope="module")
def flat_50_5() -> MarketInputs:
    return MarketInputs.flat(price_eur_mwh=50.0, marktwert_ct_kwh=5.0)


@pytest.fixture(scope="module")
def flat_50_5_stats(flat_50_5) -> object:
    return market_stats(flat_50_5, rule_hours=4)


def test_eeg_premium_stops_after_support_years(flat_50_5, flat_50_5_stats):
    a = Assumptions(anzulegender_wert_ct_kwh=6.0, eeg_support_years=3)
    mwh = [1000.0] * 5
    rev_market, rev_premium = annual_revenue(mwh, a, flat_50_5, flat_50_5_stats, Shocks(), 6.0)
    assert rev_market == pytest.approx([50_000.0] * 5, rel=EXACT)
    assert rev_premium[:3] == pytest.approx([10_000.0] * 3, rel=EXACT)
    assert rev_premium[3:] == [0.0, 0.0]  # support over, merchant leg continues


def test_eeg_support_zero_years_no_premium(flat_50_5, flat_50_5_stats):
    a = Assumptions(anzulegender_wert_ct_kwh=6.0, eeg_support_years=0)
    _, rev_premium = annual_revenue([1000.0] * 3, a, flat_50_5, flat_50_5_stats, Shocks(), 6.0)
    assert rev_premium == [0.0, 0.0, 0.0]


def test_eeg_none_aw_means_zero_premium_leg(flat_50_5, flat_50_5_stats):
    a = Assumptions()  # AW None (underwrite() would solve break-even first)
    rev_market, rev_premium = annual_revenue(
        [1000.0] * 2, a, flat_50_5, flat_50_5_stats, Shocks(), None
    )
    assert rev_market == pytest.approx([50_000.0] * 2, rel=EXACT)
    assert rev_premium == [0.0, 0.0]


def test_merchant_mode_market_leg_only(flat_50_5, flat_50_5_stats):
    a = Assumptions(revenue_mode="merchant", anzulegender_wert_ct_kwh=6.0)
    rev_market, rev_premium = annual_revenue(
        [1000.0, 2000.0], a, flat_50_5, flat_50_5_stats, Shocks(), 6.0
    )
    assert rev_market == pytest.approx([50_000.0, 100_000.0], rel=EXACT)
    assert rev_premium == [0.0, 0.0]  # no premium even though an AW is supplied


def test_negative_prices_stay_in_market_leg(streak_market):
    """§51 removes premium, not market revenue: the market leg is identical for
    rule 0/4/8760 and prices below zero drag wwp under 50."""
    mwh = [1000.0] * 3
    legs = {}
    for rule in (0, 4, 8760):
        stats = market_stats(streak_market, rule_hours=rule)
        a = Assumptions(anzulegender_wert_ct_kwh=6.0, neg_price_rule_hours=rule)
        rev_market, _ = annual_revenue(mwh, a, streak_market, stats, Shocks(), 6.0)
        legs[rule] = rev_market
    assert legs[0] == pytest.approx(legs[4], rel=EXACT)
    assert legs[4] == pytest.approx(legs[8760], rel=EXACT)
    assert legs[4][0] == pytest.approx(1000.0 * STREAK_WWP, rel=EXACT)
    assert legs[4][0] < 1000.0 * 50.0


def test_ppa_flat_price_all_volume(flat_50_5, flat_50_5_stats):
    a = Assumptions(revenue_mode="ppa", ppa_price_eur_mwh=72.5)
    rev_market, rev_premium = annual_revenue(
        [1000.0, 900.0], a, flat_50_5, flat_50_5_stats, Shocks(), None
    )
    assert rev_market == pytest.approx([72_500.0, 65_250.0], rel=EXACT)
    assert rev_premium == [0.0, 0.0]


def test_ppa_ignores_price_shocks(flat_50_5, flat_50_5_stats):
    """Contracted PPA revenue is shock-invariant (documented in revenue.py &
    MODEL_CARD): a −40% price-level shock must not move a single year."""
    a = Assumptions(revenue_mode="ppa", ppa_price_eur_mwh=72.5)
    mwh = [1000.0] * 4
    base, _ = annual_revenue(mwh, a, flat_50_5, flat_50_5_stats, Shocks(), None)
    shocked, _ = annual_revenue(mwh, a, flat_50_5, flat_50_5_stats, Shocks(price_level=-0.40), None)
    assert shocked == pytest.approx(base, rel=EXACT)


def test_ppa_without_price_raises(flat_50_5, flat_50_5_stats):
    a = Assumptions(revenue_mode="ppa")  # ppa_price_eur_mwh None
    with pytest.raises(ValueError, match="ppa_price_eur_mwh"):
        annual_revenue([1000.0], a, flat_50_5, flat_50_5_stats, Shocks(), None)


# ------------------------------------------------- price-shock year windows


def test_price_factor_window():
    s = Shocks(price_level=-0.35, price_years=2)
    assert price_factor(1, s) == pytest.approx(0.65)
    assert price_factor(2, s) == pytest.approx(0.65)
    assert price_factor(3, s) == pytest.approx(1.0)
    assert price_factor(1, Shocks(price_level=0.4, price_years=None)) == pytest.approx(1.4)
    assert price_factor(99, Shocks(price_level=0.4, price_years=None)) == pytest.approx(1.4)
    assert price_factor(1, Shocks(price_level=-0.35, price_years=0)) == pytest.approx(1.0)


def test_price_shock_first_n_years_market_and_premium(flat_50_5, flat_50_5_stats):
    """Years 1–2 at ×0.65: market leg 50→32.5 EUR/MWh; the Marktwert tracks the
    price level (engine convention), so the premium widens to (6 − 5×0.65)×10 =
    27.5 EUR/MWh while shocked, then reverts to 10."""
    a = Assumptions(anzulegender_wert_ct_kwh=6.0, eeg_support_years=20)
    mwh = [1000.0] * 4
    shocks = Shocks(price_level=-0.35, price_years=2)
    rev_market, rev_premium = annual_revenue(mwh, a, flat_50_5, flat_50_5_stats, shocks, 6.0)
    assert rev_market == pytest.approx([32_500.0, 32_500.0, 50_000.0, 50_000.0], rel=EXACT)
    assert rev_premium == pytest.approx([27_500.0, 27_500.0, 10_000.0, 10_000.0], rel=EXACT)


def test_price_spike_can_zero_the_premium(flat_50_5, flat_50_5_stats):
    """Marktwert 5.0 × 1.4 = 7.0 > AW 6.0 → premium floors at 0 during the spike."""
    a = Assumptions(anzulegender_wert_ct_kwh=6.0)
    rev_market, rev_premium = annual_revenue(
        [1000.0] * 2, a, flat_50_5, flat_50_5_stats, Shocks(price_level=0.40, price_years=1), 6.0
    )
    assert rev_premium[0] == pytest.approx(0.0, abs=1e-12)
    assert rev_premium[1] == pytest.approx(10_000.0, rel=EXACT)
    assert rev_market[0] == pytest.approx(70_000.0, rel=EXACT)


# ------------------------------- underwrite: effective life & merchant tail


@pytest.fixture(scope="module")
def tail_farm() -> FarmInput:
    return FarmInput(
        farm_id="TAIL-01",
        name="Tail Farm (synthetic test artifact)",
        lat=53.0,
        lon=9.0,
        mw_total=30.0,
        n_units=6,
        commissioning_year=2022,
        bundesland="Niedersachsen",
        p50_cf=0.28,
        cf_uncertainty_sigma=0.09,
    )


def test_effective_life_matrix():
    base = Assumptions(anzulegender_wert_ct_kwh=6.0)  # life 25, support 20, tenor 18
    assert _effective_life(base) == 25  # merchant tail on (default)
    off = base.model_copy(update={"merchant_tail": False})
    assert _effective_life(off) == 20  # truncated to EEG support
    assert _effective_life(off.model_copy(update={"debt_tenor_years": 20})) == 20  # boundary OK
    # life < support (tenor shortened to stay feasible — tenor > life raises by design)
    assert (
        _effective_life(off.model_copy(update={"lifetime_years": 15, "debt_tenor_years": 12})) == 15
    )
    # merchant / ppa modes never truncate on merchant_tail
    assert _effective_life(Assumptions(revenue_mode="merchant", merchant_tail=False)) == 25
    assert (
        _effective_life(
            Assumptions(revenue_mode="ppa", ppa_price_eur_mwh=70.0, merchant_tail=False)
        )
        == 25
    )


def test_effective_life_tenor_beyond_truncated_life_raises():
    a = Assumptions(anzulegender_wert_ct_kwh=6.0, merchant_tail=False, debt_tenor_years=22)
    with pytest.raises(ValueError, match="exceeds effective project life"):
        _effective_life(a)


def test_effective_life_tenor_beyond_lifetime_raises_all_modes():
    with pytest.raises(ValueError, match="exceeds effective project life"):
        _effective_life(Assumptions(revenue_mode="merchant", debt_tenor_years=30))


@pytest.fixture(scope="module")
def uw_tail_on(tail_farm, flat_50_5):
    a = Assumptions(anzulegender_wert_ct_kwh=6.0, merchant_tail=True)
    return underwrite(tail_farm, a, flat_50_5, Shocks())


@pytest.fixture(scope="module")
def uw_tail_off(tail_farm, flat_50_5):
    a = Assumptions(anzulegender_wert_ct_kwh=6.0, merchant_tail=False)
    return underwrite(tail_farm, a, flat_50_5, Shocks())


def test_underwrite_tail_off_truncates_to_support(uw_tail_off):
    assert len(uw_tail_off.annual.year) == 20
    assert all(p > 0 for p in uw_tail_off.annual.revenue_premium)


def test_underwrite_tail_on_premium_stops_merchant_continues(uw_tail_on):
    res = uw_tail_on
    assert len(res.annual.year) == 25
    assert all(p > 0 for p in res.annual.revenue_premium[:20])
    assert res.annual.revenue_premium[20:] == [0.0] * 5
    # tail years earn exactly E_t × wwp (= 50 EUR/MWh flat market)
    for t in range(20, 25):
        assert res.annual.revenue_market[t] == pytest.approx(
            res.annual.energy_mwh[t] * 50.0, rel=EXACT
        )
        assert res.annual.revenue_total[t] == res.annual.revenue_market[t]


def test_underwrite_tenor_beyond_truncated_life_raises(tail_farm, flat_50_5):
    a = Assumptions(anzulegender_wert_ct_kwh=6.0, merchant_tail=False, debt_tenor_years=22)
    with pytest.raises(ValueError, match="exceeds effective project life"):
        underwrite(tail_farm, a, flat_50_5, Shocks())
