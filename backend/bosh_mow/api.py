"""Local HTTP API used by the interface, on 127.0.0.1 only.

Each request gets its own database connection. An error comes back as
{"detail": message}: a ValueError raised by a module means a request that breaks a
rule (400). The messages meant for the student are in French.
"""

import sqlite3
from collections.abc import Iterator
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from bosh_mow import __version__
from bosh_mow.content.preparation import (
    PreparationState,
    QuestionsState,
    preparation_state,
    questions_state,
    request_preparation,
    request_questions,
    validate_notions,
)
from bosh_mow.content.repository import get_notions, get_questions, report_question
from bosh_mow.db.connection import connect
from bosh_mow.paths import DataFolder
from bosh_mow.settings import Settings, get_settings, save_settings
from bosh_mow.study.claims import ClaimState, claim_state, make_claim
from bosh_mow.study.gradings import (
    Grader,
    GradingState,
    give_confidence,
    grade_in_background,
    grading_state,
    start_grading,
)
from bosh_mow.study.repository import (
    Confidence,
    Thought,
    add_thought,
    add_wandering,
    decide_thought,
    undecided_thoughts,
)
from bosh_mow.study.sessions import (
    Correction,
    NotionSession,
    NotionToStudy,
    QuestionToAsk,
    Today,
    answer,
    find_notion,
    finish,
    next_notion,
    next_question,
    start_notion,
    start_queue,
    today,
)
from bosh_mow.subjects.descriptions import (
    DescriptionCount,
    description_counts,
    request_descriptions,
)
from bosh_mow.subjects.importer import copy_path, import_file, remove_file
from bosh_mow.subjects.proposal import (
    Proposal,
    ProposalState,
    proposal_state,
    request_proposal,
)
from bosh_mow.subjects.repository import (
    Heading,
    PageText,
    Resource,
    Subject,
    SubjectSummary,
    activate_subject,
    chapter_ids,
    create_draft_subject,
    get_document,
    get_draft,
    get_pages,
    get_subject,
    list_subjects,
    update_draft,
)

router = APIRouter(prefix="/api")


