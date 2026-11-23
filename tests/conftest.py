"""Fixtures shared by the tests."""

import sqlite3
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

import pytest

from bosh_mow.db.connection import connect
from bosh_mow.db.migrate import apply_migrations


@pytest.fixture
def db(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    """A temporary database with every migration applied, closed after the test."""
    with closing(connect(tmp_path / "bosh.db")) as connection:
        apply_migrations(connection)
        yield connection
