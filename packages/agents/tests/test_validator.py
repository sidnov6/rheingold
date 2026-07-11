"""Adversarial citation-validator tests (spec §9.6 / §13.1).

Fixtures: fabricated number, orphan citation id, rounding games at the 0.5%
boundary, unit-conversion matches, uncited numeric paragraphs, PROCEED with a
failed dealbreaker gate, and conditions referencing missing claims.

All values are synthetic test fixtures, not market data.
"""

from __future__ import annotations

from rheingold_agents.schemas import Claim, Condition, GateFlag
from rheingold_agents.validator import validate
from rheingold_engine.models import EvidenceItem

EVIDENCE = [
    EvidenceItem(id="E-DSCR-MIN", type="computed", label="Minimum DSCR", value=1.32, unit="×"),
    EvidenceItem(id="E-IRR-EQ", type="computed", label="Equity IRR", value=0.084, unit=""),
    EvidenceItem(id="E-MW-REF", type="source", label="Marktwert", value=5.0, unit="ct/kWh"),
    EvidenceItem(id="E-E-P50", type="computed", label="P50 energy", value=118.4, unit="GWh"),
    EvidenceItem(id="E-CAPEX", type="assumption", label="Capex", value=63_000_000.0, unit="EUR"),
    EvidenceItem(
        id="E-OPEX-FIX", type="assumption", label="Fixed opex", value=2_310_000.0, unit="EUR"
    ),
    EvidenceItem(id="E-YEAR-COD", type="source", label="Commissioning year", value=2017, unit=""),
]

CLAIMS = [
    Claim(
        id="CRD-1",
        agent="credit",
        statement="Min DSCR headroom over the 1.15x floor is thin under P90 energy.",
        evidence_ids=["E-DSCR-MIN"],
        severity="concern",
        confidence=0.8,
    ),
]

PASSING_GATES = [
    GateFlag(rule_id="min_dscr", passed=True, value=1.32, threshold=1.15),
    GateFlag(rule_id="gearing", passed=True, value=0.70, threshold=0.75),
    GateFlag(rule_id="p90_min_dscr", passed=True, value=1.02, threshold=1.00),
    GateFlag(rule_id="avg_dscr", passed=True, value=1.41, threshold=1.25),
]


def check(markdown, *, verdict="PROCEED_WITH_CONDITIONS", gates=None, conditions=()):
    return validate(markdown, EVIDENCE, CLAIMS, gates or PASSING_GATES, verdict, list(conditions))


# --- happy path -----------------------------------------------------------------------


def test_valid_memo_passes():
    memo = (
        "The minimum DSCR is 1.32× [E:E-DSCR-MIN] and the equity IRR is 8.4% [E:E-IRR-EQ].\n\n"
        "The farm was commissioned in 2017 [E:E-YEAR-COD].\n\n"
        "No numbers here, so no citation is needed."
    )
    result = check(memo)
    assert result["ok"] is True
    assert result["errors"] == []


# --- §13.1 adversarial fixtures ---------------------------------------------------------


def test_fabricated_number_fails():
    result = check("The minimum DSCR is 1.55× [E:E-DSCR-MIN], comfortably above covenant.")
    assert result["ok"] is False
    assert any("1.55" in e for e in result["errors"])


def test_orphan_citation_id_fails():
    result = check("The minimum DSCR is 1.32× [E:E-DOES-NOT-EXIST].")
    assert result["ok"] is False
    assert any("E-DOES-NOT-EXIST" in e and "does not exist" in e for e in result["errors"])


def test_rounding_game_0_6_pct_fails():
    # evidence 1.32; 1.328 is 0.606% off -> must FAIL
    result = check("The minimum DSCR is 1.328× [E:E-DSCR-MIN].")
    assert result["ok"] is False


def test_rounding_game_0_4_pct_passes():
    # evidence 1.32; 1.325 is 0.379% off -> must PASS
    result = check("The minimum DSCR is 1.325× [E:E-DSCR-MIN].")
    assert result["ok"] is True


def test_unit_conversion_ct_kwh_vs_eur_mwh():
    # evidence 5.0 ct/kWh == 50 EUR/MWh
    assert check("The Marktwert reference is 50 EUR/MWh [E:E-MW-REF].")["ok"] is True
    assert check("The Marktwert reference is 5.0 ct/kWh [E:E-MW-REF].")["ok"] is True
    assert check("The Marktwert reference is 55 EUR/MWh [E:E-MW-REF].")["ok"] is False


