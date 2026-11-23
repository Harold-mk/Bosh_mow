"""Background AI tasks (T1, T2…), saved in the database and done one by one.

A single worker thread runs them in order. A task that cannot reach its engine
(offline, Pro limit) waits and is tried again later instead of failing; a task whose
answer stays invalid fails, and says why. Interrupted tasks resume at the next start.
"""

import json
import sqlite3
import threading
from collections.abc import Callable, Mapping
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from bosh_mow.ai.gateway import EngineUnavailable
from bosh_mow.db.connection import connect

RETRY_DELAY = timedelta(minutes=10)  # before trying an unavailable engine again
IDLE_WAIT_SECONDS = 60  # the worker checks for due tasks at least this often

type Handler = Callable[[sqlite3.Connection, dict[str, Any]], dict[str, Any]]

_wake = threading.Event()  # set when a task is added, so the worker starts at once


@dataclass(frozen=True)
class Task:
    id: int
    kind: str
    subject_id: int | None
    status: str  # pending, running, done or failed
    attempts: int
    result: dict[str, Any] | None
    error: str | None  # why it failed, or why it waits


def add_task(
    connection: sqlite3.Connection,
    kind: str,
    data: dict[str, Any],
    subject_id: int | None = None,
) -> int:
    """Queue a task for the worker and return its id."""
    with connection:
        task_id = connection.execute(
            "INSERT INTO ai_task (kind, subject_id, input) VALUES (?, ?, ?)",
            (kind, subject_id, json.dumps(data, ensure_ascii=False)),
        ).lastrowid
    wake_worker()
    return task_id


def get_task(connection: sqlite3.Connection, task_id: int) -> Task | None:
    row = connection.execute(
        "SELECT id, kind, subject_id, status, attempts, result, error"
        " FROM ai_task WHERE id = ?",
        (task_id,),
    ).fetchone()
    if row is None:
        return None
    task_id, kind, subject_id, status, attempts, result, error = row
    result = json.loads(result) if result else None
    return Task(task_id, kind, subject_id, status, attempts, result, error)


def run_next_task(
    connection: sqlite3.Connection, handlers: Mapping[str, Handler], now: datetime
) -> bool:
    """Run the oldest task that is due; return False when there is none."""
    row = connection.execute(
        "SELECT id, kind, input FROM ai_task WHERE status = 'pending'"
        " AND (not_before IS NULL OR not_before <= ?) ORDER BY id LIMIT 1",
        (_iso(now),),
    ).fetchone()
    if row is None:
        return False
    task_id, kind, data = row
    _update(connection, task_id, "status = 'running', attempts = attempts + 1")
    try:
        result = handlers[kind](connection, json.loads(data))
    except EngineUnavailable as error:
        _update(
            connection,
            task_id,
            "status = 'pending', not_before = ?, error = ?",
            (_iso(now + RETRY_DELAY), str(error)),
        )
    except Exception as error:  # an invalid answer, or a bug: say why it failed
        _update(connection, task_id, "status = 'failed', error = ?", (str(error),))
    else:
        _update(
            connection,
            task_id,
            "status = 'done', result = ?, error = NULL",
            (json.dumps(result, ensure_ascii=False),),
        )
    return True


def start_worker(
    db_path: Path, handlers: Mapping[str, Handler], stop: threading.Event
) -> threading.Thread:
    """Start the single worker, which runs until `stop` is set (with wake_worker)."""
    thread = threading.Thread(
        target=_work, args=(db_path, handlers, stop), name="ai-worker", daemon=True
    )
    thread.start()
    return thread


def wake_worker() -> None:
    _wake.set()


def _work(
    db_path: Path, handlers: Mapping[str, Handler], stop: threading.Event
) -> None:
    with closing(connect(db_path)) as connection:
        with connection:  # tasks cut by a restart are run again
            connection.execute(
                "UPDATE ai_task SET status = 'pending' WHERE status = 'running'"
            )
        while not stop.is_set():
            if not run_next_task(connection, handlers, datetime.now(UTC)):
                _wake.wait(IDLE_WAIT_SECONDS)
                _wake.clear()


def _update(
    connection: sqlite3.Connection,
    task_id: int,
    changes: str,
    values: tuple[Any, ...] = (),
) -> None:
    with connection:
        connection.execute(
            f"UPDATE ai_task SET {changes},"
            " updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = ?",
            (*values, task_id),
        )


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
