"""OWN — Only What's Needed.

Entry point: launches FastAPI server + system tray app.
"""

import sys
import os
import threading
import webbrowser
import time
import logging
import atexit

# Ensure project root is in path
if getattr(sys, 'frozen', False):
    PROJECT_ROOT = os.path.dirname(sys.executable)
else:
    PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)


# ── File logging setup ───────────────────────────────────────────────────────
# Set up file-based logging BEFORE any other module imports, so every logger
# (server, core, desktop, uvicorn, etc.) writes to the same log file.
# The log is created fresh on each launch and deleted on clean exit.

LOG_DIR = os.path.join(PROJECT_ROOT, "data")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "own_app.log")

# Delete old log from a previous session
if os.path.exists(LOG_FILE):
    try:
        os.remove(LOG_FILE)
    except OSError:
        pass

# Configure root logger with both console and file handlers
_log_formatter = logging.Formatter(
    "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

_file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
_file_handler.setLevel(logging.DEBUG)
_file_handler.setFormatter(_log_formatter)

_console_handler = logging.StreamHandler(sys.stdout)
_console_handler.setLevel(logging.INFO)
_console_handler.setFormatter(_log_formatter)

logging.basicConfig(
    level=logging.DEBUG,
    handlers=[_console_handler, _file_handler],
)

_logger = logging.getLogger("OWN")
_logger.info(f"Log file: {LOG_FILE}")


def _cleanup_log():
    """Delete the log file on clean exit."""
    _file_handler.close()
    try:
        if os.path.exists(LOG_FILE):
            os.remove(LOG_FILE)
    except OSError:
        pass

atexit.register(_cleanup_log)


def start_server(host: str = "0.0.0.0", port: int = 80):
    """Start the FastAPI server with uvicorn."""
    import uvicorn
    from server.app import app

    uvicorn.run(app, host=host, port=port, log_level="info")


def main():
    # Determine port (default 80, fallback to 8000 if not admin)
    port = 5888
    try:
        import ctypes
        if sys.platform == "win32" and ctypes.windll.shell32.IsUserAnAdmin() == 0:
            port = 5888  # Non-admin fallback
    except Exception:
        port = 5888

    server_url = f"http://localhost:{port}"

    # First-time setup
    from desktop.setup import is_first_run, run_first_time_setup
    if is_first_run():
        print("\n🎬 OWN — First Time Setup")
        print("═" * 40)
        run_first_time_setup()
        print("═" * 40)
        print()

    # Start server in background thread
    _logger.info(f"Starting OWN server on port {port}...")
    server_thread = threading.Thread(
        target=start_server,
        args=("0.0.0.0", port),
        daemon=True,
    )
    server_thread.start()

    # Give server a moment to start
    time.sleep(2)

    # Open browser
    _logger.info(f"Opening {server_url} in browser...")
    webbrowser.open(server_url)

    # Try to start tray app
    try:
        from desktop.tray_app import OWNTrayApp
        _logger.info("Starting system tray icon...")
        tray = OWNTrayApp(server_thread=server_thread, server_url=server_url)
        tray.run()  # Runs detached now

        _logger.info("Opening OWN Desktop application...")
        from desktop.main_window import OWNMainWindow
        main_window = OWNMainWindow(server_url=server_url)
        tray.set_main_window(main_window)
        
        if main_window.root:
            main_window.mainloop()
        else:
            # Fallback if UI is missing
            _logger.info("Desktop UI unavailable. Press Ctrl+C to stop the server.")
            while True:
                time.sleep(1)

    except ImportError:
        _logger.info("pystray not installed — running without tray icon")
        print("Press Ctrl+C to stop the server.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            _logger.info("Shutting down...")
    except Exception as e:
        _logger.error(f"Tray app error: {e}", exc_info=True)
        print("Press Ctrl+C to stop the server.")
        try:
            server_thread.join()
        except KeyboardInterrupt:
            _logger.info("Shutting down...")


if __name__ == "__main__":
    main()
