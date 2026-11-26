"""Exercises in the reviews (R14): the solo problems of a notion come back, with its
worked example offered until the student solves two of them in a row.
"""

from collections.abc import Sequence


def offers_worked_example(solo_results: Sequence[bool]) -> bool:
    """Whether the worked example of a notion is still offered with its solo problems,
    given their answers so far, oldest first: until the last two are right (R14)."""
    return not (len(solo_results) >= 2 and solo_results[-1] and solo_results[-2])
