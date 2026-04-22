# Task: Standard Word Style Override Fix

## Metadata
- **Status:** [x] Complete
- **Priority:** Light
- **Owner:** agent
- **Created:** 2026-04-22
- **Last Updated:** 2026-04-22

## Objective
Fix the issue where individual standard words selected from the "Segments" section could not be modified distinctly even if the "Apply for all" checkbox was unchecked. Also resolve the bug where the "Apply for all" checkbox would re-check itself automatically when the word was re-clicked.

## Subtasks
- [x] Identify root cause in `syncApplyForAllUI` and `updateGlobalStyle` (Word selections were unhandled in Standard tab)
- [x] Modify `syncApplyForAllUI` to check word `style_override` presence for standard words
- [x] Modify `initApplyForAllUI` to allow saving and removing `style_override` for individual standard words
- [x] Update `updateGlobalStyle` to mutate `style_override` instead of `global_style` when a single word is selected and "Apply for all" is unchecked
- [x] Update "Use Global Style" to reset a standard word's custom style back to global

## Proposed Changes
No architectural changes. Logic simply handles `selectedWords.length > 0 && !selSeg` branching within existing Standard UI controls.

## Blockers
None

## Related
- `.agents/code/code-editor.md`
