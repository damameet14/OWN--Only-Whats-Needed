"""Export dialog — settings, format selection, and progress."""

from __future__ import annotations
import os
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QFileDialog, QProgressBar, QLineEdit, QFrame,
)

from core.video_utils import OUTPUT_FORMATS
from core.exporter import ExportWorker
from models.subtitle import SubtitleTrack


class ExportDialog(QDialog):
    """Dialog for exporting video with burned-in subtitles."""

    def __init__(
        self,
        video_path: str,
        subtitle_track: SubtitleTrack,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Export Video")
        self.setFixedSize(500, 340)
        self.setStyleSheet("""
            QDialog { background-color: #1e1e1e; }
            QLabel { color: #e0e0e0; }
        """)

        self._video_path = video_path
        self._track = subtitle_track
        self._worker: Optional[ExportWorker] = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        # Title
        title = QLabel("🎬 Export Video with Subtitles")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #e0e0e0;")
        layout.addWidget(title)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #333;")
        layout.addWidget(sep)

        # Format selector
        fmt_layout = QHBoxLayout()
        fmt_layout.addWidget(QLabel("Format:"))
        self._format_combo = QComboBox()
        self._format_combo.addItems(list(OUTPUT_FORMATS.keys()))
        self._format_combo.setStyleSheet("""
            QComboBox {
                background: #2a2a2a; color: #e0e0e0; border: 1px solid #444;
                border-radius: 4px; padding: 6px 10px; min-width: 200px;
            }
            QComboBox:hover { border-color: #5B9BD5; }
            QComboBox QAbstractItemView {
                background: #2a2a2a; color: #e0e0e0;
                selection-background-color: #3A6EA5;
            }
        """)
        fmt_layout.addWidget(self._format_combo)
        fmt_layout.addStretch()
        layout.addLayout(fmt_layout)

        # Output path
        path_layout = QHBoxLayout()
        path_layout.addWidget(QLabel("Save to:"))
        self._path_edit = QLineEdit()
        self._path_edit.setStyleSheet("""
            QLineEdit {
                background: #2a2a2a; color: #e0e0e0; border: 1px solid #444;
                border-radius: 4px; padding: 6px;
            }
        """)
        base = os.path.splitext(os.path.basename(self._video_path))[0]
        default_out = os.path.join(
            os.path.dirname(self._video_path),
            f"{base}_subtitled.mp4",
        )
        self._path_edit.setText(default_out)
        browse_btn = QPushButton("Browse")
        browse_btn.setStyleSheet("""
            QPushButton {
                background: #3A6EA5; color: white; border: none;
                border-radius: 4px; padding: 6px 12px;
            }
            QPushButton:hover { background: #5B9BD5; }
        """)
        browse_btn.clicked.connect(self._browse_output)
        path_layout.addWidget(self._path_edit, 1)
        path_layout.addWidget(browse_btn)
        layout.addLayout(path_layout)

        # Status
        self._status_label = QLabel("Ready to export")
        self._status_label.setStyleSheet("color: #888; font-size: 12px;")
        layout.addWidget(self._status_label)

        # Progress bar
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setStyleSheet("""
            QProgressBar {
                background: #2a2a2a; border: 1px solid #444;
                border-radius: 6px; text-align: center; color: #e0e0e0;
                height: 22px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #3A6EA5, stop:1 #5B9BD5);
                border-radius: 5px;
            }
        """)
        layout.addWidget(self._progress)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self._export_btn = QPushButton("🚀 Export")
        self._export_btn.setStyleSheet("""
            QPushButton {
                background-color: #27AE60; color: white; border: none;
                border-radius: 6px; padding: 10px 28px;
                font-size: 14px; font-weight: bold;
            }
            QPushButton:hover { background-color: #2ECC71; }
            QPushButton:disabled { background-color: #555; }
        """)
        self._export_btn.clicked.connect(self._start_export)

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #555; color: white; border: none;
                border-radius: 6px; padding: 10px 20px; font-size: 13px;
            }
            QPushButton:hover { background-color: #777; }
        """)
        self._cancel_btn.clicked.connect(self._cancel_or_close)

        btn_layout.addWidget(self._cancel_btn)
        btn_layout.addWidget(self._export_btn)
        layout.addLayout(btn_layout)

    def _browse_output(self):
        fmt_key = self._format_combo.currentText()
        ext = OUTPUT_FORMATS[fmt_key]["ext"]
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Video", self._path_edit.text(),
            f"Video (*{ext})",
        )
        if path:
            self._path_edit.setText(path)

    def _start_export(self):
        output_path = self._path_edit.text().strip()
        if not output_path:
            self._status_label.setText("❌ Please specify an output path.")
            return

        # Update extension to match format
        fmt_key = self._format_combo.currentText()
        ext = OUTPUT_FORMATS[fmt_key]["ext"]
        base, _ = os.path.splitext(output_path)
        output_path = base + ext
        self._path_edit.setText(output_path)

        self._export_btn.setEnabled(False)
        self._progress.setValue(0)

        self._worker = ExportWorker(
            self._video_path,
            output_path,
            self._track,
            fmt_key,
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.status_message.connect(self._on_status)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_progress(self, pct: int):
        self._progress.setValue(pct)

    def _on_status(self, msg: str):
        self._status_label.setText(msg)

    def _on_finished(self, path: str):
        self._progress.setValue(100)
        self._status_label.setText(f"✅ Exported: {os.path.basename(path)}")
        self._export_btn.setText("✅ Done")
        self._export_btn.setEnabled(False)
        self._cancel_btn.setText("Close")

    def _on_error(self, msg: str):
        self._status_label.setText(f"❌ Error: {msg}")
        self._export_btn.setEnabled(True)

    def _cancel_or_close(self):
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(3000)
        self.close()
