"""Frame-by-frame video exporter with QPainter-based subtitle rendering.

Uses PySide6 QPainter with Qt's native text shaping engine (DirectWrite on
Windows) for correct rendering of all complex scripts: Devanagari (Hindi),
Tamil, Gujarati, Gurmukhi (Punjabi), Telugu, Kannada, Malayalam, Bengali, etc.

Pipeline: FFmpeg (decode) → QPainter (render subs) → FFmpeg (encode)
"""

from __future__ import annotations
import os
import subprocess
import sys
import tempfile
import asyncio
from typing import AsyncGenerator, Optional

import numpy as np
from PIL import Image, ImageFilter

from PySide6.QtGui import (
    QGuiApplication, QImage, QPainter, QFont, QFontMetrics, QColor,
    QPainterPath, QPen, QLinearGradient, QBrush, QFontDatabase,
)
from PySide6.QtCore import Qt, QPointF, QRectF

from models.subtitle import SubtitleTrack, SubtitleSegment, SubtitleStyle
from models.animations import AnimationType, compute_animation_state, compute_word_animation_state, WordAnimationState
from core.video_utils import get_video_info, OUTPUT_FORMATS
from server.config import FONTS_DIR


# ── Qt Application singleton ─────────────────────────────────────────────────
# QGuiApplication must exist before using QFont / QPainter.
# We don't run its event loop — it's only needed as a singleton instance.
# Disable Qt's DPI scaling so font pixel sizes match CSS pixels exactly.
os.environ.setdefault("QT_FONT_DPI", "96")
os.environ.setdefault("QT_SCALE_FACTOR", "1")

def _ensure_qapp():
    """Ensure a QGuiApplication instance exists."""
    app = QGuiApplication.instance()
    if app is None:
        app = QGuiApplication(sys.argv)
    return app

_ensure_qapp()


def _build_concat_filter(video_segments) -> Optional[str]:
    """Build FFmpeg complex filter string for concatenating video segments."""
    if not video_segments:
        return None

    filter_parts = []
    stream_labels = []

    for i, seg in enumerate(video_segments):
        ss = seg.source_start
        se = seg.source_end
        
        filter_parts.append(f"[0:v]trim=start={ss}:end={se},setpts=PTS-STARTPTS[v{i}]")
        filter_parts.append(f"[0:a]atrim=start={ss}:end={se},asetpts=PTS-STARTPTS[a{i}]")
        stream_labels.append(f"[v{i}][a{i}]")

    if not stream_labels:
        return None

    concat_part = "".join(stream_labels) + f"concat=n={len(video_segments)}:v=1:a=1[outv][outa]"
    filter_parts.append(concat_part)
    return ";".join(filter_parts)


# ── Font registration & cache ────────────────────────────────────────────────

_fonts_registered = False
_font_cache: dict[tuple[str, int, int, str], QFont] = {}

# Map CSS weight (100-900) to closest QFont.Weight enum value
_WEIGHT_MAP = {
    100: QFont.Weight.Thin,
    200: QFont.Weight.ExtraLight,
    300: QFont.Weight.Light,
    400: QFont.Weight.Normal,
    500: QFont.Weight.Medium,
    600: QFont.Weight.DemiBold,
    700: QFont.Weight.Bold,
    800: QFont.Weight.ExtraBold,
    900: QFont.Weight.Black,
}


def _register_fonts():
    """Register custom TTF/OTF fonts from FONTS_DIR with Qt's font database."""
    global _fonts_registered
    if _fonts_registered:
        return
    _fonts_registered = True

    if not os.path.isdir(FONTS_DIR):
        return

    for filename in os.listdir(FONTS_DIR):
        if filename.lower().endswith(('.ttf', '.otf')):
            font_path = os.path.join(FONTS_DIR, filename)
            font_id = QFontDatabase.addApplicationFont(font_path)
            if font_id >= 0:
                families = QFontDatabase.applicationFontFamilies(font_id)
                print(f"[Exporter] Registered font: {filename} -> {families}")


