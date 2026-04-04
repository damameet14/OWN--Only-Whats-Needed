# Task: Special Group Highlighting (UI Only)

## Goal
Implement unique, group-specific highlight colors for "Special" word groups in the editor's UI (Timeline and Segments list).

## Status
- [x] Implement deterministic HSL color generator in `getGroupColor` function
- [x] Update `timeline.js` to use group colors for word highlight pips
- [x] Update `editor.js` to apply group colors as inline background/border styles for `.word-item` elements
- [x] Manual verification of UI consistency
- [x] Verify no impact on export engine or video preview

## Proposed Changes
### `web/js/timeline.js`
- Added standalone `getGroupColor` function to hash `group_id` into a Hue.
- Modified `draw()` loop to fetch and apply these colors for special word pips.

### `web/js/editor.js`
- Added standalone `getGroupColor` function.
- Updated the `populateSegments` override to apply the colors as inline styles on `.word-item` spans.

## Last Updated: 2026-04-05
