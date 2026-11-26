"""Exercises (T3) graded against their rubric (T6): each step of the solution is worth
its points, all or none; the app adds them up and concludes, never a language model.
"""

from collections.abc import Sequence


def exercise_verdict(points: Sequence[int], met: Sequence[bool]) -> bool:
    """Whether an exercise is right: at least 80 % of the points of its rubric, and its
    last step, the result, met (T6)."""
    if len(points) != len(met):
        raise ValueError("One result per step of the rubric.")
    if not points:
        return False
    earned = sum(worth for worth, ok in zip(points, met, strict=True) if ok)
    return met[-1] and earned * 5 >= sum(points) * 4  # 80 %, in whole numbers


def dropped_at(met: Sequence[bool]) -> int | None:
    """The step where the student dropped off: the first one missed, from 1; None when
    every step is met (T6)."""
    return next((number for number, ok in enumerate(met, start=1) if not ok), None)
