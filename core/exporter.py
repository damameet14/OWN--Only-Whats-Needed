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
from PIL import Image, ImageDraw, ImageFont, ImageFilter

from models.subtitle import SubtitleTrack, SubtitleSegment, SubtitleStyle
from models.animations import AnimationType, compute_animation_state
from core.video_utils import get_video_info, OUTPUT_FORMATS
from server.config import FONTS_DIR

# Try importing cv2 for gradient support
try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False


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

_font_cache: dict[tuple[str, int, int, str], ImageFont.FreeTypeFont] = {}


def _get_font(family: str, size: int, weight: int = 400, style: str = "normal") -> ImageFont.FreeTypeFont:
    """Load a font from the fonts directory. Falls back to Pillow default."""
    key = (family, size, weight, style)
    if key in _font_cache:
        return _font_cache[key]

    font = None
    font_files = {
        "Noto Sans Devanagari": "NotoSansDevanagari-Regular.ttf",
        "Mukta": "Mukta-Regular.ttf",
        "Baloo 2": "Baloo2-Regular.ttf",
    }

    font_file = font_files.get(family)
    if font_file:
        font_path = os.path.join(FONTS_DIR, font_file)
        if os.path.exists(font_path):
            try:
                font = ImageFont.truetype(font_path, size)
            except Exception:
                pass

    if font is None:
        try:
            font = ImageFont.truetype("arial.ttf", size)
        except Exception:
            font = ImageFont.load_default()

    _font_cache[key] = font
    return font


def _parse_hex_color(hex_color: str) -> tuple[int, int, int, int]:
    """Parse hex color string to (R, G, B, A) tuple."""
    if not hex_color:
        return (0, 0, 0, 0)
    hex_color = hex_color.lstrip("#")
    if len(hex_color) == 6:
        r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
        return (r, g, b, 255)
    elif len(hex_color) == 8:
        a, r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16), int(hex_color[6:8], 16)
        return (r, g, b, a)
    return (255, 255, 255, 255)


def _apply_text_transform(text: str, transform: str) -> str:
    """Apply CSS-like text-transform to a string."""
    if transform == "uppercase":
        return text.upper()
    elif transform == "lowercase":
        return text.lower()
    elif transform == "capitalize":
        return text.title()
    return text


