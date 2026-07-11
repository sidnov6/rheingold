"""Valuation module (spec §8.6): LCOE, NPV@WACC, equity IRR, payback.

LCOE is nominal (stated on the methodology page): discounted opex + capex over
discounted energy at WACC. NPV@WACC is on unlevered after-tax FCF (no interest
shield). Equity IRR on [−(capex + DSRA − D), (CFADS_t − DS_t)…] with the DSRA
released at debt maturity.
"""

from __future__ import annotations

import math

import numpy_financial as npf


def lcoe_eur_mwh(
    capex: float, opex_total: list[float], energy_mwh: list[float], wacc: float
) -> float:
    disc_opex = sum(o / (1.0 + wacc) ** (t + 1) for t, o in enumerate(opex_total))
    disc_energy = sum(e / (1.0 + wacc) ** (t + 1) for t, e in enumerate(energy_mwh))
    if disc_energy <= 0:
        raise ValueError("discounted energy is zero — cannot compute LCOE")
    return (capex + disc_opex) / disc_energy


def npv_unlevered(capex: float, ebitda: list[float], tax_unlev: list[float], wacc: float) -> float:
    return -capex + sum(
        (e - x) / (1.0 + wacc) ** (t + 1)
        for t, (e, x) in enumerate(zip(ebitda, tax_unlev, strict=True))
    )


def equity_cash_flows(
    cfads: list[float],
    debt_service: list[float],
    tenor: int,
    dsra: float,
) -> list[float]:
    """Equity CF for years 1..life (t0 outflow handled separately)."""
    eq = []
    for t, (c, ds) in enumerate(zip(cfads, debt_service, strict=True), start=1):
        cf = c - ds
        if t == tenor:
            cf += dsra  # DSRA released at maturity
        eq.append(cf)
    return eq


def equity_irr(equity_t0: float, equity_cf: list[float]) -> float | None:
    """IRR of [−equity_t0, equity_cf...]; None when undefined."""
    if equity_t0 <= 0:
        return None  # debt covers more than uses — IRR undefined in this convention
    irr = npf.irr([-equity_t0, *equity_cf])
    if irr is None or (isinstance(irr, float) and math.isnan(irr)):
        return None
    return float(irr)


def payback_year(equity_t0: float, equity_cf: list[float]) -> int | None:
    cum = -equity_t0
    for t, cf in enumerate(equity_cf, start=1):
        cum += cf
        if cum >= 0:
            return t
    return None
