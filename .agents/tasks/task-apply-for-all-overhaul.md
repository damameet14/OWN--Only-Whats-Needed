# Task: Per-Segment Apply-for-All Overhaul

## Last Updated
2026-04-18

## Task Type
Heavy

## Summary
Overhaul the "Apply for all" system to operate per-segment (Standard) and per-word (Highlight/Spotlight), add "Use Global Style" button, per-segment position/animation, word position grid, and fix timeline selection bugs.

## Scope
**In scope**: Data model changes, Apply-for-all per-segment, Use Global Style button, position per segment/word, animation provision, bug fixes (timeline indicator, playbar seeking)
**Out of scope**: Custom animation types, export format changes

## Subtask 1: Data Model Changes
**Goal**: Add `apply_for_all`, position, animation fields to SubtitleSegment and StyledWord
**Acceptance criteria**: Fields serialize/deserialize correctly, backward compatible
**Status**: [ ] Not started

## Subtask 2: Bug Fixes — Timeline Indicator & Seeking
**Goal**: Fix editing indicator when clicking segment from timeline; seek to midpoint for words/segments
**Acceptance criteria**: Indicator shows segment words; playhead moves to midpoint
**Status**: [ ] Not started

## Subtask 3: Apply-for-All Engine & Use Global Style
**Goal**: Per-segment apply_for_all logic, Use Global Style button, Highlight/Spotlight word-level apply_for_all
**Acceptance criteria**: Style changes propagate correctly based on per-entity flags
**Status**: [ ] Not started

## Subtask 4: Position & Animation Per-Segment/Word
**Goal**: Per-segment position dragging, word position grid, per-segment animation provision
**Acceptance criteria**: Preview and exporter respect per-segment position; word grid works
**Status**: [ ] Not started

## Subtask 5: Preview & Exporter Updates
**Goal**: Update preview.js and exporter.py to resolve per-segment position/animation
**Acceptance criteria**: Per-segment position renders correctly in preview and export
**Status**: [ ] Not started

## Blockers
None

## Related Code
- .agents/code/code-style-engine.md
- .agents/code/code-web-frontend.md

## Related Architecture
- .agents/system/current_state.md

## Completion Criteria
All 9 manual verification steps from implementation plan pass

## Final Status
[ ] In progress
