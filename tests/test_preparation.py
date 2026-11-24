"""Tests of the preparation of a chapter: T1 pass 2 (notions) and T2 (questions)."""

import sqlite3
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest
from fake_ai import FakeEngine

from bosh_mow.ai.gateway import EngineUnavailable, Gateway
from bosh_mow.ai.schemas import T2Answer
from bosh_mow.ai.tasks import add_task, run_next_task
from bosh_mow.content.preparation import (
    TASK,
    ChapterFile,
    check_preparation,
    preparation_handler,
    preparation_state,
    prepare,
    request_preparation,
    to_notions,
)
from bosh_mow.content.repository import NewNotion, save_notions
from bosh_mow.subjects.repository import (
    Chapter,
    ChapterSource,
    Document,
    PageContent,
    activate_subject,
    add_resource,
    create_draft_subject,
)

FILES = [ChapterFile(1, 1, 20), ChapterFile(2, 1, 4)]
NOW = datetime(2026, 11, 24, 18, 0, tzinfo=UTC)
STATEMENTS = [
    "Why do we divide by n − 1 in the sample variance?",
    "What does a large standard deviation tell us about a dataset?",
    "Which measure of spread is expressed in the unit of the data?",
    "What happens to the sample variance when every value is doubled?",
    "Which estimator of the population variance is unbiased?",
    "What is the sample variance of 2, 4 and 6?",
    "Why is the median less sensitive than the mean to extreme values?",
]
OTHER_STATEMENTS = [
    "How is the interquartile range computed from the quartiles?",
    "Which share of the values lies below the first quartile?",
    "What does a box plot show between its two whiskers?",
    "Which quartile is also called the median of a series?",
    "When is the range a poor summary of the spread?",
    "What is the interquartile range of 1, 3, 5, 7, 9, 11, 13 and 15?",
    "Why can two series with the same mean have different spreads?",
]


def mcq(
    statement: str, role: str = "review", pages: tuple[int, int] = (2, 3)
) -> dict[str, Any]:
    return {
        "role": role,
        "type": "concept",
        "level": "explain",
        "format": "mcq",
        "difficulty": 2,
        "statement": statement,
        "first_page": pages[0],
        "last_page": pages[1],
        "options": [
            {
                "text": "Because one degree of freedom is lost",
                "correct": True,
                "explanation": "C'est ça.",
            },
            {
                "text": "It is a convention",
                "correct": False,
                "explanation": "Erreur fréquente.",
            },
            {
                "text": "To get the standard deviation",
                "correct": False,
                "explanation": "Non.",
            },
        ],
    }


def seven(statements: list[str]) -> list[dict[str, Any]]:
    """The seven questions of a notion (contract T2)."""
    value = {
        **mcq(statements[5]),
        "type": "calculation",
        "level": "apply",
        "format": "value",
        "options": None,
        "value": 4,
        "tolerance": 0.01,
        "explanation": "Moyenne 4, carrés des écarts 8, divisés par n − 1 = 2.",
    }
    why = {
        **mcq(statements[6]),
        "level": "analyze",
        "format": "open",
        "options": None,
        "expected_answer": "One extreme value moves the mean a lot, not the median.",
        "criteria": ["mentions extreme values", "explains the sensitivity of the mean"],
        "frequent_errors": ["says the median is always better"],
    }
    pretests = [mcq(statement, "pretest") for statement in statements[:2]]
    return [*pretests, *[mcq(statement) for statement in statements[2:5]], value, why]


def notion(
    statements: list[str] = STATEMENTS, file: int = 1, pages: tuple[int, int] = (1, 6)
) -> dict[str, Any]:
    return {
        "title": "Variance d'un échantillon",
        "summary": "Pourquoi diviser par n − 1.",
        "file": file,
        "first_page": pages[0],
        "last_page": pages[1],
        "questions": seven(statements),
    }


def preparation(*notions: dict[str, Any]) -> dict[str, Any]:
    return {"notions": list(notions) or [notion()], "boundary_alert": None}


def problems(raw: dict[str, Any], existing: tuple[str, ...] = ()) -> list[str]:
    return check_preparation(T2Answer.model_validate(raw), FILES, existing)


