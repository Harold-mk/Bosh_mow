-- An open answer graded by Claude (T6). The grading starts as soon as the answer is
-- written, while the confidence is chosen (R6). The answer enters the history, and its
-- question gets its next date, once the grading is done and the confidence chosen,
-- whichever comes last, even after the end of the session.
CREATE TABLE grading (
    id          INTEGER PRIMARY KEY,
    question_id INTEGER NOT NULL REFERENCES question (id) ON DELETE CASCADE,
    session_id  INTEGER REFERENCES study_session (id) ON DELETE SET NULL,
    answer_text TEXT    NOT NULL,
    written_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    status      TEXT    NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'done', 'failed')),
    result      TEXT,    -- JSON once done: each criterion met or not, and the comments
    correct     INTEGER CHECK (correct IN (0, 1)), -- once done: every criterion met
    detail      TEXT,    -- why it failed
    confidence  TEXT    CHECK (confidence IN ('sure', 'hesitant', 'guess')), -- R6
    seconds     INTEGER CHECK (seconds >= 0), -- time taken to answer
    recorded_at TEXT,    -- when the answer entered the history, once only
    answer_id   INTEGER REFERENCES answer (id) ON DELETE SET NULL
);
CREATE INDEX grading_question ON grading (question_id);
