"""Spaced repetition with FSRS (D4): each answer sets the next date of its question.

A wrong answer comes back in the same session or the next day (R7); a right one keeps
coming back, further and further apart, and is never dropped (R8).
"""

from datetime import datetime

from fsrs import Card, Rating, Scheduler

from bosh_mow.study.repository import Confidence

# The default parameters of FSRS: 90 % of the questions remembered when they come back.
SCHEDULER = Scheduler()


def rating(correct: bool, confidence: Confidence | None) -> Rating:
    """The FSRS rating of an answer. A right answer given at random is "hard"; a right
    one given with confidence is "good", never "easy", so that intervals do not grow
    too fast."""
    if not correct or confidence is None:  # None: "Je ne sais pas"
        return Rating.Again
    return Rating.Hard if confidence == "guess" else Rating.Good


def review(
    card: Card | None,
    question_id: int,
    correct: bool,
    confidence: Confidence | None,
    now: datetime,
    scheduler: Scheduler = SCHEDULER,
) -> Card:
    """The card of a question after an answer; a question without card enters the
    reviews."""
    card = card or Card(card_id=question_id, due=now)
    reviewed, _ = scheduler.review_card(card, rating(correct, confidence), now)
    return reviewed
