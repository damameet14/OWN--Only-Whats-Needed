"""Style presets — built-in and custom subtitle styles."""

from __future__ import annotations
import json
import os
from dataclasses import dataclass, asdict
from typing import Optional
from models.subtitle import SubtitleStyle


@dataclass
class StylePreset:
    """A named subtitle style preset."""
    name: str
    description: str
    style: SubtitleStyle

    def to_dict(self) -> dict:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> StylePreset:
        style_data = d.pop("style", {})
        style = SubtitleStyle(**style_data)
        return cls(style=style, **d)


# ── Built-in presets ──────────────────────────────────────────────────────────

BUILTIN_PRESETS: list[StylePreset] = [
    StylePreset(
        name="Classic White",
        description="Clean white text with black outline",
        style=SubtitleStyle(
            font_family="Noto Sans Devanagari",
            font_size=48,
            text_color="#FFFFFF",
            outline_color="#000000",
            outline_width=2,
            bold=False,
        ),
    ),
    StylePreset(
        name="Bold Yellow",
        description="Bold yellow text for high visibility",
        style=SubtitleStyle(
            font_family="Mukta",
            font_size=52,
            text_color="#FFD700",
            outline_color="#000000",
            outline_width=3,
            bold=True,
        ),
    ),
    StylePreset(
        name="Neon Glow",
        description="Cyan neon text with glow effect",
        style=SubtitleStyle(
            font_family="Baloo 2",
            font_size=46,
            text_color="#00FFFF",
            outline_color="#0066FF",
            outline_width=3,
            shadow_color="#8000FFFF",
            shadow_offset_x=0,
            shadow_offset_y=0,
        ),
    ),
    StylePreset(
        name="Minimal Dark",
        description="Dark background box with white text",
        style=SubtitleStyle(
            font_family="Noto Sans Devanagari",
            font_size=40,
            text_color="#FFFFFF",
            outline_color="",
            outline_width=0,
            bg_color="#CC000000",
            bg_padding=12,
        ),
    ),
    StylePreset(
        name="Cinematic",
        description="Elegant serif-style with subtle shadow",
        style=SubtitleStyle(
            font_family="Noto Sans Devanagari",
            font_size=50,
            text_color="#F0E6D3",
            outline_color="#1A1A1A",
            outline_width=2,
            shadow_color="#80000000",
            shadow_offset_x=3,
            shadow_offset_y=3,
            italic=True,
        ),
    ),
    StylePreset(
        name="Karaoke Pop",
        description="Bright magenta for karaoke-style segments",
        style=SubtitleStyle(
            font_family="Mukta",
            font_size=54,
            text_color="#FF1493",
            outline_color="#FFFFFF",
            outline_width=3,
            bold=True,
        ),
    ),
]


def load_custom_presets(path: str) -> list[StylePreset]:
    """Load custom presets from a JSON file."""
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [StylePreset.from_dict(d) for d in data]


def save_custom_presets(presets: list[StylePreset], path: str) -> None:
    """Save custom presets to a JSON file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump([p.to_dict() for p in presets], f, indent=2, ensure_ascii=False)


def get_all_presets(custom_path: Optional[str] = None) -> list[StylePreset]:
    """Return built-in presets + any saved custom presets."""
    presets = list(BUILTIN_PRESETS)
    if custom_path:
        presets.extend(load_custom_presets(custom_path))
    return presets
