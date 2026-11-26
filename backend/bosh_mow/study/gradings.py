"""Open answers in a session (T6): Claude grades them while the confidence is chosen.

The grading starts as soon as the answer is written, in its own thread, so that it
never waits behind a background task. The answer enters the history, and its question
gets its next date, once the grading is done and the confidence chosen, whichever comes
last, even after the end of the session. When Claude cannot answer, the local model
grades instead (D6): its grading is provisional, and Claude checks it later in the
background. When neither can, the grading waits for Claude as a background task; a
grading that cannot be done fails, and its question stays due.
"""

import json
import sqlite3
import threading
from collections.abc import Callable
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from bosh_mow.ai.gateway import EngineUnavailable
from bosh_mow.ai.tasks import Handler, add_task
from bosh_mow.content.repository import get_question
from bosh_mow.db.connection import connect
from bosh_mow.grading.open_answers import CriterionResult, OpenGrading, OpenQuestion
from bosh_mow.study.repository import (
    Confidence,
    NewAnswer,
    get_card,
    record_answer,
    save_card,
)
from bosh_mow.study.scheduling import PastAnswer, replay, review

TASK = "t6"  # a grading that waits for Claude, done by the background worker
VERIFY_TASK = "t6_verify"  # Claude checks a grading of the local model

type Grader = Callable[[OpenQuestion, str], OpenGrading]


@dataclass(frozen=True)
class GradingState:
    """Where the grading of an open answer stands, as the interface shows it."""

    id: int
    question_id: int
    status: str  # pending, done or failed
    correct: bool | None  # once done: every criterion met
    provisional: bool  # by the local model, until Claude checks it (D6)
    priority: bool  # a mistake made while sure: shown first (R10)
    criteria: list[CriterionResult]  # once done
    comment: str | None  # once done, in French
    expected_answer: str  # the model answer, shown with the correction
    detail: str | None  # why it failed


def start_grading(
    connection: sqlite3.Connection, session_id: int | None, question_id: int, text: str
) -> int:
    """Note an open answer as it is sent, to be graded at once; return its grading."""
    question = get_question(connection, question_id)
    if question is None:
        raise ValueError(f"Question {question_id} does not exist.")
    if question.format != "open":
        raise ValueError(f"Question {question_id} is not an open answer.")
    if not text.strip():
        raise ValueError("Écris ta réponse, ou choisis « Je ne sais pas ».")
    with connection:
        return connection.execute(
            "INSERT INTO grading (question_id, session_id, answer_text)"
            " VALUES (?, ?, ?)",
            (question_id, session_id, text.strip()),
        ).lastrowid


def grade_in_background(database: Path, grading_id: int, grade: Grader) -> None:
    """Grade an answer at once, in its own thread, with its own connection."""

    def work() -> None:
        with closing(connect(database)) as connection:
            grade_or_wait(connection, grading_id, grade)

    threading.Thread(target=work, name=f"grading-{grading_id}", daemon=True).start()


def grade_or_wait(
    connection: sqlite3.Connection, grading_id: int, grade: Grader
) -> None:
    """Grade an answer now; if Claude cannot answer now, the grading waits for it as a
    background task."""
    try:
        run_grading(connection, grading_id, grade)
    except EngineUnavailable:
        _wait_for_claude(connection, grading_id)


