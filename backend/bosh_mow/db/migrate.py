"""Numbered SQL migrations, applied in order.

Each file of migrations/ is named NNN_description.sql (001, 002, ...) and must not
contain BEGIN or COMMIT. The database version is the number of the last migration
applied, stored in the schema_version table created by the first migration.
"""

import sqlite3
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def current_version(connection: sqlite3.Connection) -> int:
    """Return the database version, 0 if no migration has been applied yet."""
    found = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'schema_version'"
    ).fetchone()
    if found is None:
        return 0
    row = connection.execute("SELECT MAX(version) FROM schema_version").fetchone()
    return row[0] or 0


def apply_migrations(connection: sqlite3.Connection) -> int:
    """Apply the migrations newer than the database and return its new version."""
    version = current_version(connection)
    for number, path in _migration_files():
        if number <= version:
            continue
        # executescript() commits each statement on its own: the explicit BEGIN makes
        # the whole migration one transaction, committed or rolled back by `with`.
        with connection:
            connection.executescript("BEGIN;\n" + path.read_text(encoding="utf-8"))
            connection.execute(
                "INSERT INTO schema_version (version) VALUES (?)", (number,)
            )
        version = number
    return version


def _migration_files() -> list[tuple[int, Path]]:
    """Return the migration files as (number, path), checking they go 1, 2, 3..."""
    files = sorted(
        (int(path.name.split("_")[0]), path) for path in MIGRATIONS_DIR.glob("*.sql")
    )
    numbers = [number for number, _ in files]
    if numbers != list(range(1, len(files) + 1)):
        raise RuntimeError(
            f"Migrations must be numbered 1, 2, 3... (no gap, no duplicate): {numbers}"
        )
    return files
