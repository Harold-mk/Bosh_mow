"""Tests of the grading without AI of closed questions (T5): the MCQ in lot 2."""

import pytest

from bosh_mow.grading.closed import Option, grade_mcq, mcq_options

OPTIONS = [
    Option("It is only a convention", False, "Erreur fréquente : …"),
    Option("One degree of freedom is lost", True, "C'est ça : …"),
    Option("To get the standard deviation", False, "Non : …"),
]


def test_t5_the_correct_option_is_right() -> None:
    assert grade_mcq(OPTIONS, 2)


def test_t5_another_option_is_wrong() -> None:
    assert not grade_mcq(OPTIONS, 1)


def test_t5_dont_know_is_wrong() -> None:
    assert not grade_mcq(OPTIONS, None)


@pytest.mark.parametrize("chosen", [0, 4])
def test_t5_an_option_that_does_not_exist_is_refused(chosen: int) -> None:
    with pytest.raises(ValueError, match="no option"):
        grade_mcq(OPTIONS, chosen)


def test_the_options_come_from_the_question_content() -> None:
    content = {
        "options": [
            {
                "text": option.text,
                "correct": option.correct,
                "explanation": option.explanation,
            }
            for option in OPTIONS
        ]
    }

    assert mcq_options(content) == OPTIONS
