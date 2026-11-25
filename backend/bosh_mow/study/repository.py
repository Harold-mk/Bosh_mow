"""Storage of studying: the FSRS card of each question, the sessions, the answers, and
the thoughts and wanderings noted during a session (R6 to R18)."""

import sqlite3
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Literal

from fsrs import Card, State

from bosh_mow.study.days import DaySession, SessionKind
from bosh_mow.study.queue import DueQuestion

type Confidence = Literal["sure", "hesitant", "guess"]  # sûr, hésitant, au hasard (R6)


@dataclass(frozen=True)
class NewAnswer:
    question_id: int
    session_id: int | None
    correct: bool
    confidence: Confidence | None  # None: "Je ne sais pas", which needs no confidence
    seconds: int  # time taken to answer
    chosen_option: int | None = None  # an MCQ: the option chosen, from 1
    answer_text: str | None = None  # the other formats; both None: "Je ne sais pas"
    answered_at: datetime | None = None  # None: now; an open answer is graded later


@dataclass(frozen=True)
class Thought:
    """A thought put aside with the P key (R17)."""

    id: int
    text: str


def get_card(connection: sqlite3.Connection, question_id: int) -> Card | None:
    """The FSRS card of a question, or None while it has not entered the reviews."""
    row = connection.execute(
        "SELECT question_id, state, step, stability, difficulty, due, last_review"
        " FROM card WHERE question_id = ?",
        (question_id,),
    ).fetchone()
    if row is None:
        return None
    question, state, step, stability, difficulty, due, last_review = row
    return Card(
        card_id=question,
        state=State(state),
        step=step,
        stability=stability,
        difficulty=difficulty,
        due=_moment(due),
        last_review=_moment(last_review) if last_review else None,
    )


def save_card(connection: sqlite3.Connection, card: Card) -> None:
    """Save the FSRS card of a question; its card_id is the question id."""
    with connection:
        connection.execute(
            "INSERT OR REPLACE INTO card"
            " (question_id, state, step, stability, difficulty, due, last_review)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                card.card_id,
                card.state.value,
                card.step,
                card.stability,
                card.difficulty,
                _iso(card.due),
                _iso(card.last_review) if card.last_review else None,
            ),
        )


def record_answer(connection: sqlite3.Connection, answer: NewAnswer) -> int:
    """Add an answer to the history, the only source of the statistics."""
    with connection:
        return connection.execute(
            "INSERT INTO answer (question_id, session_id, answered_at, chosen_option,"
            " answer_text, correct, confidence, seconds)"
            " VALUES (?, ?, COALESCE(?, strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),"
            " ?, ?, ?, ?, ?)",
            (
                answer.question_id,
                answer.session_id,
                _iso(answer.answered_at) if answer.answered_at else None,
                answer.chosen_option,
                answer.answer_text,
                answer.correct,
                answer.confidence,
                answer.seconds,
            ),
        ).lastrowid


def start_session(
    connection: sqlite3.Connection,
    kind: SessionKind,
    day: date,
    notion_id: int | None = None,
    planned: int | None = None,
) -> int:
    """Start a session that counts for the local calendar day `day` (R26).

    `planned`: for the daily queue, how many questions it has at its start.
    """
    with connection:
        return connection.execute(
            "INSERT INTO study_session (kind, notion_id, planned, day)"
            " VALUES (?, ?, ?, ?)",
            (kind, notion_id, planned, day.isoformat()),
        ).lastrowid


def minutes_studied(connection: sqlite3.Connection, day: date) -> int:
    """The minutes of the sessions of a day that have ended."""
    (seconds,) = connection.execute(
        "SELECT COALESCE(SUM(unixepoch(ended_at) - unixepoch(started_at)), 0)"
        " FROM study_session WHERE day = ? AND ended_at IS NOT NULL",
        (day.isoformat(),),
    ).fetchone()
    return seconds // 60


def day_sessions(connection: sqlite3.Connection) -> list[DaySession]:
    """Every session, as it counts for its day (R26)."""
    rows = connection.execute(
        "SELECT day, kind, completed, planned FROM study_session ORDER BY id"
    ).fetchall()
    return [
        DaySession(date.fromisoformat(day), kind, bool(completed), planned)
        for day, kind, completed, planned in rows
    ]


def due_questions(connection: sqlite3.Connection, now: datetime) -> list[DueQuestion]:
    """The questions due by `now` in the active subjects, except the reported ones and
    those whose answer, already given, waits for its grading by Claude (T6)."""
    rows = connection.execute(
        """
        SELECT c.question_id, s.id, c.due
        FROM card c
        JOIN question q ON q.id = c.question_id
        JOIN notion n ON n.id = q.notion_id
        JOIN chapter ch ON ch.id = n.chapter_id
        JOIN subject s ON s.id = ch.subject_id
        WHERE s.status = 'active' AND q.reported_at IS NULL AND c.due <= ?
          AND NOT EXISTS (
            SELECT 1 FROM grading g
            WHERE g.question_id = q.id AND g.confidence IS NOT NULL
              AND g.recorded_at IS NULL AND g.status != 'failed'
          )
        """,
        (_iso(now),),
    ).fetchall()
    return [
        DueQuestion(question_id, subject_id, _moment(due))
        for question_id, subject_id, due in rows
    ]


def end_session(
    connection: sqlite3.Connection, session_id: int, completed: bool
) -> None:
    """End a session; `completed`: the queue is done or its time is up, the notion
    studied to the end."""
    with connection:
        connection.execute(
            "UPDATE study_session SET ended_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now'),"
            " completed = ? WHERE id = ?",
            (completed, session_id),
        )


def add_thought(connection: sqlite3.Connection, session_id: int, text: str) -> int:
    """Put a thought aside without leaving the question (R17)."""
    if not text.strip():
        raise ValueError("A thought needs a text.")
    with connection:
        return connection.execute(
            "INSERT INTO thought (session_id, text) VALUES (?, ?)",
            (session_id, text.strip()),
        ).lastrowid


def decide_thought(
    connection: sqlite3.Connection, thought_id: int, planned_for: datetime | None
) -> None:
    """Plan a thought for a precise moment (local time), or drop it (None)."""
    decision = "dropped" if planned_for is None else "planned"
    when = planned_for.strftime("%Y-%m-%dT%H:%M") if planned_for else None
    with connection:
        connection.execute(
            "UPDATE thought SET decision = ?, planned_for = ? WHERE id = ?",
            (decision, when, thought_id),
        )


def undecided_thoughts(
    connection: sqlite3.Connection, session_id: int
) -> list[Thought]:
    """The thoughts of a session still to plan or drop: it cannot end before (R17)."""
    rows = connection.execute(
        "SELECT id, text FROM thought WHERE session_id = ? AND decision IS NULL"
        " ORDER BY id",
        (session_id,),
    ).fetchall()
    return [Thought(*row) for row in rows]


def add_wandering(
    connection: sqlite3.Connection, session_id: int, question_id: int | None
) -> None:
    """Count a moment when the mind wandered, on the question shown (R18)."""
    with connection:
        connection.execute(
            "INSERT INTO mind_wandering (session_id, question_id) VALUES (?, ?)",
            (session_id, question_id),
        )


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _moment(text: str) -> datetime:
    return datetime.fromisoformat(text)
