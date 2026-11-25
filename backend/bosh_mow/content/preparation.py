"""Preparing a chapter just before it is studied, in two steps.

1. T1 pass 2: Claude cuts the chapter into notions, in one short call.
2. Once the student has validated the notions (R3), T2: Claude writes the 7 questions of
   each notion, in one call per notion of about half a minute.

Contract T2 asked for both in a single call per chapter. A chapter of 13 pages took
3 minutes that way, and bigger ones would not end within the time limit. In two steps,
a notion that fails does not hold back the others, and no question is written for a
notion that the student drops. Questions are not reviewed one by one: they are saved as
soon as they keep the rules of T2, and "Signaler" takes a wrong one out. Claude reads
the pages, with the descriptions of the pages mostly in images (T11, R38).
"""

import re
import sqlite3
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from typing import Any

from bosh_mow.ai.gateway import EngineUnavailable, Gateway
from bosh_mow.ai.schemas import (
    CombinedT2Answer,
    T1Pass2Answer,
    T1Pass2Notion,
    T2Answer,
    T2Question,
)
from bosh_mow.ai.tasks import Handler, Task, add_task, get_task, retry_now
from bosh_mow.content.repository import (
    NewNotion,
    NewQuestion,
    save_notions,
    save_questions,
)
from bosh_mow.subjects.descriptions import TASK as DESCRIBE_TASK

NOTIONS_PROMPT = "t1_pass2_v1"
QUESTIONS_PROMPT = "t2_v2"
NOTIONS_TASK = "t1_pass2"  # cut a chapter into notions
QUESTIONS_TASK = "t2"  # write the questions of a notion (first version: of a chapter)
MAX_NOTION_PAGES = 6  # a notion is read in 10 minutes at most (R13)
TOO_CLOSE = 0.8  # two statements sharing this much of their words repeat each other
EXPECTED = {  # the questions of each notion (contract T2)
    ("pretest", "mcq"): (2, "pretest MCQs"),
    ("review", "mcq"): (3, "review MCQs"),
    ("review", "value or short"): (1, "value or short answer"),
    ("review", "open"): (1, "open « why? » question"),
}
SUB_QUESTION = re.compile(r"(?:^|\s)\(?([a-d])\)\s")  # "(a) …", "b) …"
WORD = re.compile(r"\w+")


@dataclass(frozen=True)
class ChapterFile:
    """Pages of one file: those of a chapter, where its notions take theirs."""

    id: int
    first_page: int
    last_page: int


@dataclass(frozen=True)
class PreparationState:
    """Where the cutting of a chapter into notions stands."""

    status: str  # pending, running, done or failed
    error: str | None  # why Claude is awaited, or why it failed
    notions: list[NewNotion] = field(default_factory=list)  # once done
    boundary_alert: str | None = None


@dataclass(frozen=True)
class QuestionsState:
    """Where the writing of the questions of a notion stands."""

    status: str  # pending, running, done or failed
    error: str | None


# Step 1: the notions of a chapter (T1 pass 2)


