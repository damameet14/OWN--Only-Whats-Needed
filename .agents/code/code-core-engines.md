# Code Context: Core Engines

## Last Updated
2026-03-21

## Overview
Transcription and export engines that process video files. All engines use async generators yielding `(progress, message, result)` tuples for progress tracking. PySide6 dependencies removed; uses Pillow for image rendering.

## Entry Points
- `server/app.py:_run_transcription` → `transcribe_vosk()` or `transcribe_whisper()`
- `server/app.py:_run_export` → `export_video()`

## Execution Flow
### Transcription (Vosk)
1. Extract audio via FFmpeg → WAV 16kHz mono
2. Load Vosk model from disk
3. Feed audio chunks → partial results → final results
4. Yield `WordTiming` list

### Transcription (Whisper)
1. Load faster-whisper model (auto-download from HuggingFace on first use)
2. Transcribe audio file directly
3. Extract word-level timestamps from segments
4. Yield `WordTiming` list

### Export
1. Probe video dimensions via ffprobe
2. Start FFmpeg decode (raw frames) and encode pipelines
3. For each frame: create Pillow Image → draw subtitle text with outline/shadow → write to encode pipe
4. Yield progress percentages

## Functions / Methods / Classes
| Name | Type | File Path | Description | Calls / Used By |
|------|------|-----------|-------------|-----------------|
| `transcribe_vosk` | async gen | `core/transcriber.py` | Vosk transcription with progress | `_run_transcription` |
| `transcribe_whisper` | async gen | `core/whisper_transcriber.py` | faster-whisper transcription | `_run_transcription` |
| `export_video` | async gen | `core/exporter.py` | FFmpeg + Pillow subtitle rendering | `_run_export` |
| `get_video_info` | fn | `core/video_utils.py` | ffprobe wrapper returning VideoInfo | `create_project`, `export_video` |
| `generate_srt` | fn | `core/srt_utils.py` | Builds SRT string from SubtitleTrack | `GET /api/projects/{id}/srt` |
| `WordTiming` | dataclass | `models/subtitle.py` | Word with start/end time | Transcribers, SubtitleSegment |
| `SubtitleSegment` | dataclass | `models/subtitle.py` | Group of words with style | SubtitleTrack |
| `SubtitleTrack` | dataclass | `models/subtitle.py` | Full subtitle data + JSON serialization | DB storage, API, editor |

## External Dependencies
- `vosk`, `faster-whisper`, `ffmpeg-python`, `numpy`, `Pillow`

## Internal Dependencies
- `models/subtitle.py`, `models/styles.py`, `models/animations.py`

## Related Tasks
- .agents/tasks/task-own-revamp.md

## Related Architecture
- .agents/system/system_change-hybrid-architecture.md

## Known Limitations
- Whisper is CPU-bound without CUDA — transcription of long videos can be slow
- Exporter reads/writes raw frames — high memory usage for 4K video
- Vosk model must be pre-downloaded; no auto-download in transcriber itself

## Change Log
| Date | Change |
|------|--------|
| 2026-03-20 | Removed PySide6 from transcriber/exporter; added whisper_transcriber; added to_dict/from_dict to subtitle models |
| 2026-03-21 | Added video and subtitle `rotation` values to models, injected Pillow-based rotation transforms into export pipeline, repaired `exporter.py` FFMPEG os-pipe deadlocks + missing MP4 `moov` atoms. Removed all Groq API transcription integration & related dependencies from core and legacy UI. |
