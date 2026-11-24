"""Tests of successful days (R26) and of the return after an absence (R27)."""

from datetime import date, timedelta

from bosh_mow.study.days import (
    DaySession,
    after_absence,
    missed_yesterday,
    successful_days,
)

TODAY = date(2026, 11, 24)


def days_ago(n: int) -> date:
    return TODAY - timedelta(days=n)


def test_r26_a_finished_queue_makes_the_day() -> None:
    assert successful_days([DaySession(TODAY, "queue", True, 12)]) == {TODAY}


def test_r26_an_unfinished_queue_does_not() -> None:
    assert successful_days([DaySession(TODAY, "queue", False, 12)]) == set()


def test_r26_with_nothing_to_review_a_studied_notion_makes_the_day() -> None:
    sessions = [DaySession(TODAY, "queue", False, 0), DaySession(TODAY, "notion", True)]

    assert successful_days(sessions) == {TODAY}


def test_r26_an_empty_queue_alone_does_not_make_the_day() -> None:
    assert successful_days([DaySession(TODAY, "queue", True, 0)]) == set()


def test_r26_a_notion_does_not_replace_a_queue_that_had_questions() -> None:
    sessions = [DaySession(TODAY, "queue", False, 5), DaySession(TODAY, "notion", True)]

    assert successful_days(sessions) == set()


def test_r26_warn_before_a_second_missed_day_in_a_row() -> None:
    assert missed_yesterday({days_ago(2)}, first_day=days_ago(5), today=TODAY)
    # Not once today is done, nor when yesterday was done, nor on the first day.
    assert not missed_yesterday({days_ago(2), TODAY}, days_ago(5), TODAY)
    assert not missed_yesterday({days_ago(1)}, days_ago(5), TODAY)
    assert not missed_yesterday(set(), first_day=TODAY, today=TODAY)


def test_r27_back_after_missing_the_last_two_days() -> None:
    assert after_absence({days_ago(3)}, first_day=days_ago(10), today=TODAY)
    assert not after_absence({days_ago(1)}, days_ago(10), TODAY)
    assert not after_absence({days_ago(2)}, days_ago(10), TODAY)
    assert not after_absence(set(), first_day=days_ago(1), today=TODAY)
    assert not after_absence(set(), first_day=None, today=TODAY)
