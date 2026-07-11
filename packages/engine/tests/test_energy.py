"""Energy module unit tests (spec §8.2). All inputs synthetic, clearly-labeled test artifacts.

Hand derivations (independent of energy.py, recomputed from the spec formulas):

E_p50 = MW × 8760 × p50_cf × (1−wake) × availability × (1−elec) × (1−curtail)
For the conftest simple_farm (30 MW, cf 0.28, σ_method 0.09) at default assumptions
(wake 0.06, avail 0.97, elec 0.02, curtail 0.02):
    E_p50 = 30 × 8760 × 0.28 × 0.94 × 0.97 × 0.98 × 0.98 = 64_437.639775 MWh

Degradation: E_t = E_p50 × (1−d)^(t−1) — year 1 exponent is 0, i.e. NO degradation
in year 1 (§8.2).

Uncertainty stack (§8.2.2), σ's combined in quadrature:
    σ_total = sqrt(σ_method² + 0.03²)              (loss σ always included)
    σ_1yr   = sqrt(σ_method² + 0.03² + 0.06²)      (inter-annual 0.06 ONLY here)
    P90 = P50 × (1 − 1.2816 σ_total); P75 = P50 × (1 − 0.6745 σ_total)
    P90_1yr = P50 × (1 − 1.2816 σ_1yr)
Inter-annual variability is excluded from the long-term P90 and reported
separately as the 1-yr P90.
"""

import math

import pytest
from rheingold_engine import energy
from rheingold_engine.models import Assumptions, Shocks

EXACT = 1e-9  # hand-recomputed closed forms (tolerates multiply-order float noise)

# simple_farm at default losses — the spec §8.2 product, written out term by term
E_P50 = 30.0 * 8760 * 0.28 * (1 - 0.06) * 0.97 * (1 - 0.02) * (1 - 0.02)


def test_p50_formula_exact(simple_farm, base_assumptions):
    got = energy.p50_energy_mwh(simple_farm, base_assumptions, Shocks())
    assert got == pytest.approx(E_P50, rel=EXACT)


def test_p50_scales_linearly_in_each_factor(simple_farm, base_assumptions):
    base = energy.p50_energy_mwh(simple_farm, base_assumptions, Shocks())
    double_mw = simple_farm.model_copy(update={"mw_total": 60.0})
    assert energy.p50_energy_mwh(double_mw, base_assumptions, Shocks()) == pytest.approx(
        2 * base, rel=EXACT
    )
    no_wake = base_assumptions.model_copy(update={"wake_losses": 0.0})
    assert energy.p50_energy_mwh(simple_farm, no_wake, Shocks()) == pytest.approx(
        base / (1 - 0.06), rel=EXACT
    )


# ---------------------------------------------------------------- degradation


def test_degradation_year1_is_undegraded(simple_farm, base_assumptions):
    """Year 1 uses exponent (t−1) = 0: first-year energy equals E_p50 exactly."""
    a = base_assumptions.model_copy(update={"degradation_pa": 0.004})
    years = energy.annual_energy_mwh(simple_farm, a, Shocks(), 5)
    assert years[0] == pytest.approx(E_P50, rel=EXACT)


def test_degradation_exponent_compounds_from_year_2(simple_farm, base_assumptions):
    d = 0.004
    a = base_assumptions.model_copy(update={"degradation_pa": d})
    years = energy.annual_energy_mwh(simple_farm, a, Shocks(), 6)
    for t, e_t in enumerate(years, start=1):
        assert e_t == pytest.approx(E_P50 * (1 - d) ** (t - 1), rel=EXACT)
    # consecutive ratio is exactly (1−d)
    for prev, nxt in zip(years, years[1:], strict=False):
        assert nxt / prev == pytest.approx(1 - d, rel=EXACT)


def test_zero_degradation_flat_series(simple_farm, base_assumptions):
    a = base_assumptions.model_copy(update={"degradation_pa": 0.0})
    years = energy.annual_energy_mwh(simple_farm, a, Shocks(), 10)
    assert all(e == pytest.approx(E_P50, rel=EXACT) for e in years)


