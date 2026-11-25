"""Tests of the sessions as the interface drives them: queue, answers, notions."""

import sqlite3
from datetime import UTC, date, datetime, timedelta

import pytest
from fsrs import Card, State
from test_preparation import OTHER_STATEMENTS, STATEMENTS, questions

from bosh_mow.ai.schemas import T2Answer
from bosh_mow.content.preparation import to_questions
from bosh_mow.content.repository import (
    NewNotion,
    get_notions,
    get_questions,
    save_notions,
)
from bosh_mow.study.repository import add_thought, decide_thought, get_card, save_card
from bosh_mow.study.sessions import (
    answer,
    finish,
    next_notion,
    next_question,
    start_notion,
    start_queue,
    today,
)
from bosh_mow.subjects.repository import (
    Chapter,
    ChapterSource,
    Document,
    PageContent,
    activate_subject,
    add_resource,
    chapter_ids,
    create_draft_subject,
)

NOW = datetime(2026, 11, 24, 18, 0, tzinfo=UTC)
TODAY = date(2026, 11, 24)


def make_subject(
    db: sqlite3.Connection,
    name: str = "Statistiques",
    exam: date = date(2027, 1, 15),
    statements: list[str] = STATEMENTS,
) -> tuple[int, list[int]]:
    """A subject of two chapters, the first with one validated notion of 7 questions:
    (notion id, ids of its 3 review MCQs)."""
    subject_id = create_draft_subject(db, name, exam)
    pages = [PageContent(f"Page {number}") for number in range(1, 13)]
    file_id = add_resource(
        db, subject_id, f"{name}.pdf", Document("pdf", pages, [], "none")
    )
    activate_subject(
        db,
        subject_id,
        ["Être capable de mesurer la dispersion"],
        [
            Chapter("Dispersion", "core", [ChapterSource(file_id, 1, 6)], [1]),
            Chapter("Quartiles", "core", [ChapterSource(file_id, 7, 12)], [1]),
        ],
    )
    first, _ = chapter_ids(db, subject_id)
    written = to_questions(T2Answer.model_validate(questions(statements)))
    variance = NewNotion("Variance", "Pourquoi n − 1.", file_id, 1, 6, written)
    (notion_id,) = save_notions(db, first, [variance])
    reviews = [
        q.id
        for q in get_questions(db, notion_id)
        if q.role == "review" and q.format == "mcq"
    ]
    return notion_id, reviews


def make_due(
    db: sqlite3.Connection, question_ids: list[int], minutes_ago: int = 60
) -> None:
    for question_id in question_ids:
        due = NOW - timedelta(minutes=minutes_ago)
        save_card(
            db,
            Card(
                card_id=question_id,
                state=State.Review,
                stability=2.0,
                difficulty=5.0,
                due=due,
            ),
        )


# The day and the daily queue


def test_today_counts_the_queue_and_the_successful_days(db: sqlite3.Connection) -> None:
    _, reviews = make_subject(db)
    make_due(db, reviews)
    assert today(db, TODAY, NOW).due == 3

    session_id = start_queue(db, TODAY, NOW)
    assert finish(db, session_id, completed=True, day=TODAY)

    day = today(db, TODAY, NOW)
    assert (day.successful_days, day.minimum_done) == (1, True)


def test_the_queue_gives_one_question_at_a_time_without_its_correction(
    db: sqlite3.Connection,
) -> None:
    _, reviews = make_subject(db)
    make_due(db, reviews[:1])
    session_id = start_queue(db, TODAY, NOW)

    question = next_question(db, session_id, NOW)

    assert question is not None
    assert question.id == reviews[0]
    assert sorted(option.number for option in question.options) == [1, 2, 3]
    assert not hasattr(question.options[0], "correct")
    assert question.subject == "Statistiques"


def test_r9_the_subject_changes_from_one_question_to_the_next(
    db: sqlite3.Connection,
) -> None:
    _, stats = make_subject(db)
    _, other = make_subject(db, "Probabilités", statements=OTHER_STATEMENTS)
    make_due(db, stats, minutes_ago=120)  # the most urgent
    make_due(db, other)
    session_id = start_queue(db, TODAY, NOW)
    first = next_question(db, session_id, NOW)
    assert first is not None
    assert first.subject == "Statistiques"

    answer(db, session_id, first.id, 1, "sure", 10, NOW)
    second = next_question(db, session_id, NOW)

    assert second is not None
    assert second.subject == "Probabilités"


def test_t5_an_answer_is_graded_and_sets_the_next_date(db: sqlite3.Connection) -> None:
    _, reviews = make_subject(db)

    correction = answer(db, None, reviews[0], 1, "sure", 12, NOW)

    assert (correction.correct, correction.correct_option, correction.priority) == (
        True,
        1,
        False,
    )
    assert correction.explanations == ["C'est ça.", "Erreur fréquente.", "Non."]
    card = get_card(db, reviews[0])
    assert card is not None
    assert card.due > NOW


