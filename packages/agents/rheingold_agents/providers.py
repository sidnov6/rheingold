"""LLM provider selection (deployment fallback; MODEL_CARD 'Agent layer limits').

Default (spec §9.2): the Anthropic SDK, model claude-sonnet-4-6, selected when
ANTHROPIC_API_KEY is set. Deployment fallback: when only GROQ_API_KEY is set,
an OpenAI-compatible endpoint (Groq) is wrapped in an adapter that mimics the
exact slice of the Anthropic messages API the orchestrator uses — forced tool
calls and input_json_delta streaming — so orchestrator.py stays provider-blind.
The citation-integrity validator (§9.6) gates output quality identically on
both paths.
"""

from __future__ import annotations

import asyncio
import os
import re
from dataclasses import dataclass
from typing import Any

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
# llama-3.3-70b follows JSON tool schemas more tightly than gpt-oss under Groq's
# server-side tool-call validation. Override with RHEINGOLD_GROQ_MODEL.
DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"


class ProviderNotConfigured(RuntimeError):
    pass


class ToolSchemaError(RuntimeError):
    """Groq rejected a tool call server-side (400 tool_use_failed). Retryable:
    the orchestrator appends this message and re-prompts, same as an Anthropic
    schema violation."""


def make_client() -> Any:
    """AsyncAnthropic when ANTHROPIC_API_KEY is set; else the Groq adapter."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        import anthropic

        return anthropic.AsyncAnthropic()
    if os.environ.get("GROQ_API_KEY"):
        return GroqAnthropicAdapter(
            model=os.environ.get("RHEINGOLD_GROQ_MODEL", DEFAULT_GROQ_MODEL)
        )
    raise ProviderNotConfigured(
        "memo generation needs ANTHROPIC_API_KEY (default) or GROQ_API_KEY (fallback) in the "
        "environment"
    )


def provider_name() -> str:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.environ.get("GROQ_API_KEY"):
        return "groq"
    return "none"


# --------------------------------------------------------------- adapter shapes
@dataclass
class _ToolUseBlock:
    type: str
    name: str
    input: dict[str, Any]


@dataclass
class _Response:
    content: list[_ToolUseBlock]


@dataclass
class _InputJsonDelta:
    type: str
    partial_json: str


@dataclass
class _StreamEvent:
    type: str
    delta: _InputJsonDelta


_MAX_RATE_RETRIES = 4


def _rate_limit_wait(exc: Exception) -> float | None:
    """Seconds to wait for a 429, or None if this isn't a rate-limit error."""
    if getattr(exc, "status_code", None) != 429 and type(exc).__name__ != "RateLimitError":
        return None
    body = getattr(exc, "body", None)
    msg = body.get("error", {}).get("message", "") if isinstance(body, dict) else str(exc)
    m = re.search(r"try again in ([\d.]+)s", msg)
    return min(float(m.group(1)) + 1.0, 65.0) if m else 20.0


def _as_tool_error(exc: Exception) -> Exception:
    """Convert Groq's server-side tool-call rejection into a retryable ToolSchemaError.

    Groq validates tool arguments against the schema and returns HTTP 400 with
    code 'tool_use_failed' plus the exact validation message (e.g. "missing
    properties: 'statement', 'evidence_ids'") — far more useful to feed back
    than a generic error. Anything else propagates unchanged.
    """
    body = getattr(exc, "body", None)
    err = body.get("error", {}) if isinstance(body, dict) else {}
    if err.get("code") == "tool_use_failed":
        return ToolSchemaError(err.get("message", "tool call did not match schema"))
    return exc


def _to_openai_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t["input_schema"],
            },
        }
        for t in tools
    ]


class _Messages:
    def __init__(self, adapter: GroqAnthropicAdapter) -> None:
        self._a = adapter

    async def create(
        self,
        *,
        model: str,  # ignored — the adapter pins its own model
        max_tokens: int,
        temperature: float,
        system: str,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]],
        tool_choice: dict[str, Any],
        stream: bool = False,
    ) -> Any:
        del model
        oai_messages = [{"role": "system", "content": system}, *messages]
        kwargs: dict[str, Any] = {
            "model": self._a.model,
            "max_completion_tokens": max_tokens,
            "temperature": temperature,
            "messages": oai_messages,
            "tools": _to_openai_tools(tools),
            "tool_choice": {"type": "function", "function": {"name": tool_choice["name"]}},
        }
        if not stream:
            response = await self._create_with_backoff(kwargs)
            return _Response(content=self._blocks_from(response))
        return await self._stream(kwargs)

    async def _create_with_backoff(self, kwargs: dict[str, Any], stream: bool = False) -> Any:
        """Groq free-tier TPM limits are tight; honour 429 Retry-After and retry."""
        for attempt in range(_MAX_RATE_RETRIES):
            try:
                return await self._a.client.chat.completions.create(stream=stream, **kwargs)
            except Exception as exc:  # noqa: BLE001
                wait = _rate_limit_wait(exc)
                if wait is None or attempt == _MAX_RATE_RETRIES - 1:
                    raise _as_tool_error(exc) from exc
                await asyncio.sleep(wait)
        raise RuntimeError("unreachable")  # pragma: no cover

    def _blocks_from(self, response: Any) -> list[_ToolUseBlock]:
        import json as _json

        blocks: list[_ToolUseBlock] = []
        choice = response.choices[0]
        for call in choice.message.tool_calls or []:
            try:
                args = _json.loads(call.function.arguments or "{}")
            except ValueError:
                continue
            blocks.append(_ToolUseBlock(type="tool_use", name=call.function.name, input=args))
        return blocks

    async def _stream(self, kwargs: dict[str, Any]) -> Any:
        """Async iterator of Anthropic-shaped input_json_delta events."""
        response = await self._create_with_backoff(kwargs, stream=True)

        async def gen():
            async for chunk in response:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                for call in delta.tool_calls or []:
                    fragment = getattr(call.function, "arguments", None) if call.function else None
                    if fragment:
                        yield _StreamEvent(
                            type="content_block_delta",
                            delta=_InputJsonDelta(type="input_json_delta", partial_json=fragment),
                        )

        return gen()


class GroqAnthropicAdapter:
    """The slice of AsyncAnthropic that orchestrator.py touches, backed by Groq."""

    #: Free-tier TPM is tight — the orchestrator runs critics sequentially when set.
    sequential_tools = True

    def __init__(self, model: str) -> None:
        from openai import AsyncOpenAI

        self.model = model
        self.client = AsyncOpenAI(base_url=GROQ_BASE_URL, api_key=os.environ["GROQ_API_KEY"])
        self.messages = _Messages(self)
