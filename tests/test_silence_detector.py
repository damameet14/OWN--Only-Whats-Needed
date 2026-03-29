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
            max_chunk_duration=5.0  # Use smaller value to trigger chunking
        )

        # Should have 3 chunks (5s audio each, split at silence)
        assert len(chunks) == 3

        # Check first chunk
        assert chunks[0][0] == 0.0
        assert 4.5 <= chunks[0][1] <= 5.5  # Around 5 seconds

        # Check second chunk
        assert 4.5 <= chunks[1][0] <= 5.5
        assert 9.5 <= chunks[1][1] <= 10.5

        # Check third chunk
        assert 9.5 <= chunks[2][0] <= 10.5
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
