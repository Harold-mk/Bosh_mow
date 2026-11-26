"""Tests of the local model adapter (D6), against a fake Ollama server: the tests never
call a real model."""

import json
import threading
import time
from collections.abc import Callable, Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest

from bosh_mow.ai.gateway import EngineTimeout, EngineUnavailable
from bosh_mow.ai.ollama import OllamaEngine

SCHEMA = {"type": "object", "properties": {"met": {"type": "boolean"}}}

type Reply = Callable[[dict[str, Any]], tuple[int, str]]


class FakeOllama:
    """A local server that answers /api/chat as told, and keeps what it was asked."""

    def __init__(self) -> None:
        self.asked: list[dict[str, Any]] = []
        self.reply: Reply = answering("{}")
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                fake.asked.append({"path": self.path, **body})
                status, text = fake.reply(body)
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(text.encode("utf-8"))

            def log_message(self, *args: object) -> None:  # quiet
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"


@pytest.fixture
def ollama() -> Iterator[FakeOllama]:
    fake = FakeOllama()
    thread = threading.Thread(target=fake.server.serve_forever, daemon=True)
    thread.start()
    yield fake
    fake.server.shutdown()
    fake.server.server_close()


def answering(content: str) -> Reply:
    return lambda body: (200, json.dumps({"message": {"content": content}}))


def test_the_local_model_answers_with_the_json_of_the_schema(
    ollama: FakeOllama,
) -> None:
    ollama.reply = answering('{"met": true}')

    answer = OllamaEngine(url=ollama.url).run("Grade this.", SCHEMA)

    assert answer == {"met": True}
    (asked,) = ollama.asked
    assert asked["path"] == "/api/chat"
    assert asked["model"] == "qwen3.5:4b"
    assert asked["format"] == SCHEMA  # the answer is held to the schema of the task
    assert (asked["stream"], asked["think"]) == (False, False)
    assert asked["messages"][-1] == {"role": "user", "content": "Grade this."}


def test_an_answer_that_is_not_json_is_rejected_by_the_gateway(
    ollama: FakeOllama,
) -> None:
    ollama.reply = answering("Sure! Here is my grading.")

    assert OllamaEngine(url=ollama.url).run("Grade this.", SCHEMA) == {}


def test_a_model_that_ollama_does_not_have_is_unavailable(ollama: FakeOllama) -> None:
    ollama.reply = lambda body: (404, '{"error": "model not found"}')

    with pytest.raises(EngineUnavailable, match="model not found"):
        OllamaEngine(url=ollama.url).run("Grade this.", SCHEMA)


def test_ollama_not_started_is_unavailable(ollama: FakeOllama) -> None:
    url = ollama.url
    ollama.server.shutdown()
    ollama.server.server_close()

    with pytest.raises(EngineUnavailable, match="pas lancé"):
        OllamaEngine(url=url).run("Grade this.", SCHEMA)


def test_a_model_too_slow_times_out(ollama: FakeOllama) -> None:
    def slow(body: dict[str, Any]) -> tuple[int, str]:
        time.sleep(1)
        return 200, json.dumps({"message": {"content": "{}"}})

    ollama.reply = slow

    with pytest.raises(EngineTimeout):
        OllamaEngine(url=ollama.url, timeout_seconds=0.2).run("Grade this.", SCHEMA)


def test_the_local_model_does_not_read_images() -> None:
    with pytest.raises(EngineUnavailable, match="images"):
        OllamaEngine().run("Describe this page.", SCHEMA, [b"png"])