def create_app(folder: DataFolder, grade: Grader | None = None) -> FastAPI:
    """The API, working on the data in `folder`; `grade` grades the open answers at
    once (T6), and without it they cannot be sent."""
    app = FastAPI(title="Bosh mow", version=__version__)
    app.state.folder = folder
    app.state.grade = grade
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
    hand, and the proposal is validated later in the same way. Once the chapters are
    known, the pages mostly in images are described in the background (T11), then
    chapter 1 is prepared: its notions and questions (T1 pass 2, T2).
    """
    _subject(db, subject_id)
    activate_subject(
        db, subject_id, proposal.objectives, proposal.chapters, proposal.glossary
    )
    if proposal.chapters:
        request_descriptions(db, subject_id)
        # After the descriptions: the questions of a chapter need them (R38).
        request_preparation(db, chapter_ids(db, subject_id)[0])
    return _subject(db, subject_id)


@router.get("/subjects/{subject_id}/descriptions")
def descriptions(subject_id: int, db: Database) -> list[DescriptionCount]:
    """For each PDF file with pages mostly in images, how many are described (T11)."""
    _subject(db, subject_id)
    return description_counts(db, subject_id)


# Chapters: their notions and questions, prepared by Claude, then validated (R3)


@dataclass(frozen=True)
class QuestionSummary:
    id: int
    role: str
    format: str
    statement: str
    reported: bool


@dataclass(frozen=True)
class NotionWithQuestions:
    id: int
    number: int
    title: str
    summary: str
    resource_id: int
    first_page: int
    last_page: int
    studied: bool
    questions: list[QuestionSummary]  # [] while Claude writes them
    writing: QuestionsState | None  # where their writing stands; null if never asked


@dataclass(frozen=True)
class ChapterView:
    id: int
    number: int
    title: str
    role: str
    notions: list[NotionWithQuestions]  # [] until they are validated


@dataclass(frozen=True)
class ChapterSummary:
    """A chapter in the list of its subject, with where its notions stand."""

    number: int
    title: str
    role: str
    notions: int  # validated
    studied: int  # R13
    preparation: str | None  # the proposal of its notions, until they are validated


@dataclass(frozen=True)
class NotionTitles:
    titles: list[str]  # one per notion proposed, in order


@router.get("/subjects/{subject_id}/chapters")
def chapters(subject_id: int, db: Database) -> list[ChapterSummary]:
    _subject(db, subject_id)
    summaries = []
    for chapter_id in chapter_ids(db, subject_id):
        number, title, role = db.execute(
            "SELECT number, title, role FROM chapter WHERE id = ?", (chapter_id,)
        ).fetchone()
        notions = get_notions(db, chapter_id)
        state = None if notions else preparation_state(db, chapter_id)
        summaries.append(
            ChapterSummary(
                number,
                title,
                role,
                len(notions),
                sum(notion.studied for notion in notions),
                state.status if state else None,
            )
        )
    return summaries


@router.get("/subjects/{subject_id}/chapters/{number}")
def chapter(subject_id: int, number: int, db: Database) -> ChapterView:
    return _chapter_view(db, _chapter_id(db, subject_id, number))


@router.get("/subjects/{subject_id}/chapters/{number}/preparation")
def preparation(subject_id: int, number: int, db: Database) -> PreparationState | None:
    """Where the preparation of a chapter stands; null if it was never asked for."""
    return preparation_state(db, _chapter_id(db, subject_id, number))


@router.post("/subjects/{subject_id}/chapters/{number}/preparation", status_code=202)
def prepare_chapter(subject_id: int, number: int, db: Database) -> PreparationState:
    """Préparer ce chapitre: ask Claude for its notions (T1 pass 2)."""
    chapter_id = _chapter_id(db, subject_id, number)
    if get_notions(db, chapter_id):
        raise HTTPException(409, "Les notions de ce chapitre sont déjà validées.")
    request_preparation(db, chapter_id)
    state = preparation_state(db, chapter_id)
    assert state is not None  # it was just asked for
    return state


@router.post("/subjects/{subject_id}/chapters/{number}/notions")
def validate_chapter(
    subject_id: int, number: int, notions: NotionTitles, db: Database
) -> ChapterView:
    """Save the notions proposed for a chapter, with the titles the student gave them
    (R3); Claude then writes the questions of each one (T2)."""
    chapter_id = _chapter_id(db, subject_id, number)
    validate_notions(db, chapter_id, notions.titles)
    return _chapter_view(db, chapter_id)


@router.post("/notions/{notion_id}/questions", status_code=202)
def write_questions(notion_id: int, db: Database) -> QuestionsState:
    """Ask Claude again for the questions of a notion, after a failure (T2)."""
    if get_questions(db, notion_id):
        raise HTTPException(409, "Cette notion a déjà ses questions.")
    request_questions(db, notion_id)
    state = questions_state(db, notion_id)
    assert state is not None  # it was just asked for
    return state


@router.post("/questions/{question_id}/report", status_code=204)
def report(question_id: int, db: Database) -> None:
    """Signaler: take a wrong question out of the reviews."""
    report_question(db, question_id)


# Studying: the day, the daily queue and a new notion (R6 to R18, R26, R27)


@dataclass(frozen=True)
class QueueStarted:
    id: int
    planned: int  # questions in the queue at its start


@dataclass(frozen=True)
class AnswerGiven:
    """An MCQ is answered with the number of its option, a value or a short answer with
    its text; neither is "Je ne sais pas"."""

    question_id: int
    chosen_option: int | None
    confidence: Confidence | None
    seconds: int
    answer_text: str | None = None


@dataclass(frozen=True)
class OpenAnswerWritten:
    question_id: int
    answer_text: str


@dataclass(frozen=True)
class GradingStarted:
    id: int


@dataclass(frozen=True)
class ConfidenceGiven:
    confidence: Confidence
    seconds: int


@dataclass(frozen=True)
class ClaimStarted:
    id: int


@dataclass(frozen=True)
class SessionEnd:
    completed: bool  # the queue emptied or its time up; the notion studied to the end


@dataclass(frozen=True)
class DayStatus:
    minimum_done: bool  # the day is successful (R26)


@dataclass(frozen=True)
class ThoughtNoted:
    text: str


@dataclass(frozen=True)
class ThoughtDecision:
    planned_for: str | None  # local date and time "YYYY-MM-DDTHH:MM"; null: dropped


@dataclass(frozen=True)
class Wandering:
    question_id: int | None  # the question shown


@router.get("/today")
def day(db: Database) -> Today:
    """Where the day stands, for the home screen."""
    return today(db, date.today(), datetime.now(UTC))


@router.post("/sessions", status_code=201)
def new_queue(db: Database) -> QueueStarted:
    """Start the daily queue, the minimum session (R12)."""
    session_id = start_queue(db, date.today(), datetime.now(UTC))
    (planned,) = db.execute(
        "SELECT planned FROM study_session WHERE id = ?", (session_id,)
    ).fetchone()
    return QueueStarted(session_id, planned)


@router.get("/sessions/{session_id}/next")
def next_in_queue(session_id: int, db: Database) -> QuestionToAsk | None:
    """The next question of the daily queue; null once it is empty."""
    return next_question(db, session_id, datetime.now(UTC))


@router.post("/sessions/{session_id}/answers")
def give_answer(session_id: int, given: AnswerGiven, db: Database) -> Correction:
    """Grade an answer at once, without AI (T5); set the next date of its question."""
    return answer(
        db,
        session_id,
        given.question_id,
        given.chosen_option,
        given.confidence,
        given.seconds,
        datetime.now(UTC),
        given.answer_text,
    )


@router.post("/sessions/{session_id}/gradings", status_code=202)
def send_open_answer(
    session_id: int,
    written: OpenAnswerWritten,
    db: Database,
    folder: Folder,
    request: Request,
) -> GradingStarted:
    """Send an open answer to Claude at once (T6), while the confidence is chosen."""
    grade: Grader | None = request.app.state.grade
    if grade is None:
        raise HTTPException(503, "La correction par Claude n'est pas disponible.")
    grading_id = start_grading(db, session_id, written.question_id, written.answer_text)
    grade_in_background(folder.database, grading_id, grade)
    return GradingStarted(grading_id)


@router.post("/gradings/{grading_id}/confidence")
def confide(grading_id: int, given: ConfidenceGiven, db: Database) -> GradingState:
    """The confidence in an open answer already sent (R6): the answer enters the
    history once its grading is done too."""
    _grading(db, grading_id)
    return give_confidence(db, grading_id, given.confidence, given.seconds)


@router.get("/gradings/{grading_id}")
def grading(grading_id: int, db: Database) -> GradingState:
    """Where the grading of an open answer stands: the interface asks until it is
    done."""
    return _grading(db, grading_id)


def _grading(db: sqlite3.Connection, grading_id: int) -> GradingState:
    state = grading_state(db, grading_id)
    if state is None:
        raise HTTPException(404, "Cette correction n'existe pas.")
    return state


@router.post("/answers/{answer_id}/claim", status_code=202)
def claim(answer_id: int, db: Database) -> ClaimStarted:
    """Je pense avoir juste (T5): Claude judges the answer again, in the background."""
    return ClaimStarted(make_claim(db, answer_id))


@router.get("/claims/{claim_id}")
def claim_of(claim_id: int, db: Database) -> ClaimState:
    """Where a claim stands: the interface asks until Claude has decided."""
    state = claim_state(db, claim_id)
    if state is None:
        raise HTTPException(404, "Cette demande n'existe pas.")
    return state


@router.post("/sessions/{session_id}/end")
def end_study(session_id: int, ending: SessionEnd, db: Database) -> DayStatus:
    """End a session once its thoughts are sorted (R17)."""
    return DayStatus(finish(db, session_id, ending.completed, date.today()))


@router.post("/sessions/{session_id}/thoughts", status_code=201)
def note_thought(session_id: int, thought: ThoughtNoted, db: Database) -> Thought:
    """Put a thought aside without leaving the question (key P, R17)."""
    return Thought(add_thought(db, session_id, thought.text), thought.text.strip())


@router.get("/sessions/{session_id}/thoughts")
def thoughts(session_id: int, db: Database) -> list[Thought]:
    """The thoughts still to plan or drop before the session ends (R17)."""
    return undecided_thoughts(db, session_id)


@router.post("/thoughts/{thought_id}/decision", status_code=204)
def decide(thought_id: int, decision: ThoughtDecision, db: Database) -> None:
    when = (
        datetime.fromisoformat(decision.planned_for) if decision.planned_for else None
    )
    decide_thought(db, thought_id, when)


@router.post("/sessions/{session_id}/wanderings", status_code=204)
def wandered(session_id: int, wandering: Wandering, db: Database) -> None:
    """J'ai décroché: counted, and the session goes on (R18)."""
    add_wandering(db, session_id, wandering.question_id)


