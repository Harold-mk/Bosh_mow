"""Connection to the local SQLite database."""

import os
import sqlite3
from pathlib import Path


def default_db_path() -> Path:
    r"""Return the database file: %LOCALAPPDATA%\BoshMow\bosh.db."""
    return Path(os.environ["LOCALAPPDATA"]) / "BoshMow" / "bosh.db"


def connect(path: Path) -> sqlite3.Connection:
    """Open the database at `path`, creating its folder if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    # SQLite only enforces foreign keys when asked to, on each connection.
    connection.execute("PRAGMA foreign_keys = ON")
    return connection
