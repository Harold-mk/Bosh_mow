"""Tests of the settings chosen at first launch (R11, R25)."""

import sqlite3

from bosh_mow.settings import Settings, get_settings, save_settings


def test_no_settings_before_the_first_launch(db: sqlite3.Connection) -> None:
    assert get_settings(db) is None


def test_saved_settings_replace_the_previous_ones(db: sqlite3.Connection) -> None:
    save_settings(db, Settings(90, 180, "je rentre", "je lance la file du jour"))
    save_settings(db, Settings(60, 120, "j'ai dîné", "je lance la file du jour"))

    assert get_settings(db) == Settings(
        60, 120, "j'ai dîné", "je lance la file du jour"
    )
