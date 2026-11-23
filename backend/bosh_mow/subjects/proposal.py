"""T1, pass 1: the objectives and chapters that Claude proposes for a new subject.

The app reads the files without AI and sends only what Claude needs (contract T1): the
outline of a file when it has one, otherwise its guessed titles, otherwise its text,
whole for a short file and the start of each page for a long one. The answer must keep
the rules of T1 before the student sees it; it stays a proposal that the student
corrects (R2, R3).
"""

import re
import sqlite3
import unicodedata
from collections.abc import Sequence
from typing import Any

from bosh_mow.ai.gateway import Gateway
from bosh_mow.ai.schemas import T1Answer
from bosh_mow.subjects.repository import (
    MAX_OBJECTIVES,
    Document,
    Resource,
    get_document,
    get_subject,
)

PROMPT = "t1_v1"
FULL_TEXT_LIMIT = 50  # pages: a shorter file without structure is sent whole
PAGE_START_CHARS = 300  # about 75 tokens: 30,000 tokens for 400 pages
OBJECTIVE_START = re.compile(r"Être capable d(e |'|’)\S")  # R2


def propose(
    connection: sqlite3.Connection, gateway: Gateway, subject_id: int
) -> T1Answer:
    """Ask Claude for the objectives, chapters and glossary of a draft subject.

    Raises EngineUnavailable if Claude cannot answer now, and InvalidAnswer if its
    answer breaks the rules of T1 twice in a row.
    """
    subject = get_subject(connection, subject_id)
    if subject is None:
        raise ValueError(f"Subject {subject_id} does not exist.")
    if not subject.resources:
        raise ValueError(f"Subject {subject_id} has no file to split.")
    data = {
        "subject": subject.name,
        "exam_date": subject.exam_date.isoformat(),
        "files": [
            describe_file(resource, get_document(connection, resource.id))
            for resource in subject.resources
        ],
    }
    return gateway.ask(
        PROMPT,
        data,
        T1Answer,
        check=lambda answer: check_proposal(answer, subject.resources),
    )


def describe_file(resource: Resource, document: Document) -> dict[str, Any]:
    """What Claude receives about one file, depending on what the import found in it."""
    described: dict[str, Any] = {
        "id": resource.id,
        "name": resource.file_name,
        "kind": document.kind,
        "page_count": len(document.pages),
    }
    if document.outline == "structure":
        described["outline"] = _titles(document)
    elif document.outline == "fonts":
        described["title_candidates"] = _titles(document)
    elif len(document.pages) < FULL_TEXT_LIMIT:
        described["page_texts"] = _texts(document, limit=None)
    else:
        described["page_starts"] = _texts(document, limit=PAGE_START_CHARS)
    return described


def check_proposal(answer: T1Answer, files: Sequence[Resource]) -> list[str]:
    """What breaks the rules of T1 in an answer, as sentences for Claude ([] if none).

    `files` are the files of the subject, which the chapters must cover.
    """
    return (
        _check_objectives(answer)
        + _check_chapters(answer, files)
        + _check_coverage(answer, files)
    )


def _check_objectives(answer: T1Answer) -> list[str]:
    """1 to 5 objectives « Être capable de… », each taught by a chapter."""
    problems: list[str] = []
    count = len(answer.objectives)
    if not 1 <= count <= MAX_OBJECTIVES:
        problems.append(f"Give 1 to {MAX_OBJECTIVES} objectives, not {count}.")
    for number, text in enumerate(answer.objectives, start=1):
        if not OBJECTIVE_START.match(unicodedata.normalize("NFC", text.strip())):
            problems.append(f"Objective {number} must start with « Être capable de ».")
        if not any(number in chapter.objectives for chapter in answer.chapters):
            problems.append(f"Objective {number} is taught by no chapter.")
    return problems


def _check_chapters(answer: T1Answer, files: Sequence[Resource]) -> list[str]:
    """Each chapter has a title, existing objectives, and pages of existing files."""
    problems: list[str] = []
    if not answer.chapters:
        problems.append("Give at least one chapter.")
    by_id = {file.id: file for file in files}
    for number, chapter in enumerate(answer.chapters, start=1):
        if not chapter.title.strip():
            problems.append(f"Chapter {number} has no title.")
        if not chapter.sources:
            problems.append(f"Chapter {number} has no pages.")
        for objective in sorted(set(chapter.objectives)):
            if not 1 <= objective <= len(answer.objectives):
                problems.append(
                    f"Chapter {number} refers to objective {objective},"
                    " which does not exist."
                )
            elif chapter.objectives.count(objective) > 1:
                problems.append(f"Chapter {number} lists objective {objective} twice.")
        used: set[int] = set()
        for source in chapter.sources:
            file = by_id.get(source.file)
            if file is None:
                problems.append(
                    f"Chapter {number} uses file {source.file}, which does not exist."
                )
            elif source.file in used:
                problems.append(
                    f"Chapter {number} uses {_name(file)} twice:"
                    " give a single range of pages per file."
                )
            elif not _exists(source.first_page, source.last_page, file):
                problems.append(
                    f"Chapter {number} cannot cover"
                    f" {_pages(source.first_page, source.last_page)} of {_name(file)},"
                    f" which has pages 1 to {file.page_count}."
                )
            used.add(source.file)
    return problems


def _check_coverage(answer: T1Answer, files: Sequence[Resource]) -> list[str]:
    """The chapters cover each file without gap or overlap (contract T1)."""
    problems: list[str] = []
    for file in files:
        ranges = sorted(
            (source.first_page, source.last_page, number)
            for number, chapter in enumerate(answer.chapters, start=1)
            for source in chapter.sources
            if source.file == file.id
        )
        if not all(_exists(first, last, file) for first, last, _ in ranges):
            continue  # already reported: a coverage message would only add noise
        # The first page that is not covered yet, and the chapter that covers the one
        # before it.
        next_page, previous = 1, 0
        for first, last, number in ranges:
            if first > next_page:
                problems.append(
                    f"No chapter covers {_pages(next_page, first - 1)}"
                    f" of {_name(file)}."
                )
            elif first < next_page:
                both = sorted((previous, number))
                problems.append(
                    f"Chapters {both[0]} and {both[1]} both cover"
                    f" {_pages(first, min(last, next_page - 1))} of {_name(file)}."
                )
            if last >= next_page:
                next_page, previous = last + 1, number
        if next_page <= file.page_count:
            problems.append(
                f"No chapter covers {_pages(next_page, file.page_count)}"
                f" of {_name(file)}."
            )
    return problems


def _exists(first: int, last: int, file: Resource) -> bool:
    return 1 <= first <= last <= file.page_count


def _pages(first: int, last: int) -> str:
    return f"page {first}" if first == last else f"pages {first} to {last}"


def _name(file: Resource) -> str:
    return f"{file.file_name} (file {file.id})"


def _titles(document: Document) -> list[dict[str, Any]]:
    return [
        {"level": heading.level, "title": heading.title, "page": heading.page}
        for heading in document.headings
    ]


def _texts(document: Document, limit: int | None) -> list[dict[str, Any]]:
    """The text of each page, cut after `limit` characters (None: the whole text)."""
    return [
        {"page": number, "text": _clean(page.text)[:limit]}
        for number, page in enumerate(document.pages, start=1)
    ]


def _clean(text: str) -> str:
    """The lines of a text, without blank lines or extra spaces."""
    lines = (" ".join(line.split()) for line in text.splitlines())
    return "\n".join(line for line in lines if line)