@router.get("/notions/next")
def notion_to_study(db: Database) -> NotionToStudy | None:
    """The next notion to study, in the subject with the closest exam."""
    return next_notion(db)


@router.get("/notions/{notion_id}")
def notion(notion_id: int, db: Database) -> NotionToStudy:
    return _notion(db, notion_id)


@router.get("/notions/{notion_id}/pages")
def notion_pages(notion_id: int, db: Database) -> list[PageText]:
    """The pages of a notion, for its guided reading (R13)."""
    found = _notion(db, notion_id)
    return get_pages(db, found.resource_id, found.first_page, found.last_page)


@router.post("/notions/{notion_id}/session", status_code=201)
def study_notion(notion_id: int, db: Database) -> NotionSession:
    """Start the study of a notion: pretests, reading, then test (R13)."""
    return start_notion(db, notion_id, date.today())


# The reader: the imported files, untouched, and their outline (R4)


@dataclass(frozen=True)
class ResourceView:
    """An imported file with its subject: the reader offers its other files."""

    id: int
    subject_id: int
    file_name: str
    kind: str
    page_count: int  # pages of a PDF, sections of a Markdown file


@router.get("/resources/{resource_id}")
def resource(resource_id: int, db: Database) -> ResourceView:
    return _resource(db, resource_id)


