"""Storage of subjects and their content: objectives, imported files, chapters.

A subject stays a draft while it is being created, and appears in the app only once
its objectives are validated (R2). Its chapters can come later, if Claude is away.
"""

import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Literal

type Kind = Literal["pdf", "markdown"]
type Role = Literal["core", "secondary"]
# Where the outline of a file comes from: PDF bookmarks or Markdown # and ## titles
# ("structure"), titles guessed from their size or weight ("fonts"), or nothing.
type Outline = Literal["structure", "fonts", "none"]

MAX_OBJECTIVES = 5  # R2


@dataclass(frozen=True)
class PageContent:
    """Text of a PDF page or of a Markdown section, and its number of images.

    For a PDF, diagrams drawn as vectors count as images.
    """

    text: str
    image_count: int = 0


@dataclass(frozen=True)
class Heading:
    """A title of a file's outline; `page` is a PDF page or a Markdown section."""

    level: int
    title: str
    page: int


@dataclass(frozen=True)
class Document:
    """An imported file once read: its pages (numbered from 1) and its outline."""

    kind: Kind
    pages: list[PageContent]
    headings: list[Heading]
    outline: Outline


@dataclass(frozen=True)
class ChapterSource:
    """The pages of one imported file that a chapter covers."""

    resource_id: int
    first_page: int
    last_page: int


@dataclass(frozen=True)
class Chapter:
    """A chapter; `objectives` are positions (from 1) in the subject's objectives."""

    title: str
    role: Role
    sources: list[ChapterSource]
    objectives: list[int]


@dataclass(frozen=True)
class Resource:
    id: int
    file_name: str
    kind: Kind
    page_count: int


@dataclass(frozen=True)
class Subject:
    id: int
    name: str
    exam_date: date
    status: str
    objectives: list[str]
    chapters: list[Chapter]  # in order: chapter 1 first
    resources: list[Resource]
    glossary: list[str]  # technical terms that are never translated (T9)


@dataclass(frozen=True)
class SubjectSummary:
    """One line of the "Mes matières" screen."""

    id: int
    name: str
    exam_date: date
    chapter_count: int
    resource_count: int


def create_draft_subject(
    connection: sqlite3.Connection, name: str, exam_date: date
) -> int:
    """Create a subject as a draft, hidden until it is activated, and return its id."""
    if not name.strip():
        raise ValueError("A subject needs a name.")
    with connection:
        cursor = connection.execute(
            "INSERT INTO subject (name, exam_date) VALUES (?, ?)",
            (name.strip(), exam_date.isoformat()),
        )
    return cursor.lastrowid


def update_draft(
    connection: sqlite3.Connection, subject_id: int, name: str, exam_date: date
) -> None:
    """Change the name or the exam date of a subject still being created."""
    if not name.strip():
        raise ValueError("A subject needs a name.")
    with connection:
        changed = connection.execute(
            "UPDATE subject SET name = ?, exam_date = ?"
            " WHERE id = ? AND status = 'draft'",
            (name.strip(), exam_date.isoformat(), subject_id),
        ).rowcount
    if not changed:
        raise ValueError(f"Subject {subject_id} is not a draft.")