def _css_weight_to_qt(weight: int) -> QFont.Weight:
    """Map a CSS font-weight (100-900) to the closest QFont.Weight."""
    closest = min(_WEIGHT_MAP.keys(), key=lambda k: abs(k - weight))
    return _WEIGHT_MAP[closest]


def _get_font(family: str, size: int, weight: int = 400, style: str = "normal") -> QFont:
    """Get a QFont with the specified family, size, weight, and style.

    Qt's font system provides automatic fallback for scripts not covered
    by the primary font — if the chosen font lacks Tamil/Gujarati/etc.
    glyphs, Qt will transparently use a system font that supports them.
    """
    key = (family, size, weight, style)
    if key in _font_cache:
        return _font_cache[key]

    _register_fonts()

    font = QFont(family)
    font.setPixelSize(size)  # Pixel size, not points — matches CSS px exactly
    font.setWeight(_css_weight_to_qt(weight))

    if style in ('italic', 'oblique'):
        font.setItalic(True)

    font.setKerning(True)
    font.setHintingPreference(QFont.HintingPreference.PreferFullHinting)

    _font_cache[key] = font
    return font


def _parse_hex_color(hex_color: str, effective_opacity: float = 1.0) -> QColor:
    """Parse hex color string to QColor with opacity applied."""
    if not hex_color:
        return QColor(0, 0, 0, 0)

    hex_color = hex_color.lstrip("#")

    if len(hex_color) == 6:
        r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
        a = 255
    elif len(hex_color) == 8:
        a, r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16), int(hex_color[6:8], 16)
    else:
        r, g, b, a = 255, 255, 255, 255

    a = int(a * effective_opacity)
    return QColor(r, g, b, a)


def _apply_text_transform(text: str, transform: str) -> str:
    """Apply CSS-like text-transform to a string."""
    if transform == "uppercase":
        return text.upper()
    elif transform == "lowercase":
        return text.lower()
    elif transform == "capitalize":
        return text.title()
    return text


# ── Export function ───────────────────────────────────────────────────────────

