"""Chunked Whisper transcription with RAM management."""

from __future__ import annotations
import logging
import os
import subprocess
import sys
import tempfile
import asyncio
from typing import AsyncGenerator, Optional, Callable

from models.subtitle import WordTiming
from core.silence_detector import detect_silence_boundaries
from server.config import (
    WHISPER_MAX_CHUNK_DURATION,
    WHISPER_MIN_SILENCE_DURATION,
    WHISPER_SILENCE_THRESHOLD,
)

# Configure logging
logger = logging.getLogger(__name__)


async def transcribe_whisper_chunked(
    video_path: str,
    model_path: str = None,
    model_size: str = "large-v3-turbo",
    language: str = "hi",
    device: str = "cpu",
    compute_type: str = "int8",
    max_chunk_duration: float = WHISPER_MAX_CHUNK_DURATION,
    progress_callback: Optional[Callable[[int, str], None]] = None,
    vad_filter: bool = False,  # Disabled by default - can be too aggressive
    chunk_timeout: float = 300.0,  # Timeout per chunk in seconds
) -> AsyncGenerator[tuple[int, str, Optional[list[WordTiming]]], None]:
    """Async generator that transcribes using Whisper with chunked processing.

    Processes audio in ~30-second chunks at silence boundaries to manage RAM usage.
    The Whisper model is loaded once and reused across chunks.

    Args:
        video_path: Path to video file
        model_path: Path to Whisper model directory (if None, uses model_size with default cache)
        model_size: Model size name for faster-whisper (used if model_path is None)
        language: Language code
        device: Device to run on ("cpu" or "cuda")
        compute_type: Compute type ("int8", "float16", etc.)
        max_chunk_duration: Maximum chunk duration in seconds
        progress_callback: Optional callback for progress updates

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
        """Internal helper to update progress and optionally call callback."""
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

    # Step 2 — detect silence boundaries (10%)
    logger.info("[WHISPER] Step 2: Detecting silence boundaries...")
    yield (15, "Detecting silence for chunking…", None)
    _update_progress(15, "Detecting silence for chunking…")
    try:
        chunks = await detect_silence_boundaries(
            wav_path,
            min_silence_duration=WHISPER_MIN_SILENCE_DURATION,
            silence_threshold=WHISPER_SILENCE_THRESHOLD,
            max_chunk_duration=max_chunk_duration,
        )
        logger.info(f"[WHISPER] Detected {len(chunks)} chunks: {chunks[:3]}...")
    except Exception as e:
        logger.error(f"[WHISPER] Silence detection failed: {e}", exc_info=True)
        yield (0, f"Error detecting silence: {e}", None)
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

    # Step 4 — transcribe chunks (80%)
    logger.info(f"[WHISPER] Step 4: Transcribing {len(chunks)} chunks...")
    yield (25, f"Transcribing {len(chunks)} chunks…", None)
    _update_progress(25, f"Transcribing {len(chunks)} chunks…")

    all_words: list[WordTiming] = []
    total_chunks = len(chunks)

    for chunk_idx, (chunk_start, chunk_end) in enumerate(chunks):
        chunk_progress = 25 + int(((chunk_idx + 1) / total_chunks) * 75)
        logger.info(f"[WHISPER] Processing chunk {chunk_idx + 1}/{total_chunks} ({chunk_start:.2f}s - {chunk_end:.2f}s)...")
        yield (chunk_progress, f"Processing chunk {chunk_idx + 1}/{total_chunks}…", None)
        _update_progress(chunk_progress, f"Processing chunk {chunk_idx + 1}/{total_chunks}…")

        # Extract chunk audio
        try:
            chunk_wav = await asyncio.to_thread(
                _extract_chunk_audio,
                wav_path,
                chunk_start,
                chunk_end,
            )
            logger.debug(f"[WHISPER] Chunk audio extracted to: {chunk_wav}")
        except Exception as e:
            logger.error(f"[WHISPER] Chunk {chunk_idx + 1} audio extraction failed: {e}", exc_info=True)
            continue

        # Transcribe chunk
        try:
            chunk_words = await asyncio.wait_for(
                asyncio.to_thread(
                    _transcribe_chunk,
                    model,
                    chunk_wav,
                    language,
                    vad_filter,
                ),
                timeout=chunk_timeout,
            )
            logger.info(f"[WHISPER] Chunk {chunk_idx + 1} transcribed: {len(chunk_words)} words")
        except asyncio.TimeoutError:
            logger.error(f"[WHISPER] Chunk {chunk_idx + 1} transcription timed out after {chunk_timeout}s")
            try:
                os.remove(chunk_wav)
            except OSError:
                pass
            continue
        except Exception as e:
            logger.error(f"[WHISPER] Chunk {chunk_idx + 1} transcription failed: {e}", exc_info=True)
            try:
                os.remove(chunk_wav)
            except OSError:
                pass
            continue

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
        logger.info(f"[WHISPER] Cleaned up main wav: {wav_path}")
    except OSError:
        pass

    logger.info(f"[WHISPER] COMPLETE: Total {len(all_words)} words transcribed")
    yield (100, "Transcription complete.", all_words)
    _update_progress(100, "Transcription complete.")


def _extract_audio(video_path: str) -> str:
    """Extract 16 kHz mono WAV from video."""
    logger.debug(f"[WHISPER] _extract_audio: video_path={video_path}")
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
        "ffmpeg", "-y",
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
    try:
        segments, info = model.transcribe(
            wav_path,
            language=language,
            word_timestamps=True,
            beam_size=5,
            vad_filter=vad_filter,
        )
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
