"""Tests of T1, pass 1: what Claude receives, and the rules its proposal must keep."""

import sqlite3
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from fake_ai import FakeEngine
from pydantic import ValidationError

from bosh_mow.ai.gateway import Gateway
from bosh_mow.ai.schemas import T1Answer
from bosh_mow.subjects.proposal import (
    PAGE_START_CHARS,
    check_proposal,
    describe_file,
    propose,
)
from bosh_mow.subjects.repository import (
    Document,
    Heading,
    PageContent,
    Resource,
    add_resource,
    create_draft_subject,
)

FILES = [Resource(1, "stats.pdf", "pdf", 40), Resource(2, "notes.md", "markdown", 3)]


def proposal() -> dict[str, Any]:
    """An answer that keeps every rule of T1 for FILES."""
    return {
        "objectives": [
            "Être capable de calculer et d'interpréter une variance",
            "Être capable d'estimer un modèle de régression linéaire",
        ],
        "chapters": [
            {
                "title": "Variance et écart-type",
                "role": "core",
                "sources": [
                    {"file": 1, "first_page": 1, "last_page": 20},
                    {"file": 2, "first_page": 1, "last_page": 2},
                ],
                "objectives": [1],
            },
            {
                "title": "Régression linéaire",
                "role": "secondary",
                "sources": [
                    {"file": 1, "first_page": 21, "last_page": 40},
                    {"file": 2, "first_page": 3, "last_page": 3},
                ],
                "objectives": [2],
            },
        ],
        "glossary": ["p-value"],
    }


def problems(answer: dict[str, Any]) -> list[str]:
    return check_proposal(T1Answer.model_validate(answer), FILES)


# Objectives (R2)


def test_a_proposal_that_keeps_the_rules_passes() -> None:
    assert problems(proposal()) == []


def test_r2_five_objectives_at_most() -> None:
    answer = proposal()
    answer["objectives"] += [f"Être capable de traiter le cas {n}" for n in range(4)]
    answer["chapters"][1]["objectives"] += [3, 4, 5, 6]

    assert problems(answer) == ["Give 1 to 5 objectives, not 6."]


def test_r2_one_objective_at_least() -> None:
    answer = proposal()
    answer["objectives"] = []
    for chapter in answer["chapters"]:
        chapter["objectives"] = []

    assert problems(answer) == ["Give 1 to 5 objectives, not 0."]


@pytest.mark.parametrize(
    ("text", "accepted"),
    [
        ("Être capable de lire un tableau", True),
        ("Être capable d'estimer une moyenne", True),
        ("Être capable d’estimer une moyenne", True),
        ("Savoir lire un tableau", False),
        ("être capable de lire un tableau", False),
        ("Être capable de", False),
    ],
)
def test_r2_objectives_start_with_etre_capable_de(text: str, accepted: bool) -> None:
    answer = proposal()
    answer["objectives"][0] = text

    expected = [] if accepted else ["Objective 1 must start with « Être capable de »."]
    assert problems(answer) == expected


def test_each_objective_is_taught_by_a_chapter() -> None:
    answer = proposal()
    answer["chapters"][1]["objectives"] = [1]

    assert problems(answer) == ["Objective 2 is taught by no chapter."]


def test_a_chapter_refers_to_existing_objectives_only() -> None:
    answer = proposal()
    answer["chapters"][1]["objectives"] = [2, 3]

    assert problems(answer) == [
        "Chapter 2 refers to objective 3, which does not exist."
    ]


def test_a_chapter_lists_each_objective_once() -> None:
    answer = proposal()
    answer["chapters"][1]["objectives"] = [2, 2]

    assert problems(answer) == ["Chapter 2 lists objective 2 twice."]


# Chapters (R3)


def test_one_chapter_at_least() -> None:
    answer = proposal()
    answer["chapters"] = []

    assert "Give at least one chapter." in problems(answer)


def test_a_chapter_has_a_title() -> None:
    answer = proposal()
    answer["chapters"][0]["title"] = "  "

    assert problems(answer) == ["Chapter 1 has no title."]


