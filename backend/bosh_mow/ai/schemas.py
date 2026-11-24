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


class T11Answer(BaseModel):
    """T11: the description of a page whose content is mostly in images."""

    page: int
    description: str
    elements: list[str]  # the visible parts: axes, curves, legends, labels…
    to_check: str | None  # what is unreadable or ambiguous, never in the description
