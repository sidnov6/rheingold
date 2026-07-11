"""RHEINGOLD agent layer (spec §9): critics, narrator, compliance gate, citation validator.

The agents never compute and never fetch. They read a frozen EvidenceStore built by
the deterministic engine, argue about it, and write. Compliance is code, not vibes.
"""

from .compliance_gate import DEALBREAKER_GATES
from .compliance_gate import run as run_compliance_gate
from .critics import CREDIT_CRITIC, CRITICS, RESOURCE_CRITIC, REVENUE_CRITIC, CriticDef
from .narrator import MEMO_SECTIONS, build_metrics_table
from .orchestrator import DEFAULT_MODEL, run_debate
from .schemas import (
    SUBMIT_CLAIMS_TOOL,
    SUBMIT_MEMO_TOOL,
    SUBMIT_REBUTTALS_TOOL,
    Claim,
    ClaimsSubmission,
    Condition,
    GateFlag,
    Memo,
    MemoSection,
    Rebuttal,
    RebuttalsSubmission,
)
from .validator import validate

__all__ = [
    "CREDIT_CRITIC",
    "CRITICS",
    "DEALBREAKER_GATES",
    "DEFAULT_MODEL",
    "MEMO_SECTIONS",
    "RESOURCE_CRITIC",
    "REVENUE_CRITIC",
    "SUBMIT_CLAIMS_TOOL",
    "SUBMIT_MEMO_TOOL",
    "SUBMIT_REBUTTALS_TOOL",
    "Claim",
    "ClaimsSubmission",
    "Condition",
    "CriticDef",
    "GateFlag",
    "Memo",
    "MemoSection",
    "Rebuttal",
    "RebuttalsSubmission",
    "build_metrics_table",
    "run_compliance_gate",
    "run_debate",
    "validate",
]
