# System Change: Hybrid Architecture Migration

## Date
2026-03-20

## What Changed
Migrated from a monolithic PySide6 desktop application to a hybrid architecture with four layers:
1. **Backend**: FastAPI server (`server/`) with REST API, WebSocket progress, SQLite database
2. **Core Engines**: Async generators for transcription (Vosk + faster-whisper) and export (Pillow + FFmpeg) — PySide6 dependencies removed
3. **Web Frontend**: Vanilla HTML/CSS/JS (`web/`) with Tailwind CDN — home page + full editor with canvas subtitle preview
4. **Desktop App**: pystray tray icon + customtkinter management window (`desktop/`)

New files created: `server/config.py`, `server/database.py`, `server/model_manager.py`, `server/app.py`, `core/whisper_transcriber.py`, `desktop/tray_app.py`, `desktop/main_window.py`, `desktop/setup.py`, `web/index.html`, `web/editor.html`, `web/css/app.css`, `web/js/api.js`, `web/js/app.js`, `web/js/editor.js`, `web/js/preview.js`, `web/js/timeline.js`.

Modified files: `main.py`, `requirements.txt`, `core/transcriber.py`, `core/exporter.py`, `models/subtitle.py`.

## Why
The PySide6 monolith was difficult to extend, had no API for external integration, and could not serve a web interface. The hybrid approach enables browser-based editing, keeps offline capability, and separates concerns for maintainability.

## What It Replaces
- PySide6 QThread-based transcription → asyncio async generators
- QPainter/QImage subtitle rendering → Pillow (PIL)
- PySide6 GUI → web frontend (HTML/JS) + customtkinter for desktop management
- Direct function calls → REST API + WebSocket for inter-component communication
- No database → SQLite with full CRUD for projects, models, users

## Impact on Other Systems
- `main.py` entry point completely rewritten — old PySide6 launch code replaced
- `requirements.txt` updated — PySide6 still listed (legacy) but no longer imported by core
- Any code importing from `core/transcriber.py` or `core/exporter.py` must use the new async generator interface
- `models/subtitle.py` dataclasses now include `to_dict()`/`from_dict()` — backward-compatible addition

## Confidence
Medium — Code is written and structurally complete. Needs runtime verification (venv fix + server startup test).

## Related Tasks
- .agents/tasks/task-own-revamp.md
