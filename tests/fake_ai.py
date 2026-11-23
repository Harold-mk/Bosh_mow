"""A fake AI for the tests: it returns prepared answers and never calls a real model."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FakeEngine:
    """Returns its answers in order; an exception in the list is raised instead."""

    answers: list[dict[str, Any] | Exception]
    name: str = "fake"
    prompts: list[str] = field(default_factory=list)  # what it was asked

    def run(self, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        self.prompts.append(prompt)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer
