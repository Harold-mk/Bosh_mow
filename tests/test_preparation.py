"""Tests of the preparation of a chapter: its notions (T1 pass 2), then the questions on
each validated notion (T2)."""

import sqlite3
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest
from fake_ai import FakeEngine

from bosh_mow.ai.gateway import EngineUnavailable, Gateway
from bosh_mow.ai.schemas import T1Pass2Answer, T2Answer
from bosh_mow.ai.tasks import add_task, run_next_task
from bosh_mow.content.preparation import (
    NOTIONS_TASK,
    QUESTIONS_TASK,
    ChapterFile,
    QuestionsState,
    check_notions,
    check_questions,
    notions_handler,
    preparation_state,
    prepare_notions,
    questions_handler,
    questions_state,
    request_preparation,
    request_questions,
    to_questions,
    validate_notions,
)
from bosh_mow.content.repository import (
    NewNotion,
    get_notions,
    get_questions,
    save_notions,
)
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


def notion(file: int = 1, pages: tuple[int, int] = (1, 6)) -> dict[str, Any]:
    return {
        "title": "Variance d'un échantillon",
        "summary": "Pourquoi diviser par n − 1.",
        "file": file,
        "first_page": pages[0],
        "last_page": pages[1],
    }


def notions(*proposed: dict[str, Any]) -> dict[str, Any]:
    """An answer of T1 pass 2."""
    return {"notions": list(proposed) or [notion()], "boundary_alert": None}


def questions(statements: list[str] = STATEMENTS) -> dict[str, Any]:
    """An answer of T2."""
    return {"questions": seven(statements)}


def fake_gateway(tmp_path: Path, *answers: dict[str, Any]) -> Gateway:
    return Gateway(FakeEngine([*answers]), tmp_path / "log")


def notion_problems(raw: dict[str, Any]) -> list[str]:
    return check_notions(T1Pass2Answer.model_validate(raw), FILES)


def question_problems(raw: dict[str, Any], existing: tuple[str, ...] = ()) -> list[str]:
    """The problems of the questions of a notion of pages 1 to 6."""
    return check_questions(T2Answer.model_validate(raw), 1, 6, existing)


# The rules of T1 pass 2


def test_notions_that_keep_the_rules_pass() -> None:
    assert notion_problems(notions(notion(), notion(file=2, pages=(1, 4)))) == []


def test_one_notion_at_least() -> None:
    assert notion_problems({"notions": [], "boundary_alert": None}) == [
        "Give at least one notion."
    ]


def test_r4_a_notion_stays_in_the_pages_of_the_chapter() -> None:
    assert notion_problems(notions(notion(file=3))) == [
        "Notion 1 uses file 3, which is not in the chapter."
    ]
    assert notion_problems(notions(notion(pages=(19, 22)))) == [
        "Notion 1: pages 19 to 22 are not in the chapter,"
        " which has pages 1 to 20 of file 1."
    ]


def test_r13_a_notion_is_read_in_10_minutes_at_most() -> None:
    assert notion_problems(notions(notion(pages=(1, 7)))) == [
        "Notion 1 has 7 pages: 6 at most, to be read in 10 minutes."
    ]


# The rules of T2


def test_questions_that_keep_the_rules_pass() -> None:
    assert question_problems(questions()) == []


def test_a_notion_has_the_seven_questions_of_the_contract() -> None:
    raw = questions()
    del raw["questions"][0]  # one pretest less
    raw["questions"].append(mcq("Which value has the largest deviation?"))

    assert question_problems(raw) == [
        "The notion needs 2 pretest MCQs, not 1.",
        "The notion needs 3 review MCQs, not 4.",
    ]


def test_a_pretest_is_an_mcq() -> None:
    raw = questions()
    raw["questions"][6]["role"] = "pretest"  # the open question

    assert question_problems(raw) == [
        "The notion needs 1 open « why? » question, not 0.",
        "Question 7: a pretest is an MCQ.",
    ]


def test_an_mcq_has_3_or_4_options_and_a_single_correct_one() -> None:
    raw = questions()
    options = raw["questions"][2]["options"]
    del options[2]
    options[1]["correct"] = True

    assert question_problems(raw) == [
        "Question 3: an MCQ has 3 or 4 options, not 2.",
        "Question 3: an MCQ has a single correct option, not 2.",
    ]


def test_every_option_is_explained() -> None:
    raw = questions()
    raw["questions"][2]["options"][1]["explanation"] = " "

    assert question_problems(raw) == ["Question 3: every option needs its explanation."]


def test_the_other_formats_have_what_their_correction_needs() -> None:
    raw = questions()
    value, why = raw["questions"][5:]
    value["value"] = None
    why["criteria"] = ["mentions extreme values"]

    assert question_problems(raw) == [
        "Question 6: a value question needs its value.",
        "Question 7: an open question needs 2 to 4 criteria, not 1.",
    ]


def test_a_question_asks_a_single_thing() -> None:
    raw = questions()
    raw["questions"][3]["statement"] = (
        "(a) Compute the mean. (b) Compute the variance of 2, 4 and 6."
    )

    assert question_problems(raw) == [
        "Question 4 asks several things: one idea per question, without (a), (b)."
    ]


def test_difficulty_is_1_2_or_3() -> None:
    raw = questions()
    raw["questions"][2]["difficulty"] = 5

    assert question_problems(raw) == ["Question 3: the difficulty is 1, 2 or 3, not 5."]


def test_r4_a_question_stays_in_the_pages_of_its_notion() -> None:
    raw = questions()
    raw["questions"][2].update(first_page=5, last_page=8)

    assert question_problems(raw) == [
        "Question 3: pages 5 to 8 are not in the notion, pages 1 to 6."
    ]


def test_no_question_repeats_an_existing_one_nor_another() -> None:
    assert question_problems(
        questions(), existing=("What is the sample variance of 2, 4, and 6?",)
    ) == [
        "Question 6 is too close to an existing question: "
        "« What is the sample variance of 2, 4, and 6? »."
    ]
    raw = questions()
    raw["questions"][3]["statement"] = raw["questions"][2]["statement"]
    assert question_problems(raw) == ["Question 4 is too close to question 3."]


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


def propose_notions(
    db: sqlite3.Connection, tmp_path: Path, chapter_id: int, answer: dict[str, Any]
) -> None:
    """Ask for the notions of a chapter and let the fake AI give `answer`."""
    request_preparation(db, chapter_id)
    gateway = fake_gateway(tmp_path, answer)
    assert run_next_task(db, {NOTIONS_TASK: notions_handler(gateway)}, NOW)


def test_the_notions_are_asked_with_the_pages_and_the_objectives(
    db: sqlite3.Connection, tmp_path: Path
) -> None:
    first, _ = make_chapters(db)
    describe(db, 3, "Une boîte à moustaches : médiane, quartiles et extrêmes.")
    engine = FakeEngine([notions()])

    answer = prepare_notions(db, Gateway(engine, tmp_path / "log"), first)

    assert answer == T1Pass2Answer.model_validate(notions())
    sent = engine.prompts[0]
    assert '"text": "Texte de la page 6."' in sent
    assert "Texte de la page 7." not in sent  # another chapter
    assert (
        '"description": "Une boîte à moustaches : médiane, quartiles et extrêmes."'
        in sent
    )
    assert "Être capable de mesurer la dispersion" in sent


def test_r38_the_notions_wait_for_the_descriptions_of_their_pages(
    db: sqlite3.Connection, tmp_path: Path
) -> None:
    first, _ = make_chapters(db)
    add_task(db, "t11", {"resource_id": 1, "page": 3})  # not described yet
    engine = FakeEngine([notions()])

    with pytest.raises(EngineUnavailable, match="descriptions"):
        prepare_notions(db, Gateway(engine, tmp_path / "log"), first)

    assert engine.prompts == []  # Claude was not asked


