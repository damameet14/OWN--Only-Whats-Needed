# task-fix-whisper-download

Fix the missing Whisper model download option in the tray app and improve model management in the desktop UI.

- [x] Update Tray Application labels and menu structure (`desktop/tray_app.py`)
- [x] Update Desktop Window "Models" tab to show all models (`desktop/main_window.py`)
- [x] Add model download triggering from the Desktop UI
- [x] Verify model download status reflects correctly in the UI

## Proposed Changes

### desktop/tray_app.py
- Rename labels of Whisper models to be more descriptive.
- Add Vosk models to the "Download Models" menu.

### desktop/main_window.py
- List all available models (Vosk and Whisper).
- Add functionality to trigger model downloads from the desktop UI.
