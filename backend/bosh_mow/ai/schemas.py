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


class T2Notion(BaseModel):
    """A notion: one idea studied in 10 minutes at most, on pages of one file (R13)."""

    title: str  # in French
    summary: str  # one line, in French
    file: int
    first_page: int
    last_page: int
    questions: list[T2Question]


class T2Answer(BaseModel):
    """T1 pass 2 and T2: the notions of a chapter and the questions on each notion."""

    notions: list[T2Notion]
    boundary_alert: str | None  # if the bounds of the chapter seem misplaced


class T11Answer(BaseModel):
    """T11: the description of a page whose content is mostly in images."""

    page: int
    description: str
    elements: list[str]  # the visible parts: axes, curves, legends, labels…
    to_check: str | None  # what is unreadable or ambiguous, never in the description
