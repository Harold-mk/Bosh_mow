"""Tests of the background AI tasks: done, waiting for the engine, failed, resumed."""

import sqlite3
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from bosh_mow.ai.gateway import EngineUnavailable, InvalidAnswer
from bosh_mow.ai.tasks import (
    RETRY_DELAY,
    add_task,
    get_task,
    run_next_task,
    start_worker,
    wake_worker,
)

NOW = datetime(2026, 11, 23, 18, 0, tzinfo=UTC)


def echo(connection: sqlite3.Connection, data: dict[str, Any]) -> dict[str, Any]:
    return {"echo": data["text"]}


def unavailable(connection: sqlite3.Connection, data: dict[str, Any]) -> dict[str, Any]:
    raise EngineUnavailable("Limite du forfait Pro atteinte")


def invalid(connection: sqlite3.Connection, data: dict[str, Any]) -> dict[str, Any]:
    raise InvalidAnswer("objectives: 6 objectives, 5 at most")


def test_task_is_done_with_its_result(db: sqlite3.Connection) -> None:
    task_id = add_task(db, "echo", {"text": "bonjour"})

    assert run_next_task(db, {"echo": echo}, NOW)

    task = get_task(db, task_id)
    assert task is not None
    assert (task.status, task.attempts, task.result) == ("done", 1, {"echo": "bonjour"})


def test_without_task_due_nothing_runs(db: sqlite3.Connection) -> None:
    assert not run_next_task(db, {"echo": echo}, NOW)


def test_task_waits_while_the_engine_is_unavailable(db: sqlite3.Connection) -> None:
    task_id = add_task(db, "echo", {"text": "bonjour"})

    run_next_task(db, {"echo": unavailable}, NOW)

    task = get_task(db, task_id)
    assert task is not None
    assert (task.status, task.error) == ("pending", "Limite du forfait Pro atteinte")
    just_before = NOW + RETRY_DELAY - timedelta(seconds=1)
    assert not run_next_task(db, {"echo": echo}, just_before)
    assert run_next_task(db, {"echo": echo}, NOW + RETRY_DELAY)
    task = get_task(db, task_id)
    assert task is not None
    assert (task.status, task.attempts, task.error) == ("done", 2, None)


def test_invalid_answer_makes_the_task_fail_and_say_why(db: sqlite3.Connection) -> None:
    task_id = add_task(db, "t1", {})

    run_next_task(db, {"t1": invalid}, NOW)

    task = get_task(db, task_id)
    assert task is not None
    assert (task.status, task.error) == (
        "failed",
        "objectives: 6 objectives, 5 at most",
    )


def test_worker_resumes_interrupted_tasks_and_runs_new_ones(
    db: sqlite3.Connection, tmp_path: Path
) -> None:
    interrupted = add_task(db, "echo", {"text": "avant"})
    with db:
        db.execute("UPDATE ai_task SET status = 'running' WHERE id = ?", (interrupted,))
    stop = threading.Event()
    start_worker(tmp_path / "bosh.db", {"echo": echo}, stop)
    try:
        added = add_task(db, "echo", {"text": "après"})
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            tasks = [get_task(db, task_id) for task_id in (interrupted, added)]
            if all(task is not None and task.status == "done" for task in tasks):
                break
            time.sleep(0.05)
        assert [task.result for task in tasks if task is not None] == [
            {"echo": "avant"},
            {"echo": "après"},
        ]
    finally:
        stop.set()
        wake_worker()
