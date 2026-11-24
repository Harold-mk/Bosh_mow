"""Tests of the local HTTP API, on a temporary data folder and with the fake AI."""

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pymupdf
import pytest
from fake_ai import FakeEngine
from fastapi.testclient import TestClient
from httpx2 import Response

from bosh_mow import __version__
from bosh_mow.ai.gateway import EngineUnavailable, Gateway
from bosh_mow.ai.tasks import run_next_task
from bosh_mow.api import create_app
from bosh_mow.paths import DataFolder
from bosh_mow.subjects.proposal import TASK, proposal_handler

NOW = datetime(2026, 11, 23, 18, 0, tzinfo=UTC)
NOTES = "# Variance\nMoyenne des carrés des écarts.\n# Écart-type\nSa racine.\n"


@pytest.fixture
def client(db: sqlite3.Connection, tmp_path: Path) -> TestClient:
    """The API on the data folder of the temporary database `db`."""
    return TestClient(create_app(DataFolder(tmp_path)))


def claude_answers(
    db: sqlite3.Connection, tmp_path: Path, *answers: dict[str, Any] | Exception
) -> None:
    """Run the next background task, with the fake AI giving `answers`."""
    gateway = Gateway(FakeEngine(list(answers)), tmp_path / "ai_calls.jsonl")
    assert run_next_task(db, {TASK: proposal_handler(gateway)}, NOW)


def t1_answer(file_id: int) -> dict[str, Any]:
    """Claude's answer for a subject made of the NOTES file only."""
    return {
        "objectives": ["Être capable de calculer une variance"],
        "chapters": [
            {
                "title": "Variance et écart-type",
                "role": "core",
                "sources": [{"file": file_id, "first_page": 1, "last_page": 2}],
                "objectives": [1],
            }
        ],
        "glossary": ["p-value"],
    }


def new_draft(client: TestClient) -> int:
    response = client.post(
        "/api/subjects", json={"name": "Statistiques", "exam_date": "2027-01-15"}
    )
    assert response.status_code == 201
    return response.json()["id"]


def upload(
    client: TestClient, subject_id: int, name: str = "notes.md", text: str = NOTES
) -> Response:
    return client.post(
        f"/api/subjects/{subject_id}/files", files={"file": (name, text.encode())}
    )


def test_health_returns_status_and_version(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}


def test_settings_are_null_until_the_first_launch_is_completed(
    client: TestClient,
) -> None:
    settings = {
        "weekday_minutes": 90,
        "weekend_minutes": 180,
        "plan_if": "je rentre et que j'ai dîné",
        "plan_then": "je lance la file du jour à 19 h",
        "sidebar_collapsed": False,
    }

    assert client.get("/api/settings").json() is None
    assert client.put("/api/settings", json=settings).json() == settings
    assert client.get("/api/settings").json() == settings


def test_s1_a_subject_is_created_from_its_files_and_the_proposal_of_claude(
    client: TestClient, db: sqlite3.Connection, tmp_path: Path
) -> None:
    subject_id = new_draft(client)
    file = upload(client, subject_id).json()
    assert file == {
        "id": 1,
        "file_name": "notes.md",
        "kind": "markdown",
        "page_count": 2,
    }

    asked = client.post(f"/api/subjects/{subject_id}/proposal")
    assert asked.status_code == 202
    assert asked.json() == {"status": "pending", "error": None, "proposal": None}
    claude_answers(db, tmp_path, t1_answer(file["id"]))
    proposal = client.get(f"/api/subjects/{subject_id}/proposal").json()
    assert proposal["status"] == "done"
    assert proposal["proposal"]["chapters"][0]["sources"] == [
        {"resource_id": 1, "first_page": 1, "last_page": 2}
    ]
    assert client.get("/api/subjects").json() == []  # still a draft

    validated = client.post(
        f"/api/subjects/{subject_id}/validate", json=proposal["proposal"]
    )

    assert validated.status_code == 200
    subject = validated.json()
    assert subject["status"] == "active"
    assert subject["objectives"] == ["Être capable de calculer une variance"]
    assert subject["chapters"][0]["title"] == "Variance et écart-type"
    assert subject["glossary"] == ["p-value"]
    assert client.get("/api/subjects").json() == [
        {
            "id": subject_id,
            "name": "Statistiques",
            "exam_date": "2027-01-15",
            "chapter_count": 1,
            "resource_count": 1,
        }
    ]


