"""T6: open answers, graded by Claude against the criteria of their question.

Claude says which criteria an answer meets, with a comment for the student; the app
concludes, so that a verdict never depends on how a language model counts. A written
answer to an exercise (T3) is graded the same way: the steps left to the student are
its criteria, each worth its points. When Claude cannot answer, the local model grades
instead (D6), and its grading is provisional.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from typing import Any, Self

from bosh_mow.ai.gateway import EngineTimeout, EngineUnavailable, Gateway, InvalidAnswer
from bosh_mow.ai.schemas import T6Answer
from bosh_mow.grading.exercises import exercise_verdict

GRADING_PROMPT = "t6_v1"
EXERCISE_PROMPT = "t6_exercise_v1"


@dataclass(frozen=True)
class OpenQuestion:
    """What grading an answer needs: the question, its model answer, the criteria that
    a right answer meets, and the errors students often make on it. For an exercise,
    the criteria are the steps left to the student, with their points."""

    statement: str
    expected_answer: str
    criteria: list[str]
    frequent_errors: list[str]
    points: list[int] | None = None  # an exercise: what each step to do is worth
    solution: list[str] = field(default_factory=list)  # an exercise: all its steps

    @classmethod
    def of(cls, statement: str, content: dict[str, Any]) -> Self:
        """The question to grade, from the content of an open question (T2) or of an
        exercise whose result is written (T3)."""
        if "steps" in content:
            steps = content["steps"]
            to_do = [step for step in steps if not step["given"]]
            return cls(
                statement,
                content["expected_answer"],
                [step["text"] for step in to_do],
                [],
                points=[step["points"] for step in to_do],
                solution=[step["text"] for step in steps],
            )
        return cls(
            statement,
            content["expected_answer"],
            content["criteria"],
            content["frequent_errors"],
        )


@dataclass(frozen=True)
class CriterionResult:
    criterion: str  # as the question states it
    met: bool
    comment: str  # in French, for the student


@dataclass(frozen=True)
class OpenGrading:
    criteria: list[CriterionResult]
    comment: str  # in French: what is solid, then what to add or correct first
    correct: bool  # concluded by the app: every criterion met
    provisional: bool = False  # by the local model: Claude checks it later


def grade_open(gateway: Gateway, question: OpenQuestion, answer: str) -> OpenGrading:
    """Ask Claude which criteria of the question the answer meets (T6); the app
    concludes: every criterion for a question, 80 % of the points and the result for
    an exercise (T3)."""
    if question.points is None:
        prompt = GRADING_PROMPT
        data: dict[str, Any] = {
            "question": question.statement,
            "expected_answer": question.expected_answer,
            "criteria": question.criteria,
            "frequent_errors": question.frequent_errors,
            "answer": answer,
        }
    else:
        prompt = EXERCISE_PROMPT
        data = {
            "exercise": question.statement,
            "solution": question.solution,
            "steps_to_check": [
                {"step": step, "points": points}
                for step, points in zip(question.criteria, question.points, strict=True)
            ],
            "result": question.expected_answer,
            "answer": answer,
        }
    reply = gateway.ask(
        prompt,
        data,
        T6Answer,
        check=lambda reply: check_grading(reply, len(question.criteria)),
    )
    results = [
        CriterionResult(criterion, result.met, result.comment.strip())
        for criterion, result in zip(question.criteria, reply.criteria, strict=True)
    ]
    met = [result.met for result in results]
    correct = (
        verdict(met)
        if question.points is None
        else exercise_verdict(question.points, met)
    )
    return OpenGrading(results, reply.comment.strip(), correct)


def grade_with_fallback(
    claude: Gateway, local: Gateway
) -> Callable[[OpenQuestion, str], OpenGrading]:
    """Grade with Claude; when Claude cannot (offline, plan limit, too long, invalid
    twice), with the local model, provisionally (D6). When neither can, Claude's
    failure stands: an unavailable Claude makes the grading wait for it."""

    def grade(question: OpenQuestion, answer: str) -> OpenGrading:
        try:
            return grade_open(claude, question, answer)
        except (EngineUnavailable, EngineTimeout, InvalidAnswer) as failure:
            try:
                graded = grade_open(local, question, answer)
            except (EngineUnavailable, EngineTimeout, InvalidAnswer):
                raise failure from None
            return replace(graded, provisional=True)

    return grade


def check_grading(reply: T6Answer, criteria: int) -> list[str]:
    """What breaks the rules of T6: one result per criterion, each with its reason,
    and a comment for the student."""
    problems = []
    if len(reply.criteria) != criteria:
        problems.append(
            "Give one result per criterion, in their order:"
            f" {criteria} results, not {len(reply.criteria)}."
        )
    problems += [
        f"Criterion {number}: say in one sentence why it is met or not."
        for number, result in enumerate(reply.criteria, start=1)
        if not result.comment.strip()
    ]
    if not reply.comment.strip():
        problems.append("Give the student a comment.")
    return problems


def verdict(criteria_met: Sequence[bool]) -> bool:
    """Whether an open answer is right: it meets every criterion of its question. With
    the 2 to 4 criteria of a question, this is also the 80 % rule of T6."""
    return bool(criteria_met) and all(criteria_met)
