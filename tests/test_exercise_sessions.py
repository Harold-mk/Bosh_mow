"""Tests of the exercises in the sessions (T3, R14): the exercise step of a notion,
answers without confidence, the solo problems in the reviews with the worked example."""

import sqlite3
from datetime import timedelta
from functools import partial
from pathlib import Path
from typing import Any

import pytest
from test_exercise_preparation import answer as t3_answer
from test_exercise_preparation import five
from test_open_answers import graded
from test_preparation import fake_gateway
from test_sessions import NOW, TODAY, make_subject

from bosh_mow.ai.schemas import T3Answer
from bosh_mow.content.preparation import to_exercises
from bosh_mow.content.repository import (
    Question,
    get_exercises,
    report_question,
    save_exercises,
)
from bosh_mow.grading.open_answers import grade_open
from bosh_mow.study.gradings import grading_state, run_grading, start_grading
from bosh_mow.study.repository import due_questions, get_card
from bosh_mow.study.sessions import (
    answer,
    finish,
    next_question,
    start_notion,
    start_queue,
)


def with_exercises(
    db: sqlite3.Connection, raw: dict[str, Any] | None = None
) -> tuple[int, list[Question]]:
    """A notion with its 7 questions and its 5 exercises: (notion, exercises)."""
    notion_id, _ = make_subject(db)
    written = to_exercises(T3Answer.model_validate(raw or t3_answer()))
    save_exercises(db, notion_id, written)
    return notion_id, get_exercises(db, notion_id)


def written_results() -> dict[str, Any]:
    """The five exercises with a written result: a reasoning, graded by Claude."""
    return t3_answer(
        [
            {
                **exercise,
                "answer_format": "open",
                "value": None,
                "tolerance": None,
                "expected_answer": "s² = 4",
            }
            for exercise in five()
        ]
    )


# The exercise step of a notion


def test_r14_the_exercise_step_of_a_notion(db: sqlite3.Connection) -> None:
    notion_id, exercises = with_exercises(db)

    worked, completion, solo = start_notion(db, notion_id, TODAY).exercises

    assert [worked.id, completion.id, solo.id] == [e.id for e in exercises[:3]]
    assert worked.exercise is not None and completion.exercise is not None
    assert solo.exercise is not None
    assert (
        worked.exercise.kind,
        len(worked.exercise.given),
        worked.exercise.to_do,
    ) == (
        "worked",
        3,
        0,
    )
    assert (len(completion.exercise.given), completion.exercise.to_do) == (2, 1)
    assert (solo.exercise.given, solo.exercise.to_do) == ([], 3)
    assert solo.exercise.topic == "Computing a sample variance"
    assert solo.exercise.worked_example is None  # it is the step before
    assert (solo.format, solo.tolerance) == ("value", 0.01)


def test_the_exercise_step_leaves_out_a_reported_exercise(
    db: sqlite3.Connection,
) -> None:
    notion_id, exercises = with_exercises(db)
    report_question(db, exercises[2].id)  # the first solo problem is wrong

    *_, solo = start_notion(db, notion_id, TODAY).exercises

    assert solo.statement == "Compute the sample variance of 2, 6 and 10."


def test_a_notion_without_exercises_has_no_exercise_step(
    db: sqlite3.Connection,
) -> None:
    notion_id, _ = make_subject(db)

    assert start_notion(db, notion_id, TODAY).exercises == []


# Answering an exercise: no confidence (T3)


def test_t5_a_value_of_an_exercise_is_graded_without_confidence(
    db: sqlite3.Connection,
) -> None:
    notion_id, (_, completion, solo, *_) = with_exercises(db)
    session = start_notion(db, notion_id, TODAY)

    completed = answer(
        db, session.session_id, completion.id, None, None, 60, NOW, answer_text="6,67"
    )
    solved = answer(
        db, session.session_id, solo.id, None, None, 90, NOW, answer_text="4"
    )

    assert (completed.correct, solved.correct) == (True, True)
    assert len(completed.solution) == 3  # the whole solution, to read after
    assert get_card(db, completion.id) is None  # a scaffold: it does not come back
    card = get_card(db, solo.id)
    assert card is not None and card.due > NOW  # right: it comes back later
    assert db.execute("SELECT DISTINCT confidence FROM answer").fetchall() == [(None,)]


