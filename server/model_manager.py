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
    {
        "name": "gemma-4-E2B-it-UD-IQ3_XXS.gguf",
        "engine": "llama",
        "language": "multi",
        "label": "Gemma Transliteration Model (unsloth) — 1.5 GB",
        "size_mb": 1500,
        "url": None,
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


async def download_ai_model(
    model_name: str,
    progress_callback: Optional[Callable[[int, str], None]] = None,
    cancel_event: Optional["threading.Event"] = None,
) -> dict:
    """Download a model from HuggingFace Hub (CTranslate2 or GGUF)."""
    if progress_callback:
        await progress_callback(0, f"Downloading {model_name} from HuggingFace...")

    model_map = {
        "faster-whisper-large-v3": {
            "repo": "Systran/faster-whisper-large-v3",
            "size": "large-v3",
            "type": "whisper",
        },
        "faster-whisper-large-v3-turbo": {
            "repo": "deepdml/faster-whisper-large-v3-turbo-ct2",
            "size": "large-v3-turbo",
            "type": "whisper",
        },
        "gemma-4-E2B-it-UD-IQ3_XXS.gguf": {
            "repo": "unsloth/gemma-4-E2B-it-GGUF",
            "filename": "gemma-4-E2B-it-UD-IQ3_XXS.gguf",
            "type": "llama",
        }
    }

    model_info = model_map.get(model_name)
    if model_info is None:
        raise ValueError(f"Unknown model: {model_name}")

    repo_id = model_info["repo"]
    model_type = model_info["type"]

    model_dir = os.path.join(MODELS_DIR, model_name)
    os.makedirs(model_dir, exist_ok=True)

    # BaseException subclass — escapes `except Exception:` blocks in libraries
    class _DownloadCancelled(BaseException):
        pass

    # We'll use a shared dict to capture progress from the download thread
    _progress_state = {"downloaded": 0, "total": 0, "done": False}

    def _download():
        import logging
        from huggingface_hub import snapshot_download, hf_hub_download
        import tqdm as tqdm_mod
        logging.getLogger("huggingface_hub").setLevel(logging.ERROR)

        # Custom tqdm class to capture download progress
        class ProgressTracker(tqdm_mod.tqdm):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                if self.total:
                    _progress_state["total"] += self.total

            def update(self, n=1):
                super().update(n)
                _progress_state["downloaded"] += n
                # Check cancel flag inside the download thread
                if cancel_event and cancel_event.is_set():
                    raise _DownloadCancelled("Download cancelled")

        try:
            if model_type == "llama":
                filename = model_info["filename"]
                hf_hub_download(
                    repo_id=repo_id,
                    filename=filename,
                    local_dir=model_dir,
                    tqdm_class=ProgressTracker,
                )
            else:
                snapshot_download(
                    repo_id=repo_id,
                    local_dir=model_dir,
                    tqdm_class=ProgressTracker,
                )
        except _DownloadCancelled:
            raise
        except Exception:
            # If any library caught and re-wrapped our exception, check the flag
            if cancel_event and cancel_event.is_set():
                raise _DownloadCancelled("Download cancelled")
            raise

        _progress_state["done"] = True
        return model_dir

    # Run the blocking download in a thread, but poll progress from the async side
    import concurrent.futures
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    loop = asyncio.get_running_loop()
    future = loop.run_in_executor(executor, _download)

    def _cleanup_on_done(f):
        """Clean up partial files if the thread finishes after cancellation."""
        if cancel_event and cancel_event.is_set():
            try:
                if os.path.isdir(model_dir):
                    shutil.rmtree(model_dir, ignore_errors=True)
            except Exception:
                pass

    future.add_done_callback(_cleanup_on_done)

    # Poll progress while the download runs
    cancelled = False
    while not future.done():
        await asyncio.sleep(2)

        # Check if cancellation was requested
        if cancel_event and cancel_event.is_set():
            cancelled = True
            break

        total = _progress_state["total"]
        downloaded = _progress_state["downloaded"]
        if total > 0:
            pct = min(90, int((downloaded / total) * 90))  # Cap at 90% until registration
            size_mb = downloaded / (1024 * 1024)
            total_mb = total / (1024 * 1024)
            if progress_callback:
                await progress_callback(pct, f"Downloading... {size_mb:.0f} / {total_mb:.0f} MB")
        else:
            if progress_callback:
                await progress_callback(5, "Connecting to HuggingFace...")

    if cancelled:
        # Don't wait for the thread — the done_callback will clean up files
        raise asyncio.CancelledError("Download cancelled by user")

    # Retrieve result (will raise if _download() raised)
    try:
        await future
    except (_DownloadCancelled, BaseException) as exc:
        if cancel_event and cancel_event.is_set():
            if os.path.isdir(model_dir):
                shutil.rmtree(model_dir, ignore_errors=True)
            raise asyncio.CancelledError("Download cancelled by user") from exc
        raise

    if progress_callback:
        await progress_callback(95, "Registering model...")

    size = sum(
        os.path.getsize(os.path.join(dp, f))
        for dp, _, fnames in os.walk(model_dir)
        for f in fnames
    )

    model = db.register_model(
        name=model_name,
        engine=model_type,
        language="multi",
        path=model_dir,
        size_bytes=size,
        is_default=False,
    )

    if progress_callback:
        await progress_callback(100, f"{model_name} ready!")

    return model


def install_model_from_zip(zip_path: str, model_name: str, engine: str) -> dict:
    """Extract a ZIP file containing a model and register it."""
    import zipfile
    
    model_dir = os.path.join(MODELS_DIR, model_name)
    os.makedirs(model_dir, exist_ok=True)
    
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            # Check if it has a single top-level directory or directly files
            top_level_items = set(p.split('/')[0] for p in zip_ref.namelist())
            
            # Extract
            zip_ref.extractall(model_dir)
            
            # If the zip had a single wrapper folder (e.g. faster-whisper-turbo/), move files up
            if len(top_level_items) == 1:
                wrapper_folder = list(top_level_items)[0]
                wrapper_path = os.path.join(model_dir, wrapper_folder)
                if os.path.isdir(wrapper_path):
                    for item in os.listdir(wrapper_path):
                        shutil.move(os.path.join(wrapper_path, item), model_dir)
                    os.rmdir(wrapper_path)
            
        # Verify model files exist depending on engine
        if engine == "whisper":
            if not os.path.exists(os.path.join(model_dir, "model.bin")):
                raise ValueError("ZIP does not contain 'model.bin'. Is this a valid CTranslate2 Faster-Whisper model?")
        elif engine == "llama":
            if not any(f.endswith(".gguf") for f in os.listdir(model_dir)):
                raise ValueError("ZIP does not contain a .gguf file. Is this a valid LLaMA model?")
                
        # Register model
        size = sum(
            os.path.getsize(os.path.join(dp, f))
            for dp, _, fnames in os.walk(model_dir)
            for f in fnames
        )
        
        model = db.register_model(
            name=model_name,
            engine=engine,
            language="multi",
            path=model_dir,
            size_bytes=size,
            is_default=False,
        )
        
        return model
    except Exception as e:
        # Cleanup on failure
        if os.path.isdir(model_dir):
            shutil.rmtree(model_dir, ignore_errors=True)
        raise e


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
