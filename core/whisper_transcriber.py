"""Faster-Whisper offline transcription engine (no API, local inference).

NOTE: For RAM-efficient transcription of long videos, use core.whisper_chunked
instead. This module is kept for backward compatibility with short videos.
"""

from __future__ import annotations
import os
import subprocess
import sys
import tempfile
import asyncio
from typing import AsyncGenerator, Optional

from models.subtitle import WordTiming


async def transcribe_whisper(
    video_path: str,
    model_size: str = "large-v3-turbo",
    language: str = "hi",
    device: str = "cpu",
    compute_type: str = "int8",
) -> AsyncGenerator[tuple[int, str, Optional[list[WordTiming]]], None]:
    """Async generator that transcribes using faster-whisper locally.

    Yields:
        (progress_percent, status_message, word_timings_or_none)
    """
    yield (5, "Extracting audio from video…", None)
    wav_path = await asyncio.to_thread(_extract_audio, video_path)

    yield (10, "Loading Whisper model (this may take a moment first time)…", None)

    def _load_and_transcribe():
        from faster_whisper import WhisperModel

        model = WhisperModel(model_size, device=device, compute_type=compute_type)

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

    yield (15, "Transcribing with Whisper (local inference)…", None)
    words = await asyncio.to_thread(_load_and_transcribe)

    # Cleanup
    try:
        os.remove(wav_path)
    except OSError:
        pass

    yield (100, "Whisper transcription complete.", words)


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
