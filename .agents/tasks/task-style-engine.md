# Task: Style Engine Revamp

## Last Updated
2025-04-02

## Task Type
Heavy

## Summary
Replace legacy style controls with a structured, feature-rich interface supporting gradient fills, advanced shadow effects, typography controls, and video-level settings.

## Scope
**In scope**: SubtitleStyle model expansion, HTML style panel restructure (6 collapsible sections), JS control bindings, canvas preview rendering, exporter rendering
**Out of scope**: Custom font upload, preset management overhaul, SRT/export format changes

## Subtask 1: Data Model Expansion
**Goal**: Extend SubtitleStyle with font_weight, font_style, text_transform, fill_type, gradient fields, stroke/shadow toggles, blur, spacing, opacity
**Acceptance criteria**: `from_dict` backwards-compatible, all new fields have defaults
**Status**: [x] Complete

## Subtask 2: HTML UI Restructure
**Goal**: Add Video tab, rebuild Text tab with 6 collapsible sections (Font, Fill, Stroke, Shadow, Spacing, Opacity) for both All and Specials
**Acceptance criteria**: All controls have correct IDs matching JS bindings
**Status**: [x] Complete

## Subtask 3: JS Control Bindings (editor.js)
**Goal**: Wire all new controls to updateGlobalStyle / updateSpecialStyle, update applyTrackToControls and loadSpecialStyle for new fields
**Acceptance criteria**: All controls update subtitleTrack state and trigger preview refresh
**Status**: [x] Complete

## Subtask 4: Canvas Preview (preview.js)
**Goal**: Update rendering to support font_weight, font_style, text_transform, gradient fills, stroke/shadow toggles, shadow blur, letter spacing, text opacity
**Acceptance criteria**: Canvas renders gradients, blur shadows, and respects all new style properties
**Status**: [x] Complete

## Subtask 5: CSS Styling (app.css)
**Goal**: Add styles for collapsible style-group, style-label, style-select, style-range, style-color components
**Acceptance criteria**: New controls match existing dark theme aesthetic
**Status**: [x] Complete

## Subtask 6: Exporter (exporter.py)
**Goal**: Support all new style properties using cv2/numpy for gradient fills, Pillow for shadow blur
**Acceptance criteria**: Exported video matches canvas preview visually
**Status**: [x] Complete

## Blockers
None

## Related Code
- .agents/code/code-style-engine.md

## Related Architecture
- Models: models/subtitle.py (SubtitleStyle expanded)
- UI: web/editor.html (Style panel restructured)
- JS: web/js/editor.js (control bindings), web/js/preview.js (canvas rendering)
- CSS: web/css/app.css (new component styles)
- Backend: core/exporter.py (cv2/numpy gradient rendering)

## Completion Criteria
All 6 subtasks complete. UI loads without errors, controls update state, canvas renders all new properties.

## Final Status
[x] Complete
