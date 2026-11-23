-- Background AI tasks (T1, T2…), done one by one by a single worker. A task that
-- cannot reach its engine (offline, Pro limit) waits until `not_before`, then is
-- tried again: it does not fail for that.
CREATE TABLE ai_task (
    id         INTEGER PRIMARY KEY,
    kind       TEXT    NOT NULL,
    subject_id INTEGER REFERENCES subject (id) ON DELETE CASCADE,
    input      TEXT    NOT NULL,  -- JSON
    status     TEXT    NOT NULL DEFAULT 'pending'
                       CHECK (status IN ('pending', 'running', 'done', 'failed')),
    attempts   INTEGER NOT NULL DEFAULT 0,
    not_before TEXT,              -- not tried again before this time
    result     TEXT,              -- JSON, once done
    error      TEXT,              -- why it failed, or why it waits
    created_at TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
