"""Settings chosen at first launch: study time per day (R11) and plan (R25)."""

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    weekday_minutes: int
    weekend_minutes: int
    plan_if: str  # "Si je rentre et que j'ai dîné…"
    plan_then: str  # "… alors je lance la file du jour à 19 h"


def get_settings(connection: sqlite3.Connection) -> Settings | None:
    """The saved settings, or None as long as the first launch is not completed."""
    row = connection.execute(
        "SELECT weekday_minutes, weekend_minutes, plan_if, plan_then FROM settings"
    ).fetchone()
    return Settings(*row) if row else None


def save_settings(connection: sqlite3.Connection, settings: Settings) -> None:
    """Save the settings, replacing the previous ones."""
    with connection:
        connection.execute(
            "INSERT OR REPLACE INTO settings"
            " (id, weekday_minutes, weekend_minutes, plan_if, plan_then)"
            " VALUES (1, ?, ?, ?, ?)",
            (
                settings.weekday_minutes,
                settings.weekend_minutes,
                settings.plan_if,
                settings.plan_then,
            ),
        )