def test_a_draft_left_being_created_is_taken_up_again(client: TestClient) -> None:
    assert client.get("/api/draft").json() is None
    subject_id = new_draft(client)
    upload(client, subject_id)

    draft = client.get("/api/draft").json()

    assert (draft["id"], draft["name"]) == (subject_id, "Statistiques")
    assert [file["file_name"] for file in draft["resources"]] == ["notes.md"]


def test_the_name_and_date_of_a_draft_can_change(client: TestClient) -> None:
    subject_id = new_draft(client)
    changed = {"name": "Statistique descriptive", "exam_date": "2027-02-01"}

    response = client.put(f"/api/subjects/{subject_id}", json=changed)

    assert response.status_code == 200
    subject = response.json()
    assert (subject["name"], subject["exam_date"]) == (
        "Statistique descriptive",
        "2027-02-01",
    )
    handwritten = {"objectives": ["Être capable de A"], "chapters": [], "glossary": []}
    client.post(f"/api/subjects/{subject_id}/validate", json=handwritten)
    assert client.put(f"/api/subjects/{subject_id}", json=changed).status_code == 409
    assert client.get("/api/draft").json() is None


def test_a_subject_needs_a_name(client: TestClient) -> None:
    response = client.post(
        "/api/subjects", json={"name": "  ", "exam_date": "2027-01-15"}
    )

    assert response.status_code == 400


def test_an_unknown_subject_is_not_found(client: TestClient) -> None:
    assert client.get("/api/subjects/999").status_code == 404
    assert upload(client, 999).status_code == 404


def test_an_unsupported_file_is_refused_with_its_reason(client: TestClient) -> None:
    subject_id = new_draft(client)

    response = upload(client, subject_id, name="notes.docx")

    assert response.status_code == 400
    assert response.json()["detail"].startswith("Seuls les PDF")


def test_a_file_can_be_removed_from_a_draft(client: TestClient, tmp_path: Path) -> None:
    subject_id = new_draft(client)
    file_id = upload(client, subject_id).json()["id"]
    assert (tmp_path / "resources" / f"{file_id}.md").exists()

    response = client.delete(f"/api/subjects/{subject_id}/files/{file_id}")

    assert response.status_code == 204
    assert client.get(f"/api/subjects/{subject_id}").json()["resources"] == []
    assert not (tmp_path / "resources" / f"{file_id}.md").exists()


def test_a_proposal_needs_a_file(client: TestClient) -> None:
    subject_id = new_draft(client)

    assert client.post(f"/api/subjects/{subject_id}/proposal").status_code == 400
    assert client.get(f"/api/subjects/{subject_id}/proposal").json() is None


def test_a_proposal_waits_while_claude_is_unavailable(
    client: TestClient, db: sqlite3.Connection, tmp_path: Path
) -> None:
    subject_id = new_draft(client)
    file_id = upload(client, subject_id).json()["id"]
    client.post(f"/api/subjects/{subject_id}/proposal")

    claude_answers(db, tmp_path, EngineUnavailable("Claude Code n'est pas installé."))

    assert client.get(f"/api/subjects/{subject_id}/proposal").json() == {
        "status": "pending",
        "error": "Claude Code n'est pas installé.",
        "proposal": None,
    }
    # Asked again, for example once Claude Code is installed: tried at once.
    client.post(f"/api/subjects/{subject_id}/proposal")
    claude_answers(db, tmp_path, t1_answer(file_id))
    proposal = client.get(f"/api/subjects/{subject_id}/proposal").json()
    assert (proposal["status"], proposal["error"]) == ("done", None)
    assert db.execute("SELECT COUNT(*) FROM ai_task").fetchone() == (1,)


