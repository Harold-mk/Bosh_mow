"""The daily queue: the questions due, subjects mixed (R9), in about 15 minutes (R12).

The most urgent questions come first. Those that do not fit wait for the next days
without being counted late: after an absence, the queue is not longer (R27).
"""

from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

SESSION_SECONDS = 15 * 60  # the minimum session (R12)
SECONDS_PER_QUESTION = 36  # an estimate for an MCQ, until the answers say better
QUESTIONS_PER_SESSION = SESSION_SECONDS // SECONDS_PER_QUESTION


@dataclass(frozen=True)
class DueQuestion:
    question_id: int
    subject_id: int
    due: datetime


def daily_queue(questions: Sequence[DueQuestion], now: datetime) -> list[int]:
    """The questions to ask now, in order: the most urgent first, as many as fit in the
    minimum session, and never two of a subject in a row while another one waits."""
    ready = sorted(
        (question for question in questions if question.due <= now),
        key=lambda question: (question.due, question.question_id),
    )
    return [question.question_id for question in _mix(ready[:QUESTIONS_PER_SESSION])]


def _mix(questions: Sequence[DueQuestion]) -> list[DueQuestion]:
    """Round after round, one question of each subject, the most urgent subject first.

    `questions` are sorted, the most urgent first.
    """
    by_subject: dict[int, deque[DueQuestion]] = {}
    for question in questions:
        by_subject.setdefault(question.subject_id, deque()).append(question)
    mixed: list[DueQuestion] = []
    while by_subject:
        for subject_id in sorted(by_subject, key=lambda s: _urgency(by_subject[s][0])):
            waiting = by_subject[subject_id]
            mixed.append(waiting.popleft())
            if not waiting:
                del by_subject[subject_id]
    return mixed


def _urgency(question: DueQuestion) -> tuple[datetime, int]:
    return question.due, question.question_id