async def export_video(
    video_path: str,
    output_path: str,
    subtitle_track: SubtitleTrack,
    output_format_key: str = "MP4 (H.264)",
) -> AsyncGenerator[tuple[int, str, Optional[str]], None]:
    """Async generator that exports video with burned-in subtitles.

    Yields:
        (progress_percent, status_message, output_path_or_none)
    """
    yield (0, "Analysing video…", None)
    info = await asyncio.to_thread(get_video_info, video_path)
    width, height = info.width, info.height
    
    # Ensure dimensions are even for yuv420p support in x264/VP9
    w = width if width % 2 == 0 else width - 1
    h = height if height % 2 == 0 else height - 1

    fps = info.fps
    fmt = OUTPUT_FORMATS.get(output_format_key, OUTPUT_FORMATS["MP4 (H.264)"])

    # 1. PRE-PROCESS CUTS if needed
    source_video_path = video_path
    temp_preprocessed = None
    
    if subtitle_track.video_segments and len(subtitle_track.video_segments) > 0:
        seg = subtitle_track.video_segments[0]
        is_uncut = len(subtitle_track.video_segments) == 1 and seg.source_start <= 0.1 and seg.source_end >= info.duration - 0.1
        
        if not is_uncut:
            yield (1, "Applying cuts and trims…", None)
            filter_str = _build_concat_filter(subtitle_track.video_segments)
            if filter_str:
                temp_preprocessed = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
                temp_preprocessed.close()
                
                concat_cmd = [
                    "ffmpeg", "-y",
                    "-i", video_path,
                    "-filter_complex", filter_str,
                    "-map", "[outv]", "-map", "[outa]",
                    "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18",
                    "-c:a", "aac", "-b:a", "192k",
                    temp_preprocessed.name
                ]
                
                await asyncio.to_thread(subprocess.run, concat_cmd, check=True)
                source_video_path = temp_preprocessed.name
                
                info = await asyncio.to_thread(get_video_info, source_video_path)

    total_frames = int(info.duration * fps)

    # Extract audio to temp file
    yield (2, "Extracting audio…", None)
    audio_tmp = tempfile.NamedTemporaryFile(suffix=".aac", delete=False)
    audio_tmp.close()

    def _extract_audio():
        audio_cmd = [
            "ffmpeg", "-y",
            "-i", source_video_path,
            "-vn", "-acodec", "aac", "-b:a", "192k",
            audio_tmp.name,
        ]
        subprocess.run(
            audio_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )

    await asyncio.to_thread(_extract_audio)

    yield (5, "Rendering subtitles frame by frame…", None)
    
    loop = asyncio.get_running_loop()
    q = asyncio.Queue()

    def _render_all_frames():
        """Decode → render → encode pipeline in a thread."""
        decode_cmd = [
            "ffmpeg", "-y",
            "-i", source_video_path,
            "-f", "rawvideo",
            "-pix_fmt", "rgb24",
            "-vf", "scale='trunc(iw/2)*2:trunc(ih/2)*2'",
            "-v", "quiet",
            "-"
        ]

        encode_cmd = [
            "ffmpeg", "-y",
            "-f", "rawvideo",
            "-pix_fmt", "rgb24",
            "-s", f"{w}x{h}",
            "-r", str(fps),
            "-i", "-",
            "-i", audio_tmp.name,
            "-c:v", fmt["vcodec"],
            "-c:a", fmt["acodec"],
            "-pix_fmt", "yuv420p",
            output_path,
        ]

        decoder = subprocess.Popen(
            decode_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        encoder = subprocess.Popen(
            encode_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )

        frame_size = w * h * 3
        frame_number = 0

        has_error = False
        try:
            while True:
                if encoder.poll() is not None:
                    raise RuntimeError("FFmpeg encoder crashed or exited early.")

                raw = decoder.stdout.read(frame_size)
                if len(raw) < frame_size:
                    break

                current_time = frame_number / fps

                # Convert raw bytes → PIL Image
                img = Image.frombytes("RGB", (w, h), raw)

                if subtitle_track.video_rotation != 0:
                    img = img.rotate(-subtitle_track.video_rotation, resample=Image.Resampling.BICUBIC, expand=False, fillcolor=(0,0,0))

                # Render subtitles
                _render_subtitle_on_frame(img, current_time, subtitle_track, w, h)

                # Write rendered frame
                encoder.stdin.write(img.tobytes())

                frame_number += 1
                if frame_number % 10 == 0:
                    loop.call_soon_threadsafe(q.put_nowait, frame_number)

        except Exception as e:
            has_error = True
            loop.call_soon_threadsafe(q.put_nowait, e)
        finally:
            if decoder.poll() is None:
                decoder.kill()

            if decoder.stdout:
                decoder.stdout.close()
            decoder.wait()

            # Must close stdin first so FFmpeg knows to finish the encoding!
            if encoder.stdin:
                encoder.stdin.close()

            if has_error:
                if encoder.poll() is None:
                    encoder.kill()
                encoder.wait()
            else:
                try:
                    encoder.wait(timeout=120)
                except subprocess.TimeoutExpired:
                    encoder.kill()
                    encoder.wait()

            try:
                os.remove(audio_tmp.name)
                if temp_preprocessed:
                    os.remove(temp_preprocessed.name)
            except OSError:
                pass
            
            if not has_error:
                loop.call_soon_threadsafe(q.put_nowait, "DONE")

    # Run in background and listen to queue
    thread_task = asyncio.create_task(asyncio.to_thread(_render_all_frames))

    while True:
        msg = await q.get()
        if msg == "DONE":
            break
        if isinstance(msg, Exception):
            raise msg

        # Emitting progress continuously
        if total_frames > 0:
            pct = 5 + int(94 * msg / total_frames)
            yield (pct, f"Rendering... {msg}/{total_frames} frames", None)

    await thread_task
    yield (100, "Export complete!", output_path)


def _qimage_to_pil(qimg: QImage, w: int, h: int) -> Image.Image:
    """Convert a QImage (ARGB32) to a PIL RGBA Image."""
    ptr = qimg.bits()
    arr = np.array(ptr).reshape(h, w, 4).copy()
    # Qt ARGB32 is BGRA in memory (little-endian) — swap B↔R
    arr[:, :, [0, 2]] = arr[:, :, [2, 0]]
    return Image.fromarray(arr, "RGBA")


def _draw_text_shadow(painter: QPainter, text_path: QPainterPath,
                      style, effective_opacity: float, w: int, h: int):
    """Draw a (possibly blurred) drop shadow for text_path onto painter."""
    if not (style.shadow_enabled and style.shadow_color and
            (style.shadow_offset_x or style.shadow_offset_y or style.shadow_blur)):
        return

    shadow_color = _parse_hex_color(style.shadow_color, effective_opacity)
    shadow_path = QPainterPath(text_path)
    shadow_path.translate(style.shadow_offset_x, style.shadow_offset_y)

    if style.shadow_blur <= 0:
        # No blur — draw directly
        painter.save()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(shadow_color))
        painter.drawPath(shadow_path)
        painter.restore()
        return

    # Draw shadow on separate image, blur with PIL, composite back
    shadow_img = QImage(w, h, QImage.Format.Format_ARGB32)
    shadow_img.fill(Qt.GlobalColor.transparent)
    sp = QPainter(shadow_img)
    sp.setRenderHint(QPainter.RenderHint.Antialiasing)
    sp.setPen(Qt.PenStyle.NoPen)
    sp.setBrush(QBrush(shadow_color))
    # Paint twice to boost intensity (blur dilutes alpha)
    sp.drawPath(shadow_path)
    sp.drawPath(shadow_path)
    sp.end()

    pil_shadow = _qimage_to_pil(shadow_img, w, h)
    pil_shadow = pil_shadow.filter(ImageFilter.GaussianBlur(radius=style.shadow_blur))

    # Convert blurred PIL back to QImage
    arr_blurred = np.array(pil_shadow).copy()
    arr_blurred[:, :, [0, 2]] = arr_blurred[:, :, [2, 0]]  # RGBA → BGRA
    blurred_qimg = QImage(arr_blurred.data, w, h, w * 4, QImage.Format.Format_ARGB32)
    blurred_qimg._np_ref = arr_blurred  # prevent GC
    painter.drawImage(0, 0, blurred_qimg)


