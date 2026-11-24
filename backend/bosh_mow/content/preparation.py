"""Preparing a chapter just before it is studied: T1 pass 2 cuts it into notions, and T2
writes the questions on each notion, in a single call to Claude (contract T2).

Claude reads the pages of the chapter, with the descriptions of the pages mostly in
images (T11, R38), its objectives, and the statements that exist in the subject. The
answer must keep the rules of T2; it stays a proposal until the student validates the
notions (R3).
"""

import re
import sqlite3
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from typing import Any

from bosh_mow.ai.gateway import EngineUnavailable, Gateway
from bosh_mow.ai.schemas import T2Answer, T2Notion, T2Question
from bosh_mow.ai.tasks import Handler, Task, add_task, get_task, retry_now
from bosh_mow.content.repository import NewNotion, NewQuestion, save_notions
from bosh_mow.subjects.descriptions import TASK as DESCRIBE_TASK

PROMPT = "t2_v1"
TASK = "t2"  # the kind of the background task that runs prepare()
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
    """The pages of one file in a chapter: the notions take theirs there."""

    id: int
    first_page: int
    last_page: int


@dataclass(frozen=True)
class PreparationState:
    """Where the preparation of a chapter stands."""

    status: str  # pending, running, done or failed
    error: str | None  # why Claude is awaited, or why the preparation failed
    notions: list[NewNotion] = field(default_factory=list)  # once done
    boundary_alert: str | None = None


