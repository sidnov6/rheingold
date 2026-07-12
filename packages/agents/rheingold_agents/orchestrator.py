"""Debate orchestrator (spec §9.3): critics -> cross-examination -> narrator -> validator.

- anthropic AsyncAnthropic; model from env RHEINGOLD_MODEL (default 'claude-sonnet-4-6',
  spec §9.2 — verified as a current Anthropic model id at build time).
- temperature 0.2; max_tokens 1500 (critics) / 3000 (narrator).
- Critics run concurrently via asyncio.gather; structured outputs via forced tool_choice.
- Every model call retries once on schema violation with the validation error appended.
- After the narrator: run the citation validator; on failure regenerate once with the
  errors attached; on second failure the validation errors are RETURNED, never raised —
  the API layer surfaces them to the UI (§9.3 step 6).
- Events are emitted through on_event(type, payload) for SSE:
  agent_status, claim, rebuttal, memo_delta (narrator tool-json deltas), validation, done.
  The callback may be sync or async.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import os
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from pydantic import BaseModel, ValidationError
from rheingold_engine.models import EvidenceItem

from .critics import CRITICS, CriticDef, build_claims_prompt, build_rebuttals_prompt
from .narrator import build_metrics_table, build_narrator_prompt, narrator_system_prompt
from .providers import ToolSchemaError
from .schemas import (
    SUBMIT_CLAIMS_TOOL,
    SUBMIT_MEMO_TOOL,
    SUBMIT_REBUTTALS_TOOL,
    Claim,
    ClaimsSubmission,
    GateFlag,
    Memo,
    Rebuttal,
    RebuttalsSubmission,
)
from .validator import validate

DEFAULT_MODEL = "claude-sonnet-4-6"  # spec §9.2 pin; override via RHEINGOLD_MODEL
TEMPERATURE = 0.2
MAX_TOKENS_CRITIC = 1500
MAX_TOKENS_NARRATOR = 3000

#: SSE event callback. May be a plain function or a coroutine function.
OnEvent = Callable[[str, dict[str, Any]], Awaitable[None] | None]


class SchemaViolation(Exception):
    """The model's tool submission did not satisfy the expected schema."""


def _model_id() -> str:
    return os.environ.get("RHEINGOLD_MODEL", DEFAULT_MODEL)


async def _emit(on_event: OnEvent | None, event_type: str, payload: dict[str, Any]) -> None:
    if on_event is None:
        return
    result = on_event(event_type, payload)
    if inspect.isawaitable(result):
        await result


def _retry_prompt(prompt: str, tool_name: str, error: Exception) -> str:
    return (
        f"{prompt}\n\nYour previous submission failed schema validation:\n{error}\n"
        f"Call the {tool_name} tool again with corrected input."
    )


def _find_tool_use(content: Sequence[Any]) -> Any:
    for block in content:
        if getattr(block, "type", None) == "tool_use":
            return block
    return None


async def _call_tool(
    client: Any,
    *,
    system: str,
    prompt: str,
    tool: dict[str, Any],
    max_tokens: int,
    parse_model: type[BaseModel],
) -> BaseModel | None:
    """One forced-tool call; retry once on schema violation with the error appended."""

    async def once(user_prompt: str) -> BaseModel:
        response = await client.messages.create(
            model=_model_id(),
            max_tokens=max_tokens,
            temperature=TEMPERATURE,
            system=system,
            messages=[{"role": "user", "content": user_prompt}],
            tools=[tool],
            tool_choice={"type": "tool", "name": tool["name"]},
        )
        block = _find_tool_use(response.content)
        if block is None:
            raise SchemaViolation(f"response contained no {tool['name']} tool_use block")
        return parse_model.model_validate(block.input)

    try:
        return await once(prompt)
    except (ValidationError, SchemaViolation, ToolSchemaError) as first_error:
        try:
            return await once(_retry_prompt(prompt, tool["name"], first_error))
        except (ValidationError, SchemaViolation, ToolSchemaError):
            return None


