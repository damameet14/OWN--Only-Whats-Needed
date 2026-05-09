"""Chunked Whisper transcription with RAM management.

Uses fixed 20-second chunks processed in batches of 4 for efficient
memory usage and throughput. No silence detection — simple fixed-length splits.
"""

from __future__ import annotations
import logging
import math
import os
import subprocess
import sys
import tempfile
import asyncio
from typing import AsyncGenerator, Optional, Callable

from models.subtitle import WordTiming
from server.config import get_ffmpeg_path

# Configure logging
logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────
CHUNK_DURATION = 20.0   # seconds per chunk
BATCH_SIZE = 4          # chunks processed per batch


async def transcribe_whisper_chunked(
    video_path: str,
    model_path: str = None,
    model_size: str = "large-v3-turbo",
    language: str = "hi",
    device: str = "cpu",
    compute_type: str = "int8",
    progress_callback: Optional[Callable[[int, str], None]] = None,
    vad_filter: bool = False,
    chunk_timeout: float = 300.0,
) -> AsyncGenerator[tuple[int, str, Optional[list[WordTiming]]], None]:
    """Async generator that transcribes using Whisper with fixed-length chunked processing.

    Splits audio into exact 20-second chunks and processes them in batches of 4.
    The Whisper model is loaded once and reused across all chunks.

    Yields:
        (progress_percent, status_message, word_timings_or_none)
        When progress == 100, word_timings will contain the final results.
    """
    logger.info(f"[WHISPER] START: video_path={video_path}, model_path={model_path}, model_size={model_size}, language={language}")

    # Validate input
    if not os.path.exists(video_path):
        logger.error(f"[WHISPER] Video file not found: {video_path}")
        yield (0, f"Error: Video file not found: {video_path}", None)
        return

    def _update_progress(percent: int, message: str) -> None:
        logger.debug(f"[WHISPER] Progress: {percent}% - {message}")
        if progress_callback is not None:
            progress_callback(percent, message)

    # Step 1 — extract audio (5%)
    logger.info("[WHISPER] Step 1: Extracting audio from video...")
    yield (5, "Extracting audio from video…", None)
    _update_progress(5, "Extracting audio from video…")
    try:
        wav_path = await asyncio.to_thread(_extract_audio, video_path)
        logger.info(f"[WHISPER] Audio extracted to: {wav_path}")
    except Exception as e:
        logger.error(f"[WHISPER] Audio extraction failed: {e}", exc_info=True)
        yield (0, f"Error extracting audio: {e}", None)
        return

    # Step 2 — get audio duration and compute fixed chunks (10%)
    logger.info("[WHISPER] Step 2: Computing fixed-length chunks...")
    yield (10, "Splitting audio into chunks…", None)
    _update_progress(10, "Splitting audio into chunks…")
    try:
        duration = await asyncio.to_thread(_get_audio_duration, wav_path)
        chunks = _compute_fixed_chunks(duration, CHUNK_DURATION)
        logger.info(f"[WHISPER] Audio duration: {duration:.2f}s, split into {len(chunks)} chunks of {CHUNK_DURATION}s")
    except Exception as e:
        logger.error(f"[WHISPER] Chunk computation failed: {e}", exc_info=True)
        yield (0, f"Error computing chunks: {e}", None)
        try:
            os.remove(wav_path)
        except OSError:
            pass
        return

    # Step 3 — load model (5%)
    logger.info(f"[WHISPER] Step 3: Loading Whisper model (model_path={model_path}, model_size={model_size})...")
    yield (20, "Loading Whisper model…", None)
    _update_progress(20, "Loading Whisper model…")

    def _load_model():
        from faster_whisper import WhisperModel
        logger.info(f"[WHISPER] Importing faster_whisper, creating model...")
        if model_path:
            logger.info(f"[WHISPER] Using model from path: {model_path}")
            return WhisperModel(model_path, device=device, compute_type=compute_type)
        logger.info(f"[WHISPER] Using model size: {model_size}")
        return WhisperModel(model_size, device=device, compute_type=compute_type)

    try:
        model = await asyncio.to_thread(_load_model)
        logger.info("[WHISPER] Model loaded successfully")
    except Exception as e:
        logger.error(f"[WHISPER] Model loading failed: {e}", exc_info=True)
        yield (0, f"Error loading Whisper model: {e}", None)
        _update_progress(0, f"Error loading Whisper model: {e}")
        try:
            os.remove(wav_path)
        except OSError:
            pass
        return

    # Step 4 — transcribe in batches of BATCH_SIZE chunks (75%)
    total_chunks = len(chunks)
    total_batches = math.ceil(total_chunks / BATCH_SIZE)
    logger.info(f"[WHISPER] Step 4: Transcribing {total_chunks} chunks in {total_batches} batches of {BATCH_SIZE}...")
    yield (25, f"Transcribing {total_chunks} chunks in {total_batches} batches…", None)
    _update_progress(25, f"Transcribing {total_chunks} chunks…")

    all_words: list[WordTiming] = []

    for batch_idx in range(total_batches):
        batch_start = batch_idx * BATCH_SIZE
        batch_end = min(batch_start + BATCH_SIZE, total_chunks)
        batch_chunks = chunks[batch_start:batch_end]

        batch_progress = 25 + int(((batch_idx + 1) / total_batches) * 70)
        logger.info(f"[WHISPER] Processing batch {batch_idx + 1}/{total_batches} (chunks {batch_start + 1}-{batch_end})...")
        yield (batch_progress, f"Batch {batch_idx + 1}/{total_batches} — chunks {batch_start + 1}–{batch_end}…", None)
        _update_progress(batch_progress, f"Batch {batch_idx + 1}/{total_batches}")

        # Extract all chunk audio files for this batch
        chunk_wavs = []
        chunk_offsets = []
        for chunk_start, chunk_end in batch_chunks:
            try:
                chunk_wav = await asyncio.to_thread(
                    _extract_chunk_audio, wav_path, chunk_start, chunk_end,
                )
                chunk_wavs.append(chunk_wav)
                chunk_offsets.append(chunk_start)
            except Exception as e:
                logger.error(f"[WHISPER] Chunk audio extraction failed ({chunk_start:.1f}s-{chunk_end:.1f}s): {e}", exc_info=True)
                chunk_wavs.append(None)
                chunk_offsets.append(chunk_start)

        # Transcribe each chunk in the batch sequentially
        for i, (chunk_wav, chunk_offset) in enumerate(zip(chunk_wavs, chunk_offsets)):
            if chunk_wav is None:
                continue

            chunk_num = batch_start + i + 1
            try:
                chunk_words = await asyncio.wait_for(
                    asyncio.to_thread(
                        _transcribe_chunk, model, chunk_wav, language, vad_filter,
                    ),
                    timeout=chunk_timeout,
                )
                logger.info(f"[WHISPER] Chunk {chunk_num}/{total_chunks} transcribed: {len(chunk_words)} words")
            except asyncio.TimeoutError:
                logger.error(f"[WHISPER] Chunk {chunk_num} timed out after {chunk_timeout}s")
                continue
            except Exception as e:
                logger.error(f"[WHISPER] Chunk {chunk_num} transcription failed: {e}", exc_info=True)
                continue
            finally:
                try:
                    os.remove(chunk_wav)
                except OSError:
                    pass

            # Adjust timestamps by chunk offset
            for word in chunk_words:
                word.start_time += chunk_offset
                word.end_time += chunk_offset

            all_words.extend(chunk_words)

    # Cleanup main wav
    try:
        os.remove(wav_path)
        logger.info(f"[WHISPER] Cleaned up main wav: {wav_path}")
    except OSError:
        pass

    # Finalization
    logger.info(f"[WHISPER] Finalizing transcription...")
    yield (98, "Finalizing transcription…", None)
    _update_progress(98, "Finalizing transcription…")

    logger.info(f"[WHISPER] COMPLETE: Total {len(all_words)} words transcribed")
    yield (100, "Transcription complete.", all_words)
    _update_progress(100, "Transcription complete.")


