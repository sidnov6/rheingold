"""Shared fixtures for engine tests. All synthetic — clearly-labeled test artifacts."""

import pytest
from rheingold_engine.models import Assumptions, FarmInput, MarketInputs


@pytest.fixture
def simple_farm() -> FarmInput:
    return FarmInput(
        farm_id="TEST-SIMPLE",
        name="Simple Test Farm (synthetic)",
        lat=53.0,
        lon=9.0,
        mw_total=30.0,
        n_units=6,
        commissioning_year=2022,
        bundesland="Niedersachsen",
        p50_cf=0.28,
        cf_uncertainty_sigma=0.09,
    )


@pytest.fixture
def base_assumptions() -> Assumptions:
    return Assumptions(anzulegender_wert_ct_kwh=6.0)


@pytest.fixture
def flat_market() -> MarketInputs:
    return MarketInputs.flat(price_eur_mwh=55.0, marktwert_ct_kwh=5.5)
