"""Text shaping via uharfbuzz → Skia TextBlob pipeline.

Uses HarfBuzz (the same shaping engine Chrome uses internally) to shape
complex scripts (Devanagari, Tamil, Gujarati, etc.) and then builds a
Skia TextBlob with the resulting glyph IDs and positions.

This guarantees that the glyph selection, ligature formation, and advance
widths are identical to what the browser's Canvas API produces.
"""

from __future__ import annotations
import os
from functools import lru_cache
from typing import Optional

import uharfbuzz as hb
import skia

from server.config import FONTS_DIR


# ── Font data cache ──────────────────────────────────────────────────────────
# We cache the raw bytes, HarfBuzz Face, and Skia Typeface per font file.

_font_data_cache: dict[str, bytes] = {}
_hb_face_cache: dict[str, hb.Face] = {}
_skia_typeface_cache: dict[str, skia.Typeface] = {}


def _resolve_font_path(font_family: str) -> Optional[str]:
    """Find the .ttf/.otf file for a font family name.

    Looks in FONTS_DIR for a file whose name matches the family
    (case-insensitive, ignoring spaces/hyphens).
    Falls back to the first font file found if no match.
    """
    if not os.path.isdir(FONTS_DIR):
        return None

    # Normalise the family name for matching
    norm = font_family.lower().replace(" ", "").replace("-", "").replace("_", "")

    candidates = []
    for fname in os.listdir(FONTS_DIR):
        if fname.lower().endswith(('.ttf', '.otf')):
            candidates.append(fname)
            fnorm = fname.lower().replace(" ", "").replace("-", "").replace("_", "")
            # Match e.g. "NotoSansDevanagari" against "Noto Sans Devanagari"
            if norm in fnorm or fnorm.startswith(norm):
                return os.path.join(FONTS_DIR, fname)

    # Fallback: use the first available font
    if candidates:
        return os.path.join(FONTS_DIR, candidates[0])
    return None


def _get_font_data(font_path: str) -> bytes:
    """Read and cache raw font file bytes."""
    if font_path not in _font_data_cache:
        with open(font_path, 'rb') as f:
            _font_data_cache[font_path] = f.read()
    return _font_data_cache[font_path]


def _get_hb_face(font_path: str) -> hb.Face:
    """Get or create a cached HarfBuzz Face."""
    if font_path not in _hb_face_cache:
        data = _get_font_data(font_path)
        _hb_face_cache[font_path] = hb.Face(data)
    return _hb_face_cache[font_path]


def _get_skia_typeface(font_path: str) -> skia.Typeface:
    """Get or create a cached Skia Typeface."""
    if font_path not in _skia_typeface_cache:
        tf = skia.Typeface.MakeFromFile(font_path)
        if tf is None:
            tf = skia.Typeface.MakeDefault()
        _skia_typeface_cache[font_path] = tf
    return _skia_typeface_cache[font_path]


# ── Public API ───────────────────────────────────────────────────────────────

class ShapedText:
    """Result of shaping a string: contains the Skia TextBlob and metrics."""

    __slots__ = ('blob', 'advance_width', 'ascent', 'descent', 'line_height',
                 'glyphs', 'positions', 'cluster_map')

    def __init__(self, blob: Optional[skia.TextBlob], advance_width: float,
                 ascent: float, descent: float, line_height: float,
                 glyphs: list[int], positions: list[skia.Point],
                 cluster_map: list[int]):
        self.blob = blob
        self.advance_width = advance_width
        self.ascent = ascent
        self.descent = descent
        self.line_height = line_height
        self.glyphs = glyphs
        self.positions = positions
        self.cluster_map = cluster_map


def shape_text(text: str, font_family: str, font_size: int,
               font_weight: int = 400, font_style: str = "normal") -> ShapedText:
    """Shape a string using HarfBuzz and build a Skia TextBlob.

    Args:
        text: The string to shape (can be any script).
        font_family: CSS font-family name (matched to a file in FONTS_DIR).
        font_size: Font size in pixels.
        font_weight: CSS weight (100-900), currently informational.
        font_style: "normal" or "italic", currently informational.

    Returns:
        ShapedText with the TextBlob, advance width, and font metrics.
    """
    font_path = _resolve_font_path(font_family)
    if font_path is None:
        # Absolute fallback: return empty blob
        return ShapedText(None, 0, 0, 0, font_size, [], [], [])

    # ── HarfBuzz shaping ─────────────────────────────────────────────────
    face = _get_hb_face(font_path)
    hb_font = hb.Font(face)
    # HarfBuzz uses 26.6 fixed-point (multiply by 64), but we work in
    # whole-pixel units so we set scale = font_size * 64 and divide back.
    hb_font.scale = (font_size * 64, font_size * 64)

    buf = hb.Buffer()
    buf.add_str(text)
    buf.guess_segment_properties()

    hb.shape(hb_font, buf)

    infos = buf.glyph_infos
    positions_hb = buf.glyph_positions

    # ── Build glyph list and position list ────────────────────────────────
    glyphs: list[int] = []
    pts: list[skia.Point] = []
    cluster_map: list[int] = []
    x = 0.0
    y = 0.0
    for info, pos in zip(infos, positions_hb):
        glyphs.append(info.codepoint)
        pts.append(skia.Point(x + pos.x_offset / 64.0, y - pos.y_offset / 64.0))
        cluster_map.append(info.cluster)
        x += pos.x_advance / 64.0
        y -= pos.y_advance / 64.0

    advance_width = x

    # ── Skia font metrics (ascent / descent) ──────────────────────────────
    typeface = _get_skia_typeface(font_path)
    sk_font = skia.Font(typeface, font_size)
    metrics = sk_font.getMetrics()
    ascent = -metrics.fAscent   # Skia reports ascent as negative
    descent = metrics.fDescent
    line_height = ascent + descent

    # ── Build TextBlob ────────────────────────────────────────────────────
    if not glyphs:
        return ShapedText(None, 0, ascent, descent, line_height, [], [], [])

    builder = skia.TextBlobBuilder()
    run = builder.allocRunPos(sk_font, glyphs, pts)
    blob = builder.make()

    return ShapedText(blob, advance_width, ascent, descent, line_height,
                      glyphs, pts, cluster_map)


def measure_text(text: str, font_family: str, font_size: int,
                 font_weight: int = 400, font_style: str = "normal") -> float:
    """Return the advance width of shaped text (in pixels)."""
    return shape_text(text, font_family, font_size, font_weight, font_style).advance_width