def test_a_chapter_role_is_core_or_secondary() -> None:
    answer = proposal()
    answer["chapters"][0]["role"] = "important"

    with pytest.raises(ValidationError):
        T1Answer.model_validate(answer)


def test_a_chapter_has_pages() -> None:
    answer = proposal()
    answer["chapters"][1]["sources"] = []

    assert problems(answer) == [
        "Chapter 2 has no pages.",
        "No chapter covers pages 21 to 40 of stats.pdf (file 1).",
        "No chapter covers page 3 of notes.md (file 2).",
    ]


def test_a_chapter_uses_the_files_of_the_subject_only() -> None:
    answer = proposal()
    answer["chapters"][1]["sources"][1]["file"] = 3

    assert problems(answer) == [
        "Chapter 2 uses file 3, which does not exist.",
        "No chapter covers page 3 of notes.md (file 2).",
    ]


@pytest.mark.parametrize(("first", "last"), [(21, 41), (0, 40), (40, 21)])
def test_a_chapter_uses_pages_that_exist(first: int, last: int) -> None:
    answer = proposal()
    answer["chapters"][1]["sources"][0].update(first_page=first, last_page=last)

    assert problems(answer) == [
        f"Chapter 2 cannot cover pages {first} to {last} of stats.pdf (file 1),"
        " which has pages 1 to 40."
    ]


def test_a_chapter_takes_a_single_range_of_each_file() -> None:
    answer = proposal()
    answer["chapters"][0]["sources"][0]["last_page"] = 10
    answer["chapters"][0]["sources"].append(
        {"file": 1, "first_page": 11, "last_page": 20}
    )

    assert problems(answer) == [
        "Chapter 1 uses stats.pdf (file 1) twice: give a single range of pages"
        " per file."
    ]


# Coverage: each file without gap or overlap


def test_chapters_leave_no_gap_in_a_file() -> None:
    answer = proposal()
    answer["chapters"][1]["sources"][0]["first_page"] = 23

    assert problems(answer) == [
        "No chapter covers pages 21 to 22 of stats.pdf (file 1)."
    ]


def test_chapters_do_not_overlap() -> None:
    answer = proposal()
    answer["chapters"][1]["sources"][0]["first_page"] = 19

    assert problems(answer) == [
        "Chapters 1 and 2 both cover pages 19 to 20 of stats.pdf (file 1)."
    ]


def test_chapters_cover_a_file_up_to_its_last_page() -> None:
    answer = proposal()
    answer["chapters"][1]["sources"][0]["last_page"] = 38

    assert problems(answer) == [
        "No chapter covers pages 39 to 40 of stats.pdf (file 1)."
    ]


def test_chapters_cover_every_file() -> None:
    answer = proposal()
    for chapter in answer["chapters"]:
        chapter["sources"] = [s for s in chapter["sources"] if s["file"] != 2]

    assert problems(answer) == ["No chapter covers pages 1 to 3 of notes.md (file 2)."]


def test_chapters_can_be_studied_in_another_order_than_the_pages() -> None:
    answer = proposal()
    answer["chapters"].reverse()

    assert problems(answer) == []


# What Claude receives about each file (contract T1, input of pass 1)


def numbered_pages(count: int, text: str = "Texte de la page") -> list[PageContent]:
    return [PageContent(f"{text} {number}") for number in range(1, count + 1)]


def test_a_file_with_an_outline_is_sent_as_its_titles_only() -> None:
    headings = [Heading(1, "Variance", 1), Heading(2, "Écart-type", 12)]
    document = Document("pdf", numbered_pages(40), headings, "structure")

    assert describe_file(FILES[0], document) == {
        "id": 1,
        "name": "stats.pdf",
        "kind": "pdf",
        "page_count": 40,
        "outline": [
            {"level": 1, "title": "Variance", "page": 1},
            {"level": 2, "title": "Écart-type", "page": 12},
        ],
    }


def test_guessed_titles_are_sent_as_candidates() -> None:
    document = Document("pdf", numbered_pages(40), [Heading(1, "Variance", 3)], "fonts")

    described = describe_file(FILES[0], document)

    assert described["title_candidates"] == [
        {"level": 1, "title": "Variance", "page": 3}
    ]
    assert "outline" not in described


