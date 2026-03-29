# Whisper Chunked Transcription Design

**Date:** 2026-03-29
**Status:** Approved for Implementation

## Overview

Add Whisper Large v3 Turbo transcription support with RAM-efficient chunked processing. The system processes video in ~30-second chunks at silence boundaries, enabling transcription of long videos on systems with limited RAM.

## Requirements

1. **Model Management**
   - Add Whisper Large v3 Turbo to available models
   - Provide UI for model download and selection
   - Support both Vosk and Whisper engines

2. **Chunked Transcription**
   - Process video in ~30-second chunks
   - Detect silence/pause points for intelligent chunk boundaries
   - Maintain word-level timestamps across chunks
   - Show accurate progress during transcription

3. **User Control**
   - User selects transcription engine (Vosk/Whisper)
   - User selects specific Whisper model
   - User controls words-per-line for subtitle display

## Architecture

### Component Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                     Transcription Flow                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Video File → Audio Extraction → Silence Detection              │
│                                          ↓                        │
│                                  Chunk Boundaries                 │
│                                          ↓                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │  Chunk 1     │  │  Chunk 2     │  │  Chunk N     │           │
│  │  (~30s)      │  │  (~30s)      │  │  (~30s)      │           │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘           │
│         ↓                 ↓                 ↓                    │
│  Whisper Model     Whisper Model     Whisper Model               │
│  (loaded once)    (reused)          (reused)                     │
│         ↓                 ↓                 ↓                    │
│  Word Timings     Word Timings     Word Timings                  │
│         └─────────────────┴─────────────────┘                    │
│                           ↓                                       │
│                    Merge & Adjust                                 │
│                           ↓                                       │
│                    SubtitleTrack                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Components

### 1. Silence Detection Module

**File:** `core/silence_detector.py`

**Purpose:** Detect pause points in audio for intelligent chunking.

**Interface:**
```python
async def detect_silence_boundaries(
    wav_path: str,
    min_silence_duration: float = 0.5,  # seconds
    silence_threshold: float = -40.0,   # dB
    max_chunk_duration: float = 30.0,  # seconds
) -> list[tuple[float, float]]:  # Returns [(start, end), ...]
```

**Implementation Details:**
- Use FFmpeg's `silencedetect` filter for efficient silence detection
- Parse FFmpeg output to find silence regions
- Generate chunk boundaries at midpoints of silence regions
- Ensure no chunk exceeds `max_chunk_duration`
- If no silence found, fall back to fixed-duration chunks

**FFmpeg Command:**
```bash
ffmpeg -i input.wav -af "silencedetect=noise=-40dB:duration=0.5" -f null -
```

### 2. Chunked Whisper Transcriber

**File:** `core/whisper_chunked.py`

**Purpose:** Transcribe audio chunks with RAM management.

**Interface:**
```python
async def transcribe_whisper_chunked(
    video_path: str,
    model_size: str = "large-v3-turbo",
    language: str = "hi",
    max_chunk_duration: float = 30.0,
    progress_callback: Callable[[int, str], None] = None,
) -> AsyncGenerator[tuple[int, str, Optional[list[WordTiming]]], None]
```

**Key Behaviors:**
1. Extract audio once to temporary WAV
2. Run silence detection to get chunk boundaries
3. Load Whisper model once (reused across chunks)
4. Process chunks sequentially, yielding progress
5. Adjust word timestamps by chunk offset
6. Clean up temporary files

**Progress Calculation:**
```
Total progress = (audio_extract * 5%) +
                 (silence_detect * 10%) +
                 (model_load * 5%) +
                 (chunk_processing * 80%)

Chunk progress = (current_chunk / total_chunks) * 80%
```

### 3. Model Selection UI

**Location:** Web frontend - [web/editor.html](web/editor.html)

**UI Elements:**
- Engine dropdown: "Vosk (Hindi)" / "Whisper (Multilingual)"
- Whisper model dropdown: "Large v3 Turbo (800MB)" / "Large v3 (3GB)"
- Download button for uninstalled models
- Progress indicator for model download

**API Integration:**
- `GET /api/models/available` - List available models with install status
- `POST /api/models/download` - Download a model
- `POST /api/projects/{id}/transcribe` - Start transcription with engine/model selection

### 4. API Updates

**File:** `server/app.py`

**Transcription Endpoint Update:**
```python
@app.post("/api/projects/{project_id}/transcribe")
async def start_transcription(
    project_id: int,
    body: dict = None
):
    body = body or {}
    engine = body.get("engine", "vosk")  # "vosk" or "whisper"
    model = body.get("model", None)      # Specific model name
    language = body.get("language", "hi")
```

### 5. Configuration

**File:** `server/config.py`

**New Entries:**
```python
# Whisper chunked transcription settings
WHISPER_MAX_CHUNK_DURATION = 30.0      # seconds
WHISPER_MIN_SILENCE_DURATION = 0.5     # seconds
WHISPER_SILENCE_THRESHOLD = -40.0      # dB
```

## Data Flow

### Transcription Request Flow

```
1. User selects Whisper engine + model in web UI
2. POST /api/projects/{id}/transcribe with {engine: "whisper", model: "large-v3-turbo"}
3. Server validates model is installed
4. Server starts background task
5. WebSocket sends progress updates
6. Client shows progress bar
7. On completion, subtitle data saved to project
```

### Word Timing Adjustment

When processing chunks, word timestamps must be adjusted by the chunk's start time:

```python
for chunk_idx, (chunk_start, chunk_end) in enumerate(chunks):
    words = transcribe_chunk(chunk_start, chunk_end)
    for word in words:
        word.start_time += chunk_start
        word.end_time += chunk_start
    all_words.extend(words)
```

## Error Handling

| Scenario | Handling |
|----------|----------|
| Model not installed | Return 400 with download URL |
| Silence detection fails | Fallback to fixed 30s chunks |
| Chunk transcription fails | Log error, continue with remaining chunks |
| Out of memory | Reduce chunk size to 15s and retry |
| FFmpeg not available | Return 500 with clear error message |
| Invalid audio format | Return 400 with error details |

## Files to Create

1. `core/silence_detector.py` - Silence detection module
2. `core/whisper_chunked.py` - Chunked Whisper transcriber

## Files to Modify

1. `server/app.py` - Update transcription endpoint
2. `server/config.py` - Add Whisper configuration
3. `server/model_manager.py` - Ensure Whisper models are registered
4. `web/editor.html` - Add model selection UI
5. `web/js/editor.js` - Handle model selection and download
6. `web/js/api.js` - Add model-related API calls

## Testing Checklist

- [ ] Silence detection correctly identifies pause points
- [ ] Chunks do not exceed max duration
- [ ] Word timestamps are correctly adjusted across chunks
- [ ] Progress updates are accurate
- [ ] Model download works and registers in database
- [ ] Model selection UI shows correct status
- [ ] Fallback to fixed chunks works when silence detection fails
- [ ] RAM usage stays within expected bounds
- [ ] Transcription quality matches non-chunked Whisper

## Dependencies

**New:**
- `webrtcvad` (optional, for alternative silence detection)

**Existing:**
- `faster-whisper` - Already in requirements.txt
- `ffmpeg-python` - Already in requirements.txt