def test_a_failed_proposal_can_be_asked_again(
    client: TestClient, db: sqlite3.Connection, tmp_path: Path
) -> None:
    subject_id = new_draft(client)
    file_id = upload(client, subject_id).json()["id"]
    client.post(f"/api/subjects/{subject_id}/proposal")
    wrong = t1_answer(file_id)
    wrong["objectives"] = ["Savoir calculer une variance"]

    claude_answers(db, tmp_path, wrong, wrong)

    failed = client.get(f"/api/subjects/{subject_id}/proposal").json()
    assert failed["status"] == "failed"
    assert "Être capable de" in failed["error"]
    again = client.post(f"/api/subjects/{subject_id}/proposal").json()
    assert again == {"status": "pending", "error": None, "proposal": None}


def test_r2_without_claude_the_objectives_are_written_by_hand_in_the_meantime(
    client: TestClient, db: sqlite3.Connection, tmp_path: Path
) -> None:
    subject_id = new_draft(client)
    file_id = upload(client, subject_id).json()["id"]
    client.post(f"/api/subjects/{subject_id}/proposal")
    handwritten = {
        "objectives": ["Être capable de lire mes notes"],
        "chapters": [],
        "glossary": [],
    }

    created = client.post(f"/api/subjects/{subject_id}/validate", json=handwritten)

    assert created.json()["status"] == "active"
    assert client.get("/api/subjects").json()[0]["chapter_count"] == 0
    # Claude comes back: its proposal is validated later, objectives included.
    claude_answers(db, tmp_path, t1_answer(file_id))
    proposal = client.get(f"/api/subjects/{subject_id}/proposal").json()["proposal"]
    subject = client.post(f"/api/subjects/{subject_id}/validate", json=proposal).json()
    assert subject["objectives"] == ["Être capable de calculer une variance"]
    assert len(subject["chapters"]) == 1
    assert upload(client, subject_id).status_code == 409  # its files are fixed


def test_a_validation_that_breaks_a_rule_is_refused(client: TestClient) -> None:
    subject_id = new_draft(client)
    six = {
        "objectives": [f"Être capable de faire {n}" for n in range(6)],
        "chapters": [],
        "glossary": [],
    }

    response = client.post(f"/api/subjects/{subject_id}/validate", json=six)

    assert response.status_code == 400
    assert "1 to 5 objectives" in response.json()["detail"]


def test_validated_chapters_lead_to_the_description_of_pages_in_images(
    client: TestClient, db: sqlite3.Connection
) -> None:
    pdf = pymupdf.open()
    pdf.new_page().insert_text((72, 72), "Notes de cours " * 20, fontsize=9)
    diagram = pdf.new_page()
    diagram.insert_text((72, 72), "Courbe d'erreur", fontsize=20)
    diagram.draw_rect(pymupdf.Rect(100, 120, 400, 400), color=(0, 0, 0))
    subject_id = new_draft(client)
    upload = client.post(
        f"/api/subjects/{subject_id}/files",
        files={"file": ("cours.pdf", pdf.tobytes())},
    )
    file_id = upload.json()["id"]
    split = {
        "objectives": ["Être capable de lire une courbe d'erreur"],
        "chapters": [
            {
                "title": "Erreur",
                "role": "core",
                "sources": [{"resource_id": file_id, "first_page": 1, "last_page": 2}],
                "objectives": [1],
            }
        ],
        "glossary": [],
    }

    client.post(f"/api/subjects/{subject_id}/validate", json=split)

    assert client.get(f"/api/subjects/{subject_id}/descriptions").json() == [
        {"resource_id": file_id, "to_describe": 1, "described": 0}
    ]
    queued = db.execute("SELECT input FROM ai_task WHERE kind = 't11'").fetchall()
    assert queued == [(f'{{"resource_id": {file_id}, "page": 2}}',)]
