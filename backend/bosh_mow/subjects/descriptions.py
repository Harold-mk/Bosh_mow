"""T11: Claude describes in text the pages whose content is mostly in images (R38).

A PDF page of fewer than 150 characters with an image or a diagram is turned into an
image and described once, in the background. Descriptions are asked for as soon as the
split into chapters is validated: the chapter of each page is then known, and they do
not delay the proposal of chapters. They serve the questions and the assistant; the
reader always shows the page itself.
"""

import json
import sqlite3
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pymupdf

from bosh_mow.ai.gateway import Gateway
from bosh_mow.ai.schemas import T11Answer
from bosh_mow.ai.tasks import Handler, add_task
from bosh_mow.subjects.importer import copy_path, needs_description
from bosh_mow.subjects.repository import PageContent

PROMPT = "t11_v1"
TASK = "t11"  # the kind of the background task that runs describe_page()
MAX_WORDS = 150  # contract T11
IMAGE_SIZE = 1200  # pixels on the longest side: about 1,000 to 1,500 tokens


@dataclass(frozen=True)
class DescriptionCount:
    """For one PDF file: how many of its pages need a description, how many have one."""

    resource_id: int
    to_describe: int
    described: int


def request_descriptions(connection: sqlite3.Connection, subject_id: int) -> int:
    """Ask in the background for the description of every page of the subject that
    needs one and has none yet; return how many pages were asked for."""
    pages = [
        (resource_id, number)
        for resource_id, number, described in _text_poor_pages(connection, subject_id)
        if not described
    ]
    for resource_id, number in pages:
        add_task(
            connection, TASK, {"resource_id": resource_id, "page": number}, subject_id
        )
    return len(pages)


def description_counts(
    connection: sqlite3.Connection, subject_id: int
) -> list[DescriptionCount]:
    """For each PDF file of the subject with pages to describe, how far it is."""
    to_describe: Counter[int] = Counter()
    described: Counter[int] = Counter()
    for resource_id, _, done in _text_poor_pages(connection, subject_id):
        to_describe[resource_id] += 1
        described[resource_id] += done
    return [
        DescriptionCount(resource_id, to_describe[resource_id], described[resource_id])
        for resource_id in sorted(to_describe)
    ]


def describe_page(
    connection: sqlite3.Connection,
    gateway: Gateway,
    resources_dir: Path,
    resource_id: int,
    number: int,
) -> T11Answer:
    """Ask Claude to describe one page from its image, then keep the description.

    Raises EngineUnavailable if Claude cannot answer now, and InvalidAnswer if its
    answer breaks the rules of T11 twice in a row.
    """
    row = connection.execute(
        "SELECT r.file_name, p.text FROM page p JOIN resource r ON r.id = p.resource_id"
        " WHERE p.resource_id = ? AND p.number = ?",
        (resource_id, number),
    ).fetchone()
    if row is None:
        raise ValueError(f"Page {number} of file {resource_id} does not exist.")
    file_name, text = row
    chapter = connection.execute(
        "SELECT c.title FROM chapter_source s JOIN chapter c ON c.id = s.chapter_id"
        " WHERE s.resource_id = ? AND ? BETWEEN s.first_page AND s.last_page",
        (resource_id, number),
    ).fetchone()
    data = {
        "page": number,
        "document": file_name,
        "chapter": chapter[0] if chapter else None,
        "text": " ".join(text.split()),
    }
    image = render_page(copy_path(resources_dir, resource_id, "pdf"), number)
    answer = gateway.ask(
        PROMPT,
        data,
        T11Answer,
        check=lambda answer: check_description(answer, number),
        images=[image],
    )
    with connection:
        connection.execute(
            "INSERT OR REPLACE INTO page_description"
            " (resource_id, number, description, elements, to_check)"
            " VALUES (?, ?, ?, ?, ?)",
            (
                resource_id,
                number,
                answer.description.strip(),
                json.dumps(answer.elements, ensure_ascii=False),
                answer.to_check,
            ),
        )
    return answer


def check_description(answer: T11Answer, page: int) -> list[str]:
    """What breaks the rules of T11, in sentences for Claude; [] if nothing does."""
    problems: list[str] = []
    words = len(answer.description.split())
    if words == 0:
        problems.append("The description is empty.")
    elif words > MAX_WORDS:
        problems.append(f"The description has {words} words: {MAX_WORDS} at most.")
    if answer.page != page:
        problems.append(f"The page is {page}, not {answer.page}.")
    return problems


def render_page(pdf_path: Path, number: int) -> bytes:
    """A page of a PDF file as a PNG image, IMAGE_SIZE pixels on its longest side."""
    with pymupdf.open(pdf_path) as pdf:
        page = pdf[number - 1]
        zoom = IMAGE_SIZE / max(page.rect.width, page.rect.height)
        return page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom)).tobytes("png")


def description_handler(gateway: Gateway, resources_dir: Path) -> Handler:
    """The background task TASK: describe_page() for the page given in its data."""

    def run(connection: sqlite3.Connection, data: dict[str, Any]) -> dict[str, Any]:
        page = describe_page(
            connection, gateway, resources_dir, data["resource_id"], data["page"]
        )
        return page.model_dump()

    return run


def _text_poor_pages(
    connection: sqlite3.Connection, subject_id: int
) -> list[tuple[int, int, bool]]:
    """The pages of the subject's PDF files that need a description (R38), as
    (file id, page number, already described)."""
    rows = connection.execute(
        """
        SELECT p.resource_id, p.number, p.text, p.image_count, d.number IS NOT NULL
        FROM page p
        JOIN resource r ON r.id = p.resource_id
        LEFT JOIN page_description d
               ON d.resource_id = p.resource_id AND d.number = p.number
        WHERE r.subject_id = ? AND r.kind = 'pdf'
        ORDER BY p.resource_id, p.number
        """,
        (subject_id,),
    ).fetchall()
    return [
        (resource_id, number, bool(described))
        for resource_id, number, text, image_count, described in rows
        if needs_description(PageContent(text, image_count))
    ]
