"""Sessions as the interface drives them: the daily queue question by question, the
study of a new notion (R13), and the state of the day for the home screen.

Questions are sent without their correction, their options in a random order. Each
answer is graded here, without AI (T5), saved with its confidence (R6), and sets the
next date of its question (FSRS); a pretest only primes the reading and has no date.
"""

import random
import sqlite3
from dataclasses import dataclass, field, replace
from datetime import date, datetime

from bosh_mow.content.preparation import preparation_state, request_preparation
from bosh_mow.content.repository import (
    Question,
    get_notions,
    get_question,
    get_questions,
    mark_studied,
)
from bosh_mow.grading.closed import grade_mcq, grade_short, grade_value, mcq_options
from bosh_mow.study.days import after_absence, missed_yesterday, successful_days
from bosh_mow.study.queue import daily_queue
from bosh_mow.study.repository import (
    Confidence,
    NewAnswer,
    day_sessions,
    due_questions,
    end_session,
    get_card,
    minutes_studied,
    record_answer,
    save_card,
    start_session,
    undecided_thoughts,
)
from bosh_mow.study.scheduling import review

_shuffle = random.Random()

# The formats a session asks; the open answer joins them with its grading by Claude.
_ASKED_FORMATS = ("mcq", "value", "short")


@dataclass(frozen=True)
class OptionToAsk:
    number: int  # its number in the question, from 1: the answer sends it back
    text: str


@dataclass(frozen=True)
class QuestionToAsk:
    """A question as it is asked: without its correction, options in a random order."""

    id: int
    role: str
    format: str  # mcq, value or short
    statement: str
    options: list[OptionToAsk]  # an MCQ only
    tolerance: float | None  # a value only: relative, 0.01 for 1 %
    subject: str
    resource_id: int  # where its answer is (R4)
    first_page: int
    last_page: int


@dataclass(frozen=True)
class Correction:
    correct: bool
    priority: bool  # a mistake made while sure: shown first (R10)
    correct_option: int | None = None  # an MCQ: the right option, from 1
    explanations: list[str] = field(default_factory=list)  # an MCQ: of each option
    expected: str | None = None  # a value or a short answer: what was expected
    explanation: str | None = None  # a value or a short answer: how to find it


@dataclass(frozen=True)
class Today:
    due: int  # the questions of today's queue: never a backlog (R12, R27)
    successful_days: int  # R26
    minimum_done: bool
    missed_yesterday: bool  # warn before a second missed day in a row (R26)
    after_absence: bool  # today, the minimum session alone (R27)
    minutes: int  # studied today, in the sessions that have ended


@dataclass(frozen=True)
class NotionToStudy:
    id: int
    title: str
    summary: str
    subject: str
    chapter: str
    resource_id: int
    first_page: int
    last_page: int


@dataclass(frozen=True)
class NotionSession:
    session_id: int
    notion: NotionToStudy
    warmup: QuestionToAsk | None  # a question already succeeded, first (R15)
    pretests: list[QuestionToAsk]  # before the reading
    tests: list[QuestionToAsk]  # after the reading, the review questions (R13)


def today(connection: sqlite3.Connection, day: date, now: datetime) -> Today:
    """Where the day stands: the questions to review, the successful days."""
    sessions = day_sessions(connection)
    done = successful_days(sessions)
    first = min((session.day for session in sessions), default=None)
    return Today(
        len(daily_queue(due_questions(connection, now), now)),
        len(done),
        day in done,
        missed_yesterday(done, first, day),
        after_absence(done, first, day),
        minutes_studied(connection, day),
    )


def start_queue(connection: sqlite3.Connection, day: date, now: datetime) -> int:
    """Start the daily queue, noting how many questions it has (R26)."""
    planned = len(daily_queue(due_questions(connection, now), now))
    return start_session(connection, "queue", day, planned=planned)


def next_question(
    connection: sqlite3.Connection, session_id: int, now: datetime
) -> QuestionToAsk | None:
    """The next question of the daily queue, None once it is empty. A question just
    failed comes back when it is due again, within the session (R7); the subject
    changes from one question to the next when another one waits (R9)."""
    due = due_questions(connection, now)
    queue = daily_queue(due, now)
    if not queue:
        return None
    subject_of = {question.question_id: question.subject_id for question in due}
    last = connection.execute(
        "SELECT c.subject_id FROM answer a JOIN question q ON q.id = a.question_id"
        " JOIN notion n ON n.id = q.notion_id JOIN chapter c ON c.id = n.chapter_id"
        " WHERE a.session_id = ? ORDER BY a.id DESC LIMIT 1",
        (session_id,),
    ).fetchone()
    chosen = queue[0]
    if last is not None:
        chosen = next((q for q in queue if subject_of[q] != last[0]), queue[0])
    question = get_question(connection, chosen)
    assert question is not None  # it comes from the queue
    return _to_ask(connection, question)


