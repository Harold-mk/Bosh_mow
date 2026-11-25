"""Claude through Claude Code (`claude -p`), on the user's Pro plan (D7).

Each call runs in an empty temporary folder, without any tool, settings or MCP server:
Claude only sees the message and can neither read nor change any file. The message,
images included, goes on stdin in stream JSON; the answer is the "result" line of the
output stream. The API key is removed from the environment, so that a call is never
billed to the API by mistake.
"""

import base64
import json
import os
import subprocess
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from bosh_mow.ai.gateway import EngineTimeout, EngineUnavailable

SYSTEM_PROMPT = (
    "You are a component of a study app. Follow the instructions and answer only "
    "with the requested JSON."
)


@dataclass(frozen=True)
class ClaudeEngine:
    model: str | None = None  # None: the default model of the account
    timeout_seconds: float = 300
    name: str = "claude"

    def run(
        self, prompt: str, schema: dict[str, Any], images: Sequence[bytes] = ()
    ) -> dict[str, Any]:
        """Answer the prompt, about the PNG `images` if any, with a JSON object that
        fits `schema`."""
        with tempfile.TemporaryDirectory() as empty_folder:
            try:
                completed = subprocess.run(
                    claude_command(schema, self.model),
                    input=user_message(prompt, images),
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
                raise EngineTimeout("Claude n'a pas répondu à temps.") from error
        return parse_answer(completed.stdout, completed.stderr)


def claude_command(schema: dict[str, Any], model: str | None = None) -> list[str]:
    """The `claude -p` command line: JSON answer, no tool, no settings, no session."""
    command = [
        "claude",
        "-p",
        "--input-format", "stream-json",  # the message on stdin, images included
        "--output-format", "stream-json",  # required by a stream JSON input
        "--verbose",  # required by a stream JSON output
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


def user_message(prompt: str, images: Sequence[bytes] = ()) -> str:
    """The line that Claude Code reads on stdin: the PNG images, then the prompt."""
    content: list[dict[str, Any]] = [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": base64.b64encode(image).decode("ascii"),
            },
        }
        for image in images
    ]
    content.append({"type": "text", "text": prompt})
    message = {"type": "user", "message": {"role": "user", "content": content}}
    return json.dumps(message) + "\n"


def environment_without_api_key() -> dict[str, str]:
    """The current environment, without ANTHROPIC_API_KEY (D7)."""
    return {
        key: value for key, value in os.environ.items() if key != "ANTHROPIC_API_KEY"
    }


def parse_answer(stdout: str, stderr: str) -> dict[str, Any]:
    """The structured answer in the output stream: its line of type "result"."""
    result = None
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict) and event.get("type") == "result":
            result = event
    if result is None:
        message = _short(stderr or stdout) or "Claude Code n'a rien renvoyé."
        raise EngineUnavailable(message)
    answer = result.get("structured_output")
    if result.get("is_error") or not isinstance(answer, dict):
        raise EngineUnavailable(_short(str(result.get("result") or result)))
    return answer


def _short(text: str) -> str:
    return " ".join(text.split())[:300]
