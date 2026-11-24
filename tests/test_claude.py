"""Tests of the Claude adapter, without ever calling Claude: command, key, answer."""

import base64
import json

import pytest

from bosh_mow.ai.claude import (
    claude_command,
    environment_without_api_key,
    parse_answer,
    user_message,
)
from bosh_mow.ai.gateway import EngineUnavailable

# The lines that `claude -p --output-format stream-json` printed in a real call
# (shortened): the answer is on the last one, of type "result".
INIT = {"type": "system", "subtype": "init", "tools": ["StructuredOutput"]}
TURN = {"type": "assistant", "message": {"content": []}}
SUCCESS = {
    "type": "result",
    "subtype": "success",
    "is_error": False,
    "result": '{"ok":true}',
    "structured_output": {"ok": True},
}


def stream(*events: dict[str, object]) -> str:
    return "".join(json.dumps(event) + "\n" for event in events)


def test_structured_answer_is_read_from_the_result_line() -> None:
    assert parse_answer(stream(INIT, TURN, SUCCESS), "") == {"ok": True}


def test_error_reported_by_claude_code_means_unavailable() -> None:
    failure = {
        **SUCCESS,
        "is_error": True,
        "result": "Claude AI usage limit reached",
        "structured_output": None,
    }

    with pytest.raises(EngineUnavailable, match="usage limit"):
        parse_answer(stream(INIT, failure), "")


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
        ("--input-format", "stream-json"),
        ("--output-format", "stream-json"),
        ("--tools", ""),
        ("--setting-sources", ""),
        ("--model", "sonnet"),
    ]:
        assert command[command.index(flag) + 1] == value
    assert "--verbose" in command
    assert "--strict-mcp-config" in command
    assert "--no-session-persistence" in command


def test_images_come_before_the_prompt_in_the_message() -> None:
    png = b"fake PNG image"

    line = user_message("Décris cette page.", [png])

    assert line.endswith("\n")
    message = json.loads(line)
    assert message["type"] == "user"
    image, text = message["message"]["content"]
    assert image["source"]["media_type"] == "image/png"
    assert base64.b64decode(image["source"]["data"]) == png
    assert text == {"type": "text", "text": "Décris cette page."}
