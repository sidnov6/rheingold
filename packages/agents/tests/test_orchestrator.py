"""Orchestrator tests (spec §9.3) with a MOCKED anthropic client.

No network, no API key: the stub returns canned tool_use blocks / stream events.
Covers the retry-on-schema-violation path, the narrator regeneration-on-validation-
failure path, and event emission order. All values are synthetic test fixtures.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace as NS

import pytest
from rheingold_agents.narrator import build_metrics_table
from rheingold_agents.orchestrator import run_debate
from rheingold_agents.schemas import GateFlag
from rheingold_engine.models import EvidenceItem

EVIDENCE = [
    EvidenceItem(id="E-DSCR-MIN", type="computed", label="Minimum DSCR", value=1.32, unit="×"),
]
GATE_FLAGS = [GateFlag(rule_id="min_dscr", passed=True, value=1.32, threshold=1.15)]


# --- stub anthropic client ---------------------------------------------------------------


class StubMessages:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        assert self._responses, "stub ran out of canned responses"
        item = self._responses.pop(0)
        if kwargs.get("stream"):
            return _agen(item)
        return item


async def _agen(items):
    for item in items:
        yield item


class StubClient:
    def __init__(self, responses):
        self.messages = StubMessages(responses)


def tool_use_response(input_dict, name):
    return NS(
        content=[
            NS(type="text", text="submitting"),
            NS(type="tool_use", id="tu_1", name=name, input=input_dict),
        ],
        stop_reason="tool_use",
    )


def claim(agent, cid, evidence_ids=("E-DSCR-MIN",), severity="concern"):
    return {
        "id": cid,
        "agent": agent,
        "statement": f"{agent} statement grounded in evidence.",
        "evidence_ids": list(evidence_ids),
        "severity": severity,
        "confidence": 0.8,
    }


def claims_response(agent, cid):
    return tool_use_response({"claims": [claim(agent, cid)]}, "submit_claims")


def rebuttals_response(rebuttals):
    return tool_use_response({"rebuttals": rebuttals}, "submit_rebuttals")


VALID_MEMO = {
    "verdict": "PROCEED_WITH_CONDITIONS",
    "thesis": "Minimum DSCR of 1.32× [E:E-DSCR-MIN] supports lending with conditions.",
    "sections": [
        {
            "key": "recommendation",
            "title": "1. Recommendation",
            "markdown": "Coverage at 1.32× [E:E-DSCR-MIN] is adequate for the structure.",
        }
    ],
    "conditions": [{"text": "Obtain an availability warranty.", "claim_id": "RES-1"}],
    "metrics_table_md": "",
}


def memo_stream_events(memo: dict, n_chunks: int = 4) -> list[NS]:
    raw = json.dumps(memo, ensure_ascii=False)
    events = [
        NS(type="message_start"),
        NS(
            type="content_block_start",
            index=0,
            content_block=NS(type="tool_use", id="tu_memo", name="submit_memo"),
        ),
    ]
    size = max(1, len(raw) // n_chunks)
    for i in range(0, len(raw), size):
        events.append(
            NS(
                type="content_block_delta",
                index=0,
                delta=NS(type="input_json_delta", partial_json=raw[i : i + size]),
            )
        )
    events.append(NS(type="content_block_stop", index=0))
    events.append(NS(type="message_stop"))
    return events


def happy_path_responses():
    return [
        claims_response("resource", "RES-1"),
        claims_response("revenue", "REV-1"),
        claims_response("credit", "CRD-1"),
        rebuttals_response([]),  # resource
        rebuttals_response([]),  # revenue
        rebuttals_response(  # credit rebuts the resource claim
            [{**claim("credit", "CRD-R1", severity="info"), "targets_claim_id": "RES-1"}]
        ),
        memo_stream_events(VALID_MEMO),
    ]


def run(client, on_event=None):
    return asyncio.run(run_debate(EVIDENCE, GATE_FLAGS, on_event, client=client))


# --- tests -------------------------------------------------------------------------------


def test_happy_path_result_and_call_params(monkeypatch):
    monkeypatch.delenv("RHEINGOLD_MODEL", raising=False)
    client = StubClient(happy_path_responses())
    result = run(client)

    assert [c.id for c in result["claims"]] == ["RES-1", "REV-1", "CRD-1"]
    assert [r.targets_claim_id for r in result["rebuttals"]] == ["RES-1"]
    assert result["memo"].verdict == "PROCEED_WITH_CONDITIONS"
    assert result["memo"].metrics_table_md == build_metrics_table(EVIDENCE)
    assert result["validation"] == {"ok": True, "errors": []}

    calls = client.messages.calls
    assert len(calls) == 7  # 3 critics + 3 rebuttal rounds + 1 narrator
    for call in calls:
        assert call["model"] == "claude-sonnet-4-6"  # spec §9.2 default, env-overridable
        assert call["temperature"] == 0.2
        assert call["tool_choice"]["type"] == "tool"
    assert all(c["max_tokens"] == 1500 for c in calls[:6])
    assert calls[6]["max_tokens"] == 3000
    assert calls[6]["stream"] is True
    assert calls[6]["tool_choice"]["name"] == "submit_memo"
    assert {c["tool_choice"]["name"] for c in calls[:3]} == {"submit_claims"}
    assert {c["tool_choice"]["name"] for c in calls[3:6]} == {"submit_rebuttals"}


def test_model_env_override(monkeypatch):
    monkeypatch.setenv("RHEINGOLD_MODEL", "claude-test-model")
    client = StubClient(happy_path_responses())
    run(client)
    assert {c["model"] for c in client.messages.calls} == {"claude-test-model"}


def test_event_emission_order(monkeypatch):
    monkeypatch.delenv("RHEINGOLD_MODEL", raising=False)
    events: list[tuple[str, dict]] = []

    async def on_event(event_type, payload):  # async callback, as the SSE layer uses
        events.append((event_type, payload))

    client = StubClient(happy_path_responses())
    run(client, on_event)

    types = [t for t, _ in events]
    # Phases appear in protocol order.
    assert types[0] == "agent_status"
    assert types[-1] == "done"
    assert types[-2] == "validation"
    assert types.count("claim") == 3
    assert types.count("rebuttal") == 1
    assert types.count("memo_delta") >= 2
    assert types.index("claim") < types.index("rebuttal")
    assert types.index("rebuttal") < types.index("memo_delta")
    assert types.index("memo_delta") < types.index("validation")

    # Per-critic claim phase: running -> claim -> done.
    resource_statuses = [
        p["status"]
        for t, p in events
        if t == "agent_status" and p.get("agent") == "resource" and p.get("phase") == "claims"
    ]
    assert resource_statuses == ["running", "done"]

    # memo_delta payloads reassemble to the submitted memo JSON.
    raw = "".join(p["text"] for t, p in events if t == "memo_delta")
    assert json.loads(raw)["verdict"] == "PROCEED_WITH_CONDITIONS"

    # done payload summarises the run.
    done_payload = events[-1][1]
    assert done_payload == {
        "verdict": "PROCEED_WITH_CONDITIONS",
        "ok": True,
        "n_claims": 3,
        "n_rebuttals": 1,
    }


def test_retry_on_schema_violation(monkeypatch):
    monkeypatch.delenv("RHEINGOLD_MODEL", raising=False)
    bad = tool_use_response(
        {"claims": [{**claim("resource", "RES-1"), "severity": "fatal"}]},  # invalid literal
        "submit_claims",
    )
    responses = [bad, *happy_path_responses()]  # retry consumes the good RES-1 response next
    client = StubClient(responses)
    result = run(client)

    calls = client.messages.calls
    assert len(calls) == 8  # one extra call for the retry
    retry_prompt = calls[1]["messages"][0]["content"]
    assert "failed schema validation" in retry_prompt
    assert "submit_claims" in retry_prompt
    # The corrected submission made it through.
    assert [c.id for c in result["claims"]] == ["RES-1", "REV-1", "CRD-1"]
    assert result["validation"]["ok"] is True


def test_critic_dropped_after_second_schema_violation(monkeypatch):
    monkeypatch.delenv("RHEINGOLD_MODEL", raising=False)
    bad = tool_use_response({"claims": [{"id": "RES-1"}]}, "submit_claims")  # missing fields
    responses = [
        bad,
        bad,  # retry also fails -> resource critic yields no claims
        claims_response("revenue", "REV-1"),
        claims_response("credit", "CRD-1"),
        rebuttals_response([]),  # resource still cross-examines others' claims
        rebuttals_response([]),
        rebuttals_response([]),
        memo_stream_events(
            {**VALID_MEMO, "conditions": [{"text": "Refresh price data.", "claim_id": "REV-1"}]}
        ),
    ]
    client = StubClient(responses)
    result = run(client)
    assert [c.id for c in result["claims"]] == ["REV-1", "CRD-1"]
    assert result["validation"]["ok"] is True


def test_narrator_regenerates_once_on_validation_failure(monkeypatch):
    monkeypatch.delenv("RHEINGOLD_MODEL", raising=False)
    fabricated = {
        **VALID_MEMO,
        "thesis": "Minimum DSCR of 1.99× [E:E-DSCR-MIN] supports lending.",  # fabricated number
    }
    responses = [
        claims_response("resource", "RES-1"),
        claims_response("revenue", "REV-1"),
        claims_response("credit", "CRD-1"),
        rebuttals_response([]),
        rebuttals_response([]),
        rebuttals_response([]),
        memo_stream_events(fabricated),
        memo_stream_events(VALID_MEMO),
    ]
    events: list[tuple[str, dict]] = []
    client = StubClient(responses)
    result = run(client, lambda t, p: events.append((t, p)))

    validations = [p for t, p in events if t == "validation"]
    assert len(validations) == 2
    assert validations[0]["ok"] is False
    assert any("1.99" in e for e in validations[0]["errors"])
    assert validations[1] == {"ok": True, "errors": []}

    # Second narrator call carries the validator errors.
    narrator_calls = [c for c in client.messages.calls if c.get("stream")]
    assert len(narrator_calls) == 2
    regen_prompt = narrator_calls[1]["messages"][0]["content"]
    assert "FAILED the citation-integrity" in regen_prompt
    assert "1.99" in regen_prompt

    assert result["validation"]["ok"] is True
    assert result["memo"].thesis.startswith("Minimum DSCR of 1.32×")


def test_validation_errors_returned_not_raised_after_second_failure(monkeypatch):
    monkeypatch.delenv("RHEINGOLD_MODEL", raising=False)
    fabricated = {
        **VALID_MEMO,
        "thesis": "Minimum DSCR of 1.99× [E:E-DSCR-MIN] supports lending.",
    }
    responses = [
        claims_response("resource", "RES-1"),
        claims_response("revenue", "REV-1"),
        claims_response("credit", "CRD-1"),
        rebuttals_response([]),
        rebuttals_response([]),
        rebuttals_response([]),
        memo_stream_events(fabricated),
        memo_stream_events(fabricated),  # regeneration fails the same way
    ]
    client = StubClient(responses)
    result = run(client)  # must not raise (§9.3 step 6: API surfaces the errors)
    assert result["validation"]["ok"] is False
    assert any("1.99" in e for e in result["validation"]["errors"])
    assert result["memo"] is not None  # the failing memo is still returned for the amber UI state


def test_invalid_rebuttal_target_is_dropped(monkeypatch):
    monkeypatch.delenv("RHEINGOLD_MODEL", raising=False)
    responses = happy_path_responses()
    responses[5] = rebuttals_response(
        [{**claim("credit", "CRD-R1", severity="info"), "targets_claim_id": "GHOST-1"}]
    )
    client = StubClient(responses)
    result = run(client)
    assert result["rebuttals"] == []
    assert result["validation"]["ok"] is True


@pytest.mark.parametrize("verdict", ["PROCEED", "DECLINE"])
def test_memo_verdict_passthrough(monkeypatch, verdict):
    monkeypatch.delenv("RHEINGOLD_MODEL", raising=False)
    memo = {**VALID_MEMO, "verdict": verdict}
    responses = happy_path_responses()
    responses[6] = memo_stream_events(memo)
    client = StubClient(responses)
    result = run(client)
    assert result["memo"].verdict == verdict
    assert result["validation"]["ok"] is True  # min_dscr gate passed, so PROCEED is allowed