def _render_subtitle_on_frame(
    img: Image.Image, current_time: float,
    track: SubtitleTrack, w: int, h: int,
):
    """Render the active subtitle segment onto a PIL Image using QPainter."""
    seg = track.segment_at(current_time)
    if seg is None:
        return

    # Resolve per-line animation (segment override → track default)
    line_anim_str = getattr(seg, 'line_animation_type', None) or track.line_animation_type
    line_anim_dur = getattr(seg, 'line_animation_duration', None)
    if line_anim_dur is None:
        line_anim_dur = track.line_animation_duration
    line_anim_type = AnimationType(line_anim_str)
    anim_state = compute_animation_state(
        line_anim_type, seg, current_time,
        anim_duration=line_anim_dur,
        frame_height=float(h),
    )

    if anim_state.opacity <= 0:
        return

    # Resolve per-word animation type (segment override → track default)
    word_anim_str = getattr(seg, 'word_animation_type', None) or track.word_animation_type
    word_anim_dur = getattr(seg, 'word_animation_duration', None)
    if word_anim_dur is None:
        word_anim_dur = track.word_animation_duration
    word_anim_type = AnimationType(word_anim_str)

    # Create a QImage overlay for subtitle rendering
    overlay = QImage(w, h, QImage.Format.Format_ARGB32)
    overlay.fill(Qt.GlobalColor.transparent)

    painter = QPainter(overlay)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    _paint_subtitle(painter, seg, track, anim_state, word_anim_type, word_anim_dur, current_time, w, h)
    painter.end()

    # Composite QImage onto PIL frame
    overlay_pil = _qimage_to_pil(overlay, w, h)

    if img.mode != "RGBA":
        img_rgba = img.convert("RGBA")
        composited = Image.alpha_composite(img_rgba, overlay_pil)
        img.paste(composited.convert("RGB"))
    else:
        img.paste(Image.alpha_composite(img.convert("RGBA"), overlay_pil).convert("RGB"))