# The rules of T2


def test_a_preparation_that_keeps_the_rules_passes() -> None:
    assert (
        problems(preparation(notion(), notion(OTHER_STATEMENTS, file=2, pages=(1, 4))))
        == []
    )


def test_one_notion_at_least() -> None:
    assert problems({"notions": [], "boundary_alert": None}) == [
        "Give at least one notion."
    ]


def test_each_notion_has_the_seven_questions_of_the_contract() -> None:
    raw = preparation()
    del raw["notions"][0]["questions"][0]  # one pretest less
    raw["notions"][0]["questions"].append(mcq("Which value has the largest deviation?"))

    assert problems(raw) == [
        "Notion 1 needs 2 pretest MCQs, not 1.",
        "Notion 1 needs 3 review MCQs, not 4.",
    ]


def test_a_pretest_is_an_mcq() -> None:
    raw = preparation()
    raw["notions"][0]["questions"][0]["role"] = "pretest"
    raw["notions"][0]["questions"][6]["role"] = "pretest"  # the open question

    assert problems(raw) == [
        "Notion 1 needs 1 open « why? » question, not 0.",
        "Notion 1, question 7: a pretest is an MCQ.",
    ]


def test_an_mcq_has_3_or_4_options_and_a_single_correct_one() -> None:
    raw = preparation()
    options = raw["notions"][0]["questions"][2]["options"]
    del options[2]
    options[1]["correct"] = True

    assert problems(raw) == [
        "Notion 1, question 3: an MCQ has 3 or 4 options, not 2.",
        "Notion 1, question 3: an MCQ has a single correct option, not 2.",
    ]


def test_every_option_is_explained() -> None:
    raw = preparation()
    raw["notions"][0]["questions"][2]["options"][1]["explanation"] = " "

    assert problems(raw) == [
        "Notion 1, question 3: every option needs its explanation."
    ]


def test_the_other_formats_have_what_their_correction_needs() -> None:
    raw = preparation()
    value, why = raw["notions"][0]["questions"][5:]
    value["value"] = None
    why["criteria"] = ["mentions extreme values"]

    assert problems(raw) == [
        "Notion 1, question 6: a value question needs its value.",
        "Notion 1, question 7: an open question needs 2 to 4 criteria, not 1.",
    ]


def test_a_question_asks_a_single_thing() -> None:
    raw = preparation()
    raw["notions"][0]["questions"][3]["statement"] = (
        "(a) Compute the mean. (b) Compute the variance of 2, 4 and 6."
    )

    assert problems(raw) == [
        "Notion 1, question 4 asks several things:"
        " one idea per question, without (a), (b)."
    ]


def test_difficulty_is_1_2_or_3() -> None:
    raw = preparation()
    raw["notions"][0]["questions"][2]["difficulty"] = 5

    assert problems(raw) == [
        "Notion 1, question 3: the difficulty is 1, 2 or 3, not 5."
    ]


def test_r4_a_notion_stays_in_the_pages_of_the_chapter() -> None:
    assert problems(preparation(notion(file=3))) == [
        "Notion 1 uses file 3, which is not in the chapter."
    ]
    assert problems(preparation(notion(pages=(19, 22)))) == [
        "Notion 1: pages 19 to 22 are not in the chapter,"
        " which has pages 1 to 20 of file 1."
    ]


def test_r13_a_notion_is_read_in_10_minutes_at_most() -> None:
    assert problems(preparation(notion(pages=(1, 7)))) == [
        "Notion 1 has 7 pages: 6 at most, to be read in 10 minutes."
    ]


def test_r4_a_question_stays_in_the_pages_of_its_notion() -> None:
    raw = preparation()
    raw["notions"][0]["questions"][2].update(first_page=5, last_page=8)

    assert problems(raw) == [
        "Notion 1, question 3: pages 5 to 8 are not in its notion, pages 1 to 6."
    ]


