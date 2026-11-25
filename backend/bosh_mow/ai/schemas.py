"""Output schemas of the AI tasks (docs/contrats-ia.md), with their keys in English.

A schema fixes the shape of an answer. The rules that a shape cannot express (counts,
references, page coverage) are checked by the module that asks the task.
"""

from typing import Literal

from pydantic import BaseModel


class T1Source(BaseModel):
    """A range of pages of one imported file, given by the file's id."""

    file: int
    first_page: int
    last_page: int


class T1Chapter(BaseModel):
    title: str
    role: Literal["core", "secondary"]
    sources: list[T1Source]
    objectives: list[int]  # numbers of the objectives it teaches, from 1


class T1Answer(BaseModel):
    """T1, pass 1: the objectives, chapters and glossary proposed for a new subject."""

    objectives: list[str]  # « Être capable de… »
    chapters: list[T1Chapter]  # in the order of study
    glossary: list[str]  # technical terms that are never translated (T9)


class T2Option(BaseModel):
    """An option of an MCQ; its explanation, in French, is shown after the answer."""

    text: str
    correct: bool
    explanation: str


class T2Question(BaseModel):
    """A question on a single idea (R5). The fields after `last_page` depend on the
    format: options for an MCQ; value, tolerance and explanation for a value;
    accepted answers and explanation for a short answer; expected answer, criteria and
    frequent errors for an open answer."""

    role: Literal["pretest", "review"]
    type: Literal["concept", "calculation", "code"]
    level: Literal["recall", "explain", "apply", "analyze"]  # R5
    format: Literal["mcq", "value", "short", "open"]
    difficulty: int  # 1 to 3
    statement: str  # in English (R5)
    first_page: int
    last_page: int
    options: list[T2Option] | None = None
    value: float | None = None
    tolerance: float | None = None  # relative: 0.01 for 1 %
    accepted: list[str] | None = None
    explanation: str | None = None  # in French
    expected_answer: str | None = None
    criteria: list[str] | None = None
    frequent_errors: list[str] | None = None


class T2Answer(BaseModel):
    """T2: the 7 questions of one notion."""

    questions: list[T2Question]


class T1Pass2Notion(BaseModel):
    """A notion: one idea studied in 10 minutes at most, on pages of one file (R13)."""

    title: str  # in French
    summary: str  # one line, in French
    file: int
    first_page: int
    last_page: int


class T1Pass2Answer(BaseModel):
    """T1 pass 2: the notions of a chapter."""

    notions: list[T1Pass2Notion]
    boundary_alert: str | None  # if the bounds of the chapter seem misplaced


class CombinedT2Notion(T1Pass2Notion):
    questions: list[T2Question]


class CombinedT2Answer(BaseModel):
    """The first version of lot 2: notions and their questions in a single call per
    chapter, too long for big chapters. Its proposals are still read."""

    notions: list[CombinedT2Notion]
    boundary_alert: str | None


class T6Criterion(BaseModel):
    """Whether an answer meets one criterion of its question, and why."""

    met: bool
    comment: str  # in French, one sentence for the student


class T6Answer(BaseModel):
    """T6: an open answer graded against the criteria of its question. The app
    concludes from the criteria met; Claude never gives the verdict itself."""

    criteria: list[T6Criterion]  # one per criterion, in their order
    comment: str  # in French: what is solid, then what to add or correct first


class T11Answer(BaseModel):
    """T11: the description of a page whose content is mostly in images."""

    page: int
    description: str
    elements: list[str]  # the visible parts: axes, curves, legends, labels…
    to_check: str | None  # what is unreadable or ambiguous, never in the description
