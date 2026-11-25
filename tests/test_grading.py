"""Tests of the grading without AI of closed questions (T5): the MCQ, the value and the
short answer; and of the verdict on an open answer graded by Claude (T6)."""

import pytest

from bosh_mow.grading.closed import (
    Option,
    grade_mcq,
    grade_short,
    grade_value,
    mcq_options,
    parse_value,
)
from bosh_mow.grading.open_answers import verdict

NARROW_SPACE = chr(0x202F)  # the no-break space between thousands in French

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


# The value: a number, with a comma or a point, within a tolerance.


@pytest.mark.parametrize(
    ("answer", "number"),
    [
        ("4", 4.0),
        ("4,5", 4.5),
        ("4.5", 4.5),
        (" 1 000 ", 1000.0),
        (f"1{NARROW_SPACE}000,5", 1000.5),  # as numbers are written in French
        ("-2", -2.0),
        ("−2", -2.0),  # the minus sign of the statements, "n − 1"
        ("+3", 3.0),
        (".5", 0.5),
        ("3e2", 300.0),
        ("1,5E-3", 0.0015),
        ("20/3", 20 / 3),
        ("-1/4", -0.25),
        ("20/3 kg", 20 / 3),
        ("2,5 kg", 2.5),
        ("4 ms", 4.0),
        ("25 %", 25.0),
        ("9,81 m/s²", 9.81),
    ],
)
def test_t5_a_value_is_read_from_the_answer(answer: str, number: float) -> None:
    assert parse_value(answer) == pytest.approx(number)


@pytest.mark.parametrize(
    "answer",
    [
        "",
        "   ",
        "four",
        "x = 4",
        "4^2",
        "4 * 2",
        "1/0",
        "1/3/2",
        "4/",
        "/4",
        "--4",
        "1,2,3",
    ],
)
def test_t5_an_answer_that_is_not_a_number_has_no_value(answer: str) -> None:
    assert parse_value(answer) is None


@pytest.mark.parametrize(
    ("answer", "right"),
    [
        ("4", True),
        ("4,0", True),
        ("4,04", True),  # 1 % above: still right
        ("3,96", True),  # 1 % below
        ("4,05", False),
        ("3,95", False),
        ("40", False),
        ("four", False),
        ("", False),
    ],
)
def test_t5_a_value_is_right_within_one_percent(answer: str, right: bool) -> None:
    assert grade_value(4.0, 0.01, answer) is right


def test_t5_the_tolerance_is_the_one_of_the_question() -> None:
    assert grade_value(100.0, 0.05, "104,9")
    assert not grade_value(100.0, 0.05, "105,1")


def test_t5_a_fraction_and_its_rounding_are_both_right() -> None:
    assert grade_value(20 / 3, 0.01, "20/3")
    assert grade_value(20 / 3, 0.01, "6,67")
    assert not grade_value(20 / 3, 0.01, "6,5")


def test_t5_a_negative_value_keeps_its_tolerance() -> None:
    assert grade_value(-2.0, 0.01, "-2,01")
    assert not grade_value(-2.0, 0.01, "2")


def test_t5_a_value_of_zero_is_given_exactly() -> None:
    assert grade_value(0.0, 0.01, "0")
    assert not grade_value(0.0, 0.01, "0,001")


def test_t5_a_wording_accepted_after_a_claim_is_right() -> None:
    """ "Je pense avoir juste": Claude agreed that 25 % is 0.25, now accepted."""
    assert not grade_value(0.25, 0.01, "25 %")
    assert grade_value(0.25, 0.01, "25 %", accepted=["25 %"])
    assert grade_value(0.25, 0.01, "25%", accepted=["25 %"])


# The short answer: cleaned, then compared to each accepted answer, one typo tolerated.


@pytest.mark.parametrize(
    "answer",
    [
        "HAVING",
        "having",
        "  Having ",
        "having clause",
        "Having-clause.",
        "havin",  # a letter missing
        "havingg",  # a letter too many
        "having",
        "hiving",  # a letter replaced
        "haivng",  # two letters swapped
    ],
)
def test_t5_a_short_answer_is_right_once_cleaned_with_one_typo(answer: str) -> None:
    assert grade_short(["HAVING", "having clause"], answer)


@pytest.mark.parametrize("answer", ["WHERE", "hvaign", "", "group by"])
def test_t5_another_short_answer_is_wrong(answer: str) -> None:
    assert not grade_short(["HAVING", "having clause"], answer)


@pytest.mark.parametrize("answer", ["ecart type", "Écart-Type", "écart-typ"])
def test_t5_accents_do_not_count(answer: str) -> None:
    assert grade_short(["écart-type", "standard deviation"], answer)


@pytest.mark.parametrize(
    ("answer", "right"),
    [("bse 10", True), ("base 11", False), ("base 100", False), ("base 01", False)],
)
def test_t5_a_typo_on_a_digit_is_a_mistake(answer: str, right: bool) -> None:
    assert grade_short(["base 10"], answer) is right


@pytest.mark.parametrize(
    ("accepted", "answer", "right"),
    [
        ("n − 1", "n - 1", True),
        ("n − 1", "N-1", True),
        ("n − 1", "n-2", False),  # a typo would make it right
        ("n − 1", "n", False),
        ("O(n)", "o(n)", True),
        ("O(n)", "O(1)", False),
        ("SQL", "sql", True),
        ("SQL", "sq", False),
    ],
)
def test_t5_no_typo_in_an_answer_under_four_characters(
    accepted: str, answer: str, right: bool
) -> None:
    assert grade_short([accepted], answer) is right


@pytest.mark.parametrize(
    ("answer", "right"), [("c ++", True), ("C", False), ("C#", False)]
)
def test_t5_the_signs_of_a_language_name_count(answer: str, right: bool) -> None:
    assert grade_short(["C++"], answer) is right


@pytest.mark.parametrize(
    ("answer", "right"), [("!=", True), (" != ", True), ("==", False)]
)
def test_t5_an_answer_made_only_of_signs_is_compared_as_written(
    answer: str, right: bool
) -> None:
    assert grade_short(["!="], answer) is right


def test_t5_exponents_and_ligatures_are_read_as_letters_and_digits() -> None:
    assert grade_short(["m²"], "m2")
    assert grade_short(["Straße"], "strasse")


# The open answer (T6): Claude says which criteria are met, the app concludes.


def test_t6_an_open_answer_is_right_when_every_criterion_is_met() -> None:
    assert verdict([True, True, True])


@pytest.mark.parametrize("met", [[True, False], [False, False], [True, True, False]])
def test_t6_an_open_answer_missing_a_criterion_is_to_review(met: list[bool]) -> None:
    assert not verdict(met)


def test_t6_an_open_answer_without_criteria_is_never_right() -> None:
    assert not verdict([])
