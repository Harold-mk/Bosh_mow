-- The outline of each imported file: used to propose the chapters (T1), and later to
-- show the table of contents in the reader.

-- Where the outline comes from: 'structure' (PDF bookmarks or Markdown # and ##
-- titles), 'fonts' (titles guessed from their size or weight) or 'none'.
ALTER TABLE resource ADD COLUMN outline TEXT NOT NULL DEFAULT 'none'
    CHECK (outline IN ('structure', 'fonts', 'none'));

-- `page` is a PDF page or a Markdown section, numbered from 1.
CREATE TABLE heading (
    resource_id INTEGER NOT NULL REFERENCES resource (id) ON DELETE CASCADE,
    position    INTEGER NOT NULL,
    level       INTEGER NOT NULL CHECK (level >= 1),
    title       TEXT    NOT NULL,
    page        INTEGER NOT NULL,
    PRIMARY KEY (resource_id, position)
);
