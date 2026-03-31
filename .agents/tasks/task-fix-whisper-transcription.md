# task-fix-whisper-transcription

Fix Whisper model selection not working during transcription — both from the Home page and the Editor.

## Last Updated
2026-03-31

## Status
[x] Complete

## Owner
agent

## Priority
High

## Task Type
Standard

## Root Causes Found

1. **Editor passed `{engine, model}` object as string arg** — `editor.js:845` called `startTranscription(id, {engine, model})` but the API function expected `(projectId, engine, language)` as positional string args.
2. **Server never forwarded `model` to background task** — `_run_transcription` never received the user-selected model name.
3. **Editor didn't send language** — the editor transcription call did not include the project's language.
4. **Browser caching** — `editor.html` had stale cache-buster versions (`?v=2`, `?v=4`), so browsers served old JS files.
5. **CRITICAL: Wrong HuggingFace repos** — `model_manager.py` downloaded from `openai/whisper-large-v3-turbo` (PyTorch `model.safetensors` format) instead of `Systran/faster-whisper-large-v3-turbo` (CTranslate2 `model.bin` format). `faster-whisper` cannot load PyTorch models.

## Subtasks
- [x] Fix `api.js` — `startTranscription()` to accept options object `{ engine, language, model }`
- [x] Fix `editor.js` — pass `{ engine, language, model }` options object
- [x] Fix `server/app.py` — forward `model` to `_run_transcription()`
- [x] Bump cache-buster versions in `editor.html` and `index.html`
- [x] Fix `model_manager.py` — use correct Systran CTranslate2 repos for faster-whisper
- [x] Add CTranslate2 format validation (model.bin check) with fallback
- [x] Remove bad model files and DB entry

## Files Modified
- `web/js/api.js` — `startTranscription()` now supports options object
- `web/js/editor.js` — transcription call passes engine, language, model correctly
- `web/editor.html` — bumped cache-buster versions (api.js?v=3, editor.js?v=5)
- `web/index.html` — added cache-buster versions (api.js?v=3, app.js?v=2)
- `server/app.py` — `_run_transcription()` accepts model_name, validates CTranslate2 format, fallback
- `server/model_manager.py` — fixed HuggingFace repos to Systran CTranslate2 format

## Related
- `.agents/code/code-server.md`
- `.agents/code/code-web-frontend.md`
- `.agents/tasks/task-fix-whisper-download.md`
