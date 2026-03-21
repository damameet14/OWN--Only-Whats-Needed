"""Video preview widget with real-time subtitle overlay."""

from __future__ import annotations
import subprocess
import sys
import os
from typing import Optional

from PySide6.QtCore import Qt, QTimer, Signal, QRectF, QPointF, QUrl
from PySide6.QtGui import (
    QImage, QPainter, QFont, QColor, QPen, QBrush, QFontMetrics,
    QPainterPath, QMouseEvent, QResizeEvent, QPaintEvent,
)
from PySide6.QtWidgets import QWidget, QVBoxLayout, QSizePolicy
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput, QVideoSink

from models.subtitle import SubtitleTrack, SubtitleSegment, SubtitleStyle
from models.animations import AnimationType, compute_animation_state
from core.exporter import _paint_subtitle


class VideoPreviewWidget(QWidget):
    """Widget that displays video frames with subtitle overlay.

    Uses FFmpeg to decode frames and QPainter to render subtitles.
    Supports dragging to reposition subtitles.
    """

    position_changed = Signal(float, float)  # normalised (x, y) when user drags
    subtitle_clicked = Signal()                # emitted when subtitle area is clicked

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(320, 180)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)

        self._current_frame: Optional[QImage] = None
        self._video_path: Optional[str] = None
        self._video_width = 0
        self._video_height = 0
        self._fps = 30.0
        self._duration = 0.0
        self._current_time = 0.0

        self._track: Optional[SubtitleTrack] = None
        self._is_playing = False
        self._dragging_subtitle = False
        self._drag_offset = QPointF()

        # Media player and video sink
        self._media_player = QMediaPlayer(self)
        self._audio_output = QAudioOutput(self)
        self._media_player.setAudioOutput(self._audio_output)
        
        self._video_sink = QVideoSink(self)
        self._media_player.setVideoSink(self._video_sink)
        self._video_sink.videoFrameChanged.connect(self._on_video_frame_changed)
        self._media_player.positionChanged.connect(self._on_position_changed)
        self._media_player.mediaStatusChanged.connect(self._on_media_status_changed)

        self.setStyleSheet("background-color: #1a1a1a;")

    @property
    def current_time(self) -> float:
        return self._current_time

    @property
    def duration(self) -> float:
        return self._duration

    @property
    def is_playing(self) -> bool:
        return self._is_playing

    def set_subtitle_track(self, track: SubtitleTrack):
        self._track = track
        self.update()

    def load_video(self, path: str, info):
        """Load a video file for frame-by-frame preview."""
        self._video_path = path
        self._video_width = info.width
        self._video_height = info.height
        self._fps = info.fps
        self._duration = info.duration
        self._current_time = 0.0
        self._is_playing = False
        
        # We still need info.width etc. to calculate the aspect ratio for painting
        self._media_player.setSource(QUrl.fromLocalFile(path))
        self._media_player.pause()
        self._media_player.setPosition(0)
        self.update()

    def _on_video_frame_changed(self, frame):
        if frame.isValid():
            img = frame.toImage()
            img = img.convertToFormat(QImage.Format.Format_RGB888)
            self._current_frame = img
            self.update()

    def _on_position_changed(self, position_ms: int):
        self._current_time = position_ms / 1000.0
        self.update()

    def _on_media_status_changed(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self._is_playing = False
            self._media_player.setPosition(0)
            self.pause()

    def seek(self, time_sec: float):
        """Seek to a specific timestamp."""
        self._current_time = max(0.0, min(time_sec, self._duration))
        self._media_player.setPosition(int(self._current_time * 1000))

    def play(self):
        """Start playback."""
        if self._current_time >= self._duration:
            self._current_time = 0.0
            self._media_player.setPosition(0)
        self._is_playing = True
        self._media_player.play()

    def pause(self):
        """Pause playback."""
        self._is_playing = False
        self._media_player.pause()

    def toggle_play(self):
        if self._is_playing:
            self.pause()
        else:
            self.play()

    # ── Painting ──────────────────────────────────────────────────────────

    def paintEvent(self, event: QPaintEvent):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        widget_w = self.width()
        widget_h = self.height()

        if self._current_frame:
            # Scale frame to fit widget while maintaining aspect ratio
            frame = self._current_frame
            scale_x = widget_w / frame.width()
            scale_y = widget_h / frame.height()
            scale = min(scale_x, scale_y)
            draw_w = int(frame.width() * scale)
            draw_h = int(frame.height() * scale)
            draw_x = (widget_w - draw_w) // 2
            draw_y = (widget_h - draw_h) // 2

            scaled = frame.scaled(
                draw_w, draw_h,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            painter.drawImage(draw_x, draw_y, scaled)

            # Draw subtitles on the scaled area
            if self._track:
                seg = self._track.segment_at(self._current_time)
                if seg:
                    anim_type = AnimationType(self._track.animation_type)
                    anim_state = compute_animation_state(
                        anim_type, seg, self._current_time,
                        anim_duration=self._track.animation_duration,
                        frame_height=float(draw_h),
                    )
                    if anim_state.opacity > 0:
                        painter.save()
                        painter.translate(draw_x, draw_y)
                        # Scale subtitle sizes relative to preview
                        scale_factor = draw_h / max(self._video_height, 1)
                        _paint_subtitle_preview(
                            painter, seg, self._track, anim_state,
                            draw_w, draw_h, scale_factor,
                        )
                        painter.restore()
        else:
            # No frame - draw placeholder
            painter.fillRect(0, 0, widget_w, widget_h, QColor("#1a1a1a"))
            painter.setPen(QColor("#666"))
            painter.setFont(QFont("Segoe UI", 14))
            painter.drawText(
                QRectF(0, 0, widget_w, widget_h),
                Qt.AlignmentFlag.AlignCenter,
                "Open a video to begin",
            )

        painter.end()

    # ── Mouse events for subtitle dragging ────────────────────────────────

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton and self._track:
            self._dragging_subtitle = True
            self.subtitle_clicked.emit()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._dragging_subtitle and self._track:
            pos = event.position()
            widget_w = self.width()
            widget_h = self.height()

            # Calculate video area bounds
            if self._current_frame:
                scale_x = widget_w / self._current_frame.width()
                scale_y = widget_h / self._current_frame.height()
                scale = min(scale_x, scale_y)
                draw_w = int(self._current_frame.width() * scale)
                draw_h = int(self._current_frame.height() * scale)
                draw_x = (widget_w - draw_w) // 2
                draw_y = (widget_h - draw_h) // 2

                # Normalise position within video area
                nx = (pos.x() - draw_x) / draw_w
                ny = (pos.y() - draw_y) / draw_h
                nx = max(0.05, min(0.95, nx))
                ny = max(0.05, min(0.95, ny))

                self._track.position_x = nx
                self._track.position_y = ny
                self.position_changed.emit(nx, ny)
                self.update()

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._dragging_subtitle = False

    def closeEvent(self, event):
        self._media_player.stop()
        super().closeEvent(event)


def _paint_subtitle_preview(painter, seg, track, anim_state, draw_w, draw_h, scale_factor):
    """Paint subtitles scaled for the preview widget."""
    style = seg.style
    pos_x = track.position_x
    pos_y = track.position_y

    # Scaled font
    scaled_size = max(int(style.font_size * scale_factor), 8)
    font = QFont(style.font_family, scaled_size)
    font.setBold(style.bold)
    font.setItalic(style.italic)

    if anim_state.scale != 1.0:
        scaled_size = max(int(scaled_size * anim_state.scale), 6)
        font.setPointSize(scaled_size)

    painter.setFont(font)
    fm = QFontMetrics(font)

    anim_type = AnimationType(track.animation_type)

    if anim_type == AnimationType.TYPEWRITER and anim_state.visible_char_count >= 0:
        display_text = seg.text[:anim_state.visible_char_count]
    else:
        display_text = seg.text

    if not display_text.strip():
        return

    text_w = fm.horizontalAdvance(display_text)
    text_h = fm.height()

    x = pos_x * draw_w - text_w / 2
    y = pos_y * draw_h

    x += anim_state.offset_x * scale_factor
    y += anim_state.offset_y * scale_factor

    x = max(0, min(x, draw_w - text_w))
    y = max(text_h, min(y, draw_h))

    painter.setOpacity(anim_state.opacity)

    # Background
    if style.bg_color:
        bg = QColor(style.bg_color)
        pad = int(style.bg_padding * scale_factor)
        bg_rect = QRectF(x - pad, y - text_h - pad, text_w + 2 * pad, text_h + 2 * pad)
        painter.fillRect(bg_rect, bg)

    outline_w = max(int(style.outline_width * scale_factor), 1) if style.outline_width else 0

    # Karaoke mode
    if anim_type == AnimationType.KARAOKE:
        _draw_karaoke_preview(painter, seg, style, anim_state, font, fm, x, y, scale_factor)
        return

    # Shadow
    if style.shadow_color and (style.shadow_offset_x or style.shadow_offset_y):
        sx = style.shadow_offset_x * scale_factor
        sy = style.shadow_offset_y * scale_factor
        shadow_color = QColor(style.shadow_color)
        _draw_outlined_text_preview(
            painter, display_text, font, x + sx, y + sy,
            shadow_color, QColor(0, 0, 0, 0), 0,
        )

    text_color = QColor(style.text_color)
    outline_color = QColor(style.outline_color) if style.outline_color else QColor(0, 0, 0, 0)
    _draw_outlined_text_preview(
        painter, display_text, font, x, y,
        text_color, outline_color, outline_w,
    )

    painter.setOpacity(1.0)


def _draw_outlined_text_preview(painter, text, font, x, y, fill_color, stroke_color, stroke_width):
    path = QPainterPath()
    path.addText(x, y, font, text)
    if stroke_width > 0 and stroke_color.alpha() > 0:
        pen = QPen(stroke_color, stroke_width * 2, Qt.PenStyle.SolidLine,
                   Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(fill_color))
    painter.drawPath(path)


def _draw_karaoke_preview(painter, seg, style, anim_state, font, fm, base_x, base_y, scale_factor):
    cursor_x = base_x
    highlight_idx = anim_state.highlight_word_index
    outline_w = max(int(style.outline_width * scale_factor), 1) if style.outline_width else 0

    for i, word in enumerate(seg.words):
        word_text = word.word + " "
        word_style = word.style_override or style

        if i == highlight_idx:
            fill = QColor("#FFD700")
            outline = QColor(word_style.outline_color) if word_style.outline_color else QColor(0, 0, 0, 0)
            scale_font = QFont(font)
            scale_font.setPointSize(int(font.pointSize() * 1.15))
            _draw_outlined_text_preview(
                painter, word_text, scale_font, cursor_x, base_y,
                fill, outline, outline_w,
            )
            cursor_x += QFontMetrics(scale_font).horizontalAdvance(word_text)
        else:
            fill = QColor(word_style.text_color)
            outline = QColor(word_style.outline_color) if word_style.outline_color else QColor(0, 0, 0, 0)
            _draw_outlined_text_preview(
                painter, word_text, font, cursor_x, base_y,
                fill, outline, outline_w,
            )
            cursor_x += fm.horizontalAdvance(word_text)
