"""Cost module (spec §8.4).

Opex_t = opex_fixed × MW × (1+infl)^(t−1) + opex_var × E_t + land_lease% × Rev_t
       + municipal 0.2 ct/kWh × E_t (when enabled; ct/kWh → EUR/MWh is ×10).
Insurance/management are folded into the fixed rate. Year 1 runs at today's
price level ((1+infl)^0).
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import CT_KWH_TO_EUR_MWH, Assumptions


@dataclass(frozen=True)
class CostLines:
    opex_fixed: list[float]
    opex_variable: list[float]
    land_lease: list[float]
    municipal_participation: list[float]
    opex_total: list[float]


def annual_costs(
    annual_mwh: list[float],
    revenue_total: list[float],
    mw_total: float,
    a: Assumptions,
) -> CostLines:
    fixed, variable, lease, municipal, total = [], [], [], [], []
    municipal_eur_mwh = (
        a.municipal_participation_ct_kwh * CT_KWH_TO_EUR_MWH
        if a.municipal_participation_enabled
        else 0.0
    )
    for idx, (e_t, rev_t) in enumerate(zip(annual_mwh, revenue_total, strict=True)):
        f = a.opex_fixed_eur_per_mw_yr * mw_total * (1.0 + a.inflation_pa) ** idx
        v = a.opex_variable_eur_per_mwh * e_t
        le = a.land_lease_pct_revenue * rev_t
        mu = municipal_eur_mwh * e_t
        fixed.append(f)
        variable.append(v)
        lease.append(le)
        municipal.append(mu)
        total.append(f + v + le + mu)
    return CostLines(fixed, variable, lease, municipal, total)
