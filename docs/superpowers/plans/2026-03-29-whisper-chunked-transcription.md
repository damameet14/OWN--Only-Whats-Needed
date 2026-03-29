# Whisper Chunked Transcription Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Whisper Large v3 Turbo transcription support with RAM-efficient 30-second chunked processing using silence detection for intelligent chunk boundaries.

**Architecture:** Extract audio once, detect silence points with FFmpeg, split into ~30s chunks at pause boundaries, process each chunk sequentially with Whisper (model loaded once), merge word timings with timestamp adjustments.

**Tech Stack:** Python, FastAPI, faster-whisper, FFmpeg, WebSockets, HTML/JS

---

## File Structure

**New Files:**
- `core/silence_detector.py` - Silence detection using FFmpeg
- `core/whisper_chunked.py` - Chunked Whisper transcriber

**Modified Files:**
- `server/config.py` - Add Whisper configuration constants
- `server/app.py` - Update transcription endpoint for engine/model selection
- `web/editor.html` - Add model selection UI to transcription modal
- `web/js/editor.js` - Handle model selection and download
- `web/js/api.js` - Add model-related API calls

---

## Task 1: Add Whisper Configuration

**Files:**
- Modify: `server/config.py`

- [ ] **Step 1: Add Whisper configuration constants**

Add these constants to `server/config.py` after the existing configuration:

```python
# ── Whisper chunked transcription settings ────────────────────────────────
WHISPER_MAX_CHUNK_DURATION = 30.0      # Maximum chunk duration in seconds
WHISPER_MIN_SILENCE_DURATION = 0.5     # Minimum silence duration to split at
WHISPER_SILENCE_THRESHOLD = -40.0      # Silence threshold in dB
```

- [ ] **Step 2: Commit**

```bash
git add server/config.py
git commit -m "feat: add Whisper chunked transcription configuration"
```

---

## Task 2: Implement Silence Detection Module

**Files:**
- Create: `core/silence_detector.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_silence_detector.py`:

```python
"""Tests for silence detection module."""

import pytest
import os
import tempfile
import wave
import struct
import asyncio
from core.silence_detector import detect_silence_boundaries


def create_test_wav(path: str, duration: float, sample_rate: int = 16000):
    """Create a test WAV file with alternating silence and audio."""
    with wave.open(path, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)

        # Create pattern: 5s audio, 1s silence, 5s audio, 1s silence, 5s audio
        pattern_duration = 12.0
        samples_per_pattern = int(pattern_duration * sample_rate)

        for i in range(samples_per_pattern):
            # 5s audio (sine wave), 1s silence (zeros), repeat
            pos_in_pattern = i % int(pattern_duration * sample_rate)
            pos_in_6s = pos_in_pattern % int(6.0 * sample_rate)

            if pos_in_6s < int(5.0 * sample_rate):
                # Audio: sine wave
                t = pos_in_6s / sample_rate
                value = int(32767 * 0.5 * (1 + (0.5 * (1 - 2 * (t % 1)))))
            else:
                # Silence
                value = 0

            wf.writeframes(struct.pack('<h', value))


@pytest.mark.asyncio
async def test_detect_silence_boundaries_basic():
    """Test basic silence detection with known pattern."""
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
        wav_path = tmp.name

    try:
        create_test_wav(wav_path, duration=12.0)

        chunks = await detect_silence_boundaries(
            wav_path,
            min_silence_duration=0.5,
            silence_threshold=-40.0,
            max_chunk_duration=30.0
        )

        # Should have 3 chunks (5s audio each, split at silence)
        assert len(chunks) == 3

        # Check first chunk
        assert chunks[0][0] == 0.0
        assert 4.5 <= chunks[0][1] <= 5.5  # Around 5 seconds

        # Check second chunk
        assert 5.5 <= chunks[1][0] <= 6.5
        assert 10.5 <= chunks[1][1] <= 11.5

        # Check third chunk
        assert 11.0 <= chunks[2][0] <= 12.0
        assert chunks[2][1] <= 12.5

    finally:
        if os.path.exists(wav_path):
            os.remove(wav_path)


@pytest.mark.asyncio
async def test_detect_silence_no_silence_fallback():
    """Test fallback to fixed chunks when no silence detected."""
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
        wav_path = tmp.name

    try:
        # Create continuous audio (no silence)
        with wave.open(wav_path, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)

            for i in range(int(60 * 16000)):
                value = int(32767 * 0.5 * (1 + (0.5 * (1 - 2 * ((i / 16000) % 1)))))
                wf.writeframes(struct.pack('<h', value))

        chunks = await detect_silence_boundaries(
            wav_path,
            min_silence_duration=0.5,
            silence_threshold=-40.0,
            max_chunk_duration=30.0
        )

        # Should fall back to 2 fixed 30s chunks
        assert len(chunks) == 2
        assert chunks[0] == (0.0, 30.0)
        assert chunks[1] == (30.0, 60.0)

    finally:
        if os.path.exists(wav_path):
            os.remove(wav_path)


@pytest.mark.asyncio
async def test_detect_silence_max_chunk_enforced():
    """Test that max_chunk_duration is enforced."""
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
        wav_path = tmp.name

    try:
        # Create 90 seconds of audio with silence at 30s and 60s
        with wave.open(wav_path, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)

            for i in range(int(90 * 16000)):
                # Add silence at 30s and 60s
                pos = i / 16000
                if 29.5 < pos < 30.5 or 59.5 < pos < 60.5:
                    value = 0
                else:
                    value = int(32767 * 0.5)
                wf.writeframes(struct.pack('<h', value))

        chunks = await detect_silence_boundaries(
            wav_path,
            min_silence_duration=0.5,
            silence_threshold=-40.0,
            max_chunk_duration=30.0
        )

        # Should have 3 chunks, each ~30s
        assert len(chunks) == 3
        for start, end in chunks:
            assert end - start <= 30.0

    finally:
        if os.path.exists(wav_path):
            os.remove(wav_path)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_silence_detector.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'core.silence_detector'"

- [ ] **Step 3: Write minimal implementation**

Create `core/silence_detector.py`:

```python
"""Silence detection module for intelligent audio chunking."""

