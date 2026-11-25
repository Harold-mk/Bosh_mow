"""Tests of open answers in a session (T6): graded while the confidence is chosen, and
saved in the history once both are there. A fake grader stands for Claude."""

import json
import sqlite3
from collections.abc import Sequence

import pytest
from test_sessions import NOW, TODAY, make_due, make_subject, question_of

from bosh_mow.ai.gateway import EngineTimeout, EngineUnavailable, InvalidAnswer
from bosh_mow.ai.tasks import run_next_task
from bosh_mow.grading.open_answers import (
    CriterionResult,
    OpenGrading,
    OpenQuestion,
    verdict,
)
from bosh_mow.study.gradings import (
    TASK,
    Grader,
    give_confidence,
    grade_or_wait,
    grading_handler,
    grading_state,
    resume_gradings,
    run_grading,
    start_grading,
)
from bosh_mow.study.repository import due_questions, get_card
from bosh_mow.study.sessions import start_queue

ANSWER = "Extreme values pull the mean, not the median."


def grader(*met: bool) -> Grader:
    """A fake Claude that finds these criteria met, in order."""

    def grade(question: OpenQuestion, answer: str) -> OpenGrading:
        results = [
            CriterionResult(criterion, one, "C'est dit." if one else "Il manque ça.")
            for criterion, one in zip(question.criteria, met, strict=True)
        ]
        return OpenGrading(results, "Bien vu.", verdict(met))

    return grade


def failing(error: Exception) -> Grader:
    """A fake Claude that cannot grade."""

    def grade(question: OpenQuestion, answer: str) -> OpenGrading:
        raise error

    return grade


def open_answer(db: sqlite3.Connection) -> tuple[int, int]:
    """A daily queue with the open question of a notion due: (session, question)."""
    notion_id, _ = make_subject(db)
    why = question_of(db, notion_id, "open")
    make_due(db, [why])
    return start_queue(db, TODAY, NOW), why


def answers(db: sqlite3.Connection) -> Sequence[tuple[int, str, int, str, int]]:
    return db.execute(
        "SELECT question_id, answer_text, correct, confidence, seconds FROM answer"
    ).fetchall()


def test_t6_the_answer_enters_the_history_once_graded_and_confided(
    db: sqlite3.Connection,
) -> None:
    session_id, why = open_answer(db)
    grading_id = start_grading(db, session_id, why, f"  {ANSWER} ")

    run_grading(db, grading_id, grader(True, True))
    assert answers(db) == []  # the confidence is not chosen yet
    state = give_confidence(db, grading_id, "hesitant", 40)

    assert (state.status, state.correct, state.priority) == ("done", True, False)
    assert [result.met for result in state.criteria] == [True, True]
    assert state.comment == "Bien vu."
    assert state.expected_answer.startswith("One extreme value moves the mean")
    assert answers(db) == [(why, ANSWER, 1, "hesitant", 40)]
    card = get_card(db, why)
    assert card is not None
    assert card.due > NOW  # its next date


def test_r6_the_confidence_may_come_before_the_grading(db: sqlite3.Connection) -> None:
    session_id, why = open_answer(db)
    grading_id = start_grading(db, session_id, why, ANSWER)

    assert give_confidence(db, grading_id, "sure", 20).status == "pending"
    assert answers(db) == []
    run_grading(db, grading_id, grader(True, False))

    state = grading_state(db, grading_id)
    assert state is not None
    assert (state.correct, state.priority) == (False, True)  # wrong while sure (R10)
    assert answers(db) == [(why, ANSWER, 0, "sure", 20)]


def test_an_answer_enters_the_history_once_only(db: sqlite3.Connection) -> None:
    session_id, why = open_answer(db)
    grading_id = start_grading(db, session_id, why, ANSWER)

    give_confidence(db, grading_id, "sure", 20)
    give_confidence(db, grading_id, "guess", 25)  # a second click changes nothing
    run_grading(db, grading_id, grader(True, True))
    run_grading(db, grading_id, grader(False, False))  # graded already

    assert answers(db) == [(why, ANSWER, 1, "sure", 20)]


