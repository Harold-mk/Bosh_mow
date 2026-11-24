-- What Claude sees on a page whose content is mostly in images (T11, R38). The
-- questions and the assistant read this text; the reader always shows the page itself.
CREATE TABLE page_description (
    resource_id INTEGER NOT NULL,
    number      INTEGER NOT NULL,
    description TEXT    NOT NULL,
    elements    TEXT    NOT NULL, -- JSON list: axes, curves, legends, labels…
    to_check    TEXT,             -- what is unreadable or ambiguous, if anything
    PRIMARY KEY (resource_id, number),
    FOREIGN KEY (resource_id, number) REFERENCES page (resource_id, number)
        ON DELETE CASCADE
);
