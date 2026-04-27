"""Frame-by-frame video exporter with Skia + HarfBuzz subtitle rendering.

Uses uharfbuzz (the same shaping engine Chrome uses) for correct rendering
of all complex scripts: Devanagari (Hindi), Tamil, Gujarati, etc.
Uses skia-python for drawing text, strokes, shadows, and gradients.

Pipeline: FFmpeg (decode) → Skia (render subs) → FFmpeg (encode)
"""

from __future__ import annotations
import os
import subprocess
import sys
import tempfile
import asyncio
import math
from typing import AsyncGenerator, Optional

import numpy as np
from PIL import Image, ImageFilter
import skia

from models.subtitle import SubtitleTrack, SubtitleSegment, SubtitleStyle
from models.animations import AnimationType, compute_animation_state, compute_word_animation_state, WordAnimationState
from core.video_utils import get_video_info, OUTPUT_FORMATS
from core.text_shaping import shape_text, measure_text, ShapedText
from server.config import FONTS_DIR, get_ffmpeg_path


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


# ── Color helpers ─────────────────────────────────────────────────────────────

def _parse_hex_color(hex_color: str, opacity: float = 1.0) -> int:
    """Parse hex color string to a Skia color int (ARGB)."""
    if not hex_color:
        return skia.Color(0, 0, 0, 0)

    hex_color = hex_color.lstrip("#")

    if len(hex_color) == 6:
        r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
        a = 255
    elif len(hex_color) == 8:
        a, r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16), int(hex_color[6:8], 16)
    else:
        r, g, b, a = 255, 255, 255, 255

    a = int(a * opacity)
    return skia.Color(r, g, b, a)


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
    layout_data: list = None,
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
                    get_ffmpeg_path(), "-y",
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
            get_ffmpeg_path(), "-y",
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
            get_ffmpeg_path(), "-y",
            "-i", source_video_path,
            "-f", "rawvideo",
            "-pix_fmt", "rgb24",
            "-vf", "scale='trunc(iw/2)*2:trunc(ih/2)*2'",
            "-v", "quiet",
            "-"
        ]

        encode_cmd = [
            get_ffmpeg_path(), "-y",
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

        # Build layout lookup: seg_idx → layout
        _layout_map = {}
        if layout_data:
            for entry in layout_data:
                _layout_map[entry["seg_idx"]] = entry

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
                _render_subtitle_on_frame(img, current_time, subtitle_track, w, h, _layout_map)

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


# ── Subtitle rendering (Skia) ────────────────────────────────────────────────

def _render_subtitle_on_frame(
    img: Image.Image, current_time: float,
    track: SubtitleTrack, w: int, h: int,
    layout_map: dict = None,
):
    """Render the active subtitle segment onto a PIL Image using Skia."""
    seg = track.segment_at(current_time)
    if seg is None:
        return

    # Find segment index for layout lookup
    seg_idx = None
    if layout_map:
        for i, s in enumerate(track.segments):
            if s is seg:
                seg_idx = i
                break
    seg_layout = layout_map.get(seg_idx) if (layout_map and seg_idx is not None) else None

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

    # Create Skia surface for overlay
    surface = skia.Surface(w, h)
    canvas = surface.getCanvas()
    canvas.clear(skia.Color(0, 0, 0, 0))

    _paint_subtitle(canvas, seg, track, anim_state, word_anim_type, word_anim_dur,
                    current_time, w, h, seg_layout)

    # Convert Skia surface → PIL RGBA and composite
    # IMPORTANT: use toarray() with explicit RGBA color type.
    # tobytes() returns native BGRA which swaps R/B channels!
    overlay_img_np = surface.makeImageSnapshot().toarray(
        colorType=skia.ColorType.kRGBA_8888_ColorType,
        alphaType=skia.AlphaType.kUnpremul_AlphaType
    )
    overlay_pil = Image.fromarray(overlay_img_np, "RGBA")

    if img.mode != "RGBA":
        img_rgba = img.convert("RGBA")
        composited = Image.alpha_composite(img_rgba, overlay_pil)
        img.paste(composited.convert("RGB"))
    else:
        img.paste(Image.alpha_composite(img.convert("RGBA"), overlay_pil).convert("RGB"))


def _get_word_style(word, seg_style: SubtitleStyle, track: SubtitleTrack) -> SubtitleStyle:
    """Resolve the effective style for a word using the marker system.
    
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


def _paint_subtitle(canvas: skia.Canvas, seg, track: SubtitleTrack, anim_state,
                    word_anim_type: AnimationType, word_anim_dur: float,
                    current_time: float, frame_w, frame_h, seg_layout=None):
    """Paint subtitle text — routes to word-by-word if non-standard markers or word animation."""
    has_non_standard = any(
        getattr(w, 'marker', 'standard') != 'standard' or w.style_override is not None
        for w in seg.words
    )

    # Word animation requires word-by-word rendering
    needs_word_by_word = has_non_standard or word_anim_type != AnimationType.NONE

    if needs_word_by_word:
        _paint_subtitle_word_by_word(canvas, seg, track, anim_state,
                                     word_anim_type, word_anim_dur, current_time,
                                     frame_w, frame_h, seg_layout)
    else:
        _paint_subtitle_uniform(canvas, seg, track, anim_state, frame_w, frame_h, seg_layout)


# ── Draw helpers ──────────────────────────────────────────────────────────────

def _draw_text_blob(canvas: skia.Canvas, blob: skia.TextBlob, x: float, y: float,
                    style: SubtitleStyle, effective_opacity: float,
                    advance_width: float, line_h: float,
                    is_highlighted: bool = False,
                    frame_w: int = 0, frame_h: int = 0):
    """Draw a shaped text blob with background, shadow, stroke, and fill."""
    if blob is None:
        return

    # ── Background box (drawn first, behind everything) ───────────────────
    if style.bg_color:
        bg_pad = getattr(style, 'bg_padding', 0)
        bg_paint = skia.Paint(AntiAlias=True)
        bg_paint.setColor(_parse_hex_color(style.bg_color, effective_opacity))
        bg_rect = skia.Rect.MakeXYWH(
            x - bg_pad, y - line_h - bg_pad,
            advance_width + bg_pad * 2, line_h + bg_pad * 2)
        canvas.drawRect(bg_rect, bg_paint)

    # ── Prepare shadow as DropShadow image filter ─────────────────────────
    shadow_filter = None
    if (style.shadow_enabled and style.shadow_color and
            (style.shadow_offset_x or style.shadow_offset_y or style.shadow_blur)):
        sc = _parse_hex_color(style.shadow_color, effective_opacity)
        shadow_filter = skia.ImageFilters.DropShadow(
            style.shadow_offset_x, style.shadow_offset_y,
            style.shadow_blur, style.shadow_blur, sc
        )

    # ── Fill paint ────────────────────────────────────────────────────────
    fill_paint = skia.Paint(AntiAlias=True)

    if is_highlighted:
        fill_paint.setColor(_parse_hex_color('#FFD700', effective_opacity))
    elif style.fill_type == "gradient":
        c1 = _parse_hex_color(style.gradient_color1, effective_opacity)
        c2 = _parse_hex_color(style.gradient_color2, effective_opacity)
        rad = math.radians(getattr(style, 'gradient_angle', 0))
        cx = x + advance_width / 2
        cy = y - line_h / 2
        dx = math.cos(rad) * advance_width / 2
        dy = math.sin(rad) * line_h / 2
        shader = skia.GradientShader.MakeLinear(
            points=[skia.Point(cx - dx, cy - dy), skia.Point(cx + dx, cy + dy)],
            colors=[c1, c2],
        )
        fill_paint.setShader(shader)
    else:
        fill_paint.setColor(_parse_hex_color(style.text_color, effective_opacity))

    # ── Stroke + Shadow ───────────────────────────────────────────────────
    if style.stroke_enabled and getattr(style, 'outline_width', 0) > 0:
        stroke_paint = skia.Paint(AntiAlias=True)
        stroke_paint.setStyle(skia.Paint.kStroke_Style)
        stroke_paint.setColor(_parse_hex_color(style.outline_color, effective_opacity))
        stroke_paint.setStrokeWidth(style.outline_width * 2)
        stroke_paint.setStrokeJoin(skia.Paint.kRound_Join)
        # Shadow goes on stroke paint (drawn first), fill has no shadow
        if shadow_filter:
            stroke_paint.setImageFilter(shadow_filter)
        canvas.drawTextBlob(blob, x, y, stroke_paint)
        # Fill on top without shadow
        canvas.drawTextBlob(blob, x, y, fill_paint)
    else:
        # No stroke — shadow goes on the fill paint
        if shadow_filter:
            fill_paint.setImageFilter(shadow_filter)
        canvas.drawTextBlob(blob, x, y, fill_paint)



# ── Word-by-word rendering ────────────────────────────────────────────────────

def _paint_subtitle_word_by_word(canvas: skia.Canvas, seg, track: SubtitleTrack, anim_state,
                                  word_anim_type: AnimationType, word_anim_dur: float,
                                  current_time: float, frame_w, frame_h, seg_layout=None):
    """Render each word individually with its own style and per-word animation."""
    seg_style = seg.style

    # Build pre-computed position lookup: word_idx → {x, y, width, line_height}
    layout_by_idx = {}
    if seg_layout and seg_layout.get("mode") == "word_by_word" and seg_layout.get("words"):
        for wl in seg_layout["words"]:
            layout_by_idx[wl["word_idx"]] = wl

    # 1. Shape every word and compute per-word animation
    word_infos = []
    for i, word in enumerate(seg.words):
        style = _get_word_style(word, seg_style, track)
        word_text = _apply_text_transform(word.word, style.text_transform)
        display = word_text + (" " if i < len(seg.words) - 1 else "")

        shaped = shape_text(display, style.font_family, style.font_size,
                           style.font_weight, style.font_style)

        # Compute per-word animation state
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

        word_infos.append((display, style, shaped, word, w_anim_state, i))

    if not word_infos:
        return

    # If we have pre-computed layout, use those positions directly
    if layout_by_idx:
        for display, style, shaped, word, w_anim, word_idx in word_infos:
            wl = layout_by_idx.get(word_idx)
            if wl is None:
                continue

            if not w_anim.visible:
                continue

            word_opacity = w_anim.opacity
            effective_opacity = anim_state.opacity * word_opacity * getattr(style, 'text_opacity', 1.0)
            if effective_opacity <= 0:
                continue

            # Use frontend-computed positions + animation offsets
            # Frontend uses textBaseline='top', so y is top of text.
            # Skia drawTextBlob uses baseline, so add ascent.
            draw_x = wl["x"] + w_anim.offset_x + anim_state.offset_x
            draw_y = wl["y"] + w_anim.offset_y + anim_state.offset_y + shaped.ascent

            line_h = wl.get("line_height", shaped.line_height)

            if w_anim.scale != 1.0 and shaped.blob is not None:
                canvas.save()
                cx = draw_x + wl["width"] / 2
                cy = draw_y - shaped.ascent / 2
                canvas.translate(cx, cy)
                canvas.scale(w_anim.scale, w_anim.scale)
                canvas.translate(-cx, -cy)
                _draw_text_blob(canvas, shaped.blob, draw_x, draw_y,
                               style, effective_opacity,
                               wl["width"], line_h,
                               is_highlighted=w_anim.is_highlighted,
                               frame_w=frame_w, frame_h=frame_h)
                canvas.restore()
            else:
                _draw_text_blob(canvas, shaped.blob, draw_x, draw_y,
                               style, effective_opacity,
                               wl["width"], line_h,
                               is_highlighted=w_anim.is_highlighted,
                               frame_w=frame_w, frame_h=frame_h)
        return

    # ── Fallback: compute positions on backend (no layout_data) ──
    pos_x = getattr(seg, 'position_x', None)
    if pos_x is None:
        pos_x = track.position_x
    pos_y = getattr(seg, 'position_y', None)
    if pos_y is None:
        pos_y = track.position_y
    box_w = track.text_box_width * frame_w

    # Wrap into lines
    lines: list[list[tuple]] = []
    current_line: list[tuple] = []
    current_line_w = 0.0
    for info in word_infos:
        w_adv = info[2].advance_width
        if current_line and current_line_w + w_adv > box_w:
            lines.append(current_line)
            current_line = [info]
            current_line_w = w_adv
        else:
            current_line.append(info)
            current_line_w += w_adv
    if current_line:
        lines.append(current_line)

    first_style = word_infos[0][1]
    base_line_h = first_style.font_size * getattr(first_style, 'line_height', 1.2)
    total_block_h = base_line_h * len(lines)

    base_x = pos_x * frame_w
    base_y = pos_y * frame_h - total_block_h + anim_state.offset_y

    cursor_y = base_y
    for line in lines:
        line_w = sum(info[2].advance_width for info in line)
        cursor_x = base_x - line_w / 2 + anim_state.offset_x

        for display, style, shaped, word, w_anim, word_idx in line:
            if not w_anim.visible:
                cursor_x += shaped.advance_width
                continue

            word_opacity = w_anim.opacity
            effective_opacity = anim_state.opacity * word_opacity * getattr(style, 'text_opacity', 1.0)
            if effective_opacity <= 0:
                cursor_x += shaped.advance_width
                continue

            draw_x = cursor_x + w_anim.offset_x
            draw_y = cursor_y + w_anim.offset_y + shaped.ascent

            if w_anim.scale != 1.0 and shaped.blob is not None:
                canvas.save()
                cx = draw_x + shaped.advance_width / 2
                cy = draw_y - shaped.ascent / 2
                canvas.translate(cx, cy)
                canvas.scale(w_anim.scale, w_anim.scale)
                canvas.translate(-cx, -cy)

                _draw_text_blob(canvas, shaped.blob, draw_x, draw_y,
                               style, effective_opacity,
                               shaped.advance_width, shaped.line_height,
                               is_highlighted=w_anim.is_highlighted,
                               frame_w=frame_w, frame_h=frame_h)
                canvas.restore()
            else:
                _draw_text_blob(canvas, shaped.blob, draw_x, draw_y,
                               style, effective_opacity,
                               shaped.advance_width, shaped.line_height,
                               is_highlighted=w_anim.is_highlighted,
                               frame_w=frame_w, frame_h=frame_h)

            cursor_x += shaped.advance_width

        cursor_y += base_line_h


# ── Uniform rendering ─────────────────────────────────────────────────────────

def _paint_subtitle_uniform(canvas: skia.Canvas, seg, track: SubtitleTrack, anim_state,
                            frame_w, frame_h, seg_layout=None):
    """Paint subtitle text as a uniform block using HarfBuzz shaping."""
    style = seg.style

    anim_type_str = getattr(seg, 'line_animation_type', None) or track.line_animation_type
    anim_type = AnimationType(anim_type_str)
    if anim_type == AnimationType.TYPEWRITER and anim_state.visible_char_count >= 0:
        full_text = seg.text[:anim_state.visible_char_count]
    else:
        full_text = seg.text

    full_text = _apply_text_transform(full_text, style.text_transform)
    if not full_text.strip():
        return

    effective_opacity = anim_state.opacity * getattr(style, 'text_opacity', 1.0)

    # If we have pre-computed layout from frontend, use it directly
    if seg_layout and seg_layout.get("mode") == "uniform" and seg_layout.get("lines"):
        canvas.save()
        rotation = getattr(style, 'rotation', 0)
        if rotation != 0:
            # Need to compute rotation center from layout
            ll = seg_layout["lines"]
            block_top = ll[0]["y"]
            total_h = seg_layout.get("base_line_h", 57.6) * len(ll)
            pos_x = getattr(seg, 'position_x', None)
            if pos_x is None:
                pos_x = track.position_x
            center_x = pos_x * frame_w
            center_y = block_top + total_h / 2
            canvas.translate(center_x, center_y)
            canvas.rotate(rotation)
            canvas.translate(-center_x, -center_y)

        for ll in seg_layout["lines"]:
            line_text = ll["text"]
            if not line_text.strip():
                continue

            shaped = shape_text(line_text, style.font_family, style.font_size,
                               style.font_weight, style.font_style)
            if shaped.blob is None:
                continue

            # Frontend uses textBaseline='top', Skia uses baseline, so add ascent
            start_x = ll["x"] + anim_state.offset_x
            baseline_y = ll["y"] + anim_state.offset_y + shaped.ascent

            _draw_text_blob(canvas, shaped.blob, start_x, baseline_y,
                           style, effective_opacity,
                           ll["width"], ll.get("line_height", shaped.line_height),
                           frame_w=frame_w, frame_h=frame_h)

        canvas.restore()
        return

    # ── Fallback: compute positions on backend ──
    pos_x = getattr(seg, 'position_x', None)
    if pos_x is None:
        pos_x = track.position_x
    pos_y = getattr(seg, 'position_y', None)
    if pos_y is None:
        pos_y = track.position_y
    box_w = track.text_box_width * frame_w

    words = full_text.split()
    lines: list[str] = []
    current_line = ""
    for w in words:
        test = (current_line + " " + w).strip()
        test_width = measure_text(test, style.font_family, style.font_size,
                                  style.font_weight, style.font_style)
        if current_line and test_width > box_w:
            lines.append(current_line)
            current_line = w
        else:
            current_line = test
    if current_line:
        lines.append(current_line)

    line_h = style.font_size * getattr(style, 'line_height', 1.2)
    total_block_h = line_h * len(lines)

    base_x = pos_x * frame_w
    base_y = pos_y * frame_h - total_block_h + anim_state.offset_y

    canvas.save()
    rotation = getattr(style, 'rotation', 0)
    if rotation != 0:
        cx = base_x
        cy = base_y + total_block_h / 2
        canvas.translate(cx, cy)
        canvas.rotate(rotation)
        canvas.translate(-cx, -cy)

    for line_idx, line_text in enumerate(lines):
        if not line_text.strip():
            continue

        shaped = shape_text(line_text, style.font_family, style.font_size,
                           style.font_weight, style.font_style)
        if shaped.blob is None:
            continue

        line_top = base_y + line_idx * line_h
        baseline_y = line_top + shaped.ascent
        start_x = base_x - shaped.advance_width / 2 + anim_state.offset_x

        _draw_text_blob(canvas, shaped.blob, start_x, baseline_y,
                       style, effective_opacity,
                       shaped.advance_width, shaped.line_height,
                       frame_w=frame_w, frame_h=frame_h)

    canvas.restore()