def get_draft(connection: sqlite3.Connection) -> Subject | None:
    """The subject left being created, to take it up again; None if there is none."""
    row = connection.execute(
        "SELECT id FROM subject WHERE status = 'draft' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return get_subject(connection, row[0]) if row else None


def add_resource(
    connection: sqlite3.Connection,
    subject_id: int,
    file_name: str,
    document: Document,
) -> int:
    """Record an imported file with its pages and its outline; return its id."""
    with connection:
        resource_id = connection.execute(
            "INSERT INTO resource (subject_id, file_name, kind, outline)"
            " VALUES (?, ?, ?, ?)",
            (subject_id, file_name, document.kind, document.outline),
        ).lastrowid
        connection.executemany(
            "INSERT INTO page (resource_id, number, text, image_count)"
            " VALUES (?, ?, ?, ?)",
            [
                (resource_id, number, page.text, page.image_count)
                for number, page in enumerate(document.pages, start=1)
            ],
        )
        connection.executemany(
            "INSERT INTO heading (resource_id, position, level, title, page)"
            " VALUES (?, ?, ?, ?, ?)",
            [
                (resource_id, position, heading.level, heading.title, heading.page)
                for position, heading in enumerate(document.headings, start=1)
            ],
        )
    return resource_id


def get_document(connection: sqlite3.Connection, resource_id: int) -> Document:
    """An imported file as it was read: its pages and its outline."""
    row = connection.execute(
        "SELECT kind, outline FROM resource WHERE id = ?", (resource_id,)
    ).fetchone()
    if row is None:
        raise ValueError(f"File {resource_id} does not exist.")
    kind, outline = row
    pages = [
        PageContent(text, image_count)
        for text, image_count in connection.execute(
            "SELECT text, image_count FROM page WHERE resource_id = ? ORDER BY number",
            (resource_id,),
        )
    ]
    headings = [
        Heading(level, title, page)
        for level, title, page in connection.execute(
            "SELECT level, title, page FROM heading WHERE resource_id = ?"
            " ORDER BY position",
            (resource_id,),
        )
    ]
    return Document(kind, pages, headings, outline)


def delete_resource(connection: sqlite3.Connection, resource_id: int) -> None:
    """Forget an imported file, with its pages and its outline."""
    with connection:
        connection.execute("DELETE FROM resource WHERE id = ?", (resource_id,))


def activate_subject(
    connection: sqlite3.Connection,
    subject_id: int,
    objectives: Sequence[str],
    chapters: Sequence[Chapter],
    glossary: Sequence[str] = (),
) -> None:
    """Save the validated objectives, chapters and glossary; show the subject (R2, R3).

    `chapters` can be empty: if Claude is unavailable, the objectives are written by
    hand in the meantime. Claude's proposal is then validated later in the same way,
    and its objectives replace the handwritten ones. All or nothing is saved.
    """
    if not 1 <= len(objectives) <= MAX_OBJECTIVES or not all(
        text.strip() for text in objectives
    ):
        raise ValueError(f"A subject needs 1 to {MAX_OBJECTIVES} objectives.")
    row = connection.execute(
        "SELECT status, EXISTS (SELECT 1 FROM chapter WHERE subject_id = s.id)"
        " FROM subject s WHERE id = ?",
        (subject_id,),
    ).fetchone()
    if row is None or row[0] == "archived" or row[1]:
        raise ValueError(
            f"Subject {subject_id} is unknown, archived or already split into chapters."
        )
    own_files = {
        resource_id
        for (resource_id,) in connection.execute(
            "SELECT id FROM resource WHERE subject_id = ?", (subject_id,)
        )
    }
    with connection:
        connection.execute("DELETE FROM objective WHERE subject_id = ?", (subject_id,))
        objective_ids = [
            connection.execute(
                "INSERT INTO objective (subject_id, position, text) VALUES (?, ?, ?)",
                (subject_id, position, text.strip()),
            ).lastrowid
            for position, text in enumerate(objectives, start=1)
        ]
        for number, chapter in enumerate(chapters, start=1):
            _insert_chapter(
                connection, subject_id, number, chapter, objective_ids, own_files
            )
        connection.execute(
            "DELETE FROM glossary_term WHERE subject_id = ?", (subject_id,)
        )
        connection.executemany(
            "INSERT OR IGNORE INTO glossary_term (subject_id, term) VALUES (?, ?)",
            [(subject_id, term.strip()) for term in glossary if term.strip()],
        )
        connection.execute(
            "UPDATE subject SET status = 'active' WHERE id = ?", (subject_id,)
        )


def _insert_chapter(
    connection: sqlite3.Connection,
    subject_id: int,
    number: int,
    chapter: Chapter,
    objective_ids: Sequence[int],
    own_files: set[int],
) -> None:
    chapter_id = connection.execute(
        "INSERT INTO chapter (subject_id, number, title, role) VALUES (?, ?, ?, ?)",
        (subject_id, number, chapter.title.strip(), chapter.role),
    ).lastrowid
    for source in chapter.sources:
        if source.resource_id not in own_files:
            raise ValueError(f"Chapter {number} uses a file of another subject.")
        connection.execute(
            "INSERT INTO chapter_source"
            " (chapter_id, resource_id, first_page, last_page) VALUES (?, ?, ?, ?)",
            (chapter_id, source.resource_id, source.first_page, source.last_page),
        )
    for position in chapter.objectives:
        if not 1 <= position <= len(objective_ids):
            raise ValueError(f"Chapter {number} uses a missing objective.")
        connection.execute(
            "INSERT INTO chapter_objective (chapter_id, objective_id) VALUES (?, ?)",
            (chapter_id, objective_ids[position - 1]),
        )


def chapter_ids(connection: sqlite3.Connection, subject_id: int) -> list[int]:
    """The ids of the chapters of a subject, chapter 1 first."""
    return [
        chapter_id
        for (chapter_id,) in connection.execute(
            "SELECT id FROM chapter WHERE subject_id = ? ORDER BY number", (subject_id,)
        )
    ]


def list_subjects(connection: sqlite3.Connection) -> list[SubjectSummary]:
    """The active subjects, the closest exam first."""
    rows = connection.execute(
        """
        SELECT s.id, s.name, s.exam_date,
               (SELECT COUNT(*) FROM chapter WHERE subject_id = s.id),
               (SELECT COUNT(*) FROM resource WHERE subject_id = s.id)
        FROM subject s
        WHERE s.status = 'active'
        ORDER BY s.exam_date, s.name
        """
    ).fetchall()
    return [
        SubjectSummary(subject_id, name, date.fromisoformat(exam), chapters, files)
        for subject_id, name, exam, chapters, files in rows
    ]


def get_subject(connection: sqlite3.Connection, subject_id: int) -> Subject | None:
    """A subject with its objectives, chapters and files, or None if it is unknown."""
    row = connection.execute(
        "SELECT name, exam_date, status FROM subject WHERE id = ?", (subject_id,)
    ).fetchone()
    if row is None:
        return None
    name, exam_date, status = row
    objectives = [
        text
        for (text,) in connection.execute(
            "SELECT text FROM objective WHERE subject_id = ? ORDER BY position",
            (subject_id,),
        )
    ]
    resources = [
        Resource(*resource)
        for resource in connection.execute(
            """
            SELECT r.id, r.file_name, r.kind, COUNT(p.number)
            FROM resource r LEFT JOIN page p ON p.resource_id = r.id
            WHERE r.subject_id = ?
            GROUP BY r.id
            ORDER BY r.id
            """,
            (subject_id,),
        )
    ]
    chapters = [
        _read_chapter(connection, chapter_id, title, role)
        for chapter_id, title, role in connection.execute(
            "SELECT id, title, role FROM chapter WHERE subject_id = ? ORDER BY number",
            (subject_id,),
        ).fetchall()
    ]
    glossary = [
        term
        for (term,) in connection.execute(
            "SELECT term FROM glossary_term WHERE subject_id = ? ORDER BY rowid",
            (subject_id,),
        )
    ]
    return Subject(
        subject_id,
        name,
        date.fromisoformat(exam_date),
        status,
        objectives,
        chapters,
        resources,
        glossary,
    )


def _read_chapter(
    connection: sqlite3.Connection, chapter_id: int, title: str, role: Role
) -> Chapter:
    sources = [
        ChapterSource(*source)
        for source in connection.execute(
            "SELECT resource_id, first_page, last_page FROM chapter_source"
            " WHERE chapter_id = ? ORDER BY resource_id",
            (chapter_id,),
        )
    ]
    objectives = [
        position
        for (position,) in connection.execute(
            """
            SELECT o.position
            FROM chapter_objective co JOIN objective o ON o.id = co.objective_id
            WHERE co.chapter_id = ?
            ORDER BY o.position
            """,
            (chapter_id,),
        )
    ]
    return Chapter(title, role, sources, objectives)
