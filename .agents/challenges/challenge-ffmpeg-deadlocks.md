# Challenge: ffmpeg-deadlocks

## Context
During video export (`core/exporter.py`), the process involves a FFMPEG decoder pipe, a python middle layer using Pillow, and an FFMPEG encoder pipe. The export abruptly hung at exactly ~200 frames into processing. In our final attempts, generated MP4s were successfully saved but immediately seen as corrupted by video players.

## The Problem
1. **OS Buffer Deadlock:** The system created unread output pipes (`subprocess.PIPE`) for the encoder and decoder's `stderr` streams. FFMPEG generates massive amounts of status logging on `stderr`. Once the internal OS pipe buffer filled up (~64kb or ~200 frames), FFMPEG's internal standard error `write()` blocked indefinitely. Because the encoder blocked, it stopped reading from `stdin`. This caused the python script's `stdin.write()` to block infinitely, resulting in a deadlocked pipeline.
2. **Missing MP4 MOOV Atom:** After solving the deadlock, the python script ended cleanly and prematurely forcefully terminated (`SIGKILL` via `.kill()`) the FFMPEG encoder within the `finally` block of the exporter loop immediately after the last frame was piped. However, an MP4 container requires the `moov` atom trailer to be successfully flushed to disk AFTER all frames are received and muxed. Force-killing FFMPEG prevented it from writing this final header chunk, resulting in unplayable/corrupt files.

## The Solution
1. Configured all unused subprocess pipes (`stdout` / `stderr`) directly into `subprocess.DEVNULL` to securely discard the FFMPEG verbose logs and prevent any OS pipe freezing.
2. Refactored the `finally` cleanup block inside `_render_all_frames()`. Instead of `.kill()`, we now gracefully call `encoder.stdin.close()` to signal EOF, and invoke `encoder.wait(timeout=15)` to afford FFMPEG the requisite time to package the headers and officially close the output file intact, preserving playback validity.

## Related
- task-user-feedback.md
- code-core-engines.md
