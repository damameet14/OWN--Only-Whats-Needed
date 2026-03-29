"""Chunked Whisper transcription with RAM management."""

from __future__ import annotations
import os
import subprocess
import sys
import tempfile
import wave
import asyncio
from typing import AsyncGenerator, Optional, Callable

from models.subtitle import WordTiming
from core.silence_detector import detect_silence_boundaries
from server.config import (
    WHISPER_MAX_CHUNK_DURATION,
    WHISPER_MIN_SILENCE_DURATION,
    WHISPER_SILENCE_THRESHOLD,
)


async def transcribe_whisper_chunked(
    video_path: str,
    model_size: str = "large-v3-turbo",
    language: str = "hi",
    device: str = "cpu",
    compute_type: str = "int8",
    max_chunk_duration: float = WHISPER_MAX_CHUNK_DURATION,
    progress_callback: Optional[Callable[[int, str], None]] = None,
) -> AsyncGenerator[tuple[int, str, Optional[list[WordTiming]]], None]:
    """Async generator that transcribes using Whisper with chunked processing.

    Processes audio in ~30-second chunks at silence boundaries to manage RAM usage.
    The Whisper model is loaded once and reused across chunks.

    Yields:
        (progress_percent, status_message, word_timings_or_none)
        When progress == 100, word_timings will contain the final results.
    """
    # Step 1 — extract audio (5%)
    yield (5, "Extracting audio from video…", None)
    wav_path = await asyncio.to_thread(_extract_audio, video_path)

    # Step 2 — detect silence boundaries (10%)
    yield (15, "Detecting silence for chunking…", None)
    chunks = await detect_silence_boundaries(
        wav_path,
        min_silence_duration=WHISPER_MIN_SILENCE_DURATION,
        silence_threshold=WHISPER_SILENCE_THRESHOLD,
        max_chunk_duration=max_chunk_duration,
    )

    # Step 3 — load model (5%)
    yield (20, "Loading Whisper model…", None)

    def _load_model():
        from faster_whisper import WhisperModel
        return WhisperModel(model_size, device=device, compute_type=compute_type)

    model = await asyncio.to_thread(_load_model)

    # Step 4 — transcribe chunks (80%)
    yield (25, f"Transcribing {len(chunks)} chunks…", None)

    all_words: list[WordTiming] = []
    total_chunks = len(chunks)

    for chunk_idx, (chunk_start, chunk_end) in enumerate(chunks):
        chunk_progress = 25 + int((chunk_idx / total_chunks) * 75)
        yield (chunk_progress, f"Processing chunk {chunk_idx + 1}/{total_chunks}…", None)

        # Extract chunk audio
        chunk_wav = await asyncio.to_thread(
            _extract_chunk_audio,
            wav_path,
            chunk_start,
            chunk_end,
        )

        # Transcribe chunk
        chunk_words = await asyncio.to_thread(
            _transcribe_chunk,
            model,
            chunk_wav,
            language,
        )

        # Adjust timestamps by chunk offset
        for word in chunk_words:
            word.start_time += chunk_start
            word.end_time += chunk_start

        all_words.extend(chunk_words)

        # Clean up chunk wav
        try:
            os.remove(chunk_wav)
        except OSError:
            pass

    # Cleanup main wav
    try:
        os.remove(wav_path)
    except OSError:
        pass

    yield (100, "Transcription complete.", all_words)


def _extract_audio(video_path: str) -> str:
    """Extract 16 kHz mono WAV from video."""
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-ar", "16000",
        "-ac", "1",
        "-f", "wav",
        tmp.name,
    ]
    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"FFmpeg audio extraction failed:\n{result.stderr.decode(errors='replace')}"
        )
    return tmp.name


def _extract_chunk_audio(wav_path: str, start_time: float, end_time: float) -> str:
    """Extract a chunk from WAV file."""
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    duration = end_time - start_time

    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start_time),
        "-i", wav_path,
        "-t", str(duration),
        "-c", "copy",
        tmp.name,
    ]
    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"FFmpeg chunk extraction failed:\n{result.stderr.decode(errors='replace')}"
        )
    return tmp.name


def _transcribe_chunk(model, wav_path: str, language: str) -> list[WordTiming]:
    """Transcribe a single audio chunk with Whisper."""
    segments, info = model.transcribe(
        wav_path,
        language=language,
        word_timestamps=True,
        beam_size=5,
        vad_filter=True,
    )

    words: list[WordTiming] = []
    for segment in segments:
        if segment.words:
            for word_info in segment.words:
                words.append(WordTiming(
                    word=word_info.word.strip(),
                    start_time=word_info.start,
                    end_time=word_info.end,
                    confidence=word_info.probability,
                ))

    return words
