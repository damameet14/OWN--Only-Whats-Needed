# Code Context: Desktop App

## Last Updated
2026-03-21

## Overview
Desktop layer consisting of a system tray icon (pystray), a management window (customtkinter), and a first-run setup script. Launched by `main.py` after starting the FastAPI server.

## Entry Points
- `main.py:main()` → `OWNTrayApp.run()` (blocking)
- `main.py:main()` → `run_first_time_setup()` (on first run only)

## Execution Flow
1. `main.py` checks `is_first_run()` → if true, runs `run_first_time_setup()` (hosts file + model check)
2. Starts FastAPI server on a daemon thread
3. Opens browser to `localhost`
4. Creates `OWNTrayApp` and calls `run()` — blocks on tray icon event loop
5. Tray menu: "Open OWN" launches `OWNMainWindow`, "Open in Browser" opens URL, "Quit" stops icon

## Functions / Methods / Classes
| Name | Type | File Path | Description | Calls / Used By |
|------|------|-----------|-------------|-----------------|
| `main` | fn | `main.py` | Entry point — server + tray + setup | `__main__` |
| `start_server` | fn | `main.py` | Runs `uvicorn.run()` | `main` (daemon thread) |
| `OWNTrayApp` | class | `desktop/tray_app.py` | pystray icon with menu | `main` |
| `OWNTrayApp.run` | method | `desktop/tray_app.py` | Starts tray icon event loop | `main` |
| `OWNTrayApp._create_icon_image` | method | `desktop/tray_app.py` | Generates yellow CC icon | `run` |
| `OWNTrayApp._open_window` | method | `desktop/tray_app.py` | Launches customtkinter window | Tray menu |
| `OWNMainWindow` | class | `desktop/main_window.py` | Tabbed UI (Home/Models/Users) | `_open_window` |
| `OWNMainWindow._list_local_models` | method | `desktop/main_window.py` | Scans for Vosk model dirs | Models tab |
| `OWNMainWindow._save_profile` | method | `desktop/main_window.py` | PUT /api/user via requests | Users tab |
| `is_first_run` | fn | `desktop/setup.py` | Checks `.setup_complete` marker | `main` |
| `run_first_time_setup` | fn | `desktop/setup.py` | Configures hosts + checks models | `main` |
| `configure_hosts_file` | fn | `desktop/setup.py` | Adds `own.local` to hosts file | `run_first_time_setup` |

## External Dependencies
- `pystray`, `customtkinter`, `Pillow` (for icon generation), `requests` (for profile save)

## Internal Dependencies
- Depends on `server/app.py` being running (for profile save API call)

## Related Tasks
- .agents/tasks/task-own-revamp.md

## Known Limitations
- `configure_hosts_file` requires admin/root privileges
- customtkinter and pystray are optional — app works without them (browser-only mode)
- Tray icon event loop is blocking — limits threading options

## Change Log
| Date | Change |
|------|--------|
| 2026-03-20 | Initial creation: tray_app, main_window, setup, main.py rewrite |
| 2026-03-21 | Fixed pystray tray app thread blocking issues, enabling icon visibility alongside FastAPI daemon. |
