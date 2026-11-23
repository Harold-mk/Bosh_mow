-- Version of the database schema: one row per applied migration.
CREATE TABLE schema_version (
    version    INTEGER PRIMARY KEY,
    applied_at TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);
