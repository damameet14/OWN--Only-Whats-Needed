"""CustomTkinter main window for OWN — Home, Models, and Users tabs."""

import os
import sys
import threading
import webbrowser

try:
    import customtkinter as ctk
except ImportError:
    ctk = None

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)


class OWNMainWindow:
    """Desktop management window with tabs for Home, Models, and Users."""

    def __init__(self, server_url="http://localhost:80"):
        if ctk is None:
            print("customtkinter not installed. Desktop UI disabled.")
            return

        self.server_url = server_url
        self.root = ctk.CTk()
        self.root.title("OWN — Only What's Needed")
        self.root.geometry("700x500")
        self.root.minsize(600, 400)

        # Hide to tray instead of closing
        self.root.protocol("WM_DELETE_WINDOW", self.root.withdraw)

        # Colors
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")

        self._build_ui()

    def _build_ui(self):
        # Header
        header = ctk.CTkFrame(self.root, fg_color="#23200f", height=60)
        header.pack(fill="x", padx=0, pady=0)
        header.pack_propagate(False)

        ctk.CTkLabel(header, text="🎬 OWN", font=("Inter", 20, "bold"),
                      text_color="#ffe74d").pack(side="left", padx=16, pady=10)
        ctk.CTkLabel(header, text="Only What's Needed", font=("Inter", 11),
                      text_color="#a8a48e").pack(side="left", padx=0, pady=10)

        # Tabview
        self.tabs = ctk.CTkTabview(self.root, fg_color="#2d2914",
                                    segmented_button_fg_color="#23200f",
                                    segmented_button_selected_color="#ffe74d",
                                    segmented_button_selected_hover_color="#ffd700",
                                    text_color="#23200f")
        self.tabs.pack(fill="both", expand=True, padx=16, pady=16)

        self._build_home_tab()
        self._build_models_tab()
        self._build_users_tab()

    def _build_home_tab(self):
        tab = self.tabs.add("Home")

        # Welcome
        ctk.CTkLabel(tab, text="Welcome to OWN!", font=("Inter", 24, "bold"),
                      text_color="#fff").pack(pady=(30, 5))
        ctk.CTkLabel(tab, text="Auto-caption your videos with offline AI",
                      font=("Inter", 14), text_color="#a8a48e").pack(pady=(0, 30))

        # Status
        status_frame = ctk.CTkFrame(tab, fg_color="#352f1a", corner_radius=12)
        status_frame.pack(fill="x", padx=40, pady=10)

        ctk.CTkLabel(status_frame, text="● Server Running", font=("Inter", 13),
                      text_color="#34d399").pack(pady=12, padx=16, anchor="w")

        # Open in Browser button
        ctk.CTkButton(
            tab, text="Open in Browser", font=("Inter", 14, "bold"),
            fg_color="#ffe74d", text_color="#23200f",
            hover_color="#ffd700", height=44, corner_radius=10,
            command=lambda: webbrowser.open(self.server_url)
        ).pack(pady=20)

        ctk.CTkLabel(tab, text=f"Access at: {self.server_url}",
                      font=("Inter", 11), text_color="#a8a48e").pack()

    def _build_models_tab(self):
        tab = self.tabs.add("Models")

        ctk.CTkLabel(tab, text="Installed Models", font=("Inter", 18, "bold"),
                      text_color="#fff").pack(pady=(20, 10), anchor="w", padx=16)

        # Models list (will be populated at runtime)
        self.models_frame = ctk.CTkScrollableFrame(tab, fg_color="#352f1a", corner_radius=12)
        self.models_frame.pack(fill="both", expand=True, padx=16, pady=10)

        # Scan for models
        self._list_local_models()

        # Refresh button
        ctk.CTkButton(
            tab, text="Refresh Models", font=("Inter", 12),
            fg_color="#23200f", text_color="#ffe74d", border_width=1,
            border_color="#ffe74d", hover_color="#352f1a",
            command=self._list_local_models
        ).pack(pady=10)

    def _list_local_models(self):
        """Scan for Vosk model directories in the project root."""
        for widget in self.models_frame.winfo_children():
            widget.destroy()

        model_dirs = [
            d for d in os.listdir(_PROJECT_ROOT)
            if os.path.isdir(os.path.join(_PROJECT_ROOT, d))
            and d.startswith("vosk-model")
        ]

        if not model_dirs:
            ctk.CTkLabel(self.models_frame, text="No models found. Download one via the web UI.",
                          font=("Inter", 12), text_color="#a8a48e").pack(pady=20)
            return

        for model_name in model_dirs:
            model_path = os.path.join(_PROJECT_ROOT, model_name)
            size = sum(
                os.path.getsize(os.path.join(dp, f))
                for dp, _, fnames in os.walk(model_path)
                for f in fnames
            )
            size_mb = size / (1024 * 1024)

            row = ctk.CTkFrame(self.models_frame, fg_color="#23200f", corner_radius=8)
            row.pack(fill="x", pady=4, padx=4)

            ctk.CTkLabel(row, text=f"📦 {model_name}", font=("Inter", 13, "bold"),
                          text_color="#fff").pack(side="left", padx=12, pady=10)
            ctk.CTkLabel(row, text=f"{size_mb:.0f} MB", font=("Inter", 11),
                          text_color="#a8a48e").pack(side="right", padx=12, pady=10)

    def _build_users_tab(self):
        tab = self.tabs.add("Users")

        ctk.CTkLabel(tab, text="User Profile", font=("Inter", 18, "bold"),
                      text_color="#fff").pack(pady=(20, 20), anchor="w", padx=16)

        form = ctk.CTkFrame(tab, fg_color="#352f1a", corner_radius=12)
        form.pack(fill="x", padx=16, pady=10)

        # Name
        ctk.CTkLabel(form, text="Name", font=("Inter", 12), text_color="#a8a48e").pack(anchor="w", padx=16, pady=(16, 2))
        self.name_entry = ctk.CTkEntry(form, placeholder_text="Your Name", fg_color="#23200f")
        self.name_entry.pack(fill="x", padx=16, pady=(0, 8))

        # Email
        ctk.CTkLabel(form, text="Email", font=("Inter", 12), text_color="#a8a48e").pack(anchor="w", padx=16, pady=(8, 2))
        self.email_entry = ctk.CTkEntry(form, placeholder_text="email@example.com", fg_color="#23200f")
        self.email_entry.pack(fill="x", padx=16, pady=(0, 8))

        # Mobile
        ctk.CTkLabel(form, text="Mobile", font=("Inter", 12), text_color="#a8a48e").pack(anchor="w", padx=16, pady=(8, 2))
        self.mobile_entry = ctk.CTkEntry(form, placeholder_text="+91-XXXXXXXXXX", fg_color="#23200f")
        self.mobile_entry.pack(fill="x", padx=16, pady=(0, 16))

        # Save button
        ctk.CTkButton(
            tab, text="Save Profile", font=("Inter", 14, "bold"),
            fg_color="#ffe74d", text_color="#23200f",
            hover_color="#ffd700", height=40, corner_radius=10,
            command=self._save_profile
        ).pack(pady=16)

    def _save_profile(self):
        """Save user profile via API."""
        import requests
        name = self.name_entry.get()
        email = self.email_entry.get()
        mobile = self.mobile_entry.get()

        try:
            requests.put(
                f"{self.server_url}/api/user",
                json={"name": name, "email": email, "mobile": mobile},
                timeout=5,
            )
        except Exception as e:
            print(f"Save profile error: {e}")

    def mainloop(self):
        if self.root:
            self.root.mainloop()

    def deiconify(self):
        if self.root:
            self.root.deiconify()

    def focus_force(self):
        if self.root:
            self.root.focus_force()
