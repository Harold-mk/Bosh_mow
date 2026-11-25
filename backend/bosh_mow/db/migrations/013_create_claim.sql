-- "Je pense avoir juste" (T5): a value or a short answer that the code found wrong,
-- judged again by Claude in the background (T6). If Claude agrees, the answer becomes
-- right in the history, its question is rescheduled, and its wording joins the
-- accepted answers. One claim per answer.
CREATE TABLE claim (
    id        INTEGER PRIMARY KEY,
    answer_id INTEGER NOT NULL UNIQUE REFERENCES answer (id) ON DELETE CASCADE,
    status    TEXT    NOT NULL DEFAULT 'pending'
                      CHECK (status IN ('pending', 'accepted', 'refused', 'failed')),
    comment   TEXT,   -- Claude's reason, in French
    detail    TEXT,   -- why it failed
    asked_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
