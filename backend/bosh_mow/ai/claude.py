"""Claude through Claude Code (`claude -p`), on the user's Pro plan (D7).

Each call runs in an empty temporary folder, without any tool, settings or MCP server:
Claude only sees the prompt and can neither read nor change any file. The API key is
removed from the environment, so that a call is never billed to the API by mistake.
"""

import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Any

from bosh_mow.ai.gateway import EngineUnavailable

SYSTEM_PROMPT = (
    "You are a component of a study app. Follow the instructions and answer only "
    "with the requested JSON."
)


@dataclass(frozen=True)
class ClaudeEngine:
    model: str | None = None  # None: the default model of the account
    timeout_seconds: float = 300
    name: str = "claude"

    def run(self, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        """Answer the prompt, sent on stdin, with a JSON object that fits `schema`."""
        with tempfile.TemporaryDirectory() as empty_folder:
            try:
                completed = subprocess.run(
                    claude_command(schema, self.model),
                    input=prompt,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    env=environment_without_api_key(),
                    cwd=empty_folder,
                    timeout=self.timeout_seconds,
                    check=False,
                )
            except FileNotFoundError as error:
                raise EngineUnavailable("Claude Code n'est pas installé.") from error
            except subprocess.TimeoutExpired as error:
                raise EngineUnavailable("Claude n'a pas répondu à temps.") from error
        return parse_answer(completed.stdout, completed.stderr)


def claude_command(schema: dict[str, Any], model: str | None = None) -> list[str]:
    """The `claude -p` command line: JSON answer, no tool, no settings, no session."""
    command = [
        "claude",
        "-p",
        "--output-format", "json",
        "--json-schema", json.dumps(schema),
        "--system-prompt", SYSTEM_PROMPT,
        "--tools", "",  # no tool at all
        "--setting-sources", "",  # neither user nor project settings (hooks…)
        "--strict-mcp-config",  # no MCP server
        "--disable-slash-commands",
        "--no-session-persistence",
    ]  # fmt: skip
    if model:
        command += ["--model", model]
    return command


def environment_without_api_key() -> dict[str, str]:
    """The current environment, without ANTHROPIC_API_KEY (D7)."""
    return {
        key: value for key, value in os.environ.items() if key != "ANTHROPIC_API_KEY"
    }


def parse_answer(stdout: str, stderr: str) -> dict[str, Any]:
    """The structured answer in what `claude -p --output-format json` printed."""
    try:
        envelope = json.loads(stdout)
    except json.JSONDecodeError:
        message = _short(stderr or stdout) or "Claude Code n'a rien renvoyé."
        raise EngineUnavailable(message) from None
    answer = envelope.get("structured_output")
    if envelope.get("is_error") or not isinstance(answer, dict):
        raise EngineUnavailable(_short(str(envelope.get("result") or envelope)))
    return answer


def _short(text: str) -> str:
    return " ".join(text.split())[:300]
