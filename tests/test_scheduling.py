"""Tests of spaced repetition (FSRS, D4): the rating of an answer, its next date, and
the card rebuilt from the history when a verdict changes after the fact."""

from datetime import UTC, datetime, timedelta
from itertools import pairwise

import pytest
from fsrs import Rating, Scheduler, State

from bosh_mow.study.repository import Confidence
from bosh_mow.study.scheduling import PastAnswer, rating, replay, review

NOW = datetime(2026, 11, 24, 18, 0, tzinfo=UTC)
STEADY = Scheduler(enable_fuzzing=False)  # no random spread of the intervals in tests


@pytest.mark.parametrize(
    ("correct", "confidence", "expected"),
    [
        (False, "sure", Rating.Again),
        (False, None, Rating.Again),  # "Je ne sais pas", or an exercise missed
        (True, None, Rating.Good),  # an exercise: no confidence is asked
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


ANSWERS = [
    PastAnswer(NOW, True, "sure"),
    PastAnswer(NOW + timedelta(days=2), False, "hesitant"),
    PastAnswer(NOW + timedelta(days=3), False, None),  # "Je ne sais pas"
    PastAnswer(NOW + timedelta(days=4), True, "guess"),
]


def test_a_card_is_rebuilt_by_replaying_the_answers_of_its_question() -> None:
    card = None
    for past in ANSWERS:
        card = review(card, 7, past.correct, past.confidence, past.at, STEADY)

    assert replay(7, ANSWERS, STEADY) == card


def test_the_answers_are_replayed_in_the_order_they_were_given() -> None:
    assert replay(7, ANSWERS[::-1], STEADY) == replay(7, ANSWERS, STEADY)


def test_a_verdict_changed_after_the_fact_changes_the_next_date() -> None:
    """ "Je pense avoir juste" accepted: the answer was right, the question comes back
    later than after a mistake."""
    wrong = replay(7, [PastAnswer(NOW, False, "sure")], STEADY)
    right = replay(7, [PastAnswer(NOW, True, "sure")], STEADY)

    assert wrong is not None and right is not None
    assert right.due > wrong.due


def test_a_question_without_answers_has_no_card() -> None:
    assert replay(7, [], STEADY) is None
