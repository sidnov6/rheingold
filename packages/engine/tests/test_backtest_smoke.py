"""Backtest smoke test (§12 deliverable): 2 rounds on a synthetic mini-fleet.

The farm rows here are SYNTHETIC TEST ARTIFACTS derived from the GOLDEN-01
archetype (the repo's single sanctioned synthetic fixture family) — CI has no
mart, so this exercises the backtest mechanics, not real registry data.
"""

import pandas as pd
import pytest
from rheingold_engine.backtest import (
    build_market_inputs,
    neg_rule_hours_for_round,
    run_backtest,
    wind_class,
)
from rheingold_engine.models import MarketInputs


def _synthetic_fleet() -> pd.DataFrame:
    rows = []
    lands = ["Schleswig-Holstein", "Brandenburg", "Bayern", "Niedersachsen"]
    cfs = [0.34, 0.28, 0.22, 0.31]
    for year in (2017, 2018, 2019, 2020):
        for i, (bl, cf) in enumerate(zip(lands, cfs, strict=True)):
            rows.append(
                {
                    "farm_id": f"syn-{year}-{i}",
                    "name": f"Synthetic {bl} {year} (test artifact)",
                    "lat": 52.0 + i * 0.5,
                    "lon": 9.0 + i * 0.8,
                    "mw_total": 21.0 + 3 * i,
                    "n_units": 5 + i,
                    "turbine_type": None,
                    "hub_height_m": 120.0,
                    "rotor_d_m": 120.0,
                    "commissioning_year": year,
                    "bundesland": bl,
                    "p50_cf": cf,
                }
            )
    return pd.DataFrame(rows)


@pytest.fixture(scope="module")
def result():
    auctions = pd.DataFrame(
        [
            # real BNetzA values (2017-05-01 and 2018-05-01 rounds) — assertion
            # targets only; the model side runs on the synthetic fleet above
            {"round_date": "2017-05-01", "avg_award_ct_kwh": 5.71, "max_price_ct_kwh": 7.0},
            {"round_date": "2018-05-01", "avg_award_ct_kwh": 5.73, "max_price_ct_kwh": 6.3},
        ]
    )
    vintages = pd.DataFrame(
        [
            {
                "vintage_year": 2017,
                "capex_eur_per_mw": 1_560_000,
                "opex_fixed_eur_per_mw_yr": 57_500,
                "interest_rate": 0.021,
            },
            {
                "vintage_year": 2018,
                "capex_eur_per_mw": 1_553_000,
                "opex_fixed_eur_per_mw_yr": 57_500,
                "interest_rate": 0.021,
            },
        ]
    )
    market = MarketInputs.flat(price_eur_mwh=45.0, marktwert_ct_kwh=4.0)
    return run_backtest(_synthetic_fleet(), auctions, vintages, market, n_per_round=8)


def test_two_rounds_produced(result):
    assert len(result["rounds"]) == 2
    for r in result["rounds"]:
        assert r["n_farms"] >= 5
        assert (
            2.0
            <= r["model_p25_ct_kwh"]
            <= r["model_median_ct_kwh"]
            <= r["model_p75_ct_kwh"]
            <= 12.0
        )


def test_mae_and_shape(result):
    assert result["mae_ct_kwh"] == result["mae_ct_kwh"]  # not NaN
    assert "method_note" in result and "seed" in result["method_note"]


def test_determinism():
    a = run_backtest(
        _synthetic_fleet(),
        pd.DataFrame(
            [{"round_date": "2017-05-01", "avg_award_ct_kwh": 5.71, "max_price_ct_kwh": 7.0}]
        ),
        pd.DataFrame(
            [
                {
                    "vintage_year": 2017,
                    "capex_eur_per_mw": 1_560_000,
                    "opex_fixed_eur_per_mw_yr": 57_500,
                    "interest_rate": 0.021,
                }
            ]
        ),
        MarketInputs.flat(45.0, 4.0),
        n_per_round=8,
    )
    b = run_backtest(
        _synthetic_fleet(),
        pd.DataFrame(
            [{"round_date": "2017-05-01", "avg_award_ct_kwh": 5.71, "max_price_ct_kwh": 7.0}]
        ),
        pd.DataFrame(
            [
                {
                    "vintage_year": 2017,
                    "capex_eur_per_mw": 1_560_000,
                    "opex_fixed_eur_per_mw_yr": 57_500,
                    "interest_rate": 0.021,
                }
            ]
        ),
        MarketInputs.flat(45.0, 4.0),
        n_per_round=8,
    )
    assert a["rounds"] == b["rounds"]


def test_cohort_mapping():
    assert neg_rule_hours_for_round("2017-05-01") == 6
    assert neg_rule_hours_for_round("2021-02-01") == 4
    assert neg_rule_hours_for_round("2023-02-01") == 1
    assert neg_rule_hours_for_round("2025-02-01") == 1
    assert neg_rule_hours_for_round("2025-05-01") == 0
    assert neg_rule_hours_for_round("2026-05-01") == 0


def test_wind_class():
    assert wind_class("Schleswig-Holstein") == "north"
    assert wind_class("Bayern") == "south"
    assert wind_class("Brandenburg") == "center"
    assert wind_class(None) == "center"


def test_build_market_inputs_requires_mart(tmp_path):
    with pytest.raises(FileNotFoundError):
        build_market_inputs(tmp_path)
