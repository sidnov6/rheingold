"""Structured-output pydantic models + Anthropic tool schemas for the agent layer (spec §9).

The agents never compute and never fetch: they read a frozen EvidenceStore, argue
about it via these schemas, and write. Tool schemas below are derived from the
pydantic models so the API contract and the parse contract cannot drift apart.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Severity = Literal["info", "concern", "dealbreaker"]
Verdict = Literal["PROCEED", "PROCEED_WITH_CONDITIONS", "DECLINE"]


class Claim(BaseModel):
    """One critic claim (§9.3 step 3). evidence_ids may only reference existing ids."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Short unique claim id, e.g. 'RES-1'")
    agent: str = Field(description="Agent name: 'resource' | 'revenue' | 'credit'")
    statement: str = Field(description="One-sentence claim grounded in the cited evidence")
    evidence_ids: list[str] = Field(
        description="Ids of EvidenceStore items backing this claim. Inventing an id is a hard failure."
    )
    severity: Severity
    confidence: float = Field(ge=0.0, le=1.0)


class Rebuttal(Claim):
    """Cross-examination rebuttal (§9.3 step 4): a Claim that targets another claim."""

    targets_claim_id: str = Field(description="Id of the claim being rebutted")


class GateFlag(BaseModel):
    """Deterministic compliance-gate result (§9.4). Produced by code, never an LLM."""

    rule_id: str
    passed: bool
    value: float | None = None
    threshold: float


class MemoSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(description="Stable section key, e.g. 'risks_mitigants'")
    title: str
    markdown: str = Field(description="Section body. Every numeric literal needs an [E:ID] citation.")


class Condition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    claim_id: str = Field(description="Id of the claim this condition addresses")


class Memo(BaseModel):
    """The IC memo (§9.7 fixed structure, filled by the narrator)."""

    model_config = ConfigDict(extra="forbid")

    verdict: Verdict
    thesis: str = Field(description="3-sentence recommendation thesis with [E:ID] citations")
    sections: list[MemoSection]
    conditions: list[Condition] = Field(default_factory=list)
    metrics_table_md: str = Field(
        default="",
        description="Section-4 metrics table. Built by code from evidence; do not invent rows.",
    )


class ClaimsSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claims: list[Claim]


class RebuttalsSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rebuttals: list[Rebuttal] = Field(default_factory=list, max_length=2)


def _tool(name: str, description: str, model: type[BaseModel]) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "input_schema": model.model_json_schema(),
    }


SUBMIT_CLAIMS_TOOL: dict[str, Any] = _tool(
    "submit_claims",
    "Submit your claims about this deal. Each claim must cite only existing evidence ids.",
    ClaimsSubmission,
)

SUBMIT_REBUTTALS_TOOL: dict[str, Any] = _tool(
    "submit_rebuttals",
    "Submit up to 2 rebuttals against other critics' claims. Cite only existing evidence ids "
    "and target only listed claim ids. Submit an empty list if you have no rebuttals.",
    RebuttalsSubmission,
)

SUBMIT_MEMO_TOOL: dict[str, Any] = _tool(
    "submit_memo",
    "Submit the final investment-committee memo with the fixed section structure.",
    Memo,
)