def _create_gradient_image(width: int, height: int, color1: str, color2: str,
                           angle: int = 0, gradient_type: str = "linear") -> Image.Image:
    """Create a gradient image using cv2/numpy. Falls back to solid color1 if cv2 unavailable."""
    c1 = _parse_hex_color(color1)
    c2 = _parse_hex_color(color2)

    if not HAS_CV2 or width <= 0 or height <= 0:
        img = Image.new("RGBA", (max(1, width), max(1, height)), c1)
        return img

    if gradient_type == "radial":
        # Radial gradient from center
        cx, cy = width / 2, height / 2
        max_dist = np.sqrt(cx ** 2 + cy ** 2)
        y_coords, x_coords = np.mgrid[0:height, 0:width].astype(np.float32)
        dist = np.sqrt((x_coords - cx) ** 2 + (y_coords - cy) ** 2) / max_dist
        dist = np.clip(dist, 0, 1)
    else:
        # Linear gradient at given angle
        rad = np.radians(angle)
        cos_a, sin_a = np.cos(rad), np.sin(rad)
        y_coords, x_coords = np.mgrid[0:height, 0:width].astype(np.float32)
        # Project coordinates onto the gradient direction
        proj = x_coords * cos_a + y_coords * sin_a
        proj_min, proj_max = proj.min(), proj.max()
        if proj_max - proj_min > 0:
            dist = (proj - proj_min) / (proj_max - proj_min)
        else:
            dist = np.zeros_like(proj)

    # Interpolate colors
    gradient = np.zeros((height, width, 4), dtype=np.uint8)
    for i in range(4):
        gradient[:, :, i] = (c1[i] * (1 - dist) + c2[i] * dist).astype(np.uint8)

    return Image.fromarray(gradient, "RGBA")


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
            "-shortest",
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
                    encoder.wait(timeout=15)
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
    """Render the active subtitle segment onto a PIL Image."""
    seg = track.segment_at(current_time)
    if seg is None:
        return

    anim_type = AnimationType(track.animation_type)
    anim_state = compute_animation_state(
        anim_type, seg, current_time,
        anim_duration=track.animation_duration,
        frame_height=float(h),
    )

    if anim_state.opacity <= 0:
        return

    # Create an overlay for alpha compositing
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    _paint_subtitle(draw, seg, track, anim_state, w, h)

    # Composite
    if img.mode != "RGBA":
        img_rgba = img.convert("RGBA")
        composited = Image.alpha_composite(img_rgba, overlay)
        img.paste(composited.convert("RGB"))
    else:
        img.paste(Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB"))


def _paint_subtitle(draw, seg, track, anim_state, frame_w, frame_h):
    """Paint subtitle text using Pillow with support for all style properties."""
    style = seg.style
    pos_x = track.position_x
    pos_y = track.position_y

    font = _get_font(style.font_family, style.font_size, style.font_weight, style.font_style)

    # Build display text based on animation
    anim_type = AnimationType(track.animation_type)

    if anim_type == AnimationType.TYPEWRITER and anim_state.visible_char_count >= 0:
        display_text = seg.text[:anim_state.visible_char_count]
    else:
        display_text = seg.text

    # Apply text transform
    display_text = _apply_text_transform(display_text, style.text_transform)

    if not display_text.strip():
        return

    # Measure text
    text_bbox = draw.textbbox((0, 0), display_text, font=font)
    text_w = text_bbox[2] - text_bbox[0]
    text_h = text_bbox[3] - text_bbox[1]

    # Position
    x = pos_x * frame_w - text_w / 2
    y = pos_y * frame_h - text_h

    # Apply offset animation
    x += anim_state.offset_x
    y += anim_state.offset_y

    # Clamp to frame
    x = max(0, min(x, frame_w - text_w))
    y = max(0, min(y, frame_h - text_h))

    # Compute effective opacity
    effective_opacity = anim_state.opacity * style.text_opacity

    # Setup isolated text render canvas to support rotated components
    pad = style.bg_padding if style.bg_color else 0
    canvas_w = max(1, int(text_w + pad * 2))
    canvas_h = max(1, int(text_h + pad * 2))
    text_overlay = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    text_draw = ImageDraw.Draw(text_overlay)

    if style.bg_color:
        bg_r, bg_g, bg_b, bg_a = _parse_hex_color(style.bg_color)
        bg_a = int(bg_a * effective_opacity)
        text_draw.rectangle(
            [0, 0, text_w + pad * 2, text_h + pad * 2],
            fill=(bg_r, bg_g, bg_b, bg_a)
        )
    else:
        pad = 0

    # Shadow (with blur support)
    if style.shadow_enabled and style.shadow_color and (style.shadow_offset_x or style.shadow_offset_y or style.shadow_blur):
        sr, sg, sb, sa = _parse_hex_color(style.shadow_color)
        sa = int(sa * effective_opacity)

        if style.shadow_blur > 0:
            # Render shadow on separate image for blur
            shadow_img = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
            shadow_draw = ImageDraw.Draw(shadow_img)
            shadow_draw.text(
                (pad + style.shadow_offset_x, pad + style.shadow_offset_y),
                display_text, font=font, fill=(sr, sg, sb, sa)
            )
            shadow_img = shadow_img.filter(ImageFilter.GaussianBlur(radius=style.shadow_blur))
            text_overlay = Image.alpha_composite(text_overlay, shadow_img)
            text_draw = ImageDraw.Draw(text_overlay)
        else:
            text_draw.text(
                (pad + style.shadow_offset_x, pad + style.shadow_offset_y),
                display_text, font=font, fill=(sr, sg, sb, sa)
            )

    # Stroke
    if style.stroke_enabled and style.outline_color and style.outline_width > 0:
        or_, og, ob, oa = _parse_hex_color(style.outline_color)
        oa = int(oa * effective_opacity)
        ow = style.outline_width
        for dx in range(-ow, ow + 1):
            for dy in range(-ow, ow + 1):
                if dx == 0 and dy == 0:
                    continue
                text_draw.text((pad + dx, pad + dy), display_text, font=font,
                          fill=(or_, og, ob, oa))

    # Main text fill
    if style.fill_type == "gradient":
        # Render text as white mask, then composite with gradient
        text_mask = Image.new("L", (canvas_w, canvas_h), 0)
        mask_draw = ImageDraw.Draw(text_mask)
        mask_draw.text((pad, pad), display_text, font=font, fill=255)

        gradient_img = _create_gradient_image(
            canvas_w, canvas_h,
            style.gradient_color1, style.gradient_color2,
            style.gradient_angle, style.gradient_type
        )

        # Apply opacity to gradient
        if effective_opacity < 1.0:
            gradient_arr = np.array(gradient_img)
            gradient_arr[:, :, 3] = (gradient_arr[:, :, 3] * effective_opacity).astype(np.uint8)
            gradient_img = Image.fromarray(gradient_arr, "RGBA")

        # Apply text mask to gradient
        gradient_img.putalpha(text_mask)
        text_overlay = Image.alpha_composite(text_overlay, gradient_img)
    else:
        tr, tg, tb, ta = _parse_hex_color(style.text_color)
        ta = int(ta * effective_opacity)
        text_draw.text((pad, pad), display_text, font=font, fill=(tr, tg, tb, ta))

    # Perform Subtitle Rotation
    if style.rotation != 0:
        text_overlay = text_overlay.rotate(-style.rotation, resample=Image.Resampling.BICUBIC, expand=True)

    # Calculate final paste position (centered on x,y anchor)
    final_w, final_h = text_overlay.size
    paste_x = int(x - (final_w - text_w) / 2)
    paste_y = int(y - (final_h - text_h) / 2)

    # Paste rotated block onto main overlay
    draw._image.paste(text_overlay, (paste_x, paste_y), text_overlay)
