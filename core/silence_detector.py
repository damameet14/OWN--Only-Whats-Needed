"""Silence detection module for intelligent audio chunking."""

from __future__ import annotations
import subprocess
import sys
import re
import asyncio


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
        "ffmpeg", "-v", "info",
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
    # Only merge if there's a gap between chunks, not if they're adjacent
    merged_chunks = []
    for i, (start, end) in enumerate(chunks):
        if i == 0:
            merged_chunks.append([start, end])
        else:
            prev_start, prev_end = merged_chunks[-1]
            # Only merge if there's a gap (start > prev_end) and the gap is small
            # Don't merge adjacent chunks (start == prev_end)
            if start > prev_end and (start - prev_end) < 1.0:
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
