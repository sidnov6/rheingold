"""Tornado anchoring + shape tests (verification findings regression)."""

import pytest
from rheingold_engine import underwrite
from rheingold_engine.models import Assumptions, FarmInput, MarketInputs, Shocks


@pytest.fixture(scope="module")
def farm():
    return FarmInput(
        farm_id="TEST-TORNADO",
        name="Tornado Test Farm (synthetic)",
        lat=53.0,
        lon=9.0,
        mw_total=30.0,
        n_units=6,
        commissioning_year=2022,
        bundesland="Niedersachsen",
        p50_cf=0.30,
        cf_uncertainty_sigma=0.09,
    )


MARKET = MarketInputs.flat(price_eur_mwh=55.0, marktwert_ct_kwh=5.5)
SHOCKS = Shocks(price_level=-0.35, price_years=2, capex_delta=0.15)


def test_tornado_unshocked_with_explicit_aw(farm):
    a = Assumptions(anzulegender_wert_ct_kwh=6.5)
    base = underwrite(farm, a, MARKET, Shocks())
    shocked = underwrite(farm, a, MARKET, SHOCKS)
    assert [t.model_dump() for t in base.tornado] == [t.model_dump() for t in shocked.tornado]


def test_tornado_unshocked_in_breakeven_mode(farm):
    """Break-even AW must not leak scenario shocks into the tornado base."""
    a = Assumptions(anzulegender_wert_ct_kwh=None)
    base = underwrite(farm, a, MARKET, Shocks())
    shocked = underwrite(farm, a, MARKET, SHOCKS)
    # headline bid IS shock-consistent (scenario re-pricing)...
    assert shocked.valuation.breakeven_bid_ct_kwh > base.valuation.breakeven_bid_ct_kwh
    # ...but the tornado stays anchored to the unshocked deal
    assert [t.model_dump() for t in base.tornado] == [t.model_dump() for t in shocked.tornado]


def test_tornado_shape_and_order(farm):
    a = Assumptions(anzulegender_wert_ct_kwh=6.5)
    result = underwrite(farm, a, MARKET, Shocks())
    assert len(result.tornado) == 6
    spans = [
        abs(t.irr_high - t.irr_low)
        for t in result.tornado
        if t.irr_low is not None and t.irr_high is not None
    ]
    assert spans == sorted(spans, reverse=True)
