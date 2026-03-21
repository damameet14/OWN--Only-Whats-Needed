"""Timeline widget with playhead, subtitle segments, and zoom."""

from __future__ import annotations
from typing import Optional

from PySide6.QtCore import Qt, Signal, QRectF, QPointF
from PySide6.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont, QFontMetrics,
    QMouseEvent, QPaintEvent, QWheelEvent, QLinearGradient,
)
from PySide6.QtWidgets import QWidget, QSizePolicy

from models.subtitle import SubtitleTrack


class TimelineWidget(QWidget):
    """Custom-painted timeline with playhead, subtitle blocks, and zoom.

    Emits seek_requested(float) when user clicks/drags on timeline.
    """

    seek_requested = Signal(float)       # seconds
    segment_selected = Signal(int)       # segment index

    # Layout constants
    RULER_HEIGHT = 28
    TRACK_HEIGHT = 36
    HANDLE_WIDTH = 2
    MIN_ZOOM = 1.0
    MAX_ZOOM = 50.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(self.RULER_HEIGHT + self.TRACK_HEIGHT + 16)
        self.setFixedHeight(80)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMouseTracking(True)

        self._duration = 0.0
        self._playhead = 0.0
        self._zoom = 1.0
        self._scroll_offset = 0.0  # pixels scrolled

        self._track: Optional[SubtitleTrack] = None
        self._dragging_playhead = False
        self._selected_segment = -1

        self.setStyleSheet("background-color: #1e1e1e;")

    # ── Public API ────────────────────────────────────────────────────────

    def set_duration(self, duration: float):
        self._duration = max(duration, 0.01)
        self.update()

    def set_playhead(self, time_sec: float):
        self._playhead = max(0.0, min(time_sec, self._duration))
        self._ensure_playhead_visible()
        self.update()

    def set_subtitle_track(self, track: SubtitleTrack):
        self._track = track
        self.update()

    def select_segment(self, index: int):
        self._selected_segment = index
        self.update()

    # ── Coordinate helpers ────────────────────────────────────────────────

    def _pixels_per_second(self) -> float:
        return (self.width() / max(self._duration, 0.01)) * self._zoom

    def _time_to_x(self, time_sec: float) -> float:
        return time_sec * self._pixels_per_second() - self._scroll_offset

    def _x_to_time(self, x: float) -> float:
        t = (x + self._scroll_offset) / self._pixels_per_second()
        return max(0.0, min(t, self._duration))

    def _ensure_playhead_visible(self):
        px = self._time_to_x(self._playhead)
        w = self.width()
        if px < 0:
            self._scroll_offset = self._playhead * self._pixels_per_second()
        elif px > w:
            self._scroll_offset = self._playhead * self._pixels_per_second() - w + 20

    # ── Painting ──────────────────────────────────────────────────────────

    def paintEvent(self, event: QPaintEvent):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        h = self.height()

        # Background
        painter.fillRect(0, 0, w, h, QColor("#1e1e1e"))

        pps = self._pixels_per_second()

        # ── Ruler ────────────────────────────────────────────────────────
        painter.setPen(QColor("#555"))
        painter.setFont(QFont("Segoe UI", 8))
        fm = QFontMetrics(painter.font())

        # Determine tick interval based on zoom
        if pps > 200:
            tick_interval = 0.5
        elif pps > 50:
            tick_interval = 1.0
        elif pps > 20:
            tick_interval = 5.0
        elif pps > 5:
            tick_interval = 10.0
        else:
            tick_interval = 30.0

        t = 0.0
        while t <= self._duration:
            x = self._time_to_x(t)
            if 0 <= x <= w:
                painter.drawLine(int(x), 0, int(x), self.RULER_HEIGHT - 4)
                label = self._format_time(t)
                painter.drawText(int(x) + 3, self.RULER_HEIGHT - 6, label)
            t += tick_interval

        # ── Subtitle segments ────────────────────────────────────────────
        track_y = self.RULER_HEIGHT + 4
        if self._track:
            for i, seg in enumerate(self._track.segments):
                x1 = self._time_to_x(seg.start_time)
                x2 = self._time_to_x(seg.end_time)
                if x2 < 0 or x1 > w:
                    continue
                seg_rect = QRectF(x1, track_y, x2 - x1, self.TRACK_HEIGHT)

                # Color
                if i == self._selected_segment:
                    color = QColor("#5B9BD5")
                else:
                    color = QColor("#3A6EA5")

                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(color))
                painter.drawRoundedRect(seg_rect, 3, 3)

                # Segment text (clipped)
                painter.setPen(QColor("#FFF"))
                painter.setFont(QFont("Segoe UI", 7))
                text = seg.text[:30]
                painter.drawText(
                    seg_rect.adjusted(4, 2, -4, -2),
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                    text,
                )

        # ── Playhead ────────────────────────────────────────────────────
        px = self._time_to_x(self._playhead)
        if 0 <= px <= w:
            pen = QPen(QColor("#FF4444"), 2)
            painter.setPen(pen)
            painter.drawLine(int(px), 0, int(px), h)

            # Playhead handle (triangle)
            painter.setBrush(QBrush(QColor("#FF4444")))
            painter.setPen(Qt.PenStyle.NoPen)
            triangle = [
                QPointF(px - 6, 0),
                QPointF(px + 6, 0),
                QPointF(px, 10),
            ]
            painter.drawPolygon(triangle)

        painter.end()

    @staticmethod
    def _format_time(seconds: float) -> str:
        m = int(seconds // 60)
        s = int(seconds % 60)
        ms = int((seconds - int(seconds)) * 10)
        return f"{m}:{s:02d}.{ms}"

    # ── Mouse events ──────────────────────────────────────────────────

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            y = event.position().y()
            if y < self.RULER_HEIGHT + 4:
                # Click on ruler → seek
                self._dragging_playhead = True
                t = self._x_to_time(event.position().x())
                self.seek_requested.emit(t)
            else:
                # Click on track → select segment
                t = self._x_to_time(event.position().x())
                self._select_segment_at(t)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._dragging_playhead:
            t = self._x_to_time(event.position().x())
            self.seek_requested.emit(t)

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._dragging_playhead = False

    def wheelEvent(self, event: QWheelEvent):
        delta = event.angleDelta().y()
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            # Ctrl+scroll → zoom
            factor = 1.15 if delta > 0 else 1 / 1.15
            self._zoom = max(self.MIN_ZOOM, min(self._zoom * factor, self.MAX_ZOOM))
        else:
            # Scroll → pan
            self._scroll_offset -= delta * 0.5
            max_scroll = max(0, self._duration * self._pixels_per_second() - self.width())
            self._scroll_offset = max(0, min(self._scroll_offset, max_scroll))
        self.update()

    def _select_segment_at(self, time_sec: float):
        if not self._track:
            return
        for i, seg in enumerate(self._track.segments):
            if seg.start_time <= time_sec <= seg.end_time:
                self._selected_segment = i
                self.segment_selected.emit(i)
                self.update()
                return