def test_t6_a_written_exercise_is_graded_on_its_steps_without_confidence(
    db: sqlite3.Connection, tmp_path: Path
) -> None:
    notion_id, (_, completion, solo, *_) = with_exercises(db, written_results())
    session_id = start_notion(db, notion_id, TODAY).session_id
    with pytest.raises(ValueError, match="time its answer took"):
        start_grading(db, session_id, solo.id, "s² = 8 / 2 = 4")

    on_solo = start_grading(db, session_id, solo.id, "Mean 4, then 8 / 3.", seconds=120)
    run_grading(
        db,
        on_solo,
        partial(grade_open, fake_gateway(tmp_path, graded(True, False, True))),
    )
    on_completion = start_grading(
        db, session_id, completion.id, "8 / 2 = 4", seconds=40
    )
    run_grading(
        db, on_completion, partial(grade_open, fake_gateway(tmp_path, graded(True)))
    )

    state = grading_state(db, on_solo)
    assert state is not None
    # Steps worth 1, 1 and 2: 3 points out of 4, under 80 %; dropped at the second.
    assert (state.correct, state.points, state.out_of, state.dropped_at) == (
        False,
        3,
        4,
        2,
    )
    assert len(state.solution) == 3
    done = grading_state(db, on_completion)
    assert done is not None
    assert (done.correct, len(done.criteria)) == (True, 1)  # its one step to do
    saved = db.execute(
        "SELECT question_id, correct, confidence, seconds FROM answer ORDER BY id"
    ).fetchall()
    assert saved == [(solo.id, 0, None, 120), (completion.id, 1, None, 40)]
    assert get_card(db, solo.id) is not None
    assert get_card(db, completion.id) is None


# The solo problems in the reviews (R14)


def test_r14_the_solo_problems_not_done_come_back_the_next_day(
    db: sqlite3.Connection,
) -> None:
    notion_id, (worked, completion, first, second, third) = with_exercises(db)
    session = start_notion(db, notion_id, TODAY)
    answer(db, session.session_id, first.id, None, None, 90, NOW, answer_text="4")
    answered = get_card(db, first.id)

    finish(db, session.session_id, completed=True, day=TODAY, now=NOW)

    for later in (second, third):
        card = get_card(db, later.id)
        assert card is not None and card.due == NOW + timedelta(days=1)
    assert get_card(db, first.id) == answered
    assert get_card(db, worked.id) is None and get_card(db, completion.id) is None


def test_a_notion_left_for_later_does_not_date_its_solo_problems(
    db: sqlite3.Connection,
) -> None:
    notion_id, exercises = with_exercises(db)
    session = start_notion(db, notion_id, TODAY)

    finish(db, session.session_id, completed=False, day=TODAY, now=NOW)

    assert all(get_card(db, exercise.id) is None for exercise in exercises)


def test_r14_a_solo_problem_comes_back_with_its_worked_example_until_two_are_solved(
    db: sqlite3.Connection,
) -> None:
    notion_id, (_, _, first, second, third) = with_exercises(db)
    session = start_notion(db, notion_id, TODAY)
    answer(db, session.session_id, first.id, None, None, 90, NOW, answer_text="4")
    finish(db, session.session_id, completed=True, day=TODAY, now=NOW)
    later = NOW + timedelta(days=1, minutes=1)
    queue = start_queue(db, TODAY + timedelta(days=1), later)

    due = due_questions(db, later)
    review = next_question(db, queue, later)
    assert {(item.question_id, item.seconds) for item in due} == {
        (first.id, 180),  # an exercise takes 3 minutes of the queue
        (second.id, 180),
        (third.id, 180),
    }
    # The first one comes back first: 10 minutes after its answer, as it is learned.
    assert review is not None and review.exercise is not None
    assert review.id == first.id
    offered = review.exercise.worked_example
    assert offered is not None  # one solo problem solved so far
    assert offered.statement == "Compute the sample variance of 2, 4 and 6."
    assert len(offered.steps) == 3

    answer(db, queue, first.id, None, None, 80, later, answer_text="4")
    after_two = next_question(db, queue, later)

    assert after_two is not None and after_two.id == second.id
    assert after_two.exercise is not None
    assert after_two.exercise.worked_example is None  # two solved in a row
