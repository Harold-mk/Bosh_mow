"""Tests of the Claude adapter, without ever calling Claude: command, key, answer."""

import json

import pytest

from bosh_mow.ai.claude import claude_command, environment_without_api_key, parse_answer
from bosh_mow.ai.gateway import EngineUnavailable

# The shape of what `claude -p --output-format json` printed in a real call (shortened).
SUCCESS = {
    "type": "result",
    "subtype": "success",
    "is_error": False,
    "result": '{"ok":true}',
    "structured_output": {"ok": True},
}


def test_structured_answer_is_read_from_the_output() -> None:
    assert parse_answer(json.dumps(SUCCESS), "") == {"ok": True}


def test_error_reported_by_claude_code_means_unavailable() -> None:
    failure = {
        **SUCCESS,
        "is_error": True,
        "result": "Claude AI usage limit reached",
        "structured_output": None,
    }

    with pytest.raises(EngineUnavailable, match="usage limit"):
        parse_answer(json.dumps(failure), "")


def test_output_that_is_not_json_means_unavailable() -> None:
    with pytest.raises(EngineUnavailable, match="not logged in"):
        parse_answer("", "Error: not logged in")


def test_d7_api_key_is_removed_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-a-real-key")
    monkeypatch.setenv("BOSH_TEST_VARIABLE", "kept")

    environment = environment_without_api_key()

    assert "ANTHROPIC_API_KEY" not in environment
    assert environment["BOSH_TEST_VARIABLE"] == "kept"


def test_claude_runs_without_tools_settings_or_saved_session() -> None:
    command = claude_command({"type": "object"}, model="sonnet")

    assert command[:2] == ["claude", "-p"]
    for flag, value in [
        ("--output-format", "json"),
        ("--tools", ""),
        ("--setting-sources", ""),
        ("--model", "sonnet"),
    ]:
        assert command[command.index(flag) + 1] == value
    assert "--strict-mcp-config" in command
    assert "--no-session-persistence" in command
