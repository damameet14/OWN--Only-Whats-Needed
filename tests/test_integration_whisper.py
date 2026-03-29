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
