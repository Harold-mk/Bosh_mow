"""Tests of the start of the app: how the built interface is served."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from bosh_mow.app import serve_frontend


def test_the_worker_of_the_reader_is_served_as_javascript(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<!doctype html>", encoding="utf-8")
    (tmp_path / "pdf.worker.min.mjs").write_text("export {}", encoding="utf-8")
    api = FastAPI()
    serve_frontend(api, tmp_path)

    response = TestClient(api).get("/pdf.worker.min.mjs")

    assert response.headers["content-type"].startswith("text/javascript")
