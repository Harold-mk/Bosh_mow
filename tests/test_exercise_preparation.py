"""Tests of T3: the exercises of a notion written by Claude (a fake one here), checked
against the contract, then saved after its questions."""

import sqlite3
from pathlib import Path
from typing import Any

import pytest
from test_preparation import fake_gateway
from test_sessions import make_subject

from bosh_mow.ai.schemas import T3Answer
from bosh_mow.content.preparation import (
    check_exercises,
    prepare_exercises,
    to_exercises,
)
from bosh_mow.content.repository import get_exercises, get_questions, save_exercises

GIVEN = {"worked": [True] * 3, "completion": [True, True, False], "solo": [False] * 3}


def exercise(
    kind: str, statement: str, value: float, **changes: object
) -> dict[str, Any]:
    """An exercise of T3 on the variance: three steps, the result last."""
    texts = ["Mean: 4", "Squares of the deviations: 4, 0, 4, sum 8", "s² = 8 / 2 = 4"]
    steps = [
        {"text": text, "points": 2 if last else 1, "given": given}
        for text, given, last in zip(
            texts, GIVEN[kind], [False, False, True], strict=True
        )
    ]
    return {
        "kind": kind,
        "type": "calculation",
        "statement": statement,
        "steps": steps,
        "answer_format": "value",
        "value": value,
        "tolerance": 0.01,
        "first_page": 2,
        "last_page": 3,
        **changes,
    }


def five() -> list[dict[str, Any]]:
    return [
        exercise("worked", "Compute the sample variance of 2, 4 and 6.", 4),
        exercise("completion", "Compute the sample variance of 1, 3, 5 and 7.", 6.67),
        exercise("solo", "Compute the sample variance of 3, 5 and 7.", 4),
        exercise("solo", "Compute the sample variance of 2, 6 and 10.", 16),
        exercise("solo", "Compute the sample variance of 1, 2 and 3.", 1),
    ]


def answer(
    exercises: list[dict[str, Any]] | None = None, none_reason: str | None = None
) -> dict[str, Any]:
    """An answer of T3."""
    return {
        "topic": "Computing a sample variance",
        "none_reason": none_reason,
        "exercises": five() if exercises is None else exercises,
    }


def problems(raw: dict[str, Any]) -> list[str]:
    """The problems of the exercises of a notion of pages 1 to 6."""
    return check_exercises(T3Answer.model_validate(raw), 1, 6)


def changed(number: int, **changes: object) -> dict[str, Any]:
    """The five exercises, the one at `number` (from 1) changed."""
    exercises = five()
    exercises[number - 1] = {**exercises[number - 1], **changes}
    return answer(exercises)


def with_steps(number: int, *given: bool, points: int = 1) -> dict[str, Any]:
    steps = [
        {"text": f"Step {k}", "points": points, "given": g} for k, g in enumerate(given)
    ]
    return changed(number, steps=steps)


# The rules of T3


def test_exercises_that_keep_the_rules_pass() -> None:
    assert problems(answer()) == []


def test_a_purely_theoretical_notion_has_no_exercise_but_says_why() -> None:
    assert problems(answer([], "A definition: nothing to practise.")) == []
    assert problems(answer([], None)) == [
        "Give the five exercises, or none with the reason in none_reason."
    ]


def test_r14_one_worked_example_one_completion_and_three_solo_problems() -> None:
    assert problems(answer(five()[:4])) == [
        "The notion needs 1 worked example, 1 problem to complete and 3 solo problems,"
        " not 1, 1 and 2."
    ]


def test_each_step_has_its_line_in_the_rubric() -> None:
    assert problems(with_steps(1, True, True, points=0)) == [
        "Exercise 1: each step is worth 1 point at least."
    ]


def test_a_solution_has_two_steps_at_least() -> None:
    assert problems(with_steps(1, True)) == [
        "Exercise 1: give the solution in 2 steps at least."
    ]


def test_a_worked_example_gives_every_step() -> None:
    assert problems(with_steps(1, True, False)) == [
        "Exercise 1: a worked example gives every step."
    ]


