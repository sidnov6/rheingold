"""Citation-integrity validator (spec §9.6). Pure code — the agents cannot talk past it.

Checks, in order:
  1. Every [E:ID] token references an existing evidence id.
  2. Every paragraph containing a numeric literal carries >= 1 [E:ID] citation.
  3. Every numeric literal matches some evidence value cited IN THAT PARAGRAPH
     within 0.5% relative (exact for integer-formatted literals / years),
     allowing unit conversions:
         ct/kWh <-> EUR/MWh  (x10)     M€ <-> EUR (x1e6)     k€ <-> EUR (x1e3)
         %      <-> decimal  (x100)    GWh <-> MWh (x1000)   bps -> decimal (x1e-4)
  4. Verdict obeys the gate rules: no PROCEED if any dealbreaker-severity gate failed
     (dealbreaker gates: min_dscr, p90_min_dscr, gearing).
  5. Every condition references an existing claim id.

Returns {"ok": bool, "errors": [str, ...]}.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from rheingold_engine.models import EvidenceItem

from .compliance_gate import DEALBREAKER_GATES
from .schemas import Claim, Condition, GateFlag

REL_TOLERANCE = 0.005  # 0.5% relative for decimal literals
_EXACT_EPS = 1e-9

CITATION_RE = re.compile(r"\[E:([A-Za-z0-9_.\-]+)\]")
_ISO_DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")

# Longest alternatives first so e.g. "MWh" wins over "MW", "EUR/MWh" over "EUR".
_UNIT_PATTERN = r"ct/kWh|EUR/MWh|€/MWh|Mio\.?\s?€|M€|k€|EUR|GWh|MWh|MW|bps|pp|%|×|x(?![\w])|€"
NUMERIC_RE = re.compile(
    rf"(?<![\w§.,])(?P<sign>[-−])?(?P<num>\d{{1,3}}(?:,\d{{3}})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    rf"[ \t]*(?P<unit>{_UNIT_PATTERN})?"
)

# unit -> (dimension, factor to the dimension's canonical unit)
_UNIT_DIM: dict[str, tuple[str, float]] = {
    "": ("scalar", 1.0),
    "×": ("scalar", 1.0),
    "x": ("scalar", 1.0),
    "%": ("scalar", 0.01),
    "pp": ("scalar", 0.01),
    "bps": ("scalar", 1e-4),
    "ct/kwh": ("price_eur_mwh", 10.0),
    "eur/mwh": ("price_eur_mwh", 1.0),
    "€/mwh": ("price_eur_mwh", 1.0),
    "m€": ("money_eur", 1e6),
    "mio€": ("money_eur", 1e6),
    "mio.€": ("money_eur", 1e6),
    "k€": ("money_eur", 1e3),
    "€": ("money_eur", 1.0),
    "eur": ("money_eur", 1.0),
    "gwh": ("energy_mwh", 1000.0),
    "mwh": ("energy_mwh", 1.0),
    "mw": ("power_mw", 1.0),
}


def _unit_key(unit: str) -> str:
    return unit.strip().replace(" ", "").lower()


def _dim(unit: str) -> tuple[str, float]:
    key = _unit_key(unit)
    if key in _UNIT_DIM:
        return _UNIT_DIM[key]
    # Unknown unit (e.g. "m" hub height): its own dimension, exact-unit compare only.
    return (f"unit:{key}", 1.0)


class _Literal:
    __slots__ = ("raw", "value", "unit", "is_integer")

    def __init__(self, raw: str, value: float, unit: str, is_integer: bool):
        self.raw = raw
        self.value = value
        self.unit = unit
        self.is_integer = is_integer


def _extract_literals(text: str) -> list[_Literal]:
    out: list[_Literal] = []
    for m in NUMERIC_RE.finditer(text):
        num = m.group("num")
        unit = m.group("unit") or ""
        value = float(num.replace(",", ""))
        if m.group("sign"):
            value = -value
        out.append(_Literal(m.group(0).strip(), value, unit, "." not in num))
    return out


def _matches(lit: _Literal, ev_value: float, ev_unit: str) -> bool:
    lit_dim, lit_factor = _dim(lit.unit)
    ev_dim, ev_factor = _dim(ev_unit)

    candidates: list[tuple[float, float]] = []  # (literal canonical, evidence canonical)
    if lit_dim == ev_dim:
        candidates.append((lit.value * lit_factor, ev_value * ev_factor))
    if lit.unit == "":
        # A bare literal also compares raw against the evidence value (covers
        # unknown evidence units and "%"-typed evidence quoted as plain numbers).
        candidates.append((lit.value, ev_value))

    for lit_canon, ev_canon in candidates:
        if lit.is_integer:
            if abs(lit_canon - ev_canon) <= _EXACT_EPS * max(1.0, abs(ev_canon)):
                return True
        else:
            denom = max(abs(ev_canon), 1e-12)
            if abs(lit_canon - ev_canon) / denom <= REL_TOLERANCE:
                return True
    return False


def _paragraphs(markdown: str) -> list[str]:
    return [block.strip() for block in re.split(r"\n\s*\n", markdown) if block.strip()]


def _strip_non_prose(block: str) -> str:
    """Remove markdown headings and table-separator rows before numeric extraction."""
    kept: list[str] = []
    for line in block.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if re.fullmatch(r"\|?[\s:|-]+\|?", stripped):  # table separator row
            continue
        kept.append(line)
    return "\n".join(kept)


def validate(
    memo_markdown: str,
    evidence: Sequence[EvidenceItem],
    claims: Sequence[Claim],
    gate_flags: Sequence[GateFlag],
    verdict: str,
    conditions: Sequence[Condition | Mapping[str, Any]],
) -> dict[str, Any]:
    errors: list[str] = []
    evidence_by_id = {e.id: e for e in evidence}
    claim_ids = {c.id for c in claims}

    for para_no, block in enumerate(_paragraphs(memo_markdown), start=1):
        cited_ids = CITATION_RE.findall(block)
        known_cited: list[EvidenceItem] = []
        for cid in cited_ids:
            item = evidence_by_id.get(cid)
            if item is None:
                errors.append(f"paragraph {para_no}: cited evidence id '{cid}' does not exist")
            else:
                known_cited.append(item)

        prose = _strip_non_prose(CITATION_RE.sub(" ", block))
        prose = _ISO_DATE_RE.sub(" ", prose)
        literals = _extract_literals(prose)
        if not literals:
            continue
        if not cited_ids:
            errors.append(
                f"paragraph {para_no}: contains numeric literal(s) "
                f"({', '.join(lit.raw for lit in literals[:3])}) but no [E:ID] citation"
            )
            continue

        numeric_cited = [
            (item, float(item.value)) for item in known_cited if isinstance(item.value, int | float)
        ]
        for lit in literals:
            if not any(_matches(lit, ev_val, item.unit) for item, ev_val in numeric_cited):
                errors.append(
                    f"paragraph {para_no}: numeric literal '{lit.raw}' does not match any "
                    f"evidence value cited in that paragraph (within 0.5% / exact for integers)"
                )

    if verdict == "PROCEED":
        failed_dealbreakers = [
            g.rule_id for g in gate_flags if not g.passed and g.rule_id in DEALBREAKER_GATES
        ]
        if failed_dealbreakers:
            errors.append(
                "verdict PROCEED is not allowed: failed dealbreaker gate(s): "
                + ", ".join(sorted(failed_dealbreakers))
            )

    for i, cond in enumerate(conditions, start=1):
        c = cond if isinstance(cond, Condition) else Condition.model_validate(cond)
        if c.claim_id not in claim_ids:
            errors.append(f"condition {i} references unknown claim id '{c.claim_id}'")

    return {"ok": not errors, "errors": errors}
