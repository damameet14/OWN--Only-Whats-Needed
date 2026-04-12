# Task: Frontend Marker & Sentence Mode Overhaul

**Owner:** agent  
**Priority:** High  
**Type:** Heavy  
**Last Updated:** 2026-04-12  
**Status:** [/] In Progress

---

## Objective

Complete the frontend implementation of the architecture changes made in the previous session, aligning the UI with the new backend data model (Standard/Highlight/Spotlight marker system, sentence_mode, text_box_width draggable handle).

---

## Subtasks

- [x] Rewrite `preview.js` — marker-aware word style resolution, text_box_width wrapping, draggable right-edge handle
- [x] Clean `timeline.js` — remove stale `getGroupColor` helper and dead blank lines
- [x] Editor.js — `ensureSubtitleTrackMethods` simplified (no legacy group methods)
- [x] Editor.js — Wire `preview.onWidthChange` back to `global-text-box-width` slider
- [x] Editor.js — `initTranscription` Whisper-only (no engine dropdown)
- [x] Editor.js — `initSentenceMode` + `resegmentBySentence` / `resegmentByWords`
- [x] Editor.js — Replace `initSpecialStyleControls` with `initMarkerStyleControls` (reads/writes `highlight_style` / `spotlight_style`)
- [x] Editor.js — `initSubTabSwitching` adds `[data-marker-tab]` listener for Standard/Highlight/Spotlight
- [x] Editor.js — Replace group-based context menu with new marker actions (`ctx-mark-highlight`, `ctx-mark-spotlight`, `ctx-mark-standard`)
- [x] Editor.js — Replace `getGroupColor` word chips with `markerChipColor` (amber=highlight, purple=spotlight)
- [x] Editor.js — Replace all legacy `markWordsAsSpecial` / `unmarkWords` / `createGroup` / `removeFromGroup` / `cleanupEmptyGroups` with single `setWordMarker(marker)`
- [x] Editor.js — `loadPresets` now applies `standard_style` / `highlight_style` / `spotlight_style`; save-preset button uses named prompt
- [x] Editor.js — `applyTrackToControls` populates `text_box_width` and `sentence_mode` controls
- [x] Editor.js — `global-wpl` handler respects `sentence_mode` (disabled when true)
- [x] Editor.js — `global-text-box-width` slider handler added
- [x] Update `.agents/tasks/index.md`

### Phase 2 Fixes (2026-04-12)
- [x] Remove Vosk engine select from upload modal (`index.html`)
- [x] Hardcode `engine = 'whisper'` in `app.js`
- [x] Remove "Transcribe" button from editor header
- [x] Replace "All/Specials" tabs with "Standard/Highlight/Spotlight" marker tabs
- [x] Add "✂️ Make a Segment" to word context menu + `makeWordSegment()` function
- [x] Fix `makeWordSegment` — wrong field names (`start`→`start_time`) and API (`setTrack`→`setData`)
- [x] Add "Editing: ..." current-word indicator to Standard tab
- [x] Add "Editing: ..." current-word indicator to Highlight/Spotlight tabs
- [x] Add "Apply for all" checkbox to Standard tab
- [x] Add "Apply for all" checkbox to Highlight/Spotlight tabs
- [x] Add word-list chips to Highlight/Spotlight tabs (always visible)
- [x] Always show style controls in Highlight/Spotlight (not hidden behind selection)
- [x] Auto-switch to correct marker tab when clicking a word from Segments panel
- [x] Auto-switch to Standard tab when selecting a segment from timeline
- [x] `switchToMarkerTab()` helper function — programmatic tab switching

---

## Files Modified

| File | Change |
|---|---|
| `web/js/preview.js` | Full rewrite — marker styles, text wrapping, draggable handle |
| `web/js/timeline.js` | Remove `getGroupColor`, clean up |
| `web/js/editor.js` | All marker system, sentence mode, whisper-only transcription, switchToMarkerTab, makeWordSegment, updateMarkersPanel with word chips |
| `web/editor.html` | Standard/Highlight/Spotlight tabs, editing indicators, Apply for All, word list, Make a Segment button |
| `web/index.html` | Remove Vosk engine select, hardcode Whisper |
| `web/js/app.js` | Hardcode `engine = 'whisper'` |

---

## Related

- `.agents/code/code-editor.md`
- `.agents/system/current_state.md`
