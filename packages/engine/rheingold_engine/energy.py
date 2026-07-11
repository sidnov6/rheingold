"""Energy module (spec §8.2). Pure functions: farm + assumptions + shocks → annual MWh.

P50 formula: E_p50 = MW × 8760 × p50_cf × (1−wake) × availability × (1−elec) × (1−curtail).
Uncertainty stack combined in quadrature; inter-annual variability (σ = 0.06) is
EXCLUDED from the long-term P90 and reported separately as a 1-year P90 (§8.2.2).
"""

from __future__ import annotations

import math

from .models import Assumptions, EnergyResult, FarmInput, Shocks, UncertaintyStackRow

HOURS_PER_YEAR = 8760.0
LOSS_SIGMA = 0.03  # loss-uncertainty component, always included
INTERANNUAL_SIGMA = 0.06  # reported separately as 1-yr P90, never in long-term P90
Z_P90 = 1.2816
Z_P75 = 0.6745


def effective_availability(a: Assumptions, shocks: Shocks) -> float:
    return (
        shocks.availability_override if shocks.availability_override is not None else a.availability
    )


def effective_curtailment(a: Assumptions, shocks: Shocks) -> float:
    return (
        shocks.curtailment_override
        if shocks.curtailment_override is not None
        else a.curtailment_redispatch
    )


def p50_energy_mwh(farm: FarmInput, a: Assumptions, shocks: Shocks) -> float:
    return (
        farm.mw_total
        * HOURS_PER_YEAR
        * farm.p50_cf
        * (1.0 - a.wake_losses)
        * effective_availability(a, shocks)
        * (1.0 - a.electrical_losses)
        * effective_curtailment_factor(a, shocks)
    )


def effective_curtailment_factor(a: Assumptions, shocks: Shocks) -> float:
    return 1.0 - effective_curtailment(a, shocks)


def annual_energy_mwh(farm: FarmInput, a: Assumptions, shocks: Shocks, life: int) -> list[float]:
    """Year-by-year net energy, degradation compounding from year 1, production shocks applied."""
    e_p50 = p50_energy_mwh(farm, a, shocks)
    energy = []
    for t in range(1, life + 1):
        e_t = e_p50 * (1.0 - a.degradation_pa) ** (t - 1)
        if shocks.production_delta != 0.0 and (
            shocks.production_years is None or t <= shocks.production_years
        ):
            e_t *= 1.0 + shocks.production_delta
        energy.append(e_t)
    return energy


def energy_result(
    farm: FarmInput, a: Assumptions, shocks: Shocks, annual_mwh: list[float]
) -> EnergyResult:
    sigma_method = farm.cf_uncertainty_sigma
    sigma_total = math.sqrt(sigma_method**2 + LOSS_SIGMA**2)
    sigma_1yr = math.sqrt(sigma_method**2 + LOSS_SIGMA**2 + INTERANNUAL_SIGMA**2)
    p50_gwh = annual_mwh[0] / 1000.0
    denom = farm.mw_total * HOURS_PER_YEAR
    return EnergyResult(
        p50_gwh=p50_gwh,
        p75_gwh=p50_gwh * (1.0 - Z_P75 * sigma_total),
        p90_gwh=p50_gwh * (1.0 - Z_P90 * sigma_total),
        p90_1yr_gwh=p50_gwh * (1.0 - Z_P90 * sigma_1yr),
        net_cf=annual_mwh[0] / denom if denom > 0 else 0.0,
        sigma_total=sigma_total,
        uncertainty_stack=[
            UncertaintyStackRow(
                component="Wind data / method",
                sigma=sigma_method,
                included_in_p90=True,
                note="Path A (ninja) ≈ 0.06, Path B (GWA + power curve) ≈ 0.09",
            ),
            UncertaintyStackRow(
                component="Loss uncertainties",
                sigma=LOSS_SIGMA,
                included_in_p90=True,
                note="availability / electrical / curtailment estimation error",
            ),
            UncertaintyStackRow(
                component="Inter-annual variability",
                sigma=INTERANNUAL_SIGMA,
                included_in_p90=False,
                note="excluded from long-term P90; reported as 1-yr P90",
            ),
        ],
    )
