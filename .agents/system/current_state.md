# Current System State

## Last Updated
2026-03-20

## Architecture Summary
OWN is a hybrid offline video captioning application. A FastAPI backend serves a REST API and static web frontend on `localhost`. Core transcription (Vosk + faster-whisper) and export (FFmpeg + Pillow) engines run as async generators on the server. A desktop tray app (pystray) manages the server lifecycle. SQLite stores project metadata, user profiles, and model registry. The web editor provides real-time subtitle preview via canvas overlay, style controls, and a timeline widget.

## System Entry Points
- API: `server/app.py` — FastAPI on `http://localhost:80` (or `:8000` non-admin)
- Background jobs: `asyncio.create_task` for transcription/export (in-process)
- CLI / scripts: `main.py` — unified entry point (server + tray + setup)

## Core Components
| Component | Description | Related Files |
|-----------|-------------|---------------|
| FastAPI Server | REST + WebSocket API, static file serving | `server/app.py`, `server/config.py` |
| Database | SQLite CRUD for users, models, projects | `server/database.py` |
| Model Manager | Download/registry for Vosk + Whisper models | `server/model_manager.py` |
| Vosk Transcriber | Async speech-to-text with Vosk | `core/transcriber.py` |
| Whisper Transcriber | Async speech-to-text with faster-whisper | `core/whisper_transcriber.py` |
| Video Exporter | FFmpeg decode → Pillow render → encode | `core/exporter.py` |
| Subtitle Models | WordTiming, SubtitleSegment, SubtitleTrack + JSON serialization | `models/subtitle.py` |
| Web Home | Upload zone, project grid, search | `web/index.html`, `web/js/app.js` |
| Web Editor | Video preview, canvas subtitles, style controls, timeline | `web/editor.html`, `web/js/editor.js`, `web/js/preview.js`, `web/js/timeline.js` |
| API Client | REST + WebSocket helpers for the frontend | `web/js/api.js` |
| Desktop Tray | pystray system tray icon + menu | `desktop/tray_app.py` |
| Desktop Window | customtkinter management UI | `desktop/main_window.py` |
| First-Run Setup | Hosts file config, model check | `desktop/setup.py` |

## Data Flow
1. User uploads video via web UI (`POST /api/projects` with multipart file)
2. Server saves to `data/uploads/`, generates thumbnail via FFmpeg, creates DB record
3. User starts transcription (`POST /api/projects/{id}/transcribe`) → async task
4. Transcription engine (Vosk or Whisper) extracts audio, yields `(progress, message, result)` tuples
5. WebSocket at `/ws/progress/{task_id}` streams progress to the frontend
6. Completed word timings are built into a `SubtitleTrack`, serialized to JSON, stored in DB
7. Editor loads subtitle data, renders on canvas overlay, applies styles in real-time
8. Export writes captioned video via FFmpeg + Pillow subtitle rendering pipeline

## Active Integrations
- **FFmpeg/ffprobe**: Video decode, audio extraction, encode, thumbnail generation
- **Vosk**: Offline speech recognition models (downloaded as zip archives)
- **faster-whisper**: Local Whisper inference (models downloaded via HuggingFace)
- **Tailwind CSS CDN**: UI styling (loaded from CDN in HTML files)

## Known Constraints
- Port 80 requires admin privileges on Windows; fallback to 8000
- No authentication — single-user local application
- Large video files limited to 500 MB upload
- Whisper transcription is CPU-bound unless CUDA is available

## Source of Truth
Consolidates: system_change-hybrid-architecture.md

## Integrity Rule
- Must reflect the latest system_change-* file
- Must not contradict any recent architectural change
- If a contradiction is found, update this file before proceeding
