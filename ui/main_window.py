"""Main window — orchestrates all panels and core logic."""

from __future__ import annotations
import os
import sys

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont, QFontDatabase, QAction, QKeySequence, QIcon
from PySide6.QtWidgets import (
    QMainWindow, QSplitter, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFileDialog, QProgressDialog, QMessageBox,
    QApplication, QStatusBar, QToolBar, QSizePolicy,
)

from core.video_utils import get_video_info, get_input_filter, VideoInfo
from core.transcriber import TranscriberWorker
from core.srt_utils import save_srt
from models.subtitle import SubtitleTrack, WordTiming
from models.animations import AnimationType

from ui.video_preview import VideoPreviewWidget
from ui.timeline_widget import TimelineWidget
from ui.transcript_editor import TranscriptEditor
from ui.style_panel import StylePanel
from ui.export_dialog import ExportDialog

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class MainWindow(QMainWindow):
    """Application main window."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Hindi Auto Captioner")
        self.setMinimumSize(1280, 720)
        self.resize(1440, 860)

        self._video_path: str | None = None
        self._video_info: VideoInfo | None = None
        self._track = SubtitleTrack()
        self._word_timings: list[WordTiming] = []
        self._transcriber: TranscriberWorker | None = None
        self._playback_timer = QTimer(self)
        self._playback_timer.setInterval(33)  # ~30 fps
        self._playback_timer.timeout.connect(self._on_playback_tick)

        self._load_fonts()
        self._setup_ui()
        self._setup_menu()
        self._setup_toolbar()
        self._setup_statusbar()
        self._connect_signals()
        self._apply_dark_theme()

    # ── Font loading ──────────────────────────────────────────────────────

    def _load_fonts(self):
        fonts_dir = os.path.join(_PROJECT_ROOT, "fonts")
        if os.path.isdir(fonts_dir):
            for fname in os.listdir(fonts_dir):
                if fname.lower().endswith((".ttf", ".otf")):
                    path = os.path.join(fonts_dir, fname)
                    QFontDatabase.addApplicationFont(path)

    # ── UI Setup ──────────────────────────────────────────────────────────

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── Top splitter (preview | style+transcript) ────────────────
        self._top_splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: Video preview
        self._preview = VideoPreviewWidget()
        self._top_splitter.addWidget(self._preview)

        # Right: Style panel + Transcript editor stacked
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        self._right_splitter = QSplitter(Qt.Orientation.Vertical)

        self._style_panel = StylePanel()
        self._right_splitter.addWidget(self._style_panel)

        self._transcript_editor = TranscriptEditor()
        self._right_splitter.addWidget(self._transcript_editor)

        self._right_splitter.setSizes([300, 400])
        right_layout.addWidget(self._right_splitter)

        self._top_splitter.addWidget(right_panel)
        self._top_splitter.setSizes([800, 400])

        main_layout.addWidget(self._top_splitter, 1)

        # ── Bottom: Playback controls + Timeline ──────────────────────
        bottom_panel = QWidget()
        bottom_panel.setStyleSheet("background-color: #1a1a1a;")
        bottom_layout = QVBoxLayout(bottom_panel)
        bottom_layout.setContentsMargins(8, 4, 8, 4)
        bottom_layout.setSpacing(4)

        # Playback controls
        controls = QHBoxLayout()

        self._play_btn = QPushButton("▶ Play")
        self._play_btn.setFixedSize(80, 32)
        self._play_btn.setStyleSheet(self._control_btn_style())
        self._play_btn.clicked.connect(self._toggle_play)
        controls.addWidget(self._play_btn)

        self._time_label = QLabel("00:00.0 / 00:00.0")
        self._time_label.setStyleSheet("color: #aaa; font-family: 'Consolas'; font-size: 13px;")
        controls.addWidget(self._time_label)
        controls.addStretch()

        bottom_layout.addLayout(controls)

        # Timeline
        self._timeline = TimelineWidget()
        bottom_layout.addWidget(self._timeline)

        main_layout.addWidget(bottom_panel)

    def _setup_menu(self):
        menubar = self.menuBar()
        menubar.setStyleSheet("""
            QMenuBar { background: #1e1e1e; color: #e0e0e0; }
            QMenuBar::item:selected { background: #3A6EA5; }
            QMenu { background: #2a2a2a; color: #e0e0e0; border: 1px solid #444; }
            QMenu::item:selected { background: #3A6EA5; }
        """)

        # File menu
        file_menu = menubar.addMenu("&File")

        open_action = QAction("&Open Video…", self)
        open_action.setShortcut(QKeySequence("Ctrl+O"))
        open_action.triggered.connect(self._open_video)
        file_menu.addAction(open_action)

        file_menu.addSeparator()

        export_srt = QAction("Export &SRT…", self)
        export_srt.setShortcut(QKeySequence("Ctrl+Shift+S"))
        export_srt.triggered.connect(self._export_srt)
        file_menu.addAction(export_srt)

        export_video = QAction("&Export Video…", self)
        export_video.setShortcut(QKeySequence("Ctrl+E"))
        export_video.triggered.connect(self._export_video)
        file_menu.addAction(export_video)

        file_menu.addSeparator()
        exit_action = QAction("E&xit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Edit menu
        edit_menu = menubar.addMenu("&Edit")
        transcribe_action = QAction("&Transcribe", self)
        transcribe_action.setShortcut(QKeySequence("Ctrl+T"))
        transcribe_action.triggered.connect(self._start_transcription)
        edit_menu.addAction(transcribe_action)

        regroup_action = QAction("&Re-group Segments", self)
        regroup_action.triggered.connect(self._regroup_segments)
        edit_menu.addAction(regroup_action)

    def _setup_toolbar(self):
        toolbar = QToolBar("Main Toolbar")
        toolbar.setMovable(False)
        toolbar.setStyleSheet("""
            QToolBar {
                background: #1e1e1e; border-bottom: 1px solid #333;
                spacing: 6px; padding: 4px;
            }
            QToolButton {
                color: #e0e0e0; background: #2a2a2a; border: 1px solid #444;
                border-radius: 4px; padding: 6px 12px; font-size: 12px;
            }
            QToolButton:hover { background: #3A6EA5; border-color: #5B9BD5; }
        """)
        self.addToolBar(toolbar)

        open_act = toolbar.addAction("📂 Open")
        open_act.triggered.connect(self._open_video)

        self._transcribe_act = toolbar.addAction("🎙️ Transcribe")
        self._transcribe_act.triggered.connect(self._start_transcription)
        self._transcribe_act.setEnabled(False)

        toolbar.addSeparator()

        export_srt_act = toolbar.addAction("📄 Export SRT")
        export_srt_act.triggered.connect(self._export_srt)

        export_vid_act = toolbar.addAction("🎬 Export Video")
        export_vid_act.triggered.connect(self._export_video)

    def _setup_statusbar(self):
        self._statusbar = QStatusBar()
        self._statusbar.setStyleSheet(
            "QStatusBar { background: #1a1a1a; color: #888; font-size: 11px; }"
        )
        self.setStatusBar(self._statusbar)
        self._statusbar.showMessage("Ready — Open a video to begin")

    # ── Signal connections ────────────────────────────────────────────────

    def _connect_signals(self):
        # Timeline ↔ Preview
        self._timeline.seek_requested.connect(self._on_seek)
        self._timeline.segment_selected.connect(self._on_segment_selected)

        # Style panel → Preview
        self._style_panel.style_changed.connect(self._on_style_changed)
        self._style_panel.animation_changed.connect(self._on_style_changed)

        # Preview → Style panel (drag position)
        self._preview.position_changed.connect(self._style_panel.update_position)

        # Transcript editor → Track
        self._transcript_editor.track_modified.connect(self._on_track_modified)

    # ── Video loading ─────────────────────────────────────────────────────

    def _open_video(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Video", "", get_input_filter(),
        )
        if not path:
            return

        try:
            info = get_video_info(path)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Cannot open video:\n{e}")
            return

        self._video_path = path
        self._video_info = info
        self._preview.load_video(path, info)
        self._timeline.set_duration(info.duration)
        self._transcribe_act.setEnabled(True)
        self._statusbar.showMessage(
            f"Loaded: {os.path.basename(path)} — "
            f"{info.resolution} @ {info.fps:.1f}fps — "
            f"{self._format_duration(info.duration)}"
        )
        self.setWindowTitle(f"Hindi Auto Captioner — {os.path.basename(path)}")

    # ── Transcription ─────────────────────────────────────────────────────

    def _start_transcription(self):
        if not self._video_path:
            QMessageBox.warning(self, "No Video", "Please open a video first.")
            return

        self._transcribe_act.setEnabled(False)
        self._statusbar.showMessage("Transcribing…")

        # Progress dialog
        self._progress_dlg = QProgressDialog(
            "Transcribing video…", "Cancel", 0, 100, self,
        )
        self._progress_dlg.setWindowTitle("Transcription")
        self._progress_dlg.setWindowModality(Qt.WindowModality.WindowModal)
        self._progress_dlg.setStyleSheet("""
            QProgressDialog { background: #1e1e1e; }
            QLabel { color: #e0e0e0; }
            QProgressBar {
                background: #2a2a2a; border: 1px solid #444;
                border-radius: 6px; text-align: center; color: #e0e0e0;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #3A6EA5, stop:1 #5B9BD5);
                border-radius: 5px;
            }
        """)

        self._transcriber = TranscriberWorker(self._video_path)
        self._transcriber.progress.connect(self._progress_dlg.setValue)
        self._transcriber.status_message.connect(
            lambda msg: self._progress_dlg.setLabelText(msg)
        )
        self._transcriber.finished.connect(self._on_transcription_done)
        self._transcriber.error.connect(self._on_transcription_error)
        self._progress_dlg.canceled.connect(self._transcriber.cancel)
        self._transcriber.start()

    def _on_transcription_done(self, words: list):
        self._progress_dlg.close()
        self._word_timings = words
        self._transcribe_act.setEnabled(True)

        if not words:
            self._statusbar.showMessage("Transcription produced no words.")
            return

        # Build subtitle track
        self._track.rebuild_segments(words)
        self._preview.set_subtitle_track(self._track)
        self._timeline.set_subtitle_track(self._track)
        self._transcript_editor.set_subtitle_track(self._track)
        self._style_panel.set_subtitle_track(self._track)

        self._statusbar.showMessage(
            f"Transcription complete — {len(words)} words, "
            f"{len(self._track.segments)} segments"
        )

    def _on_transcription_error(self, msg: str):
        self._progress_dlg.close()
        self._transcribe_act.setEnabled(True)
        QMessageBox.critical(self, "Transcription Error", msg)
        self._statusbar.showMessage("Transcription failed")

    # ── Playback ──────────────────────────────────────────────────────────

    def _toggle_play(self):
        if self._preview.is_playing:
            self._preview.pause()
            self._playback_timer.stop()
            self._play_btn.setText("▶ Play")
        else:
            self._preview.play()
            self._playback_timer.start()
            self._play_btn.setText("⏸ Pause")

    def _on_playback_tick(self):
        t = self._preview.current_time
        self._timeline.set_playhead(t)
        self._update_time_label(t)

        # Highlight active segment in transcript
        if self._track:
            for i, seg in enumerate(self._track.segments):
                if seg.start_time <= t <= seg.end_time:
                    self._transcript_editor.highlight_segment(i)
                    break

        # Stop timer when video ends
        if not self._preview.is_playing:
            self._playback_timer.stop()
            self._play_btn.setText("▶ Play")

    def _on_seek(self, time_sec: float):
        self._preview.seek(time_sec)
        self._timeline.set_playhead(time_sec)
        self._update_time_label(time_sec)

    def _on_segment_selected(self, index: int):
        if self._track and 0 <= index < len(self._track.segments):
            seg = self._track.segments[index]
            self._on_seek(seg.start_time)
            self._transcript_editor.highlight_segment(index)

    def _update_time_label(self, t: float):
        dur = self._video_info.duration if self._video_info else 0
        self._time_label.setText(
            f"{self._format_duration(t)} / {self._format_duration(dur)}"
        )

    # ── Style / Track changes ─────────────────────────────────────────────

    def _on_style_changed(self):
        self._preview.update()
        self._timeline.update()

    def _on_track_modified(self):
        self._preview.update()
        self._timeline.set_subtitle_track(self._track)
        self._timeline.update()

    def _regroup_segments(self):
        """Re-group words into segments based on current words-per-line."""
        if not self._word_timings:
            return
        self._track.rebuild_segments(self._word_timings)
        # Re-apply current global style
        for seg in self._track.segments:
            seg.style = self._track.global_style.copy()
        self._transcript_editor.set_subtitle_track(self._track)
        self._preview.update()
        self._timeline.set_subtitle_track(self._track)
        self._statusbar.showMessage(
            f"Regrouped into {len(self._track.segments)} segments "
            f"({self._track.words_per_line} words/line)"
        )

    # ── Export ────────────────────────────────────────────────────────────

    def _export_srt(self):
        if not self._track.segments:
            QMessageBox.warning(self, "No Subtitles", "Transcribe a video first.")
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Save SRT", "", "SRT Files (*.srt)",
        )
        if path:
            save_srt(self._track, path)
            self._statusbar.showMessage(f"SRT saved: {path}")

    def _export_video(self):
        if not self._video_path or not self._track.segments:
            QMessageBox.warning(
                self, "Cannot Export",
                "Please open a video and transcribe it first.",
            )
            return

        dlg = ExportDialog(self._video_path, self._track, self)
        dlg.exec()

    # ── Helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _format_duration(seconds: float) -> str:
        m = int(seconds // 60)
        s = int(seconds % 60)
        ms = int((seconds * 10) % 10)
        return f"{m:02d}:{s:02d}.{ms}"

    @staticmethod
    def _control_btn_style() -> str:
        return """
            QPushButton {
                background-color: #3A6EA5; color: white; border: none;
                border-radius: 6px; font-size: 13px; font-weight: bold;
            }
            QPushButton:hover { background-color: #5B9BD5; }
        """

    def _apply_dark_theme(self):
        self.setStyleSheet("""
            QMainWindow { background-color: #1a1a1a; }
            QSplitter::handle {
                background-color: #333; width: 3px; height: 3px;
            }
            QSplitter::handle:hover { background-color: #5B9BD5; }
            QToolTip {
                background-color: #2a2a2a; color: #e0e0e0;
                border: 1px solid #555; padding: 4px;
            }
        """)

    def closeEvent(self, event):
        if self._transcriber and self._transcriber.isRunning():
            self._transcriber.cancel()
            self._transcriber.wait(3000)
        self._preview.pause()
        self._playback_timer.stop()
        super().closeEvent(event)