def test_r10_a_mistake_made_while_sure_comes_first(db: sqlite3.Connection) -> None:
    _, reviews = make_subject(db)

    assert answer(db, None, reviews[0], 2, "sure", 12, NOW).priority
    assert not answer(db, None, reviews[1], 2, "hesitant", 12, NOW).priority


def test_r6_an_answer_needs_its_confidence_but_dont_know_does_not(
    db: sqlite3.Connection,
) -> None:
    _, reviews = make_subject(db)

    with pytest.raises(ValueError, match="confiance"):
        answer(db, None, reviews[0], 1, None, 12, NOW)
    assert not answer(
        db, None, reviews[0], None, None, 4, NOW
    ).correct  # Je ne sais pas


def test_r7_a_failed_question_comes_back_in_the_session(db: sqlite3.Connection) -> None:
    _, reviews = make_subject(db)
    make_due(db, reviews[:1])
    session_id = start_queue(db, TODAY, NOW)

    answer(db, session_id, reviews[0], 2, "hesitant", 15, NOW)

    assert next_question(db, session_id, NOW) is None  # not right away…
    # A known question failed is relearned: it comes back 10 minutes later.
    again = next_question(db, session_id, NOW + timedelta(minutes=11))
    assert again is not None  # …but a little later
    assert again.id == reviews[0]


# Studying a notion (R13)


def test_r13_a_notion_session_gives_its_pretests_then_its_test(
    db: sqlite3.Connection,
) -> None:
    notion_id, reviews = make_subject(db)

    session = start_notion(db, notion_id, TODAY)

    assert [q.role for q in session.pretests] == ["pretest", "pretest"]
    assert [q.id for q in session.tests] == reviews  # the MCQs only, in lot 2
    answer(db, session.session_id, session.pretests[0].id, 1, "guess", 8, NOW)
    answer(db, session.session_id, session.tests[0].id, 1, "sure", 8, NOW)
    assert get_card(db, session.pretests[0].id) is None  # a pretest has no date
    assert get_card(db, session.tests[0].id) is not None  # a test enters the reviews
    finish(db, session.session_id, completed=True, day=TODAY)
    (studied,) = get_notions(db, _chapter_of(db, notion_id))
    assert studied.studied


def _chapter_of(db: sqlite3.Connection, notion_id: int) -> int:
    (chapter_id,) = db.execute(
        "SELECT chapter_id FROM notion WHERE id = ?", (notion_id,)
    ).fetchone()
    return chapter_id


def test_starting_a_chapter_asks_for_the_next_one(db: sqlite3.Connection) -> None:
    notion_id, _ = make_subject(db)

    start_notion(db, notion_id, TODAY)
    start_notion(db, notion_id, TODAY)  # asked once only

    tasks = db.execute("SELECT kind, input FROM ai_task").fetchall()
    assert tasks == [("t1_pass2", '{"chapter_id": 2}')]  # its notions


def test_r17_a_session_ends_once_its_thoughts_are_sorted(
    db: sqlite3.Connection,
) -> None:
    session_id = start_queue(db, TODAY, NOW)
    thought = add_thought(db, session_id, "Rappeler le dentiste")

    with pytest.raises(ValueError, match="pensées à trier"):
        finish(db, session_id, completed=True, day=TODAY)

    decide_thought(db, thought, None)
    finish(db, session_id, completed=True, day=TODAY)


def test_the_next_notion_comes_from_the_closest_exam(db: sqlite3.Connection) -> None:
    later, _ = make_subject(db, exam=date(2027, 3, 1))
    sooner, _ = make_subject(db, "Probabilités", date(2027, 1, 10), OTHER_STATEMENTS)

    first = next_notion(db)
    assert first is not None
    assert first.id == sooner
    session = start_notion(db, sooner, TODAY)
    finish(db, session.session_id, completed=True, day=TODAY)

    following = next_notion(db)
    assert following is not None
    assert following.id == later


def test_a_notion_is_studied_once_its_questions_are_written(
    db: sqlite3.Connection,
) -> None:
    ready, _ = make_subject(db, exam=date(2027, 3, 1))
    waiting, _ = make_subject(db, "Probabilités", date(2027, 1, 10), OTHER_STATEMENTS)
    db.execute("DELETE FROM question WHERE notion_id = ?", (waiting,))  # not written
    db.commit()

    following = next_notion(db)

    assert following is not None
    assert following.id == ready  # the closer exam waits for its questions
    with pytest.raises(ValueError, match="pas encore prêtes"):
        start_notion(db, waiting, TODAY)