from __future__ import annotations
import os
import subprocess
import sys
import re
import asyncio
from typing import Optional, Callable


async def detect_silence_boundaries(
    wav_path: str,
    min_silence_duration: float = 0.5,
    silence_threshold: float = -40.0,
    max_chunk_duration: float = 30.0,
) -> list[tuple[float, float]]:
    """Detect silence boundaries in audio for intelligent chunking.

    Uses FFmpeg's silencedetect filter to find silence regions, then
    generates chunk boundaries at midpoints of those regions.

    Args:
        wav_path: Path to WAV audio file
        min_silence_duration: Minimum silence duration to consider as a split point (seconds)
        silence_threshold: Silence threshold in dB (more negative = more sensitive)
        max_chunk_duration: Maximum duration for any chunk (seconds)

    Returns:
        List of (start_time, end_time) tuples for each chunk
    """
    # Get audio duration first
    duration = await _get_audio_duration(wav_path)

    if duration <= max_chunk_duration:
        # No need to chunk
        return [(0.0, duration)]

    # Run FFmpeg silence detection
    silence_regions = await _detect_silence_with_ffmpeg(
        wav_path, min_silence_duration, silence_threshold
    )

    if not silence_regions:
        # No silence found, fall back to fixed chunks
        return _create_fixed_chunks(duration, max_chunk_duration)

    # Generate chunk boundaries at silence midpoints
    chunks = _create_chunks_from_silence(
        duration, silence_regions, max_chunk_duration
    )

    return chunks


