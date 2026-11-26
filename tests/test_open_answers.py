"""Tests of T6: an open answer graded by Claude against the criteria of its question,
with a fake AI. Claude says which criteria are met; the app concludes."""

from pathlib import Path
from typing import Any

import pytest
from fake_ai import FakeEngine

from bosh_mow.ai.gateway import EngineTimeout, EngineUnavailable, Gateway, InvalidAnswer
from bosh_mow.ai.schemas import T6Answer
from bosh_mow.grading.open_answers import (
    OpenQuestion,
    check_grading,
    grade_open,
    grade_with_fallback,
)

WHY = OpenQuestion(
    statement="Why is the median less sensitive than the mean to extreme values?",
    expected_answer="One extreme value moves the mean a lot, not the median.",
    criteria=["mentions extreme values", "explains the sensitivity of the mean"],
    frequent_errors=["says the median is always better"],
)
ANSWER = "An outlier pulls the mean towards it, not the median."


def graded(*met: bool, comment: str = "Tout y est.") -> dict[str, Any]:
    """An answer of T6: whether each criterion is met, in order."""
    return {
        "criteria": [
            {"met": one, "comment": "C'est dit." if one else "Il manque ce point."}
            for one in met
        ],
        "comment": comment,
    }


def problems(raw: dict[str, Any], criteria: int = 2) -> list[str]:
    return check_grading(T6Answer.model_validate(raw), criteria)


def fake(
    tmp_path: Path, *answers: dict[str, Any] | Exception
) -> tuple[Gateway, FakeEngine]:
    engine = FakeEngine([*answers])
    return Gateway(engine, tmp_path / "log"), engine


# The rules of T6


def test_a_grading_that_keeps_the_rules_passes() -> None:
    assert problems(graded(True, False)) == []


def test_one_result_per_criterion() -> None:
    assert problems(graded(True)) == [
        "Give one result per criterion, in their order: 2 results, not 1."
    ]


def test_each_result_says_why() -> None:
    raw = graded(True, False)
    raw["criteria"][1]["comment"] = " "

    assert problems(raw) == ["Criterion 2: say in one sentence why it is met or not."]


def test_the_student_gets_a_comment() -> None:
    assert problems(graded(True, True, comment="")) == ["Give the student a comment."]


# Grading through the gateway


def test_t6_claude_says_which_criteria_are_met_and_the_app_concludes(
    tmp_path: Path,
) -> None:
    gateway, engine = fake(tmp_path, graded(True, True))

    grading = grade_open(gateway, WHY, ANSWER)

    assert grading.correct
    assert [(c.criterion, c.met) for c in grading.criteria] == [
        ("mentions extreme values", True),
        ("explains the sensitivity of the mean", True),
    ]
    assert grading.comment == "Tout y est."
    (sent,) = engine.prompts
    for part in (WHY.statement, WHY.expected_answer, *WHY.criteria, ANSWER):
        assert part in sent
    assert WHY.frequent_errors[0] in sent


def test_t6_an_answer_missing_a_criterion_is_to_review(tmp_path: Path) -> None:
    gateway, _ = fake(tmp_path, graded(True, False))

    grading = grade_open(gateway, WHY, "Because of extreme values.")

    assert not grading.correct
    assert grading.criteria[1].comment == "Il manque ce point."


def test_t6_a_grading_that_breaks_the_rules_is_asked_again_once(
    tmp_path: Path,
) -> None:
    gateway, engine = fake(tmp_path, graded(True), graded(True, False))

    grading = grade_open(gateway, WHY, "Because of extreme values.")

    assert len(engine.prompts) == 2
    assert "one result per criterion" in engine.prompts[1]
    assert not grading.correct


def test_t6_a_grading_wrong_twice_is_reported(tmp_path: Path) -> None:
    gateway, _ = fake(tmp_path, graded(True), graded(True, True, True))

    with pytest.raises(InvalidAnswer):
        grade_open(gateway, WHY, ANSWER)


# The local model, when Claude cannot grade (D6)


def test_t6_claude_grades_first(tmp_path: Path) -> None:
    claude, _ = fake(tmp_path, graded(True, True))
    local, local_engine = fake(tmp_path, graded(False, False))

    grading = grade_with_fallback(claude, local)(WHY, ANSWER)

    assert (grading.correct, grading.provisional) == (True, False)
    assert local_engine.prompts == []


