"""Narrator (spec §9.7): builds the IC memo prompt and the code-built metrics table.

The section-4 metrics table is BUILT BY CODE from evidence — never by the LLM —
so every row carries a verbatim evidence value and its [E:ID] citation. The
narrator receives evidence + claims + rebuttals + gate flags + the prebuilt table
and fills the fixed section structure, embedding [E:ID] citations everywhere a
number appears.
"""

from __future__ import annotations

from collections.abc import Sequence

from rheingold_engine.models import EvidenceItem

#: Fixed §9.7 memo structure the narrator must fill, in order.
MEMO_SECTIONS: tuple[tuple[str, str], ...] = (
    ("recommendation", "1. Recommendation"),
    ("asset_resource", "2. Asset & Resource"),
    ("revenue_market", "3. Revenue & Market"),
    ("financial_structure", "4. Financial Structure"),
    ("risks_mitigants", "5. Risks & Mitigants"),
    ("sensitivities", "6. Sensitivities"),
    ("conditions_precedent", "7. Conditions Precedent"),
    ("appendix_assumptions", "Appendix: Assumptions"),
)


def _fmt_value(value: float) -> str:
    """Format so the citation validator parses back to the same value.

    Integers render exactly; decimals keep 4 significant digits (rounding error
    well inside the validator's 0.5% relative tolerance) with thousands commas.
    """
    v = float(value)
    if v.is_integer() and abs(v) < 1e15:
        return f"{int(v):,}"
    if abs(v) >= 1000:
        return f"{v:,.1f}"
    # 4 significant figures, but guarantee a decimal point so the validator never
    # treats a non-integer value (e.g. 180.04 → "180") as an exact-match integer.
    s = f"{v:.4g}"
    if "." not in s and "e" not in s and "E" not in s:
        s = f"{v:.1f}"
    return s


def build_metrics_table(
    evidence: Sequence[EvidenceItem],
    ids: Sequence[str] | None = None,
) -> str:
    """Build the section-4 metrics table (markdown) from evidence, one [E:ID] per row.

    By default every `computed` evidence item with a numeric value is included,
    in store order. Pass `ids` to select and order specific rows.
    """
    by_id = {e.id: e for e in evidence}
    if ids is not None:
        items = [by_id[i] for i in ids if i in by_id]
    else:
        items = [e for e in evidence if e.type == "computed" and isinstance(e.value, int | float)]

    lines = ["| Metric | Value | Evidence |", "|---|---|---|"]
    for item in items:
        if isinstance(item.value, int | float):
            cell = _fmt_value(float(item.value))
            if item.unit:
                cell = f"{cell} {item.unit}"
        else:
            cell = str(item.value)
        lines.append(f"| {item.label} | {cell} | [E:{item.id}] |")
    return "\n".join(lines)


NARRATOR_SYSTEM = """\
You are the Narrator of a German onshore-wind project-finance investment committee.
You write the final IC memo from evidence the deterministic engine produced and the
claims/rebuttals the three critics (resource, revenue, credit) debated.

Hard rules — a deterministic citation validator rejects violations:
- You may ONLY reference evidence ids that exist in the EVIDENCE JSON, using the
  inline token form [E:ID]. Inventing an id is a hard failure.
- EVERY paragraph that contains a numeric literal must contain at least one [E:ID]
  citation, and every number must match a cited evidence value in that same
  paragraph (0.5% tolerance; exact for integers and years). Quote evidence values
  verbatim rather than re-deriving or aggressively rounding them.
- Section '4. Financial Structure' must include the prebuilt METRICS TABLE verbatim
  as given — it was built by code from evidence. Do not invent, alter, or add rows.
- Verdict is one of PROCEED | PROCEED_WITH_CONDITIONS | DECLINE. You cannot output
  PROCEED if any dealbreaker gate (min_dscr, p90_min_dscr, gearing) failed — this is
  enforced in code after generation.
- Cite any failed gate flag explicitly in '5. Risks & Mitigants'.
- Every condition must reference an existing claim id from the debate. Keep condition
  text free of numeric literals (put numbers, with citations, in the sections).
- Fill the fixed section structure exactly, in order, using these (key, title) pairs:
{section_list}
- Order '5. Risks & Mitigants' by severity (dealbreaker, then concern, then info).
- Register: a disciplined credit memo — terse, evidence-first, no marketing prose.
Respond ONLY with the submit_memo tool call."""


def narrator_system_prompt() -> str:
    section_list = "\n".join(f"  - ({key!r}, {title!r})" for key, title in MEMO_SECTIONS)
    return NARRATOR_SYSTEM.format(section_list=section_list)


def build_narrator_prompt(
    evidence_json: str,
    claims_json: str,
    rebuttals_json: str,
    gate_flags_json: str,
    metrics_table_md: str,
) -> str:
    return (
        f"EVIDENCE (frozen EvidenceStore — the only ids you may cite):\n{evidence_json}\n\n"
        f"CRITIC CLAIMS:\n{claims_json}\n\n"
        f"REBUTTALS:\n{rebuttals_json}\n\n"
        f"COMPLIANCE GATE FLAGS (deterministic):\n{gate_flags_json}\n\n"
        f"METRICS TABLE (prebuilt by code — include verbatim as the body of section "
        f"'4. Financial Structure'):\n{metrics_table_md}\n\n"
        f"Write the IC memo now via the submit_memo tool."
    )
