-- The exercises of a notion (T3, R14), stored as its questions: a worked example, a
-- problem to complete and three problems to solve alone, after its 7 questions. The
-- steps of their solution, each with its points (the rubric), are in the content. NULL
-- for a question.
ALTER TABLE question ADD COLUMN exercise TEXT
    CHECK (exercise IN ('worked', 'completion', 'solo'));
