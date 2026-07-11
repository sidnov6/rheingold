"""Tax module (spec §8.7) — simple, honest.

Straight-line depreciation over depreciation_years (16y standard for wind),
interest deductible, tax_t = max(0, rate × (EBITDA − depr − interest)).
No loss carryforward, no Zinsschranke, no trade-tax split (MODEL_CARD limits).
The interest circularity is resolved by exactly two sculpting passes in
underwrite.py — this module is a pure function of its inputs.
"""

from __future__ import annotations

from .models import Assumptions


def depreciation_schedule(capex: float, a: Assumptions, life: int) -> list[float]:
    years = min(a.depreciation_years, life)
    annual = capex / a.depreciation_years
    return [annual if t <= years else 0.0 for t in range(1, life + 1)]


def annual_tax(
    ebitda: list[float],
    depreciation: list[float],
    interest: list[float],
    a: Assumptions,
) -> list[float]:
    return [
        max(0.0, a.tax_rate * (e - d - i))
        for e, d, i in zip(ebitda, depreciation, interest, strict=True)
    ]


def unlevered_tax(ebitda: list[float], depreciation: list[float], a: Assumptions) -> list[float]:
    """Tax without the interest shield — for the unlevered NPV@WACC (§8.6)."""
    return [max(0.0, a.tax_rate * (e - d)) for e, d in zip(ebitda, depreciation, strict=True)]
