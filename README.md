# Bosh mow

A personal, local and free desktop app to learn your courses: import your course PDFs,
answer AI-generated questions, review them with spaced repetition and test yourself with exams.

Everything runs on your computer and the interface is in French. Built with Python (FastAPI,
SQLite), React + TypeScript and pywebview. Spaced repetition uses
[FSRS](https://github.com/open-spaced-repetition/py-fsrs); the AI features use Claude
(through Claude Code) and a local model with Ollama.

> **Status:** early development.

## Requirements

- Windows 10 or 11 with the Microsoft Edge WebView2 Runtime (preinstalled on Windows 11)
- Python 3.12 or newer
- Node.js 22 or newer

The AI features, coming in later versions, will also need [Ollama](https://ollama.com) and
[Claude Code](https://claude.com/claude-code) signed in with a Claude subscription.

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

Your courses and progress are stored in a local SQLite database,
`%LOCALAPPDATA%\BoshMow\bosh.db`, outside the repository.

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
