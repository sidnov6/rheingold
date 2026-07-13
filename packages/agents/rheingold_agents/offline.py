"""Deterministic offline agent debate (spec §15 zero-API demo).

When no LLM provider is configured, memo generation still runs: rule-based
critics derive real, evidence-cited claims from the frozen EvidenceStore + gate
flags, and a deterministic narrator composes the §9.7 memo. It streams through
the SAME on_event contract as the LLM orchestrator (agent_status / claim /
rebuttal / memo_delta / validation / done) so the AgentDebatePanel and the paper
memo animate identically — you watch the committee draft in real time.

Every number the narrator writes is routed through cite(), which formats the
value to round-trip through the citation-integrity validator (§9.6) within its
0.5 % tolerance. The debate is pure and deterministic: same evidence → same memo.
It is clearly labelled "rule-based" so it is never mistaken for LLM-authored prose.
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Sequence
from typing import Any

from rheingold_engine.models import EvidenceItem

from .compliance_gate import DEALBREAKER_GATES
from .narrator import _fmt_value, build_metrics_table
from .schemas import Claim, Condition, GateFlag, Memo, MemoSection, Rebuttal
from .validator import validate

# Evidence ids whose bare decimal reads best as a percentage (both map to the
# validator's "scalar" dimension, so "17.2 %" matches an evidence value of 0.172).
_PCT_IDS = frozenset(
    {
        "E-VAL-IRR",
        "E-ASM-WACC",
        "E-ASM-HURDLE",
        "E-ASM-RATE",
        "E-ASM-AVAILABILITY",
        "E-ASM-ELEC-LOSSES",
        "E-ASM-WAKE",
        "E-ASM-CURTAILMENT",
        "E-ASM-DEGRADATION",
        "E-ASM-LEASE",
        "E-ASM-INFLATION",
        "E-ASM-TAX",
        "E-DBT-GEARING",
        "E-ASM-MAX-GEARING",
        "E-REV-CAPTURE",
        "E-ENE-NET-CF",
    }
)
# Units the validator understands directly (safe to print adjacent to the number).
_KNOWN_UNITS = frozenset({"", "×", "GWh", "MWh", "m", "ct/kWh", "EUR/MWh"})


def _num4(v: float) -> str:
    """4 significant figures, but never an integer-looking string for a non-integer
    value (the validator would then demand an exact match). '30.21', '143.04', '75'."""
    s = f"{v:.4g}"
    if "." not in s and "e" not in s.lower() and not float(v).is_integer():
        s = f"{v:.2f}"
    return s


class OfflineEvidence:
    """Convenience wrapper over the evidence list keyed by id."""

    def __init__(self, evidence: Sequence[EvidenceItem]) -> None:
        self.by_id = {e.id: e for e in evidence}

    def has(self, id_: str) -> bool:
        return id_ in self.by_id

    def num(self, id_: str) -> float | None:
        item = self.by_id.get(id_)
        if item is None or not isinstance(item.value, int | float):
            return None
        return float(item.value)

    def text(self, id_: str) -> str | None:
        item = self.by_id.get(id_)
        return str(item.value) if item is not None else None

    def cite(self, id_: str) -> str:
        """'<value><unit> [E:id]', formatted to pass the citation validator.

        Returns '' if the id is absent so callers can guard optional evidence.
        """
        item = self.by_id.get(id_)
        if item is None:
            return ""
        v = item.value
        if isinstance(v, str):
            return f"{v} [E:{id_}]"
        v = float(v)
        unit = item.unit
        if id_ in _PCT_IDS:  # decimal → percent (scalar dimension both ways)
            disp = f"{_num4(v * 100)} %"
        elif unit == "EUR":  # money → M€ / k€ (money_eur dimension)
            if abs(v) >= 1e6:
                disp = f"{_num4(v / 1e6)} M€"
            elif abs(v) >= 1e3:
                disp = f"{_num4(v / 1e3)} k€"
            else:
                disp = f"{v:.0f} €"
        elif unit in _KNOWN_UNITS:
            disp = f"{_fmt_value(v)} {unit}".strip()
        else:
            # Unit not in the validator's map (EUR/MW, EUR/MW/yr, years, months, h):
            # print a bare number so the validator bare-compares against the value.
            disp = _fmt_value(v)
        return f"{disp} [E:{id_}]"


# ------------------------------------------------------------------- critics
def _sev_for(value: float, concern_below: float, dealbreaker_below: float) -> str:
    if value < dealbreaker_below:
        return "dealbreaker"
    if value < concern_below:
        return "concern"
    return "info"


def resource_claims(ev: OfflineEvidence) -> list[Claim]:
    out: list[Claim] = []
    net_cf = ev.num("E-ENE-NET-CF")
    if net_cf is not None:
        out.append(
            Claim(
                id="RES-1",
                agent="resource",
                statement=(
                    f"Net capacity factor lands at {net_cf * 100:.1f}% after farm losses, a "
                    "credible P50 for this site class."
                ),
                evidence_ids=["E-ENE-NET-CF", "E-ENE-P50"],
                severity="info",
                confidence=0.9,
            )
        )
    avail = ev.num("E-ASM-AVAILABILITY")
    vintage = ev.num("E-INP-COMMISSIONING")
    if avail is not None:
        old = vintage is not None and vintage <= 2013
        out.append(
            Claim(
                id="RES-2",
                agent="resource",
                statement=(
                    f"Assumed energy availability of {avail * 100:.0f}% is "
                    + (
                        "optimistic for an older fleet and warrants an O&M reserve."
                        if old
                        else "consistent with modern full-service O&M contracts."
                    )
                ),
                evidence_ids=["E-ASM-AVAILABILITY", "E-INP-COMMISSIONING"],
                severity="concern" if old else "info",
                confidence=0.75 if old else 0.85,
            )
        )
    sigma = ev.num("E-ENE-SIGMA")
    if sigma is not None:
        out.append(
            Claim(
                id="RES-3",
                agent="resource",
                statement=(
                    f"Combined resource uncertainty of sigma {sigma:.3f} pulls P90 well below "
                    "P50; a Path-B (atlas) estimate carries wider error than metered data."
                ),
                evidence_ids=["E-ENE-SIGMA", "E-ENE-P90", "E-ENE-P50"],
                severity="concern" if sigma >= 0.09 else "info",
                confidence=0.7,
            )
        )
    turbine = ev.text("E-INP-TURBINE")
    if turbine is not None and vintage is not None:
        old = vintage <= 2012
        out.append(
            Claim(
                id="RES-4",
                agent="resource",
                statement=(
                    f"Turbine type {turbine} (commissioned {int(vintage)}) "
                    + (
                        "is a gearbox-era machine — technology and spares risk is elevated."
                        if old
                        else "is a modern platform with a mature service ecosystem."
                    )
                ),
                evidence_ids=["E-INP-TURBINE", "E-INP-COMMISSIONING"],
                severity="concern" if old else "info",
                confidence=0.8 if old else 0.9,
            )
        )
    return out


def revenue_claims(ev: OfflineEvidence) -> list[Claim]:
    out: list[Claim] = []
    capture = ev.num("E-REV-CAPTURE")
    if capture is not None:
        out.append(
            Claim(
                id="REV-1",
                agent="revenue",
                statement=(
                    f"Wind capture rate of {capture * 100:.0f}% of baseload reflects the "
                    "cannibalisation discount wind earns in high-wind hours."
                ),
                evidence_ids=["E-REV-CAPTURE"],
                severity="concern" if capture < 0.9 else "info",
                confidence=0.8,
            )
        )
    mode = ev.text("E-ASM-REVENUE-MODE")
    if mode == "eeg_premium":
        out.append(
            Claim(
                id="REV-2",
                agent="revenue",
                statement=(
                    "Revenue rests on the EEG market premium, which floors the anzulegender "
                    "Wert but transfers merchant risk after the support window."
                ),
                evidence_ids=["E-ASM-REVENUE-MODE", "E-ASM-EEG-SUPPORT"],
                severity="info",
                confidence=0.85,
            )
        )
    elif mode == "merchant":
        out.append(
            Claim(
                id="REV-2",
                agent="revenue",
                statement=(
                    "The project runs fully merchant — no EEG premium floor, so cash flows "
                    "track the wholesale curve one-for-one."
                ),
                evidence_ids=["E-ASM-REVENUE-MODE"],
                severity="concern",
                confidence=0.85,
            )
        )
    neg = ev.num("E-ASM-NEG-RULE")
    if neg is not None:
        out.append(
            Claim(
                id="REV-3",
                agent="revenue",
                statement=(
                    "The §51 negative-price rule voids the premium in every negative "
                    "quarter-hour for this cohort — a growing drag as negative hours rise."
                    if neg <= 0
                    else f"The §51 rule voids the premium only in negative streaks of {int(neg)}+ "
                    "hours, a moderate exposure for this vintage."
                ),
                evidence_ids=["E-ASM-NEG-RULE"],
                severity="concern" if neg <= 1 else "info",
                confidence=0.7,
            )
        )
    support = ev.num("E-ASM-EEG-SUPPORT")
    lifetime = ev.num("E-ASM-LIFETIME")
    if support is not None and lifetime is not None and lifetime > support:
        out.append(
            Claim(
                id="REV-4",
                agent="revenue",
                statement=(
                    f"Support ends at year {int(support)} while the asset runs to year "
                    f"{int(lifetime)}; the merchant tail is a real valuation swing factor."
                ),
                evidence_ids=["E-ASM-EEG-SUPPORT", "E-ASM-LIFETIME"],
                severity="concern",
                confidence=0.75,
            )
        )
    return out


def credit_claims(ev: OfflineEvidence, gate_flags: Sequence[GateFlag]) -> list[Claim]:
    out: list[Claim] = []
    gate = {g.rule_id: g for g in gate_flags}
    min_dscr = ev.num("E-DBT-MIN-DSCR")
    if min_dscr is not None:
        out.append(
            Claim(
                id="CRE-1",
                agent="credit",
                statement=(
                    f"Minimum DSCR of {min_dscr:.2f}x sits "
                    + (
                        "below the 1.20x covenant — a structural breach."
                        if min_dscr < 1.20
                        else f"{(min_dscr - 1.20):.2f}x above the 1.20x covenant, giving real headroom."
                    )
                ),
                evidence_ids=["E-DBT-MIN-DSCR"],
                severity=_sev_for(min_dscr, concern_below=1.25, dealbreaker_below=1.15),
                confidence=0.95,
            )
        )
    p90 = ev.num("E-VAL-P90-DSCR")
    if p90 is not None:
        out.append(
            Claim(
                id="CRE-2",
                agent="credit",
                statement=(
                    f"Under P90 energy the minimum DSCR falls to {p90:.2f}x — "
                    + (
                        "debt is not covered in the downside."
                        if p90 < 1.0
                        else "coverage survives the resource downside."
                    )
                ),
                evidence_ids=["E-VAL-P90-DSCR"],
                severity=_sev_for(p90, concern_below=1.1, dealbreaker_below=1.0),
                confidence=0.9,
            )
        )
    gearing = ev.num("E-DBT-GEARING")
    if gearing is not None:
        at_cap = gearing >= 0.749
        out.append(
            Claim(
                id="CRE-3",
                agent="credit",
                statement=(
                    f"Gearing reaches {gearing * 100:.0f}% "
                    + (
                        "— the cap binds, so debt capacity is leverage-limited, not cash-limited."
                        if at_cap
                        else "of capex, leaving the sculpt cash-flow driven."
                    )
                ),
                evidence_ids=["E-DBT-GEARING", "E-ASM-MAX-GEARING"],
                severity="concern" if at_cap else "info",
                confidence=0.8,
            )
        )
    llcr = ev.num("E-DBT-LLCR")
    if llcr is not None:
        out.append(
            Claim(
                id="CRE-4",
                agent="credit",
                statement=(
                    f"LLCR of {llcr:.2f}x indicates loan-life coverage "
                    + ("that is tight." if llcr < 1.3 else "with comfortable margin.")
                ),
                evidence_ids=["E-DBT-LLCR"],
                severity="concern" if llcr < 1.3 else "info",
                confidence=0.8,
            )
        )
    # Surface any failed gate not already captured as a dealbreaker claim.
    for rid, g in gate.items():
        if not g.passed and rid not in {"min_dscr", "p90_min_dscr", "gearing"}:
            out.append(
                Claim(
                    id=f"CRE-GATE-{rid}",
                    agent="credit",
                    statement=f"Compliance gate '{rid}' failed (value {g.value}, threshold {g.threshold}).",
                    evidence_ids=[],
                    severity="concern",
                    confidence=1.0,
                )
            )
    return out


def build_rebuttals(claims: Sequence[Claim], ev: OfflineEvidence) -> list[Rebuttal]:
    """One deterministic cross-examination: credit answers a resource concern when
    coverage headroom absorbs it."""
    rebuttals: list[Rebuttal] = []
    min_dscr = ev.num("E-DBT-MIN-DSCR")
    resource_concern = next(
        (c for c in claims if c.agent == "resource" and c.severity == "concern"), None
    )
    if resource_concern is not None and min_dscr is not None and min_dscr >= 1.30:
        rebuttals.append(
            Rebuttal(
                id="CRE-R1",
                agent="credit",
                statement=(
                    f"Credit view: the {min_dscr:.2f}x coverage headroom absorbs this resource "
                    "concern within the base-case sculpt; it is a pricing input, not a dealbreaker."
                ),
                evidence_ids=["E-DBT-MIN-DSCR"],
                severity="info",
                confidence=0.7,
                targets_claim_id=resource_concern.id,
            )
        )
    return rebuttals[:2]


# ------------------------------------------------------------------- narrator
def _verdict(claims: Sequence[Claim], gate_flags: Sequence[GateFlag]) -> str:
    dealbreaker_failed = any(not g.passed and g.rule_id in DEALBREAKER_GATES for g in gate_flags)
    if dealbreaker_failed or any(c.severity == "dealbreaker" for c in claims):
        return "DECLINE"
    any_gate_failed = any(not g.passed for g in gate_flags)
    has_concern = any(c.severity == "concern" for c in claims)
    if any_gate_failed or has_concern:
        return "PROCEED_WITH_CONDITIONS"
    return "PROCEED"


_VERDICT_PROSE = {
    "PROCEED": "The committee recommends proceeding.",
    "PROCEED_WITH_CONDITIONS": "The committee recommends proceeding, subject to conditions.",
    "DECLINE": "The committee recommends declining on current terms.",
}


def build_offline_memo(
    ev: OfflineEvidence, claims: Sequence[Claim], gate_flags: Sequence[GateFlag]
) -> Memo:
    verdict = _verdict(claims, gate_flags)
    metrics_table = build_metrics_table(list(ev.by_id.values()))

    # 1. Recommendation — thesis with two cited headline metrics.
    irr = ev.cite("E-VAL-IRR")
    dscr = ev.cite("E-DBT-MIN-DSCR")
    lcoe = ev.cite("E-VAL-LCOE")
    thesis_bits = [_VERDICT_PROSE[verdict]]
    if irr and dscr:
        thesis_bits.append(f"Base-case equity IRR is {irr} against a minimum DSCR of {dscr}.")
    if lcoe:
        thesis_bits.append(f"Levelised cost of energy is {lcoe}, framing the merchant downside.")
    thesis = " ".join(thesis_bits)

    sections: list[MemoSection] = []
    sections.append(
        MemoSection(
            key="recommendation",
            title="1. Recommendation",
            markdown=f"**{verdict.replace('_', ' ')}.** {thesis}",
        )
    )

    # 2. Asset & Resource
    asset_lines = [
        f"Installed capacity {ev.cite('E-INP-MW')} across {ev.cite('E-INP-N-UNITS')} turbines.",
        f"P50 annual energy is {ev.cite('E-ENE-P50')} at a net capacity factor of "
        f"{ev.cite('E-ENE-NET-CF')}; the P90 estimate is {ev.cite('E-ENE-P90')}.",
    ]
    sections.append(
        MemoSection(
            key="asset_resource", title="2. Asset & Resource", markdown="\n\n".join(asset_lines)
        )
    )

    # 3. Revenue & Market
    rev_lines = [
        f"Year-one revenue is {ev.cite('E-REV-Y1')} with a wind capture rate of "
        f"{ev.cite('E-REV-CAPTURE')}.",
    ]
    if ev.has("E-ASM-AW"):
        rev_lines.append(f"The award value (anzulegender Wert) is {ev.cite('E-ASM-AW')}.")
    sections.append(
        MemoSection(
            key="revenue_market", title="3. Revenue & Market", markdown="\n\n".join(rev_lines)
        )
    )

    # 4. Financial Structure — code-built metrics table verbatim.
    sections.append(
        MemoSection(
            key="financial_structure",
            title="4. Financial Structure",
            markdown=metrics_table,
        )
    )

    # 5. Risks & Mitigants — claims, severity-ordered. Numeric-free headlines so
    # the section carries no uncited literals; the numbers live in the debate panel.
    order = {"dealbreaker": 0, "concern": 1, "info": 2}
    ranked = sorted(claims, key=lambda c: (order.get(c.severity, 3), c.id))
    risk_lines = []
    for c in ranked:
        if c.severity == "info":
            continue
        risk_lines.append(f"- **[{c.severity}]** {_risk_headline(c)}")
    failed = [g for g in gate_flags if not g.passed]
    for g in failed:
        risk_lines.append(
            f"- **[gate]** Compliance rule '{g.rule_id}' failed against its threshold."
        )
    if not risk_lines:
        risk_lines.append(
            "- No material risks: every compliance gate passed and no critic raised a concern."
        )
    sections.append(
        MemoSection(
            key="risks_mitigants", title="5. Risks & Mitigants", markdown="\n".join(risk_lines)
        )
    )

    # 6. Sensitivities — the P90 coverage is the headline sensitivity.
    sens = f"Under P90 energy the minimum DSCR moves to {ev.cite('E-VAL-P90-DSCR')}, the binding "
    sens += "downside for the debt sizing."
    sections.append(MemoSection(key="sensitivities", title="6. Sensitivities", markdown=sens))

    # 7. Conditions Precedent — one per concern/dealbreaker claim (numeric-free text).
    conditions: list[Condition] = []
    for c in ranked:
        if c.severity in ("concern", "dealbreaker"):
            conditions.append(
                Condition(
                    text=_condition_text(c),
                    claim_id=c.id,
                )
            )
    # Render text only — the claim_id link lives in the structured Condition
    # (a claim id like 'REV-3' would otherwise leak an uncited digit into prose).
    cond_md = (
        "\n".join(f"- {c.text}" for c in conditions)
        if conditions
        else "- None: the base case clears all gates without conditions."
    )
    sections.append(
        MemoSection(key="conditions_precedent", title="7. Conditions Precedent", markdown=cond_md)
    )

    # Appendix — key assumptions (each cited).
    appx = [
        f"WACC {ev.cite('E-ASM-WACC')}; equity hurdle {ev.cite('E-ASM-HURDLE')}; "
        f"senior rate {ev.cite('E-ASM-RATE')}.",
        "Rule-based memo: claims and prose are derived deterministically from the evidence "
        "store — no LLM was used. Figures trace to the citation seals.",
    ]
    sections.append(
        MemoSection(
            key="appendix_assumptions", title="Appendix: Assumptions", markdown="\n\n".join(appx)
        )
    )

    return Memo(
        verdict=verdict,
        thesis=thesis,
        sections=sections,
        conditions=conditions,
        metrics_table_md=metrics_table,
    )


def _risk_headline(claim: Claim) -> str:
    """Numeric-free one-line risk summary for the memo (the panel keeps the full,
    number-rich statement)."""
    headlines = {
        "RES-2": "Assumed availability may be optimistic for the fleet age — O&M reserve advised.",
        "RES-3": "Resource uncertainty is wide (atlas-based estimate); P90 sits well below P50.",
        "RES-4": "Gearbox-era turbine technology carries elevated spares and reliability risk.",
        "REV-1": "Wind capture rate reflects a material cannibalisation discount to baseload.",
        "REV-2": "Merchant exposure after the EEG support window is unhedged.",
        "REV-3": "The §51 negative-price rule erodes the premium and worsens as negative hours rise.",
        "REV-4": "A merchant tail follows the end of EEG support — a valuation swing factor.",
        "CRE-1": "Minimum DSCR breaches the sculpting covenant.",
        "CRE-2": "Debt coverage is thin or uncovered under the P90 resource downside.",
        "CRE-3": "Gearing is at the cap — debt capacity is leverage-limited.",
        "CRE-4": "Loan-life coverage is tight.",
    }
    if claim.id in headlines:
        return headlines[claim.id]
    if claim.id.startswith("CRE-GATE-"):
        return f"A deterministic compliance gate failed ({claim.id.removeprefix('CRE-GATE-')})."
    # Fallback: strip the statement of digits/percent to stay citation-free.
    import re as _re

    return _re.sub(r"[0-9]+(?:[.,][0-9]+)?\s*%?", "", claim.statement).replace("  ", " ").strip()


def _condition_text(claim: Claim) -> str:
    key = claim.id
    templates = {
        "RES-2": "Fund an availability/O&M reserve sized to the resource critic's downside.",
        "RES-3": "Obtain an independent (metered or Path-A) resource assessment before close.",
        "RES-4": "Secure a long-term full-service O&M and spares agreement for the fleet.",
        "REV-1": "Stress the capture-rate assumption in the base case and covenant sizing.",
        "REV-2": "Evaluate a PPA or hedge to cap merchant exposure after the support window.",
        "REV-3": "Model the §51 negative-hour drag under a rising-negative-hours scenario.",
        "REV-4": "Reserve for the merchant-tail years or shorten the debt tenor accordingly.",
        "CRE-1": "Re-size senior debt to restore covenant headroom before drawdown.",
        "CRE-2": "Add a cash sweep or larger DSRA to protect the P90 downside.",
        "CRE-3": "Confirm the gearing cap is acceptable to the credit committee.",
        "CRE-4": "Tighten the loan-life coverage through a shorter tenor or reserve.",
    }
    return templates.get(key, "Address the flagged item to the credit committee's satisfaction.")


def memo_to_markdown(memo: Memo) -> str:
    # Section 1 already carries the verdict + thesis, so no separate header block
    # (avoids repeating the thesis twice).
    parts: list[str] = []
    for s in memo.sections:
        parts.append(f"## {s.title}")
        parts.append(s.markdown)
    return "\n\n".join(p for p in parts if p.strip())


# ------------------------------------------------------------------- driver
async def _emit(on_event: Any, event_type: str, payload: dict[str, Any]) -> None:
    if on_event is None:
        return
    result = on_event(event_type, payload)
    if inspect.isawaitable(result):
        await result


async def run_offline_debate(
    evidence: Sequence[EvidenceItem],
    gate_flags: Sequence[GateFlag],
    on_event: Any = None,
    *,
    delay: float = 0.35,
) -> dict[str, Any]:
    """Deterministic debate that streams the same events as run_debate.

    delay: seconds between streamed items (set 0 for batch/showcase precompute).
    """
    ev = OfflineEvidence(evidence)

    def _clean(claims: list[Claim]) -> list[Claim]:
        # Drop any evidence id not in the store so no claim shows a broken seal.
        for c in claims:
            c.evidence_ids = [i for i in c.evidence_ids if ev.has(i)]
        return claims

    critic_fns = [
        ("resource", lambda: _clean(resource_claims(ev))),
        ("revenue", lambda: _clean(revenue_claims(ev))),
        ("credit", lambda: _clean(credit_claims(ev, gate_flags))),
    ]
    all_claims: list[Claim] = []
    for agent, fn in critic_fns:
        await _emit(
            on_event, "agent_status", {"agent": agent, "phase": "claims", "status": "running"}
        )
        if delay:
            await asyncio.sleep(delay)
        claims = fn()
        for c in claims:
            all_claims.append(c)
            await _emit(on_event, "claim", c.model_dump())
            if delay:
                await asyncio.sleep(delay * 0.5)
        await _emit(
            on_event,
            "agent_status",
            {"agent": agent, "phase": "claims", "status": "done", "n_claims": len(claims)},
        )

    # Rebuttal round
    rebuttals = build_rebuttals(all_claims, ev)
    if rebuttals:
        await _emit(
            on_event, "agent_status", {"agent": "credit", "phase": "rebuttals", "status": "running"}
        )
        for r in rebuttals:
            await _emit(on_event, "rebuttal", r.model_dump())
            if delay:
                await asyncio.sleep(delay)
        await _emit(
            on_event,
            "agent_status",
            {
                "agent": "credit",
                "phase": "rebuttals",
                "status": "done",
                "n_rebuttals": len(rebuttals),
            },
        )

    # Narrator (deterministic)
    await _emit(
        on_event, "agent_status", {"agent": "narrator", "phase": "memo", "status": "running"}
    )
    memo = build_offline_memo(ev, all_claims, gate_flags)
    markdown = memo_to_markdown(memo)

    # Stream the memo as deltas so the paper types itself in.
    if on_event is not None:
        for chunk in _chunks(markdown, 48):
            await _emit(on_event, "memo_delta", {"text": chunk})
            if delay:
                await asyncio.sleep(delay * 0.25)

    citable = [*all_claims, *rebuttals]
    validation = validate(markdown, evidence, citable, gate_flags, memo.verdict, memo.conditions)

    await _emit(on_event, "agent_status", {"agent": "narrator", "phase": "memo", "status": "done"})
    await _emit(on_event, "validation", validation)
    await _emit(
        on_event,
        "done",
        {
            "verdict": memo.verdict,
            "ok": validation["ok"],
            "n_claims": len(all_claims),
            "n_rebuttals": len(rebuttals),
            "mode": "offline",
        },
    )

    return {
        "claims": all_claims,
        "rebuttals": rebuttals,
        "memo": memo,
        "memo_markdown": markdown,
        "validation": validation,
        "mode": "offline",
    }


def _chunks(text: str, size: int) -> list[str]:
    return [text[i : i + size] for i in range(0, len(text), size)]
