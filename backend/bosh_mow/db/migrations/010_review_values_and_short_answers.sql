-- Sessions now ask values and short answers, graded without AI (T5). The notions
-- studied before asked only their MCQs: their value and short answer questions enter
-- the reviews now, due at once, as a question at its first answer (FSRS learning).
INSERT INTO card (question_id, state, step, due)
SELECT q.id, 1, 0, strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
FROM question q
JOIN notion n ON n.id = q.notion_id
WHERE n.studied_at IS NOT NULL
  AND q.role = 'review'
  AND q.format IN ('value', 'short')
  AND q.reported_at IS NULL
  AND NOT EXISTS (SELECT 1 FROM card c WHERE c.question_id = q.id);