def _get_word_style(word, seg_style: SubtitleStyle, track: SubtitleTrack) -> SubtitleStyle:
    """Resolve the effective style for a word using the new marker system.
    
    Priority:
    1. word.style_override (per-word individual style, apply-all=false)
    2. marker == 'highlight' → track.highlight_style
    3. marker == 'spotlight' → track.spotlight_style
    4. Default → segment style
    """
    if word.style_override is not None:
        if isinstance(word.style_override, SubtitleStyle):
            return word.style_override
        return SubtitleStyle.from_dict(word.style_override)

    marker = getattr(word, 'marker', 'standard')
    if marker == 'highlight':
        return track.highlight_style
    if marker == 'spotlight':
        return track.spotlight_style

    return seg_style


def _paint_subtitle(painter: QPainter, seg, track: SubtitleTrack, anim_state,
                    word_anim_type: AnimationType, word_anim_dur: float,
                    current_time: float, frame_w, frame_h):
    """Paint subtitle text — routes to word-by-word if non-standard markers or word animation."""
    has_non_standard = any(
        getattr(w, 'marker', 'standard') != 'standard' or w.style_override is not None
        for w in seg.words
    )

    # Word animation requires word-by-word rendering
    needs_word_by_word = has_non_standard or word_anim_type != AnimationType.NONE

    if needs_word_by_word:
        _paint_subtitle_word_by_word(painter, seg, track, anim_state,
                                     word_anim_type, word_anim_dur, current_time,
                                     frame_w, frame_h)
    else:
        _paint_subtitle_uniform(painter, seg, track, anim_state, frame_w, frame_h)