# ── Helper functions ──────────────────────────────────────────────────────────

def _get_audio_duration(wav_path: str) -> float:
    """Get duration of a WAV file using ffprobe."""
    cmd = [
        get_ffmpeg_path().replace("ffmpeg", "ffprobe"),
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        wav_path,
    ]
    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {result.stderr.decode(errors='replace')}")

    import json
    data = json.loads(result.stdout)
    return float(data.get("format", {}).get("duration", 0))


def _compute_fixed_chunks(duration: float, chunk_duration: float) -> list[tuple[float, float]]:
    """Split duration into fixed-length chunks.

    Returns list of (start_time, end_time) tuples.
    The last chunk may be shorter than chunk_duration.
    """
    chunks = []
    start = 0.0
    while start < duration:
        end = min(start + chunk_duration, duration)
        if end - start > 0.1:  # Skip tiny residual chunks
            chunks.append((start, end))
        start = end
    return chunks


def _extract_audio(video_path: str) -> str:
    """Extract 16 kHz mono WAV from video."""
    logger.debug(f"[WHISPER] _extract_audio: video_path={video_path}")
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    cmd = [
        get_ffmpeg_path(), "-y",
        "-i", video_path,
        "-ar", "16000",
        "-ac", "1",
        "-f", "wav",
        tmp.name,
    ]
    logger.debug(f"[WHISPER] _extract_audio: running ffmpeg: {' '.join(cmd)}")
    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    if result.returncode != 0:
        logger.error(f"[WHISPER] _extract_audio: ffmpeg failed with returncode={result.returncode}")
        logger.error(f"[WHISPER] _extract_audio: stderr={result.stderr.decode(errors='replace')}")
        raise RuntimeError(
            f"FFmpeg audio extraction failed:\n{result.stderr.decode(errors='replace')}"
        )
    logger.debug(f"[WHISPER] _extract_audio: success, output={tmp.name}")
    return tmp.name


