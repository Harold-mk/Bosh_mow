"""Tests of the API of lot 2: chapters and notions, studying, the reader's files."""

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pymupdf
import pytest
from fake_ai import FakeEngine
from fastapi.testclient import TestClient
from test_preparation import make_chapters, preparation
from test_sessions import make_due, make_subject

from bosh_mow.ai.gateway import Gateway
from bosh_mow.ai.tasks import run_next_task
from bosh_mow.api import create_app
from bosh_mow.content.preparation import TASK, preparation_handler
from bosh_mow.paths import DataFolder


@pytest.fixture
def client(db: sqlite3.Connection, tmp_path: Path) -> TestClient:
    """The API on the data folder of the temporary database `db`."""
    return TestClient(create_app(DataFolder(tmp_path)))


def test_r3_a_chapter_is_prepared_then_its_notions_are_validated(
    client: TestClient, db: sqlite3.Connection, tmp_path: Path
) -> None:
    make_chapters(db)
    chapter = "/api/subjects/1/chapters/1"
    assert client.get(f"{chapter}/preparation").json() is None

    asked = client.post(f"{chapter}/preparation")
    assert (asked.status_code, asked.json()["status"]) == (202, "pending")
    gateway = Gateway(FakeEngine([preparation()]), tmp_path / "log")
    run_next_task(db, {TASK: preparation_handler(gateway)}, datetime.now(UTC))
    proposed = client.get(f"{chapter}/preparation").json()
    assert proposed["status"] == "done"
    assert [notion["title"] for notion in proposed["notions"]] == [
        "Variance d'un échantillon"
    ]

    saved = client.post(f"{chapter}/notions", json={"titles": ["Variance"]}).json()

    (notion,) = saved["notions"]
    assert (notion["title"], len(notion["questions"])) == ("Variance", 7)
    assert client.get(chapter).json() == saved
    again = client.post(f"{chapter}/preparation")
    assert again.status_code == 409  # already validated


def test_a_wrong_question_can_be_reported(
    client: TestClient, db: sqlite3.Connection
) -> None:
    _, reviews = make_subject(db)

    assert client.post(f"/api/questions/{reviews[0]}/report").status_code == 204

    (notion,) = client.get("/api/subjects/1/chapters/1").json()["notions"]
    reported = [q["id"] for q in notion["questions"] if q["reported"]]
    assert reported == [reviews[0]]


def test_the_daily_queue_through_the_api(
    client: TestClient, db: sqlite3.Connection
) -> None:
    _, reviews = make_subject(db)
    make_due(db, reviews)
    assert client.get("/api/today").json()["due"] == 3

    session = client.post("/api/sessions").json()
    assert session["planned"] == 3
    asked = 0
    while (
        question := client.get(f"/api/sessions/{session['id']}/next").json()
    ) is not None:
        assert "correct" not in question["options"][0]  # no correction sent
        given = {
            "question_id": question["id"],
            "chosen_option": 1,
            "confidence": "sure",
            "seconds": 9,
        }
        correction = client.post(
            f"/api/sessions/{session['id']}/answers", json=given
        ).json()
        assert (correction["correct"], correction["correct_option"]) == (True, 1)
        asked += 1

    assert asked == 3
    ended = client.post(f"/api/sessions/{session['id']}/end", json={"completed": True})
    assert ended.json() == {"minimum_done": True}
    assert client.get("/api/today").json()["successful_days"] == 1


def test_thoughts_and_wanderings_through_the_api(client: TestClient) -> None:
    session = client.post("/api/sessions").json()["id"]
    thought = client.post(
        f"/api/sessions/{session}/thoughts", json={"text": " Écrire à Léa "}
    ).json()
    assert thought["text"] == "Écrire à Léa"
    assert (
        client.post(
            f"/api/sessions/{session}/wanderings", json={"question_id": None}
        ).status_code
        == 204
    )

    refused = client.post(f"/api/sessions/{session}/end", json={"completed": True})
    assert refused.status_code == 400
    assert "pensées à trier" in refused.json()["detail"]
    client.post(
        f"/api/thoughts/{thought['id']}/decision",
        json={"planned_for": "2026-11-25T18:30"},
    )
    assert client.get(f"/api/sessions/{session}/thoughts").json() == []
    assert (
        client.post(
            f"/api/sessions/{session}/end", json={"completed": False}
        ).status_code
        == 200
    )


def test_studying_a_notion_through_the_api(
    client: TestClient, db: sqlite3.Connection
) -> None:
    notion_id, reviews = make_subject(db)

    proposed = client.get("/api/notions/next").json()
    started = client.post(f"/api/notions/{notion_id}/session").json()

    assert proposed["id"] == notion_id
    assert len(started["pretests"]) == 2
    assert [q["id"] for q in started["tests"]] == reviews


def test_the_reader_gets_a_file_untouched_and_its_outline(client: TestClient) -> None:
    pdf = pymupdf.open()
    for number in range(1, 4):
        pdf.new_page().insert_text((72, 72), f"Page {number}", fontsize=12)
    pdf.set_toc([[1, "Introduction", 1], [1, "Variance", 2]])
    content = pdf.tobytes()
    subject = client.post(
        "/api/subjects", json={"name": "Statistiques", "exam_date": "2027-01-15"}
    ).json()
    file_id = client.post(
        f"/api/subjects/{subject['id']}/files", files={"file": ("stats.pdf", content)}
    ).json()["id"]

    downloaded = client.get(f"/api/resources/{file_id}/file")

    assert downloaded.headers["content-type"] == "application/pdf"
    assert downloaded.content == content
    assert client.get(f"/api/resources/{file_id}/outline").json() == [
        {"level": 1, "title": "Introduction", "page": 1},
        {"level": 1, "title": "Variance", "page": 2},
    ]
    assert client.get("/api/resources/999/file").status_code == 404
