"""Style panel — presets, custom editor, animations, and layout settings."""

from __future__ import annotations
import os
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QColor, QIcon
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QLabel,
    QPushButton, QComboBox, QSpinBox, QDoubleSpinBox, QCheckBox,
    QColorDialog, QGridLayout, QFrame, QScrollArea, QSlider,
    QSizePolicy, QInputDialog, QMessageBox,
)

from models.subtitle import SubtitleStyle, SubtitleTrack
from models.styles import (
    StylePreset, BUILTIN_PRESETS, get_all_presets,
    save_custom_presets, load_custom_presets,
)
from models.animations import AnimationType, ANIMATION_LABELS

# Bundled fonts
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONTS_DIR = os.path.join(_PROJECT_ROOT, "fonts")

BUNDLED_FONTS = [
    "Noto Sans Devanagari",
    "Mukta",
    "Baloo 2",
]


def _color_button_style(color_hex: str) -> str:
    return f"""
        QPushButton {{
            background-color: {color_hex};
            border: 2px solid #555; border-radius: 4px;
            min-width: 40px; min-height: 24px;
        }}
        QPushButton:hover {{ border-color: #FFD700; }}
    """


class ColorPickerButton(QPushButton):
    """Button that shows a color and opens a color picker on click."""
    color_changed = Signal(str)

    def __init__(self, initial_color: str = "#FFFFFF", label: str = "", parent=None):
        super().__init__(parent)
        self._color = initial_color
        self._label = label
        self.setFixedSize(44, 28)
        self._update_style()
        self.clicked.connect(self._pick_color)

    def _update_style(self):
        self.setStyleSheet(_color_button_style(self._color if self._color else "#00000000"))

    def _pick_color(self):
        color = QColorDialog.getColor(
            QColor(self._color) if self._color else QColor("#FFFFFF"),
            self, f"Choose {self._label} Color",
            QColorDialog.ColorDialogOption.ShowAlphaChannel,
        )
        if color.isValid():
            self._color = color.name(QColor.NameFormat.HexArgb)
            self._update_style()
            self.color_changed.emit(self._color)

    def set_color(self, hex_color: str):
        self._color = hex_color
        self._update_style()

    def get_color(self) -> str:
        return self._color