async def _stream_memo_call(
    client: Any,
    *,
    system: str,
    prompt: str,
    on_event: OnEvent | None,
) -> tuple[Memo | None, str | None]:
    """One streaming forced-tool narrator call; retry once on schema violation.

    Emits memo_delta events with the partial tool-input JSON as it streams.
    Returns (memo, error_message).
    """

    async def once(user_prompt: str) -> Memo:
        stream = await client.messages.create(
            model=_model_id(),
            max_tokens=MAX_TOKENS_NARRATOR,
            temperature=TEMPERATURE,
            system=system,
            messages=[{"role": "user", "content": user_prompt}],
            tools=[SUBMIT_MEMO_TOOL],
            tool_choice={"type": "tool", "name": SUBMIT_MEMO_TOOL["name"]},
            stream=True,
        )
        chunks: list[str] = []
        async for event in stream:
            if getattr(event, "type", "") != "content_block_delta":
                continue
            delta = event.delta
            if getattr(delta, "type", "") == "input_json_delta":
                chunks.append(delta.partial_json)
                await _emit(on_event, "memo_delta", {"text": delta.partial_json})
        raw = "".join(chunks)
        if not raw:
            raise SchemaViolation("narrator stream produced no submit_memo tool input")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SchemaViolation(f"submit_memo input was not valid JSON: {exc}") from exc
        return Memo.model_validate(payload)

    try:
        return await once(prompt), None
    except (ValidationError, SchemaViolation, ToolSchemaError) as first_error:
        try:
            return await once(_retry_prompt(prompt, "submit_memo", first_error)), None
        except (ValidationError, SchemaViolation, ToolSchemaError) as second_error:
            return None, f"narrator failed schema validation twice: {second_error}"


def _memo_markdown(memo: Memo) -> str:
    parts = [f"## Recommendation: {memo.verdict}", memo.thesis]
    for section in memo.sections:
        parts.append(f"## {section.title}")
        parts.append(section.markdown)
    return "\n\n".join(p for p in parts if p.strip())


def _dedupe_claim_ids(claims: list[Claim]) -> None:
    seen: set[str] = set()
    for claim in claims:
        if claim.id in seen:
            claim.id = f"{claim.agent}:{claim.id}"
        seen.add(claim.id)


