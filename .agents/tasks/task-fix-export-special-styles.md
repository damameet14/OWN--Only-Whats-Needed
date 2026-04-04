# Task: Fix Export — Special Word Styles & Trimmed Text

## Last Updated
2026-04-04

## Task Type
Standard

## Summary
Fix the video export pipeline to render per-word special styles and prevent subtitle text trimming.

## Scope
**In scope**: `core/exporter.py` `_paint_subtitle()` — add word-level rendering
**Out of scope**: preview.js (already works), frontend controls, animation changes

## Subtask 1: Add per-word rendering to exporter
**Goal**: When a segment contains `is_special` words, render each word individually with its own style (via `style_override` or group style).
**Acceptance criteria**: Exported video shows different styles per special word, matching preview.
**Status**: [x] Complete

## Subtask 2: Fix text trimming / clamping
**Goal**: Correct text measurement when words have different font sizes so text isn't clipped.
**Acceptance criteria**: All subtitle text is fully visible in export, no trimming.
**Status**: [x] Complete

## Subtask 3: Update context documentation
**Goal**: Update code context and task index.
**Acceptance criteria**: All docs are current.
**Status**: [x] Complete

## Blockers
None

## Related Code
- .agents/code/code-style-engine.md

## Related Architecture
N/A — no architectural change

## Completion Criteria
Exported video renders special word styles correctly and text is not trimmed.

## Final Status
[x] Complete
