-- The notions of a chapter, cut just before it is studied (T1, pass 2), and the
-- questions on each notion (T2). They are saved once the student validates the notions
-- of the chapter (R3): until then they are only a proposal.

-- A notion: one idea, studied in a block of 10 minutes at most (R13), on pages of one
-- of the chapter's files.
CREATE TABLE notion (
    id          INTEGER PRIMARY KEY,
    chapter_id  INTEGER NOT NULL REFERENCES chapter (id) ON DELETE CASCADE,
    number      INTEGER NOT NULL, -- its place in the chapter, from 1
    title       TEXT    NOT NULL,
    summary     TEXT    NOT NULL, -- one line
    resource_id INTEGER NOT NULL REFERENCES resource (id) ON DELETE CASCADE,
    first_page  INTEGER NOT NULL,
    last_page   INTEGER NOT NULL CHECK (last_page >= first_page),
    studied_at  TEXT,             -- when it was first studied (R13); NULL before
    UNIQUE (chapter_id, number)
);

-- A question on a single idea of a notion (R5), with its source pages (R4). `content`
-- holds, as JSON, what its format needs: the options of an MCQ with their explanations,
-- the value and tolerance of a value, the accepted answers of a short answer, or the
-- expected answer, criteria and frequent errors of an open answer.
CREATE TABLE question (
    id          INTEGER PRIMARY KEY,
    notion_id   INTEGER NOT NULL REFERENCES notion (id) ON DELETE CASCADE,
    position    INTEGER NOT NULL,
    role        TEXT    NOT NULL CHECK (role IN ('pretest', 'review')),
    type        TEXT    NOT NULL CHECK (type IN ('concept', 'calculation', 'code')),
    level       TEXT    NOT NULL CHECK (level IN ('recall', 'explain', 'apply', 'analyze')),
    format      TEXT    NOT NULL CHECK (format IN ('mcq', 'value', 'short', 'open')),
    difficulty  INTEGER NOT NULL CHECK (difficulty BETWEEN 1 AND 3),
    statement   TEXT    NOT NULL, -- in English (R5)
    first_page  INTEGER NOT NULL,
    last_page   INTEGER NOT NULL CHECK (last_page >= first_page),
    content     TEXT    NOT NULL, -- JSON
    reported_at TEXT,             -- "Signaler": out of the reviews, kept for the prompt
    UNIQUE (notion_id, position)
);
