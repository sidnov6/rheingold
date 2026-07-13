"""Deterministic offline-debate tests: it must stream the right events, cite real
evidence, and always pass the citation validator (no LLM, no network)."""

import asyncio

import pytest
from rheingold_agents.offline import (
    OfflineEvidence,
    _num4,
    build_offline_memo,
    run_offline_debate,
)
from rheingold_agents.schemas import GateFlag
from rheingold_agents.validator import validate
from rheingold_engine.models import EvidenceItem


def _evidence() -> list[EvidenceItem]:
    """A compact but realistic evidence store (subset of the real ids)."""
    return [
        EvidenceItem(
            id="E-INP-MW", type="source", label="Installed capacity", value=42.0, unit="MW"
        ),
        EvidenceItem(id="E-INP-N-UNITS", type="source", label="Turbine count", value=10.0, unit=""),
        EvidenceItem(
            id="E-INP-COMMISSIONING",
            type="source",
            label="Commissioning year",
            value=2011.0,
            unit="",
        ),
        EvidenceItem(
            id="E-INP-TURBINE", type="source", label="Turbine type", value="MM92", unit=""
        ),
        EvidenceItem(
            id="E-ASM-AVAILABILITY", type="assumption", label="Availability", value=0.97, unit=""
        ),
        EvidenceItem(
            id="E-ASM-REVENUE-MODE",
            type="assumption",
            label="Revenue mode",
            value="eeg_premium",
            unit="",
        ),
        EvidenceItem(id="E-ASM-NEG-RULE", type="assumption", label="§51", value=4.0, unit="h"),
        EvidenceItem(
            id="E-ASM-EEG-SUPPORT", type="assumption", label="Support", value=20.0, unit="years"
        ),
        EvidenceItem(
            id="E-ASM-LIFETIME", type="assumption", label="Lifetime", value=25.0, unit="years"
        ),
        EvidenceItem(id="E-ASM-WACC", type="assumption", label="WACC", value=0.058, unit=""),
        EvidenceItem(id="E-ASM-HURDLE", type="assumption", label="Hurdle", value=0.08, unit=""),
        EvidenceItem(id="E-ASM-RATE", type="assumption", label="Rate", value=0.045, unit=""),
        EvidenceItem(
            id="E-ENE-P50",
            type="computed",
            label="P50 energy",
            value=96.66,
            unit="GWh",
            formula_ref="§8.2",
        ),
        EvidenceItem(
            id="E-ENE-P90",
            type="computed",
            label="P90 energy",
            value=84.3,
            unit="GWh",
            formula_ref="§8.2.2",
        ),
        EvidenceItem(
            id="E-ENE-NET-CF",
            type="computed",
            label="Net CF",
            value=0.2843,
            unit="",
            formula_ref="§8.2",
        ),
        EvidenceItem(
            id="E-ENE-SIGMA",
            type="computed",
            label="Sigma",
            value=0.0949,
            unit="",
            formula_ref="§8.2.2",
        ),
        EvidenceItem(
            id="E-REV-CAPTURE",
            type="computed",
            label="Capture",
            value=0.91,
            unit="",
            formula_ref="§8.3.4",
        ),
        EvidenceItem(
            id="E-REV-Y1",
            type="computed",
            label="Revenue y1",
            value=5_803_262.0,
            unit="EUR",
            formula_ref="§8.3",
        ),
        EvidenceItem(
            id="E-DBT-MIN-DSCR",
            type="computed",
            label="Min DSCR",
            value=1.32,
            unit="×",
            formula_ref="§8.5",
        ),
        EvidenceItem(
            id="E-DBT-LLCR", type="computed", label="LLCR", value=1.41, unit="×", formula_ref="§8.5"
        ),
        EvidenceItem(
            id="E-DBT-GEARING",
            type="computed",
            label="Gearing",
            value=0.75,
            unit="",
            formula_ref="§8.5",
        ),
        EvidenceItem(
            id="E-ASM-MAX-GEARING", type="assumption", label="Gearing cap", value=0.75, unit=""
        ),
        EvidenceItem(
            id="E-VAL-LCOE",
            type="computed",
            label="LCOE",
            value=58.4,
            unit="EUR/MWh",
            formula_ref="§8.6",
        ),
        EvidenceItem(
            id="E-VAL-IRR",
            type="computed",
            label="Equity IRR",
            value=0.16004,
            unit="",
            formula_ref="§8.6",
        ),
        EvidenceItem(
            id="E-VAL-P90-DSCR",
            type="computed",
            label="P90 min DSCR",
            value=1.08,
            unit="×",
            formula_ref="§9.4",
        ),
        EvidenceItem(id="E-ASM-AW", type="assumption", label="AW", value=5.874, unit="ct/kWh"),
    ]


