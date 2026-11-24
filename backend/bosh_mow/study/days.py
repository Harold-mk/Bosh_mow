"""Successful days (R26) and the return after an absence (R27).

A day is successful once its minimum session is done: the daily queue finished, emptied
or its time up. On a day with nothing to review, a notion studied to the end is enough.
No screen counts days or questions late: the app only warns before a second missed day
in a row, and after an absence it proposes the minimum session alone.
"""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta

from bosh_mow.study.repository import SessionKind


@dataclass(frozen=True)
class DaySession:
    day: date  # the local calendar day it counts for
    kind: SessionKind
    completed: bool
    planned: int | None = None  # questions in the queue at its start; None: a notion


def successful_days(sessions: Iterable[DaySession]) -> set[date]:
    """The days when the minimum session was done (R26)."""
    by_day: defaultdict[date, list[DaySession]] = defaultdict(list)
    for session in sessions:
        by_day[session.day].append(session)
    return {day for day, of_day in by_day.items() if _minimum_done(of_day)}


def missed_yesterday(
    successful: set[date], first_day: date | None, today: date
) -> bool:
    """Whether to warn that a second missed day in a row is coming (R26)."""
    yesterday = today - timedelta(days=1)
    return (
        first_day is not None
        and first_day <= yesterday
        and yesterday not in successful
        and today not in successful
    )


def after_absence(successful: set[date], first_day: date | None, today: date) -> bool:
    """Whether the last two days were missed: today, the minimum session alone (R27)."""
    yesterday, before = today - timedelta(days=1), today - timedelta(days=2)
    return (
        first_day is not None
        and first_day <= before
        and yesterday not in successful
        and before not in successful
    )


def _minimum_done(sessions: list[DaySession]) -> bool:
    queues = [session for session in sessions if session.kind == "queue"]
    if any(session.completed and session.planned for session in queues):
        return True
    nothing_to_review = bool(queues) and not any(session.planned for session in queues)
    notion_studied = any(
        session.kind == "notion" and session.completed for session in sessions
    )
    return nothing_to_review and notion_studied
