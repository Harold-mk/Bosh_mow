"""Local HTTP API used by the interface."""

from fastapi import FastAPI

from bosh_mow import __version__

app = FastAPI(title="Bosh mow", version=__version__)


@app.get("/api/health")
def health() -> dict[str, str]:
    """Tell the interface that the backend is running."""
    return {"status": "ok", "version": __version__}
