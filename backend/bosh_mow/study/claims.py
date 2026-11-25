"""Claims ("Je pense avoir juste", T5): a value or a short answer that the code found
wrong goes to Claude in the background, and the session goes on. If Claude agrees, the
answer becomes right in the history, its question is rescheduled from all its answers,
and its wording joins the accepted answers, so that it is right at once next time.
"""

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from bosh_mow.ai.gateway import EngineUnavailable
from bosh_mow.ai.tasks import Handler, add_task
from bosh_mow.content.repository import accept_wording, get_question
from bosh_mow.grading.claims import claim_question
from bosh_mow.study.gradings import Grader
from bosh_mow.study.repository import save_card
from bosh_mow.study.scheduling import PastAnswer, replay

TASK = "t6_claim"  # a claim judged by Claude, done by the background worker


@dataclass(frozen=True)
class ClaimState:
    id: int
    answer_id: int
    status: str  # pending, accepted, refused or failed
    comment: str | None  # Claude's reason, in French
    detail: str | None  # why it failed


def make_claim(connection: sqlite3.Connection, answer_id: int) -> int:
    """Send to Claude a value or a short answer that the code found wrong; return the
    claim, judged in the background."""
    row = connection.execute(
        "SELECT q.format, a.answer_text, a.correct FROM answer a"
        " JOIN question q ON q.id = a.question_id WHERE a.id = ?",
        (answer_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"Answer {answer_id} does not exist.")
    form, text, correct = row
    if form not in ("value", "short"):
        raise ValueError("Only a value or a short answer can be claimed.")
    if correct:
        raise ValueError("This answer is right already.")
    if text is None:
        raise ValueError("There is no answer to claim: it was « Je ne sais pas ».")
    claimed = connection.execute(
        "SELECT 1 FROM claim WHERE answer_id = ?", (answer_id,)
    ).fetchone()
    if claimed:
        raise ValueError("This answer is claimed already.")
    with connection:
        claim_id = connection.execute(
            "INSERT INTO claim (answer_id) VALUES (?)", (answer_id,)
        ).lastrowid
    add_task(connection, TASK, {"claim_id": claim_id})
    return claim_id


def judge_claim(connection: sqlite3.Connection, claim_id: int, grade: Grader) -> None:
    """Ask Claude whether the answer claimed is right after all, and apply the decision.
    A claim that cannot be judged fails, and says why; an engine unavailable raises
    EngineUnavailable, to be tried again later."""
    row = connection.execute(
        "SELECT c.answer_id, a.question_id, a.answer_text FROM claim c"
        " JOIN answer a ON a.id = c.answer_id WHERE c.id = ? AND c.status = 'pending'",
        (claim_id,),
    ).fetchone()
    if row is None:
        return  # judged already
    answer_id, question_id, text = row
    question = get_question(connection, question_id)
    assert question is not None  # an answer goes with its question
    asked = claim_question(question.statement, question.format, question.content, text)
    try:
        graded = grade(asked, text)
    except EngineUnavailable:
        raise
    except Exception as error:  # an invalid answer, too long, or a bug: say why
        _decide(connection, claim_id, "failed", detail=str(error))
        return
    if graded.correct:
        _accept(connection, answer_id, question_id, text, question.role)
    status = "accepted" if graded.correct else "refused"
    _decide(connection, claim_id, status, comment=graded.comment)


def claim_state(connection: sqlite3.Connection, claim_id: int) -> ClaimState | None:
    row = connection.execute(
        "SELECT id, answer_id, status, comment, detail FROM claim WHERE id = ?",
        (claim_id,),
    ).fetchone()
    return ClaimState(*row) if row else None


def claim_handler(grade: Grader) -> Handler:
    """The background worker's handler of a claim."""

    def handle(connection: sqlite3.Connection, data: dict[str, Any]) -> dict[str, Any]:
        judge_claim(connection, data["claim_id"], grade)
        return {"claim_id": data["claim_id"]}

    return handle


def _accept(
    connection: sqlite3.Connection,
    answer_id: int,
    question_id: int,
    text: str,
    role: str,
) -> None:
    """The answer was right: so it is in the history, its wording is accepted, and its
    question gets the date that all its answers give it (FSRS)."""
    with connection:
        connection.execute("UPDATE answer SET correct = 1 WHERE id = ?", (answer_id,))
    accept_wording(connection, question_id, text)
    if role != "review":
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


def _decide(
    connection: sqlite3.Connection,
    claim_id: int,
    status: str,
    comment: str | None = None,
    detail: str | None = None,
) -> None:
    with connection:
        connection.execute(
            "UPDATE claim SET status = ?, comment = ?, detail = ?"
            " WHERE id = ? AND status = 'pending'",
            (status, comment, detail, claim_id),
        )