# ---------------------------------------------------- production shock window


def test_production_shock_first_n_years_only(simple_farm, base_assumptions):
    a = base_assumptions.model_copy(update={"degradation_pa": 0.0})
    shocks = Shocks(production_delta=-0.12, production_years=3)
    years = energy.annual_energy_mwh(simple_farm, a, shocks, 6)
    for t in (1, 2, 3):
        assert years[t - 1] == pytest.approx(E_P50 * 0.88, rel=EXACT)
    for t in (4, 5, 6):
        assert years[t - 1] == pytest.approx(E_P50, rel=EXACT)


def test_production_shock_none_years_means_whole_life(simple_farm, base_assumptions):
    a = base_assumptions.model_copy(update={"degradation_pa": 0.0})
    years = energy.annual_energy_mwh(
        simple_farm, a, Shocks(production_delta=0.15, production_years=None), 8
    )
    assert all(e == pytest.approx(E_P50 * 1.15, rel=EXACT) for e in years)


def test_production_shock_zero_years_is_no_shock(simple_farm, base_assumptions):
    a = base_assumptions.model_copy(update={"degradation_pa": 0.0})
    years = energy.annual_energy_mwh(
        simple_farm, a, Shocks(production_delta=-0.12, production_years=0), 4
    )
    assert all(e == pytest.approx(E_P50, rel=EXACT) for e in years)


def test_production_shock_stacks_on_degradation(simple_farm, base_assumptions):
    d = 0.002
    a = base_assumptions.model_copy(update={"degradation_pa": d})
    years = energy.annual_energy_mwh(
        simple_farm, a, Shocks(production_delta=-0.12, production_years=2), 3
    )
    assert years[0] == pytest.approx(E_P50 * 0.88, rel=EXACT)
    assert years[1] == pytest.approx(E_P50 * (1 - d) * 0.88, rel=EXACT)
    assert years[2] == pytest.approx(E_P50 * (1 - d) ** 2, rel=EXACT)  # window over


# ------------------------------------------- availability/curtailment overrides


def test_availability_override_replaces_base(simple_farm, base_assumptions):
    shocked = energy.p50_energy_mwh(
        simple_farm, base_assumptions, Shocks(availability_override=0.90)
    )
    assert shocked == pytest.approx(E_P50 * 0.90 / 0.97, rel=EXACT)


def test_curtailment_override_replaces_base(simple_farm, base_assumptions):
    shocked = energy.p50_energy_mwh(
        simple_farm, base_assumptions, Shocks(curtailment_override=0.06)
    )
    assert shocked == pytest.approx(E_P50 * (1 - 0.06) / (1 - 0.02), rel=EXACT)


def test_none_overrides_keep_assumption_values(simple_farm, base_assumptions):
    shocks = Shocks(availability_override=None, curtailment_override=None)
    assert energy.p50_energy_mwh(simple_farm, base_assumptions, shocks) == pytest.approx(
        E_P50, rel=EXACT
    )


def test_both_overrides_combine(simple_farm, base_assumptions):
    shocks = Shocks(availability_override=0.95, curtailment_override=0.10)
    want = E_P50 * (0.95 / 0.97) * ((1 - 0.10) / (1 - 0.02))
    assert energy.p50_energy_mwh(simple_farm, base_assumptions, shocks) == pytest.approx(
        want, rel=EXACT
    )


# ------------------------------------------------------- uncertainty stack/P90


def test_sigma_quadrature(simple_farm, base_assumptions):
    """σ_total = sqrt(method² + loss²); simple_farm has σ_method = 0.09 (Path B)."""
    mwh = energy.annual_energy_mwh(simple_farm, base_assumptions, Shocks(), 20)
    result = energy.energy_result(simple_farm, base_assumptions, Shocks(), mwh)
    assert result.sigma_total == pytest.approx(math.sqrt(0.09**2 + 0.03**2), rel=EXACT)


