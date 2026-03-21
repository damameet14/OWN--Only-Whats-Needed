# Code Context: Web Frontend

## Last Updated
2026-03-21

## Overview
Vanilla HTML/CSS/JS web application served as static files by FastAPI. Two pages: home (upload + project grid) and editor (video preview + subtitle styling + timeline). Uses Tailwind CSS CDN for layout and custom CSS for theming.

## Entry Points
- `GET /` → `web/index.html` (home page)
- `GET /editor/{id}` → `web/editor.html` (editor page)

## Execution Flow
### Home Page
1. Load page → `app.js:loadProjects()` fetches `GET /api/projects`
2. Render project cards in grid with thumbnails, duration, status badges
3. Upload: drag-and-drop or click → show modal (title/language/engine) → `POST /api/projects` → `POST /api/projects/{id}/transcribe` → WebSocket progress → redirect to editor

### Editor Page
1. `editor.js:loadProject()` fetches project + subtitle data
2. Load video element with `GET /api/projects/{id}/video`
3. `SubtitlePreview` renders subtitles on canvas overlay synced to video time
4. `SubtitleTimeline` initialized with project ID, loads sprite and waveform images
5. `SubtitleTimeline` draws images, segments, and sticky track headers on canvas with playhead
6. Style controls update subtitle track → auto-save via `PUT /api/projects/{id}`
7. Export: modal → `POST /api/projects/{id}/export` → WebSocket progress → download link

## Functions / Methods / Classes
| Name | Type | File Path | Description | Calls / Used By |
|------|------|-----------|-------------|-----------------|
| `apiRequest` | fn | `web/js/api.js` | Generic fetch wrapper | All API functions |
| `watchProgress` | fn | `web/js/api.js` | WebSocket progress listener | Upload, export flows |
| `createProject` | fn | `web/js/api.js` | POST /api/projects | `app.js:uploadAndTranscribe` |
| `startTranscription` | fn | `web/js/api.js` | POST /api/projects/{id}/transcribe | `app.js:uploadAndTranscribe` |
| `loadProjects` | fn | `web/js/app.js` | Fetches and renders project grid | Page load |
| `uploadAndTranscribe` | fn | `web/js/app.js` | Full upload → transcribe → redirect flow | Upload zone |
| `SubtitlePreview` | class | `web/js/preview.js` | Canvas subtitle renderer with animations | `editor.js` |
| `SubtitleTimeline` | class | `web/js/timeline.js` | Canvas timeline with segments + playhead | `editor.js` |
| `loadProject` | fn | `web/js/editor.js` | Loads project data, initializes preview/timeline | Page load |
| `updateStyle` | fn | `web/js/editor.js` | Applies style change to all segments | Style controls |
| `autoSave` | fn | `web/js/editor.js` | Debounced PUT to save subtitle changes | Style/edit changes |

## External Dependencies
- Tailwind CSS CDN, Google Fonts (Inter), Material Symbols Outlined

## Internal Dependencies
- All `web/js/api.js` functions depend on the FastAPI routes in `server/app.py`

## Related Tasks
- .agents/tasks/task-own-revamp.md

## Known Limitations
- Tailwind loaded from CDN — requires internet on first load (cached after)
- Canvas subtitle preview is an approximation — not pixel-identical to Pillow export
- No offline font loading — Google Fonts require internet

## Change Log
| Date | Change |
|------|--------|
| 2026-03-20 | Initial creation: index.html, editor.html, app.css, api.js, app.js, editor.js, preview.js, timeline.js |
| 2026-03-21 | Added video and subtitle properties handles (`editor.js`, `preview.js`) and throttled timeline canvas scrubbing events (`timeline.js`) to resolve stutter. |
| 2026-03-21 | Updated `editor.html` and `timeline.js` to support timeline resizing, split/trim buttons, and pre-rendered Sprite/Waveform visual assets. |
| 2026-03-21 | Implemented Split and Trim core logic in `editor.js`, cached-busted JS files in `editor.html`, and updated `timeline.js` so that tracks align cleanly to the sticky headers and the playhead is clamped to the left panel border. |
