"""Tornado sensitivities (spec §8 sensitivity.py): one-at-a-time re-runs
measuring equity IRR. Computed off the UNSHOCKED base case (the sliders show
scenarios; the tornado shows the deal's structural sensitivities — documented
in MODEL_CARD). Sorted by IRR span, widest first.
"""

from __future__ import annotations

from collections.abc import Callable

from .models import Assumptions, FarmInput, MarketInputs, Shocks, TornadoItem

# (variable, label, low_label, high_label, low_shocks, high_shocks)
_VARS: list[tuple[str, str, str, str, Shocks, Shocks]] = [
    (
        "price",
        "Power price level",
        "−20 %",
        "+20 %",
        Shocks(price_level=-0.20),
        Shocks(price_level=0.20),
    ),
    (
        "production",
        "Energy production",
        "−10 %",
        "+10 %",
        Shocks(production_delta=-0.10),
        Shocks(production_delta=0.10),
    ),
    (
        "rate",
        "Interest rate",
        "+150 bps",
        "−150 bps",
        Shocks(rate_delta_bps=150.0),
        Shocks(rate_delta_bps=-150.0),
    ),
    (
        "capex",
        "Capex",
        "+15 %",
        "−15 %",
        Shocks(capex_delta=0.15),
        Shocks(capex_delta=-0.15),
    ),
    (
        "availability",
        "Availability",
        "92 %",
        "99 %",
        Shocks(availability_override=0.92),
        Shocks(availability_override=0.99),
    ),
    (
        "curtailment",
        "Curtailment / redispatch",
        "6 %",
        "0 %",
        Shocks(curtailment_override=0.06),
        Shocks(curtailment_override=0.0),
    ),
]

IrrRunner = Callable[[FarmInput, Assumptions, MarketInputs, Shocks], float | None]


def tornado(
    farm: FarmInput,
    a: Assumptions,
    market: MarketInputs,
    irr_of: IrrRunner,
) -> list[TornadoItem]:
    items: list[TornadoItem] = []
    for variable, label, low_label, high_label, low_shocks, high_shocks in _VARS:
        irr_low = irr_of(farm, a, market, low_shocks)
        irr_high = irr_of(farm, a, market, high_shocks)
        items.append(
            TornadoItem(
                variable=variable,
                label=label,
                low_input=low_label,
                high_input=high_label,
                irr_low=irr_low,
                irr_high=irr_high,
            )
        )

    def span(item: TornadoItem) -> float:
        if item.irr_low is None or item.irr_high is None:
            return float("-inf")  # unknown span sorts first — visible, not hidden
        return -abs(item.irr_high - item.irr_low)

    return sorted(items, key=lambda i: (span(i), i.variable))
