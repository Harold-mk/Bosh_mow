"""Import of PDF and Markdown files, without AI: text, outline and images of each page.

The text and the outline go to the database; the file itself is kept as an untouched
copy in the data folder. Error messages are shown as they are in the interface.
"""

import re
import sqlite3
from collections import Counter
from pathlib import Path

import pymupdf

from bosh_mow.subjects.repository import (
    Document,
    Heading,
    Kind,
    PageContent,
    Resource,
    add_resource,
    delete_resource,
)

KINDS: dict[str, Kind] = {".pdf": "pdf", ".md": "markdown", ".markdown": "markdown"}
TEXT_POOR_LIMIT = 150  # R38: a page with fewer characters and an image is described
MIN_DIAGRAM_SIZE = 20  # in points: smaller drawings are rules or decorations
TITLE_SIZE_RATIO = 1.15  # a line this much bigger than the body text may be a title

MARKDOWN_TITLE = re.compile(r"^(#{1,2})\s+(.+?)\s*#*\s*$")  # "# Title" or "## Title"
MARKDOWN_FENCE = re.compile(r"^\s*(```|~~~)")  # start or end of a code block
MARKDOWN_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")  # ![text](file)


class UnsupportedFile(ValueError):
    """A file that cannot be imported; its message is meant for the user."""


def import_file(
    connection: sqlite3.Connection,
    resources_dir: Path,
    subject_id: int,
    file_name: str,
    content: bytes,
) -> Resource:
    """Read a PDF or Markdown file, record it and keep an untouched copy of it.

    An unsupported file raises UnsupportedFile and changes nothing.
    """
    kind = KINDS.get(Path(file_name).suffix.lower())
    if kind is None:
        raise UnsupportedFile(
            "Seuls les PDF et les fichiers Markdown (.md) sont pris en charge."
        )
    document = read_pdf(content) if kind == "pdf" else read_markdown(_decode(content))
    resource_id = add_resource(connection, subject_id, file_name, document)
    try:
        resources_dir.mkdir(parents=True, exist_ok=True)
        copy_path(resources_dir, resource_id, kind).write_bytes(content)
    except OSError:
        delete_resource(connection, resource_id)
        raise
    return Resource(resource_id, file_name, kind, len(document.pages))


def remove_file(
    connection: sqlite3.Connection, resources_dir: Path, resource: Resource
) -> None:
    """Forget an imported file, and delete its copy."""
    delete_resource(connection, resource.id)
    copy_path(resources_dir, resource.id, resource.kind).unlink(missing_ok=True)


def copy_path(resources_dir: Path, resource_id: int, kind: Kind) -> Path:
    """Where the untouched copy of an imported file is kept."""
    return resources_dir / f"{resource_id}.{'pdf' if kind == 'pdf' else 'md'}"


def needs_description(page: PageContent) -> bool:
    """R38: a page of fewer than 150 characters with an image is described by Claude."""
    return len(" ".join(page.text.split())) < TEXT_POOR_LIMIT and page.image_count > 0


def read_pdf(content: bytes) -> Document:
    """Text and images of each page, and the outline: bookmarks, or guessed titles."""
    try:
        pdf = pymupdf.open(stream=content, filetype="pdf")
    except pymupdf.FileDataError as error:
        raise UnsupportedFile("Ce fichier PDF est illisible.") from error
    with pdf:
        if pdf.needs_pass:
            raise UnsupportedFile(
                "Ce PDF est protégé par un mot de passe : "
                "retire-le avant de l'importer."
            )
        pages = [PageContent(page.get_text(), _image_count(page)) for page in pdf]
        if not any(page.text.strip() for page in pages):
            raise UnsupportedFile(
                "Ce PDF ne contient aucun texte (PDF scanné ?) : "
                "il n'est pas pris en charge pour l'instant."
            )
        bookmarks = [
            Heading(level, title.strip(), page)
            for level, title, page in pdf.get_toc()
            if page >= 1 and title.strip()
        ]
        if bookmarks:
            return Document("pdf", pages, bookmarks, "structure")
        titles = _guess_titles(pdf)
        return Document("pdf", pages, titles, "fonts" if titles else "none")


def read_markdown(text: str) -> Document:
    """Sections delimited by # and ## titles: each one plays the role of a page."""
    sections: list[list[str]] = [[]]
    headings: list[Heading] = []
    in_code = False
    for line in text.splitlines():
        if MARKDOWN_FENCE.match(line):
            in_code = not in_code
        title = None if in_code else MARKDOWN_TITLE.match(line)
        if title:
            if any(previous.strip() for previous in sections[-1]):
                sections.append([])
            headings.append(Heading(len(title.group(1)), title.group(2), len(sections)))
        sections[-1].append(line)
    pages = [
        PageContent(section, len(MARKDOWN_IMAGE.findall(section)))
        for section in ("\n".join(lines).strip() for lines in sections)
        if section
    ]
    if not pages:
        raise UnsupportedFile("Ce fichier Markdown est vide.")
    return Document("markdown", pages, headings, "structure" if headings else "none")


def _decode(content: bytes) -> str:
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise UnsupportedFile(
            "Ce fichier Markdown n'est pas encodé en UTF-8."
        ) from error


def _image_count(page: pymupdf.Page) -> int:
    """Images, plus diagrams drawn as vectors: neither rules nor page backgrounds."""
    page_area = page.rect.get_area()
    diagrams = [
        rect
        for rect in page.cluster_drawings()
        if rect.width >= MIN_DIAGRAM_SIZE
        and rect.height >= MIN_DIAGRAM_SIZE
        and rect.get_area() < 0.9 * page_area
    ]
    return len(page.get_images()) + len(diagrams)


def _guess_titles(pdf: pymupdf.Document) -> list[Heading]:
    """Titles guessed from their size or weight, for a PDF without bookmarks.

    A short line bigger than the body text, or entirely bold, is a candidate title.
    Levels go from 1 to 3, the biggest titles first.
    """
    lines: list[tuple[int, float, bool, str]] = []  # page, size, bold, text
    for number, page in enumerate(pdf, start=1):
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                spans = [span for span in line["spans"] if span["text"].strip()]
                if spans:
                    lines.append(
                        (
                            number,
                            round(max(span["size"] for span in spans), 1),
                            all(
                                span["flags"] & pymupdf.TEXT_FONT_BOLD for span in spans
                            ),
                            " ".join(span["text"].strip() for span in spans),
                        )
                    )
    characters: Counter[float] = Counter()
    for _, size, _, text in lines:
        characters[size] += len(text)
    if not characters:
        return []
    body = characters.most_common(1)[0][0]  # the size of most of the text
    candidates = [
        (number, size, text)
        for number, size, bold, text in lines
        if 3 <= len(text) <= 80
        and not text.replace(" ", "").isdigit()
        and (size >= body * TITLE_SIZE_RATIO or (bold and size >= body))
    ]
    sizes = sorted({size for _, size, _ in candidates}, reverse=True)
    return [
        Heading(min(sizes.index(size) + 1, 3), text, number)
        for number, size, text in candidates
    ]
