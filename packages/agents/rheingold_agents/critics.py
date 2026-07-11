"""Critic definitions (spec §9.1) and the cross-examination round (§9.3 step 4).

Three critics — resource / revenue / credit — each read the frozen EvidenceStore
plus the deterministic gate flags and produce claims via the `submit_claims` tool.
In the cross-examination round each critic receives the other two critics' claims
and may submit up to 2 rebuttals via `submit_rebuttals`.

The critics never compute and never fetch. Prompts state the hard rule: they may
ONLY reference existing evidence ids — inventing an id is a hard failure that the
citation validator (§9.6) will reject.
"""

from __future__ import annotations

from dataclasses import dataclass

_COMMON_RULES = """\
Hard rules — violations are rejected by a deterministic validator, not a person:
- You may ONLY reference evidence ids that exist in the EVIDENCE JSON you were given.
  Inventing, guessing, or mutating an id is a hard failure.
- You never compute new numbers and you never fetch data. Every quantitative statement
  must be traceable to the cited evidence items.
- Prefix your claim ids with '{id_prefix}' (e.g. '{id_prefix}1', '{id_prefix}2').
- Severity scale: 'info' (context worth recording), 'concern' (needs a mitigant or
  condition), 'dealbreaker' (would justify DECLINE on its own).
- confidence is your subjective probability (0..1) that the claim holds.
- Submit 2 to 5 claims via the submit_claims tool. Respond ONLY with the tool call."""


@dataclass(frozen=True)
class CriticDef:
    agent: str  # "resource" | "revenue" | "credit"
    display_name: str
    id_prefix: str
    system_prompt: str


def _system(agent: str, display_name: str, id_prefix: str, focus: str) -> str:
    return (
        f"You are the {display_name} on a German onshore-wind project-finance "
        f"investment committee (agent name: '{agent}').\n\n"
        f"Your remit: {focus}\n\n" + _COMMON_RULES.format(id_prefix=id_prefix)
    )


RESOURCE_CRITIC = CriticDef(
    agent="resource",
    display_name="Resource Critic",
    id_prefix="RES-",
    system_prompt=_system(
        "resource",
        "Resource Critic",
        "RES-",
        "energy evidence, the P50/P90 uncertainty stack, and turbine/vintage facts. "
        "You judge P50 credibility, availability realism (is 97% defensible for this "
        "fleet age and manufacturer?), and technology risk — an old Senvion fleet or "
        "gearbox-era machines carry different failure and O&M profiles than modern "
        "direct-drive turbines.",
    ),
)

REVENUE_CRITIC = CriticDef(
    agent="revenue",
    display_name="Revenue Critic",
    id_prefix="REV-",
    system_prompt=_system(
        "revenue",
        "Revenue Critic",
        "REV-",
        "the revenue stack, capture rates, §51 negative-price losses, and Marktwert "
        "history. You judge merchant exposure, the negative-hour trend risk as wind "
        "penetration rises, and the EEG cliff at year 20 when the market premium ends "
        "and the project falls to merchant capture prices.",
    ),
)

CREDIT_CRITIC = CriticDef(
    agent="credit",
    display_name="Credit Critic",
    id_prefix="CRD-",
    system_prompt=_system(
        "credit",
        "Credit Critic",
        "CRD-",
        "the sculpted debt schedule, DSCR/LLCR/PLCR, gate flags, and scenario results. "
        "You judge covenant headroom, break-even robustness, gearing-cap pressure, and "
        "sculpting fragility (back-loaded CFADS, refinancing exposure, DSRA adequacy).",
    ),
)

CRITICS: tuple[CriticDef, ...] = (RESOURCE_CRITIC, REVENUE_CRITIC, CREDIT_CRITIC)

_REBUTTAL_RULES = """\
Cross-examination round. You have received the other critics' claims.
- You may submit AT MOST 2 rebuttals via the submit_rebuttals tool; submit an empty
  list if nothing warrants a rebuttal.
- Each rebuttal must set targets_claim_id to one of the listed claim ids — targeting
  a claim id that is not listed is a hard failure.
- The same evidence rules apply: cite only existing evidence ids; never compute.
- Rebut only where the evidence genuinely undercuts or reframes the claim. Do not
  rebut for the sake of it. Respond ONLY with the tool call."""


def build_claims_prompt(critic: CriticDef, evidence_json: str, gate_flags_json: str) -> str:
    return (
        f"EVIDENCE (frozen EvidenceStore — the only ids you may cite):\n{evidence_json}\n\n"
        f"COMPLIANCE GATE FLAGS (deterministic, computed by code):\n{gate_flags_json}\n\n"
        f"As the {critic.display_name}, submit your claims about this deal via the "
        f"submit_claims tool. Set agent='{critic.agent}' on every claim."
    )


def build_rebuttals_prompt(
    critic: CriticDef,
    evidence_json: str,
    own_claims_json: str,
    other_claims_json: str,
) -> str:
    return (
        f"EVIDENCE (frozen EvidenceStore — the only ids you may cite):\n{evidence_json}\n\n"
        f"YOUR OWN CLAIMS (for context, do not rebut these):\n{own_claims_json}\n\n"
        f"OTHER CRITICS' CLAIMS (rebuttable — targets_claim_id must be one of these ids):\n"
        f"{other_claims_json}\n\n"
        f"{_REBUTTAL_RULES}\n\n"
        f"Set agent='{critic.agent}' on every rebuttal and prefix rebuttal ids with "
        f"'{critic.id_prefix}R'."
    )