def run_grading(connection: sqlite3.Connection, grading_id: int, grade: Grader) -> None:
    """Grade an answer and save the result; the answer enters the history if its
    confidence is chosen. A grading that cannot be done fails, and says why; an engine
    unavailable raises EngineUnavailable, to be tried again later."""
    row = connection.execute(
        "SELECT question_id, answer_text FROM grading"
        " WHERE id = ? AND status = 'pending'",
        (grading_id,),
    ).fetchone()
    if row is None:
        return  # graded or failed meanwhile
    question_id, text = row
    question = get_question(connection, question_id)
    assert question is not None  # a grading goes with its question
    try:
        graded = grade(OpenQuestion.of(question.statement, question.content), text)
    except EngineUnavailable:
        raise
    except Exception as error:  # an invalid answer, too long, or a bug: say why
        _finish(connection, grading_id, "status = 'failed', detail = ?", (str(error),))
        return
    _finish(
        connection,
        grading_id,
        "status = 'done', result = ?, correct = ?, provisional = ?",
        (_result(graded), graded.correct, graded.provisional),
    )
    if graded.provisional:
        add_task(connection, VERIFY_TASK, {"grading_id": grading_id})
    _record(connection, grading_id)


def verify_grading(
    connection: sqlite3.Connection, grading_id: int, grade: Grader
) -> None:
    """Claude checks a provisional grading of the local model (D6), with `grade`, which
    asks Claude alone. Claude's grading stands; if its verdict differs, the answer is
    corrected in the history and its question rescheduled. An engine unavailable raises
    EngineUnavailable, to be tried again later."""
    row = connection.execute(
        "SELECT question_id, answer_text, correct, answer_id FROM grading"
        " WHERE id = ? AND status = 'done' AND provisional = 1",
        (grading_id,),
    ).fetchone()
    if row is None:
        return  # checked already
    question_id, text, correct, answer_id = row
    question = get_question(connection, question_id)
    assert question is not None  # a grading goes with its question
    graded = grade(OpenQuestion.of(question.statement, question.content), text)
    with connection:
        connection.execute(
            "UPDATE grading SET result = ?, correct = ?, provisional = 0 WHERE id = ?",
            (_result(graded), graded.correct, grading_id),
        )
    if answer_id is not None and bool(correct) != graded.correct:
        with connection:
            connection.execute(
                "UPDATE answer SET correct = ? WHERE id = ?",
                (graded.correct, answer_id),
            )
        reschedule(connection, question_id)


def reschedule(connection: sqlite3.Connection, question_id: int) -> None:
    """Set the next date of a review question from all its answers, when a verdict
    changed after the fact (FSRS)."""
    question = get_question(connection, question_id)
    if question is None or question.role != "review":
        return  # a pretest has no date
    rows = connection.execute(
        "SELECT answered_at, correct, confidence FROM answer WHERE question_id = ?"
        " ORDER BY answered_at, id",
        (question_id,),
    ).fetchall()
    card = replay(
        question_id,
        [
            PastAnswer(datetime.fromisoformat(at), bool(correct), confidence)
            for at, correct, confidence in rows
        ],
    )
    if card is not None:
        save_card(connection, card)


def give_confidence(
    connection: sqlite3.Connection,
    grading_id: int,
    confidence: Confidence,
    seconds: int,
) -> GradingState:
    """The confidence chosen after the answer was sent (R6); the first one counts."""
    with connection:
        connection.execute(
            "UPDATE grading SET confidence = ?, seconds = ?"
            " WHERE id = ? AND confidence IS NULL",
            (confidence, seconds, grading_id),
        )
    _record(connection, grading_id)
    state = grading_state(connection, grading_id)
    if state is None:
        raise ValueError(f"Grading {grading_id} does not exist.")
    return state


def grading_state(
    connection: sqlite3.Connection, grading_id: int
) -> GradingState | None:
    """Where the grading of an answer stands; None if there is no such grading."""
    row = connection.execute(
        "SELECT question_id, status, result, correct, provisional, confidence, detail"
        " FROM grading WHERE id = ?",
        (grading_id,),
    ).fetchone()
    if row is None:
        return None
    question_id, status, result, correct, provisional, confidence, detail = row
    question = get_question(connection, question_id)
    assert question is not None  # a grading goes with its question
    graded: dict[str, Any] = json.loads(result) if result else {}
    right = None if correct is None else bool(correct)
    return GradingState(
        grading_id,
        question_id,
        status,
        right,
        provisional=bool(provisional),
        priority=right is False and confidence == "sure",
        criteria=[CriterionResult(**one) for one in graded.get("criteria", [])],
        comment=graded.get("comment"),
        expected_answer=question.content["expected_answer"],
        detail=detail,
    )