@router.get("/resources/{resource_id}/pages")
def resource_pages(resource_id: int, db: Database) -> list[PageText]:
    """Every page of a file as text: the reader shows a Markdown file so."""
    found = _resource(db, resource_id)
    return get_pages(db, resource_id, 1, found.page_count)


@router.get("/resources/{resource_id}/file")
def resource_file(resource_id: int, db: Database, folder: Folder) -> FileResponse:
    row = db.execute(
        "SELECT kind FROM resource WHERE id = ?", (resource_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(404, "Ce fichier n'existe pas.")
    (kind,) = row
    path = copy_path(folder.resources, resource_id, kind)
    if not path.exists():
        raise HTTPException(404, "La copie de ce fichier est introuvable.")
    media = "application/pdf" if kind == "pdf" else "text/markdown; charset=utf-8"
    return FileResponse(path, media_type=media)


@router.get("/resources/{resource_id}/outline")
def resource_outline(resource_id: int, db: Database) -> list[Heading]:
    """The outline of a file, for the table of contents of the reader."""
    if (
        db.execute("SELECT 1 FROM resource WHERE id = ?", (resource_id,)).fetchone()
        is None
    ):
        raise HTTPException(404, "Ce fichier n'existe pas.")
    return get_document(db, resource_id).headings


def _chapter_id(db: sqlite3.Connection, subject_id: int, number: int) -> int:
    row = db.execute(
        "SELECT id FROM chapter WHERE subject_id = ? AND number = ?",
        (subject_id, number),
    ).fetchone()
    if row is None:
        raise HTTPException(404, "Ce chapitre n'existe pas.")
    return row[0]


def _chapter_view(db: sqlite3.Connection, chapter_id: int) -> ChapterView:
    number, title, role = db.execute(
        "SELECT number, title, role FROM chapter WHERE id = ?", (chapter_id,)
    ).fetchone()
    notions = [
        NotionWithQuestions(
            notion.id,
            notion.number,
            notion.title,
            notion.summary,
            notion.resource_id,
            notion.first_page,
            notion.last_page,
            notion.studied,
            [
                QuestionSummary(q.id, q.role, q.format, q.statement, q.reported)
                for q in get_questions(db, notion.id)
            ],
            questions_state(db, notion.id),
        )
        for notion in get_notions(db, chapter_id)
    ]
    return ChapterView(chapter_id, number, title, role, notions)


def _resource(db: sqlite3.Connection, resource_id: int) -> ResourceView:
    row = db.execute(
        "SELECT id, subject_id, file_name, kind,"
        " (SELECT COUNT(*) FROM page p WHERE p.resource_id = r.id)"
        " FROM resource r WHERE id = ?",
        (resource_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(404, "Ce fichier n'existe pas.")
    return ResourceView(*row)


def _notion(db: sqlite3.Connection, notion_id: int) -> NotionToStudy:
    found = find_notion(db, notion_id)
    if found is None:
        raise HTTPException(404, "Cette notion n'existe pas.")
    return found


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
