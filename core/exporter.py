"""Frame-by-frame video exporter using headless Playwright for subtitle rendering.

Pipeline: FFmpeg (decode) → Playwright Canvas (render subs) → FFmpeg (encode)
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

from models.subtitle import SubtitleTrack
from core.video_utils import get_video_info, OUTPUT_FORMATS
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

    def _render_all_frames_async_wrapper():
        # This is a synchronous wrapper that will use asyncio.run to run the playwright logic
        # Because we're in a separate thread spawned by asyncio.to_thread, we need a new event loop
        # Wait, the current approach is: thread_task = asyncio.create_task(asyncio.to_thread(_render_all_frames))
        # Since Playwright needs an async loop, we can just spawn an async task in the main loop!
        pass

    async def _render_all_frames_async():
        """Decode → render via Playwright → encode pipeline."""
        import json
        import base64
        import pathlib
        from io import BytesIO
        from playwright.async_api import async_playwright

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
        has_error = False

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                
                from server.config import PROJECT_ROOT
                html_path = pathlib.Path(os.path.join(PROJECT_ROOT, "web", "export_render.html")).as_uri()
                await page.goto(html_path)
                
                import pathlib
                import json
                
                custom_fonts = []
                if os.path.isdir(FONTS_DIR):
                    for f in os.listdir(FONTS_DIR):
                        if f.lower().endswith(('.ttf', '.otf', '.woff2')):
                            name = os.path.splitext(f)[0]
                            f_path = pathlib.Path(os.path.join(FONTS_DIR, f)).absolute()
                            custom_fonts.append({
                                "name": name,
                                "url": f_path.as_uri()
                            })
                            
                track_json = subtitle_track.to_dict()
                await page.evaluate(f"initRenderer({w}, {h}, {json.dumps(json.dumps(track_json))}, {json.dumps(custom_fonts)})")
                
                batch_size = 30
                frames_batch = []
                timestamps = []
                
                while True:
                    if encoder.poll() is not None:
                        raise RuntimeError("FFmpeg encoder crashed or exited early.")
                    
                    # Fill batch
                    while len(frames_batch) < batch_size:
                        raw = await asyncio.to_thread(decoder.stdout.read, frame_size)
                        if not raw or len(raw) < frame_size:
                            break
                        frames_batch.append(raw)
                        timestamps.append(frame_number / fps)
                        frame_number += 1
                        
                    if not frames_batch:
                        break
                        
                    # Render batch in Playwright
                    frames_data = await page.evaluate(f"renderFrameBatch({timestamps})")
                    
                    for i, raw in enumerate(frames_batch):
                        img = Image.frombytes("RGB", (w, h), raw)
                        
                        if subtitle_track.video_rotation != 0:
                            img = img.rotate(-subtitle_track.video_rotation, resample=Image.Resampling.BICUBIC, expand=False, fillcolor=(0,0,0))
                            
                        # Composite overlay
                        overlay_info = frames_data[i]
                        if overlay_info.get("has_subtitle"):
                            b64_data = overlay_info["data"]
                            if b64_data.startswith("data:image/png;base64,"):
                                b64_data = b64_data.split(",", 1)[1]
                                
                            png_bytes = base64.b64decode(b64_data)
                            overlay = Image.open(BytesIO(png_bytes)).convert("RGBA")
                            
                            img.paste(overlay, (overlay_info["x"], overlay_info["y"]), overlay)
                        
                        # Write to encoder
                        await asyncio.to_thread(encoder.stdin.write, img.tobytes())
                        
                    # Emit progress
                    loop.call_soon_threadsafe(q.put_nowait, frame_number)
                    
                    frames_batch.clear()
                    timestamps.clear()

        except Exception as e:
            has_error = True
            loop.call_soon_threadsafe(q.put_nowait, e)
        finally:
            if decoder.poll() is None:
                decoder.kill()

            if decoder.stdout:
                decoder.stdout.close()
            decoder.wait()

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

    # Run the async loop instead of threading
    thread_task = asyncio.create_task(_render_all_frames_async())

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


