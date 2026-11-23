"""Connection to the local SQLite database."""

import sqlite3
from pathlib import Path


def connect(path: Path) -> sqlite3.Connection:
    """Open the database at `path`, creating its folder if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    # FastAPI may open, use and close a connection in different threads; a connection
    # still serves a single request, or the worker, at a time.
    connection = sqlite3.connect(path, check_same_thread=False)
    # SQLite only enforces foreign keys when asked to, on each connection.
    connection.execute("PRAGMA foreign_keys = ON")
    return connection
