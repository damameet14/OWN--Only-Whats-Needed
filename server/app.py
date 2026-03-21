"""FastAPI application — REST API + WebSocket + static file serving."""

from __future__ import annotations
import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from typing import Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware

from server.config import (
    PROJECT_ROOT, UPLOADS_DIR, THUMBNAILS_DIR, EXPORTS_DIR,
    PRESETS_PATH, INPUT_EXTENSIONS, MAX_UPLOAD_SIZE, ensure_directories,
)
from server import database as db
from server.model_manager import get_available_models, download_vosk_model, download_whisper_model, delete_model
from models.subtitle import SubtitleTrack, WordTiming
from core.video_utils import get_video_info
from core.srt_utils import generate_srt


# ── App setup ─────────────────────────────────────────────────────────────────

app = FastAPI(title="OWN — Only What's Needed", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Task progress store (task_id → {percent, message, result})
_tasks: dict[str, dict] = {}
_task_events: dict[str, asyncio.Event] = {}


@app.on_event("startup")
async def startup():
    loop = asyncio.get_running_loop()
    def silence_connection_reset(loop, context):
        if isinstance(context.get('exception'), ConnectionResetError):
            return
        loop.default_exception_handler(context)
    loop.set_exception_handler(silence_connection_reset)

    ensure_directories()
    db.init_database()
    db.scan_existing_models(PROJECT_ROOT)


# Mount static files last (in lifespan, after routes are set)
WEB_DIR = os.path.join(PROJECT_ROOT, "web")


# ── Page routes ───────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    """Serve home page."""
    index_path = os.path.join(WEB_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return JSONResponse({"message": "OWN API is running. Web frontend not found."})


@app.get("/editor/{project_id}")
async def editor_page(project_id: int):
    """Serve editor page."""
    editor_path = os.path.join(WEB_DIR, "editor.html")
    if os.path.exists(editor_path):
        return FileResponse(editor_path)
    raise HTTPException(404, "Editor page not found")


# ── Project API ───────────────────────────────────────────────────────────────

@app.get("/api/projects")
async def list_projects():
    return db.list_projects()


@app.post("/api/projects")
async def create_project(
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    language: Optional[str] = Form("hi"),
):
    """Upload a video and create a project."""
    # Validate extension
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in INPUT_EXTENSIONS:
        raise HTTPException(400, f"Unsupported format: {ext}")

    # Save uploaded file
    safe_name = f"{uuid.uuid4().hex}{ext}"
    video_path = os.path.join(UPLOADS_DIR, safe_name)

    with open(video_path, "wb") as f:
        content = await file.read()
        if len(content) > MAX_UPLOAD_SIZE:
            raise HTTPException(413, "File too large (max 500 MB)")
        f.write(content)

    # Probe video info
    try:
        info = get_video_info(video_path)
    except Exception as e:
        os.remove(video_path)
        raise HTTPException(400, f"Invalid video file: {e}")

    # Generate thumbnail
    thumb_name = f"{uuid.uuid4().hex}.jpg"
    thumb_path = os.path.join(THUMBNAILS_DIR, thumb_name)
    _generate_thumbnail(video_path, thumb_path)

    project_title = title or file.filename or "Untitled Project"

    project = db.create_project(
        title=project_title,
        video_path=video_path,
        video_duration=info.duration,
        video_width=info.width,
        video_height=info.height,
        thumbnail_path=thumb_path,
        language=language,
    )

    return project


@app.get("/api/projects/{project_id}")
async def get_project(project_id: int):
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    # Parse subtitle data if present
    if project.get("subtitle_data"):
        try:
            project["subtitle_data"] = json.loads(project["subtitle_data"])
        except (json.JSONDecodeError, TypeError):
            pass
    return project


@app.put("/api/projects/{project_id}")
async def update_project(project_id: int, body: dict):
    """Update project fields (subtitle data, title, language, etc.)."""
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    update_fields = {}
    if "title" in body:
        update_fields["title"] = body["title"]
    if "language" in body:
        update_fields["language"] = body["language"]
    if "subtitle_data" in body:
        # Store as JSON string
        if isinstance(body["subtitle_data"], dict):
            update_fields["subtitle_data"] = json.dumps(body["subtitle_data"], ensure_ascii=False)
        else:
            update_fields["subtitle_data"] = body["subtitle_data"]
    if "status" in body:
        update_fields["status"] = body["status"]

    updated = db.update_project(project_id, **update_fields)
    return updated


@app.delete("/api/projects/{project_id}")
async def delete_project(project_id: int):
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    # Clean up files
    for path_key in ["video_path", "thumbnail_path"]:
        path = project.get(path_key)
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass

    db.delete_project(project_id)
    return {"deleted": True}


# ── Transcription ─────────────────────────────────────────────────────────────

@app.post("/api/projects/{project_id}/transcribe")
async def start_transcription(project_id: int, body: dict = None):
    """Start transcription for a project. Returns a task_id for progress tracking."""
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    body = body or {}
    engine = body.get("engine", "vosk")  # "vosk" or "whisper"
    language = body.get("language", project.get("language", "hi"))

    task_id = uuid.uuid4().hex
    _tasks[task_id] = {"percent": 0, "message": "Starting...", "result": None}
    _task_events[task_id] = asyncio.Event()

    # Run transcription in background
    asyncio.create_task(_run_transcription(task_id, project, engine, language))

    db.update_project(project_id, status="transcribing")
    return {"task_id": task_id}


async def _run_transcription(task_id: str, project: dict, engine: str, language: str):
    """Background task for transcription."""
    try:
        video_path = project["video_path"]

        if engine == "whisper":
            from core.whisper_transcriber import transcribe_whisper

            # Find the whisper model to use
            model_size = "large-v3-turbo"
            models = db.list_models()
            for m in models:
                if m["engine"] == "whisper":
                    if "turbo" in m["name"]:
                        model_size = "large-v3-turbo"
                    else:
                        model_size = "large-v3"
                    break

            gen = transcribe_whisper(video_path, model_size=model_size, language=language)
        else:
            from core.transcriber import transcribe_vosk

            # Find the vosk model path
            model_path = None
            models = db.list_models()
            for m in models:
                if m["engine"] == "vosk" and m["language"] == language:
                    model_path = m["path"]
                    break
                elif m["engine"] == "vosk" and m.get("is_default"):
                    model_path = m["path"]

            if model_path is None:
                # Fallback to default path
                model_path = os.path.join(PROJECT_ROOT, "vosk-model-hi-0.22")

            gen = transcribe_vosk(video_path, model_path=model_path)

        words = None
        async for progress, message, result in gen:
            _tasks[task_id] = {"percent": progress, "message": message, "result": None}
            _task_events[task_id].set()
            _task_events[task_id] = asyncio.Event()
            if result is not None:
                words = result

        if words:
            # Build subtitle track
            track = SubtitleTrack()
            track.rebuild_segments(words)
            subtitle_json = track.to_json()

            db.update_project(
                project["id"],
                subtitle_data=subtitle_json,
                status="completed",
            )

            _tasks[task_id] = {
                "percent": 100,
                "message": "Transcription complete!",
                "result": {"word_count": len(words)},
            }
        else:
            db.update_project(project["id"], status="draft")
            _tasks[task_id] = {
                "percent": 100,
                "message": "No words detected.",
                "result": {"word_count": 0},
            }

    except Exception as e:
        _tasks[task_id] = {"percent": -1, "message": f"Error: {e}", "result": None}
        db.update_project(project["id"], status="draft")

    _task_events.get(task_id, asyncio.Event()).set()


# ── Export ────────────────────────────────────────────────────────────────────

@app.post("/api/projects/{project_id}/export")
async def start_export(project_id: int, body: dict = None):
    """Start video export. Returns a task_id for progress tracking."""
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    if not project.get("subtitle_data"):
        raise HTTPException(400, "No subtitles to export. Transcribe first.")

    body = body or {}
    format_key = body.get("format", "MP4 (H.264)")

    task_id = uuid.uuid4().hex
    _tasks[task_id] = {"percent": 0, "message": "Starting export...", "result": None}
    _task_events[task_id] = asyncio.Event()

    asyncio.create_task(_run_export(task_id, project, format_key))
    return {"task_id": task_id}


async def _run_export(task_id: str, project: dict, format_key: str):
    """Background task for video export."""
    try:
        from core.exporter import export_video
        from core.video_utils import OUTPUT_FORMATS

        fmt_info = OUTPUT_FORMATS.get(format_key, OUTPUT_FORMATS["MP4 (H.264)"])
        ext = fmt_info["ext"]

        # Build subtitle track from stored data
        subtitle_data = project["subtitle_data"]
        if isinstance(subtitle_data, str):
            track = SubtitleTrack.from_json(subtitle_data)
        else:
            track = SubtitleTrack.from_dict(subtitle_data)

        # Output path
        base_name = os.path.splitext(os.path.basename(project["title"]))[0]
        output_name = f"{base_name}_captioned_{uuid.uuid4().hex[:6]}{ext}"
        output_path = os.path.join(EXPORTS_DIR, output_name)

        gen = export_video(project["video_path"], output_path, track, format_key)

        async for progress, message, result in gen:
            _tasks[task_id] = {"percent": progress, "message": message, "result": None}
            _task_events[task_id].set()
            _task_events[task_id] = asyncio.Event()
            if result is not None:
                _tasks[task_id] = {
                    "percent": 100,
                    "message": "Export complete!",
                    "result": {"output_path": result, "filename": output_name},
                }

    except Exception as e:
        _tasks[task_id] = {"percent": -1, "message": f"Error: {e}", "result": None}

    _task_events.get(task_id, asyncio.Event()).set()


@app.get("/api/projects/{project_id}/srt")
async def download_srt(project_id: int):
    """Download SRT file for a project."""
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    if not project.get("subtitle_data"):
        raise HTTPException(400, "No subtitles available")

    subtitle_data = project["subtitle_data"]
    if isinstance(subtitle_data, str):
        track = SubtitleTrack.from_json(subtitle_data)
    else:
        track = SubtitleTrack.from_dict(subtitle_data)

    srt_content = generate_srt(track)

    # Write to temp file
    tmp = tempfile.NamedTemporaryFile(suffix=".srt", delete=False, mode="w", encoding="utf-8")
    tmp.write(srt_content)
    tmp.close()

    base_name = os.path.splitext(project["title"])[0]
    return FileResponse(
        tmp.name,
        media_type="text/plain",
        filename=f"{base_name}.srt",
    )


@app.get("/api/projects/{project_id}/thumbnail")
async def get_thumbnail(project_id: int):
    """Get project thumbnail image."""
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    thumb_path = project.get("thumbnail_path")
    if thumb_path and os.path.exists(thumb_path):
        return FileResponse(thumb_path, media_type="image/jpeg")

    raise HTTPException(404, "Thumbnail not available")


# ── Export download ───────────────────────────────────────────────────────────

@app.get("/api/exports/{filename}")
async def download_export(filename: str):
    """Download an exported video file."""
    filepath = os.path.join(EXPORTS_DIR, filename)
    if not os.path.exists(filepath):
        raise HTTPException(404, "File not found")
    return FileResponse(filepath, filename=filename)


# ── Video streaming ───────────────────────────────────────────────────────────

@app.get("/api/projects/{project_id}/video")
async def stream_video(project_id: int):
    """Stream the project's video file."""
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    video_path = project.get("video_path")
    if not video_path or not os.path.exists(video_path):
        raise HTTPException(404, "Video file not found")

    return FileResponse(video_path, media_type="video/mp4")


# ── Model API ─────────────────────────────────────────────────────────────────

@app.get("/api/models")
async def list_models():
    return db.list_models()


@app.get("/api/models/available")
async def list_available_models():
    return get_available_models()


@app.post("/api/models/download")
async def download_model(body: dict):
    """Start downloading a model. Returns a task_id."""
    model_name = body.get("name")
    if not model_name:
        raise HTTPException(400, "Model name required")

    task_id = uuid.uuid4().hex
    _tasks[task_id] = {"percent": 0, "message": "Starting download...", "result": None}
    _task_events[task_id] = asyncio.Event()

    asyncio.create_task(_run_model_download(task_id, model_name))
    return {"task_id": task_id}


async def _run_model_download(task_id: str, model_name: str):
    """Background model download task."""
    try:
        async def progress_cb(percent, message):
            _tasks[task_id] = {"percent": percent, "message": message, "result": None}
            _task_events[task_id].set()
            _task_events[task_id] = asyncio.Event()

        if model_name.startswith("faster-whisper"):
            model = await download_whisper_model(model_name, progress_cb)
        else:
            model = await download_vosk_model(model_name, progress_cb)

        _tasks[task_id] = {
            "percent": 100,
            "message": "Download complete!",
            "result": model,
        }
    except Exception as e:
        _tasks[task_id] = {"percent": -1, "message": f"Error: {e}", "result": None}

    _task_events.get(task_id, asyncio.Event()).set()


@app.delete("/api/models/{model_id}")
async def remove_model(model_id: int):
    success = delete_model(model_id)
    if not success:
        raise HTTPException(404, "Model not found")
    return {"deleted": True}


# ── User API ──────────────────────────────────────────────────────────────────

@app.get("/api/user")
async def get_user():
    user = db.get_user()
    if not user:
        return {"id": None, "name": "Guest", "email": None, "mobile": None}
    return user


@app.put("/api/user")
async def update_user(body: dict):
    name = body.get("name", "User")
    email = body.get("email")
    mobile = body.get("mobile")
    user = db.create_or_update_user(name=name, email=email, mobile=mobile)
    return user


# ── Presets API ───────────────────────────────────────────────────────────────

@app.get("/api/presets")
async def get_presets():
    if os.path.exists(PRESETS_PATH):
        with open(PRESETS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


# ── WebSocket progress ────────────────────────────────────────────────────────

@app.websocket("/ws/progress/{task_id}")
async def ws_progress(websocket: WebSocket, task_id: str):
    await websocket.accept()
    try:
        while True:
            task = _tasks.get(task_id)
            if task is None:
                await websocket.send_json({"error": "Task not found"})
                break

            await websocket.send_json(task)

            if task["percent"] >= 100 or task["percent"] < 0:
                break

            # Wait for next update
            event = _task_events.get(task_id)
            if event:
                try:
                    await asyncio.wait_for(event.wait(), timeout=30.0)
                except asyncio.TimeoutError:
                    pass

    except WebSocketDisconnect:
        pass
    except Exception:
        pass


# ── Helpers ───────────────────────────────────────────────────────────────────

def _generate_thumbnail(video_path: str, thumb_path: str):
    """Generate a thumbnail from the video at 1 second."""
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-ss", "1",
        "-vframes", "1",
        "-vf", "scale=480:-1",
        thumb_path,
    ]
    subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )


# ── Mount static files (after all routes) ─────────────────────────────────────

if os.path.isdir(WEB_DIR):
    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
    # Also mount CSS and JS subdirectories
    css_dir = os.path.join(WEB_DIR, "css")
    js_dir = os.path.join(WEB_DIR, "js")
    if os.path.isdir(css_dir):
        app.mount("/css", StaticFiles(directory=css_dir), name="css")
    if os.path.isdir(js_dir):
        app.mount("/js", StaticFiles(directory=js_dir), name="js")