@pytest.mark.parametrize(("count", "key"), [(49, "page_texts"), (50, "page_starts")])
def test_without_structure_a_file_of_less_than_50_pages_is_sent_whole(
    count: int, key: str
) -> None:
    document = Document("pdf", numbered_pages(count), [], "none")

    described = describe_file(Resource(3, "cours.pdf", "pdf", count), document)

    assert [page["page"] for page in described[key]] == list(range(1, count + 1))
    assert described[key][-1]["text"] == f"Texte de la page {count}"


def test_the_whole_text_is_sent_without_blank_lines_or_extra_spaces() -> None:
    page = PageContent("  Chapitre 3\n\n Inférence   et tests \n  Le test de Student\n")
    document = Document("pdf", [page], [], "none")

    described = describe_file(Resource(3, "cours.pdf", "pdf", 1), document)

    assert described["page_texts"] == [
        {"page": 1, "text": "Chapitre 3\nInférence et tests\nLe test de Student"}
    ]


def test_a_long_file_without_structure_is_sent_as_the_start_of_each_page() -> None:
    text = "Chapitre 3\n\nInférence et tests\n" + "Le test de Student. " * 40
    document = Document("pdf", [PageContent(text)] * 60, [], "none")

    starts = describe_file(Resource(3, "cours.pdf", "pdf", 60), document)["page_starts"]

    assert len(starts) == 60
    assert starts[0]["text"].startswith("Chapitre 3\nInférence et tests\nLe test")
    assert len(starts[0]["text"]) == PAGE_START_CHARS


# Asking Claude, with the fake AI


def make_subject(db: sqlite3.Connection) -> int:
    """A draft subject with the two FILES (ids 1 and 2 in a new database)."""
    subject_id = create_draft_subject(db, "Statistiques", date(2027, 1, 15))
    book = Document(
        "pdf",
        numbered_pages(40),
        [Heading(1, "Variance", 1), Heading(1, "Régression", 21)],
        "structure",
    )
    titles = ["Variance", "Écart-type", "Régression"]
    notes = Document(
        "markdown",
        [PageContent(f"# {title}") for title in titles],
        [Heading(1, title, page) for page, title in enumerate(titles, start=1)],
        "structure",
    )
    ids = [
        add_resource(db, subject_id, "stats.pdf", book),
        add_resource(db, subject_id, "notes.md", notes),
    ]
    assert ids == [file.id for file in FILES]
    return subject_id


def test_propose_sends_the_subject_and_its_files(
    db: sqlite3.Connection, tmp_path: Path
) -> None:
    subject_id = make_subject(db)
    engine = FakeEngine([proposal()])

    answer = propose(db, Gateway(engine, tmp_path / "ai_calls.jsonl"), subject_id)

    assert answer == T1Answer.model_validate(proposal())
    sent = engine.prompts[0]
    assert '"subject": "Statistiques"' in sent
    assert '"exam_date": "2027-01-15"' in sent
    assert '"title": "Écart-type"' in sent


def test_propose_asks_again_when_the_split_breaks_a_rule(
    db: sqlite3.Connection, tmp_path: Path
) -> None:
    subject_id = make_subject(db)
    wrong = proposal()
    wrong["chapters"][1]["sources"][0]["first_page"] = 23
    engine = FakeEngine([wrong, proposal()])

    answer = propose(db, Gateway(engine, tmp_path / "ai_calls.jsonl"), subject_id)

    assert answer == T1Answer.model_validate(proposal())
    assert (
        "No chapter covers pages 21 to 22 of stats.pdf (file 1)." in engine.prompts[1]
    )


def test_propose_needs_imported_files(db: sqlite3.Connection, tmp_path: Path) -> None:
    subject_id = create_draft_subject(db, "Statistiques", date(2027, 1, 15))
    gateway = Gateway(FakeEngine([]), tmp_path / "ai_calls.jsonl")

    with pytest.raises(ValueError, match="no file"):
        propose(db, gateway, subject_id)
