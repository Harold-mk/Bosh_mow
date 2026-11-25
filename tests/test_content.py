"""Tests of the storage of notions and questions (T1 pass 2, T2, R3 to R5)."""

import sqlite3
from dataclasses import asdict, replace
from datetime import date

import pytest

from bosh_mow.content.repository import (
    NewNotion,
    NewQuestion,
    get_notions,
    get_question,
    get_questions,
    mark_studied,
    report_question,
    save_notions,
    save_questions,
)
from bosh_mow.subjects.repository import (
    Chapter,
    ChapterSource,
    Document,
    PageContent,
    activate_subject,
    add_resource,
    create_draft_subject,
)

MCQ = NewQuestion(
    role="review",
    type="concept",
    level="explain",
    format="mcq",
    difficulty=2,
    statement="Why do we divide by n − 1 in the sample variance?",
    first_page=4,
    last_page=5,
    content={
        "options": [
            {
                "text": "One degree of freedom is lost when the mean is estimated",
                "correct": True,
                "explanation": "C'est ça : la moyenne vient des mêmes données.",
            },
            {
                "text": "It is only a convention",
                "correct": False,
                "explanation": "Erreur fréquente : ce n'est pas une convention.",
            },
        ]
    },
)
VALUE = NewQuestion(
    role="review",
    type="calculation",
    level="apply",
    format="value",
    difficulty=1,
    statement="What is the sample variance of 2, 4 and 6?",
    first_page=6,
    last_page=6,
    content={"value": 4, "tolerance": 0.01},
)


def make_chapter(db: sqlite3.Connection) -> tuple[int, int]:
    """An active subject with one chapter on a 20-page PDF: (chapter id, file id)."""
    subject_id = create_draft_subject(db, "Statistiques", date(2027, 1, 15))
    pages = [PageContent(f"Page {number}") for number in range(1, 21)]
    file_id = add_resource(
        db, subject_id, "stats.pdf", Document("pdf", pages, [], "none")
    )
    chapter = Chapter("Variance", "core", [ChapterSource(file_id, 1, 20)], [1])
    activate_subject(
        db, subject_id, ["Être capable de calculer une variance"], [chapter]
    )
    (chapter_id,) = db.execute(
        "SELECT id FROM chapter WHERE subject_id = ?", (subject_id,)
    ).fetchone()
    return chapter_id, file_id


def test_r3_validated_notions_are_saved_with_their_questions(
    db: sqlite3.Connection,
) -> None:
    chapter_id, file_id = make_chapter(db)
    notions = [
        NewNotion(
            "Variance d'un échantillon", "Pourquoi n − 1.", file_id, 4, 6, [MCQ, VALUE]
        ),
        NewNotion("Écart-type", "La racine de la variance.", file_id, 7, 9),
    ]

    first, second = save_notions(db, chapter_id, notions)

    saved = get_notions(db, chapter_id)
    assert [(n.id, n.number, n.title, n.first_page, n.studied) for n in saved] == [
        (first, 1, "Variance d'un échantillon", 4, False),
        (second, 2, "Écart-type", 7, False),
    ]
    mcq, value = get_questions(db, first)
    assert asdict(mcq) == {
        **asdict(MCQ),
        "id": mcq.id,
        "notion_id": first,
        "reported": False,
    }
    assert value.content == {"value": 4, "tolerance": 0.01}
    assert get_questions(db, second) == []


def test_the_notions_of_a_chapter_are_saved_once(db: sqlite3.Connection) -> None:
    chapter_id, file_id = make_chapter(db)
    save_notions(db, chapter_id, [NewNotion("Variance", "…", file_id, 1, 20)])

    with pytest.raises(ValueError, match="already has its notions"):
        save_notions(db, chapter_id, [NewNotion("Autre", "…", file_id, 1, 20)])


def test_the_questions_of_a_notion_are_saved_once_written(
    db: sqlite3.Connection,
) -> None:
    chapter_id, file_id = make_chapter(db)
    (notion_id,) = save_notions(
        db, chapter_id, [NewNotion("Variance", "Pourquoi n − 1.", file_id, 4, 6)]
    )

    save_questions(db, notion_id, [MCQ, VALUE])

    assert [q.statement for q in get_questions(db, notion_id)] == [
        MCQ.statement,
        VALUE.statement,
    ]
    with pytest.raises(ValueError, match="already has its questions"):
        save_questions(db, notion_id, [MCQ])


def test_r5_a_question_keeps_to_the_known_formats(db: sqlite3.Connection) -> None:
    chapter_id, file_id = make_chapter(db)
    wrong = replace(MCQ, format="qcm")  # the French name instead of "mcq"

    with pytest.raises(sqlite3.IntegrityError):
        save_notions(
            db, chapter_id, [NewNotion("Variance", "…", file_id, 1, 20, [wrong])]
        )

    assert get_notions(db, chapter_id) == []  # nothing was saved


def test_a_reported_question_leaves_the_reviews(db: sqlite3.Connection) -> None:
    chapter_id, file_id = make_chapter(db)
    (notion_id,) = save_notions(
        db, chapter_id, [NewNotion("V", "…", file_id, 4, 6, [MCQ])]
    )
    (question,) = get_questions(db, notion_id)

    report_question(db, question.id)

    reported = get_question(db, question.id)
    assert reported is not None
    assert reported.reported
    with pytest.raises(ValueError, match="does not exist"):
        report_question(db, 999)


def test_r13_a_notion_is_marked_as_studied(db: sqlite3.Connection) -> None:
    chapter_id, file_id = make_chapter(db)
    (notion_id,) = save_notions(db, chapter_id, [NewNotion("V", "…", file_id, 4, 6)])

    mark_studied(db, notion_id)

    (notion,) = get_notions(db, chapter_id)
    assert notion.studied
