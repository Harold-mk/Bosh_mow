"""Tests of the local HTTP API."""

from fastapi.testclient import TestClient

from bosh_mow import __version__
from bosh_mow.api import app


def test_health_returns_status_and_version() -> None:
    response = TestClient(app).get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}
