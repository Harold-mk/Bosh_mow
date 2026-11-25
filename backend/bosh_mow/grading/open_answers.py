"""T6: open answers, graded by Claude against the criteria of their question.

Claude says which criteria an answer meets; the app concludes, so that a verdict never
depends on how a language model counts.
"""

from collections.abc import Sequence


def verdict(criteria_met: Sequence[bool]) -> bool:
    """Whether an open answer is right: it meets every criterion of its question. With
    the 2 to 4 criteria of a question, this is also the 80 % rule of T6."""
    return bool(criteria_met) and all(criteria_met)
