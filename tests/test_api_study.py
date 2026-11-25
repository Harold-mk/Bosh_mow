"""Tests of the API of lot 2: chapters and notions, studying, the reader's files."""

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pymupdf
import pytest
from fake_ai import FakeEngine
from fastapi.testclient import TestClient
from test_preparation import make_chapters, notions, questions
from test_sessions import make_due, make_subject, question_of

from bosh_mow.ai.gateway import Gateway
from bosh_mow.ai.tasks import run_next_task
from bosh_mow.api import create_app
from bosh_mow.content.preparation import (
    NOTIONS_TASK,
    QUESTIONS_TASK,
    notions_handler,
    questions_handler,
)
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
    gateway = Gateway(FakeEngine([notions()]), tmp_path / "log")
    run_next_task(db, {NOTIONS_TASK: notions_handler(gateway)}, datetime.now(UTC))
    proposed = client.get(f"{chapter}/preparation").json()
    assert proposed["status"] == "done"
    assert [notion["title"] for notion in proposed["notions"]] == [
        "Variance d'un échantillon"
    ]

    saved = client.post(f"{chapter}/notions", json={"titles": ["Variance"]}).json()

    (notion,) = saved["notions"]
    assert (notion["title"], notion["questions"]) == ("Variance", [])
    assert notion["writing"] == {"status": "pending", "error": None}
    gateway = Gateway(FakeEngine([questions()]), tmp_path / "log")
    run_next_task(db, {QUESTIONS_TASK: questions_handler(gateway)}, datetime.now(UTC))
    (notion,) = client.get(chapter).json()["notions"]
    assert (len(notion["questions"]), notion["writing"]["status"]) == (7, "done")
    again = client.post(f"{chapter}/preparation")
    assert again.status_code == 409  # already validated


def test_the_questions_of_a_notion_can_be_asked_again(
    client: TestClient, db: sqlite3.Connection
) -> None:
    notion_id, _ = make_subject(db)
    assert client.post(f"/api/notions/{notion_id}/questions").status_code == 409

    db.execute("DELETE FROM question WHERE notion_id = ?", (notion_id,))  # failed
    db.commit()
    asked = client.post(f"/api/notions/{notion_id}/questions")

    assert (asked.status_code, asked.json()) == (
        202,
        {"status": "pending", "error": None},
    )


def test_the_chapters_of_a_subject_say_where_their_notions_stand(
    client: TestClient, db: sqlite3.Connection
) -> None:
    make_subject(db)  # chapter 1 has one validated notion
    client.post("/api/subjects/1/chapters/2/preparation")

    chapters = client.get("/api/subjects/1/chapters").json()

    assert [
        (c["number"], c["title"], c["notions"], c["studied"], c["preparation"])
        for c in chapters
    ] == [(1, "Dispersion", 1, 0, None), (2, "Quartiles", 0, 0, "pending")]


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


def test_a_value_is_answered_with_its_text_through_the_api(
    client: TestClient, db: sqlite3.Connection
) -> None:
    notion_id, _ = make_subject(db)
    value = question_of(db, notion_id, "value")
    make_due(db, [value])
    session = client.post("/api/sessions").json()["id"]

    question = client.get(f"/api/sessions/{session}/next").json()
    given = {
        "question_id": value,
        "chosen_option": None,
        "answer_text": "4",
        "confidence": "sure",
        "seconds": 7,
    }
    correction = client.post(f"/api/sessions/{session}/answers", json=given).json()

    assert (question["format"], question["options"], question["tolerance"]) == (
        "value",
        [],
        0.01,
    )
    assert (correction["correct"], correction["expected"]) == (True, "4")


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
    assert started["warmup"] is None  # nothing succeeded yet (R15)
    assert len(started["pretests"]) == 2
    assert [q["id"] for q in started["tests"]] == [
        *reviews,
        question_of(db, notion_id, "value"),
    ]


def test_a_notion_and_its_pages_for_the_reading(
    client: TestClient, db: sqlite3.Connection
) -> None:
    notion_id, _ = make_subject(db)  # a notion of pages 1 to 6

    found = client.get(f"/api/notions/{notion_id}").json()
    pages = client.get(f"/api/notions/{notion_id}/pages").json()

    assert (found["title"], found["subject"]) == ("Variance", "Statistiques")
    assert [page["number"] for page in pages] == [1, 2, 3, 4, 5, 6]
    assert pages[0] == {"number": 1, "text": "Page 1", "description": None}
    assert client.get("/api/notions/99").status_code == 404


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
    assert client.get(f"/api/resources/{file_id}").json() == {
        "id": file_id,
        "subject_id": subject["id"],
        "file_name": "stats.pdf",
        "kind": "pdf",
        "page_count": 3,
    }
    pages = client.get(f"/api/resources/{file_id}/pages").json()
    assert [(page["number"], page["text"].strip()) for page in pages] == [
        (1, "Page 1"),
        (2, "Page 2"),
        (3, "Page 3"),
    ]
