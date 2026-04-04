# UX Fixes

## Overview
Status: [x] Complete
Owner: agent
Last Updated: 2026-04-05
Priority: Normal
Type: Light

## Description
Fixes 3 specific UX issues requested by the user:
1. Timeline playhead lag on click (jumps to start / waits for move)
2. Remove special words styling highlight from the Timeline
3. Make the Video Preview panel responsive so controls are not pushed under the timeline

## Proposed Changes
- `[MODIFY] timeline.js`:
  - Fixed playhead timeline seeking bug: Clicking a segment directly used to select it *and* snap the playhead to its start while setting `isDraggingPlayhead=true`. If the mouse was released immediately, `mousemove` wasn't firing, and a final `handleInteraction` ran during `mouseup` forcing the playhead to calculate a new position under the mouse pointer. This created a "jump to start of a segment and snap back" glitch.
  - Added playhead interaction radius override: Clicking within 15px of the playhead explicitly overrides segment selection to prioritize scrubbing. Also enabled explicit ruler clicking to easily scrub the timeline safely without interacting with tracks.
  - Instantly set `this.currentTime = seekTime` and `this.draw()` on mousedown interaction while scrub seeking, overriding the video event delay.
  - Remove UI highlighting block for `word.is_special` in the bottom Text Track timeline rendering.
- `[MODIFY] editor.html`:
  - Enhance Flexbox constraints (`min-h-0`, `flex-shrink-0` on controls container) to make the preview center container perfectly responsive. Made Video limit to `max-h-full` instead of fixed `max-h-[60vh]`, ensuring it responds to window heights elegantly. Also updated `subtitle-canvas` positioning to `top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2` to match perfectly on center.

## Blockers
None.

## Related Links
None.
