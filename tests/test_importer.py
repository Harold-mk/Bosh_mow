"""Tests of the import of PDF and Markdown files, with text-poor pages (R38).

The PDF files are built by the tests themselves: no real course is needed.
"""

import sqlite3
from datetime import date
from pathlib import Path

import pymupdf
import pytest

from bosh_mow.subjects.importer import (
    UnsupportedFile,
    import_file,
    needs_description,
    read_markdown,
    read_pdf,
)
from bosh_mow.subjects.repository import (
    Heading,
    PageContent,
    Resource,
    create_draft_subject,
    get_subject,
)

BODY = "Body text of the chapter.\n" * 6


def new_pdf(*texts: str) -> pymupdf.Document:
    """A PDF with one page per text, in 11 pt Helvetica."""
    pdf = pymupdf.open()
    for text in texts:
        pdf.new_page().insert_text((72, 72), text, fontsize=11)
    return pdf


def add_image(page: pymupdf.Page) -> None:
    pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 8, 8), False)
    pixmap.clear_with(200)
    page.insert_image(pymupdf.Rect(72, 120, 272, 320), pixmap=pixmap)


# PDF


def test_pdf_pages_keep_their_text_in_order() -> None:
    document = read_pdf(new_pdf("First page", "Second page").tobytes())

    assert document.kind == "pdf"
    assert [page.text.strip() for page in document.pages] == [
        "First page",
        "Second page",
    ]


def test_pdf_bookmarks_give_the_outline() -> None:
    pdf = new_pdf("Intro", "Variance", "Tests")
    pdf.set_toc([[1, "Chapter 1", 1], [2, "Variance", 2], [1, "Chapter 2", 3]])

    document = read_pdf(pdf.tobytes())

    assert document.outline == "structure"
    assert document.headings == [
        Heading(1, "Chapter 1", 1),
        Heading(2, "Variance", 2),
        Heading(1, "Chapter 2", 3),
    ]


def test_pdf_without_bookmarks_guesses_titles_from_their_size_and_weight() -> None:
    pdf = pymupdf.open()
    first = pdf.new_page()
    first.insert_text((72, 72), "Variance", fontsize=20)
    first.insert_text((72, 110), BODY, fontsize=11)
    second = pdf.new_page()
    second.insert_text((72, 72), "Sample variance", fontsize=15)
    second.insert_text((72, 100), "Definition", fontsize=11, fontname="hebo")
    second.insert_text((72, 130), BODY, fontsize=11)

    document = read_pdf(pdf.tobytes())

    assert document.outline == "fonts"
    assert document.headings == [
        Heading(1, "Variance", 1),
        Heading(2, "Sample variance", 2),
        Heading(3, "Definition", 2),
    ]


def test_pdf_counts_images_and_drawn_diagrams() -> None:
    pdf = new_pdf("Photo", "Diagram", "Rule", "Background")
    add_image(pdf[0])
    pdf[1].draw_rect(pymupdf.Rect(72, 120, 300, 300))
    pdf[2].draw_line((72, 120), (500, 120))  # a rule is not a diagram
    pdf[3].draw_rect(pdf[3].rect, fill=(0.9, 0.9, 0.9))  # nor a page background

    document = read_pdf(pdf.tobytes())

    assert [page.image_count for page in document.pages] == [1, 1, 0, 0]


def test_scanned_pdf_without_text_is_refused() -> None:
    pdf = pymupdf.open()
    add_image(pdf.new_page())

    with pytest.raises(UnsupportedFile, match="aucun texte"):
        read_pdf(pdf.tobytes())


def test_password_protected_pdf_is_refused() -> None:
    content = new_pdf("Secret").tobytes(
        encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="secret", owner_pw="owner"
    )

    with pytest.raises(UnsupportedFile, match="mot de passe"):
        read_pdf(content)


def test_unreadable_pdf_is_refused() -> None:
    with pytest.raises(UnsupportedFile, match="illisible"):
        read_pdf(b"this is not a PDF")


# Markdown


