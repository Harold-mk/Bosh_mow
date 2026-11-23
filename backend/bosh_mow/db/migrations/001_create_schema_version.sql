-- Version of the database schema: one row per applied migration.
-- Dates are stored as ISO 8601 text with their time zone (here UTC, written Z).
CREATE TABLE schema_version (
    version    INTEGER PRIMARY KEY,
    applied_at TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
