"""Deterministic compliance gate (spec §9.4). Pure code — NO LLM, no clock.

Rules:
    min_dscr        >= 1.15
    avg_dscr        >= 1.25
    llcr            >= 1.30
    gearing         <= max_gearing
    equity_irr      >= hurdle - 150 bps
    p90_min_dscr    >= 1.00
    prices_fresh    latest day-ahead price within 45 days of `as_of`
    marktwerte_fresh latest Marktwert month within 2 calendar months of `as_of`

The freshness inputs are passed as explicit datetimes — the engine and this gate
have no clock of their own. If a freshness input is omitted, that gate is not
emitted (unknown vintage is handled upstream, not silently passed here).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from typing import Any

from .schemas import GateFlag

MIN_DSCR_FLOOR = 1.15
AVG_DSCR_FLOOR = 1.25
LLCR_FLOOR = 1.30
IRR_HURDLE_BUFFER = 0.015  # 150 bps below hurdle
P90_MIN_DSCR_FLOOR = 1.00
PRICE_FRESHNESS_DAYS = 45
MARKTWERT_FRESHNESS_MONTHS = 2

#: Gates whose failure is dealbreaker-severity: the narrator cannot output PROCEED
#: if any of these failed. Enforced in code by the validator (§9.6), not by prompt.
DEALBREAKER_GATES: frozenset[str] = frozenset({"min_dscr", "p90_min_dscr", "gearing"})

_SCALAR_KEYS = (
    "min_dscr",
    "avg_dscr",
    "llcr",
    "gearing",
    "max_gearing",
    "equity_irr",
    "equity_target_irr",
    "p90_min_dscr",
)


def _extract_scalars(result: Any) -> dict[str, float | None]:
    """Accept a plain mapping of scalars or an UnderwriteResult-shaped object."""
    if isinstance(result, Mapping):
        missing = [k for k in _SCALAR_KEYS if k not in result]
        if missing:
            raise KeyError(f"compliance gate scalars missing keys: {missing}")
        return {k: result[k] for k in _SCALAR_KEYS}
    # Duck-typed UnderwriteResult: .debt, .valuation, .assumptions
    return {
        "min_dscr": result.debt.min_dscr,
        "avg_dscr": result.debt.avg_dscr,
        "llcr": result.debt.llcr,
        "gearing": result.debt.gearing,
        "max_gearing": result.assumptions.max_gearing,
        "equity_irr": result.valuation.equity_irr,
        "equity_target_irr": result.assumptions.equity_target_irr,
        "p90_min_dscr": result.valuation.p90_min_dscr,
    }


def _as_date(d: datetime | date) -> date:
    return d.date() if isinstance(d, datetime) else d


def _months_between(later: date, earlier: date) -> int:
    return (later.year - earlier.year) * 12 + (later.month - earlier.month)


def run(
    result: Mapping[str, float | None] | Any,
    *,
    as_of: datetime | date | None = None,
    latest_price_date: datetime | date | None = None,
    latest_marktwert_month: datetime | date | None = None,
) -> list[GateFlag]:
    """Run all deterministic gate rules against underwrite scalars.

    `result` is either an UnderwriteResult or a mapping with keys
    min_dscr, avg_dscr, llcr, gearing, max_gearing, equity_irr,
    equity_target_irr, p90_min_dscr.

    Freshness gates are emitted only when the corresponding datetime input is
    provided (both require `as_of`).
    """
    s = _extract_scalars(result)
    flags: list[GateFlag] = []

    def ge(rule_id: str, value: float | None, threshold: float) -> None:
        passed = value is not None and value >= threshold
        flags.append(GateFlag(rule_id=rule_id, passed=passed, value=value, threshold=threshold))

    ge("min_dscr", s["min_dscr"], MIN_DSCR_FLOOR)
    ge("avg_dscr", s["avg_dscr"], AVG_DSCR_FLOOR)
    ge("llcr", s["llcr"], LLCR_FLOOR)

    max_gearing = s["max_gearing"]
    gearing = s["gearing"]
    if max_gearing is None:
        raise ValueError("max_gearing must be provided to the compliance gate")
    flags.append(
        GateFlag(
            rule_id="gearing",
            passed=gearing is not None and gearing <= max_gearing,
            value=gearing,
            threshold=max_gearing,
        )
    )

    hurdle = s["equity_target_irr"]
    if hurdle is None:
        raise ValueError("equity_target_irr (hurdle) must be provided to the compliance gate")
    ge("equity_irr", s["equity_irr"], hurdle - IRR_HURDLE_BUFFER)
    ge("p90_min_dscr", s["p90_min_dscr"], P90_MIN_DSCR_FLOOR)

    if latest_price_date is not None:
        if as_of is None:
            raise ValueError("as_of is required when latest_price_date is provided")
        age_days = (_as_date(as_of) - _as_date(latest_price_date)).days
        flags.append(
            GateFlag(
                rule_id="prices_fresh",
                passed=age_days <= PRICE_FRESHNESS_DAYS,
                value=float(age_days),
                threshold=float(PRICE_FRESHNESS_DAYS),
            )
        )

    if latest_marktwert_month is not None:
        if as_of is None:
            raise ValueError("as_of is required when latest_marktwert_month is provided")
        age_months = _months_between(_as_date(as_of), _as_date(latest_marktwert_month))
        flags.append(
            GateFlag(
                rule_id="marktwerte_fresh",
                passed=age_months <= MARKTWERT_FRESHNESS_MONTHS,
                value=float(age_months),
                threshold=float(MARKTWERT_FRESHNESS_MONTHS),
            )
        )

    return flags
