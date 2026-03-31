"""Model download manager — registry of available Vosk/Whisper models."""

import logging
import os
import zipfile
import shutil
import asyncio
from typing import Optional, Callable

import requests

from server.config import MODELS_DIR, PROJECT_ROOT
from server import database as db

# Suppress logging for download libraries
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
logging.getLogger("requests").setLevel(logging.ERROR)
logging.getLogger("urllib3").setLevel(logging.ERROR)


# ── Available Model Registry ──────────────────────────────────────────────────

AVAILABLE_MODELS = [
    # Vosk models — https://alphacephei.com/vosk/models
    {
        "name": "vosk-model-small-hi-0.22",
        "engine": "vosk",
        "language": "hi",
        "label": "Hindi (Small) — 42 MB",
        "size_mb": 42,
        "url": "https://alphacephei.com/vosk/models/vosk-model-small-hi-0.22.zip",
    },
    {
        "name": "vosk-model-hi-0.22",
        "engine": "vosk",
        "language": "hi",
        "label": "Hindi (Large) — 1.5 GB",
        "size_mb": 1500,
        "url": "https://alphacephei.com/vosk/models/vosk-model-hi-0.22.zip",
    },
    {
        "name": "vosk-model-small-en-us-0.15",
        "engine": "vosk",
        "language": "en",
        "label": "English (Small) — 40 MB",
        "size_mb": 40,
        "url": "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip",
    },
    {
        "name": "vosk-model-en-us-0.22",
        "engine": "vosk",
        "language": "en",
        "label": "English (Large) — 1.8 GB",
        "size_mb": 1800,
        "url": "https://alphacephei.com/vosk/models/vosk-model-en-us-0.22.zip",
    },
    # Whisper models (faster-whisper)
    {
        "name": "faster-whisper-large-v3",
        "engine": "whisper",
        "language": "multi",
        "label": "Whisper Large v3 (Multilingual) — 3 GB",
        "size_mb": 3000,
        "url": None,  # Downloaded via faster-whisper library
    },
    {
        "name": "faster-whisper-large-v3-turbo",
        "engine": "whisper",
        "language": "multi",
        "label": "Whisper Large v3 Turbo (Multilingual) — 800 MB",
        "size_mb": 800,
        "url": None,  # Downloaded via faster-whisper library
    },
]


def get_available_models() -> list[dict]:
    """Return list of available models with install status."""
    installed = {m["name"]: m for m in db.list_models()}
    result = []
    for model in AVAILABLE_MODELS:
        info = dict(model)
        if model["name"] in installed:
            info["installed"] = True
            info["model_id"] = installed[model["name"]]["id"]
        else:
            info["installed"] = False
            info["model_id"] = None
        result.append(info)
    return result


