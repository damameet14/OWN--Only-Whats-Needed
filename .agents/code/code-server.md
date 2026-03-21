# Code Context: Server (FastAPI Backend)

## Last Updated
2026-03-21

## Overview
FastAPI backend serving REST API, WebSocket progress, SQLite database, and static web files. Handles project CRUD, transcription orchestration, export jobs, model management, and user profiles.

## Entry Points
- `main.py` → `start_server()` → `uvicorn.run(app)`
- All API routes defined in `server/app.py`

## Execution Flow
1. `startup` event → `ensure_directories()` + `init_database()` + `scan_existing_models()`
2. `POST /api/projects` → save upload → probe video → generate thumbnail → create DB record → generate timeline assets (async)
3. `POST /api/projects/{id}/transcribe` → spawn `asyncio.create_task(_run_transcription)` → returns `task_id`
4. `ws/progress/{task_id}` → streams `{percent, message, result}` updates
5. `POST /api/projects/{id}/export` → spawn `_run_export` → streams progress → produces file
6. `GET /api/projects/{id}/timeline_sprite` & `/waveform` → serve generated timeline image assets

## Functions / Methods / Classes
| Name | Type | File Path | Description | Calls / Used By |
|------|------|-----------|-------------|-----------------|
| `startup` | fn | `server/app.py` | Initializes directories, database, model scan | FastAPI lifecycle |
| `create_project` | fn | `server/app.py` | Upload handler — saves file, probes, creates record | `POST /api/projects` |
| `start_transcription` | fn | `server/app.py` | Launches async transcription task | `POST /api/projects/{id}/transcribe` |
| `_run_transcription` | fn | `server/app.py` | Background task — calls Vosk or Whisper engine | `start_transcription` |
| `start_export` | fn | `server/app.py` | Launches async export task | `POST /api/projects/{id}/export` |
| `_run_export` | fn | `server/app.py` | Background task — calls exporter engine | `start_export` |
| `ws_progress` | fn | `server/app.py` | WebSocket endpoint for task progress | Frontend `watchProgress()` |
| `ensure_directories` | fn | `server/config.py` | Creates data/uploads/thumbnails/exports dirs | `startup` |
| `init_database` | fn | `server/database.py` | Creates SQLite tables | `startup` |
| `create_project` | fn | `server/database.py` | INSERT project record | `app.create_project` |
| `get_project` | fn | `server/database.py` | SELECT project by ID | Multiple routes |
| `list_projects` | fn | `server/database.py` | SELECT all projects | `GET /api/projects` |
| `update_project` | fn | `server/database.py` | UPDATE project fields | Multiple routes |
| `delete_project` | fn | `server/database.py` | DELETE project record | `DELETE /api/projects/{id}` |
| `scan_existing_models` | fn | `server/database.py` | Auto-register Vosk model dirs | `startup` |
| `get_available_models` | fn | `server/model_manager.py` | Lists Vosk + Whisper models with install status | `GET /api/models/available` |
| `download_vosk_model` | fn | `server/model_manager.py` | Downloads + extracts Vosk model zip | `POST /api/models/download` |
| `download_whisper_model` | fn | `server/model_manager.py` | Downloads Whisper model via faster-whisper | `POST /api/models/download` |
| `delete_model` | fn | `server/model_manager.py` | Removes model from disk + DB | `DELETE /api/models/{id}` |

## External Dependencies
- `fastapi`, `uvicorn`, `python-multipart`, `websockets`, `aiofiles`

## Internal Dependencies
- `core/transcriber.py`, `core/whisper_transcriber.py`, `core/exporter.py`
- `models/subtitle.py`
- `core/video_utils.py`, `core/srt_utils.py`

## Related Tasks
- .agents/tasks/task-own-revamp.md

## Related Architecture
- .agents/system/system_change-hybrid-architecture.md

## Known Limitations
- No rate limiting or auth — single-user only
- Background tasks use in-process `asyncio` — no task queue
- File uploads are fully buffered in memory before writing

## Change Log
| Date | Change |
|------|--------|
| 2026-03-20 | Initial creation: config, database, model_manager, app |
| 2026-03-21 | Added `generate_timeline_assets` integration in `app.py` |
| 2026-03-21 | Fixed python cross-platform lint errors for `subprocess.CREATE_NO_WINDOW` in `core/timeline_utils.py` |

