"""Storage of the notions of a chapter and of the questions on each notion.

Claude proposes them just before a chapter is studied (T1 pass 2, T2). They are saved
once the student validates the notions (R3); questions are not reviewed one by one, and
"Signaler" takes a wrong one out of the reviews.
"""

import json
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

type Role = Literal["pretest", "review"]
type QuestionType = Literal["concept", "calculation", "code"]
# R5: restituer, expliquer, appliquer, analyser.
type Level = Literal["recall", "explain", "apply", "analyze"]
type Format = Literal["mcq", "value", "short", "open"]
# T3, R14: an example solved step by step, a problem to complete, a problem alone.
type ExerciseKind = Literal["worked", "completion", "solo"]


@dataclass(frozen=True)
class NewQuestion:
    """A question on a single idea (R5), with its source pages in its notion's file;
    or an exercise of the notion (T3), with the steps of its solution in its content."""

    role: Role
    type: QuestionType
    level: Level
    format: Format
    difficulty: int  # 1 (easy) to 3 (hard)
    statement: str  # in English (R5)
    first_page: int
    last_page: int
    content: dict[str, Any]  # what its format needs (see migrations 008 and 015)
    # The kind of an exercise; None for a question.
    exercise: ExerciseKind | None = field(default=None, kw_only=True)


@dataclass(frozen=True)
class Question(NewQuestion):
    id: int
    notion_id: int
    reported: bool  # "Signaler": out of the reviews


@dataclass(frozen=True)
class NewNotion:
    """A notion as validated, with the questions Claude wrote on it."""

    title: str
    summary: str
    resource_id: int
    first_page: int
    last_page: int
    questions: list[NewQuestion] = field(default_factory=list)


@dataclass(frozen=True)
class Notion:
    id: int
    chapter_id: int
    number: int  # its place in the chapter, from 1
    title: str
    summary: str
    resource_id: int
    first_page: int
    last_page: int
    studied: bool  # its first study is done (R13)


def save_notions(
    connection: sqlite3.Connection, chapter_id: int, notions: Sequence[NewNotion]
) -> list[int]:
    """Save the validated notions of a chapter with their questions; return their ids.

    The notions of a chapter are saved once. All or nothing is saved.
    """
    if connection.execute(
        "SELECT 1 FROM notion WHERE chapter_id = ?", (chapter_id,)
    ).fetchone():
        raise ValueError(f"Chapter {chapter_id} already has its notions.")
    notion_ids: list[int] = []
    with connection:
        for number, notion in enumerate(notions, start=1):
            notion_id = connection.execute(
                "INSERT INTO notion (chapter_id, number, title, summary, resource_id,"
                " first_page, last_page) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    chapter_id,
                    number,
                    notion.title.strip(),
                    notion.summary.strip(),
                    notion.resource_id,
                    notion.first_page,
                    notion.last_page,
                ),
            ).lastrowid
            _insert_questions(connection, notion_id, notion.questions)
            notion_ids.append(notion_id)
    return notion_ids


def save_questions(
    connection: sqlite3.Connection, notion_id: int, questions: Sequence[NewQuestion]
) -> None:
    """Save the questions Claude wrote on a validated notion (T2); a notion gets its
    questions once."""
    if connection.execute(
        "SELECT 1 FROM question WHERE notion_id = ? AND exercise IS NULL", (notion_id,)
    ).fetchone():
        raise ValueError(f"Notion {notion_id} already has its questions.")
    with connection:
        _insert_questions(connection, notion_id, questions)


def save_exercises(
    connection: sqlite3.Connection, notion_id: int, exercises: Sequence[NewQuestion]
) -> None:
    """Save the exercises Claude wrote on a notion (T3), after its questions; a notion
    gets its exercises once."""
    if connection.execute(
        "SELECT 1 FROM question WHERE notion_id = ? AND exercise IS NOT NULL",
        (notion_id,),
    ).fetchone():
        raise ValueError(f"Notion {notion_id} already has its exercises.")
    if any(exercise.exercise is None for exercise in exercises):
        raise ValueError("An exercise needs its kind: worked, completion or solo.")
    with connection:
        _insert_questions(connection, notion_id, exercises)


