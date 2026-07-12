"""Provider-selection + Groq adapter tests (no network)."""

import pytest
from rheingold_agents import providers
from rheingold_agents.providers import (
    ProviderNotConfigured,
    ToolSchemaError,
    _as_tool_error,
    _rate_limit_wait,
    _to_openai_tools,
    provider_name,
)


def test_provider_name_prefers_anthropic(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-x")
    monkeypatch.setenv("GROQ_API_KEY", "gsk-y")
    assert provider_name() == "anthropic"


def test_provider_name_groq_fallback(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "gsk-y")
    assert provider_name() == "groq"


def test_provider_name_none(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    assert provider_name() == "none"


def test_make_client_unconfigured_raises(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(ProviderNotConfigured):
        providers.make_client()


def test_groq_adapter_construction(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "gsk-test")
    client = providers.make_client()
    assert client.__class__.__name__ == "GroqAnthropicAdapter"
    assert client.sequential_tools is True
    assert client.model == providers.DEFAULT_GROQ_MODEL
    assert hasattr(client.messages, "create")


def test_groq_model_override(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "gsk-test")
    monkeypatch.setenv("RHEINGOLD_GROQ_MODEL", "openai/gpt-oss-120b")
    assert providers.make_client().model == "openai/gpt-oss-120b"


def test_tool_schema_translation():
    anthropic_tool = {
        "name": "submit_claims",
        "description": "submit the claims",
        "input_schema": {"type": "object", "properties": {"claims": {"type": "array"}}},
    }
    [oai] = _to_openai_tools([anthropic_tool])
    assert oai["type"] == "function"
    assert oai["function"]["name"] == "submit_claims"
    assert oai["function"]["parameters"] == anthropic_tool["input_schema"]


def test_tool_use_failed_becomes_retryable():
    exc = Exception("boom")
    exc.body = {"error": {"code": "tool_use_failed", "message": "missing properties: 'statement'"}}
    converted = _as_tool_error(exc)
    assert isinstance(converted, ToolSchemaError)
    assert "statement" in str(converted)


def test_non_tool_error_passes_through():
    exc = ValueError("unrelated")
    assert _as_tool_error(exc) is exc


def test_rate_limit_wait_parses_seconds():
    exc = type("RateLimitError", (Exception,), {})()
    exc.body = {"error": {"message": "Rate limit reached. Please try again in 12.5s. Upgrade..."}}
    wait = _rate_limit_wait(exc)
    assert wait == pytest.approx(13.5)


def test_rate_limit_wait_none_for_other_errors():
    assert _rate_limit_wait(ValueError("nope")) is None
