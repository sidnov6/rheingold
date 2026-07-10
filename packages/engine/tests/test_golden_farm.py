"""Golden-farm end-to-end regression test (spec §13.2).

GOLDEN-01 is a SYNTHETIC TEST ARTIFACT — the only fabricated data in the repo.
Every expected value below is hand-derived from the §8 formulas before the engine
existed. Any engine change that moves these numbers is a regression by definition.

Hand derivation
---------------
Farm: 10 units × 4.2 MW = 42 MW; p50_cf 0.30; availability 0.97; wake 0.06;
elec 0.02; curtail 0.02; degradation 0; 20y life.
Market: AW = 6.0 ct/kWh flat, Marktwert = 5.0 ct/kWh flat → premium
max(0, 6−5) = 1.0 ct/kWh = 10 EUR/MWh; merchant leg 50 EUR/MWh flat, no
negative hours, capture rate 1.0. eeg_support_years = 20 → support spans life.
Costs: capex 1.5 M€/MW → 63.0 M€; opex fixed 45 k€/MW·yr → 1.89 M€/yr;
no variable opex / lease / municipal / tax / inflation.
Debt: DSCR target 1.30, tenor 15, rate 5%, gearing cap 0.75, DSRA 6 months.

E_p50  = 42 × 8760 × 0.30 × 0.94 × 0.97 × 0.98 × 0.98
       = 96_655.45966272 MWh                                   (§8.2, exact)
Rev    = E_p50 × (50 + 10) = E_p50 × 60 EUR/MWh (flat all years)
Opex   = 1_890_000 EUR/yr flat
EBITDA = CFADS (tax = 0) = E_p50×60 − 1_890_000 = 3_909_327.579763 EUR/yr flat
DS_t   = CFADS / 1.30 (flat → annuity), t = 1..15
AF     = (1 − 1.05^−15) / 0.05 = 10.379658203...
D0     = (CFADS/1.3) × AF ≈ 31_213_262.5 EUR   (computed exactly in test)
Cap    = 0.75 × 63 M€ = 47.25 M€ > D0 → gearing cap NOT binding
gearing= D0 / 63 M€ ≈ 0.4954
DSCR_t = 1.30 exactly for all t in 1..15; B_15 = 0
DSRA   = 6/12 × avg(DS) = CFADS/1.3/2
LCOE   = (63 M€ + 1.89 M€ × AF(5.8%, 20)) / (E_p50 × AF(5.8%, 20))  (§8.6, nominal)
Equity CF: t0 = −(63 M€ + DSRA − D0); t1..14 = CFADS − DS; t15 = CFADS − DS + DSRA;
t16..20 = CFADS.  IRR cross-checked against numpy_financial.irr.
P90: sigma_total = sqrt(0.10² + 0.03²) (method σ from farm input + loss σ 0.03;
inter-annual 0.06 excluded from long-term P90 per §8.2.2)
     → P90 = P50 × (1 − 1.2816 × sigma_total), P75 = P50 × (1 − 0.6745 × σ).
"""

import math

import numpy_financial as npf
import pytest

from rheingold_engine import underwrite
from rheingold_engine.models import Assumptions, FarmInput, MarketInputs, Shocks

EXACT = 1e-6  # relative tolerance where closed-form
ITER = 1e-4  # relative tolerance where iterative

E_P50_MWH = 42 * 8760 * 0.30 * 0.94 * 0.97 * 0.98 * 0.98  # = 96_655.45966272
REVENUE = E_P50_MWH * 60.0
OPEX = 1_890_000.0
CFADS = REVENUE - OPEX
DS = CFADS / 1.30
AF_5_15 = (1 - 1.05**-15) / 0.05
D0 = DS * AF_5_15
CAPEX = 63_000_000.0
DSRA = 0.5 * DS
AF_58_20 = (1 - 1.058**-20) / 0.058
LCOE = (CAPEX + 1_890_000.0 * AF_58_20) / (E_P50_MWH * AF_58_20)
EQUITY_T0 = CAPEX + DSRA - D0
SIGMA_TOTAL = math.sqrt(0.10**2 + 0.03**2)


@pytest.fixture(scope="module")
def golden():
    farm = FarmInput(
        farm_id="GOLDEN-01",
        name="Golden Farm (synthetic test artifact)",
        lat=52.5,
        lon=13.0,
        mw_total=42.0,
        n_units=10,
        turbine_type="GENERIC-4200",
        hub_height_m=120.0,
        rotor_d_m=130.0,
        commissioning_year=2024,
        bundesland="Brandenburg",
        p50_cf=0.30,
        cf_uncertainty_sigma=0.10,
    )
    assumptions = Assumptions(
        lifetime_years=20,
        availability=0.97,
        electrical_losses=0.02,
        wake_losses=0.06,
        curtailment_redispatch=0.02,
        degradation_pa=0.0,
        capex_eur_per_mw=1_500_000.0,
        opex_fixed_eur_per_mw_yr=45_000.0,
        opex_variable_eur_per_mwh=0.0,
        land_lease_pct_revenue=0.0,
        municipal_participation_enabled=False,
        inflation_pa=0.0,
        revenue_mode="eeg_premium",
        anzulegender_wert_ct_kwh=6.0,
        eeg_support_years=20,
        neg_price_rule_hours=4,
        merchant_tail=True,
        target_dscr=1.30,
        max_gearing=0.75,
        debt_tenor_years=15,
        interest_rate=0.05,
        dsra_months=6,
        wacc=0.058,
        equity_target_irr=0.08,
        tax_rate=0.0,
        depreciation_years=16,
    )
    market = MarketInputs.flat(price_eur_mwh=50.0, marktwert_ct_kwh=5.0)
    return underwrite(farm, assumptions, market, Shocks())


