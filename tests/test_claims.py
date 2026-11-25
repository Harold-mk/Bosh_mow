"""Tests of "Je pense avoir juste" (T5): a value or a short answer that the code found
wrong goes to Claude (T6); if Claude agrees, the answer becomes right in the history,
its question is rescheduled, and its wording joins the accepted answers."""

import sqlite3

import pytest
from test_gradings import failing, grader
from test_sessions import NOW, make_subject, question_of

from bosh_mow.ai.gateway import EngineUnavailable, InvalidAnswer
from bosh_mow.ai.tasks import run_next_task
from bosh_mow.content.repository import get_question
from bosh_mow.grading.claims import claim_question
from bosh_mow.study.claims import (
    TASK,
    claim_handler,
    claim_state,
    judge_claim,
    make_claim,
)
from bosh_mow.study.repository import get_card
from bosh_mow.study.sessions import answer

QUARTER = {"value": 0.25, "tolerance": 0.01, "explanation": "Un quart."}
HAVING = {"accepted": ["HAVING", "having clause"], "explanation": "Après GROUP BY."}


# What Claude is asked


def test_a_claim_on_a_value_says_what_the_app_read() -> None:
    question = claim_question("What is one quarter?", "value", QUARTER, "25 %")

    assert question.statement == "What is one quarter?"
    assert question.expected_answer == "0.25. Un quart."
    (criterion,) = question.criteria
    assert "0.25" in criterion
    assert "1 %" in criterion  # the tolerance
    assert "it read 25 in the answer, 9900.0 % away" in criterion
    assert question.frequent_errors == []


def test_a_claim_on_a_value_that_is_not_a_number() -> None:
    question = claim_question("What is one quarter?", "value", QUARTER, "a quarter")

    assert "it read no number in the answer" in question.criteria[0]


def test_a_claim_on_a_short_answer_gives_its_accepted_answers() -> None:
    question = claim_question("Which clause?", "short", HAVING, "the HAVING clause")

    assert question.expected_answer == "HAVING / having clause. Après GROUP BY."
    assert "synonym" in question.criteria[0]


def test_only_a_value_or_a_short_answer_is_claimed() -> None:
    with pytest.raises(ValueError, match="value or a short answer"):
        claim_question("Why?", "open", {}, "Because.")


# The claim, from the answer to the decision


def wrong_value(db: sqlite3.Connection, text: str = "8") -> tuple[int, int]:
    """A value answered wrong while sure: (question, answer)."""
    notion_id, _ = make_subject(db)
    value = question_of(db, notion_id, "value")
    correction = answer(db, None, value, None, "sure", 20, NOW, answer_text=text)
    assert not correction.correct
    return value, correction.answer_id


def test_a_claim_accepted_makes_the_answer_right_and_its_wording_accepted(
    db: sqlite3.Connection,
) -> None:
    value, answer_id = wrong_value(db, "quatre")
    wrong_due = get_card(db, value)
    assert wrong_due is not None
    claim_id = make_claim(db, answer_id)

    judge_claim(db, claim_id, grader(True))

    state = claim_state(db, claim_id)
    assert state is not None
    assert (state.status, state.comment) == ("accepted", "Bien vu.")
    assert db.execute(
        "SELECT correct FROM answer WHERE id = ?", (answer_id,)
    ).fetchone() == (1,)
    card = get_card(db, value)
    assert card is not None
    assert card.due > wrong_due.due  # rescheduled as right: it comes back later
    question = get_question(db, value)
    assert question is not None
    assert question.content["accepted"] == ["quatre"]  # right at once, next time


def test_a_claim_refused_changes_nothing(db: sqlite3.Connection) -> None:
    value, answer_id = wrong_value(db)
    before = get_card(db, value)
    claim_id = make_claim(db, answer_id)

    judge_claim(db, claim_id, grader(False))

    state = claim_state(db, claim_id)
    assert state is not None
    assert state.status == "refused"
    assert db.execute(
        "SELECT correct FROM answer WHERE id = ?", (answer_id,)
    ).fetchone() == (0,)
    assert get_card(db, value) == before


def test_a_claim_that_cannot_be_judged_fails_and_says_why(
    db: sqlite3.Connection,
) -> None:
    _, answer_id = wrong_value(db)
    claim_id = make_claim(db, answer_id)

    judge_claim(db, claim_id, failing(InvalidAnswer("criteria: missing")))

    state = claim_state(db, claim_id)
    assert state is not None
    assert (state.status, state.detail) == ("failed", "criteria: missing")


def test_a_claim_waits_for_claude_in_the_background(db: sqlite3.Connection) -> None:
    _, answer_id = wrong_value(db)
    claim_id = make_claim(db, answer_id)

    # Claude unavailable: the claim waits; then the worker judges it.
    run_next_task(
        db, {TASK: claim_handler(failing(EngineUnavailable("Hors ligne.")))}, NOW
    )
    state = claim_state(db, claim_id)
    assert state is not None
    assert state.status == "pending"
    db.execute("UPDATE ai_task SET not_before = NULL")
    db.commit()
    run_next_task(db, {TASK: claim_handler(grader(True))}, NOW)

    state = claim_state(db, claim_id)
    assert state is not None
    assert state.status == "accepted"


def test_a_short_answer_claimed_is_accepted_the_next_time(
    db: sqlite3.Connection,
) -> None:
    notion_id, _ = make_subject(db, short=True)
    short = question_of(db, notion_id, "short")
    first = answer(db, None, short, None, "hesitant", 9, NOW, answer_text="impartial")
    assert not first.correct
    judge_claim(db, make_claim(db, first.answer_id), grader(True))

    assert answer(
        db, None, short, None, "hesitant", 9, NOW, answer_text="Impartial"
    ).correct


def test_only_a_wrong_written_answer_can_be_claimed_once(
    db: sqlite3.Connection,
) -> None:
    notion_id, reviews = make_subject(db)
    value = question_of(db, notion_id, "value")
    right = answer(db, None, value, None, "sure", 9, NOW, answer_text="4")
    dont_know = answer(db, None, value, None, None, 3, NOW)
    mcq = answer(db, None, reviews[0], 2, "sure", 5, NOW)
    wrong = answer(db, None, value, None, "sure", 9, NOW, answer_text="8")
    make_claim(db, wrong.answer_id)

    for answer_id, why in [
        (right.answer_id, "right already"),
        (dont_know.answer_id, "no answer"),
        (mcq.answer_id, "value or a short answer"),
        (wrong.answer_id, "claimed already"),
        (999, "does not exist"),
    ]:
        with pytest.raises(ValueError, match=why):
            make_claim(db, answer_id)