@pytest.mark.parametrize(
    "failure",
    [
        [EngineUnavailable("Limite du forfait atteinte.")],  # offline, Pro limit
        [EngineTimeout("Trop long."), EngineTimeout("Trop long.")],  # tried twice
        [graded(True), graded(True)],  # an answer that breaks the rules twice
    ],
)
def test_t6_the_local_model_grades_when_claude_cannot(
    tmp_path: Path, failure: list[dict[str, Any] | Exception]
) -> None:
    claude, _ = fake(tmp_path, *failure)
    local, _ = fake(tmp_path, graded(True, False))

    grading = grade_with_fallback(claude, local)(WHY, ANSWER)

    assert (grading.correct, grading.provisional) == (False, True)


def test_t6_without_claude_nor_the_local_model_the_grading_waits_for_claude(
    tmp_path: Path,
) -> None:
    claude, _ = fake(tmp_path, EngineUnavailable("Hors ligne."))
    local, _ = fake(tmp_path, EngineUnavailable("Ollama n'est pas lancé."))

    with pytest.raises(EngineUnavailable, match="Hors ligne"):
        grade_with_fallback(claude, local)(WHY, ANSWER)


def test_t6_when_both_fail_claudes_failure_is_reported(tmp_path: Path) -> None:
    claude, _ = fake(tmp_path, EngineTimeout("Trop long."), EngineTimeout("Trop long."))
    local, _ = fake(tmp_path, EngineUnavailable("Ollama n'est pas lancé."))

    with pytest.raises(EngineTimeout):
        grade_with_fallback(claude, local)(WHY, ANSWER)


# A written answer to an exercise (T3): the steps to do, each worth its points

EXERCISE = OpenQuestion.of(
    "Why does the sample variance divide by n - 1 and not by n?",
    {
        "topic": "Explaining the n - 1 of the sample variance",
        "steps": [
            {
                "text": "The deviations are taken from the sample mean.",
                "points": 1,
                "given": True,
            },
            {
                "text": "The sample mean is closer to the data than the true mean.",
                "points": 1,
                "given": False,
            },
            {
                "text": "So dividing by n underestimates the variance.",
                "points": 3,
                "given": False,
            },
            {
                "text": "Dividing by n - 1 gives an unbiased estimator.",
                "points": 1,
                "given": False,
            },
        ],
        "expected_answer": "Dividing by n - 1 corrects the bias of dividing by n.",
    },
)


def test_the_steps_left_to_the_student_are_the_criteria_of_an_exercise() -> None:
    assert EXERCISE.criteria == [
        "The sample mean is closer to the data than the true mean.",
        "So dividing by n underestimates the variance.",
        "Dividing by n - 1 gives an unbiased estimator.",
    ]
    assert EXERCISE.points == [1, 3, 1]
    assert len(EXERCISE.solution) == 4  # the step given too, to read after


@pytest.mark.parametrize(
    ("met", "right"),
    [
        ((True, True, True), True),
        ((False, True, True), True),  # a step missed, but 4 points out of 5: 80 %
        ((True, False, True), False),  # 2 points out of 5
        ((True, True, False), False),  # 4 out of 5, but the result is wrong
    ],
)
def test_t6_an_exercise_is_concluded_with_its_rubric(
    tmp_path: Path, met: tuple[bool, ...], right: bool
) -> None:
    gateway, engine = fake(tmp_path, graded(*met))

    grading = grade_open(gateway, EXERCISE, "Dividing by n is biased, n - 1 is not.")

    assert grading.correct is right
    (sent,) = engine.prompts
    assert sent.startswith("# T6: grade the written answer to an exercise")
    assert '"points": 3' in sent  # the rubric goes with the steps to check
    # The whole solution, the step given too.
    assert "The deviations are taken from the sample mean." in sent


def test_the_question_to_grade_comes_from_an_open_question() -> None:
    content = {
        "expected_answer": WHY.expected_answer,
        "criteria": WHY.criteria,
        "frequent_errors": WHY.frequent_errors,
    }

    assert OpenQuestion.of(WHY.statement, content) == WHY
