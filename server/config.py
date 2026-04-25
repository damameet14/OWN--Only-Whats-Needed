"""Configuration constants for the OWN server."""

import os
import sys

# ── Project root ──────────────────────────────────────────────────────────────
# When running as a PyInstaller bundle, sys.executable points to the .exe;
# PROJECT_ROOT is the directory containing it.  In dev mode it's the repo root.

if getattr(sys, 'frozen', False):
    PROJECT_ROOT = os.path.dirname(sys.executable)
else:
    PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── Data directories ─────────────────────────────────────────────────────────

DATA_DIR = os.path.join(PROJECT_ROOT, "data")
UPLOADS_DIR = os.path.join(DATA_DIR, "uploads")
THUMBNAILS_DIR = os.path.join(DATA_DIR, "thumbnails")
EXPORTS_DIR = os.path.join(DATA_DIR, "exports")

# ── Models directory (Whisper models) ─────────────────────────────────────────

MODELS_DIR = os.path.join(PROJECT_ROOT, "models_data")

# ── Fonts directory ───────────────────────────────────────────────────────────

FONTS_DIR = os.path.join(PROJECT_ROOT, "fonts")

# ── Resources ─────────────────────────────────────────────────────────────────

PRESETS_PATH = os.path.join(PROJECT_ROOT, "resources", "presets.json")

# ── Database ──────────────────────────────────────────────────────────────────

DATABASE_PATH = os.path.join(PROJECT_ROOT, "own.db")

# ── Server settings ──────────────────────────────────────────────────────────

SERVER_HOST = "0.0.0.0"
SERVER_PORT = 80

# ── Supported input formats ──────────────────────────────────────────────────

INPUT_EXTENSIONS = {
    ".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv",
    ".wmv", ".m4v", ".3gp", ".ts", ".mpg", ".mpeg",
}

# ── Max upload size (500 MB) ─────────────────────────────────────────────────

MAX_UPLOAD_SIZE = 500 * 1024 * 1024

# ── Whisper chunked transcription settings ───────────────────────────────────

WHISPER_MAX_CHUNK_DURATION = 30.0      # Maximum chunk duration in seconds
WHISPER_MIN_SILENCE_DURATION = 0.5     # Minimum silence duration to split at
WHISPER_SILENCE_THRESHOLD = -40.0      # Silence threshold in dB


# ── FFmpeg / FFprobe paths ───────────────────────────────────────────────────
# In dev mode, these fall back to PATH.  In bundled mode, check bin/ first.

_BIN_DIR = os.path.join(PROJECT_ROOT, "bin")
_EXE_EXT = ".exe" if sys.platform == "win32" else ""


def get_ffmpeg_path() -> str:
    """Return path to ffmpeg binary. Checks bundled bin/ first, then PATH."""
    bundled = os.path.join(_BIN_DIR, f"ffmpeg{_EXE_EXT}")
    if os.path.isfile(bundled):
        return bundled
    return "ffmpeg"


def get_ffprobe_path() -> str:
    """Return path to ffprobe binary. Checks bundled bin/ first, then PATH."""
    bundled = os.path.join(_BIN_DIR, f"ffprobe{_EXE_EXT}")
    if os.path.isfile(bundled):
        return bundled
    return "ffprobe"


# ── Directory bootstrapping ──────────────────────────────────────────────────

def ensure_directories():
    """Create required directories if they don't exist."""
    for d in [DATA_DIR, UPLOADS_DIR, THUMBNAILS_DIR, EXPORTS_DIR, MODELS_DIR]:
        os.makedirs(d, exist_ok=True)