async def run_debate(
    evidence: Sequence[EvidenceItem],
    gate_flags: Sequence[GateFlag],
    on_event: OnEvent | None = None,
    *,
    client: Any | None = None,
) -> dict[str, Any]:
    """Run one full debate round and return claims, rebuttals, memo, and validation.

    Never raises validation problems past this function — a failed memo comes back as
    {"memo": ..., "validation": {"ok": False, "errors": [...]}} for the API to surface.
    """
    if client is None:  # pragma: no cover - exercised only with real credentials
        from .providers import make_client

        client = make_client()

    evidence_json = json.dumps(
        [e.model_dump(exclude_none=True) for e in evidence], ensure_ascii=False
    )
    gate_flags_json = json.dumps([g.model_dump() for g in gate_flags], ensure_ascii=False)

    # --- Step 3: critics, concurrent -------------------------------------------------
    async def run_critic(critic: CriticDef) -> list[Claim]:
        await _emit(
            on_event,
            "agent_status",
            {"agent": critic.agent, "phase": "claims", "status": "running"},
        )
        submission = await _call_tool(
            client,
            system=critic.system_prompt,
            prompt=build_claims_prompt(critic, evidence_json, gate_flags_json),
            tool=SUBMIT_CLAIMS_TOOL,
            max_tokens=MAX_TOKENS_CRITIC,
            parse_model=ClaimsSubmission,
        )
        claims: list[Claim] = (
            list(submission.claims) if isinstance(submission, ClaimsSubmission) else []
        )
        for claim in claims:
            claim.agent = critic.agent
            await _emit(on_event, "claim", claim.model_dump())
        await _emit(
            on_event,
            "agent_status",
            {
                "agent": critic.agent,
                "phase": "claims",
                "status": "done" if submission is not None else "error",
                "n_claims": len(claims),
            },
        )
        return claims

    # Concurrent by default (spec §9.2); sequential when the provider asks for it
    # (Groq free-tier TPM would otherwise 429 on a 3-critic burst).
    if getattr(client, "sequential_tools", False):
        claim_lists = [await run_critic(c) for c in CRITICS]
    else:
        claim_lists = await asyncio.gather(*(run_critic(c) for c in CRITICS))
    all_claims: list[Claim] = [c for claims in claim_lists for c in claims]
    _dedupe_claim_ids(all_claims)
    known_claim_ids = {c.id for c in all_claims}

    # --- Step 4: cross-examination (one round, up to 2 rebuttals each) ---------------
    async def run_rebuttals(critic: CriticDef) -> list[Rebuttal]:
        others = [c for c in all_claims if c.agent != critic.agent]
        if not others:
            return []
        await _emit(
            on_event,
            "agent_status",
            {"agent": critic.agent, "phase": "rebuttals", "status": "running"},
        )
        own = [c for c in all_claims if c.agent == critic.agent]
        submission = await _call_tool(
            client,
            system=critic.system_prompt,
            prompt=build_rebuttals_prompt(
                critic,
                evidence_json,
                json.dumps([c.model_dump() for c in own], ensure_ascii=False),
                json.dumps([c.model_dump() for c in others], ensure_ascii=False),
            ),
            tool=SUBMIT_REBUTTALS_TOOL,
            max_tokens=MAX_TOKENS_CRITIC,
            parse_model=RebuttalsSubmission,
        )
        rebuttals: list[Rebuttal] = []
        if isinstance(submission, RebuttalsSubmission):
            rebuttals = [r for r in submission.rebuttals if r.targets_claim_id in known_claim_ids]
            rebuttals = rebuttals[:2]
        for rebuttal in rebuttals:
            rebuttal.agent = critic.agent
            await _emit(on_event, "rebuttal", rebuttal.model_dump())
        await _emit(
            on_event,
            "agent_status",
            {
                "agent": critic.agent,
                "phase": "rebuttals",
                "status": "done" if submission is not None else "error",
                "n_rebuttals": len(rebuttals),
            },
        )
        return rebuttals

    if getattr(client, "sequential_tools", False):
        rebuttal_lists = [await run_rebuttals(c) for c in CRITICS]
    else:
        rebuttal_lists = await asyncio.gather(*(run_rebuttals(c) for c in CRITICS))
    all_rebuttals: list[Rebuttal] = [r for rebuttals in rebuttal_lists for r in rebuttals]

    # --- Steps 5-6: narrator, then citation validator (regenerate once on failure) ---
    metrics_table = build_metrics_table(evidence)
    narrator_prompt = build_narrator_prompt(
        evidence_json,
        json.dumps([c.model_dump() for c in all_claims], ensure_ascii=False),
        json.dumps([r.model_dump() for r in all_rebuttals], ensure_ascii=False),
        gate_flags_json,
        metrics_table,
    )
    citable_claims: list[Claim] = [*all_claims, *all_rebuttals]

    memo: Memo | None = None
    validation: dict[str, Any] = {"ok": False, "errors": []}
    prompt = narrator_prompt
    for attempt in range(2):
        await _emit(
            on_event,
            "agent_status",
            {"agent": "narrator", "phase": "memo", "status": "running", "attempt": attempt + 1},
        )
        memo, schema_error = await _stream_memo_call(
            client, system=narrator_system_prompt(), prompt=prompt, on_event=on_event
        )
        if memo is None:
            validation = {"ok": False, "errors": [schema_error or "narrator produced no memo"]}
            await _emit(
                on_event,
                "agent_status",
                {"agent": "narrator", "phase": "memo", "status": "error", "attempt": attempt + 1},
            )
            await _emit(on_event, "validation", validation)
            break

        memo.metrics_table_md = metrics_table  # section-4 table is code-built, always
        validation = validate(
            _memo_markdown(memo),
            evidence,
            citable_claims,
            gate_flags,
            memo.verdict,
            memo.conditions,
        )
        await _emit(
            on_event,
            "agent_status",
            {"agent": "narrator", "phase": "memo", "status": "done", "attempt": attempt + 1},
        )
        await _emit(on_event, "validation", validation)
        if validation["ok"]:
            break
        # Regenerate once with the citation-validator errors attached (§9.3 step 6).
        prompt = (
            f"{narrator_prompt}\n\nYour previous memo FAILED the citation-integrity "
            f"validator with these errors:\n"
            + "\n".join(f"- {e}" for e in validation["errors"])
            + "\nFix every error and submit the memo again via submit_memo."
        )

    result = {
        "claims": all_claims,
        "rebuttals": all_rebuttals,
        "memo": memo,
        "validation": validation,
    }
    await _emit(
        on_event,
        "done",
        {
            "verdict": memo.verdict if memo is not None else None,
            "ok": validation["ok"],
            "n_claims": len(all_claims),
            "n_rebuttals": len(all_rebuttals),
        },
    )
    return result