def test_markdown_sections_play_the_role_of_pages() -> None:
    text = (
        "Intro\n# Chapitre 1\nTexte\n## Section 1.1\nDétail\n### Point\nEncore\n"
        "# Chapitre 2\nFin\n"
    )

    document = read_markdown(text)

    assert document.kind == "markdown"
    assert document.outline == "structure"
    assert [page.text for page in document.pages] == [
        "Intro",
        "# Chapitre 1\nTexte",
        "## Section 1.1\nDétail\n### Point\nEncore",
        "# Chapitre 2\nFin",
    ]
    assert document.headings == [
        Heading(1, "Chapitre 1", 2),
        Heading(2, "Section 1.1", 3),
        Heading(1, "Chapitre 2", 4),
    ]


def test_markdown_titles_inside_code_blocks_are_ignored() -> None:
    document = read_markdown("# Code\n```python\n# not a title\nx = 1\n```\n")

    assert len(document.pages) == 1
    assert document.headings == [Heading(1, "Code", 1)]


def test_markdown_without_titles_is_a_single_page() -> None:
    document = read_markdown("Some notes.\n![schéma](schema.png)\n")

    assert document.outline == "none"
    assert document.pages == [PageContent("Some notes.\n![schéma](schema.png)", 1)]
    assert document.headings == []


def test_empty_markdown_is_refused() -> None:
    with pytest.raises(UnsupportedFile, match="vide"):
        read_markdown("  \n\n")


# Text-poor pages


@pytest.mark.parametrize(
    ("page", "expected"),
    [
        (PageContent("Courbe d'erreur", image_count=1), True),
        (PageContent("x" * 149, image_count=1), True),
        (PageContent("x" * 150, image_count=1), False),
        (PageContent("Titre seul", image_count=0), False),
    ],
    ids=["short-with-image", "149-chars", "150-chars", "no-image"],
)
def test_r38_text_poor_page_with_an_image_needs_a_description(
    page: PageContent, expected: bool
) -> None:
    assert needs_description(page) is expected


# Import into a subject


def test_import_keeps_an_untouched_copy_of_the_file(
    db: sqlite3.Connection, tmp_path: Path
) -> None:
    subject_id = create_draft_subject(db, "Statistiques", date(2027, 1, 15))
    content = new_pdf("Page 1", "Page 2").tobytes()

    resource = import_file(
        db, tmp_path / "resources", subject_id, "Cours de stats.pdf", content
    )

    assert resource == Resource(resource.id, "Cours de stats.pdf", "pdf", 2)
    assert (tmp_path / "resources" / f"{resource.id}.pdf").read_bytes() == content
    subject = get_subject(db, subject_id)
    assert subject is not None
    assert subject.resources == [resource]


def test_import_reads_markdown_and_keeps_its_outline(
    db: sqlite3.Connection, tmp_path: Path
) -> None:
    subject_id = create_draft_subject(db, "Statistiques", date(2027, 1, 15))
    content = b"# Variance\nNotes de cours\n"

    resource = import_file(db, tmp_path / "resources", subject_id, "notes.md", content)

    assert (tmp_path / "resources" / f"{resource.id}.md").read_bytes() == content
    headings = db.execute(
        "SELECT level, title, page FROM heading WHERE resource_id = ?", (resource.id,)
    ).fetchall()
    assert headings == [(1, "Variance", 1)]


@pytest.mark.parametrize(
    ("file_name", "content", "message"),
    [
        ("notes.docx", b"...", "PDF et les fichiers Markdown"),
        ("notes.md", "é".encode("cp1252"), "UTF-8"),
    ],
    ids=["other-type", "not-utf8"],
)
def test_unsupported_file_changes_nothing(
    db: sqlite3.Connection, tmp_path: Path, file_name: str, content: bytes, message: str
) -> None:
    subject_id = create_draft_subject(db, "Statistiques", date(2027, 1, 15))

    with pytest.raises(UnsupportedFile, match=message):
        import_file(db, tmp_path / "resources", subject_id, file_name, content)

    subject = get_subject(db, subject_id)
    assert subject is not None
    assert subject.resources == []
    assert not (tmp_path / "resources").exists()
