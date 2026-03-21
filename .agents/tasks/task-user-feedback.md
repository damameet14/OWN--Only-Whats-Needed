# Task: user-feedback

## Last Updated
2026-03-21

## Task Type
Heavy

## Summary
Address comprehensive user feedback regarding missing tray app, UI/timeline bugs, export hanging, and add new features (element rotation, Ctrl+S save).

## Scope
**In scope**: `desktop/tray_app.py`, `web/js/timeline.js`, `web/js/editor.js`, `core/exporter.py`, Frontend UI rotation controls.
**Out of scope**: Changes to overall architecture or FastAPI routes unrelated to export progress.

## Subtask 1: Tray App & Export Bugs
**Goal**: Fix the system tray application launch behavior and ensure export progresses past "Rendering subtitles".
**Acceptance criteria**: Tray app icon is visible after starting `main.py`. Export correctly reaches 100% with logs.
**Status**: [x] Complete

## Subtask 2: Timeline & UI Dragging
**Goal**: Add Audio/Video tracks to timeline, smooth the seeking behavior, and allow free dragging of subtitles on canvas.
**Acceptance criteria**: Timeline shows distinct tracks; dragging seek thumb is smooth; user can drag subtitle text freely.
**Status**: [x] Complete

## Subtask 3: Features - Rotation & Save Shortcut
**Goal**: Allow rotational transforms for subtitles/video and implement Ctrl+S to save project.
**Acceptance criteria**: New UI handles for rotation exist and affect rendering/export. Ctrl+S triggers API save instead of browser save.
**Status**: [x] Complete

## Blockers
- None at the moment. All issues resolved.

## Related Code
- .agents/code/code-web-frontend.md
- .agents/code/code-desktop.md
- .agents/code/code-core-engines.md

## Related Architecture
- .agents/system/system_change-hybrid-architecture.md

## Completion Criteria
Tray icon launches successfully, timeline is smooth and detailed, subtitles are draggable and rotatable, video is rotatable, Ctrl+S saves, and export completes reliably.

## Final Status
[x] Complete
