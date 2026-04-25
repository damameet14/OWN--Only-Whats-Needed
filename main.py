"""OWN — Only What's Needed.

Entry point: launches FastAPI server + system tray app.
"""

import sys
import os
import threading
import webbrowser
import time

# Ensure project root is in path
if getattr(sys, 'frozen', False):
    PROJECT_ROOT = os.path.dirname(sys.executable)
else:
    PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)


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
    print(f"\n🚀 Starting OWN server on port {port}...")
    server_thread = threading.Thread(
        target=start_server,
        args=("0.0.0.0", port),
        daemon=True,
    )
    server_thread.start()

    # Give server a moment to start
    time.sleep(2)

    # Open browser
    print(f"🌐 Opening {server_url} in your browser...")
    webbrowser.open(server_url)

    # Try to start tray app
    try:
        from desktop.tray_app import OWNTrayApp
        print("📌 Starting system tray icon...")
        tray = OWNTrayApp(server_thread=server_thread, server_url=server_url)
        tray.run()  # Runs detached now

        print("💻 Opening OWN Desktop application...")
        from desktop.main_window import OWNMainWindow
        main_window = OWNMainWindow(server_url=server_url)
        tray.set_main_window(main_window)
        
        if main_window.root:
            main_window.mainloop()
        else:
            # Fallback if UI is missing
            print("Press Ctrl+C to stop the server.")
            while True:
                time.sleep(1)

    except ImportError:
        print("ℹ pystray not installed — running without tray icon")
        print("Press Ctrl+C to stop the server.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n👋 Shutting down...")
    except Exception as e:
        print(f"Tray app error: {e}")
        print("Press Ctrl+C to stop the server.")
        try:
            server_thread.join()
        except KeyboardInterrupt:
            print("\n👋 Shutting down...")


if __name__ == "__main__":
    main()
