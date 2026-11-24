"""Tests of the settings chosen at first launch (R11, R25) and of the interface."""

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


def test_the_reduced_sidebar_is_remembered(db: sqlite3.Connection) -> None:
    settings = Settings(90, 180, "je rentre", "je lance la file du jour")
    assert settings.sidebar_collapsed is False

    save_settings(db, Settings(90, 180, "je rentre", "je lance la file du jour", True))

    saved = get_settings(db)
    assert saved is not None
    assert saved.sidebar_collapsed is True