def _extract_chunk_audio(wav_path: str, start_time: float, end_time: float) -> str:
    """Extract a chunk from WAV file."""
    logger.debug(f"[WHISPER] _extract_chunk_audio: wav_path={wav_path}, start={start_time}, end={end_time}, duration={end_time - start_time}")
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    duration = end_time - start_time

    cmd = [
        get_ffmpeg_path(), "-y",
        "-ss", str(start_time),
        "-i", wav_path,
        "-t", str(duration),
        "-c", "copy",
        tmp.name,
    ]
    logger.debug(f"[WHISPER] _extract_chunk_audio: running ffmpeg: {' '.join(cmd)}")
    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    if result.returncode != 0:
        logger.error(f"[WHISPER] _extract_chunk_audio: ffmpeg failed with returncode={result.returncode}")
        logger.error(f"[WHISPER] _extract_chunk_audio: stderr={result.stderr.decode(errors='replace')}")
        raise RuntimeError(
            f"FFmpeg chunk extraction failed:\n{result.stderr.decode(errors='replace')}"
        )
    logger.debug(f"[WHISPER] _extract_chunk_audio: success, output={tmp.name}")
    return tmp.name


def _transcribe_chunk(model, wav_path: str, language: str, vad_filter: bool = False) -> list[WordTiming]:
    """Transcribe a single audio chunk with Whisper."""
    logger.debug(f"[WHISPER] _transcribe_chunk: wav_path={wav_path}, language={language}, vad_filter={vad_filter}")

    # Map 'multi'/'auto' to None for faster-whisper auto-detection
    effective_language = language
    if language in ("multi", "auto", ""):
        effective_language = None
        logger.info(f"[WHISPER] _transcribe_chunk: auto-detect mode (language={language!r} -> None)")

    # Build transcription kwargs
    transcribe_kwargs = {
        "word_timestamps": True,
        "beam_size": 5,
        "vad_filter": vad_filter,
        "task": "transcribe",  # Always transcribe, never translate
    }

    if effective_language is not None:
        transcribe_kwargs["language"] = effective_language

    # Prompt to preserve original language words (prevents translation to English)
    transcribe_kwargs["initial_prompt"] = (
        "Transcribe exactly as spoken. Preserve all original language words. "
        "Do not translate any words into English or any other language."
    )

    try:
        segments, info = model.transcribe(wav_path, **transcribe_kwargs)
        logger.debug(f"[WHISPER] _transcribe_chunk: model.transcribe returned, info={info}")

        words: list[WordTiming] = []
        segment_count = 0
        for segment in segments:
            segment_count += 1
            logger.debug(f"[WHISPER] _transcribe_chunk: segment {segment_count}: text={segment.text!r}, start={segment.start}, end={segment.end}, words={segment.words is not None}")
            if segment.words:
                for word_info in segment.words:
                    words.append(WordTiming(
                        word=word_info.word.strip(),
                        start_time=word_info.start,
                        end_time=word_info.end,
                        confidence=word_info.probability,
                    ))

        logger.info(f"[WHISPER] _transcribe_chunk: processed {segment_count} segments, extracted {len(words)} words")
        return words
    except Exception as e:
        logger.error(f"[WHISPER] _transcribe_chunk error: {e}", exc_info=True)
        raise
