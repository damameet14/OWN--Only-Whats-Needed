"""CustomTkinter main window for OWN — Home, Models, and Users tabs."""

import os
import sys
import threading
import webbrowser

try:
    import customtkinter as ctk
except ImportError:
    ctk = None

if getattr(sys, 'frozen', False):
    _PROJECT_ROOT = os.path.dirname(sys.executable)
else:
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

        self.is_downloading = False
        self.download_buttons = []
        self._active_task_id = None

        self._build_ui()
        self._poll_active_tasks()

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
        self._models_tab = self.tabs.add("Models")

        ctk.CTkLabel(self._models_tab, text="Installed Models", font=("Inter", 18, "bold"),
                      text_color="#fff").pack(pady=(20, 10), anchor="w", padx=16)

        # Progress UI (packed first, then hidden — keeps correct order when shown)
        self.progress_frame = ctk.CTkFrame(self._models_tab, fg_color="#23200f", corner_radius=8)
        self.progress_label = ctk.CTkLabel(self.progress_frame, text="Downloading...", font=("Inter", 12), text_color="#ffe74d")
        self.progress_label.pack(side="left", padx=12, pady=10)
        self.cancel_btn = ctk.CTkButton(
            self.progress_frame, text="✕ Cancel", font=("Inter", 10, "bold"),
            fg_color="#ef4444", text_color="#fff", hover_color="#dc2626",
            width=70, height=26, corner_radius=6,
            command=self._cancel_download
        )
        self.cancel_btn.pack(side="right", padx=(0, 12), pady=10)
        self.progress_bar = ctk.CTkProgressBar(self.progress_frame, progress_color="#34d399")
        self.progress_bar.pack(side="right", padx=12, pady=10, fill="x", expand=True)
        self.progress_bar.set(0)
        # Start hidden
        self.progress_frame.pack(fill="x", padx=16, pady=5)
        self.progress_frame.pack_forget()

        # Models list (will be populated at runtime)
        self.models_frame = ctk.CTkScrollableFrame(self._models_tab, fg_color="#352f1a", corner_radius=12)
        self.models_frame.pack(fill="both", expand=True, padx=16, pady=5)

        # Scan for models
        self._list_local_models()

        # Bottom buttons frame
        self.models_btn_frame = ctk.CTkFrame(self._models_tab, fg_color="transparent")
        self.models_btn_frame.pack(pady=10, fill="x", padx=16)

        self.refresh_btn = ctk.CTkButton(
            self.models_btn_frame, text="Refresh Models", font=("Inter", 12),
            fg_color="#23200f", text_color="#ffe74d", border_width=1,
            border_color="#ffe74d", hover_color="#352f1a", width=120,
            command=self._list_local_models
        )
        self.refresh_btn.pack(side="left", padx=(0, 10))
        
        self.install_zip_btn = ctk.CTkButton(
            self.models_btn_frame, text="Install from ZIP", font=("Inter", 12, "bold"),
            fg_color="#ffe74d", text_color="#23200f", hover_color="#ffd700", width=120,
            command=self._install_from_zip
        )
        self.install_zip_btn.pack(side="right")

    def _list_local_models(self):
        """Scan for both Vosk and Whisper models and show download status."""
        import requests
        self.download_buttons.clear()
        for widget in self.models_frame.winfo_children():
            widget.destroy()

        # Get installed models from root (Vosk)
        vosk_model_dirs = [
            d for d in os.listdir(_PROJECT_ROOT)
            if os.path.isdir(os.path.join(_PROJECT_ROOT, d))
            and d.startswith("vosk-model")
        ]

        # Get installed models from models/ directory (Whisper)
        models_dir = os.path.join(_PROJECT_ROOT, "models")
        whisper_model_dirs = []
        if os.path.isdir(models_dir):
            whisper_model_dirs = [
                d for d in os.listdir(models_dir)
                if os.path.isdir(os.path.join(models_dir, d))
                and (d.startswith("faster-whisper") or d.startswith("whisper"))
            ]

        installed_names = set(vosk_model_dirs + whisper_model_dirs)

        # Get all available models from API
        try:
            resp = requests.get(f"{self.server_url}/api/models/available", timeout=5)
            available_models = resp.json() if resp.status_code == 200 else []
        except Exception:
            available_models = []

        # List models
        if not available_models and not installed_names:
            ctk.CTkLabel(self.models_frame, text="No models found. Check server connection.",
                          font=("Inter", 12), text_color="#a8a48e").pack(pady=20)
            return

        for model_info in available_models:
            name = model_info["name"]
            label = model_info["label"]
            is_installed = model_info.get("installed", False) or name in installed_names

            row = ctk.CTkFrame(self.models_frame, fg_color="#23200f", corner_radius=8)
            row.pack(fill="x", pady=4, padx=4)

            # Icon based on engine
            icon = "🎙️" if model_info.get("engine") == "whisper" else "📦"
            
            ctk.CTkLabel(row, text=f"{icon} {label}", font=("Inter", 12, "bold"),
                          text_color="#fff").pack(side="left", padx=12, pady=10)

            if is_installed:
                ctk.CTkLabel(row, text="Installed", font=("Inter", 11),
                              text_color="#34d399").pack(side="right", padx=12, pady=10)
            else:
                btn = ctk.CTkButton(
                    row, text="Download", font=("Inter", 10, "bold"),
                    fg_color="#ffe74d", text_color="#23200f",
                    width=80, height=26, corner_radius=6,
                    state="disabled" if self.is_downloading else "normal",
                    command=lambda n=name: self._download_model(n)
                )
                btn.pack(side="right", padx=12, pady=8)
                self.download_buttons.append(btn)

    def _download_model(self, model_name):
        """Trigger model download via API."""
        import requests
        try:
            resp = requests.post(
                f"{self.server_url}/api/models/download",
                json={"name": model_name},
                timeout=5
            )
            if resp.status_code == 200:
                data = resp.json()
                task_id = data.get("task_id")
                print(f"Started download for {model_name} (task_id={task_id})")
                # Store task_id immediately so Cancel works right away
                self._active_task_id = task_id
                # Immediately show progress bar
                self.is_downloading = True
                self._show_progress()
                self.progress_bar.set(0)
                self.progress_label.configure(text=f"Starting {model_name}...")
                for btn in self.download_buttons:
                    try:
                        btn.configure(state="disabled")
                    except Exception:
                        pass
                # Kick off fast polling immediately
                self.root.after(1000, self._poll_active_tasks)
        except Exception as e:
            print(f"Download error: {e}")

    def _cancel_download(self):
        """Cancel the active model download via API."""
        if not self._active_task_id:
            return

        # Immediate visual feedback
        self.cancel_btn.configure(state="disabled", text="Cancelling...")
        self.progress_label.configure(text="Cancelling download...")

        task_id = self._active_task_id

        def _do_cancel():
            import requests as _req
            try:
                _req.post(
                    f"{self.server_url}/api/tasks/{task_id}/cancel",
                    timeout=5
                )
            except Exception:
                pass
            # Schedule a quick poll so the UI picks up the cancelled state fast
            try:
                self.root.after(500, self._poll_active_tasks)
            except Exception:
                pass

        threading.Thread(target=_do_cancel, daemon=True).start()

    def _install_from_zip(self):
        from tkinter import filedialog, simpledialog
        import threading
        
        zip_path = filedialog.askopenfilename(
            title="Select Model ZIP",
            filetypes=[("ZIP Archives", "*.zip")]
        )
        if not zip_path:
            return
            
        # Determine engine
        engine = "whisper"
        if "llama" in zip_path.lower() or "gemma" in zip_path.lower():
            engine = "llama"
            
        # Ask for name
        default_name = os.path.basename(zip_path).replace(".zip", "")
        model_name = simpledialog.askstring("Model Name", "Enter a name for this model:", initialvalue=default_name)
        if not model_name:
            return

        self.is_downloading = True
        self._show_progress()
        self.progress_bar.set(0)
        self.progress_bar.configure(mode="indeterminate")
        self.progress_bar.start()
        self.progress_label.configure(text=f"Extracting {model_name}...")
        self.cancel_btn.configure(state="disabled", text="Please wait")

        for btn in self.download_buttons:
            try:
                btn.configure(state="disabled")
            except Exception:
                pass

        def _do_upload():
            import requests as _req
            try:
                with open(zip_path, 'rb') as f:
                    resp = _req.post(
                        f"{self.server_url}/api/models/upload",
                        data={"name": model_name, "engine": engine},
                        files={"file": (os.path.basename(zip_path), f, "application/zip")}
                    )
                
                # Update UI safely
                if self.root:
                    self.root.after(0, lambda: self._on_upload_complete(resp.status_code == 200))
            except Exception as e:
                print(f"Zip upload failed: {e}")
                if self.root:
                    self.root.after(0, lambda: self._on_upload_complete(False))

        threading.Thread(target=_do_upload, daemon=True).start()

    def _on_upload_complete(self, success: bool):
        self.progress_bar.stop()
        self.progress_bar.configure(mode="determinate")
        self.is_downloading = False
        self._hide_progress()
        self.cancel_btn.configure(state="normal", text="✕ Cancel")
        self._list_local_models()

    def _poll_active_tasks(self):
        """Poll the server for any active tasks and update the progress bar.
        Runs the HTTP request in a background thread to avoid blocking tkinter."""
        if not self.root:
            return

        def _fetch():
            import requests as _req
            try:
                resp = _req.get(f"{self.server_url}/api/tasks/active", timeout=2)
                if resp.status_code == 200:
                    return resp.json()
            except Exception:
                pass
            return None

        def _on_result(active_tasks):
            if not self.root:
                return

            if active_tasks:
                # Find first active task
                download_task = None
                task_id = None
                for tid, t in active_tasks.items():
                    download_task = t
                    task_id = tid
                    break

                if download_task:
                    self._active_task_id = task_id
                    pct = max(0, min(100, download_task.get("percent", 0)))
                    msg = download_task.get("message", "Downloading...")

                    if not self.is_downloading:
                        self.is_downloading = True
                        self._show_progress()
                        for btn in self.download_buttons:
                            try:
                                btn.configure(state="disabled")
                            except Exception:
                                pass

                    self.progress_bar.set(pct / 100.0)
                    self.progress_label.configure(text=f"{msg} ({pct}%)")
                else:
                    self._finish_download()
            else:
                self._finish_download()

            # Re-schedule only while downloading
            if self.is_downloading:
                self.root.after(2000, self._poll_active_tasks)

        def _bg_poll():
            result = _fetch()
            # Schedule UI update on main thread
            try:
                self.root.after(0, lambda: _on_result(result))
            except Exception:
                pass

        thread = threading.Thread(target=_bg_poll, daemon=True)
        thread.start()

    def _show_progress(self):
        """Show the progress bar by repacking widgets in the correct order."""
        # Unpack models and refresh, show progress, repack in order
        self.refresh_btn.pack_forget()
        self.models_frame.pack_forget()
        self.progress_frame.pack(fill="x", padx=16, pady=5)
        self.models_frame.pack(fill="both", expand=True, padx=16, pady=5)
        self.refresh_btn.pack(pady=10)

    def _finish_download(self):
        """Called when no active tasks remain — hide progress and refresh."""
        if self.is_downloading:
            self.is_downloading = False
            self._active_task_id = None
            self.progress_frame.pack_forget()
            self.progress_bar.set(0)
            # Reset cancel button for next download
            self.cancel_btn.configure(state="normal", text="✕ Cancel")
            for btn in self.download_buttons:
                try:
                    btn.configure(state="normal")
                except Exception:
                    pass
            self._list_local_models()

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
