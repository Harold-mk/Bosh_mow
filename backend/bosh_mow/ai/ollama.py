"""The local model through Ollama (D6): Qwen 3.5 4B, on this computer, free and offline.

It answers through the local HTTP API of Ollama, with the JSON schema of the task as
the format of its answer, without thinking first: about 15 seconds for a grading. Too
slow to grade live, it is the fallback of T6 when Claude cannot answer, and its
gradings are provisional until Claude checks them.
"""

import json
import urllib.error
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from bosh_mow.ai.gateway import EngineTimeout, EngineUnavailable

SYSTEM_PROMPT = (
    "You are a component of a study app. Follow the instructions and answer only "
    "with the requested JSON."
)


@dataclass(frozen=True)
class OllamaEngine:
    model: str = "qwen3.5:4b"
    url: str = "http://127.0.0.1:11434"  # Ollama, on this computer only
    timeout_seconds: float = 120
    name: str = "local"

    def run(
        self, prompt: str, schema: dict[str, Any], images: Sequence[bytes] = ()
    ) -> dict[str, Any]:
        """Answer the prompt with a JSON object that fits `schema`."""
        if images:
            raise EngineUnavailable("Le modèle local ne lit pas les images ici.")
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "format": schema,  # the answer follows the schema of the task
            "stream": False,
            "think": False,  # thinking first would double the time of an answer
            "options": {"temperature": 0},
        }
        request = urllib.request.Request(
            f"{self.url}/api/chat",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as reply:
                answer = json.load(reply)
        except TimeoutError as error:
            raise EngineTimeout("Le modèle local n'a pas répondu à temps.") from error
        except urllib.error.HTTPError as error:  # an unknown model, for instance
            detail = error.read().decode("utf-8", "replace")[:300]
            raise EngineUnavailable(f"Le modèle local refuse : {detail}") from error
        except urllib.error.URLError as error:
            if isinstance(error.reason, TimeoutError):
                message = "Le modèle local n'a pas répondu à temps."
                raise EngineTimeout(message) from error
            message = "Le modèle local n'est pas lancé (Ollama)."
            raise EngineUnavailable(message) from error
        try:
            content = json.loads(answer["message"]["content"])
        except (KeyError, TypeError, json.JSONDecodeError):
            return {}  # not the JSON asked for: rejected, then asked again once
        return content if isinstance(content, dict) else {}
