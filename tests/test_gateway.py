"""Tests of the AI gateway: checked answers, a single retry, the log of every call."""

import json
from pathlib import Path
from typing import Any

import pytest
from fake_ai import FakeEngine
from pydantic import BaseModel

from bosh_mow.ai.gateway import EngineUnavailable, Gateway, InvalidAnswer


class Answer(BaseModel):
    word: str
    count: int


def make_gateway(
    tmp_path: Path, *answers: dict[str, Any] | Exception
) -> tuple[Gateway, FakeEngine]:
    prompts = tmp_path / "prompts"
    prompts.mkdir()
    (prompts / "demo_v1.md").write_text("Give a word and a count.", encoding="utf-8")
    engine = FakeEngine(list(answers))
    return Gateway(engine, tmp_path / "logs" / "ai_calls.jsonl", prompts), engine


def logged(tmp_path: Path) -> list[dict[str, Any]]:
    lines = (tmp_path / "logs" / "ai_calls.jsonl").read_text(encoding="utf-8")
    return [json.loads(line) for line in lines.splitlines()]


def test_valid_answer_is_accepted_and_logged(tmp_path: Path) -> None:
    gateway, engine = make_gateway(tmp_path, {"word": "chat", "count": 2})

    answer = gateway.ask("demo_v1", {"subject": "Économétrie"}, Answer)

    assert answer == Answer(word="chat", count=2)
    assert engine.prompts[0].startswith("Give a word and a count.")
    assert '"subject": "Économétrie"' in engine.prompts[0]
    [entry] = logged(tmp_path)
    assert (entry["prompt"], entry["engine"], entry["outcome"]) == (
        "demo_v1",
        "fake",
        "accepted",
    )


def test_invalid_answer_is_asked_again_once_with_the_reasons(tmp_path: Path) -> None:
    gateway, engine = make_gateway(
        tmp_path, {"word": "chat"}, {"word": "chat", "count": 2}
    )

    answer = gateway.ask("demo_v1", {}, Answer)

    assert answer.count == 2
    assert "rejected" in engine.prompts[1]
    assert "count: Field required" in engine.prompts[1]
    assert [entry["outcome"] for entry in logged(tmp_path)] == ["rejected", "accepted"]


def test_answer_rejected_twice_fails(tmp_path: Path) -> None:
    gateway, _ = make_gateway(tmp_path, {"word": "chat"}, {"count": "many"})

    with pytest.raises(InvalidAnswer):
        gateway.ask("demo_v1", {}, Answer)

    assert [entry["outcome"] for entry in logged(tmp_path)] == ["rejected", "rejected"]


def test_rules_of_the_task_are_checked_too(tmp_path: Path) -> None:
    gateway, engine = make_gateway(
        tmp_path, {"word": "chat", "count": 0}, {"word": "chat", "count": 3}
    )

    answer = gateway.ask(
        "demo_v1",
        {},
        Answer,
        check=lambda answer: [] if answer.count > 0 else ["count must be positive"],
    )

    assert answer.count == 3
    assert "count must be positive" in engine.prompts[1]


def test_unavailable_engine_is_logged_and_reported(tmp_path: Path) -> None:
    gateway, _ = make_gateway(tmp_path, EngineUnavailable("Limite du forfait atteinte"))

    with pytest.raises(EngineUnavailable, match="Limite du forfait"):
        gateway.ask("demo_v1", {}, Answer)

    assert [entry["outcome"] for entry in logged(tmp_path)] == ["unavailable"]