class PresetCard(QFrame):
    """A card representing a style preset."""
    preset_selected = Signal(object)  # StylePreset

    def __init__(self, preset: StylePreset, parent=None):
        super().__init__(parent)
        self._preset = preset
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(60)
        self.setStyleSheet("""
            QFrame {
                background-color: #2a2a2a; border: 1px solid #444;
                border-radius: 8px; margin: 2px;
            }
            QFrame:hover { border-color: #5B9BD5; background-color: #333; }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)

        name = QLabel(preset.name)
        name.setStyleSheet("color: #e0e0e0; font-weight: bold; font-size: 13px; border: none;")
        desc = QLabel(preset.description)
        desc.setStyleSheet("color: #888; font-size: 10px; border: none;")

        layout.addWidget(name)
        layout.addWidget(desc)

    def mousePressEvent(self, event):
        self.preset_selected.emit(self._preset)


class StylePanel(QWidget):
    """Tabbed panel for style presets, custom editing, animation, and layout."""

    style_changed = Signal()         # emitted when any style changes
    animation_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._track: Optional[SubtitleTrack] = None
        self._custom_presets_path = os.path.join(_PROJECT_ROOT, "resources", "custom_presets.json")
        self._setup_ui()

    def set_subtitle_track(self, track: SubtitleTrack):
        self._track = track
        self._sync_ui_from_track()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        header = QLabel("🎨 Style")
        header.setStyleSheet("""
            font-size: 14px; font-weight: bold; color: #e0e0e0;
            padding: 6px 10px; background-color: #1e1e1e;
            border-bottom: 1px solid #333;
        """)
        main_layout.addWidget(header)

        self._tabs = QTabWidget()
        self._tabs.setStyleSheet("""
            QTabWidget::pane { border: none; background: #1e1e1e; }
            QTabBar::tab {
                background: #2a2a2a; color: #aaa; padding: 6px 14px;
                border: 1px solid #333; border-bottom: none;
                border-top-left-radius: 6px; border-top-right-radius: 6px;
                margin-right: 2px;
            }
            QTabBar::tab:selected { background: #1e1e1e; color: #e0e0e0; }
            QTabBar::tab:hover { color: #5B9BD5; }
        """)

        self._tabs.addTab(self._create_presets_tab(), "Presets")
        self._tabs.addTab(self._create_custom_tab(), "Custom")
        self._tabs.addTab(self._create_animation_tab(), "Animation")
        self._tabs.addTab(self._create_layout_tab(), "Layout")

        main_layout.addWidget(self._tabs)

    # ── Presets Tab ───────────────────────────────────────────────────────

    def _create_presets_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: #1e1e1e; }")
        content = QWidget()
        self._presets_layout = QVBoxLayout(content)
        self._presets_layout.setSpacing(4)

        for preset in get_all_presets(self._custom_presets_path):
            card = PresetCard(preset)
            card.preset_selected.connect(self._apply_preset)
            self._presets_layout.addWidget(card)

        self._presets_layout.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll)

        return tab

    def _apply_preset(self, preset: StylePreset):
        if self._track:
            self._track.global_style = preset.style.copy()
            for seg in self._track.segments:
                seg.style = preset.style.copy()
            self._sync_ui_from_track()
            self.style_changed.emit()

    # ── Custom Tab ────────────────────────────────────────────────────────

    def _create_custom_tab(self) -> QWidget:
        tab = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: #1e1e1e; }")
        content = QWidget()
        layout = QGridLayout(content)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setVerticalSpacing(10)
        layout.setHorizontalSpacing(8)

        row = 0

        # Font family
        layout.addWidget(self._make_label("Font"), row, 0)
        self._font_combo = QComboBox()
        self._font_combo.addItems(BUNDLED_FONTS)
        self._font_combo.setStyleSheet(self._combo_style())
        self._font_combo.currentTextChanged.connect(self._on_style_changed)
        layout.addWidget(self._font_combo, row, 1)
        row += 1

        # Font size
        layout.addWidget(self._make_label("Size"), row, 0)
        self._size_spin = QSpinBox()
        self._size_spin.setRange(12, 120)
        self._size_spin.setValue(48)
        self._size_spin.setStyleSheet(self._spin_style())
        self._size_spin.valueChanged.connect(self._on_style_changed)
        layout.addWidget(self._size_spin, row, 1)
        row += 1

        # Text color
        layout.addWidget(self._make_label("Text Color"), row, 0)
        self._text_color = ColorPickerButton("#FFFFFF", "Text")
        self._text_color.color_changed.connect(lambda _: self._on_style_changed())
        layout.addWidget(self._text_color, row, 1)
        row += 1

        # Outline color
        layout.addWidget(self._make_label("Outline"), row, 0)
        outline_row = QHBoxLayout()
        self._outline_color = ColorPickerButton("#000000", "Outline")
        self._outline_color.color_changed.connect(lambda _: self._on_style_changed())
        self._outline_width = QSpinBox()
        self._outline_width.setRange(0, 10)
        self._outline_width.setValue(2)
        self._outline_width.setSuffix("px")
        self._outline_width.setStyleSheet(self._spin_style())
        self._outline_width.setFixedWidth(70)
        self._outline_width.valueChanged.connect(self._on_style_changed)
        outline_row.addWidget(self._outline_color)
        outline_row.addWidget(self._outline_width)
        outline_row.addStretch()
        layout.addLayout(outline_row, row, 1)
        row += 1

        # Shadow
        layout.addWidget(self._make_label("Shadow"), row, 0)
        shadow_row = QHBoxLayout()
        self._shadow_color = ColorPickerButton("#80000000", "Shadow")
        self._shadow_color.color_changed.connect(lambda _: self._on_style_changed())
        self._shadow_x = QSpinBox()
        self._shadow_x.setRange(-20, 20)
        self._shadow_x.setValue(2)
        self._shadow_x.setPrefix("X:")
        self._shadow_x.setStyleSheet(self._spin_style())
        self._shadow_x.setFixedWidth(60)
        self._shadow_x.valueChanged.connect(self._on_style_changed)
        self._shadow_y = QSpinBox()
        self._shadow_y.setRange(-20, 20)
        self._shadow_y.setValue(2)
        self._shadow_y.setPrefix("Y:")
        self._shadow_y.setStyleSheet(self._spin_style())
        self._shadow_y.setFixedWidth(60)
        self._shadow_y.valueChanged.connect(self._on_style_changed)
        shadow_row.addWidget(self._shadow_color)
        shadow_row.addWidget(self._shadow_x)
        shadow_row.addWidget(self._shadow_y)
        shadow_row.addStretch()
        layout.addLayout(shadow_row, row, 1)
        row += 1

        # Background
        layout.addWidget(self._make_label("Background"), row, 0)
        bg_row = QHBoxLayout()
        self._bg_color = ColorPickerButton("", "Background")
        self._bg_color.color_changed.connect(lambda _: self._on_style_changed())
        self._bg_padding = QSpinBox()
        self._bg_padding.setRange(0, 40)
        self._bg_padding.setValue(8)
        self._bg_padding.setSuffix("px")
        self._bg_padding.setStyleSheet(self._spin_style())
        self._bg_padding.setFixedWidth(70)
        self._bg_padding.valueChanged.connect(self._on_style_changed)
        bg_row.addWidget(self._bg_color)
        bg_row.addWidget(self._bg_padding)
        bg_row.addStretch()
        layout.addLayout(bg_row, row, 1)
        row += 1

        # Bold / Italic
        layout.addWidget(self._make_label("Style"), row, 0)
        style_row = QHBoxLayout()
        self._bold_cb = QCheckBox("Bold")
        self._bold_cb.setStyleSheet("color: #ccc;")
        self._bold_cb.stateChanged.connect(self._on_style_changed)
        self._italic_cb = QCheckBox("Italic")
        self._italic_cb.setStyleSheet("color: #ccc;")
        self._italic_cb.stateChanged.connect(self._on_style_changed)
        style_row.addWidget(self._bold_cb)
        style_row.addWidget(self._italic_cb)
        style_row.addStretch()
        layout.addLayout(style_row, row, 1)
        row += 1

        # Alignment
        layout.addWidget(self._make_label("Align"), row, 0)
        self._align_combo = QComboBox()
        self._align_combo.addItems(["left", "center", "right"])
        self._align_combo.setCurrentText("center")
        self._align_combo.setStyleSheet(self._combo_style())
        self._align_combo.currentTextChanged.connect(self._on_style_changed)
        layout.addWidget(self._align_combo, row, 1)
        row += 1

        # Save as preset
        save_btn = QPushButton("💾 Save as Preset")
        save_btn.setStyleSheet("""
            QPushButton {
                background-color: #3A6EA5; color: white;
                border: none; border-radius: 6px;
                padding: 8px 16px; font-size: 12px;
            }
            QPushButton:hover { background-color: #5B9BD5; }
        """)
        save_btn.clicked.connect(self._save_as_preset)
        layout.addWidget(save_btn, row, 0, 1, 2)

        layout.setRowStretch(row + 1, 1)
        scroll.setWidget(content)

        tab_layout = QVBoxLayout(tab)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.addWidget(scroll)
        return tab

    # ── Animation Tab ─────────────────────────────────────────────────────

    def _create_animation_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(12)

        layout.addWidget(self._make_label("Animation Type"))
        self._anim_combo = QComboBox()
        for atype in AnimationType:
            self._anim_combo.addItem(ANIMATION_LABELS[atype], atype.value)
        self._anim_combo.setStyleSheet(self._combo_style())
        self._anim_combo.currentIndexChanged.connect(self._on_animation_changed)
        layout.addWidget(self._anim_combo)

        layout.addWidget(self._make_label("Duration (seconds)"))
        self._anim_duration = QDoubleSpinBox()
        self._anim_duration.setRange(0.1, 2.0)
        self._anim_duration.setValue(0.3)
        self._anim_duration.setSingleStep(0.1)
        self._anim_duration.setStyleSheet(self._spin_style())
        self._anim_duration.valueChanged.connect(self._on_animation_changed)
        layout.addWidget(self._anim_duration)

        layout.addStretch()
        return tab

    # ── Layout Tab ────────────────────────────────────────────────────────

    def _create_layout_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(12)

        layout.addWidget(self._make_label("Words Per Line"))
        self._words_per_line = QSpinBox()
        self._words_per_line.setRange(1, 20)
        self._words_per_line.setValue(5)
        self._words_per_line.setStyleSheet(self._spin_style())
        self._words_per_line.valueChanged.connect(self._on_layout_changed)
        layout.addWidget(self._words_per_line)

        layout.addWidget(self._make_label("Position X (0.0–1.0)"))
        self._pos_x = QDoubleSpinBox()
        self._pos_x.setRange(0.0, 1.0)
        self._pos_x.setValue(0.5)
        self._pos_x.setSingleStep(0.05)
        self._pos_x.setStyleSheet(self._spin_style())
        self._pos_x.valueChanged.connect(self._on_layout_changed)
        layout.addWidget(self._pos_x)

        layout.addWidget(self._make_label("Position Y (0.0–1.0)"))
        self._pos_y = QDoubleSpinBox()
        self._pos_y.setRange(0.0, 1.0)
        self._pos_y.setValue(0.9)
        self._pos_y.setSingleStep(0.05)
        self._pos_y.setStyleSheet(self._spin_style())
        self._pos_y.valueChanged.connect(self._on_layout_changed)
        layout.addWidget(self._pos_y)

        info = QLabel("💡 Tip: You can also drag subtitles\ndirectly on the video preview!")
        info.setStyleSheet("color: #888; font-size: 11px; padding: 8px;")
        layout.addWidget(info)

        layout.addStretch()
        return tab

    # ── Sync helpers ──────────────────────────────────────────────────────

    def _sync_ui_from_track(self):
        if not self._track:
            return
        style = self._track.global_style

        self._font_combo.blockSignals(True)
        idx = self._font_combo.findText(style.font_family)
        if idx >= 0:
            self._font_combo.setCurrentIndex(idx)
        self._font_combo.blockSignals(False)

        self._size_spin.blockSignals(True)
        self._size_spin.setValue(style.font_size)
        self._size_spin.blockSignals(False)

        self._text_color.set_color(style.text_color)
        self._outline_color.set_color(style.outline_color)

        self._outline_width.blockSignals(True)
        self._outline_width.setValue(style.outline_width)
        self._outline_width.blockSignals(False)

        self._shadow_color.set_color(style.shadow_color)
        self._shadow_x.blockSignals(True)
        self._shadow_x.setValue(style.shadow_offset_x)
        self._shadow_x.blockSignals(False)
        self._shadow_y.blockSignals(True)
        self._shadow_y.setValue(style.shadow_offset_y)
        self._shadow_y.blockSignals(False)

        self._bg_color.set_color(style.bg_color)
        self._bg_padding.blockSignals(True)
        self._bg_padding.setValue(style.bg_padding)
        self._bg_padding.blockSignals(False)

        self._bold_cb.blockSignals(True)
        self._bold_cb.setChecked(style.bold)
        self._bold_cb.blockSignals(False)

        self._italic_cb.blockSignals(True)
        self._italic_cb.setChecked(style.italic)
        self._italic_cb.blockSignals(False)

        self._align_combo.blockSignals(True)
        self._align_combo.setCurrentText(style.alignment)
        self._align_combo.blockSignals(False)

        # Animation
        self._anim_combo.blockSignals(True)
        idx = self._anim_combo.findData(self._track.animation_type)
        if idx >= 0:
            self._anim_combo.setCurrentIndex(idx)
        self._anim_combo.blockSignals(False)

        self._anim_duration.blockSignals(True)
        self._anim_duration.setValue(self._track.animation_duration)
        self._anim_duration.blockSignals(False)

        # Layout
        self._words_per_line.blockSignals(True)
        self._words_per_line.setValue(self._track.words_per_line)
        self._words_per_line.blockSignals(False)

        self._pos_x.blockSignals(True)
        self._pos_x.setValue(self._track.position_x)
        self._pos_x.blockSignals(False)

        self._pos_y.blockSignals(True)
        self._pos_y.setValue(self._track.position_y)
        self._pos_y.blockSignals(False)

    def _build_style_from_ui(self) -> SubtitleStyle:
        return SubtitleStyle(
            font_family=self._font_combo.currentText(),
            font_size=self._size_spin.value(),
            text_color=self._text_color.get_color(),
            outline_color=self._outline_color.get_color(),
            outline_width=self._outline_width.value(),
            shadow_color=self._shadow_color.get_color(),
            shadow_offset_x=self._shadow_x.value(),
            shadow_offset_y=self._shadow_y.value(),
            bg_color=self._bg_color.get_color(),
            bg_padding=self._bg_padding.value(),
            bold=self._bold_cb.isChecked(),
            italic=self._italic_cb.isChecked(),
            alignment=self._align_combo.currentText(),
        )

    def _on_style_changed(self, *_args):
        if not self._track:
            return
        style = self._build_style_from_ui()
        self._track.global_style = style
        for seg in self._track.segments:
            seg.style = style.copy()
        self.style_changed.emit()

    def _on_animation_changed(self, *_args):
        if not self._track:
            return
        self._track.animation_type = self._anim_combo.currentData()
        self._track.animation_duration = self._anim_duration.value()
        self.animation_changed.emit()

    def _on_layout_changed(self, *_args):
        if not self._track:
            return
        self._track.words_per_line = self._words_per_line.value()
        self._track.position_x = self._pos_x.value()
        self._track.position_y = self._pos_y.value()
        self.style_changed.emit()

    def update_position(self, x: float, y: float):
        """Called when user drags subtitle in preview."""
        self._pos_x.blockSignals(True)
        self._pos_x.setValue(x)
        self._pos_x.blockSignals(False)
        self._pos_y.blockSignals(True)
        self._pos_y.setValue(y)
        self._pos_y.blockSignals(False)

    def _save_as_preset(self):
        style = self._build_style_from_ui()
        name, ok = QInputDialog.getText(self, "Save Preset", "Preset name:")
        if ok and name.strip():
            preset = StylePreset(
                name=name.strip(),
                description="Custom preset",
                style=style,
            )
            custom = load_custom_presets(self._custom_presets_path)
            custom.append(preset)
            save_custom_presets(custom, self._custom_presets_path)
            QMessageBox.information(self, "Saved", f"Preset '{name}' saved!")

    # ── Common styles ─────────────────────────────────────────────────────

    @staticmethod
    def _make_label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("color: #bbb; font-size: 12px;")
        return lbl

    @staticmethod
    def _combo_style() -> str:
        return """
            QComboBox {
                background: #2a2a2a; color: #e0e0e0; border: 1px solid #444;
                border-radius: 4px; padding: 4px 8px; font-size: 12px;
            }
            QComboBox:hover { border-color: #5B9BD5; }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView {
                background: #2a2a2a; color: #e0e0e0;
                selection-background-color: #3A6EA5;
            }
        """

    @staticmethod
    def _spin_style() -> str:
        return """
            QSpinBox, QDoubleSpinBox {
                background: #2a2a2a; color: #e0e0e0; border: 1px solid #444;
                border-radius: 4px; padding: 3px 6px;
            }
            QSpinBox:hover, QDoubleSpinBox:hover { border-color: #5B9BD5; }
        """
