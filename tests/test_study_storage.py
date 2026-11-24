"""Tests of the storage of studying: cards, answers, sessions, thoughts, wanderings."""

import sqlite3
from datetime import UTC, date, datetime

import pytest
from fsrs import Card, State
from test_content import MCQ, make_chapter

from bosh_mow.content.repository import NewNotion, save_notions
from bosh_mow.study.repository import (
    NewAnswer,
    add_thought,
    add_wandering,
    decide_thought,
    end_session,
    get_card,
    record_answer,
    save_card,
    start_session,
    undecided_thoughts,
)

TODAY = date(2026, 11, 24)


def make_question(db: sqlite3.Connection) -> int:
    chapter_id, file_id = make_chapter(db)
    (notion_id,) = save_notions(
        db, chapter_id, [NewNotion("V", "…", file_id, 4, 6, [MCQ])]
    )
    (question_id,) = db.execute(
        "SELECT id FROM question WHERE notion_id = ?", (notion_id,)
    ).fetchone()
    return question_id


def test_a_card_comes_back_as_it_was_saved(db: sqlite3.Connection) -> None:
    question_id = make_question(db)
    card = Card(
        card_id=question_id,
        state=State.Review,
        step=None,
        stability=3.2,
        difficulty=5.1,
        due=datetime(2026, 11, 30, 18, 0, tzinfo=UTC),
        last_review=datetime(2026, 11, 24, 18, 0, tzinfo=UTC),
    )

    save_card(db, card)

    saved = get_card(db, question_id)
    assert saved is not None
    assert saved.to_dict() == card.to_dict()


def test_a_question_without_card_has_not_entered_the_reviews(
    db: sqlite3.Connection,
) -> None:
    assert get_card(db, make_question(db)) is None


def test_r6_an_answer_keeps_the_choice_the_confidence_and_the_time(
    db: sqlite3.Connection,
) -> None:
    question_id = make_question(db)
    session_id = start_session(db, "queue", TODAY)

    record_answer(
        db, NewAnswer(question_id, session_id, True, "sure", 12, chosen_option=1)
    )
    # "Je ne sais pas": no option, no text, no confidence.
    record_answer(db, NewAnswer(question_id, session_id, False, None, 3))

    rows = db.execute(
        "SELECT chosen_option, answer_text, correct, confidence, seconds FROM answer"
        " ORDER BY id"
    ).fetchall()
    assert rows == [(1, None, 1, "sure", 12), (None, None, 0, None, 3)]


def test_r26_a_session_counts_for_its_day(db: sqlite3.Connection) -> None:
    session_id = start_session(db, "queue", TODAY)

    end_session(db, session_id, completed=True)

    row = db.execute(
        "SELECT kind, day, ended_at IS NOT NULL, completed FROM study_session"
    ).fetchone()
    assert row == ("queue", "2026-11-24", 1, 1)


def test_r17_thoughts_wait_for_a_decision(db: sqlite3.Connection) -> None:
    session_id = start_session(db, "queue", TODAY)
    message = add_thought(db, session_id, "  Répondre au message de Léa ")
    add_thought(db, session_id, "Acheter du café")
    assert [t.text for t in undecided_thoughts(db, session_id)] == [
        "Répondre au message de Léa",
        "Acheter du café",
    ]

    decide_thought(db, message, datetime(2026, 11, 24, 21, 30))
    remaining = undecided_thoughts(db, session_id)
    decide_thought(db, remaining[0].id, None)

    assert undecided_thoughts(db, session_id) == []
    assert db.execute(
        "SELECT decision, planned_for FROM thought ORDER BY id"
    ).fetchall() == [
        ("planned", "2026-11-24T21:30"),
        ("dropped", None),
    ]
    with pytest.raises(ValueError, match="needs a text"):
        add_thought(db, session_id, "  ")


def test_r18_a_wandering_is_counted_on_the_question_shown(
    db: sqlite3.Connection,
) -> None:
    question_id = make_question(db)
    session_id = start_session(db, "queue", TODAY)

    add_wandering(db, session_id, question_id)

    assert db.execute(
        "SELECT session_id, question_id FROM mind_wandering"
    ).fetchall() == [(session_id, question_id)]
