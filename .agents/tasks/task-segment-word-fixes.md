# Task: Segment & Word Selection Fixes

## Last Updated
2026-04-18

## Task Type
Light

## Summary
Fix three bugs: word click modifying entire segment, marker changes not reflecting in Segments UI, and timeline segment click seeking to start instead of midpoint.

## Scope
**In scope**: `getSelectedSegment()` guard, `setWordMarker()` re-render, timeline midpoint seek
**Out of scope**: Per-word styling for Standard words, architectural changes

## Subtask 1: Fix word click scoping
**Goal**: `getSelectedSegment()` returns segment only when ALL words selected
**Acceptance criteria**: Clicking a single word does NOT scope style changes to that segment
**Status**: [x] Complete

## Subtask 2: Fix marker UI refresh
**Goal**: `setWordMarker()` re-renders Segments panel after marker change
**Acceptance criteria**: Marking a word Highlight/Spotlight immediately updates chip colours in Segments section
**Status**: [x] Complete

## Subtask 3: Fix timeline segment midpoint seek
**Goal**: Timeline segment click seeks to midpoint, not start
**Acceptance criteria**: Clicking a segment in the timeline places playhead at midpoint of segment duration
**Status**: [x] Complete

## Blockers
None

## Related Code
- .agents/code/code-web-frontend.md
- .agents/code/code-style-engine.md

## Related Architecture
N/A

## Completion Criteria
All three bugs resolved, verified in browser

## Final Status
[x] Complete
