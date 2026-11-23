-- Subjects and their content (lot 1): objectives, imported files and their pages,
-- chapters and their sources, plus the settings chosen at first launch.
-- Calendar dates are 'YYYY-MM-DD'; timestamps are ISO 8601 in UTC (Z).

-- A subject is a draft while it is being created; it appears in the app only once its
-- objectives are validated (R2). It is archived rather than deleted.
CREATE TABLE subject (
    id         INTEGER PRIMARY KEY,
    name       TEXT    NOT NULL,
    exam_date  TEXT    NOT NULL,
    status     TEXT    NOT NULL DEFAULT 'draft'
                       CHECK (status IN ('draft', 'active', 'archived')),
    created_at TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- "Être capable de…": 5 at most per subject (R2), in the order shown.
CREATE TABLE objective (
    id         INTEGER PRIMARY KEY,
    subject_id INTEGER NOT NULL REFERENCES subject (id) ON DELETE CASCADE,
    position   INTEGER NOT NULL,
    text       TEXT    NOT NULL,
    UNIQUE (subject_id, position)
);

-- An imported PDF or Markdown file. Its untouched copy is kept in the data folder.
CREATE TABLE resource (
    id          INTEGER PRIMARY KEY,
    subject_id  INTEGER NOT NULL REFERENCES subject (id) ON DELETE CASCADE,
    file_name   TEXT    NOT NULL,
    kind        TEXT    NOT NULL CHECK (kind IN ('pdf', 'markdown')),
    imported_at TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- A PDF page, or a Markdown section, which plays the role of a page. Numbered from 1.
CREATE TABLE page (
    resource_id INTEGER NOT NULL REFERENCES resource (id) ON DELETE CASCADE,
    number      INTEGER NOT NULL,
    text        TEXT    NOT NULL,
    image_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (resource_id, number)
);

CREATE TABLE chapter (
    id         INTEGER PRIMARY KEY,
    subject_id INTEGER NOT NULL REFERENCES subject (id) ON DELETE CASCADE,
    number     INTEGER NOT NULL,
    title      TEXT    NOT NULL,
    role       TEXT    NOT NULL CHECK (role IN ('core', 'secondary')),
    UNIQUE (subject_id, number)
);

-- The pages of one file that a chapter covers: a chapter can combine several files,
-- for example a book and notes.
CREATE TABLE chapter_source (
    chapter_id  INTEGER NOT NULL REFERENCES chapter (id) ON DELETE CASCADE,
    resource_id INTEGER NOT NULL REFERENCES resource (id) ON DELETE CASCADE,
    first_page  INTEGER NOT NULL,
    last_page   INTEGER NOT NULL CHECK (last_page >= first_page),
    PRIMARY KEY (chapter_id, resource_id)
);

CREATE TABLE chapter_objective (
    chapter_id   INTEGER NOT NULL REFERENCES chapter (id) ON DELETE CASCADE,
    objective_id INTEGER NOT NULL REFERENCES objective (id) ON DELETE CASCADE,
    PRIMARY KEY (chapter_id, objective_id)
);

-- Chosen at first launch: study time per day (R11) and "si… alors…" plan (R25).
-- A single row; no row means that the first launch is not completed.
CREATE TABLE settings (
    id              INTEGER PRIMARY KEY CHECK (id = 1),
    weekday_minutes INTEGER NOT NULL CHECK (weekday_minutes > 0),
    weekend_minutes INTEGER NOT NULL CHECK (weekend_minutes > 0),
    plan_if         TEXT    NOT NULL,
    plan_then       TEXT    NOT NULL
);
