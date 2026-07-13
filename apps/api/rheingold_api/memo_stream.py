"""SSE memo stream (spec §10): underwrite → compliance gate → run_debate events.

Event contract (sse-starlette): the orchestrator's on_event types pass through
verbatim — agent_status, claim, rebuttal, memo_delta, validation, done — plus a
service-level 'error' event (missing API key, missing data, engine failure).
The debate runs as a task; its events flow through an asyncio.Queue so the SSE
generator yields them as they happen.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import anyio
from fastapi import HTTPException
from rheingold_agents import compliance_gate
from rheingold_agents.offline import run_offline_debate
from rheingold_agents.orchestrator import run_debate
from rheingold_agents.providers import provider_name

from . import deps, market

if TYPE_CHECKING:  # avoid a runtime circular import with routes.py
    from .routes import UnderwriteRequest

_QUEUE_END = object()


def _sse(event: str, payload: dict[str, Any]) -> dict[str, str]:
    return {"event": event, "data": json.dumps(payload, ensure_ascii=False, default=str)}


async def memo_event_stream(body: UnderwriteRequest) -> AsyncIterator[dict[str, str]]:
    # No LLM key? The committee still drafts — a deterministic, rule-based debate
    # (spec §15 zero-API demo) runs instead, streaming the same events so the panel
    # and paper animate identically. An LLM provider, when present, takes priority.
    offline = provider_name() == "none"

    from .routes import build_underwrite  # deferred: routes imports this module

    # --- deterministic part: underwrite + compliance gate ---------------------------
    try:
        result = await anyio.to_thread.run_sync(build_underwrite, body)
        cur = deps.get_conn()
        v = market.vintages(cur)
        gate_flags = compliance_gate.run(
            result,
            as_of=datetime.now(UTC).date(),
            latest_price_date=v["prices_max_ts"],
            latest_marktwert_month=v["marktwerte_max_month"],
        )
    except HTTPException as exc:
        yield _sse("error", {"message": str(exc.detail), "status": exc.status_code})
        return
    except Exception as exc:  # noqa: BLE001 — stream errors, never half-close silently
        yield _sse("error", {"message": f"underwrite/gate failed: {exc}"})
        return

    yield _sse(
        "gate",
        {
            "flags": [f.model_dump() for f in gate_flags],
            "farm_id": result.farm.farm_id,
            "mode": "offline" if offline else "llm",
        },
    )

    # --- agent debate: pump orchestrator events through a queue ---------------------
    queue: asyncio.Queue[Any] = asyncio.Queue()

    async def on_event(event_type: str, payload: dict[str, Any]) -> None:
        await queue.put((event_type, payload))

    async def run() -> None:
        try:
            if offline:
                await run_offline_debate(result.evidence, gate_flags, on_event)
            else:
                try:
                    await run_debate(result.evidence, gate_flags, on_event)
                except Exception as exc:  # noqa: BLE001 — LLM provider failed (rate limit, etc.)
                    # Safety net: the committee still drafts. Fall back to the
                    # deterministic offline debate so a memo always completes.
                    await queue.put(
                        (
                            "agent_status",
                            {
                                "agent": "narrator",
                                "phase": "memo",
                                "status": "running",
                                "note": f"LLM unavailable ({str(exc)[:80]}); using rule-based debate",
                            },
                        )
                    )
                    await run_offline_debate(result.evidence, gate_flags, on_event)
        except Exception as exc:  # noqa: BLE001 — even the offline path failed
            await queue.put(("error", {"message": f"memo generation failed: {exc}"}))
        finally:
            await queue.put(_QUEUE_END)

    task = asyncio.create_task(run())
    try:
        while True:
            item = await queue.get()
            if item is _QUEUE_END:
                break
            event_type, payload = item
            yield _sse(event_type, payload)
    finally:
        if not task.done():
            task.cancel()
