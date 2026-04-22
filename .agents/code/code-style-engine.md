# Code Context: Style Engine

## Last Updated
2026-04-18

## Description
Comprehensive text styling system supporting 6 categories: Font, Fill, Stroke, Shadow, Spacing, Opacity. Supports global (All), per-segment (Standard), and per-word (Highlight/Spotlight) styling. Each segment has an `apply_for_all` flag controlling whether it follows global style changes. Video-level settings are in a separate tab.

## Files

### models/subtitle.py — Data Model
- **SubtitleStyle**: 6 category dataclass (Font, Fill, Stroke, Shadow, Spacing, Opacity)
- **StyledWord**: Per-word data with `marker`, `style_override`, `position_preset`, `animation_type`, `animation_duration`
- **SubtitleSegment**: Per-segment data with `style`, `apply_for_all`, `position_x`, `position_y`, `animation_type`, `animation_duration`
- **SubtitleTrack**: Track-level with `global_style`, `highlight_style`, `spotlight_style`, `position_x`, `position_y`, `animation_type`, `animation_duration`

### Apply-for-All System
- **Standard tab (segments)**: Each `SubtitleSegment.apply_for_all` (default `true`). When true, global style changes propagate. When false, segment has independent style/position/animation.
- **Highlight/Spotlight tab (words)**: Per-word via `StyledWord.style_override` presence. If `null`, word follows group global style. If set, word has independent style.
- **Use Global Style button**: Resets a customized segment/word back to global, with confirmation dialog.
- **Position grid (3×3)**: Sets `position_preset` for single words, or `position_x/y` for segments.

### web/editor.html — Style Panel Structure
- Top-level tabs: Style / Video / Presets (data-main-tab)
- Sub-tabs: Standard / Highlight / Spotlight (data-main-marker-tab)
- Standard: "Apply for all" checkbox + "Use Global Style" button + Position grid (📍)
- Specials: "Apply for all" checkbox + "Use Global Style" button
- 6 collapsible `<details>` groups per subsection (Font, Fill, Stroke, Shadow, Spacing, Opacity)
- ID convention: `{prefix}-{property}` where prefix = global | special

### web/js/editor.js — Control Bindings
- `initApplyForAllUI()`: wires Apply-for-All checkboxes and Use Global Style buttons
- `initPositionGrid()`: wires 3×3 position grid clicks
- `syncApplyForAllUI()`: syncs checkbox/button visibility with current selection
- `getSelectedSegment()`: returns segment object if all selected words belong to one segment
- `updateGlobalStyle(property, value)`: respects per-segment `apply_for_all` flag
- `updateMarkerStyle(property, value)`: respects per-word `style_override` presence
- `POSITION_PRESETS`: maps preset names to normalized (x, y) coordinates

### web/js/preview.js — Canvas Rendering
- Resolves position from `seg.position_x ?? track.position_x ?? 0.5`
- Resolves animation from `seg.animation_type ?? track.animation_type ?? 'none'`
- `getWordStyle()`: priority: style_override → marker style → segment style

### web/css/app.css — Component Styles
- `.pos-grid-btn` / `.pos-grid-btn.active`: 3×3 position grid button styles
- `.style-group` / `.style-group-header` / `.style-group-body`: collapsible section styling

### core/exporter.py — Video Export Rendering
- `_render_subtitle_on_frame()`: resolves per-segment animation_type/duration
- `_paint_subtitle_word_by_word()`: resolves per-segment position (seg → track fallback)
- `_paint_subtitle_uniform()`: resolves per-segment position and animation

## Changelog
- 2026-04-18: Fixed getSelectedSegment() to require full segment selection, setWordMarker() to re-render Segments panel chips, and timeline segment click to seek to midpoint.
- 2026-04-18: Per-segment Apply-for-All overhaul — segments can independently opt out of global style. Added Use Global Style button, position grid, per-segment position/animation. Fixed timeline indicator and seeking behavior.
- 2026-04-05: Added deterministic UI-only group highlighting to Timeline and Segments section
- 2026-04-05: Skia-Python Rendering Engine replacement
- 2026-04-04: Fixed export — added per-word rendering for special word styles
- 2025-04-02: Initial creation — full style engine implementation