async def _get_audio_duration(wav_path: str) -> float:
    """Get audio duration using FFprobe."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        wav_path
    ]

    result = await asyncio.to_thread(
        subprocess.run,
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )

    if result.returncode != 0:
        raise RuntimeError(f"Failed to get audio duration: {result.stderr.decode()}")

    return float(result.stdout.decode().strip())


async def _detect_silence_with_ffmpeg(
    wav_path: str,
    min_silence_duration: float,
    silence_threshold: float,
) -> list[tuple[float, float]]:
    """Run FFmpeg silencedetect and parse output."""
    cmd = [
        "ffmpeg", "-v", "error",
        "-i", wav_path,
        "-af", f"silencedetect=noise={silence_threshold}dB:duration={min_silence_duration}",
        "-f", "null",
        "-"
    ]

    result = await asyncio.to_thread(
        subprocess.run,
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )

    if result.returncode != 0:
        # FFmpeg returns non-zero even on success with null output
        # Check if stderr contains silence detection info
        stderr = result.stderr.decode(errors="replace")

    stderr = result.stderr.decode(errors="replace")

    # Parse silence detection output
    silence_regions = []

    # Pattern: silence_start: <time>, silence_end: <time>, silence_duration: <time>
    silence_start_pattern = re.compile(r"silence_start:\s*([\d.]+)")
    silence_end_pattern = re.compile(r"silence_end:\s*([\d.]+)")

    lines = stderr.split('\n')
    current_start = None

    for line in lines:
        start_match = silence_start_pattern.search(line)
        if start_match:
            current_start = float(start_match.group(1))
            continue

        end_match = silence_end_pattern.search(line)
        if end_match and current_start is not None:
            current_end = float(end_match.group(1))
            silence_regions.append((current_start, current_end))
            current_start = None

    return silence_regions


def _create_chunks_from_silence(
    duration: float,
    silence_regions: list[tuple[float, float]],
    max_chunk_duration: float,
) -> list[tuple[float, float]]:
    """Create chunks by splitting at silence midpoints."""
    chunks = []
    current_start = 0.0

    for silence_start, silence_end in silence_regions:
        # Split at midpoint of silence
        split_point = (silence_start + silence_end) / 2

        # Only split if we have enough audio and chunk would be too long
        if split_point > current_start and (split_point - current_start) > 1.0:
            chunk_end = min(split_point, current_start + max_chunk_duration)
            chunks.append((current_start, chunk_end))
            current_start = chunk_end

    # Add final chunk
    if current_start < duration:
        chunks.append((current_start, duration))

    # Merge any chunks that are too small (< 1 second)
    merged_chunks = []
    for i, (start, end) in enumerate(chunks):
        if i == 0:
            merged_chunks.append([start, end])
        else:
            prev_start, prev_end = merged_chunks[-1]
            if (start - prev_end) < 1.0:
                # Merge with previous
                merged_chunks[-1][1] = end
            else:
                merged_chunks.append([start, end])

    return [(s, e) for s, e in merged_chunks]


def _create_fixed_chunks(
    duration: float,
    max_chunk_duration: float,
) -> list[tuple[float, float]]:
    """Create fixed-duration chunks when no silence detected."""
    chunks = []
    current_start = 0.0

    while current_start < duration:
        chunk_end = min(current_start + max_chunk_duration, duration)
        chunks.append((current_start, chunk_end))
        current_start = chunk_end

    return chunks
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_silence_detector.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/silence_detector.py tests/test_silence_detector.py
git commit -m "feat: implement silence detection for audio chunking"
```

---

## Task 3: Implement Chunked Whisper Transcriber

**Files:**
- Create: `core/whisper_chunked.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_whisper_chunked.py`:

```python
"""Tests for chunked Whisper transcriber."""

import pytest
import os
import tempfile
import wave
import struct
import asyncio
from core.whisper_chunked import transcribe_whisper_chunked


def create_test_video_wav(path: str, duration: float, sample_rate: int = 16000):
    """Create a test WAV file with simple audio pattern."""
    with wave.open(path, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)

        samples = int(duration * sample_rate)
        for i in range(samples):
            # Simple sine wave pattern
            t = i / sample_rate
            value = int(32767 * 0.3 * (1 + (0.5 * (1 - 2 * (t % 1)))))
            wf.writeframes(struct.pack('<h', value))


@pytest.mark.asyncio
async def test_transcribe_whisper_chunked_progress_updates():
    """Test that progress updates are yielded correctly."""
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
        wav_path = tmp.name

    try:
        create_test_video_wav(wav_path, duration=10.0)

        progress_updates = []
        final_words = None

        async for progress, message, result in transcribe_whisper_chunked(
            wav_path,
            model_size="tiny",  # Use tiny for faster test
            language="en",
            max_chunk_duration=5.0,
        ):
            progress_updates.append((progress, message))
            if result is not None:
                final_words = result

        # Should have progress updates
        assert len(progress_updates) > 0

        # Should end at 100%
        assert progress_updates[-1][0] == 100

        # Should have final result
        assert final_words is not None

        # Words should have timing info
        for word in final_words:
            assert hasattr(word, 'word')
            assert hasattr(word, 'start_time')
            assert hasattr(word, 'end_time')
            assert word.start_time >= 0
            assert word.end_time >= word.start_time

    finally:
        if os.path.exists(wav_path):
            os.remove(wav_path)


@pytest.mark.asyncio
async def test_transcribe_whisper_chunked_timestamp_adjustment():
    """Test that word timestamps are adjusted for chunk offsets."""
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
        wav_path = tmp.name

    try:
        # Create 20 seconds of audio
        create_test_video_wav(wav_path, duration=20.0)

        final_words = None

        async for progress, message, result in transcribe_whisper_chunked(
            wav_path,
            model_size="tiny",
            language="en",
            max_chunk_duration=10.0,
        ):
            if result is not None:
                final_words = result

        assert final_words is not None

        # Check that timestamps span the full duration
        if final_words:
            max_time = max(w.end_time for w in final_words)
            assert max_time > 10.0  # Should have words from second chunk

    finally:
        if os.path.exists(wav_path):
            os.remove(wav_path)


@pytest.mark.asyncio
async def test_transcribe_whisper_chunked_cleanup():
    """Test that temporary files are cleaned up."""
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
        wav_path = tmp.name

    try:
        create_test_video_wav(wav_path, duration=5.0)

        # Get temp directory before transcription
        temp_dir = tempfile.gettempdir()
        temp_files_before = set(os.listdir(temp_dir))

        async for progress, message, result in transcribe_whisper_chunked(
            wav_path,
            model_size="tiny",
            language="en",
            max_chunk_duration=30.0,
        ):
            pass

        # Check temp files after (allow some tolerance for other processes)
        temp_files_after = set(os.listdir(temp_dir))
        new_files = temp_files_after - temp_files_before

        # Should not have lingering temp files from our process
        # (filter out files that might be from other processes)
        wav_temp_files = [f for f in new_files if f.endswith('.wav')]
        assert len(wav_temp_files) == 0

    finally:
        if os.path.exists(wav_path):
            os.remove(wav_path)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_whisper_chunked.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'core.whisper_chunked'"

- [ ] **Step 3: Write minimal implementation**

Create `core/whisper_chunked.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_whisper_chunked.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/whisper_chunked.py tests/test_whisper_chunked.py
git commit -m "feat: implement chunked Whisper transcriber with RAM management"
```

---

## Task 4: Update API for Engine/Model Selection

**Files:**
- Modify: `server/app.py`

- [ ] **Step 1: Update transcription endpoint to accept engine and model**

In `server/app.py`, modify the `_run_transcription` function to use chunked Whisper:

```python
async def _run_transcription(task_id: str, project: dict, engine: str, language: str):
    """Background task for transcription."""
    try:
        video_path = project["video_path"]

        if engine == "whisper":
            from core.whisper_chunked import transcribe_whisper_chunked

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

            gen = transcribe_whisper_chunked(
                video_path,
                model_size=model_size,
                language=language,
            )
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
```

- [ ] **Step 2: Add model parameter to transcription endpoint**

Update the `start_transcription` endpoint in `server/app.py`:

```python
@app.post("/api/projects/{project_id}/transcribe")
async def start_transcription(project_id: int, body: dict = None):
    """Start transcription for a project. Returns a task_id for progress tracking."""
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    body = body or {}
    engine = body.get("engine", "vosk")  # "vosk" or "whisper"
    model = body.get("model")  # Optional specific model name
    language = body.get("language", project.get("language", "hi"))

    # Validate model is installed if specified
    if model:
        models = db.list_models()
        model_found = False
        for m in models:
            if m["name"] == model:
                model_found = True
                break
        if not model_found:
            raise HTTPException(400, f"Model '{model}' not installed. Please download it first.")

    task_id = uuid.uuid4().hex
    _tasks[task_id] = {"percent": 0, "message": "Starting...", "result": None}
    _task_events[task_id] = asyncio.Event()

    # Run transcription in background
    asyncio.create_task(_run_transcription(task_id, project, engine, language))

    db.update_project(project_id, status="transcribing")
    return {"task_id": task_id}
```

- [ ] **Step 3: Commit**

```bash
git add server/app.py
git commit -m "feat: update API for Whisper engine and model selection"
```

---

## Task 5: Add Model Selection API to Frontend

**Files:**
- Modify: `web/js/api.js`

- [ ] **Step 1: Add model-related API functions**

Add these functions to `web/js/api.js`:

```javascript
// ── Model API ───────────────────────────────────────────────────────────────

/**
 * Get list of available models with install status
 */
async function getAvailableModels() {
    const response = await fetch('/api/models/available');
    if (!response.ok) throw new Error('Failed to get available models');
    return await response.json();
}

/**
 * Get list of installed models
 */
async function getInstalledModels() {
    const response = await fetch('/api/models');
    if (!response.ok) throw new Error('Failed to get installed models');
    return await response.json();
}

/**
 * Download a model
 * @param {string} modelName - Name of the model to download
 * @param {function} onProgress - Callback for progress updates (percent, message)
 */
async function downloadModel(modelName, onProgress) {
    const { task_id } = await fetch('/api/models/download', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: modelName })
    }).then(r => r.json());

    return watchProgress(task_id,
        (data) => {
            if (onProgress) onProgress(data.percent, data.message);
        },
        (data) => {
            // Download complete
        },
        (error) => {
            throw new Error(error);
        }
    );
}

/**
 * Delete a model
 * @param {number} modelId - ID of the model to delete
 */
async function deleteModel(modelId) {
    const response = await fetch(`/api/models/${modelId}`, {
        method: 'DELETE'
    });
    if (!response.ok) throw new Error('Failed to delete model');
    return await response.json();
}
```

- [ ] **Step 2: Commit**

```bash
git add web/js/api.js
git commit -m "feat: add model API functions to frontend"
```

---

## Task 6: Add Model Selection UI to Editor

**Files:**
- Modify: `web/editor.html`

- [ ] **Step 1: Add model selection dropdown to transcription modal**

Find the transcription modal in `web/editor.html` and add the model selection UI. Add this after the existing transcription controls:

```html
<!-- Model Selection Section -->
<div class="mb-4">
    <label class="block text-sm font-medium text-slate-300 mb-2">Transcription Engine</label>
    <select id="transcribe-engine" class="w-full bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-primary">
        <option value="vosk">Vosk (Hindi)</option>
        <option value="whisper">Whisper (Multilingual)</option>
    </select>
</div>

<div id="whisper-model-section" class="mb-4 hidden">
    <label class="block text-sm font-medium text-slate-300 mb-2">Whisper Model</label>
    <select id="transcribe-model" class="w-full bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-primary">
        <option value="large-v3-turbo">Large v3 Turbo (800MB) - Recommended</option>
        <option value="large-v3">Large v3 (3GB) - Higher Accuracy</option>
    </select>
    <div id="model-status" class="mt-2 text-xs text-slate-400"></div>
    <button id="download-model-btn" class="mt-2 w-full bg-slate-700 hover:bg-slate-600 text-white text-sm py-2 px-4 rounded-lg hidden">
        Download Model
    </button>
</div>
```

- [ ] **Step 2: Commit**

```bash
git add web/editor.html
git commit -m "feat: add model selection UI to transcription modal"
```

---

## Task 7: Implement Model Selection Logic in Editor

**Files:**
- Modify: `web/js/editor.js`

- [ ] **Step 1: Add model selection event handlers**

Add this code to `web/js/editor.js` after the existing initialization code:

```javascript
// ── Model Selection ───────────────────────────────────────────────────────────

let availableModels = [];
let installedModels = [];

async function initModelSelection() {
    try {
        availableModels = await getAvailableModels();
        installedModels = await getInstalledModels();
        updateModelUI();
    } catch (err) {
        console.error('Failed to load models:', err);
    }
}

function updateModelUI() {
    const engineSelect = document.getElementById('transcribe-engine');
    const whisperSection = document.getElementById('whisper-model-section');
    const modelSelect = document.getElementById('transcribe-model');
    const modelStatus = document.getElementById('model-status');
    const downloadBtn = document.getElementById('download-model-btn');

    if (!engineSelect) return;

    // Show/hide Whisper section based on engine selection
    engineSelect.addEventListener('change', () => {
        if (engineSelect.value === 'whisper') {
            whisperSection.classList.remove('hidden');
            updateWhisperModelStatus();
        } else {
            whisperSection.classList.add('hidden');
        }
    });

    // Update Whisper model status
    updateWhisperModelStatus();

    // Download button handler
    downloadBtn.addEventListener('click', async () => {
        const modelName = modelSelect.value;
        downloadBtn.disabled = true;
        downloadBtn.textContent = 'Downloading...';
        modelStatus.textContent = 'Starting download...';

        try {
            await downloadModel(modelName, (percent, message) => {
                downloadBtn.textContent = `Downloading ${percent}%`;
                modelStatus.textContent = message;
            });

            // Refresh model list
            installedModels = await getInstalledModels();
            updateWhisperModelStatus();
            showToast('Model downloaded successfully!');
        } catch (err) {
            modelStatus.textContent = `Error: ${err.message}`;
            downloadBtn.disabled = false;
            downloadBtn.textContent = 'Download Model';
        }
    });
}

function updateWhisperModelStatus() {
    const modelSelect = document.getElementById('transcribe-model');
    const modelStatus = document.getElementById('model-status');
    const downloadBtn = document.getElementById('download-model-btn');

    if (!modelSelect) return;

    const selectedModel = modelSelect.value;
    const installed = installedModels.find(m => m.name.includes(selectedModel));

    if (installed) {
        modelStatus.textContent = '✓ Model installed';
        modelStatus.classList.add('text-green-400');
        modelStatus.classList.remove('text-red-400');
        downloadBtn.classList.add('hidden');
    } else {
        const modelInfo = availableModels.find(m => m.name.includes(selectedModel));
        if (modelInfo) {
            modelStatus.textContent = `Model not installed (${modelInfo.size_mb} MB)`;
            modelStatus.classList.remove('text-green-400');
            modelStatus.classList.add('text-red-400');
            downloadBtn.classList.remove('hidden');
            downloadBtn.disabled = false;
            downloadBtn.textContent = 'Download Model';
        }
    }
}

// Initialize model selection on page load
document.addEventListener('DOMContentLoaded', () => {
    initModelSelection();
});
```

- [ ] **Step 2: Update transcription start to use selected engine and model**

Find the transcription start handler in `web/js/editor.js` and update it to include engine and model:

```javascript
// In the transcription start handler (find where startTranscription is called)
const engine = document.getElementById('transcribe-engine')?.value || 'vosk';
const model = document.getElementById('transcribe-model')?.value || null;

const { task_id } = await startTranscription(project.id, { engine, model });
```

- [ ] **Step 3: Commit**

```bash
git add web/js/editor.js
git commit -m "feat: implement model selection logic in editor"
```

---

## Task 8: Update Existing Whisper Transcriber for Compatibility

**Files:**
- Modify: `core/whisper_transcriber.py`

- [ ] **Step 1: Add deprecation notice and redirect to chunked version**

Add this comment at the top of `core/whisper_transcriber.py`:

```python
"""Faster-Whisper offline transcription engine (no API, local inference).

