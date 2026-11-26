# Bosh mow

A personal, local and free desktop app to learn your courses: import your course PDFs,
answer AI-generated questions, review them with spaced repetition and test yourself with exams.

Everything runs on your computer and the interface is in French. Built with Python (FastAPI,
SQLite), React + TypeScript and pywebview. Spaced repetition uses
[FSRS](https://github.com/open-spaced-repetition/py-fsrs); the AI features use Claude
(through Claude Code) and a local model with Ollama.

> **Status:** early development. The first three parts are ready: setting up a subject from
> its files, studying it with questions written by Claude and reviewed with spaced
> repetition, and grading every kind of answer, by the code or by Claude. Exercises and
> exams come next.

## What it does today

### Setting up a subject

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

### Studying

- **Notions and questions:** once the chapters are validated, Claude cuts the first chapter
  into notions, the ideas to learn, each with its pages. You validate them, renaming any
  title, then Claude writes the questions of each notion in the background. The next
  chapter is prepared when you start the last prepared one, or when you ask for it.
  "Signaler" removes a wrong question.
- **The daily review:** the questions due today, mixing your subjects, in a 15-minute
  full-screen session. You say how sure you were of each answer ("Sûr", "Hésitant", "Au
  hasard"): with its grading, this sets the next review date with FSRS. A missed question
  comes back later in the session; what is left after 15 minutes waits for the next day.
- **A new notion:** after the review, the next notion of the subject whose exam is closest:
  a warm-up question on a notion already learned, two pretest questions, a guided reading
  of its pages (the text is hidden after 10 minutes: you look for the answers from memory),
  a test of its five review questions, the "why?" one last, then a 5-minute break before
  the next notion.
- **Focus:** a "Ne pas déranger" check and full screen before each session, a parking for
  passing thoughts (P key) sorted at the end, and "J'ai décroché" when your mind wanders.
- **Home:** the session of the day, the questions due today and your successful days, the
  days when the minimum session was done; the sidebar shows today's minutes toward that
  15-minute minimum. No screen counts missed days or late questions: the app only warns
  before a second missed day in a row, and after an absence it proposes the minimum
  session alone.
- **Reader:** the original pages of your PDFs, with their outline, page navigation and
  zoom, opened from a subject or a chapter. From a correction ("Voir le cours") or the
  guided reading, it opens at the right page over the session, which waits underneath.

### Grading

- **Without AI, at once:** multiple-choice questions, values and short answers are graded by
  the code. A value is right within the tolerance of its question, written with a comma or
  a point, as a fraction, or with its unit. A short answer is compared without case,
  accents or punctuation, with one typo tolerated, except on a digit and in an answer under
  4 characters ("n-1" is not "n-2").
- **Open answers, by Claude:** Entrée sends your answer to Claude, which grades it while you
  choose your confidence: each criterion of the question met or not, with a sentence, then
  a comment and the model answer. The app gives the verdict: right when every criterion is
  met. After 15 seconds of waiting, the session goes on, and the grading shows at the end.
- **"Je pense avoir juste":** a value or a short answer that the code found wrong goes to
  Claude in the background. If Claude agrees, the answer becomes right in the history, the
  question is rescheduled, and your wording is accepted from then on.
- **Without Claude:** a local model, Qwen 3.5 4B with Ollama, grades open answers instead,
  provisionally. Claude checks those gradings when it is back, and corrects the history if
  it disagrees.
- **End of session:** the questions to review, the mistakes made while sure first, and the
  gradings that came after their question was left.

Coming next: exercises, exams, statistics, planning, translation and an assistant in the
reader.

## How it works

- One Python app: a local FastAPI server, on 127.0.0.1 only, and a pywebview window that
  shows the React interface.
- Your data stays on your computer, in `%LOCALAPPDATA%\BoshMow`: the SQLite database, an
  untouched copy of each imported file, and a log of the AI calls.
- Claude is called through `claude -p` with your Claude subscription, never with an API
  key. It runs without any tool, settings or MCP server: it only sees what the app sends.
  AI tasks run in the background, one at a time, and wait while Claude is unavailable. A
  call that runs too long is tried once more, then its task is reported as failed.
- A chapter is prepared in short calls: its notions first, then, once you validate them,
  the questions of each notion, one call per notion.
- An open answer is graded in its own thread as soon as it is sent, never behind a
  background task. When Claude cannot answer, the local model grades it through the local
  API of Ollama, with the same prompt and the same checks.
- When a verdict changes after the fact (a claim accepted, a provisional grading
  overruled), the question is rescheduled by replaying all its answers with FSRS.
- Each AI task has a versioned prompt in [`prompts/`](prompts), a Pydantic output schema
  and automatic checks. The tests never call an AI: they use a fake one.
- The reader draws only the PDF pages near the screen, so that a long book stays light.

## Requirements

- Windows 10 or 11 with the Microsoft Edge WebView2 Runtime (preinstalled on Windows 11)
- Python 3.12 or newer
- Node.js 22.22 or newer
- [Claude Code](https://claude.com/claude-code), signed in with a Claude subscription, for
  the AI features.
- Optional: [Ollama](https://ollama.com) with the `qwen3.5:4b` model, which grades open
  answers when Claude is unavailable.

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
under the GNU AGPL-3.0 (or a commercial license from Artifex). The reader draws PDF pages
with [PDF.js](https://mozilla.github.io/pdf.js/), licensed under the Apache License 2.0.