def get_notions(connection: sqlite3.Connection, chapter_id: int) -> list[Notion]:
    """The notions of a chapter, in order; [] while they are not validated."""
    rows = connection.execute(
        "SELECT id, chapter_id, number, title, summary, resource_id, first_page,"
        " last_page, studied_at IS NOT NULL FROM notion WHERE chapter_id = ?"
        " ORDER BY number",
        (chapter_id,),
    ).fetchall()
    return [Notion(*row[:-1], bool(row[-1])) for row in rows]


def get_questions(connection: sqlite3.Connection, notion_id: int) -> list[Question]:
    """The questions on a notion, in order, reported ones included; not its
    exercises."""
    rows = connection.execute(
        f"{_SELECT_QUESTION} WHERE notion_id = ? AND exercise IS NULL"
        " ORDER BY position",
        (notion_id,),
    ).fetchall()
    return [_question(row) for row in rows]


def get_exercises(connection: sqlite3.Connection, notion_id: int) -> list[Question]:
    """The exercises of a notion, in order (T3): the worked example, the problem to
    complete, then the solo problems; reported ones included."""
    rows = connection.execute(
        f"{_SELECT_QUESTION} WHERE notion_id = ? AND exercise IS NOT NULL"
        " ORDER BY position",
        (notion_id,),
    ).fetchall()
    return [_question(row) for row in rows]


def get_question(connection: sqlite3.Connection, question_id: int) -> Question | None:
    row = connection.execute(
        f"{_SELECT_QUESTION} WHERE id = ?", (question_id,)
    ).fetchone()
    return _question(row) if row else None


def report_question(connection: sqlite3.Connection, question_id: int) -> None:
    """Take a wrong question out of the reviews (Signaler), but keep it."""
    with connection:
        reported = connection.execute(
            "UPDATE question SET reported_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')"
            " WHERE id = ?",
            (question_id,),
        ).rowcount
    if not reported:
        raise ValueError(f"Question {question_id} does not exist.")


def accept_wording(
    connection: sqlite3.Connection, question_id: int, wording: str
) -> None:
    """Add a wording to the accepted answers of a value or a short answer, once Claude
    found it right after a claim ("Je pense avoir juste"): right at once next time."""
    question = get_question(connection, question_id)
    if question is None:
        raise ValueError(f"Question {question_id} does not exist.")
    accepted = list(question.content.get("accepted", []))
    if wording in accepted:
        return
    content = {**question.content, "accepted": [*accepted, wording]}
    with connection:
        connection.execute(
            "UPDATE question SET content = ? WHERE id = ?",
            (json.dumps(content, ensure_ascii=False), question_id),
        )


def mark_studied(connection: sqlite3.Connection, notion_id: int) -> None:
    """Note that the first study of a notion is done (R13)."""
    with connection:
        connection.execute(
            "UPDATE notion SET studied_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')"
            " WHERE id = ? AND studied_at IS NULL",
            (notion_id,),
        )


def _insert_questions(
    connection: sqlite3.Connection, notion_id: int, questions: Sequence[NewQuestion]
) -> None:
    """Add questions or exercises to a notion, after those it has."""
    (last,) = connection.execute(
        "SELECT COALESCE(MAX(position), 0) FROM question WHERE notion_id = ?",
        (notion_id,),
    ).fetchone()
    connection.executemany(
        "INSERT INTO question (notion_id, position, role, type, level, format,"
        " difficulty, statement, first_page, last_page, content, exercise)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                notion_id,
                position,
                question.role,
                question.type,
                question.level,
                question.format,
                question.difficulty,
                question.statement,
                question.first_page,
                question.last_page,
                json.dumps(question.content, ensure_ascii=False),
                question.exercise,
            )
            for position, question in enumerate(questions, start=last + 1)
        ],
    )


_SELECT_QUESTION = (
    "SELECT role, type, level, format, difficulty, statement, first_page, last_page,"
    " content, id, notion_id, reported_at IS NOT NULL, exercise FROM question"
)


def _question(row: tuple[Any, ...]) -> Question:
    *fields, content, question_id, notion_id, reported, exercise = row
    return Question(
        *fields,
        json.loads(content),
        question_id,
        notion_id,
        bool(reported),
        exercise=exercise,
    )
