# Bosh mow

A personal, local and free desktop app to learn your courses: import your course PDFs,
answer AI-generated questions, review them with spaced repetition and test yourself with exams.

Everything runs on your computer and the interface is in French. Built with Python (FastAPI,
SQLite), React + TypeScript and pywebview. Spaced repetition uses
[FSRS](https://github.com/open-spaced-repetition/py-fsrs); the AI features use Claude
(through Claude Code) and a local model with Ollama.

> **Status:** early development. The first part is ready: creating a subject from its files,
> with objectives and chapters proposed by Claude. Studying comes next.

## What it does today

- **First launch:** three study habits, your study time per day (weekdays and weekends) and
  an "if… then…" plan that anchors your daily session.
- **New subject:** give it a name and an exam date, then drop your books (PDF) and notes
  (Markdown). Each file is read on your computer, without AI: its text, its outline
  (bookmarks, Markdown titles, or titles guessed from their size) and the pages that are
  mostly images.
- **Claude's proposal:** from the outline, or the text, of your files, Claude proposes up to
  5 objectives ("Être capable de…") and a split into chapters that covers every page. You
  correct everything before it is saved: objectives, chapter titles, and which chapters are
  core or secondary. Each answer is checked against the rules of its task, and asked again
  once if it breaks one.
- **Without Claude:** when Claude is unavailable (offline, plan limit), you write your
  objectives yourself; the proposal comes later, when Claude is back.
- **Slides:** once the chapters are validated, Claude describes in text the pages that are
  mostly images or diagrams, in the background, so that the questions to come cover the
  whole course.
- **Your subjects:** the list of subjects, closest exam first, and the page of each subject
  with the days left until the exam, its objectives, chapters and documents.

Coming next: AI-generated questions and the daily review session (FSRS), grading,
exercises, exams, statistics and planning.

## How it works

- One Python app: a local FastAPI server, on 127.0.0.1 only, and a pywebview window that
  shows the React interface.
- Your data stays on your computer, in `%LOCALAPPDATA%\BoshMow`: the SQLite database, an
  untouched copy of each imported file, and a log of the AI calls.
- Claude is called through `claude -p` with your Claude subscription, never with an API
  key. It runs without any tool, settings or MCP server: it only sees what the app sends.
  AI tasks run in the background, one at a time, and wait while Claude is unavailable.
- Each AI task has a versioned prompt in [`prompts/`](prompts), a Pydantic output schema
  and automatic checks. The tests never call an AI: they use a fake one.

## Requirements

- Windows 10 or 11 with the Microsoft Edge WebView2 Runtime (preinstalled on Windows 11)
- Python 3.12 or newer
- Node.js 22.22 or newer
- [Claude Code](https://claude.com/claude-code), signed in with a Claude subscription, for
  the AI features. Later versions will also use [Ollama](https://ollama.com).

## Getting started

```powershell
# 1. Python environment
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"

# 2. Build the interface
cd frontend
npm install
npm run build
cd ..

# 3. Launch the app
python -m bosh_mow
```

## Development

Run the Vite dev server and the app in two terminals:

```powershell
cd frontend ; npm run dev     # terminal 1: interface with hot reload
python -m bosh_mow --dev      # terminal 2: app window pointing to the Vite server
```

Tests and code style:

```powershell
pytest
ruff check . ; ruff format .
```

## License

[MIT](LICENSE) © Harold Mokam

PDF files are read with [PyMuPDF](https://pymupdf.readthedocs.io), which is licensed
under the GNU AGPL-3.0 (or a commercial license from Artifex).
