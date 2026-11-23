"""Tests of the storage of subjects: drafts, files, objectives, chapters (R1 to R3)."""

import sqlite3
from datetime import date

import pytest

from bosh_mow.subjects.repository import (
    Chapter,
    ChapterSource,
    Document,
    PageContent,
    Resource,
    SubjectSummary,
    activate_subject,
    add_resource,
    create_draft_subject,
    get_subject,
    list_subjects,
)

EXAM = date(2027, 1, 15)


def make_draft(db: sqlite3.Connection) -> tuple[int, int]:
    """A draft subject with a 3-page PDF; returns the subject and file ids."""
    subject_id = create_draft_subject(db, "Économétrie", EXAM)
    pages = [PageContent("Intro"), PageContent("", image_count=1), PageContent("Fin")]
    document = Document("pdf", pages, [], "none")
    return subject_id, add_resource(db, subject_id, "cours.pdf", document)


def test_draft_subject_is_hidden_from_the_list(db: sqlite3.Connection) -> None:
    make_draft(db)

    assert list_subjects(db) == []


def test_unknown_subject_is_none(db: sqlite3.Connection) -> None:
    assert get_subject(db, 999) is None


def test_imported_file_keeps_its_pages_in_order(db: sqlite3.Connection) -> None:
    subject_id, pdf = make_draft(db)

    subject = get_subject(db, subject_id)
    assert subject is not None
    assert subject.resources == [Resource(pdf, "cours.pdf", "pdf", 3)]
    pages = db.execute(
        "SELECT number, text, image_count FROM page WHERE resource_id = ?"
        " ORDER BY number",
        (pdf,),
    ).fetchall()
    assert pages == [(1, "Intro", 0), (2, "", 1), (3, "Fin", 0)]


def test_r2_activated_subject_has_its_objectives_and_chapters(
    db: sqlite3.Connection,
) -> None:
    subject_id, pdf = make_draft(db)
    objectives = ["Être capable de A", "Être capable de B"]
    chapters = [
        Chapter("Régression", "core", [ChapterSource(pdf, 1, 2)], [1]),
        Chapter("Séries temporelles", "secondary", [ChapterSource(pdf, 3, 3)], [1, 2]),
    ]

    activate_subject(db, subject_id, objectives, chapters)

    subject = get_subject(db, subject_id)
    assert subject is not None
    assert subject.status == "active"
    assert subject.objectives == objectives
    assert subject.chapters == chapters
    assert list_subjects(db) == [SubjectSummary(subject_id, "Économétrie", EXAM, 2, 1)]


def test_chapter_can_combine_several_files(db: sqlite3.Connection) -> None:
    subject_id, pdf = make_draft(db)
    markdown = Document("markdown", [PageContent("# TD")], [], "none")
    notes = add_resource(db, subject_id, "notes.md", markdown)
    sources = [ChapterSource(pdf, 1, 3), ChapterSource(notes, 1, 1)]
    chapter = Chapter("Régression", "core", sources, [1])

    activate_subject(db, subject_id, ["Être capable de A"], [chapter])

    subject = get_subject(db, subject_id)
    assert subject is not None
    assert subject.chapters == [chapter]


@pytest.mark.parametrize(
    "objectives",
    [[], ["Être capable de A"] * 6, ["  "]],
    ids=["none", "six", "blank"],
)
def test_r2_subject_needs_one_to_five_objectives(
    db: sqlite3.Connection, objectives: list[str]
) -> None:
    subject_id, _ = make_draft(db)

    with pytest.raises(ValueError, match="1 to 5 objectives"):
        activate_subject(db, subject_id, objectives, [])

    subject = get_subject(db, subject_id)
    assert subject is not None
    assert subject.status == "draft"


def test_r2_subject_can_wait_for_its_chapters(db: sqlite3.Connection) -> None:
    """Without Claude, the objectives are written by hand and the split comes later."""
    subject_id, _ = make_draft(db)

    activate_subject(db, subject_id, ["Être capable de A"], [])

    subject = get_subject(db, subject_id)
    assert subject is not None
    assert subject.status == "active"
    assert subject.chapters == []


def test_failed_activation_saves_nothing(db: sqlite3.Connection) -> None:
    subject_id, pdf = make_draft(db)
    # The chapter refers to objective 2, which does not exist.
    wrong = Chapter("Régression", "core", [ChapterSource(pdf, 1, 3)], [2])

    with pytest.raises(ValueError, match="missing objective"):
        activate_subject(db, subject_id, ["Être capable de A"], [wrong])

    subject = get_subject(db, subject_id)
    assert subject is not None
    assert (subject.status, subject.objectives, subject.chapters) == ("draft", [], [])


def test_chapter_cannot_use_a_file_of_another_subject(db: sqlite3.Connection) -> None:
    subject_id, _ = make_draft(db)
    _, other_pdf = make_draft(db)
    chapter = Chapter("Régression", "core", [ChapterSource(other_pdf, 1, 3)], [1])

    with pytest.raises(ValueError, match="another subject"):
        activate_subject(db, subject_id, ["Être capable de A"], [chapter])


def test_subject_is_activated_only_once(db: sqlite3.Connection) -> None:
    subject_id, _ = make_draft(db)
    activate_subject(db, subject_id, ["Être capable de A"], [])

    with pytest.raises(ValueError, match="not a draft"):
        activate_subject(db, subject_id, ["Être capable de B"], [])


def test_r1_every_file_belongs_to_a_subject(db: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        add_resource(db, 999, "cours.pdf", Document("pdf", [], [], "none"))
