"""Tests of spaced repetition (FSRS, D4): the rating of an answer and its next date."""

from datetime import UTC, datetime, timedelta
from itertools import pairwise

import pytest
from fsrs import Rating, Scheduler, State

from bosh_mow.study.repository import Confidence
from bosh_mow.study.scheduling import rating, review

NOW = datetime(2026, 11, 24, 18, 0, tzinfo=UTC)
STEADY = Scheduler(enable_fuzzing=False)  # no random spread of the intervals in tests


@pytest.mark.parametrize(
    ("correct", "confidence", "expected"),
    [
        (False, "sure", Rating.Again),
        (False, None, Rating.Again),  # "Je ne sais pas"
        (True, "guess", Rating.Hard),
        (True, "hesitant", Rating.Good),
        (True, "sure", Rating.Good),  # not Easy: intervals do not grow too fast
    ],
)
def test_the_rating_of_an_answer(
    correct: bool, confidence: Confidence | None, expected: Rating
) -> None:
    assert rating(correct, confidence) == expected


def test_a_question_enters_the_reviews_at_its_first_answer() -> None:
    card = review(None, 7, True, "sure", NOW, STEADY)

    assert card.card_id == 7
    assert card.due > NOW


def test_r7_a_wrong_answer_comes_back_in_the_session_or_the_next_day() -> None:
    new = review(None, 7, False, "sure", NOW, STEADY)
    known = None
    moment = NOW
    for _ in range(4):  # a question already well known…
        known = review(known, 7, True, "sure", moment, STEADY)
        moment = known.due
    assert known.state == State.Review

    forgotten = review(known, 7, False, "hesitant", moment, STEADY)  # …then failed

    assert new.due - NOW <= timedelta(days=1)
    assert forgotten.due - moment <= timedelta(days=1)


def test_r8_a_right_answer_comes_back_later_and_later() -> None:
    card = None
    moment = NOW
    intervals = []
    for _ in range(5):
        card = review(card, 7, True, "hesitant", moment, STEADY)
        intervals.append(card.due - moment)
        moment = card.due  # answered on the day it is due

    assert all(later > sooner for sooner, later in pairwise(intervals))