def grading_handler(grade: Grader) -> Handler:
    """The background worker's handler of a grading that waited for Claude."""

    def handle(connection: sqlite3.Connection, data: dict[str, Any]) -> dict[str, Any]:
        run_grading(connection, data["grading_id"], grade)
        return {"grading_id": data["grading_id"]}

    return handle


def verification_handler(grade: Grader) -> Handler:
    """The background worker's handler of a provisional grading that Claude checks;
    `grade` asks Claude alone."""

    def handle(connection: sqlite3.Connection, data: dict[str, Any]) -> dict[str, Any]:
        verify_grading(connection, data["grading_id"], grade)
        return {"grading_id": data["grading_id"]}

    return handle


def resume_gradings(connection: sqlite3.Connection) -> None:
    """Queue again the gradings cut by the end of the app, once their confidence is
    chosen: the answer they wait for was given."""
    rows = connection.execute(
        "SELECT id FROM grading WHERE status = 'pending' AND confidence IS NOT NULL"
    ).fetchall()
    for (grading_id,) in rows:
        _wait_for_claude(connection, grading_id)


def _wait_for_claude(connection: sqlite3.Connection, grading_id: int) -> None:
    """Queue the grading for the background worker, unless it is queued already."""
    queued = connection.execute(
        "SELECT 1 FROM ai_task WHERE kind = ? AND status IN ('pending', 'running')"
        " AND json_extract(input, '$.grading_id') = ?",
        (TASK, grading_id),
    ).fetchone()
    if queued is None:
        add_task(connection, TASK, {"grading_id": grading_id})


def _record(connection: sqlite3.Connection, grading_id: int) -> None:
    """Save the answer in the history and set the next date of its question, once its
    grading is done and its confidence chosen. Exactly once: the grading thread and the
    confidence may both get there, and the first to claim the grading saves it."""
    with connection:
        claimed = connection.execute(
            "UPDATE grading SET recorded_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')"
            " WHERE id = ? AND status = 'done' AND confidence IS NOT NULL"
            " AND recorded_at IS NULL",
            (grading_id,),
        ).rowcount
    if not claimed:
        return
    question_id, session_id, text, written_at, correct, confidence, seconds = (
        connection.execute(
            "SELECT question_id, session_id, answer_text, written_at, correct,"
            " confidence, seconds FROM grading WHERE id = ?",
            (grading_id,),
        ).fetchone()
    )
    written = datetime.fromisoformat(written_at)
    answer_id = record_answer(
        connection,
        NewAnswer(
            question_id,
            session_id,
            bool(correct),
            confidence,
            seconds,
            answer_text=text,
            answered_at=written,
        ),
    )
    question = get_question(connection, question_id)
    if question is not None and question.role == "review":
        card = review(
            get_card(connection, question_id),
            question_id,
            bool(correct),
            confidence,
            written,
        )
        save_card(connection, card)
    with connection:
        connection.execute(
            "UPDATE grading SET answer_id = ? WHERE id = ?", (answer_id, grading_id)
        )


def _result(graded: OpenGrading) -> str:
    """What a grading says, as it is saved: each criterion met or not, the comment."""
    result = {
        "criteria": [asdict(criterion) for criterion in graded.criteria],
        "comment": graded.comment,
    }
    return json.dumps(result, ensure_ascii=False)


def _finish(
    connection: sqlite3.Connection,
    grading_id: int,
    changes: str,
    values: tuple[Any, ...],
) -> None:
    """End a pending grading, unless another one ended it first."""
    with connection:
        connection.execute(
            f"UPDATE grading SET {changes} WHERE id = ? AND status = 'pending'",
            (*values, grading_id),
        )
