-- When Claude cannot grade an open answer, the local model does (D6): its grading is
-- provisional until Claude checks it in the background (T6).
ALTER TABLE grading ADD COLUMN provisional INTEGER NOT NULL DEFAULT 0
    CHECK (provisional IN (0, 1));