def test_no_question_repeats_an_existing_one() -> None:
    assert problems(
        preparation(), existing=("What is the sample variance of 2, 4, and 6?",)
    ) == [
        "Notion 1, question 6 is too close to an existing question: "
        "« What is the sample variance of 2, 4, and 6? »."
    ]
    assert problems(preparation(notion(), notion(file=2, pages=(1, 4))))[0] == (
        "Notion 2, question 1 is too close to notion 1, question 1."
    )


# Asking Claude, with the fake AI


def make_chapters(db: sqlite3.Connection) -> tuple[int, int]:
    """A subject split into two chapters of a 12-page PDF: (chapter 1, chapter 2)."""
    subject_id = create_draft_subject(db, "Statistiques", date(2027, 1, 15))
    pages = [PageContent(f"Texte de la page {number}.") for number in range(1, 13)]
    pages[2] = PageContent("Boîte à moustaches", image_count=1)  # a diagram (T11)
    file_id = add_resource(
        db, subject_id, "stats.pdf", Document("pdf", pages, [], "none")
    )
    activate_subject(
        db,
        subject_id,
        ["Être capable de mesurer la dispersion", "Être capable de lire un résumé"],
        [
            Chapter("Dispersion", "core", [ChapterSource(file_id, 1, 6)], [1]),
            Chapter("Quartiles", "core", [ChapterSource(file_id, 7, 12)], [2]),
        ],
    )
    first, second = (
        row[0]
        for row in db.execute("SELECT id FROM chapter ORDER BY number").fetchall()
    )
    return first, second


def describe(db: sqlite3.Connection, page: int, text: str) -> None:
    db.execute(
        "INSERT INTO page_description (resource_id, number, description, elements)"
        " VALUES (1, ?, ?, '[]')",
        (page, text),
    )
    db.commit()


def test_prepare_sends_the_pages_the_objectives_and_the_existing_questions(
    db: sqlite3.Connection, tmp_path: Path
) -> None:
    first, second = make_chapters(db)
    describe(db, 3, "Une boîte à moustaches : médiane, quartiles et extrêmes.")
    save_notions(
        db,
        second,
        to_notions(
            T2Answer.model_validate(
                preparation(notion(OTHER_STATEMENTS, pages=(7, 12)))
            )
        ),
    )
    engine = FakeEngine([preparation()])

    answer = prepare(db, Gateway(engine, tmp_path / "log"), first)

    assert answer == T2Answer.model_validate(preparation())
    sent = engine.prompts[0]
    assert '"text": "Texte de la page 6."' in sent
    assert "Texte de la page 7." not in sent  # another chapter
    assert (
        '"description": "Une boîte à moustaches : médiane, quartiles et extrêmes."'
        in sent
    )
    assert "Être capable de mesurer la dispersion" in sent
    assert "How is the interquartile range computed from the quartiles?" in sent


def test_r38_prepare_waits_for_the_descriptions_of_its_pages(
    db: sqlite3.Connection, tmp_path: Path
) -> None:
    first, _ = make_chapters(db)
    add_task(db, "t11", {"resource_id": 1, "page": 3})  # not described yet
    engine = FakeEngine([preparation()])

    with pytest.raises(EngineUnavailable, match="descriptions"):
        prepare(db, Gateway(engine, tmp_path / "log"), first)

    assert engine.prompts == []  # Claude was not asked


def test_a_preparation_is_asked_in_the_background_and_followed(
    db: sqlite3.Connection, tmp_path: Path
) -> None:
    first, _ = make_chapters(db)
    assert preparation_state(db, first) is None

    request_preparation(db, first)
    request_preparation(db, first)  # already asked: not asked twice

    state = preparation_state(db, first)
    assert state is not None
    assert (state.status, state.notions) == ("pending", [])
    gateway = Gateway(FakeEngine([preparation()]), tmp_path / "log")
    assert run_next_task(db, {TASK: preparation_handler(gateway)}, NOW)
    state = preparation_state(db, first)
    assert state is not None
    assert state.status == "done"
    assert [notion.title for notion in state.notions] == ["Variance d'un échantillon"]
    assert isinstance(state.notions[0], NewNotion)
    assert len(state.notions[0].questions) == 7
    assert state.notions[0].questions[0].content["options"][0]["correct"] is True