@pytest.mark.parametrize(
    "given", [(False, False, False), (True, True, True), (False, True, False)]
)
def test_a_problem_to_complete_gives_its_first_steps_only(
    given: tuple[bool, ...],
) -> None:
    assert problems(with_steps(2, *given)) == [
        "Exercise 2: a problem to complete gives its first steps, then leaves one to"
        " the student at least."
    ]


def test_a_solo_problem_gives_no_step() -> None:
    assert problems(with_steps(3, True, False)) == [
        "Exercise 3: a solo problem gives no step."
    ]


def test_a_value_has_its_result_and_a_tolerance() -> None:
    assert problems(changed(1, value=None)) == [
        "Exercise 1: give the value of its result."
    ]
    assert problems(changed(1, tolerance=-0.01)) == [
        "Exercise 1: its tolerance cannot be negative."
    ]


def test_a_written_result_has_its_expected_answer() -> None:
    assert problems(changed(1, answer_format="open", value=None)) == [
        "Exercise 1: give its expected answer."
    ]


def test_r4_an_exercise_stays_in_the_pages_of_the_notion() -> None:
    assert problems(changed(3, first_page=7, last_page=8)) == [
        "Exercise 3: pages 7 to 8 are not in the notion, pages 1 to 6."
    ]


def test_the_solo_problems_are_three_different_problems() -> None:
    same_statement = changed(4, statement="Compute the sample variance of 3, 5 and 7.")
    same_result = changed(4, value=4)

    assert problems(same_statement) == [
        "Exercises 3 and 4 are the same problem: change its data or its context."
    ]
    assert problems(same_result) == [
        "Exercises 3 and 4 have the same result: give them other data."
    ]


# Asking Claude, and saving the exercises


def test_t3_claude_reads_the_notion_its_objectives_and_its_questions(
    db: sqlite3.Connection, tmp_path: Path
) -> None:
    notion_id, _ = make_subject(db)  # a notion of pages 1 to 6, with its 7 questions
    gateway = fake_gateway(tmp_path, answer())

    written = prepare_exercises(db, gateway, notion_id)

    assert [exercise.kind for exercise in written.exercises] == [
        "worked",
        "completion",
        "solo",
        "solo",
        "solo",
    ]
    (sent,) = gateway.engine.prompts
    for part in (
        "Variance",  # the notion
        "Page 3",  # the text of its pages
        "Être capable de mesurer la dispersion",  # the objectives of its chapter
        get_questions(db, notion_id)[0].statement,  # its questions, not to repeat
    ):
        assert part in sent


def test_t3_exercises_are_saved_after_the_questions_of_their_notion(
    db: sqlite3.Connection,
) -> None:
    notion_id, _ = make_subject(db)
    exercises = to_exercises(T3Answer.model_validate(answer()))

    save_exercises(db, notion_id, exercises)

    saved = get_exercises(db, notion_id)
    assert [e.exercise for e in saved] == [
        "worked",
        "completion",
        "solo",
        "solo",
        "solo",
    ]
    assert len(get_questions(db, notion_id)) == 7  # the questions alone
    assert (saved[0].role, saved[0].level, saved[0].format) == (
        "review",
        "apply",
        "value",
    )
    assert saved[1].content["topic"] == "Computing a sample variance"
    assert [step["given"] for step in saved[1].content["steps"]] == [True, True, False]
    assert (saved[1].content["value"], saved[1].content["tolerance"]) == (6.67, 0.01)
    with pytest.raises(ValueError, match="already has its exercises"):
        save_exercises(db, notion_id, exercises)


def test_a_written_result_is_saved_with_its_expected_answer() -> None:
    code = changed(
        5,
        type="code",
        answer_format="open",
        value=None,
        tolerance=None,
        expected_answer="df.groupby('shop')['amount'].sum()",
    )

    (*_, solo) = to_exercises(T3Answer.model_validate(code))

    assert (solo.format, solo.type) == ("open", "code")
    assert solo.content["expected_answer"] == "df.groupby('shop')['amount'].sum()"
    assert "value" not in solo.content


def test_a_notion_without_exercises_saves_none() -> None:
    assert (
        to_exercises(T3Answer.model_validate(answer([], "Nothing to practise."))) == []
    )
