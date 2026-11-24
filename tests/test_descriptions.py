"""Tests of T11: the description of the pages whose content is mostly in images."""

import sqlite3
from datetime import date
from pathlib import Path

import pymupdf
import pytest
from fake_ai import FakeEngine

from bosh_mow.ai.gateway import Gateway
from bosh_mow.ai.schemas import T11Answer
from bosh_mow.ai.tasks import latest_task
from bosh_mow.subjects.descriptions import (
    IMAGE_SIZE,
    TASK,
    DescriptionCount,
    check_description,
    describe_page,
    description_counts,
    request_descriptions,
)
from bosh_mow.subjects.importer import import_file
from bosh_mow.subjects.repository import (
    Chapter,
    ChapterSource,
    activate_subject,
    create_draft_subject,
)

LONG_TEXT = "La variance mesure la dispersion des valeurs autour de leur moyenne. " * 3


def slides() -> bytes:
    """Three slides: a text page, a diagram with a title, a title alone."""
    pdf = pymupdf.open()
    text = pdf.new_page(width=720, height=405)
    text.insert_textbox(pymupdf.Rect(40, 40, 680, 380), LONG_TEXT, fontsize=14)
    diagram = pdf.new_page(width=720, height=405)
    diagram.insert_text((40, 50), "Erreur et complexité", fontsize=20)
    diagram.draw_rect(pymupdf.Rect(100, 100, 400, 350), color=(0, 0, 0))
    title = pdf.new_page(width=720, height=405)
    title.insert_text((40, 50), "Questions ?", fontsize=20)
    return pdf.tobytes()


def make_subject(db: sqlite3.Connection, resources: Path) -> tuple[int, int]:
    """A subject split into one chapter, with the slides and notes with an image."""
    subject_id = create_draft_subject(db, "Machine learning", date(2027, 1, 15))
    deck = import_file(db, resources, subject_id, "cours.pdf", slides())
    notes = import_file(
        db, resources, subject_id, "notes.md", b"# Schema\n![courbe](c.png)\n"
    )
    sources = [ChapterSource(deck.id, 1, 3), ChapterSource(notes.id, 1, 1)]
    chapter = Chapter("Biais et variance", "core", sources, [1])
    activate_subject(db, subject_id, ["Être capable de choisir un modèle"], [chapter])
    return subject_id, deck.id


def answer(page: int = 2, **changes: object) -> dict[str, object]:
    return {
        "page": page,
        "description": "Un rectangle vide sous le titre « Erreur et complexité ».",
        "elements": ["titre : Erreur et complexité", "un rectangle"],
        "to_check": None,
        **changes,
    }


# Which pages are described


def test_only_the_text_poor_pdf_pages_with_an_image_are_described(
    db: sqlite3.Connection, tmp_path: Path
) -> None:
    subject_id, deck = make_subject(db, tmp_path)

    assert request_descriptions(db, subject_id) == 1

    task = latest_task(db, TASK, subject_id)
    assert task is not None
    queued = db.execute("SELECT input FROM ai_task WHERE kind = ?", (TASK,)).fetchall()
    assert queued == [(f'{{"resource_id": {deck}, "page": 2}}',)]


def test_a_described_page_is_not_described_again(
    db: sqlite3.Connection, tmp_path: Path
) -> None:
    subject_id, deck = make_subject(db, tmp_path)
    gateway = Gateway(FakeEngine([answer()]), tmp_path / "ai_calls.jsonl")
    describe_page(db, gateway, tmp_path, deck, 2)

    assert request_descriptions(db, subject_id) == 0


# Asking Claude, with the fake AI


def test_the_image_of_the_page_goes_with_its_text_and_chapter(
    db: sqlite3.Connection, tmp_path: Path
) -> None:
    _, deck = make_subject(db, tmp_path)
    engine = FakeEngine([answer()])

    describe_page(db, Gateway(engine, tmp_path / "ai_calls.jsonl"), tmp_path, deck, 2)

    (image,) = engine.images[0]
    assert image.startswith(b"\x89PNG")
    pixmap = pymupdf.Pixmap(image)
    assert max(pixmap.width, pixmap.height) == IMAGE_SIZE
    sent = engine.prompts[0]
    assert '"document": "cours.pdf"' in sent
    assert '"chapter": "Biais et variance"' in sent
    assert '"text": "Erreur et complexité"' in sent


def test_the_description_is_kept_with_the_page(
    db: sqlite3.Connection, tmp_path: Path
) -> None:
    subject_id, deck = make_subject(db, tmp_path)
    gateway = Gateway(
        FakeEngine([answer(to_check="La légende est illisible.")]), tmp_path / "log"
    )
    assert description_counts(db, subject_id) == [DescriptionCount(deck, 1, 0)]

    describe_page(db, gateway, tmp_path, deck, 2)

    row = db.execute(
        "SELECT description, elements, to_check FROM page_description"
        " WHERE resource_id = ? AND number = 2",
        (deck,),
    ).fetchone()
    assert row == (
        "Un rectangle vide sous le titre « Erreur et complexité ».",
        '["titre : Erreur et complexité", "un rectangle"]',
        "La légende est illisible.",
    )
    assert description_counts(db, subject_id) == [DescriptionCount(deck, 1, 1)]


def test_a_description_that_breaks_the_rules_is_asked_again(
    db: sqlite3.Connection, tmp_path: Path
) -> None:
    _, deck = make_subject(db, tmp_path)
    engine = FakeEngine([answer(description="mot " * 151), answer()])

    describe_page(db, Gateway(engine, tmp_path / "ai_calls.jsonl"), tmp_path, deck, 2)

    assert "The description has 151 words: 150 at most." in engine.prompts[1]
    assert engine.images[1] == engine.images[0]  # the page comes again


# The rules of T11


@pytest.mark.parametrize(
    ("changes", "problems"),
    [
        ({}, []),
        ({"description": "  "}, ["The description is empty."]),
        (
            {"description": "mot " * 151},
            ["The description has 151 words: 150 at most."],
        ),
        ({"page": 3}, ["The page is 2, not 3."]),
    ],
    ids=["valid", "empty", "too-long", "other-page"],
)
def test_t11_rules(changes: dict[str, object], problems: list[str]) -> None:
    assert check_description(T11Answer.model_validate(answer(**changes)), 2) == problems
