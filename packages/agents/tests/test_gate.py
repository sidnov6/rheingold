"""Compliance-gate tests (spec §9.4): every rule at its pass/fail boundary.

All scalar values here are synthetic test fixtures, not market data.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest
from rheingold_agents.compliance_gate import DEALBREAKER_GATES, run

AS_OF = datetime(2026, 7, 11, 12, 0, 0)

BASE = {
    "min_dscr": 1.30,
    "avg_dscr": 1.40,
    "llcr": 1.45,
    "gearing": 0.70,
    "max_gearing": 0.75,
    "equity_irr": 0.085,
    "equity_target_irr": 0.08,
    "p90_min_dscr": 1.05,
}


def flag(flags, rule_id):
    matches = [f for f in flags if f.rule_id == rule_id]
    assert len(matches) == 1, f"expected exactly one '{rule_id}' flag, got {len(matches)}"
    return matches[0]


def run_with(**overrides):
    return run({**BASE, **overrides})


@pytest.mark.parametrize(
    ("rule_id", "key", "pass_value", "fail_value", "threshold"),
    [
        ("min_dscr", "min_dscr", 1.15, 1.1499, 1.15),
        ("avg_dscr", "avg_dscr", 1.25, 1.2499, 1.25),
        ("llcr", "llcr", 1.30, 1.2999, 1.30),
        ("p90_min_dscr", "p90_min_dscr", 1.00, 0.9999, 1.00),
    ],
)
def test_floor_rules_boundary(rule_id, key, pass_value, fail_value, threshold):
    passing = flag(run_with(**{key: pass_value}), rule_id)
    assert passing.passed is True
    assert passing.value == pass_value
    assert passing.threshold == threshold

    failing = flag(run_with(**{key: fail_value}), rule_id)
    assert failing.passed is False


def test_gearing_cap_boundary():
    assert flag(run_with(gearing=0.75), "gearing").passed is True  # at cap: pass
    failing = flag(run_with(gearing=0.7501), "gearing")
    assert failing.passed is False
    assert failing.threshold == BASE["max_gearing"]


def test_equity_irr_hurdle_minus_150bps_boundary():
    # hurdle 8% -> floor 6.5%
    assert flag(run_with(equity_irr=0.065), "equity_irr").passed is True
    assert flag(run_with(equity_irr=0.0649), "equity_irr").passed is False
    irr_flag = flag(run_with(equity_irr=0.065), "equity_irr")
    assert irr_flag.threshold == pytest.approx(0.065)


def test_equity_irr_none_fails():
    assert flag(run_with(equity_irr=None), "equity_irr").passed is False


def test_price_freshness_boundary():
    flags = run(BASE, as_of=AS_OF, latest_price_date=AS_OF - timedelta(days=45))
    assert flag(flags, "prices_fresh").passed is True
    assert flag(flags, "prices_fresh").value == 45.0

    stale = run(BASE, as_of=AS_OF, latest_price_date=AS_OF - timedelta(days=46))
    assert flag(stale, "prices_fresh").passed is False


def test_marktwert_freshness_boundary():
    # as_of July 2026: May 2026 is 2 months old (pass); April 2026 is 3 months (fail).
    fresh = run(BASE, as_of=AS_OF, latest_marktwert_month=date(2026, 5, 1))
    assert flag(fresh, "marktwerte_fresh").passed is True
    assert flag(fresh, "marktwerte_fresh").value == 2.0

    stale = run(BASE, as_of=AS_OF, latest_marktwert_month=date(2026, 4, 1))
    assert flag(stale, "marktwerte_fresh").passed is False


def test_freshness_gates_omitted_without_inputs():
    rule_ids = {f.rule_id for f in run(BASE)}
    assert "prices_fresh" not in rule_ids
    assert "marktwerte_fresh" not in rule_ids
    assert rule_ids == {
        "min_dscr",
        "avg_dscr",
        "llcr",
        "gearing",
        "equity_irr",
        "p90_min_dscr",
    }


def test_freshness_requires_as_of():
    with pytest.raises(ValueError):
        run(BASE, latest_price_date=AS_OF)


def test_missing_scalar_key_raises():
    incomplete = {k: v for k, v in BASE.items() if k != "llcr"}
    with pytest.raises(KeyError):
        run(incomplete)


def test_accepts_underwrite_result_shape():
    """Duck-typed UnderwriteResult: scalars pulled from .debt / .valuation / .assumptions."""
    result = SimpleNamespace(
        debt=SimpleNamespace(min_dscr=1.32, avg_dscr=1.41, llcr=1.38, gearing=0.72),
        valuation=SimpleNamespace(equity_irr=0.084, p90_min_dscr=1.02),
        assumptions=SimpleNamespace(max_gearing=0.75, equity_target_irr=0.08),
    )
    flags = run(result)
    assert all(f.passed for f in flags)
    assert flag(flags, "gearing").value == 0.72


def test_dealbreaker_gate_set():
    assert DEALBREAKER_GATES == {"min_dscr", "p90_min_dscr", "gearing"}
