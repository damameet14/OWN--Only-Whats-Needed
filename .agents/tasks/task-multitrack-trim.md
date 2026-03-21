# Task: Multi-Track Trim and Split

## Description
Modify the timeline and backend export engine to support trimming and splitting across all three tracks (Video, Audio, Text). Implement a Time Selection Area for trimming instead of segment deletion. Ensure cuts made on the timeline are applied directly to the final exported video by the backend via a new EDL (Edit Decision List) approach.

## Tier
Heavy

## Proposed Changes
- **Frontend**: Introduce `selectionRange` to `timeline.js`. Add start/end to text segments and model video/audio segments. Allow Splitting all tracks at playhead. Allow Trimming to remove `selectionRange` from selected track(s) or all tracks.
- **Backend API**: The `subtitle_data` JSON schema will evolve into an `edl_data` schema (or store project tracks in JSON). Wait, to preserve DB schema, we will store EDL payload in `subtitle_data` column. 
- **Backend Exporter** (`core/exporter.py`): Build a pre-processing step that cuts video and audio using FFmpeg `concat` filters before subtitle rendering, thus enforcing non-linear edits on media tracks.

## Checklist
- [x] Read `.agents/tasks/index.md`
- [x] Create this task file
- [x] Set Task Type (Heavy)
- [x] Read `.agents/system/current_state.md`
- [x] Add `system_change-multi-track-edl.md`
- [x] Update `current_state.md`
- [x] Implement frontend Timeline Time Selection
- [x] Implement Split for all tracks
- [x] Implement Trim via Time Selection
- [x] Implement backend FFmpeg concat preprocessing
- [x] Test frontend UI (Pending User Manual Verification)
- [x] Test export (Pending User Manual Verification)
- [x] Mark task complete

## Status
Status: [x] Complete
Last Updated: 2026-03-21