def test_p90_p75_z_scores(simple_farm, base_assumptions):
    mwh = energy.annual_energy_mwh(simple_farm, base_assumptions, Shocks(), 20)
    result = energy.energy_result(simple_farm, base_assumptions, Shocks(), mwh)
    sigma = math.sqrt(0.09**2 + 0.03**2)
    assert result.p50_gwh == pytest.approx(mwh[0] / 1000.0, rel=EXACT)
    assert result.p90_gwh == pytest.approx(result.p50_gwh * (1 - 1.2816 * sigma), rel=EXACT)
    assert result.p75_gwh == pytest.approx(result.p50_gwh * (1 - 0.6745 * sigma), rel=EXACT)


def test_p90_1yr_adds_interannual_sigma_006(simple_farm, base_assumptions):
    """The 1-yr P90 (and ONLY it) includes the 0.06 inter-annual σ in quadrature."""
    mwh = energy.annual_energy_mwh(simple_farm, base_assumptions, Shocks(), 20)
    result = energy.energy_result(simple_farm, base_assumptions, Shocks(), mwh)
    sigma_1yr = math.sqrt(0.09**2 + 0.03**2 + 0.06**2)
    assert result.p90_1yr_gwh == pytest.approx(result.p50_gwh * (1 - 1.2816 * sigma_1yr), rel=EXACT)
    assert result.p90_1yr_gwh < result.p90_gwh < result.p75_gwh < result.p50_gwh


def test_uncertainty_stack_rows_and_flags(simple_farm, base_assumptions):
    mwh = energy.annual_energy_mwh(simple_farm, base_assumptions, Shocks(), 20)
    result = energy.energy_result(simple_farm, base_assumptions, Shocks(), mwh)
    rows = {r.component: r for r in result.uncertainty_stack}
    assert len(result.uncertainty_stack) == 3
    method = rows["Wind data / method"]
    loss = rows["Loss uncertainties"]
    inter = rows["Inter-annual variability"]
    assert method.sigma == pytest.approx(0.09) and method.included_in_p90
    assert loss.sigma == pytest.approx(0.03) and loss.included_in_p90
    assert inter.sigma == pytest.approx(0.06) and not inter.included_in_p90


def test_net_cf_is_year1_over_nameplate(simple_farm, base_assumptions):
    mwh = energy.annual_energy_mwh(simple_farm, base_assumptions, Shocks(), 20)
    result = energy.energy_result(simple_farm, base_assumptions, Shocks(), mwh)
    assert result.net_cf == pytest.approx(mwh[0] / (30.0 * 8760), rel=EXACT)


def test_method_sigma_variants_path_a_vs_b(simple_farm, base_assumptions):
    """Path A (σ 0.06) vs Path B (σ 0.09): P90 must be higher under Path A."""
    results = {}
    for sigma_m in (0.06, 0.09):
        farm = simple_farm.model_copy(update={"cf_uncertainty_sigma": sigma_m})
        mwh = energy.annual_energy_mwh(farm, base_assumptions, Shocks(), 20)
        r = energy.energy_result(farm, base_assumptions, Shocks(), mwh)
        assert r.sigma_total == pytest.approx(math.sqrt(sigma_m**2 + 0.03**2), rel=EXACT)
        results[sigma_m] = r
    assert results[0.06].p90_gwh > results[0.09].p90_gwh
    assert results[0.06].p50_gwh == pytest.approx(results[0.09].p50_gwh, rel=EXACT)


def test_energy_result_p50_reflects_shocked_year1(simple_farm):
    """P50/P90 quote the year-1 series value: production shocks flow through."""
    a = Assumptions(anzulegender_wert_ct_kwh=6.0, degradation_pa=0.0)
    shocks = Shocks(production_delta=-0.12, production_years=3)
    mwh = energy.annual_energy_mwh(simple_farm, a, shocks, 20)
    result = energy.energy_result(simple_farm, a, shocks, mwh)
    assert result.p50_gwh == pytest.approx(E_P50 * 0.88 / 1000.0, rel=EXACT)
