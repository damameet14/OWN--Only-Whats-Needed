import os
import subprocess
import sys

from server.config import get_ffmpeg_path

def generate_timeline_assets(video_path: str, duration: float, thumbnail_path: str):
    """Generate both a spritesheet and a waveform for the timeline.
    
    The outputs are saved in the same directory as the thumbnail,
    using the thumbnail's base name.
    """
    if not thumbnail_path or not video_path or duration <= 0:
        return

    base_path = os.path.splitext(thumbnail_path)[0]
    sprite_path = f"{base_path}_sprite.jpg"
    waveform_path = f"{base_path}_waveform.png"
    
    # 1. Generate video spritesheet
    # Extract 100 frames total across the entire duration
    # We tile them 100x1, each frame is 160 pixels wide.
    fps_cmd = f"fps=100/{duration}"
    sprite_cmd = [
        get_ffmpeg_path(), "-y", "-v", "error",
        "-i", video_path,
        "-vf", f"{fps_cmd},scale=160:-1,tile=100x1",
        "-frames:v", "1",
        sprite_path
    ]
    subprocess.run(
        sprite_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000),
    )

    # 2. Generate audio waveform
    # Extract audio waveform image (2000x200, green color)
    waveform_cmd = [
        get_ffmpeg_path(), "-y", "-v", "error",
        "-i", video_path,
        "-filter_complex", "showwavespic=s=2000x200:colors=#5a783a",
        "-frames:v", "1",
        waveform_path
    ]
    subprocess.run(
        waveform_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000),
    )

    return sprite_path, waveform_path
