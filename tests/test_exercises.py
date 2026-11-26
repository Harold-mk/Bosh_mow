"""Tests of the exercises (T3): their verdict against the rubric (T6), the step where
the student dropped off, and the worked example offered in the reviews (R14)."""

import pytest

from bosh_mow.grading.exercises import dropped_at, exercise_verdict
from bosh_mow.study.exercises import offers_worked_example

RUBRIC = [1, 1, 1, 2]  # mean, deviations, squares, then the variance: 5 points


# The verdict of an exercise: 80 % of its rubric, and its result


def test_t6_an_exercise_with_every_step_is_right() -> None:
    assert exercise_verdict(RUBRIC, [True, True, True, True])


def test_t6_an_exercise_is_right_with_80_percent_of_the_rubric_and_its_result() -> None:
    assert exercise_verdict(RUBRIC, [False, True, True, True])  # 4 points out of 5


def test_t6_under_80_percent_an_exercise_is_to_review() -> None:
    assert not exercise_verdict(RUBRIC, [False, False, True, True])  # 3 out of 5


def test_t6_a_wrong_result_is_to_review_whatever_the_points() -> None:
    nine_steps_then_result = [1] * 10  # 9 points out of 10, but not the last step

    assert not exercise_verdict(nine_steps_then_result, [True] * 9 + [False])


def test_an_exercise_without_steps_is_never_right() -> None:
    assert not exercise_verdict([], [])


def test_one_result_per_step_of_the_rubric() -> None:
    with pytest.raises(ValueError, match="One result per step"):
        exercise_verdict(RUBRIC, [True, True])


# Where the student dropped off


@pytest.mark.parametrize(
    ("met", "step"),
    [
        ([True, True, False, False], 3),
        ([True, False, True, True], 2),
        ([False, True, True, True], 1),
        ([True, True, True, True], None),  # nowhere: every step is met
    ],
)
def test_t6_the_step_where_the_student_dropped_off(
    met: list[bool], step: int | None
) -> None:
    assert dropped_at(met) == step


# R14: the worked example, offered until two solo problems in a row are right


@pytest.mark.parametrize(
    ("solo_results", "offered"),
    [
        ([], True),  # no solo problem answered yet
        ([True], True),  # one right only
        ([True, False], True),  # the last one missed
        ([False, True, True], False),  # the last two right: no more worked example
        ([True, True, False], True),  # missed again: it is offered again
    ],
)
def test_r14_the_worked_example_is_offered_until_the_last_two_solo_are_right(
    solo_results: list[bool], offered: bool
) -> None:
    assert offers_worked_example(solo_results) is offered
