"""The AI gateway: versioned prompts, checked answers and a log of every call.

Every answer is checked against its contract (docs/contrats-ia.md): first its format,
a Pydantic schema, then the rules of its task. A rejected answer is asked again once,
with the reasons; after that, the failure is reported, never hidden.
"""

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, ValidationError
from pydantic_core import ErrorDetails

PROMPTS_DIR = Path(__file__).resolve().parents[3] / "prompts"


class EngineUnavailable(Exception):
    """The engine cannot answer now (not installed, offline, Pro limit): try later."""


class InvalidAnswer(Exception):
    """The answer broke its contract twice in a row."""


class Engine(Protocol):
    name: str

    def run(self, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        """Answer the prompt with a JSON object that follows the JSON schema."""
        ...


@dataclass(frozen=True)
class Gateway:
    engine: Engine
    log_file: Path  # one JSON line per call
    prompts_dir: Path = PROMPTS_DIR

    def ask[T: BaseModel](
        self,
        prompt_name: str,
        data: dict[str, Any],
        schema: type[T],
        check: Callable[[T], list[str]] | None = None,
    ) -> T:
        """Ask the engine, with the prompt file `prompt_name` (e.g. "t1_v1") and `data`.

        `check` lists what breaks the rules of the task (nothing when all is well).
        """
        prompt = (self.prompts_dir / f"{prompt_name}.md").read_text(encoding="utf-8")
        prompt += (
            f"\n\n<input>\n{json.dumps(data, ensure_ascii=False, indent=2)}\n</input>\n"
        )
        problems: list[str] = []
        for _ in range(2):  # the first try, then a single retry
            started = time.monotonic()
            try:
                raw = self.engine.run(prompt, schema.model_json_schema())
            except EngineUnavailable as error:
                self._log(prompt_name, started, "unavailable", str(error))
                raise
            try:
                answer = schema.model_validate(raw)
                problems = check(answer) if check else []
            except ValidationError as error:
                problems = [_describe(detail) for detail in error.errors()]
            outcome = "rejected" if problems else "accepted"
            self._log(prompt_name, started, outcome, "; ".join(problems))
            if not problems:
                return answer
            prompt += (
                "\n\nYour previous answer was rejected:\n"
                f"{json.dumps(raw, ensure_ascii=False)}\n"
                "Reasons:\n- " + "\n- ".join(problems) + "\n"
                "Answer again, fixing these problems.\n"
            )
        raise InvalidAnswer("; ".join(problems))

    def _log(self, prompt_name: str, started: float, outcome: str, detail: str) -> None:
        entry = {
            "at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "prompt": prompt_name,
            "engine": self.engine.name,
            "duration_ms": round((time.monotonic() - started) * 1000),
            "outcome": outcome,
            "detail": detail,
        }
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        with self.log_file.open("a", encoding="utf-8") as log:
            log.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _describe(detail: ErrorDetails) -> str:
    """One line from a Pydantic error, e.g. "chapters.0.role: Input should be…"."""
    where = ".".join(str(part) for part in detail["loc"]) or "answer"
    return f"{where}: {detail['msg']}"
