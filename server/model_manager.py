"""Model download manager — registry of available Whisper models."""

import logging
import os
import shutil
import asyncio
from typing import Optional, Callable

from server.config import MODELS_DIR, PROJECT_ROOT
from server import database as db

# Suppress logging for download libraries
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
logging.getLogger("requests").setLevel(logging.ERROR)
logging.getLogger("urllib3").setLevel(logging.ERROR)


# ── Available Model Registry ──────────────────────────────────────────────────

AVAILABLE_MODELS = [
    # Whisper models (faster-whisper / CTranslate2 format)
    {
        "name": "faster-whisper-large-v3",
        "engine": "whisper",
        "language": "multi",
        "label": "Whisper Large v3 (Multilingual) — 3 GB",
        "size_mb": 3000,
        "url": None,  # Downloaded via huggingface_hub
    },
    {
        "name": "faster-whisper-large-v3-turbo",
        "engine": "whisper",
        "language": "multi",
        "label": "Whisper Large v3 Turbo (Multilingual) — 800 MB ⭐ Default",
        "size_mb": 800,
        "url": None,  # Downloaded via huggingface_hub
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


async def download_whisper_model(
    model_name: str,
    progress_callback: Optional[Callable[[int, str], None]] = None,
) -> dict:
    """Download a Whisper model from HuggingFace Hub (CTranslate2 format)."""
    if progress_callback:
        await progress_callback(0, f"Downloading {model_name} from HuggingFace...")

    # Map internal name to HuggingFace repo
    # IMPORTANT: faster-whisper requires CTranslate2-format models (model.bin), NOT safetensors.
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

    model_dir = os.path.join(MODELS_DIR, model_name)
    os.makedirs(model_dir, exist_ok=True)

    def _download():
        import logging
        from huggingface_hub import snapshot_download
        logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
        snapshot_download(repo_id=repo_id, local_dir=model_dir)
        return model_dir

    await asyncio.to_thread(_download)

    if progress_callback:
        await progress_callback(95, "Registering model...")

    size = sum(
        os.path.getsize(os.path.join(dp, f))
        for dp, _, fnames in os.walk(model_dir)
        for f in fnames
    )

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
    """Delete a model record (and its files if managed by us)."""
    model = db.get_model(model_id)
    if model is None:
        return False

    # Delete managed Whisper model directories inside MODELS_DIR
    model_path = model.get("path", "")
    if model_path and os.path.isdir(model_path):
        try:
            common = os.path.commonpath([model_path, MODELS_DIR])
            if common == MODELS_DIR:
                shutil.rmtree(model_path, ignore_errors=True)
        except ValueError:
            pass  # Paths on different drives

    return db.delete_model(model_id)