def answer(
    connection: sqlite3.Connection,
    session_id: int | None,
    question_id: int,
    chosen_option: int | None,
    confidence: Confidence | None,
    seconds: int,
    now: datetime,
    answer_text: str | None = None,
) -> Correction:
    """Grade an answer without AI (T5), save it, and set the next date of a review
    question. An MCQ is answered with `chosen_option`, a value or a short answer with
    `answer_text`; nothing given is "Je ne sais pas", which needs no confidence."""
    question = get_question(connection, question_id)
    if question is None:
        raise ValueError(f"Question {question_id} does not exist.")
    mcq = question.format == "mcq"
    text = (answer_text or "").strip() or None
    given = chosen_option if mcq else text
    if given is not None and confidence is None:
        raise ValueError("Indique ta confiance avant de valider ta réponse.")
    if given is None:
        confidence = None  # "Je ne sais pas"
    correction = _grade(question, chosen_option, text)
    correction = replace(
        correction, priority=not correction.correct and confidence == "sure"
    )
    record_answer(
        connection,
        NewAnswer(
            question_id,
            session_id,
            correction.correct,
            confidence,
            seconds,
            chosen_option=chosen_option if mcq else None,
            answer_text=None if mcq else text,
        ),
    )
    if question.role == "review":
        card = review(
            get_card(connection, question_id),
            question_id,
            correction.correct,
            confidence,
            now,
        )
        save_card(connection, card)
    return correction


def _grade(
    question: Question, chosen_option: int | None, text: str | None
) -> Correction:
    """The correction of an answer by the code (T5), before its priority is known."""
    content = question.content
    if question.format == "mcq":
        options = mcq_options(content)
        return Correction(
            grade_mcq(options, chosen_option),
            priority=False,
            correct_option=next(
                number for number, option in enumerate(options, 1) if option.correct
            ),
            explanations=[option.explanation for option in options],
        )
    if question.format == "value":
        right = text is not None and grade_value(
            content["value"], content["tolerance"], text, content.get("accepted", [])
        )
        return Correction(
            right,
            priority=False,
            expected=_french(content["value"]),
            explanation=content.get("explanation"),
        )
    if question.format == "short":
        right = text is not None and grade_short(content["accepted"], text)
        return Correction(
            right,
            priority=False,
            expected=content["accepted"][0],
            explanation=content.get("explanation"),
        )
    raise ValueError(f"Question {question.id} is an open answer: Claude grades it.")


def _french(number: float) -> str:
    """A value as T2 wrote it, in French: "4", "0,25", "6,67"."""
    return repr(float(number)).removesuffix(".0").replace(".", ",")


def finish(
    connection: sqlite3.Connection, session_id: int, completed: bool, day: date
) -> bool:
    """End a session; return whether the day is now successful (R26). A session ends
    once its thoughts are planned or dropped (R17); a notion studied to the end is
    marked as studied (R13)."""
    if undecided_thoughts(connection, session_id):
        raise ValueError(
            "Il reste des pensées à trier : planifie-les ou abandonne-les."
        )
    row = connection.execute(
        "SELECT kind, notion_id FROM study_session WHERE id = ?", (session_id,)
    ).fetchone()
    if row is None:
        raise ValueError(f"Session {session_id} does not exist.")
    kind, notion_id = row
    end_session(connection, session_id, completed)
    if kind == "notion" and completed and notion_id is not None:
        mark_studied(connection, notion_id)
    return day in successful_days(day_sessions(connection))


def next_notion(connection: sqlite3.Connection) -> NotionToStudy | None:
    """The next notion to study: the first one not studied yet whose questions are
    written, in the active subject with the closest exam that has one."""
    row = connection.execute(
        f"{_SELECT_NOTION} WHERE s.status = 'active' AND n.studied_at IS NULL"
        " AND EXISTS (SELECT 1 FROM question q WHERE q.notion_id = n.id)"
        " ORDER BY s.exam_date, s.id, c.number, n.number LIMIT 1"
    ).fetchone()
    return NotionToStudy(*row) if row else None


