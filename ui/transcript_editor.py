"""Transcript editor — word-level editing of subtitles."""

from __future__ import annotations
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QLabel,
    QPushButton, QLineEdit, QFrame, QSizePolicy, QDoubleSpinBox,
    QMenu, QColorDialog, QFontComboBox, QSpinBox,
)

from models.subtitle import SubtitleTrack, SubtitleSegment, StyledWord, SubtitleStyle


class WordChip(QPushButton):
    """A clickable 'chip' representing a single word."""

    word_clicked = Signal(int, int)       # (segment_index, word_index)
    word_edited = Signal(int, int, str)   # (segment_index, word_index, new_text)

    def __init__(self, word: StyledWord, seg_idx: int, word_idx: int, parent=None):
        super().__init__(word.word, parent)
        self.seg_idx = seg_idx
        self.word_idx = word_idx
        self._word = word
        self._editing = False

        self.setFixedHeight(32)
        self.setMinimumWidth(30)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._apply_style()
        self.clicked.connect(lambda: self.word_clicked.emit(self.seg_idx, self.word_idx))

    def _apply_style(self):
        override = self._word.style_override
        if override:
            bg = override.text_color if override.text_color else "#5B9BD5"
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: {bg}; color: #000;
                    border: 2px solid #FFD700; border-radius: 6px;
                    padding: 2px 8px; font-size: 13px;
                    font-family: 'Noto Sans Devanagari', 'Segoe UI';
                }}
                QPushButton:hover {{ background-color: #FFD700; }}
            """)
        else:
            self.setStyleSheet("""
                QPushButton {
                    background-color: #2d2d2d; color: #e0e0e0;
                    border: 1px solid #444; border-radius: 6px;
                    padding: 2px 8px; font-size: 13px;
                    font-family: 'Noto Sans Devanagari', 'Segoe UI';
                }
                QPushButton:hover { background-color: #3d3d3d; border-color: #5B9BD5; }
            """)

    def mouseDoubleClickEvent(self, event):
        """Enable inline editing on double-click."""
        self._start_edit()

    def _start_edit(self):
        self._editing = True
        self._edit_field = QLineEdit(self.text(), self.parent())
        self._edit_field.setFont(QFont("Noto Sans Devanagari", 12))
        self._edit_field.setStyleSheet("""
            QLineEdit {
                background-color: #1a1a2e; color: #FFD700;
                border: 2px solid #5B9BD5; border-radius: 4px;
                padding: 2px 6px;
            }
        """)
        self._edit_field.setGeometry(self.geometry())
        self._edit_field.selectAll()
        self._edit_field.setFocus()
        self._edit_field.show()
        self._edit_field.editingFinished.connect(self._finish_edit)

    def _finish_edit(self):
        if not self._editing:
            return
        self._editing = False
        new_text = self._edit_field.text().strip()
        if new_text and new_text != self._word.word:
            self.word_edited.emit(self.seg_idx, self.word_idx, new_text)
            self.setText(new_text)
        self._edit_field.deleteLater()


class SegmentRow(QFrame):
    """A single row representing a subtitle segment with its word chips."""

    segment_selected = Signal(int)
    word_clicked = Signal(int, int)
    word_edited = Signal(int, int, str)
    timing_changed = Signal(int, float, float)  # seg_idx, start, end

    def __init__(self, segment: SubtitleSegment, seg_idx: int, parent=None):
        super().__init__(parent)
        self.seg_idx = seg_idx
        self._segment = segment
        self._setup_ui()

    def _setup_ui(self):
        self.setStyleSheet("""
            QFrame {
                background-color: #252525;
                border: 1px solid #333;
                border-radius: 6px;
                margin: 2px 0;
            }
            QFrame:hover { border-color: #5B9BD5; }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        # ── Timing row ────────────────────────────────────────────────
        timing_layout = QHBoxLayout()

        self._start_spin = QDoubleSpinBox()
        self._start_spin.setRange(0, 9999)
        self._start_spin.setDecimals(2)
        self._start_spin.setSuffix("s")
        self._start_spin.setValue(self._segment.start_time)
        self._start_spin.setFixedWidth(100)
        self._start_spin.setStyleSheet("""
            QDoubleSpinBox {
                background: #1a1a1a; color: #aaa; border: 1px solid #333;
                border-radius: 3px; padding: 2px;
            }
        """)

        arrow_label = QLabel("→")
        arrow_label.setStyleSheet("color: #666; font-size: 14px; border: none;")
        arrow_label.setFixedWidth(20)
        arrow_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._end_spin = QDoubleSpinBox()
        self._end_spin.setRange(0, 9999)
        self._end_spin.setDecimals(2)
        self._end_spin.setSuffix("s")
        self._end_spin.setValue(self._segment.end_time)
        self._end_spin.setFixedWidth(100)
        self._end_spin.setStyleSheet(self._start_spin.styleSheet())

        self._start_spin.valueChanged.connect(self._on_timing_changed)
        self._end_spin.valueChanged.connect(self._on_timing_changed)

        seg_label = QLabel(f"#{self.seg_idx + 1}")
        seg_label.setStyleSheet("color: #5B9BD5; font-weight: bold; font-size: 11px; border: none;")
        seg_label.setFixedWidth(30)

        timing_layout.addWidget(seg_label)
        timing_layout.addWidget(self._start_spin)
        timing_layout.addWidget(arrow_label)
        timing_layout.addWidget(self._end_spin)
        timing_layout.addStretch()

        layout.addLayout(timing_layout)

        # ── Word chips row ────────────────────────────────────────────
        words_layout = QHBoxLayout()
        words_layout.setSpacing(4)

        for i, word in enumerate(self._segment.words):
            chip = WordChip(word, self.seg_idx, i)
            chip.word_clicked.connect(self.word_clicked.emit)
            chip.word_edited.connect(self.word_edited.emit)
            words_layout.addWidget(chip)

        words_layout.addStretch()
        layout.addLayout(words_layout)

    def _on_timing_changed(self):
        self.timing_changed.emit(
            self.seg_idx,
            self._start_spin.value(),
            self._end_spin.value(),
        )

    def set_selected(self, selected: bool):
        if selected:
            self.setStyleSheet("""
                QFrame {
                    background-color: #1a2a3a;
                    border: 2px solid #5B9BD5;
                    border-radius: 6px;
                    margin: 2px 0;
                }
            """)
        else:
            self.setStyleSheet("""
                QFrame {
                    background-color: #252525;
                    border: 1px solid #333;
                    border-radius: 6px;
                    margin: 2px 0;
                }
                QFrame:hover { border-color: #5B9BD5; }
            """)


class TranscriptEditor(QWidget):
    """Scrollable list of subtitle segments with word-level editing."""

    segment_selected = Signal(int)
    word_clicked = Signal(int, int)
    word_edited = Signal(int, int, str)
    timing_changed = Signal(int, float, float)
    track_modified = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._track: Optional[SubtitleTrack] = None
        self._segment_rows: list[SegmentRow] = []
        self._selected_segment = -1
        self._setup_ui()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # Header
        header = QLabel("📝 Transcript")
        header.setStyleSheet("""
            font-size: 14px; font-weight: bold; color: #e0e0e0;
            padding: 6px 10px; background-color: #1e1e1e;
            border-bottom: 1px solid #333;
        """)
        main_layout.addWidget(header)

        # Scrollable area
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet("""
            QScrollArea { background-color: #1e1e1e; border: none; }
            QScrollBar:vertical {
                background: #1e1e1e; width: 8px;
            }
            QScrollBar::handle:vertical {
                background: #444; border-radius: 4px; min-height: 20px;
            }
        """)
        self._scroll_content = QWidget()
        self._scroll_layout = QVBoxLayout(self._scroll_content)
        self._scroll_layout.setSpacing(4)
        self._scroll_layout.setContentsMargins(6, 6, 6, 6)
        self._scroll_layout.addStretch()
        self._scroll.setWidget(self._scroll_content)
        main_layout.addWidget(self._scroll)

    def set_subtitle_track(self, track: SubtitleTrack):
        self._track = track
        self._rebuild()

    def _rebuild(self):
        """Rebuild all segment rows from the track."""
        # Clear existing
        for row in self._segment_rows:
            row.deleteLater()
        self._segment_rows.clear()

        if not self._track:
            return

        # Remove stretch
        while self._scroll_layout.count():
            item = self._scroll_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for i, seg in enumerate(self._track.segments):
            row = SegmentRow(seg, i)
            row.segment_selected.connect(self.segment_selected.emit)
            row.word_clicked.connect(self._on_word_clicked)
            row.word_edited.connect(self._on_word_edited)
            row.timing_changed.connect(self._on_timing_changed)
            self._scroll_layout.addWidget(row)
            self._segment_rows.append(row)

        self._scroll_layout.addStretch()

    def highlight_segment(self, index: int):
        """Highlight the segment at the given index (during playback)."""
        for i, row in enumerate(self._segment_rows):
            row.set_selected(i == index)
        if 0 <= index < len(self._segment_rows):
            self._scroll.ensureWidgetVisible(self._segment_rows[index])
        self._selected_segment = index

    def _on_word_clicked(self, seg_idx: int, word_idx: int):
        self.word_clicked.emit(seg_idx, word_idx)
        self.highlight_segment(seg_idx)

    def _on_word_edited(self, seg_idx: int, word_idx: int, new_text: str):
        if self._track and seg_idx < len(self._track.segments):
            seg = self._track.segments[seg_idx]
            if word_idx < len(seg.words):
                seg.words[word_idx].word = new_text
                self.word_edited.emit(seg_idx, word_idx, new_text)
                self.track_modified.emit()

    def _on_timing_changed(self, seg_idx: int, start: float, end: float):
        if self._track and seg_idx < len(self._track.segments):
            seg = self._track.segments[seg_idx]
            if seg.words:
                seg.words[0].start_time = start
                seg.words[-1].end_time = end
            self.timing_changed.emit(seg_idx, start, end)
            self.track_modified.emit()
