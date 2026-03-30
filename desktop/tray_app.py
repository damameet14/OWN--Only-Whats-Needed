"""System tray icon for OWN — manages server lifecycle and provides quick actions."""

import os
import sys
import threading
import webbrowser
import subprocess
import requests
import time
from PIL import Image, ImageDraw

try:
    import pystray
except ImportError:
    pystray = None


_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_URL = "http://localhost:8080"


class OWNTrayApp:
    """System tray application for OWN."""

    def __init__(self, server_thread=None, server_url="http://localhost:80"):
        self.server_thread = server_thread
        self.server_url = server_url
        self.main_window = None

    def set_main_window(self, main_window):
        self.main_window = main_window

    def run(self):
        """Start the tray icon and immediately return (runs detached)."""
        if pystray is None:
            print("pystray not installed. Tray icon disabled.")
            return

        icon_image = self._create_icon_image()

        # Create model download submenu
        model_menu = pystray.Menu(
            pystray.MenuItem("Large v3 Turbo (800MB)", self._download_whisper_turbo),
            pystray.MenuItem("Large v3 (3GB)", self._download_whisper_large),
        )

        menu = pystray.Menu(
            pystray.MenuItem("Open OWN", self._open_window, default=True),
            pystray.MenuItem("Open in Browser", self._open_browser),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Download Models", model_menu),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Server Running", None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self._quit),
        )

        self.icon = pystray.Icon("OWN", icon_image, "OWN — Only What's Needed", menu)
        self.icon.run_detached()

    def _create_icon_image(self):
        """Create a simple icon programmatically (yellow CC on dark background)."""
        # Check for icon file first
        icon_path = os.path.join(_PROJECT_ROOT, "desktop", "assets", "icon.png")
        if os.path.exists(icon_path):
            return Image.open(icon_path)

        # Generate icon
        size = 64
        img = Image.new("RGBA", (size, size), (35, 32, 15, 255))
        draw = ImageDraw.Draw(img)

        # Yellow circle
        margin = 8
        draw.ellipse(
            [margin, margin, size - margin, size - margin],
            fill=(255, 231, 77, 255),
        )

        # CC text
        try:
            from PIL import ImageFont
            font = ImageFont.truetype("arial.ttf", 20)
        except Exception:
            font = ImageFont.load_default()

        draw.text((size // 2 - 12, size // 2 - 10), "CC", fill=(35, 32, 15, 255), font=font)
        return img

    def _open_window(self, icon=None, item=None):
        """Open the CustomTkinter desktop window safely from the background thread."""
        if self.main_window and self.main_window.root:
            try:
                # Schedule on the main thread! Tkinter requires this.
                self.main_window.root.after(0, self.main_window.deiconify)
                self.main_window.root.after(100, self.main_window.focus_force)
            except Exception:
                pass
        else:
            webbrowser.open(self.server_url)

    def _open_browser(self, icon=None, item=None):
        """Open the web UI in the default browser."""
        webbrowser.open(self.server_url)

    def _quit(self, icon=None, item=None):
        """Stop tray icon and signal app to exit."""
        if self.icon:
            self.icon.stop()
        if self.main_window and self.main_window.root:
            try:
                self.main_window.root.after(0, self.main_window.root.quit)
            except Exception:
                pass

    def _download_whisper_turbo(self, icon=None, item=None):
        """Download Whisper Large v3 Turbo model."""
        self._download_model("faster-whisper-large-v3-turbo")

    def _download_whisper_large(self, icon=None, item=None):
        """Download Whisper Large v3 model."""
        self._download_model("faster-whisper-large-v3")

    def _download_model(self, model_name: str):
        """Download a model in a background thread."""
        def _download():
            try:
                # Start download via API
                response = requests.post(
                    f"{self.server_url}/api/models/download",
                    json={"name": model_name},
                    timeout=10
                )
                response.raise_for_status()
                data = response.json()
                task_id = data.get("task_id")

                if task_id:
                    # Show notification
                    self._show_notification(f"Downloading {model_name}...")

                    # Poll for progress
                    while True:
                        try:
                            progress_resp = requests.get(
                                f"{self.server_url}/api/tasks/{task_id}",
                                timeout=5
                            )
                            progress_resp.raise_for_status()
                            progress_data = progress_resp.json()

                            percent = progress_data.get("percent", 0)
                            message = progress_data.get("message", "")

                            if percent >= 100 or percent < 0:
                                self._show_notification(f"{model_name} download complete!")
                                break
                            else:
                                self._show_notification(f"Downloading {model_name}: {percent}%")

                            time.sleep(2)
                        except requests.exceptions.Timeout:
                            continue
                        except Exception as e:
                            self._show_notification(f"Download error: {e}")
                            break
                else:
                    self._show_notification(f"Failed to start download: {data}")
            except Exception as e:
                self._show_notification(f"Download failed: {e}")

        # Run in background thread
        thread = threading.Thread(target=_download, daemon=True)
        thread.start()

    def _show_notification(self, message: str):
        """Show a system notification."""
        try:
            if sys.platform == "win32":
                from win10toast import ToastNotifier
                toaster = ToastNotifier()
                toaster.show_toast("OWN", message, duration=5)
            elif sys.platform == "darwin":
                # macOS notification
                os.system(f'osascript -e \'display notification with title "OWN" subtitle "{message}"\'')
            else:
                print(f"[OWN Tray] {message}")
        except Exception:
            print(f"[OWN Tray] {message}")
