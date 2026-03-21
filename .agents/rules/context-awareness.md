---
trigger: always_on
---

# Always read this before giving any output
# Context Awareness

## Purpose
Non-compliance is a blocking error. Verify context is current before every action. Fix missing or outdated files before proceeding. 
* Update the documentation before proceeding with the task.
* Update the documentation after each file change. 
* Update the documentation after the task is completed according to the agent. 
* Update the documentaion with user's critics on the task and changes/fixes done
* Update the documentation when the task is completed as per the users
* __All the Documentation update will be done inside .agents/ in the project directory into their respective directories__
> If code contradicts a context file → the context file is wrong → fix it before continuing.

---

## Task Tiers

| Tier         | When                          | Required on completion                                               |
| ------------ | ----------------------------- | -------------------------------------------------------------------- |
| **Light**    | Single-file fix, <30 min      | Task file + code context + `index.md`                                |
| **Standard** | Default                       | Full checklist                                                       |
| **Heavy**    | Architecture or multi-feature | Full checklist + `system_change-*` + `current_state.md` + challenges |

Escalate if: >30 min or multiple files → Standard. Architecture/schema change → Heavy. When in doubt, go higher.

---

## Checklist

### Before starting:
- [ ] Read `.agents/tasks/index.md` — check for conflicts
- [ ] Read or create `.agents/tasks/task-[name].md` (template: `.agents/rules/templates/task.md`)
- [ ] Set Task Type (Light / Standard / Heavy)
- [ ] Read `.agents/system/current_state.md`
- [ ] Read relevant `.agents/code/code-[feature].md` files

### Before writing code:
- [ ] Identify affected `.agents/code/` files
- [ ] Note new functions/classes — must be documented before completion
- [ ] Removing a feature → rename to `deprecated` first
- [ ] Architecture change → add `## Proposed Changes` to task file

### During execution:
- [ ] Update context files in real-time, not after
- [ ] Keep `Blockers` current
- [ ] Maintain `Proposed Changes` if architecture is affected

### Before marking complete:
- [ ] Subtask statuses updated
- [ ] Final status set to `[x] Complete`
- [ ] `Last Updated` date updated
- [ ] Code context changelog entry added for every modified file
- [ ] `index.md` updated
- [ ] Architecture changed → `system_change-*` created + `current_state.md` updated
- [ ] Hard problem solved → `challenge-[name].md` created
- [ ] Context Validator passed (see below)

---

## Context Validator

| Check                         | Condition                        | If failed  |
| ----------------------------- | -------------------------------- | ---------- |
| Code context current          | Function/class added or removed  | ❌ Blocking |
| Changelog entry exists        | Any code file modified           | ❌ Blocking |
| System change logged          | Architectural change made        | ❌ Blocking |
| `current_state.md` updated    | Architecture changed             | ❌ Blocking |
| `current_state.md` consistent | Matches latest `system_change-*` | ❌ Blocking |
| Task index updated            | Task status changed              | ❌ Blocking |
| Proposed Changes cleared      | Task complete                    | ❌ Blocking |
| Related links filled          | Task / code / challenge created  | ❌ Blocking |
| `Last Updated` current        | Any file modified                | ❌ Blocking |
| Challenge documented          | Hard problem solved              | ⚠️ Warning  |

---

## Read-Only Mode
No code or context changes? Skip update requirements. Still read `current_state.md` and relevant code context files.

---

## Violations and Recovery
1. Stop immediately
2. Fix context files
3. Resume only after context is accurate

Never rely on session memory.

---

## File Map

| What                 | Path                                                | Template                       |
| -------------------- | --------------------------------------------------- | ------------------------------ |
| Current architecture | `.agents/system/current_state.md`                   | `templates/current_state.md`   |
| Data dictionary      | `.agents/system/data_dictionary/data_dictionary.md` | `templates/data_dictionary.md` |
| Architecture change  | `.agents/system/system_change-[name].md`            | `templates/system_change.md`   |
| Task index           | `.agents/tasks/index.md`                            | `templates/task_index.md`      |
| Task file            | `.agents/tasks/task-[name].md`                      | `templates/task.md`            |
| Code context         | `.agents/code/code-[name].md`                       | `templates/code_context.md`    |
| Challenge            | `.agents/challenges/challenge-[name].md`            | `templates/challenge.md`       |

**When creating any file: read its template first.**

---

## General Rules

- Naming: kebab-case only, no spaces or underscores
- Dates: `YYYY-MM-DD` always
- No duplication: one source of truth per fact, cross-reference by path
- No silent changes: update all affected context files
- Linking mandatory: no isolated files — Related sections must be filled
- Granularity: features are logical units, not individual functions
- Owner required: every task has an owner; unowned = `unassigned`