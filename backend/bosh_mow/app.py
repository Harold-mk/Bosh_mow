"""Start the app: the AI worker and the local API server in threads, then the window."""

import argparse
import mimetypes
import socket
import threading
import time
from contextlib import closing
from pathlib import Path

import uvicorn
import webview
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from bosh_mow.ai.claude import ClaudeEngine
from bosh_mow.ai.gateway import Gateway
from bosh_mow.ai.tasks import start_worker
from bosh_mow.api import create_app
from bosh_mow.content import preparation
from bosh_mow.db.connection import connect
from bosh_mow.db.migrate import apply_migrations
from bosh_mow.paths import default_data_folder
from bosh_mow.subjects import descriptions, proposal

HOST = "127.0.0.1"
# In --dev mode the window shows the Vite dev server, which forwards /api to this
# fixed port (see frontend/vite.config.ts).
DEV_API_PORT = 8765
DEV_FRONTEND_URL = "http://localhost:5173"
FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


def serve_frontend(api: FastAPI, folder: Path) -> None:
    """Serve the built interface. Its .mjs files, such as the worker of PDF.js, go as
    JavaScript: Windows may know them as text, and a browser then refuses them."""
    mimetypes.add_type("text/javascript", ".mjs")
    api.mount("/", StaticFiles(directory=folder, html=True))


class WindowApi:
    """What the interface may ask of its window, as window.pywebview.api in JavaScript:
    a study session runs in full screen (R16)."""

    def __init__(self) -> None:
        self._fullscreen = False

    def fullscreen(self, on: bool) -> None:
        if on != self._fullscreen:
            webview.windows[0].toggle_fullscreen()
            self._fullscreen = on


def main() -> None:
    """Prepare the database, start the worker and the API server, open the window."""
    parser = argparse.ArgumentParser(prog="bosh_mow")
    parser.add_argument(
        "--dev", action="store_true", help="show the Vite dev server (npm run dev)"
    )
    dev = parser.parse_args().dev

    folder = default_data_folder()
    with closing(connect(folder.database)) as connection:
        apply_migrations(connection)
    api = create_app(folder)

    if dev:
        port, url = DEV_API_PORT, DEV_FRONTEND_URL
    else:
        if not FRONTEND_DIST.is_dir():
            raise SystemExit(
                "frontend/dist is missing: run `npm run build` in frontend/ first."
            )
        serve_frontend(api, FRONTEND_DIST)
        port = free_port()
        url = f"http://{HOST}:{port}/"

    # The worker ends with the app; a task cut short is run again at the next start.
    gateway = Gateway(ClaudeEngine(), folder.ai_log)
    handlers = {
        proposal.TASK: proposal.proposal_handler(gateway),
        descriptions.TASK: descriptions.description_handler(gateway, folder.resources),
        preparation.NOTIONS_TASK: preparation.notions_handler(gateway),
        preparation.QUESTIONS_TASK: preparation.questions_handler(gateway),
    }
    start_worker(folder.database, handlers, threading.Event())
    start_server(api, port)
    webview.create_window("Bosh mow", url, js_api=WindowApi())
    webview.start()  # returns when the window is closed, which ends the app


def free_port() -> int:
    """Return a TCP port that is free on this computer."""
    with socket.socket() as sock:
        sock.bind((HOST, 0))  # port 0: the system picks a free port
        return sock.getsockname()[1]


def start_server(api: FastAPI, port: int) -> None:
    """Run the API server in a thread and wait until it accepts requests."""
    server = uvicorn.Server(uvicorn.Config(api, host=HOST, port=port))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        if not thread.is_alive():
            raise SystemExit(f"The local server could not start on port {port}.")
        time.sleep(0.05)
