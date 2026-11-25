"""Tests of the sessions as the interface drives them: queue, answers, notions."""

import sqlite3
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from fsrs import Card, State
from test_preparation import OTHER_STATEMENTS, STATEMENTS, questions

from bosh_mow.ai.schemas import T2Answer
from bosh_mow.content.preparation import to_questions
from bosh_mow.content.repository import (
    NewNotion,
    get_notions,
    get_questions,
    mark_studied,
    save_notions,
)
from bosh_mow.db.migrate import MIGRATIONS_DIR
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


def with_short_answer(raw: dict[str, Any]) -> dict[str, Any]:
    """The questions of T2 with a short answer in place of the value."""
    seven = raw["questions"]
    short = {
        **seven[5],
        "type": "concept",
        "format": "short",
        "value": None,
        "tolerance": None,
        "accepted": ["unbiased", "sans biais"],
        "explanation": "Diviser par n − 1 corrige le biais.",
    }
    return {"questions": [*seven[:5], short, *seven[6:]]}


def question_of(db: sqlite3.Connection, notion_id: int, form: str) -> int:
    """The id of the review question of a notion in the format `form`."""
    (found,) = [
        q.id
        for q in get_questions(db, notion_id)
        if q.format == form and q.role == "review"
    ]
    return found


def make_subject(
    db: sqlite3.Connection,
    name: str = "Statistiques",
    exam: date = date(2027, 1, 15),
    statements: list[str] = STATEMENTS,
    short: bool = False,
) -> tuple[int, list[int]]:
    """A subject of two chapters, the first with one validated notion of 7 questions,
    with a value or, if `short`, a short answer: (notion id, ids of its 3 review
    MCQs)."""
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
    raw = questions(statements)
    written = to_questions(
        T2Answer.model_validate(with_short_answer(raw) if short else raw)
    )
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


# Values and short answers, graded without AI too (T5)


def test_a_value_is_asked_without_options_but_with_its_tolerance(
    db: sqlite3.Connection,
) -> None:
    notion_id, _ = make_subject(db)
    value = question_of(db, notion_id, "value")
    make_due(db, [value])
    session_id = start_queue(db, TODAY, NOW)

    question = next_question(db, session_id, NOW)

    assert question is not None
    assert (question.id, question.format, question.options, question.tolerance) == (
        value,
        "value",
        [],
        0.01,
    )


def test_t5_a_value_is_graded_and_its_text_saved(db: sqlite3.Connection) -> None:
    notion_id, _ = make_subject(db)
    value = question_of(db, notion_id, "value")

    right = answer(db, None, value, None, "hesitant", 20, NOW, answer_text=" 4,0 ")
    wrong = answer(db, None, value, None, "sure", 20, NOW, answer_text="8")

    assert (right.correct, right.expected, right.correct_option) == (True, "4", None)
    assert right.explanation is not None and right.explanation.startswith("Moyenne 4")
    assert (wrong.correct, wrong.priority) == (False, True)  # wrong while sure (R10)
    saved = db.execute(
        "SELECT answer_text, chosen_option, correct FROM answer"
    ).fetchall()
    assert saved == [("4,0", None, 1), ("8", None, 0)]
    assert get_card(db, value) is not None  # a review question: it has its next date


def test_t5_a_short_answer_is_graded_with_one_typo_tolerated(
    db: sqlite3.Connection,
) -> None:
    notion_id, _ = make_subject(db, short=True)
    short = question_of(db, notion_id, "short")

    typo = answer(db, None, short, None, "hesitant", 9, NOW, answer_text="Unbiassed")
    wrong = answer(db, None, short, None, "hesitant", 9, NOW, answer_text="biased")

    assert typo.correct
    assert (wrong.correct, wrong.expected) == (False, "unbiased")


def test_r6_a_written_answer_needs_its_confidence_but_dont_know_does_not(
    db: sqlite3.Connection,
) -> None:
    notion_id, _ = make_subject(db)
    value = question_of(db, notion_id, "value")

    with pytest.raises(ValueError, match="confiance"):
        answer(db, None, value, None, None, 5, NOW, answer_text="4")
    assert not answer(db, None, value, None, None, 5, NOW).correct  # Je ne sais pas
    assert not answer(db, None, value, None, None, 5, NOW, answer_text="  ").correct
    assert db.execute("SELECT answer_text, confidence FROM answer").fetchall() == [
        (None, None),
        (None, None),
    ]


def test_an_open_answer_is_not_graded_by_the_code(db: sqlite3.Connection) -> None:
    notion_id, _ = make_subject(db)
    why = question_of(db, notion_id, "open")

    with pytest.raises(ValueError, match="Claude"):
        answer(db, None, why, None, "sure", 30, NOW, answer_text="Extreme values.")


def test_the_notions_studied_before_put_their_values_in_the_reviews(
    db: sqlite3.Connection,
) -> None:
    """Migration 010: a notion studied in lot 2 asked only its MCQs."""
    studied, reviews = make_subject(db)
    mark_studied(db, studied)
    make_due(db, reviews)
    later, _ = make_subject(db, "Probabilités", statements=OTHER_STATEMENTS, short=True)
    migration = MIGRATIONS_DIR / "010_review_values_and_short_answers.sql"

    db.executescript(migration.read_text(encoding="utf-8"))
    db.executescript(migration.read_text(encoding="utf-8"))  # harmless a second time

    value = question_of(db, studied, "value")
    card = get_card(db, value)
    assert card is not None
    assert (card.state, card.step) == (State.Learning, 0)
    assert card.due <= datetime.now(UTC)
    assert get_card(db, question_of(db, studied, "open")) is None  # graded by Claude
    assert get_card(db, question_of(db, later, "short")) is None  # not studied yet
    answer(db, None, value, None, "sure", 9, NOW, answer_text="4")  # a card as FSRS's
    answered = get_card(db, value)
    assert answered is not None and answered.stability is not None


# Studying a notion (R13)


def test_r13_a_notion_session_gives_its_pretests_then_its_test(
    db: sqlite3.Connection,
) -> None:
    notion_id, reviews = make_subject(db)

    session = start_notion(db, notion_id, TODAY)

    assert [q.role for q in session.pretests] == ["pretest", "pretest"]
    # The open answer waits for its grading by Claude.
    assert [q.format for q in session.tests] == ["mcq", "mcq", "mcq", "value"]
    assert [q.id for q in session.tests[:3]] == reviews
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


def test_r15_a_notion_starts_with_a_question_already_succeeded(
    db: sqlite3.Connection,
) -> None:
    first, reviews = make_subject(db)
    second, _ = make_subject(db, "Probabilités", date(2027, 1, 10), OTHER_STATEMENTS)
    assert start_notion(db, second, TODAY).warmup is None  # nothing succeeded yet

    session = start_notion(db, first, TODAY).session_id
    answer(db, session, reviews[0], 1, "sure", 8, NOW)  # right
    answer(db, session, reviews[1], 2, "sure", 8, NOW)  # wrong

    warmup = start_notion(db, second, TODAY).warmup
    assert warmup is not None
    assert warmup.id == reviews[0]
    assert start_notion(db, first, TODAY).warmup is None  # of another notion only
