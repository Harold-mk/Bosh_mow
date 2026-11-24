-- Studying: the spaced repetition state of each question (FSRS, D4), the sessions, the
-- answers, and what happens during a session: thoughts put aside (R17) and moments when
-- the mind wandered (R18). Timestamps are ISO 8601 in UTC (Z).

-- The FSRS card of a question that has entered the reviews.
CREATE TABLE card (
    question_id INTEGER PRIMARY KEY REFERENCES question (id) ON DELETE CASCADE,
    state       INTEGER NOT NULL CHECK (state IN (1, 2, 3)), -- learning, review, relearning
    step        INTEGER,
    stability   REAL,
    difficulty  REAL,
    due         TEXT    NOT NULL,
    last_review TEXT
);
CREATE INDEX card_due ON card (due);

-- A session: the daily queue, which is the minimum session (R12), or the study of a
-- new notion (R13).
CREATE TABLE study_session (
    id         INTEGER PRIMARY KEY,
    kind       TEXT    NOT NULL CHECK (kind IN ('queue', 'notion')),
    notion_id  INTEGER REFERENCES notion (id) ON DELETE SET NULL,
    planned    INTEGER CHECK (planned >= 0), -- questions in the queue at its start
    day        TEXT    NOT NULL, -- the local calendar day it counts for (R26)
    started_at TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    ended_at   TEXT,
    completed  INTEGER NOT NULL DEFAULT 0 CHECK (completed IN (0, 1))
);

-- One answer, given in a session or not: the only source of the statistics.
CREATE TABLE answer (
    id            INTEGER PRIMARY KEY,
    question_id   INTEGER NOT NULL REFERENCES question (id) ON DELETE CASCADE,
    session_id    INTEGER REFERENCES study_session (id) ON DELETE SET NULL,
    answered_at   TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    chosen_option INTEGER, -- an MCQ: the option chosen, from 1
    answer_text   TEXT,    -- the other formats; both NULL: "Je ne sais pas"
    correct       INTEGER NOT NULL CHECK (correct IN (0, 1)),
    confidence    TEXT    CHECK (confidence IN ('sure', 'hesitant', 'guess')), -- R6
    seconds       INTEGER NOT NULL CHECK (seconds >= 0)
);
CREATE INDEX answer_question ON answer (question_id);

-- A thought noted with the P key during a session, then planned or dropped (R17).
CREATE TABLE thought (
    id          INTEGER PRIMARY KEY,
    session_id  INTEGER REFERENCES study_session (id) ON DELETE SET NULL,
    text        TEXT NOT NULL,
    noted_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    decision    TEXT CHECK (decision IN ('planned', 'dropped')), -- NULL until decided
    planned_for TEXT -- local date and time 'YYYY-MM-DDTHH:MM', when planned
);

-- "J'ai décroché": the mind wandered, and the session went on (R18).
CREATE TABLE mind_wandering (
    id          INTEGER PRIMARY KEY,
    session_id  INTEGER NOT NULL REFERENCES study_session (id) ON DELETE CASCADE,
    question_id INTEGER REFERENCES question (id) ON DELETE SET NULL,
    at          TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
