"""Video utility helpers using FFmpeg."""

from __future__ import annotations
import json
import subprocess
import sys
from dataclasses import dataclass

from server.config import get_ffprobe_path


@dataclass
class VideoInfo:
    """Metadata about a video file."""
    duration: float       # seconds
    width: int            # effective displayed width (rotation-aware)
    height: int           # effective displayed height (rotation-aware)
    fps: float
    codec: str
    audio_codec: str
    file_path: str
    rotation: int = 0     # rotation angle in degrees (0, 90, 180, 270)

    @property
    def resolution(self) -> str:
        return f"{self.width}×{self.height}"

    @property
    def is_portrait(self) -> bool:
        return self.height > self.width


def _detect_rotation(video_stream: dict) -> int:
    """Detect rotation from ffprobe stream data.

    Checks:
    1. side_data_list → displaymatrix → rotation
    2. tags → rotate
    Returns normalised angle: 0, 90, 180, or 270.
    """
    rotation = 0

    # Method 1: side_data_list (modern containers)
    side_data = video_stream.get("side_data_list", [])
    for sd in side_data:
        if "rotation" in sd:
            rotation = int(float(sd["rotation"]))
            break
        if sd.get("side_data_type") == "Display Matrix":
            rotation = int(float(sd.get("rotation", 0)))
            break

    # Method 2: tags.rotate (older containers / MOV)
    if rotation == 0:
        tags = video_stream.get("tags", {})
        rotate_tag = tags.get("rotate", tags.get("ROTATE", "0"))
        try:
            rotation = int(float(rotate_tag))
        except (ValueError, TypeError):
            rotation = 0

    # Normalise to 0/90/180/270
    rotation = rotation % 360
    if rotation < 0:
        rotation += 360
    if rotation not in (0, 90, 180, 270):
        rotation = round(rotation / 90) * 90 % 360

    return rotation


def get_video_info(path: str) -> VideoInfo:
    """Probe a video file and return its metadata.

    The returned width/height reflect the effective displayed dimensions,
    i.e. after applying any rotation metadata.
    """
    cmd = [
        get_ffprobe_path(),
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        "-show_entries", "stream=width,height,codec_type,codec_name,r_frame_rate,side_data_list,tags",
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

    coded_width = int(video_stream.get("width", 0))
    coded_height = int(video_stream.get("height", 0))
    codec = video_stream.get("codec_name", "unknown")

    # Detect rotation from metadata
    rotation = _detect_rotation(video_stream)

    # Swap dimensions for 90°/270° rotation because FFmpeg's decoder
    # auto-rotates the raw frame output to match the display orientation.
    if rotation in (90, 270):
        width, height = coded_height, coded_width
    else:
        width, height = coded_width, coded_height

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
        rotation=rotation,
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
