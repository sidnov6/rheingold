"""Scenario presets (spec §8.8). The six chips above the sliders.

The client may send any Shocks vector; these are the named presets. The
"2020 Price Crash" capture erosion (−5pp) is folded into the price level for
the affected years (documented simplification: a deeper effective price cut
approximating capture-rate deterioration).
"""

from __future__ import annotations

from .models import Shocks

PRESETS: dict[str, Shocks] = {
    "low_wind_2021": Shocks(production_delta=-0.12, production_years=3),
    "price_crash_2020": Shocks(price_level=-0.35, price_years=2),
    "negative_hour_surge": Shocks(negative_hours_multiplier=3.0),
    "rate_shock": Shocks(rate_delta_bps=200.0, wacc_delta_bps=100.0),
    "capex_overrun": Shocks(capex_delta=0.15),
    "redispatch_tightening": Shocks(curtailment_override=0.06),
}


def apply_rate_shocks(interest_rate: float, wacc: float, shocks: Shocks) -> tuple[float, float]:
    return (
        interest_rate + shocks.rate_delta_bps / 10_000.0,
        wacc + shocks.wacc_delta_bps / 10_000.0,
    )


def apply_capex_shock(capex: float, shocks: Shocks) -> float:
    return capex * (1.0 + shocks.capex_delta)
