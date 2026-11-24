"""T5: grading of closed questions by the code, without AI, in a fraction of a second.

Lot 2 grades the MCQ; the value and the short answer come in lot 3.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Option:
    """An option of an MCQ, with the explanation shown after the answer (in French)."""

    text: str
    correct: bool
    explanation: str


def mcq_options(content: dict[str, Any]) -> list[Option]:
    """The options of an MCQ, from the content of its question."""
    return [
        Option(option["text"], option["correct"], option["explanation"])
        for option in content["options"]
    ]


def grade_mcq(options: Sequence[Option], chosen: int | None) -> bool:
    """Whether the option chosen (from 1) is the correct one; None, "Je ne sais pas",
    is wrong."""
    if chosen is None:
        return False
    if not 1 <= chosen <= len(options):
        raise ValueError(f"There is no option {chosen}.")
    return options[chosen - 1].correct