async def download_vosk_model(
    model_name: str,
    progress_callback: Optional[Callable[[int, str], None]] = None,
) -> dict:
    """Download and extract a Vosk model.

    Args:
        model_name: Name of the model from AVAILABLE_MODELS
        progress_callback: Optional async callback(percent, message)

    Returns:
        Registered model dict from the database.
    """
    # Find the model config
    model_info = None
    for m in AVAILABLE_MODELS:
        if m["name"] == model_name:
            model_info = m
            break

    if model_info is None:
        raise ValueError(f"Unknown model: {model_name}")

    if model_info["engine"] != "vosk" or model_info["url"] is None:
        raise ValueError(f"Cannot download {model_name} via URL. Use library download.")

    url = model_info["url"]
    zip_path = os.path.join(MODELS_DIR, f"{model_name}.zip")
    extract_dir = os.path.join(PROJECT_ROOT, model_name)

    # Check if already exists
    if os.path.isdir(extract_dir):
        # Register if not in DB
        existing = db.list_models()
        for m in existing:
            if m["name"] == model_name:
                return m
        return db.register_model(
            name=model_name,
            engine="vosk",
            language=model_info["language"],
            path=extract_dir,
            is_default=True,
        )

    os.makedirs(MODELS_DIR, exist_ok=True)

    # Download
    if progress_callback:
        await progress_callback(0, f"Downloading {model_name}...")

    def _download():
        response = requests.get(url, stream=True)
        response.raise_for_status()
        total = int(response.headers.get("content-length", 0))
        downloaded = 0

        with open(zip_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
                downloaded += len(chunk)

        return total

    total_size = await asyncio.to_thread(_download)

    if progress_callback:
        await progress_callback(70, "Extracting model...")

    # Extract
    def _extract():
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(PROJECT_ROOT)
        os.remove(zip_path)

    await asyncio.to_thread(_extract)

    if progress_callback:
        await progress_callback(95, "Registering model...")

    # Calculate actual size
    size = sum(
        os.path.getsize(os.path.join(dp, f))
        for dp, _, fnames in os.walk(extract_dir)
        for f in fnames
    )

    # Register in database
    model = db.register_model(
        name=model_name,
        engine="vosk",
        language=model_info["language"],
        path=extract_dir,
        size_bytes=size,
        is_default=True,
    )

    if progress_callback:
        await progress_callback(100, "Download complete!")

    return model


async def download_whisper_model(
    model_name: str,
    progress_callback: Optional[Callable[[int, str], None]] = None,
) -> dict:
    """Download a Whisper model from HuggingFace Hub.

    Downloads model files to the project's models directory for better management.
    """
    if progress_callback:
        await progress_callback(0, f"Downloading {model_name} from HuggingFace...")

    # Map internal name to HuggingFace repo and model size
    # IMPORTANT: faster-whisper requires CTranslate2-format models, NOT PyTorch/safetensors.
    model_map = {
        "faster-whisper-large-v3": {
            "repo": "Systran/faster-whisper-large-v3",
            "size": "large-v3",
        },
        "faster-whisper-large-v3-turbo": {
            "repo": "deepdml/faster-whisper-large-v3-turbo-ct2",
            "size": "large-v3-turbo",
        },
    }

    model_info = model_map.get(model_name)
    if model_info is None:
        raise ValueError(f"Unknown whisper model: {model_name}")

    repo_id = model_info["repo"]
    model_size = model_info["size"]

    # Create model directory in project's models folder
    model_dir = os.path.join(MODELS_DIR, model_name)
    os.makedirs(model_dir, exist_ok=True)

    # Download using huggingface_hub
    def _download():
        import logging
        from huggingface_hub import snapshot_download

        # Suppress huggingface_hub logs
        logging.getLogger("huggingface_hub").setLevel(logging.ERROR)

        # Download model files to our directory
        snapshot_download(
            repo_id=repo_id,
            local_dir=model_dir,
        )
        return model_dir

    await asyncio.to_thread(_download)

    if progress_callback:
        await progress_callback(95, "Registering model...")

    # Calculate actual size
    size = sum(
        os.path.getsize(os.path.join(dp, f))
        for dp, _, fnames in os.walk(model_dir)
        for f in fnames
    )

    # Register in database
    model = db.register_model(
        name=model_name,
        engine="whisper",
        language="multi",
        path=model_dir,
        size_bytes=size,
        is_default=False,
    )

    if progress_callback:
        await progress_callback(100, "Whisper model ready!")

    return model


def delete_model(model_id: int) -> bool:
    """Delete a model and its files."""
    model = db.get_model(model_id)
    if model is None:
        return False

    # Only delete Vosk model directories that we manage
    if model["engine"] == "vosk" and os.path.isdir(model["path"]):
        model_dir = model["path"]
        # Safety check: only delete if it's inside project root
        if os.path.commonpath([model_dir, PROJECT_ROOT]) == PROJECT_ROOT:
            shutil.rmtree(model_dir, ignore_errors=True)

    return db.delete_model(model_id)
