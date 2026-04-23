"""Frame-by-frame video exporter with Pillow-based subtitle rendering.

Replaces the PySide6 QPainter version with PIL.ImageDraw + PIL.ImageFont.
Pipeline: FFmpeg (decode) → Pillow (render subs) → FFmpeg (encode)
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
import skia

from models.subtitle import SubtitleTrack, SubtitleSegment, SubtitleStyle
from models.animations import AnimationType, compute_animation_state
from core.video_utils import get_video_info, OUTPUT_FORMATS
from server.config import FONTS_DIR


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


# ── Font cache ────────────────────────────────────────────────────────────────

_font_cache: dict[tuple[str, int, int, str], skia.Font] = {}


def _get_font(family: str, size: int, weight: int = 400, style: str = "normal") -> skia.Font:
    """Load a skia.Font, correctly resolving weight/style variants.
    
    Priority:
    1. Weight/style-specific file (e.g. Mukta-Bold.ttf) if it exists in FONTS_DIR.
    2. Regular file from FONTS_DIR, displayed via Skia's font style (weight/slant).
    3. System font via MakeFromName with the correct Skia FontStyle.
    4. Default typeface fallback.
    """
    key = (family, size, weight, style)
    if key in _font_cache:
        return _font_cache[key]

    is_bold = weight >= 700
    is_italic = style in ('italic', 'oblique')

    # Map CSS weight to Skia weight constant
    if weight <= 300:
        sk_weight = skia.FontStyle.kLight_Weight
    elif weight <= 400:
        sk_weight = skia.FontStyle.kNormal_Weight
    elif weight <= 500:
        sk_weight = skia.FontStyle.kMedium_Weight
    elif weight <= 600:
        sk_weight = skia.FontStyle.kSemiBold_Weight
    else:
        sk_weight = skia.FontStyle.kBold_Weight

    # Map CSS style to Skia slant
    slant = skia.FontStyle.kItalic_Slant if is_italic else skia.FontStyle.kUpright_Slant
    font_style_obj = skia.FontStyle(sk_weight, skia.FontStyle.kNormal_Width, slant)

    # Font file registry — base names (without suffix) keyed by family
    font_base: dict[str, str] = {
        "Noto Sans Devanagari": "NotoSansDevanagari",
        "Mukta": "Mukta",
        "Baloo 2": "Baloo2",
    }

    typeface = None
    base = font_base.get(family)
    if base:
        # Build candidate filenames in priority order (most specific first)
        candidates = []
        if is_bold and is_italic:
            candidates += [f"{base}-BoldItalic.ttf", f"{base}-Bold.ttf"]
        elif is_bold:
            candidates.append(f"{base}-Bold.ttf")
        elif is_italic:
            candidates.append(f"{base}-Italic.ttf")
        candidates.append(f"{base}-Regular.ttf")   # fallback to Regular

        for candidate in candidates:
            font_path = os.path.join(FONTS_DIR, candidate)
            if os.path.exists(font_path):
                typeface = skia.Typeface.MakeFromFile(font_path)
                if typeface:
                    break

    # Fallback: system font with the proper Skia FontStyle (weight + slant)
    if not typeface:
        typeface = skia.Typeface.MakeFromName(family, font_style_obj)

    if not typeface:
        typeface = skia.Typeface.MakeDefault()

    font = skia.Font(typeface, size)
    font.setEdging(skia.Font.Edging.kAntiAlias)

    _font_cache[key] = font
    return font


def _parse_hex_color(hex_color: str, effective_opacity: float = 1.0) -> int:
    """Parse hex color string to skia.Color int."""
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
        
    a = int(a * effective_opacity)
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


def _render_subtitle_on_frame(
    img: Image.Image, current_time: float,
    track: SubtitleTrack, w: int, h: int,
):
    """Render the active subtitle segment onto a PIL Image using Skia."""
    seg = track.segment_at(current_time)
    if seg is None:
        return

    anim_type_str = getattr(seg, 'animation_type', None) or track.animation_type
    anim_dur = getattr(seg, 'animation_duration', None)
    if anim_dur is None:
        anim_dur = track.animation_duration
    anim_type = AnimationType(anim_type_str)
    anim_state = compute_animation_state(
        anim_type, seg, current_time,
        anim_duration=anim_dur,
        frame_height=float(h),
    )

    if anim_state.opacity <= 0:
        return

    # Create a Skia canvas for pristine rendering
    surface = skia.Surface(w, h)
    with surface as canvas:
        canvas.clear(skia.ColorTRANSPARENT)
        _paint_subtitle(canvas, seg, track, anim_state, w, h)

    # Composite Skia surface onto Pillow Image
    overlay_img_np = surface.makeImageSnapshot().toarray(
        colorType=skia.ColorType.kRGBA_8888_ColorType, 
        alphaType=skia.AlphaType.kUnpremul_AlphaType
    )
    overlay_pil = Image.fromarray(overlay_img_np, "RGBA")

    # Composite
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


def _paint_subtitle(canvas: skia.Canvas, seg, track: SubtitleTrack, anim_state, frame_w, frame_h):
    """Paint subtitle text using Skia — routes to word-by-word if any non-standard markers exist."""
    has_non_standard = any(
        getattr(w, 'marker', 'standard') != 'standard' or w.style_override is not None
        for w in seg.words
    )

    if has_non_standard:
        _paint_subtitle_word_by_word(canvas, seg, track, anim_state, frame_w, frame_h)
    else:
        _paint_subtitle_uniform(canvas, seg, track, anim_state, frame_w, frame_h)


def _paint_subtitle_word_by_word(canvas: skia.Canvas, seg, track: SubtitleTrack, anim_state, frame_w, frame_h):
    """Render each word individually with its style, with text-box wrapping."""
    # Resolve per-segment position (fallback to track)
    pos_x = getattr(seg, 'position_x', None)
    if pos_x is None:
        pos_x = track.position_x
    pos_y = getattr(seg, 'position_y', None)
    if pos_y is None:
        pos_y = track.position_y
    seg_style = seg.style
    box_w = track.text_box_width * frame_w  # max line width in pixels
    line_height_mult = getattr(seg_style, 'line_height', 1.2)

    # 1. Measure each word
    word_infos = []
    for i, word in enumerate(seg.words):
        style = _get_word_style(word, seg_style, track)
        font = _get_font(style.font_family, style.font_size, style.font_weight, style.font_style)
        word_text = _apply_text_transform(word.word, style.text_transform)
        display = word_text + (" " if i < len(seg.words) - 1 else "")
        bounds = skia.Rect()
        advance = font.measureText(display, bounds=bounds)
        h = bounds.height() if bounds.height() > 0 else font.getSize()
        word_infos.append((display, font, style, advance, h))

    if not word_infos:
        return

    # 2. Wrap into lines respecting box_w
    lines: list[list[tuple]] = []
    current_line: list[tuple] = []
    current_line_w = 0.0
    for info in word_infos:
        _, _, _, w, _ = info
        if current_line and current_line_w + w > box_w:
            lines.append(current_line)
            current_line = [info]
            current_line_w = w
        else:
            current_line.append(info)
            current_line_w += w
    if current_line:
        lines.append(current_line)

    # 3. Compute line heights and total block height
    line_max_h = []
    for line in lines:
        lh = max((h for _, _, _, _, h in line), default=0)
        line_max_h.append(lh)

    # Estimate total height using the first line's font size for line-height
    first_style = word_infos[0][2]
    lh_mult = getattr(first_style, 'line_height', 1.2) if first_style else 1.2
    total_block_h = sum(h * lh_mult for h in line_max_h)

    base_x = pos_x * frame_w
    base_y = pos_y * frame_h - total_block_h + anim_state.offset_y

    canvas.save()

    cursor_y = base_y
    for line_idx, (line, max_h) in enumerate(zip(lines, line_max_h)):
        line_w = sum(w for _, _, _, w, _ in line)
        cursor_x = base_x - line_w / 2 + anim_state.offset_x

        for display, font, style, w_w, w_h in line:
            effective_opacity = anim_state.opacity * getattr(style, 'text_opacity', 1.0)
            metrics = font.getMetrics()
            local_y = cursor_y - metrics.fAscent

            paint = skia.Paint(AntiAlias=True)

            # Shadow
            if style.shadow_enabled and style.shadow_color and (
                style.shadow_offset_x or style.shadow_offset_y or style.shadow_blur
            ):
                sc = _parse_hex_color(style.shadow_color, effective_opacity)
                paint.setImageFilter(skia.ImageFilters.DropShadow(
                    style.shadow_offset_x, style.shadow_offset_y,
                    style.shadow_blur, style.shadow_blur, sc
                ))

            # Fill
            if style.fill_type == "gradient":
                c1 = _parse_hex_color(style.gradient_color1, effective_opacity)
                c2 = _parse_hex_color(style.gradient_color2, effective_opacity)
                rad = np.radians(getattr(style, 'gradient_angle', 0))
                cxx = cursor_x + w_w / 2
                cyy = cursor_y + w_h / 2
                dx = np.cos(rad) * w_w / 2
                dy = np.sin(rad) * w_h / 2
                paint.setShader(skia.GradientShader.MakeLinear(
                    points=[(cxx - dx, cyy - dy), (cxx + dx, cyy + dy)],
                    colors=[c1, c2]
                ))
            else:
                paint.setColor(_parse_hex_color(style.text_color, effective_opacity))

            # Background
            if style.bg_color:
                bg_pad = getattr(style, 'bg_padding', 0)
                bg_paint = skia.Paint(Color=_parse_hex_color(style.bg_color, effective_opacity), AntiAlias=True)
                bg_rect = skia.Rect.MakeXYWH(cursor_x - bg_pad, cursor_y - bg_pad, w_w + bg_pad * 2, max_h + bg_pad * 2)
                canvas.drawRect(bg_rect, bg_paint)

            # Stroke
            if style.stroke_enabled and getattr(style, 'outline_width', 0) > 0:
                stroke_paint = skia.Paint(
                    AntiAlias=True,
                    Style=skia.Paint.kStroke_Style,
                    StrokeWidth=style.outline_width * 2,
                    StrokeJoin=skia.Paint.kRound_Join,
                    Color=_parse_hex_color(style.outline_color, effective_opacity)
                )
                if style.shadow_enabled and style.shadow_color:
                    stroke_paint.setImageFilter(skia.ImageFilters.DropShadow(
                        style.shadow_offset_x, style.shadow_offset_y,
                        style.shadow_blur, style.shadow_blur,
                        _parse_hex_color(style.shadow_color, effective_opacity)
                    ))
                    paint.setImageFilter(None)
                canvas.drawString(display, cursor_x, local_y, font, stroke_paint)

            canvas.drawString(display, cursor_x, local_y, font, paint)
            cursor_x += w_w

        cursor_y += max_h * getattr(first_style, 'line_height', 1.2)

    canvas.restore()


def _paint_subtitle_uniform(canvas: skia.Canvas, seg, track: SubtitleTrack, anim_state, frame_w, frame_h):
    """Paint subtitle text as a uniform block with text-box wrapping."""
    style = seg.style
    # Resolve per-segment position (fallback to track)
    pos_x = getattr(seg, 'position_x', None)
    if pos_x is None:
        pos_x = track.position_x
    pos_y = getattr(seg, 'position_y', None)
    if pos_y is None:
        pos_y = track.position_y
    box_w = track.text_box_width * frame_w

    font = _get_font(style.font_family, style.font_size, style.font_weight, style.font_style)

    anim_type_str = getattr(seg, 'animation_type', None) or track.animation_type
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
        bounds = skia.Rect()
        font.measureText(test, bounds=bounds)
        if current_line and bounds.width() > box_w:
            lines.append(current_line)
            current_line = w
        else:
            current_line = test
    if current_line:
        lines.append(current_line)

    effective_opacity = anim_state.opacity * getattr(style, 'text_opacity', 1.0)
    metrics = font.getMetrics()
    line_h = (metrics.fDescent - metrics.fAscent) * getattr(style, 'line_height', 1.2)
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

    paint = skia.Paint(AntiAlias=True)

    if style.shadow_enabled and style.shadow_color and (
        style.shadow_offset_x or style.shadow_offset_y or style.shadow_blur
    ):
        sc = _parse_hex_color(style.shadow_color, effective_opacity)
        paint.setImageFilter(skia.ImageFilters.DropShadow(
            style.shadow_offset_x, style.shadow_offset_y,
            style.shadow_blur, style.shadow_blur, sc
        ))

    stroke_paint = None
    if style.stroke_enabled and getattr(style, 'outline_width', 0) > 0:
        stroke_paint = skia.Paint(
            AntiAlias=True,
            Style=skia.Paint.kStroke_Style,
            StrokeWidth=style.outline_width * 2,
            StrokeJoin=skia.Paint.kRound_Join,
            Color=_parse_hex_color(style.outline_color, effective_opacity)
        )
        if style.shadow_enabled and style.shadow_color:
            stroke_paint.setImageFilter(skia.ImageFilters.DropShadow(
                style.shadow_offset_x, style.shadow_offset_y,
                style.shadow_blur, style.shadow_blur,
                _parse_hex_color(style.shadow_color, effective_opacity)
            ))
            paint.setImageFilter(None)

    for line_idx, line_text in enumerate(lines):
        if not line_text.strip():
            continue

        bounds = skia.Rect()
        advance = font.measureText(line_text, bounds=bounds)
        line_top = base_y + line_idx * line_h
        local_y = line_top - metrics.fAscent
        start_x = base_x - advance / 2 + anim_state.offset_x

        # Gradient (per-line)
        if style.fill_type == "gradient":
            c1 = _parse_hex_color(style.gradient_color1, effective_opacity)
            c2 = _parse_hex_color(style.gradient_color2, effective_opacity)
            rad = np.radians(getattr(style, 'gradient_angle', 0))
            cxx = start_x + advance / 2
            cyy = line_top + line_h / 2
            dx = np.cos(rad) * advance / 2
            dy = np.sin(rad) * line_h / 2
            paint.setShader(skia.GradientShader.MakeLinear(
                points=[(cxx - dx, cyy - dy), (cxx + dx, cyy + dy)],
                colors=[c1, c2]
            ))
        else:
            paint.setColor(_parse_hex_color(style.text_color, effective_opacity))

        # Background box
        if style.bg_color:
            bg_pad = getattr(style, 'bg_padding', 0)
            bg_paint = skia.Paint(Color=_parse_hex_color(style.bg_color, effective_opacity), AntiAlias=True)
            bg_rect = skia.Rect.MakeXYWH(
                start_x - bg_pad, line_top - bg_pad,
                advance + bg_pad * 2, line_h + bg_pad * 2
            )
            canvas.drawRect(bg_rect, bg_paint)

        if stroke_paint:
            canvas.drawString(line_text, start_x, local_y, font, stroke_paint)
        canvas.drawString(line_text, start_x, local_y, font, paint)

    canvas.restore()
