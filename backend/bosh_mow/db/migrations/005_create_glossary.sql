-- Technical terms of a subject that are never translated (T9). Claude proposes them
-- with the chapters (T1) and they are saved when the subject is validated, in the
-- order given.
CREATE TABLE glossary_term (
    subject_id INTEGER NOT NULL REFERENCES subject (id) ON DELETE CASCADE,
    term       TEXT    NOT NULL,
    PRIMARY KEY (subject_id, term)
);