def prepare(
    connection: sqlite3.Connection, gateway: Gateway, chapter_id: int
) -> T2Answer:
    """Ask Claude for the notions of a chapter and the questions on each one.

    Raises EngineUnavailable if Claude cannot answer now, or if pages of the chapter
    still wait for their description (R38); InvalidAnswer if the answer breaks the
    rules of T2 twice in a row.
    """
    row = connection.execute(
        "SELECT c.number, c.title, s.id, s.name FROM chapter c"
        " JOIN subject s ON s.id = c.subject_id WHERE c.id = ?",
        (chapter_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"Chapter {chapter_id} does not exist.")
    number, title, subject_id, subject = row
    sources = connection.execute(
        "SELECT s.resource_id, r.file_name, r.kind, s.first_page, s.last_page"
        " FROM chapter_source s JOIN resource r ON r.id = s.resource_id"
        " WHERE s.chapter_id = ? ORDER BY s.resource_id",
        (chapter_id,),
    ).fetchall()
    files = [
        ChapterFile(file_id, first, last) for file_id, _, _, first, last in sources
    ]
    if _descriptions_pending(connection, files):
        raise EngineUnavailable(
            "Les descriptions des schémas de ce chapitre ne sont pas encore prêtes."
        )
    existing = [
        statement
        for (statement,) in connection.execute(
            "SELECT q.statement FROM question q JOIN notion n ON n.id = q.notion_id"
            " JOIN chapter c ON c.id = n.chapter_id"
            " WHERE c.subject_id = ? ORDER BY q.id",
            (subject_id,),
        )
    ]
    objectives = [
        text
        for (text,) in connection.execute(
            "SELECT o.text FROM chapter_objective co"
            " JOIN objective o ON o.id = co.objective_id"
            " WHERE co.chapter_id = ? ORDER BY o.position",
            (chapter_id,),
        )
    ]
    data = {
        "subject": subject,
        "chapter": {"number": number, "title": title, "objectives": objectives},
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
        "existing_statements": existing,
    }
    return gateway.ask(
        PROMPT,
        data,
        T2Answer,
        check=lambda answer: check_preparation(answer, files, existing),
    )


def check_preparation(
    answer: T2Answer, files: Sequence[ChapterFile], existing: Sequence[str]
) -> list[str]:
    """What breaks the rules of T2, in sentences for Claude; [] if nothing does.

    `files` are the pages of the chapter, `existing` the statements of the subject.
    """
    if not answer.notions:
        return ["Give at least one notion."]
    problems: list[str] = []
    seen: list[tuple[str, str]] = []  # (where, statement) of the questions read so far
    for n, notion in enumerate(answer.notions, start=1):
        pages_valid = _check_pages(n, notion, files, problems)
        problems += _check_composition(n, notion)
        for m, question in enumerate(notion.questions, start=1):
            where = f"Notion {n}, question {m}"
            problems += _check_question(where, question)
            if pages_valid and not (
                notion.first_page
                <= question.first_page
                <= question.last_page
                <= notion.last_page
            ):
                problems.append(
                    f"{where}: pages {question.first_page} to {question.last_page}"
                    f" are not in its notion, pages {notion.first_page}"
                    f" to {notion.last_page}."
                )
            problems += _check_repetition(where, question.statement, existing, seen)
            seen.append((where, question.statement))
    return problems


def request_preparation(connection: sqlite3.Connection, chapter_id: int) -> None:
    """Ask for the preparation of a chapter in the background; one that waits for
    Claude is tried again at once."""
    task = _latest_task(connection, chapter_id)
    if task is not None and task.status == "pending":
        retry_now(connection, task.id)
    elif task is None or task.status != "running":
        (subject_id,) = connection.execute(
            "SELECT subject_id FROM chapter WHERE id = ?", (chapter_id,)
        ).fetchone()
        add_task(connection, TASK, {"chapter_id": chapter_id}, subject_id)


def preparation_state(
    connection: sqlite3.Connection, chapter_id: int
) -> PreparationState | None:
    """Where the last preparation asked for a chapter stands; None if none was."""
    task = _latest_task(connection, chapter_id)
    if task is None:
        return None
    if task.status == "done" and task.result is not None:
        answer = T2Answer.model_validate(task.result)
        return PreparationState(
            task.status, task.error, to_notions(answer), answer.boundary_alert
        )
    return PreparationState(task.status, task.error)


def validate_notions(
    connection: sqlite3.Connection, chapter_id: int, titles: Sequence[str]
) -> None:
    """Save the notions proposed for a chapter, with the titles the student gave them
    (R3), and their questions."""
    state = preparation_state(connection, chapter_id)
    if state is None or state.status != "done":
        raise ValueError(f"The notions of chapter {chapter_id} are not ready.")
    if len(titles) != len(state.notions) or not all(title.strip() for title in titles):
        raise ValueError("Give a title to each notion proposed.")
    notions = [
        replace(notion, title=title.strip())
        for notion, title in zip(state.notions, titles, strict=True)
    ]
    save_notions(connection, chapter_id, notions)


def preparation_handler(gateway: Gateway) -> Handler:
    """The background task TASK: prepare() for the chapter given in its data."""

    def run(connection: sqlite3.Connection, data: dict[str, Any]) -> dict[str, Any]:
        return prepare(connection, gateway, data["chapter_id"]).model_dump()

    return run


def to_notions(answer: T2Answer) -> list[NewNotion]:
    """The notions of an answer, as they are saved once validated."""
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


def _check_pages(
    n: int, notion: T2Notion, files: Sequence[ChapterFile], problems: list[str]
) -> bool:
    """Add what is wrong with the pages of a notion; return whether they are valid."""
    file = next((file for file in files if file.id == notion.file), None)
    if file is None:
        problems.append(
            f"Notion {n} uses file {notion.file}, which is not in the chapter."
        )
        return False
    if not file.first_page <= notion.first_page <= notion.last_page <= file.last_page:
        problems.append(
            f"Notion {n}: pages {notion.first_page} to {notion.last_page} are not in"
            f" the chapter, which has pages {file.first_page} to {file.last_page}"
            f" of file {file.id}."
        )
        return False
    count = notion.last_page - notion.first_page + 1
    if count > MAX_NOTION_PAGES:
        problems.append(
            f"Notion {n} has {count} pages: {MAX_NOTION_PAGES} at most,"
            " to be read in 10 minutes."
        )
    return True


def _check_composition(n: int, notion: T2Notion) -> list[str]:
    """The seven questions of the contract: 2 pretests, 3 MCQs, 1 value or short
    answer and 1 open « why? » question."""
    counts = Counter(_slot(question) for question in notion.questions)
    return [
        f"Notion {n} needs {expected} {label}, not {counts[slot]}."
        for slot, (expected, label) in EXPECTED.items()
        if counts[slot] != expected
    ]


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
            return [
                f"{where} is too close to {other_where[0].lower()}{other_where[1:]}."
            ]
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


def _descriptions_pending(
    connection: sqlite3.Connection, files: Sequence[ChapterFile]
) -> bool:
    """Whether a page of these files still waits for its description (T11)."""
    return any(
        connection.execute(
            "SELECT 1 FROM ai_task WHERE kind = ? AND status IN ('pending', 'running')"
            " AND json_extract(input, '$.resource_id') = ?"
            " AND json_extract(input, '$.page') BETWEEN ? AND ?",
            (DESCRIBE_TASK, file.id, file.first_page, file.last_page),
        ).fetchone()
        for file in files
    )


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


def _latest_task(connection: sqlite3.Connection, chapter_id: int) -> Task | None:
    row = connection.execute(
        "SELECT id FROM ai_task WHERE kind = ?"
        " AND json_extract(input, '$.chapter_id') = ? ORDER BY id DESC LIMIT 1",
        (TASK, chapter_id),
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