def test_p50_energy(golden):
    assert golden.energy.p50_gwh * 1000 == pytest.approx(E_P50_MWH, rel=EXACT)
    # degradation 0 → every year identical
    for e in golden.annual.energy_mwh:
        assert e == pytest.approx(E_P50_MWH, rel=EXACT)


def test_net_cf(golden):
    assert golden.energy.net_cf == pytest.approx(E_P50_MWH / (42 * 8760), rel=EXACT)


def test_p90_p75(golden):
    assert golden.energy.sigma_total == pytest.approx(SIGMA_TOTAL, rel=EXACT)
    assert golden.energy.p90_gwh == pytest.approx(
        golden.energy.p50_gwh * (1 - 1.2816 * SIGMA_TOTAL), rel=EXACT
    )
    assert golden.energy.p75_gwh == pytest.approx(
        golden.energy.p50_gwh * (1 - 0.6745 * SIGMA_TOTAL), rel=EXACT
    )
    assert golden.energy.p90_gwh < golden.energy.p75_gwh < golden.energy.p50_gwh


def test_revenue_60_eur_per_mwh(golden):
    for rev, e in zip(golden.annual.revenue_total, golden.annual.energy_mwh, strict=True):
        assert rev / e == pytest.approx(60.0, rel=EXACT)
    # premium leg = 10 EUR/MWh exactly
    for prem, e in zip(golden.annual.revenue_premium, golden.annual.energy_mwh, strict=True):
        assert prem / e == pytest.approx(10.0, rel=EXACT)


def test_cfads_constant(golden):
    for c in golden.annual.cfads:
        assert c == pytest.approx(CFADS, rel=EXACT)


def test_debt_capacity_annuity(golden):
    assert golden.debt.debt_capacity_eur == pytest.approx(D0, rel=EXACT)
    assert golden.debt.debt_drawn_eur == pytest.approx(D0, rel=EXACT)


def test_gearing_cap_not_binding(golden):
    # D0 ≈ 31.21 M€ < 47.25 M€ cap — computed, not assumed
    assert D0 < 0.75 * CAPEX
    assert golden.debt.gearing_cap_binding is False
    assert golden.debt.gearing == pytest.approx(D0 / CAPEX, rel=EXACT)


def test_dscr_flat_at_target(golden):
    tenor = 15
    for t, dscr in enumerate(golden.annual.dscr):
        if t < tenor:
            assert dscr == pytest.approx(1.30, rel=EXACT)
        else:
            assert dscr is None
    assert golden.debt.min_dscr == pytest.approx(1.30, rel=EXACT)
    assert golden.debt.avg_dscr == pytest.approx(1.30, rel=EXACT)


def test_debt_fully_amortized(golden):
    tenor = 15
    balance_after = (
        golden.annual.debt_balance_bop[tenor - 1]
        - golden.annual.principal[tenor - 1]
    )
    assert balance_after == pytest.approx(0.0, abs=1.0)  # EUR-level zero
    for p in golden.annual.principal[:tenor]:
        assert p >= -1e-9


def test_dsra(golden):
    assert golden.debt.dsra_eur == pytest.approx(DSRA, rel=EXACT)


def test_llcr_equals_target_when_flat(golden):
    # flat CFADS, sculpted at 1.30, discounted at the loan rate → LLCR_1 = 1.30 + DSRA/B0
    expected = (CFADS * AF_5_15 + DSRA) / D0
    assert golden.debt.llcr == pytest.approx(expected, rel=EXACT)


def test_lcoe(golden):
    assert golden.valuation.lcoe_eur_mwh == pytest.approx(LCOE, rel=EXACT)


def test_equity_cash_flows_and_irr(golden):
    eq = golden.annual.equity_cf
    for t in range(14):
        assert eq[t] == pytest.approx(CFADS - DS, rel=EXACT)
    assert eq[14] == pytest.approx(CFADS - DS + DSRA, rel=EXACT)
    for t in range(15, 20):
        assert eq[t] == pytest.approx(CFADS, rel=EXACT)
    assert golden.valuation.equity_invested_eur == pytest.approx(EQUITY_T0, rel=EXACT)
    irr_check = npf.irr([-EQUITY_T0, *eq])
    assert golden.valuation.equity_irr == pytest.approx(irr_check, abs=1e-6)


def test_capture_rate_flat_market(golden):
    assert golden.valuation.capture_rate == pytest.approx(1.0, rel=EXACT)


def test_breakeven_bid_recovers_target_irr(golden):
    """Re-running with AW = breakeven bid must hit equity_target_irr (iterative)."""
    aw = golden.valuation.breakeven_bid_ct_kwh
    assert aw is not None and 2.0 <= aw <= 12.0
    res = underwrite(
        golden.farm,
        golden.assumptions.model_copy(update={"anzulegender_wert_ct_kwh": aw}),
        MarketInputs.flat(price_eur_mwh=50.0, marktwert_ct_kwh=5.0),
        Shocks(),
    )
    assert res.valuation.equity_irr == pytest.approx(0.08, abs=1e-4)


def test_evidence_store_nonempty_and_consistent(golden):
    ids = [e.id for e in golden.evidence]
    assert len(ids) == len(set(ids)), "duplicate evidence ids"
    by_id = {e.id: e for e in golden.evidence}
    # every computed item's inputs must reference existing ids
    for e in golden.evidence:
        for ref in e.inputs:
            assert ref in by_id, f"{e.id} references unknown evidence {ref}"
    # key scalars must be present in the store
    values = {e.id: e.value for e in golden.evidence if isinstance(e.value, float)}
    assert any(abs(v - golden.valuation.lcoe_eur_mwh) < 1e-9 for v in values.values())
    assert any(abs(v - golden.debt.min_dscr) < 1e-9 for v in values.values())