def _paint_subtitle_word_by_word(painter: QPainter, seg, track: SubtitleTrack, anim_state,
                                  word_anim_type: AnimationType, word_anim_dur: float,
                                  current_time: float, frame_w, frame_h):
    """Render each word individually with its own style and per-word animation."""
    pos_x = getattr(seg, 'position_x', None)
    if pos_x is None:
        pos_x = track.position_x
    pos_y = getattr(seg, 'position_y', None)
    if pos_y is None:
        pos_y = track.position_y
    seg_style = seg.style
    box_w = track.text_box_width * frame_w

    # 1. Measure each word and compute per-word animation
    word_infos = []
    for i, word in enumerate(seg.words):
        style = _get_word_style(word, seg_style, track)
        font = _get_font(style.font_family, style.font_size, style.font_weight, style.font_style)
        fm = QFontMetrics(font)
        word_text = _apply_text_transform(word.word, style.text_transform)
        display = word_text + (" " if i < len(seg.words) - 1 else "")
        advance = fm.horizontalAdvance(display)
        wh = fm.height()

        # Compute per-word animation state
        # Per-word override takes precedence over segment/track word animation
        w_anim_type = word_anim_type
        w_anim_dur = word_anim_dur
        word_override_type = getattr(word, 'word_animation_type', None)
        if word_override_type:
            w_anim_type = AnimationType(word_override_type)
        word_override_dur = getattr(word, 'word_animation_duration', None)
        if word_override_dur is not None:
            w_anim_dur = word_override_dur

        w_anim_state = compute_word_animation_state(
            w_anim_type, word, current_time,
            anim_duration=w_anim_dur,
            frame_height=float(frame_h),
        )

        word_infos.append((display, font, fm, style, advance, wh, word, w_anim_state))

    if not word_infos:
        return

    # 2. Wrap into lines respecting box_w
    lines: list[list[tuple]] = []
    current_line: list[tuple] = []
    current_line_w = 0.0
    for info in word_infos:
        w_adv = info[4]
        if current_line and current_line_w + w_adv > box_w:
            lines.append(current_line)
            current_line = [info]
            current_line_w = w_adv
        else:
            current_line.append(info)
            current_line_w += w_adv
    if current_line:
        lines.append(current_line)

    # 3. Compute line heights and total block height
    line_max_h = [max((info[5] for info in line), default=0) for line in lines]
    first_style = word_infos[0][3]
    lh_mult = getattr(first_style, 'line_height', 1.2)
    total_block_h = sum(h * lh_mult for h in line_max_h)

    base_x = pos_x * frame_w
    base_y = pos_y * frame_h - total_block_h + anim_state.offset_y

    painter.save()
    cursor_y = base_y
    for line, max_h in zip(lines, line_max_h):
        line_w = sum(info[4] for info in line)
        cursor_x = base_x - line_w / 2 + anim_state.offset_x

        for display, font, fm, style, w_adv, w_h, word, w_anim in line:
            # Compose line animation with word animation
            word_opacity = w_anim.opacity
            word_offset_x = w_anim.offset_x
            word_offset_y = w_anim.offset_y

            # Skip invisible words (typewriter: word not yet revealed)
            if not w_anim.visible:
                cursor_x += w_adv
                continue

            effective_opacity = anim_state.opacity * word_opacity * getattr(style, 'text_opacity', 1.0)
            if effective_opacity <= 0:
                cursor_x += w_adv
                continue

            draw_x = cursor_x + word_offset_x
            draw_y = cursor_y + word_offset_y
            baseline_y = draw_y + fm.ascent()

            # Build text path (proper shaping for all scripts)
            text_path = QPainterPath()
            text_path.addText(QPointF(draw_x, baseline_y), font, display)

            # Background box
            if style.bg_color:
                bg_pad = getattr(style, 'bg_padding', 0)
                painter.fillRect(
                    QRectF(draw_x - bg_pad, draw_y - bg_pad,
                           w_adv + bg_pad * 2, max_h + bg_pad * 2),
                    _parse_hex_color(style.bg_color, effective_opacity))

            # Shadow
            _draw_text_shadow(painter, text_path, style, effective_opacity, frame_w, frame_h)

            # Stroke (drawn before fill so fill covers it)
            if style.stroke_enabled and getattr(style, 'outline_width', 0) > 0:
                stroke_pen = QPen(_parse_hex_color(style.outline_color, effective_opacity))
                stroke_pen.setWidthF(style.outline_width * 2)
                stroke_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                painter.setPen(stroke_pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawPath(text_path)

            # Fill — karaoke highlight changes the fill color
            painter.setPen(Qt.PenStyle.NoPen)
            if w_anim.is_highlighted:
                # Karaoke: highlighted word gets a distinct color
                painter.setBrush(QBrush(_parse_hex_color('#FFD700', effective_opacity)))
            elif style.fill_type == "gradient":
                c1 = _parse_hex_color(style.gradient_color1, effective_opacity)
                c2 = _parse_hex_color(style.gradient_color2, effective_opacity)
                rad = np.radians(getattr(style, 'gradient_angle', 0))
                cxx, cyy = draw_x + w_adv / 2, draw_y + w_h / 2
                dx, dy = np.cos(rad) * w_adv / 2, np.sin(rad) * w_h / 2
                gradient = QLinearGradient(QPointF(cxx - dx, cyy - dy), QPointF(cxx + dx, cyy + dy))
                gradient.setColorAt(0.0, c1)
                gradient.setColorAt(1.0, c2)
                painter.setBrush(QBrush(gradient))
            else:
                painter.setBrush(QBrush(_parse_hex_color(style.text_color, effective_opacity)))

            painter.drawPath(text_path)
            cursor_x += w_adv

        cursor_y += max_h * lh_mult

    painter.restore()


def _paint_subtitle_uniform(painter: QPainter, seg, track: SubtitleTrack, anim_state, frame_w, frame_h):
    """Paint subtitle text as a uniform block using QPainterPath for proper text shaping."""
    style = seg.style
    pos_x = getattr(seg, 'position_x', None)
    if pos_x is None:
        pos_x = track.position_x
    pos_y = getattr(seg, 'position_y', None)
    if pos_y is None:
        pos_y = track.position_y
    box_w = track.text_box_width * frame_w

    font = _get_font(style.font_family, style.font_size, style.font_weight, style.font_style)
    fm = QFontMetrics(font)

    anim_type_str = getattr(seg, 'line_animation_type', None) or track.line_animation_type
    anim_type = AnimationType(anim_type_str)
    if anim_type == AnimationType.TYPEWRITER and anim_state.visible_char_count >= 0:
        full_text = seg.text[:anim_state.visible_char_count]
    else:
        full_text = seg.text

    full_text = _apply_text_transform(full_text, style.text_transform)
    if not full_text.strip():
        return

    # Wrap text into lines respecting box_w
    words = full_text.split()
    lines = []
    current_line = ""
    for w in words:
        test = (current_line + " " + w).strip()
        if current_line and fm.horizontalAdvance(test) > box_w:
            lines.append(current_line)
            current_line = w
        else:
            current_line = test
    if current_line:
        lines.append(current_line)

    effective_opacity = anim_state.opacity * getattr(style, 'text_opacity', 1.0)
    line_h = fm.height() * getattr(style, 'line_height', 1.2)
    total_block_h = line_h * len(lines)

    base_x = pos_x * frame_w
    base_y = pos_y * frame_h - total_block_h + anim_state.offset_y

    painter.save()
    rotation = getattr(style, 'rotation', 0)
    if rotation != 0:
        cx = base_x
        cy = base_y + total_block_h / 2
        painter.translate(cx, cy)
        painter.rotate(rotation)
        painter.translate(-cx, -cy)

    for line_idx, line_text in enumerate(lines):
        if not line_text.strip():
            continue

        advance = fm.horizontalAdvance(line_text)
        line_top = base_y + line_idx * line_h
        baseline_y = line_top + fm.ascent()
        start_x = base_x - advance / 2 + anim_state.offset_x

        # Build text path (proper shaping for all Indian scripts)
        text_path = QPainterPath()
        text_path.addText(QPointF(start_x, baseline_y), font, line_text)

        # Background box
        if style.bg_color:
            bg_pad = getattr(style, 'bg_padding', 0)
            painter.fillRect(
                QRectF(start_x - bg_pad, line_top - bg_pad,
                       advance + bg_pad * 2, line_h + bg_pad * 2),
                _parse_hex_color(style.bg_color, effective_opacity))

        # Shadow
        _draw_text_shadow(painter, text_path, style, effective_opacity, frame_w, frame_h)

        # Stroke (drawn before fill)
        if style.stroke_enabled and getattr(style, 'outline_width', 0) > 0:
            stroke_pen = QPen(_parse_hex_color(style.outline_color, effective_opacity))
            stroke_pen.setWidthF(style.outline_width * 2)
            stroke_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(stroke_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(text_path)

        # Fill
        painter.setPen(Qt.PenStyle.NoPen)
        if style.fill_type == "gradient":
            c1 = _parse_hex_color(style.gradient_color1, effective_opacity)
            c2 = _parse_hex_color(style.gradient_color2, effective_opacity)
            rad = np.radians(getattr(style, 'gradient_angle', 0))
            cxx = start_x + advance / 2
            cyy = line_top + line_h / 2
            dx, dy = np.cos(rad) * advance / 2, np.sin(rad) * line_h / 2
            gradient = QLinearGradient(QPointF(cxx - dx, cyy - dy), QPointF(cxx + dx, cyy + dy))
            gradient.setColorAt(0.0, c1)
            gradient.setColorAt(1.0, c2)
            painter.setBrush(QBrush(gradient))
        else:
            painter.setBrush(QBrush(_parse_hex_color(style.text_color, effective_opacity)))

        painter.drawPath(text_path)

    painter.restore()