def _gates(all_pass: bool = True) -> list[GateFlag]:
    return [
        GateFlag(rule_id="min_dscr", passed=all_pass, value=1.32, threshold=1.15),
        GateFlag(rule_id="avg_dscr", passed=all_pass, value=1.4, threshold=1.25),
        GateFlag(rule_id="llcr", passed=all_pass, value=1.41, threshold=1.3),
        GateFlag(rule_id="gearing", passed=True, value=0.75, threshold=0.75),
        GateFlag(rule_id="equity_irr", passed=True, value=0.16, threshold=0.065),
        GateFlag(rule_id="p90_min_dscr", passed=all_pass, value=1.08, threshold=1.0),
    ]


def test_num4_forces_decimal_for_non_integers():
    assert _num4(75.0) == "75"  # clean whole number stays clean
    assert "." in _num4(16.004)  # non-integer never renders as bare integer
    assert "." in _num4(143.04)
    assert _num4(30.213262) == "30.21"


def test_offline_memo_passes_validator():
    ev = _evidence()
    gates = _gates()
    oe = OfflineEvidence(ev)
    from rheingold_agents.offline import credit_claims, resource_claims, revenue_claims

    claims = resource_claims(oe) + revenue_claims(oe) + credit_claims(oe, gates)
    memo = build_offline_memo(oe, claims, gates)
    from rheingold_agents.offline import memo_to_markdown

    v = validate(memo_to_markdown(memo), ev, claims, gates, memo.verdict, memo.conditions)
    assert v["ok"], v["errors"]


def test_verdict_declines_on_failed_dealbreaker():
    ev = _evidence()
    gates = _gates(all_pass=False)  # min_dscr / p90 fail → dealbreaker
    out = asyncio.run(run_offline_debate(ev, gates, delay=0))
    assert out["memo"].verdict == "DECLINE"
    assert out["validation"]["ok"], out["validation"]["errors"]


def test_stream_emits_expected_event_sequence():
    ev = _evidence()
    gates = _gates()
    events: list[tuple[str, dict]] = []

    def on_event(t, p):
        events.append((t, p))

    out = asyncio.run(run_offline_debate(ev, gates, on_event, delay=0))
    types = [t for t, _ in events]
    assert "claim" in types
    assert "memo_delta" in types
    assert types[-1] == "done"
    assert "validation" in types
    # every claim cites only real evidence ids
    ids = {e.id for e in ev}
    for t, p in events:
        if t == "claim":
            assert set(p["evidence_ids"]) <= ids
    assert out["mode"] == "offline"
    assert out["memo_markdown"].startswith("## 1. Recommendation")


def test_deterministic_same_input_same_memo():
    ev, gates = _evidence(), _gates()
    a = asyncio.run(run_offline_debate(ev, gates, delay=0))
    b = asyncio.run(run_offline_debate(ev, gates, delay=0))
    assert a["memo_markdown"] == b["memo_markdown"]
    assert a["memo"].verdict == b["memo"].verdict


@pytest.mark.parametrize("vintage,expect_concern", [(2005, True), (2024, False)])
def test_resource_technology_claim_scales_with_vintage(vintage, expect_concern):
    ev = [e for e in _evidence() if e.id != "E-INP-COMMISSIONING"]
    ev.append(
        EvidenceItem(
            id="E-INP-COMMISSIONING", type="source", label="year", value=float(vintage), unit=""
        )
    )
    from rheingold_agents.offline import resource_claims

    claims = resource_claims(OfflineEvidence(ev))
    tech = next(c for c in claims if c.id == "RES-4")
    assert (tech.severity == "concern") == expect_concern