def prepare_notions(
    connection: sqlite3.Connection, gateway: Gateway, chapter_id: int
) -> T1Pass2Answer:
    """Ask Claude for the notions of a chapter.

    Raises EngineUnavailable if Claude cannot answer now, or if pages of the chapter
    still wait for their description (R38).
    """
    row = connection.execute(
        "SELECT c.number, c.title, s.name FROM chapter c"
        " JOIN subject s ON s.id = c.subject_id WHERE c.id = ?",
        (chapter_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"Chapter {chapter_id} does not exist.")
    number, title, subject = row
    sources = connection.execute(
        "SELECT s.resource_id, r.file_name, r.kind, s.first_page, s.last_page"
        " FROM chapter_source s JOIN resource r ON r.id = s.resource_id"
        " WHERE s.chapter_id = ? ORDER BY s.resource_id",
        (chapter_id,),
    ).fetchall()
    files = [
        ChapterFile(file_id, first, last) for file_id, _, _, first, last in sources
    ]
    _wait_for_descriptions(connection, files)
    data = {
        "subject": subject,
        "chapter": {
            "number": number,
            "title": title,
            "objectives": _objectives(connection, chapter_id),
        },
        "files": [
            {
                "id": file_id,
                "name": name,
                "kind": kind,
                "first_page": first,
                "last_page": last,
                "pages": _pages(connection, file_id, first, last),
            }
            for file_id, name, kind, first, last in sources
        ],
    }
    return gateway.ask(
        NOTIONS_PROMPT,
        data,
        T1Pass2Answer,
        check=lambda answer: check_notions(answer, files),
    )


def check_notions(answer: T1Pass2Answer, files: Sequence[ChapterFile]) -> list[str]:
    """What breaks the rules of T1 pass 2, in sentences for Claude; [] if nothing.

    `files` are the pages of the chapter.
    """
    if not answer.notions:
        return ["Give at least one notion."]
    problems: list[str] = []
    for number, notion in enumerate(answer.notions, start=1):
        problems += _check_notion_pages(number, notion, files)
    return problems


def request_preparation(connection: sqlite3.Connection, chapter_id: int) -> None:
    """Ask for the notions of a chapter in the background; a request that waits for
    Claude is tried again at once."""
    task = _latest_task(connection, NOTIONS_TASK, "chapter_id", chapter_id)
    if task is not None and task.status == "pending":
        retry_now(connection, task.id)
    elif task is None or task.status != "running":
        (subject_id,) = connection.execute(
            "SELECT subject_id FROM chapter WHERE id = ?", (chapter_id,)
        ).fetchone()
        add_task(connection, NOTIONS_TASK, {"chapter_id": chapter_id}, subject_id)


def preparation_state(
    connection: sqlite3.Connection, chapter_id: int
) -> PreparationState | None:
    """Where the last cutting of a chapter into notions stands; None if none was
    asked for. A proposal of the first version also has the questions."""
    row = connection.execute(
        "SELECT id FROM ai_task WHERE kind IN (?, ?)"
        " AND json_extract(input, '$.chapter_id') = ? ORDER BY id DESC LIMIT 1",
        (NOTIONS_TASK, QUESTIONS_TASK, chapter_id),
    ).fetchone()
    task = get_task(connection, row[0]) if row else None
    if task is None:
        return None
    if task.status != "done" or task.result is None:
        return PreparationState(task.status, task.error)
    if task.kind == QUESTIONS_TASK:  # the first version, notions and questions
        combined = CombinedT2Answer.model_validate(task.result)
        return PreparationState(
            task.status, task.error, to_notions(combined), combined.boundary_alert
        )
    answer = T1Pass2Answer.model_validate(task.result)
    notions = [
        NewNotion(n.title, n.summary, n.file, n.first_page, n.last_page)
        for n in answer.notions
    ]
    return PreparationState(task.status, task.error, notions, answer.boundary_alert)


def validate_notions(
    connection: sqlite3.Connection, chapter_id: int, titles: Sequence[str]
) -> None:
    """Save the notions proposed for a chapter, with the titles the student gave them
    (R3), then ask for the questions of each one."""
    state = preparation_state(connection, chapter_id)
    if state is None or state.status != "done":
        raise ValueError(f"The notions of chapter {chapter_id} are not ready.")
    if len(titles) != len(state.notions) or not all(title.strip() for title in titles):
        raise ValueError("Give a title to each notion proposed.")
    notions = [
        replace(notion, title=title.strip())
        for notion, title in zip(state.notions, titles, strict=True)
    ]
    for notion_id, notion in zip(
        save_notions(connection, chapter_id, notions), notions, strict=True
    ):
        if not notion.questions:
            request_questions(connection, notion_id)


def notions_handler(gateway: Gateway) -> Handler:
    """The background task NOTIONS_TASK: prepare_notions() for its chapter."""

    def run(connection: sqlite3.Connection, data: dict[str, Any]) -> dict[str, Any]:
        return prepare_notions(connection, gateway, data["chapter_id"]).model_dump()

    return run


# Step 2: the questions of each notion (T2)


def prepare_questions(
    connection: sqlite3.Connection, gateway: Gateway, notion_id: int
) -> T2Answer:
    """Ask Claude for the 7 questions of a validated notion. Its pages have their
    descriptions: the notions waited for them (R38).

    Raises EngineUnavailable if Claude cannot answer now; InvalidAnswer if the answer
    breaks the rules of T2 twice in a row.
    """
    row = connection.execute(
        "SELECT n.title, n.summary, n.resource_id, r.file_name, r.kind, n.first_page,"
        " n.last_page, c.id, c.title, s.id, s.name FROM notion n"
        " JOIN resource r ON r.id = n.resource_id JOIN chapter c ON c.id = n.chapter_id"
        " JOIN subject s ON s.id = c.subject_id WHERE n.id = ?",
        (notion_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"Notion {notion_id} does not exist.")
    title, summary, file_id, name, kind, first, last = row[:7]
    chapter_id, chapter, subject_id, subject = row[7:]
    existing = [
        statement
        for (statement,) in connection.execute(
            "SELECT q.statement FROM question q JOIN notion n ON n.id = q.notion_id"
            " JOIN chapter c ON c.id = n.chapter_id"
            " WHERE c.subject_id = ? ORDER BY q.id",
            (subject_id,),
        )
    ]
    data = {
        "subject": subject,
        "chapter": {
            "title": chapter,
            "objectives": _objectives(connection, chapter_id),
        },
        "notion": {
            "title": title,
            "summary": summary,
            "file": name,
            "kind": kind,
            "first_page": first,
            "last_page": last,
            "pages": _pages(connection, file_id, first, last),
        },
        "existing_statements": existing,
    }
    return gateway.ask(
        QUESTIONS_PROMPT,
        data,
        T2Answer,
        check=lambda answer: check_questions(answer, first, last, existing),
    )


def check_questions(
    answer: T2Answer, first_page: int, last_page: int, existing: Sequence[str]
) -> list[str]:
    """What breaks the rules of T2 in the questions of a notion, in sentences for
    Claude; [] if nothing. The notion has pages `first_page` to `last_page`; `existing`
    are the statements of the subject."""
    counts = Counter(_slot(question) for question in answer.questions)
    problems = [
        f"The notion needs {expected} {label}, not {counts[slot]}."
        for slot, (expected, label) in EXPECTED.items()
        if counts[slot] != expected
    ]
    seen: list[tuple[str, str]] = []  # (where, statement) of the questions read so far
    for number, question in enumerate(answer.questions, start=1):
        where = f"Question {number}"
        problems += _check_question(where, question)
        if not first_page <= question.first_page <= question.last_page <= last_page:
            problems.append(
                f"{where}: pages {question.first_page} to {question.last_page} are not"
                f" in the notion, pages {first_page} to {last_page}."
            )
        problems += _check_repetition(where, question.statement, existing, seen)
        seen.append((where, question.statement))
    return problems


def request_questions(connection: sqlite3.Connection, notion_id: int) -> None:
    """Ask for the questions of a notion in the background, unless it has them; a
    request that waits for Claude is tried again at once."""
    row = connection.execute(
        "SELECT c.subject_id,"
        " EXISTS (SELECT 1 FROM question q WHERE q.notion_id = n.id)"
        " FROM notion n JOIN chapter c ON c.id = n.chapter_id WHERE n.id = ?",
        (notion_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"Notion {notion_id} does not exist.")
    subject_id, written = row
    if written:
        return
    task = _latest_task(connection, QUESTIONS_TASK, "notion_id", notion_id)
    if task is not None and task.status == "pending":
        retry_now(connection, task.id)
    elif task is None or task.status != "running":
        add_task(connection, QUESTIONS_TASK, {"notion_id": notion_id}, subject_id)


def questions_state(
    connection: sqlite3.Connection, notion_id: int
) -> QuestionsState | None:
    """Where the writing of the questions of a notion stands; None if never asked."""
    task = _latest_task(connection, QUESTIONS_TASK, "notion_id", notion_id)
    return QuestionsState(task.status, task.error) if task else None


def questions_handler(gateway: Gateway) -> Handler:
    """The background task QUESTIONS_TASK: the questions of its notion, saved as soon
    as they keep the rules."""

    def run(connection: sqlite3.Connection, data: dict[str, Any]) -> dict[str, Any]:
        answer = prepare_questions(connection, gateway, data["notion_id"])
        save_questions(connection, data["notion_id"], to_questions(answer))
        return answer.model_dump()

    return run


def to_questions(answer: T2Answer) -> list[NewQuestion]:
    """The questions of an answer, as they are saved."""
    return [_to_question(question) for question in answer.questions]


def to_notions(answer: CombinedT2Answer) -> list[NewNotion]:
    """The notions of a proposal of the first version, with their questions."""
    return [
        NewNotion(
            notion.title,
            notion.summary,
            notion.file,
            notion.first_page,
            notion.last_page,
            [_to_question(question) for question in notion.questions],
        )
        for notion in answer.notions
    ]


def _check_notion_pages(
    number: int, notion: T1Pass2Notion, files: Sequence[ChapterFile]
) -> list[str]:
    file = next((file for file in files if file.id == notion.file), None)
    if file is None:
        return [
            f"Notion {number} uses file {notion.file}, which is not in the chapter."
        ]
    if not file.first_page <= notion.first_page <= notion.last_page <= file.last_page:
        return [
            f"Notion {number}: pages {notion.first_page} to {notion.last_page} are not"
            f" in the chapter, which has pages {file.first_page} to {file.last_page}"
            f" of file {file.id}."
        ]
    count = notion.last_page - notion.first_page + 1
    if count > MAX_NOTION_PAGES:
        return [
            f"Notion {number} has {count} pages: {MAX_NOTION_PAGES} at most,"
            " to be read in 10 minutes."
        ]
    return []


def _check_question(where: str, question: T2Question) -> list[str]:
    """What a question needs: its format's fields, a single idea, a difficulty."""
    problems: list[str] = []
    if question.role == "pretest" and question.format != "mcq":
        problems.append(f"{where}: a pretest is an MCQ.")
    if question.format == "mcq":
        options = question.options or []
        if not 3 <= len(options) <= 4:
            problems.append(f"{where}: an MCQ has 3 or 4 options, not {len(options)}.")
        correct = sum(option.correct for option in options)
        if correct != 1:
            problems.append(
                f"{where}: an MCQ has a single correct option, not {correct}."
            )
        if any(not option.explanation.strip() for option in options):
            problems.append(f"{where}: every option needs its explanation.")
    elif question.format == "value":
        if question.value is None:
            problems.append(f"{where}: a value question needs its value.")
        if question.tolerance is not None and question.tolerance < 0:
            problems.append(f"{where}: the tolerance cannot be negative.")
    elif question.format == "short":
        if not any(answer.strip() for answer in question.accepted or []):
            problems.append(f"{where}: a short answer needs its accepted answers.")
    else:
        if not (question.expected_answer or "").strip():
            problems.append(f"{where}: an open question needs its expected answer.")
        count = len(question.criteria or [])
        if not 2 <= count <= 4:
            problems.append(
                f"{where}: an open question needs 2 to 4 criteria, not {count}."
            )
    if (
        question.format in ("value", "short")
        and not (question.explanation or "").strip()
    ):
        problems.append(f"{where}: a {question.format} question needs its explanation.")
    if len(set(SUB_QUESTION.findall(question.statement))) >= 2:
        problems.append(
            f"{where} asks several things: one idea per question, without (a), (b)."
        )
    if not 1 <= question.difficulty <= 3:
        problems.append(
            f"{where}: the difficulty is 1, 2 or 3, not {question.difficulty}."
        )
    return problems


def _check_repetition(
    where: str,
    statement: str,
    existing: Sequence[str],
    seen: Sequence[tuple[str, str]],
) -> list[str]:
    for other in existing:
        if _close(statement, other):
            return [f"{where} is too close to an existing question: « {other} »."]
    for other_where, other in seen:
        if _close(statement, other):
            return [f"{where} is too close to {other_where.lower()}."]
    return []


def _close(statement: str, other: str) -> bool:
    """Whether two statements share most of their words: they repeat each other."""
    words, other_words = (
        set(WORD.findall(text.lower())) for text in (statement, other)
    )
    union = words | other_words
    return bool(union) and len(words & other_words) / len(union) >= TOO_CLOSE


def _slot(question: T2Question) -> tuple[str, str]:
    kind = (
        "value or short" if question.format in ("value", "short") else question.format
    )
    return question.role, kind


def _wait_for_descriptions(
    connection: sqlite3.Connection, files: Sequence[ChapterFile]
) -> None:
    """Wait while a page of these files still waits for its description (R38)."""
    for file in files:
        if connection.execute(
            "SELECT 1 FROM ai_task WHERE kind = ? AND status IN ('pending', 'running')"
            " AND json_extract(input, '$.resource_id') = ?"
            " AND json_extract(input, '$.page') BETWEEN ? AND ?",
            (DESCRIBE_TASK, file.id, file.first_page, file.last_page),
        ).fetchone():
            raise EngineUnavailable(
                "Les descriptions des schémas de ce chapitre ne sont pas encore prêtes."
            )


def _objectives(connection: sqlite3.Connection, chapter_id: int) -> list[str]:
    return [
        text
        for (text,) in connection.execute(
            "SELECT o.text FROM chapter_objective co"
            " JOIN objective o ON o.id = co.objective_id"
            " WHERE co.chapter_id = ? ORDER BY o.position",
            (chapter_id,),
        )
    ]


def _pages(
    connection: sqlite3.Connection, file_id: int, first: int, last: int
) -> list[dict[str, Any]]:
    """The text of each page of a range, with the description of a page in images."""
    rows = connection.execute(
        "SELECT p.number, p.text, d.description FROM page p"
        " LEFT JOIN page_description d"
        " ON d.resource_id = p.resource_id AND d.number = p.number"
        " WHERE p.resource_id = ? AND p.number BETWEEN ? AND ? ORDER BY p.number",
        (file_id, first, last),
    ).fetchall()
    pages: list[dict[str, Any]] = []
    for number, text, description in rows:
        page: dict[str, Any] = {"page": number, "text": _clean(text)}
        if description:
            page["description"] = description
        pages.append(page)
    return pages


def _clean(text: str) -> str:
    """The lines of a text, without blank lines or extra spaces."""
    lines = (" ".join(line.split()) for line in text.splitlines())
    return "\n".join(line for line in lines if line)


def _latest_task(
    connection: sqlite3.Connection, kind: str, key: str, value: int
) -> Task | None:
    """The last task of a kind whose input has `key` equal to `value`."""
    row = connection.execute(
        "SELECT id FROM ai_task WHERE kind = ? AND json_extract(input, ?) = ?"
        " ORDER BY id DESC LIMIT 1",
        (kind, f"$.{key}", value),
    ).fetchone()
    return get_task(connection, row[0]) if row else None


def _to_question(question: T2Question) -> NewQuestion:
    return NewQuestion(
        question.role,
        question.type,
        question.level,
        question.format,
        question.difficulty,
        question.statement,
        question.first_page,
        question.last_page,
        _content(question),
    )


def _content(question: T2Question) -> dict[str, Any]:
    """What the format of a question needs, as it is saved (see migration 008)."""
    if question.format == "mcq":
        return {"options": [option.model_dump() for option in question.options or []]}
    if question.format == "value":
        tolerance = 0.01 if question.tolerance is None else question.tolerance
        return {
            "value": question.value,
            "tolerance": tolerance,
            "explanation": question.explanation,
        }
    if question.format == "short":
        return {
            "accepted": question.accepted or [],
            "explanation": question.explanation,
        }
    return {
        "expected_answer": question.expected_answer,
        "criteria": question.criteria or [],
        "frequent_errors": question.frequent_errors or [],
    }
