# Task: OWN App Architecture Revamp

## Last Updated
2026-03-20

## Task Type
Heavy

## Summary
Migrate OWN from a monolithic PySide6 desktop app to a hybrid architecture: FastAPI backend + web frontend + desktop tray app with offline AI transcription.

## Scope
**In scope**: Backend API, core engine adaptation (async, Pillow), web frontend (home + editor), desktop tray app, faster-whisper integration, SQLite database, model management.
**Out of scope**: Cloud deployment, user authentication, multi-user concurrency, mobile app.

## Subtask 1: Backend API & Database
**Goal**: Create FastAPI server with REST routes, WebSocket progress, SQLite CRUD, and model management.
**Acceptance criteria**: Server imports cleanly; all `/api/` routes defined; database schema covers users, models, projects.
**Status**: [x] Complete

## Subtask 2: Core Engine Adaptation
**Goal**: Remove PySide6 from transcriber/exporter, add async generators, integrate faster-whisper.
**Acceptance criteria**: `core/transcriber.py` uses async yield; `core/exporter.py` uses Pillow; `core/whisper_transcriber.py` exists; `models/subtitle.py` has `to_dict`/`from_dict`.
**Status**: [x] Complete

## Subtask 3: Web Frontend
**Goal**: Build home page (upload + project grid) and editor page (video preview + subtitle styling + timeline).
**Acceptance criteria**: `index.html` loads with upload zone; `editor.html` renders video with canvas subtitle overlay; style controls update preview in real-time.
**Status**: [x] Complete

## Subtask 4: Desktop Tray App & Entry Point
**Goal**: System tray icon with pystray, customtkinter management window, first-run setup, unified entry point.
**Acceptance criteria**: `main.py` starts server + tray; tray menu has Open/Browser/Quit; setup configures `own.local`.
**Status**: [x] Complete

## Subtask 5: Verification & Dependency Resolution
**Goal**: Install all dependencies, verify server starts, test web UI loads.
**Acceptance criteria**: `pip install` succeeds; `python -c "from server.app import app"` passes; browser opens to home page.
**Status**: [x] Complete

## Blockers
- Venv path mismatch: `pip` installs to `Meet\stt_vosk\venv` but project runs from `stt_vosk`. User needs to recreate venv or reinstall packages.

## Related Code
- .agents/code/code-server.md
- .agents/code/code-core-engines.md
- .agents/code/code-web-frontend.md
- .agents/code/code-desktop.md

## Related Architecture
- .agents/system/system_change-hybrid-architecture.md

## Completion Criteria
Server starts on `localhost`, serves the web UI, accepts video uploads, transcribes with Vosk/Whisper, renders styled subtitles in the editor, and exports captioned video.

## Final Status
[x] Complete
