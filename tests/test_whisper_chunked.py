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