def test_the_notions_are_asked_in_the_background_and_followed(
    db: sqlite3.Connection, tmp_path: Path
) -> None:
    first, _ = make_chapters(db)
    assert preparation_state(db, first) is None

    request_preparation(db, first)
    request_preparation(db, first)  # already asked: not asked twice

    state = preparation_state(db, first)
    assert state is not None
    assert (state.status, state.notions) == ("pending", [])
    alert = {**notions(), "boundary_alert": "La page 6 annonce déjà les quartiles."}
    gateway = fake_gateway(tmp_path, alert)
    assert run_next_task(db, {NOTIONS_TASK: notions_handler(gateway)}, NOW)
    state = preparation_state(db, first)
    assert state is not None
    assert state.status == "done"
    assert state.notions == [
        NewNotion("Variance d'un échantillon", "Pourquoi diviser par n − 1.", 1, 1, 6)
    ]
    assert state.boundary_alert == "La page 6 annonce déjà les quartiles."


def test_r3_validated_notions_get_their_questions_from_claude(
    db: sqlite3.Connection, tmp_path: Path
) -> None:
    first, second = make_chapters(db)
    existing = to_questions(T2Answer.model_validate(questions(OTHER_STATEMENTS)))
    save_notions(db, second, [NewNotion("Quartiles", "…", 1, 7, 12, existing)])
    propose_notions(db, tmp_path, first, notions(notion(pages=(1, 3))))

    validate_notions(db, first, [" Variance "])

    (variance,) = get_notions(db, first)
    assert (variance.title, get_questions(db, variance.id)) == ("Variance", [])
    assert questions_state(db, variance.id) == QuestionsState("pending", None)
    engine = FakeEngine([questions()])
    handlers = {QUESTIONS_TASK: questions_handler(Gateway(engine, tmp_path / "log"))}
    assert run_next_task(db, handlers, NOW)
    assert questions_state(db, variance.id) == QuestionsState("done", None)
    saved = get_questions(db, variance.id)
    assert [question.statement for question in saved] == STATEMENTS
    assert saved[0].content["options"][0]["correct"] is True
    sent = engine.prompts[0]
    assert '"text": "Texte de la page 2."' in sent
    assert "Texte de la page 4." not in sent  # another notion
    assert "How is the interquartile range computed from the quartiles?" in sent

    request_questions(db, variance.id)  # it has them: not asked again
    assert not run_next_task(db, handlers, NOW)


def test_questions_that_break_the_rules_twice_can_be_asked_again(
    db: sqlite3.Connection, tmp_path: Path
) -> None:
    first, _ = make_chapters(db)
    propose_notions(db, tmp_path, first, notions())
    validate_notions(db, first, ["Variance"])
    (variance,) = get_notions(db, first)
    wrong = questions()
    del wrong["questions"][0]  # one pretest less
    gateway = fake_gateway(tmp_path, wrong, wrong)

    run_next_task(db, {QUESTIONS_TASK: questions_handler(gateway)}, NOW)

    state = questions_state(db, variance.id)
    assert state is not None
    assert state.status == "failed"
    assert get_questions(db, variance.id) == []
    request_questions(db, variance.id)
    assert questions_state(db, variance.id) == QuestionsState("pending", None)


def test_a_proposal_of_the_first_version_is_validated_with_its_questions(
    db: sqlite3.Connection,
) -> None:
    """Before, a single call per chapter gave the notions and their questions."""
    first, _ = make_chapters(db)
    combined = {"notions": [{**notion(), "questions": seven(STATEMENTS)}]}
    add_task(db, QUESTIONS_TASK, {"chapter_id": first})
    run_next_task(
        db,
        {QUESTIONS_TASK: lambda _, __: {**combined, "boundary_alert": None}},
        NOW,
    )

    validate_notions(db, first, ["Variance"])

    (variance,) = get_notions(db, first)
    assert len(get_questions(db, variance.id)) == 7
    assert questions_state(db, variance.id) is None  # nothing more to ask