NOTE: For RAM-efficient transcription of long videos, use core.whisper_chunked
instead. This module is kept for backward compatibility with short videos.
"""
```

- [ ] **Step 2: Commit**

```bash
git add core/whisper_transcriber.py
git commit -m "docs: add deprecation notice to whisper_transcriber"
```

---

## Task 9: Integration Testing

**Files:**
- Create: `tests/test_integration_whisper.py`

- [ ] **Step 1: Write integration test**

Create `tests/test_integration_whisper.py`:

```python
"""Integration tests for Whisper chunked transcription."""

import pytest
import os
import tempfile
import asyncio
from core.whisper_chunked import transcribe_whisper_chunked
from models.subtitle import SubtitleTrack


@pytest.mark.integration
@pytest.mark.asyncio
async def test_full_transcription_workflow():
    """Test complete workflow: transcribe and build subtitle track."""
    # This test requires a real video file
    # Skip if no test video available
    test_video = os.environ.get('TEST_VIDEO_PATH')
    if not test_video or not os.path.exists(test_video):
        pytest.skip("TEST_VIDEO_PATH not set or file not found")

    all_words = None

    async for progress, message, result in transcribe_whisper_chunked(
        test_video,
        model_size="tiny",  # Use tiny for faster test
        language="en",
        max_chunk_duration=30.0,
    ):
        print(f"Progress: {progress}% - {message}")
        if result is not None:
            all_words = result

    assert all_words is not None
    assert len(all_words) > 0

    # Build subtitle track
    track = SubtitleTrack()
    track.rebuild_segments(all_words)

    assert len(track.segments) > 0
    assert track.words_per_line > 0

    # Verify segments have valid timing
    for seg in track.segments:
        assert seg.words is not None
        assert len(seg.words) > 0
        for word in seg.words:
            assert word.start_time >= 0
            assert word.end_time >= word.start_time
```

- [ ] **Step 2: Commit**

```bash
git add tests/test_integration_whisper.py
git commit -m "test: add integration test for Whisper transcription"
```

---

## Task 10: Documentation

**Files:**
- Create: `docs/whisper-transcription.md`

- [ ] **Step 1: Write user documentation**

Create `docs/whisper-transcription.md`:

```markdown
# Whisper Transcription Guide

## Overview

OWN supports two transcription engines:

1. **Vosk** - Lightweight, Hindi-focused models
2. **Whisper** - Multilingual, higher accuracy, requires more RAM

## Whisper Models

### Large v3 Turbo (Recommended)
- Size: ~800 MB
- RAM: ~4 GB recommended
- Accuracy: High
- Speed: Fast

### Large v3
- Size: ~3 GB
- RAM: ~8 GB recommended
- Accuracy: Very High
- Speed: Slower

## How to Use

1. Open a project in the editor
2. Click "Transcribe" button
3. Select "Whisper (Multilingual)" as the engine
4. Choose your preferred model
5. If not installed, click "Download Model"
6. Click "Start Transcription"

## Chunked Processing

Whisper transcription uses chunked processing to manage RAM usage:
- Audio is split into ~30-second chunks at silence boundaries
- Each chunk is processed sequentially
- Word timings are automatically adjusted across chunks
- Progress is shown in real-time

## Troubleshooting

### Out of Memory
If you encounter out-of-memory errors:
- Use the "Large v3 Turbo" model instead of "Large v3"
- Close other applications to free up RAM
- Ensure you have at least 4 GB RAM available

### Slow Transcription
Transcription speed depends on:
- CPU performance (Whisper is CPU-intensive)
- Model size (Turbo is faster than Large v3)
- Video length

### Poor Accuracy
For better accuracy:
- Ensure clear audio quality
- Use the "Large v3" model (slower but more accurate)
- Check that the correct language is selected
```

- [ ] **Step 2: Commit**

```bash
git add docs/whisper-transcription.md
git commit -m "docs: add Whisper transcription user guide"
```

---

## Summary

This implementation plan adds:

1. **Silence detection** for intelligent audio chunking
2. **Chunked Whisper transcriber** with RAM management
3. **Model selection UI** in the web editor
4. **API updates** for engine and model selection
5. **Comprehensive tests** for all components
6. **User documentation** for Whisper transcription

The system processes video in ~30-second chunks at silence boundaries, enabling transcription of long videos on systems with limited RAM while maintaining word-level timestamps.
