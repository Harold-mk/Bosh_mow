"""Local HTTP API used by the interface, on 127.0.0.1 only.

Each request gets its own database connection. An error comes back as
{"detail": message}: a ValueError raised by a module means a request that breaks a
rule (400). The messages meant for the student are in French.
"""

import sqlite3
from collections.abc import Iterator
from contextlib import closing
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse

from bosh_mow import __version__
from bosh_mow.db.connection import connect
from bosh_mow.paths import DataFolder
from bosh_mow.settings import Settings, get_settings, save_settings
from bosh_mow.subjects.importer import import_file, remove_file
from bosh_mow.subjects.proposal import (
    Proposal,
    ProposalState,
    proposal_state,
    request_proposal,
)
from bosh_mow.subjects.repository import (
    Resource,
    Subject,
    SubjectSummary,
    activate_subject,
    create_draft_subject,
    get_draft,
    get_subject,
    list_subjects,
    update_draft,
)

router = APIRouter(prefix="/api")


def create_app(folder: DataFolder) -> FastAPI:
    """The API, working on the data in `folder`."""
    app = FastAPI(title="Bosh mow", version=__version__)
    app.state.folder = folder
    app.include_router(router)
    app.add_exception_handler(ValueError, _broken_rule)
    return app


def _broken_rule(request: Request, error: Exception) -> JSONResponse:
    return JSONResponse({"detail": str(error)}, status_code=400)


def _folder(request: Request) -> DataFolder:
    return request.app.state.folder


Folder = Annotated[DataFolder, Depends(_folder)]


def _database(folder: Folder) -> Iterator[sqlite3.Connection]:
    with closing(connect(folder.database)) as connection:
        yield connection


Database = Annotated[sqlite3.Connection, Depends(_database)]


@router.get("/health")
def health() -> dict[str, str]:
    """Tell the interface that the backend is running."""
    return {"status": "ok", "version": __version__}


# Settings, chosen at first launch (Bienvenue)


@router.get("/settings")
def read_settings(db: Database) -> Settings | None:
    """The settings, or null as long as the first launch is not completed."""
    return get_settings(db)


@router.put("/settings")
def write_settings(settings: Settings, db: Database) -> Settings:
    save_settings(db, settings)
    return settings


# Subjects (Mes matières, Matière)


@router.get("/subjects")
def subjects(db: Database) -> list[SubjectSummary]:
    """The active subjects, the closest exam first."""
    return list_subjects(db)


@router.get("/subjects/{subject_id}")
def subject(subject_id: int, db: Database) -> Subject:
    return _subject(db, subject_id)


# Creation of a subject (Nouvelle matière): a draft, its files, the proposal of
# Claude, then the validation by the student.


@dataclass(frozen=True)
class NewSubject:
    name: str
    exam_date: date


@router.post("/subjects", status_code=201)
def new_subject(new: NewSubject, db: Database) -> Subject:
    """Start a subject as a draft, which stays hidden until it is validated."""
    return _subject(db, create_draft_subject(db, new.name, new.exam_date))


@router.get("/draft")
def draft(db: Database) -> Subject | None:
    """The subject left being created, to take it up again; null if there is none."""
    return get_draft(db)


@router.put("/subjects/{subject_id}")
def change_draft(subject_id: int, new: NewSubject, db: Database) -> Subject:
    """Change the name or the exam date of a subject still being created."""
    _draft(db, subject_id)
    update_draft(db, subject_id, new.name, new.exam_date)
    return _subject(db, subject_id)


@router.post("/subjects/{subject_id}/files", status_code=201)
def add_file(
    subject_id: int, file: UploadFile, db: Database, folder: Folder
) -> Resource:
    """Import a PDF or Markdown file into a draft; 400 with the reason if it cannot."""
    _draft(db, subject_id)
    name = Path(file.filename or "").name  # never a path, only a name
    return import_file(db, folder.resources, subject_id, name, file.file.read())


@router.delete("/subjects/{subject_id}/files/{file_id}", status_code=204)
def delete_file(subject_id: int, file_id: int, db: Database, folder: Folder) -> None:
    for resource in _draft(db, subject_id).resources:
        if resource.id == file_id:
            remove_file(db, folder.resources, resource)
            return
    raise HTTPException(404, "Ce fichier n'existe pas.")


@router.post("/subjects/{subject_id}/proposal", status_code=202)
def ask_proposal(subject_id: int, db: Database) -> ProposalState:
    """Ask Claude for objectives and chapters (T1), in the background."""
    subject = _subject(db, subject_id)
    if not subject.resources:
        raise HTTPException(400, "Importe au moins un fichier.")
    if subject.chapters:
        raise HTTPException(409, "Cette matière a déjà ses chapitres.")
    request_proposal(db, subject_id)
    state = proposal_state(db, subject_id)
    assert state is not None  # a proposal was just asked for
    return state


@router.get("/subjects/{subject_id}/proposal")
def proposal(subject_id: int, db: Database) -> ProposalState | None:
    """Where the proposal stands, or null if none was asked for. The interface asks
    again until it is done or failed."""
    _subject(db, subject_id)
    return proposal_state(db, subject_id)


@router.post("/subjects/{subject_id}/validate")
def validate(subject_id: int, proposal: Proposal, db: Database) -> Subject:
    """Save the objectives and chapters as corrected by the student (R2, R3).

    Without Claude, the chapters can be empty: the objectives are then written by
    hand, and the proposal is validated later in the same way.
    """
    _subject(db, subject_id)
    activate_subject(
        db, subject_id, proposal.objectives, proposal.chapters, proposal.glossary
    )
    return _subject(db, subject_id)


def _subject(db: sqlite3.Connection, subject_id: int) -> Subject:
    subject = get_subject(db, subject_id)
    if subject is None:
        raise HTTPException(404, "Cette matière n'existe pas.")
    return subject


def _draft(db: sqlite3.Connection, subject_id: int) -> Subject:
    """A subject being created: its files can still change."""
    subject = _subject(db, subject_id)
    if subject.status != "draft":
        raise HTTPException(409, "Cette matière est déjà créée.")
    return subject
