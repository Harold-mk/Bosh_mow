"""Spaced repetition with FSRS (D4): each answer sets the next date of its question.

A wrong answer comes back in the same session or the next day (R7); a right one keeps
coming back, further and further apart, and is never dropped (R8). When a verdict
changes after the fact, the card is rebuilt from the history of its answers.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from fsrs import Card, Rating, Scheduler

from bosh_mow.study.repository import Confidence

# The default parameters of FSRS: 90 % of the questions remembered when they come back.
SCHEDULER = Scheduler()


@dataclass(frozen=True)
class PastAnswer:
    """An answer of the history, as FSRS needs it."""

    at: datetime
    correct: bool
    confidence: Confidence | None  # None: "Je ne sais pas"


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


def replay(
    question_id: int, answers: Sequence[PastAnswer], scheduler: Scheduler = SCHEDULER
) -> Card | None:
    """The card of a question rebuilt from all its answers, in the order they were
    given: for a verdict that changes after the fact, such as a claim accepted ("Je
    pense avoir juste"). None for a question never answered."""
    card = None
    for past in sorted(answers, key=lambda answer: answer.at):
        card = review(
            card, question_id, past.correct, past.confidence, past.at, scheduler
        )
    return card