def test_the_answer_keeps_the_time_it_was_written(db: sqlite3.Connection) -> None:
    session_id, why = open_answer(db)
    grading_id = start_grading(db, session_id, why, ANSWER)
    with db:
        db.execute(
            "UPDATE grading SET written_at = '2026-11-20T08:00:00Z' WHERE id = ?",
            (grading_id,),
        )

    give_confidence(db, grading_id, "sure", 20)
    run_grading(db, grading_id, grader(True, True))

    assert db.execute("SELECT answered_at FROM answer").fetchone() == (
        "2026-11-20T08:00:00Z",
    )


def test_a_question_waiting_for_its_grading_leaves_the_queue(
    db: sqlite3.Connection,
) -> None:
    session_id, why = open_answer(db)
    grading_id = start_grading(db, session_id, why, ANSWER)
    # Written but not validated: the answer is not given yet.
    assert [due.question_id for due in due_questions(db, NOW)] == [why]

    give_confidence(db, grading_id, "sure", 20)

    assert due_questions(db, NOW) == []


@pytest.mark.parametrize(
    "error",
    [
        InvalidAnswer("criteria: one result missing"),
        EngineTimeout("Claude n'a pas répondu à temps."),
        RuntimeError("a bug"),
    ],
)
def test_a_grading_that_cannot_be_done_fails_and_its_question_stays_due(
    db: sqlite3.Connection, error: Exception
) -> None:
    session_id, why = open_answer(db)
    grading_id = start_grading(db, session_id, why, ANSWER)
    give_confidence(db, grading_id, "sure", 20)

    run_grading(db, grading_id, failing(error))

    state = grading_state(db, grading_id)
    assert state is not None
    assert (state.status, state.detail) == ("failed", str(error))
    assert answers(db) == []
    assert [due.question_id for due in due_questions(db, NOW)] == [why]


def test_an_open_answer_waits_for_claude_when_it_is_unavailable(
    db: sqlite3.Connection,
) -> None:
    session_id, why = open_answer(db)
    grading_id = start_grading(db, session_id, why, ANSWER)
    give_confidence(db, grading_id, "sure", 20)

    grade_or_wait(db, grading_id, failing(EngineUnavailable("Limite atteinte.")))

    state = grading_state(db, grading_id)
    assert state is not None
    assert state.status == "pending"
    assert db.execute("SELECT kind, input FROM ai_task").fetchall() == [
        (TASK, json.dumps({"grading_id": grading_id}))
    ]
    # Claude is back: the worker grades it, and the answer enters the history.
    run_next_task(db, {TASK: grading_handler(grader(True, True))}, NOW)
    assert answers(db) == [(why, ANSWER, 1, "sure", 20)]


def test_the_gradings_cut_by_the_end_of_the_app_resume(db: sqlite3.Connection) -> None:
    session_id, why = open_answer(db)
    validated = start_grading(db, session_id, why, ANSWER)
    give_confidence(db, validated, "sure", 20)
    start_grading(db, session_id, why, "Never validated: no confidence chosen.")

    resume_gradings(db)
    resume_gradings(db)  # queued once

    assert db.execute("SELECT input FROM ai_task").fetchall() == [
        (json.dumps({"grading_id": validated}),)
    ]


def test_only_a_written_open_answer_goes_to_claude(db: sqlite3.Connection) -> None:
    notion_id, reviews = make_subject(db)

    with pytest.raises(ValueError, match="not an open answer"):
        start_grading(db, None, reviews[0], ANSWER)
    with pytest.raises(ValueError, match="Écris ta réponse"):
        start_grading(db, None, question_of(db, notion_id, "open"), "   ")
    assert grading_state(db, 99) is None