def find_notion(connection: sqlite3.Connection, notion_id: int) -> NotionToStudy | None:
    """A notion as it is studied; None if it does not exist."""
    row = connection.execute(
        f"{_SELECT_NOTION} WHERE n.id = ?", (notion_id,)
    ).fetchone()
    return NotionToStudy(*row) if row else None


def start_notion(
    connection: sqlite3.Connection, notion_id: int, day: date
) -> NotionSession:
    """Start the study of a notion (R13): a question already succeeded to warm up
    (R15), its pretests, then its test. Starting a chapter also asks for the
    preparation of the next one (decision 10)."""
    notion = find_notion(connection, notion_id)
    if notion is None:
        raise ValueError(f"Notion {notion_id} does not exist.")
    questions = [
        question
        for question in get_questions(connection, notion_id)
        if question.format in _ASKED_FORMATS and not question.reported
    ]
    if not questions:
        raise ValueError("Les questions de cette notion ne sont pas encore prêtes.")
    session_id = start_session(connection, "notion", day, notion_id=notion_id)
    _prepare_next_chapter(connection, notion_id)
    return NotionSession(
        session_id,
        notion,
        _warmup(connection, notion_id),
        [_to_ask(connection, q) for q in questions if q.role == "pretest"],
        [_to_ask(connection, q) for q in questions if q.role == "review"],
    )


_SELECT_NOTION = (
    "SELECT n.id, n.title, n.summary, s.name, c.title, n.resource_id, n.first_page,"
    " n.last_page FROM notion n JOIN chapter c ON c.id = n.chapter_id"
    " JOIN subject s ON s.id = c.subject_id"
)


def _to_ask(connection: sqlite3.Connection, question: Question) -> QuestionToAsk:
    (subject,) = connection.execute(
        "SELECT s.name FROM notion n JOIN chapter c ON c.id = n.chapter_id"
        " JOIN subject s ON s.id = c.subject_id WHERE n.id = ?",
        (question.notion_id,),
    ).fetchone()
    (resource_id,) = connection.execute(
        "SELECT resource_id FROM notion WHERE id = ?", (question.notion_id,)
    ).fetchone()
    options = (
        [
            OptionToAsk(number, option.text)
            for number, option in enumerate(mcq_options(question.content), start=1)
        ]
        if question.format == "mcq"
        else []
    )
    return QuestionToAsk(
        question.id,
        question.role,
        question.format,
        question.statement,
        _shuffle.sample(options, len(options)),
        question.content.get("tolerance") if question.format == "value" else None,
        subject,
        resource_id,
        question.first_page,
        question.last_page,
    )


def _warmup(connection: sqlite3.Connection, notion_id: int) -> QuestionToAsk | None:
    """A question already succeeded, of another notion, to start with (R15): the one
    closest to being forgotten. None before a first success."""
    row = connection.execute(
        "SELECT q.id FROM question q JOIN card c ON c.question_id = q.id"
        " JOIN notion n ON n.id = q.notion_id JOIN chapter ch ON ch.id = n.chapter_id"
        " JOIN subject s ON s.id = ch.subject_id"
        " WHERE s.status = 'active' AND q.notion_id != ? AND q.role = 'review'"
        " AND q.format = 'mcq' AND q.reported_at IS NULL"
        " AND (SELECT a.correct FROM answer a WHERE a.question_id = q.id"
        " ORDER BY a.id DESC LIMIT 1) = 1"
        " ORDER BY c.due LIMIT 1",
        (notion_id,),
    ).fetchone()
    if row is None:
        return None
    question = get_question(connection, row[0])
    assert question is not None  # it was just found
    return _to_ask(connection, question)


def _prepare_next_chapter(connection: sqlite3.Connection, notion_id: int) -> None:
    """Ask for the next chapter once this one is started, if nobody did yet."""
    row = connection.execute(
        "SELECT following.id FROM notion n JOIN chapter c ON c.id = n.chapter_id"
        " JOIN chapter following ON following.subject_id = c.subject_id"
        " AND following.number = c.number + 1 WHERE n.id = ?",
        (notion_id,),
    ).fetchone()
    if row is None:
        return
    (following,) = row
    if (
        not get_notions(connection, following)
        and preparation_state(connection, following) is None
    ):
        request_preparation(connection, following)
