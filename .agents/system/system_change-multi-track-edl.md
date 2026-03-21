# System Change: Multi-Track EDL

## Date
2026-03-22

## Affected Components
- `models/subtitle.py` (Extended to hold EDL data)
- `core/exporter.py` (Exporter now pre-processes video with cuts)
- `web/js/timeline.js` (Multi-track editing and selection range)
- `web/js/editor.js` (Split and Trim logic)

## Description
The previous architecture assumed a continuous 1:1 relationship between the exported video and the original video. To support trimming and splitting across all tracks, we are introducing a frontend-to-backend Edit Decision List (EDL) structure. Features include time selection on the timeline to allow precision trimming.

## Context
When performing video edits, trimming the subtitling text is insufficient; the actual video/audio must also be cut appropriately to keep tracks in sync and to remove unwanted sections entirely. 

## Related Files
- `current_state.md`
- `task-multitrack-trim.md`
