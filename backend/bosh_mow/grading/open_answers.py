"""T6: open answers, graded by Claude against the criteria of their question.

Claude says which criteria an answer meets, with a comment for the student; the app
concludes, so that a verdict never depends on how a language model counts. When Claude
cannot answer, the local model grades instead (D6), and its grading is provisional.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from typing import Any, Self

from bosh_mow.ai.gateway import EngineTimeout, EngineUnavailable, Gateway, InvalidAnswer
from bosh_mow.ai.schemas import T6Answer

GRADING_PROMPT = "t6_v1"


@dataclass(frozen=True)
class OpenQuestion:
    """What grading an answer needs: the question, its model answer, the criteria that
    a right answer meets, and the errors students often make on it."""

    statement: str
    expected_answer: str
    criteria: list[str]
    frequent_errors: list[str]

    @classmethod
    def of(cls, statement: str, content: dict[str, Any]) -> Self:
        """The question to grade, from the content of an open question (T2)."""
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
    concludes."""
    reply = gateway.ask(
        GRADING_PROMPT,
        {
            "question": question.statement,
            "expected_answer": question.expected_answer,
            "criteria": question.criteria,
            "frequent_errors": question.frequent_errors,
            "answer": answer,
        },
        T6Answer,
        check=lambda reply: check_grading(reply, len(question.criteria)),
    )
    results = [
        CriterionResult(criterion, result.met, result.comment.strip())
        for criterion, result in zip(question.criteria, reply.criteria, strict=True)
    ]
    return OpenGrading(
        results, reply.comment.strip(), verdict([result.met for result in results])
    )


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
