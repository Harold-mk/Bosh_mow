"""Tests of the numbered SQL migrations, each on its own temporary database."""

import re
import sqlite3
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

import pytest

from bosh_mow.db import migrate
from bosh_mow.db.connection import connect
from bosh_mow.db.migrate import apply_migrations, current_version


@pytest.fixture
def connection(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    """An empty database in a temporary folder, closed after the test."""
    with closing(connect(tmp_path / "test.db")) as db:
        yield db


def latest_version() -> int:
    """Number of the last real migration (files are numbered 1, 2, 3...)."""
    return len(list(migrate.MIGRATIONS_DIR.glob("*.sql")))


def use_migrations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, files: dict[str, str]
) -> None:
    """Replace the real migrations with these files (name -> SQL) for one test."""
    folder = tmp_path / "migrations"
    folder.mkdir()
    for name, sql in files.items():
        (folder / name).write_text(sql, encoding="utf-8")
    monkeypatch.setattr(migrate, "MIGRATIONS_DIR", folder)


def test_new_database_is_brought_to_the_latest_version(
    connection: sqlite3.Connection,
) -> None:
    assert current_version(connection) == 0

    assert apply_migrations(connection) == latest_version()
    assert current_version(connection) == latest_version()
    rows = connection.execute(
        "SELECT version FROM schema_version ORDER BY version"
    ).fetchall()
    assert [version for (version,) in rows] == list(range(1, latest_version() + 1))


def test_applied_at_is_iso_8601_with_time_zone(connection: sqlite3.Connection) -> None:
    apply_migrations(connection)

    row = connection.execute("SELECT applied_at FROM schema_version").fetchone()
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", row[0])


def test_migrations_are_applied_only_once(connection: sqlite3.Connection) -> None:
    version = apply_migrations(connection)

    assert apply_migrations(connection) == version
    (count,) = connection.execute("SELECT COUNT(*) FROM schema_version").fetchone()
    assert count == version


def test_failed_migration_leaves_the_database_unchanged(
    connection: sqlite3.Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = migrate.MIGRATIONS_DIR / "001_create_schema_version.sql"
    use_migrations(
        tmp_path,
        monkeypatch,
        {
            first.name: first.read_text(encoding="utf-8"),
            # Creates a table, then fails: the table must not be left behind.
            "002_broken.sql": "CREATE TABLE half_done (x INTEGER);\n"
            "INSERT INTO missing_table VALUES (1);\n",
        },
    )

    with pytest.raises(sqlite3.Error):
        apply_migrations(connection)

    assert current_version(connection) == 1
    tables = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    assert [name for (name,) in tables.fetchall()] == ["schema_version"]


@pytest.mark.parametrize(
    "names",
    [
        ["001_first.sql", "003_gap.sql"],
        ["001_first.sql", "002_one.sql", "002_other.sql"],
    ],
    ids=["gap", "duplicate"],
)
def test_migration_numbers_must_have_no_gap_or_duplicate(
    names: list[str],
    connection: sqlite3.Connection,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    use_migrations(tmp_path, monkeypatch, {name: "SELECT 1;\n" for name in names})

    with pytest.raises(RuntimeError, match="no gap, no duplicate"):
        apply_migrations(connection)
