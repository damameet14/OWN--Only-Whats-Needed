"""Video utility helpers using FFmpeg."""

from __future__ import annotations
import json
import subprocess
import sys
from dataclasses import dataclass


@dataclass
class VideoInfo:
    """Metadata about a video file."""
    duration: float       # seconds
    width: int
    height: int
    fps: float
    codec: str
    audio_codec: str
    file_path: str

    @property
    def resolution(self) -> str:
        return f"{self.width}×{self.height}"


def get_video_info(path: str) -> VideoInfo:
    """Probe a video file and return its metadata."""
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        path,
    ]
    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"ffprobe failed: {result.stderr.decode(errors='replace')}"
        )
    data = json.loads(result.stdout)
    fmt = data.get("format", {})
    duration = float(fmt.get("duration", 0))

    # Find video and audio streams
    video_stream = None
    audio_stream = None
    for s in data.get("streams", []):
        if s["codec_type"] == "video" and video_stream is None:
            video_stream = s
        elif s["codec_type"] == "audio" and audio_stream is None:
            audio_stream = s

    if video_stream is None:
        raise RuntimeError("No video stream found in file.")

    width = int(video_stream.get("width", 0))
    height = int(video_stream.get("height", 0))
    codec = video_stream.get("codec_name", "unknown")

    # FPS from r_frame_rate (e.g. "30000/1001")
    fps_str = video_stream.get("r_frame_rate", "30/1")
    num, den = fps_str.split("/")
    fps = float(num) / float(den) if float(den) != 0 else 30.0

    audio_codec = audio_stream.get("codec_name", "none") if audio_stream else "none"

    return VideoInfo(
        duration=duration,
        width=width,
        height=height,
        fps=fps,
        codec=codec,
        audio_codec=audio_codec,
        file_path=path,
    )


# ── Supported formats ────────────────────────────────────────────────────────

INPUT_EXTENSIONS = {
    ".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv",
    ".wmv", ".m4v", ".3gp", ".ts", ".mpg", ".mpeg",
}

OUTPUT_FORMATS = {
    "MP4 (H.264)": {"ext": ".mp4", "vcodec": "libx264",  "acodec": "aac"},
    "MOV (H.264)": {"ext": ".mov", "vcodec": "libx264",  "acodec": "aac"},
    "AVI (MPEG4)": {"ext": ".avi", "vcodec": "mpeg4",    "acodec": "mp3"},
    "MKV (H.264)": {"ext": ".mkv", "vcodec": "libx264",  "acodec": "aac"},
    "WebM (VP9)":  {"ext": ".webm", "vcodec": "libvpx-vp9", "acodec": "libopus"},
}


def get_input_filter() -> str:
    """Return a file-dialog filter string for supported input formats."""
    exts = " ".join(f"*{e}" for e in sorted(INPUT_EXTENSIONS))
    return f"Video Files ({exts});;All Files (*.*)"
