# Task: Fix Timeline Choppiness and UI

## Description
Fix timeline scroll choppiness by pre-rendering frames. Update timeline UI to match the reference image (Split/Trim buttons, zooming, track headers for TEXT/VIDEO/AUDIO, audio waveform). Make section size adjustable.

## Checklist
- [x] Investigate current frame rendering and timeline implementation (`web/editor.html`, `web/js/timeline.js`, `server/app.py`, `core/exporter.py`)
- [x] Implement backend video frame pre-rendering
- [x] Implement backend audio waveform pre-rendering/extraction
- [x] Update frontend to use pre-rendered frames instead of on-the-fly rendering
- [x] Update timeline UI to include Split/Trim buttons
- [x] Update timeline UI to include Zoom slider
- [x] Update timeline UI with TEXT, VIDEO, AUDIO track labels
- [x] Render audio waveform on the audio track
- [x] Make the timeline section size adjustable (resize handle)
- [x] Update `.agents/code/code-timeline.md` or similar context file
- [x] Update `current_state.md` if necessary
- [x] Mark task completed

## Status
Status: **[x] Complete**
Last Updated: 2026-03-21