def test_unit_conversion_gwh_vs_mwh():
    assert check("P50 output is 118.4 GWh [E:E-E-P50].")["ok"] is True
    assert check("P50 output is 118,400 MWh [E:E-E-P50].")["ok"] is True


def test_unit_conversion_m_eur_and_k_eur():
    assert check("Total capex is 63 M€ [E:E-CAPEX].")["ok"] is True
    assert check("Fixed opex runs at 2,310 k€ [E:E-OPEX-FIX] per year.")["ok"] is True
    assert check("Total capex is 66 M€ [E:E-CAPEX].")["ok"] is False


def test_percent_vs_decimal_conversion():
    # evidence 0.084 (decimal, unit "") == 8.4%
    assert check("Equity IRR is 8.4% [E:E-IRR-EQ].")["ok"] is True
    assert check("Equity IRR is 0.084 [E:E-IRR-EQ].")["ok"] is True
    assert check("Equity IRR is 9.4% [E:E-IRR-EQ].")["ok"] is False


def test_paragraph_with_number_but_no_citation_fails():
    memo = "Fine paragraph with citation 1.32× [E:E-DSCR-MIN].\n\nThe DSCR floor is 1.15 though."
    result = check(memo)
    assert result["ok"] is False
    assert any("no [E:ID] citation" in e for e in result["errors"])


def test_number_must_match_evidence_cited_in_same_paragraph():
    # 8.4% matches E-IRR-EQ, but that id is cited in a DIFFERENT paragraph.
    memo = (
        "Equity IRR is attractive at 8.4% [E:E-DSCR-MIN].\n\n"
        "Separately, the IRR evidence lives here [E:E-IRR-EQ]."
    )
    result = check(memo)
    assert result["ok"] is False


def test_integer_year_must_match_exactly():
    assert check("Commissioned in 2017 [E:E-YEAR-COD].")["ok"] is True
    assert check("Commissioned in 2018 [E:E-YEAR-COD].")["ok"] is False


def test_proceed_with_failed_dealbreaker_gate_fails():
    gates = [
        GateFlag(rule_id="min_dscr", passed=False, value=1.10, threshold=1.15),
        GateFlag(rule_id="gearing", passed=True, value=0.70, threshold=0.75),
    ]
    result = check("All quiet.", verdict="PROCEED", gates=gates)
    assert result["ok"] is False
    assert any("PROCEED" in e and "min_dscr" in e for e in result["errors"])


def test_non_dealbreaker_gate_failure_allows_proceed():
    gates = [
        GateFlag(rule_id="avg_dscr", passed=False, value=1.20, threshold=1.25),
        GateFlag(rule_id="min_dscr", passed=True, value=1.32, threshold=1.15),
    ]
    assert check("All quiet.", verdict="PROCEED", gates=gates)["ok"] is True


def test_decline_allowed_despite_failed_dealbreaker():
    gates = [GateFlag(rule_id="p90_min_dscr", passed=False, value=0.94, threshold=1.00)]
    assert check("All quiet.", verdict="DECLINE", gates=gates)["ok"] is True


def test_condition_referencing_missing_claim_fails():
    result = check(
        "All quiet.",
        conditions=[Condition(text="Obtain availability warranty.", claim_id="GHOST-9")],
    )
    assert result["ok"] is False
    assert any("GHOST-9" in e for e in result["errors"])


def test_condition_referencing_existing_claim_passes():
    result = check(
        "All quiet.",
        conditions=[{"text": "Obtain availability warranty.", "claim_id": "CRD-1"}],
    )
    assert result["ok"] is True


# --- structural robustness --------------------------------------------------------------


def test_metrics_table_block_validates_as_one_paragraph():
    table = (
        "| Metric | Value | Evidence |\n"
        "|---|---|---|\n"
        "| Minimum DSCR | 1.32 × | [E:E-DSCR-MIN] |\n"
        "| P50 energy | 118.4 GWh | [E:E-E-P50] |"
    )
    assert check(table)["ok"] is True


def test_headings_and_iso_dates_do_not_need_citations():
    memo = "## 4. Financial Structure\n\nRetrieved on 2026-07-14, the record is clean."
    assert check(memo)["ok"] is True


def test_multiple_errors_are_all_reported():
    memo = "DSCR is 9.99× [E:E-NOPE].\n\nUncited 42 here."
    result = check(memo)
    assert result["ok"] is False
    assert len(result["errors"]) >= 3  # orphan id + unmatched number + uncited paragraph
