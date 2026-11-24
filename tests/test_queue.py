"""Tests of the daily queue: due questions, urgency, mixed subjects, 15 minutes."""

from datetime import UTC, datetime, timedelta

from bosh_mow.study.queue import QUESTIONS_PER_SESSION, DueQuestion, daily_queue

NOW = datetime(2026, 11, 24, 18, 0, tzinfo=UTC)


def due(question_id: int, subject_id: int, minutes_ago: int) -> DueQuestion:
    return DueQuestion(question_id, subject_id, NOW - timedelta(minutes=minutes_ago))


def test_only_the_questions_due_now_are_asked() -> None:
    assert daily_queue([due(1, 1, 5), due(2, 1, -5)], NOW) == [1]


def test_the_most_urgent_questions_come_first() -> None:
    queue = daily_queue([due(1, 1, 5), due(2, 1, 60 * 24), due(3, 1, 60)], NOW)

    assert queue == [2, 3, 1]


def test_r9_subjects_are_mixed_not_in_blocks() -> None:
    questions = [
        due(1, 1, 300),
        due(2, 1, 200),
        due(3, 1, 100),
        due(4, 2, 250),
        due(5, 2, 150),
        due(6, 3, 50),
    ]

    queue = daily_queue(questions, NOW)

    # Round after round, one question per subject, the most urgent subject first.
    assert queue == [1, 4, 6, 2, 5, 3]


def test_r12_the_queue_fits_in_about_15_minutes() -> None:
    questions = [due(n, 1 + n % 3, n) for n in range(1, 41)]

    queue = daily_queue(questions, NOW)

    assert len(queue) == QUESTIONS_PER_SESSION
    assert set(queue) == set(range(41 - QUESTIONS_PER_SESSION, 41))  # the most urgent


def test_r27_after_an_absence_the_queue_is_not_longer() -> None:
    questions = [due(n, 1, n) for n in range(1, 501)]  # a week away

    assert len(daily_queue(questions, NOW)) == QUESTIONS_PER_SESSION


def test_with_nothing_due_the_queue_is_empty() -> None:
    assert daily_queue([], NOW) == []
