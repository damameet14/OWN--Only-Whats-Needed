"""Faster-Whisper offline transcription engine (local inference).

Optimized for CPU with multi-threading and high accuracy.
"""

from __future__ import annotations
import logging
import os
import subprocess
import sys
import tempfile
import asyncio
from typing import AsyncGenerator, Optional, Callable

# Mocking WordTiming for context if not imported
from dataclasses import dataclass
@dataclass
class WordTiming:
    word: str
    start_time: float
    end_time: float
    confidence: float

logger = logging.getLogger(__name__)

async def transcribe_whisper(
    video_path: str,
    model_path: str = None,
    model_size: str = "large-v3-turbo",
    language: str = "hi",
    device: str = "cpu",
    compute_type: str = "int8",
    cpu_threads: int = 4, 
    progress_callback: Optional[Callable[[int, str], None]] = None,
) -> AsyncGenerator[tuple[int, str, Optional[list[WordTiming]]], None]:
    """Async generator that transcribes using faster-whisper locally.
    """
    logger.info(
        f"[WHISPER] START: video_path={video_path}, model_path={model_path}, "
        f"model_size={model_size}, language={language}"
    )

    if not os.path.exists(video_path):
        logger.error(f"[WHISPER] Video file not found: {video_path}")
        yield (0, f"Error: Video file not found: {video_path}", None)
        return

    def _update(pct: int, msg: str) -> None:
        logger.debug(f"[WHISPER] Progress: {pct}% - {msg}")
        if progress_callback is not None:
            progress_callback(pct, msg)

    # Step 1 — extract audio
    yield (5, "Extracting audio from video…", None)
    _update(5, "Extracting audio from video…")
    try:
        wav_path = await asyncio.to_thread(_extract_audio, video_path)
        logger.info(f"[WHISPER] Audio extracted to: {wav_path}")
    except Exception as e:
        logger.error(f"[WHISPER] Audio extraction failed: {e}", exc_info=True)
        yield (0, f"Error extracting audio: {e}", None)
        return

    # Step 2 — load model
    yield (15, "Loading Whisper model…", None)
    _update(15, "Loading Whisper model…")

    def _load_model():
        from faster_whisper import WhisperModel
        target = model_path if model_path else model_size
        logger.info(f"[WHISPER] Loading model from: {target} using {cpu_threads} threads")
        return WhisperModel(
            target, 
            device=device, 
            compute_type=compute_type, 
            cpu_threads=cpu_threads,
            num_workers=cpu_threads
        )

    try:
        model = await asyncio.to_thread(_load_model)
        logger.info("[WHISPER] Model loaded successfully")
    except Exception as e:
        logger.error(f"[WHISPER] Model loading failed: {e}", exc_info=True)
        yield (0, f"Error loading Whisper model: {e}", None)
        if os.path.exists(wav_path): os.remove(wav_path)
        return

    # Step 3 — transcribe
    yield (25, "Transcribing with Whisper…", None)
    _update(25, "Transcribing with Whisper…")

    def _run_transcription():
        effective_language = language if language not in ("multi", "auto", "") else None
        
        # Prompt to ensure accuracy and no translation
        initial_prompt = "Transcribe the audio exactly as spoken in the original language."

        segments, info = model.transcribe(
            wav_path,
            language=effective_language,
            word_timestamps=True,
            initial_prompt=initial_prompt,
            beam_size=5,       # High accuracy
            vad_filter=True    # Speed up by skipping silence
        )
        
        logger.info(f"[WHISPER] Detected language: {info.language} (prob={info.language_probability:.2f})")

        words: list[WordTiming] = []
        for segment in segments:
            if segment.words:
                for w in segment.words:
                    words.append(WordTiming(
                        word=w.word.strip(),
                        start_time=w.start,
                        end_time=w.end,
                        confidence=w.probability,
                    ))
        return words

    try:
        words = await asyncio.to_thread(_run_transcription)
        logger.info(f"[WHISPER] Transcription done: {len(words)} words")
    except Exception as e:
        logger.error(f"[WHISPER] Transcription failed: {e}", exc_info=True)
        yield (0, f"Error during transcription: {e}", None)
        return
    finally:
        if os.path.exists(wav_path): os.remove(wav_path)

    yield (100, "Transcription complete.", words)
    _update(100, "Transcription complete.")

def _extract_audio(video_path: str) -> str:
    """Convert video to whisper-compatible 16 kHz mono WAV."""
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    from server.config import get_ffmpeg_path
    cmd = [
        get_ffmpeg_path(), "-y",
        "-i", video_path,
        "-ar", "16000",
        "-ac", "1",
        "-c:a", "pcm_s16le",
        tmp.name,
    ]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg failed: {result.stderr.decode()}")
    return tmp.name