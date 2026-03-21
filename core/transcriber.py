"""Vosk STT transcription engine — async version without PySide6 dependencies."""

from __future__ import annotations
import json
import os
import subprocess
import sys
import tempfile
import wave
import asyncio
from typing import AsyncGenerator, Optional

from vosk import Model, KaldiRecognizer

from models.subtitle import WordTiming

# Path to the Vosk Hindi model (relative to project root)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_MODEL_PATH = os.path.join(_PROJECT_ROOT, "vosk-model-hi-0.22")


async def transcribe_vosk(
    video_path: str,
    model_path: str = DEFAULT_MODEL_PATH,
    sample_rate: int = 16000,
) -> AsyncGenerator[tuple[int, str, Optional[list[WordTiming]]], None]:
    """Async generator that transcribes a video file to word-level timings.

    Yields:
        (progress_percent, status_message, word_timings_or_none)
        When progress == 100, word_timings will contain the final results.
    """
    # Step 1 — extract audio
    yield (5, "Extracting audio from video…", None)
    wav_path = await asyncio.to_thread(_extract_audio, video_path, sample_rate)

    # Step 2 — load model
    yield (10, "Loading Vosk model…", None)
    if not os.path.isdir(model_path):
        raise RuntimeError(f"Vosk model not found at: {model_path}")

    model = await asyncio.to_thread(Model, model_path)

    # Step 3 — recognise
    yield (15, "Transcribing audio…", None)

    def _do_recognition():
        return _recognise_with_partials(model, wav_path, sample_rate)

    words, progress_gen = await asyncio.to_thread(
        _recognise_with_progress, model, wav_path, sample_rate
    )

    yield (100, "Transcription complete.", words)

    # Cleanup temp wav
    try:
        os.remove(wav_path)
    except OSError:
        pass


def _extract_audio(video_path: str, sample_rate: int) -> str:
    """Extract 16 kHz mono WAV from video using FFmpeg."""
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-ar", str(sample_rate),
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


def _recognise_with_progress(
    model: Model, wav_path: str, sample_rate: int,
) -> tuple[list[WordTiming], None]:
    """Run Vosk recogniser collecting word-level timings from every result chunk."""
    wf = wave.open(wav_path, "rb")
    rec = KaldiRecognizer(model, wf.getframerate())
    rec.SetWords(True)
    words: list[WordTiming] = []
    chunk_size = 4000  # ~0.25 s at 16 kHz

    while True:
        data = wf.readframes(chunk_size)
        if len(data) == 0:
            break
        if rec.AcceptWaveform(data):
            res = json.loads(rec.Result())
            words.extend(_parse_result(res))

    final = json.loads(rec.FinalResult())
    words.extend(_parse_result(final))
    wf.close()
    return words, None


def _recognise_with_partials(
    model: Model, wav_path: str, sample_rate: int,
) -> list[WordTiming]:
    """Run Vosk recogniser collecting word-level timings from every result chunk."""
    wf = wave.open(wav_path, "rb")
    rec = KaldiRecognizer(model, wf.getframerate())
    rec.SetWords(True)
    words: list[WordTiming] = []
    chunk_size = 4000

    while True:
        data = wf.readframes(chunk_size)
        if len(data) == 0:
            break
        if rec.AcceptWaveform(data):
            res = json.loads(rec.Result())
            words.extend(_parse_result(res))

    final = json.loads(rec.FinalResult())
    words.extend(_parse_result(final))
    wf.close()
    return words


def _parse_result(result: dict) -> list[WordTiming]:
    """Parse Vosk JSON result into WordTiming objects."""
    out: list[WordTiming] = []
    for r in result.get("result", []):
        out.append(WordTiming(
            word=r["word"],
            start_time=r["start"],
            end_time=r["end"],
            confidence=r.get("conf", 1.0),
        ))
    return out
