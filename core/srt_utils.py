"""SRT subtitle generation and parsing."""

from __future__ import annotations
from models.subtitle import SubtitleSegment, SubtitleTrack


def _format_timestamp(seconds: float) -> str:
    """Convert seconds to SRT timestamp format: HH:MM:SS,mmm"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds - int(seconds)) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def generate_srt(track: SubtitleTrack) -> str:
    """Generate SRT content from a SubtitleTrack."""
    lines: list[str] = []
    for idx, seg in enumerate(track.segments, start=1):
        if not seg.words:
            continue
        start = _format_timestamp(seg.start_time)
        end = _format_timestamp(seg.end_time)
        text = seg.text
        lines.append(f"{idx}")
        lines.append(f"{start} --> {end}")
        lines.append(text)
        lines.append("")  # blank line separator
    return "\n".join(lines)


def save_srt(track: SubtitleTrack, path: str) -> None:
    """Save subtitle track as an SRT file."""
    content = generate_srt(track)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def parse_srt(text: str) -> list[dict]:
    """Parse SRT text into a list of dicts with index, start, end, text.

    Returns:
        List of dicts: {"index": int, "start": float, "end": float, "text": str}
    """
    entries: list[dict] = []
    blocks = text.strip().split("\n\n")
    for block in blocks:
        lines = block.strip().split("\n")
        if len(lines) < 3:
            continue
        index = int(lines[0].strip())
        time_line = lines[1].strip()
        start_str, end_str = time_line.split(" --> ")
        start = _parse_timestamp(start_str.strip())
        end = _parse_timestamp(end_str.strip())
        subtitle_text = "\n".join(lines[2:])
        entries.append({
            "index": index,
            "start": start,
            "end": end,
            "text": subtitle_text,
        })
    return entries


def _parse_timestamp(ts: str) -> float:
    """Parse SRT timestamp HH:MM:SS,mmm → seconds."""
    ts = ts.replace(",", ".")
    parts = ts.split(":")
    hours = float(parts[0])
    minutes = float(parts[1])
    secs = float(parts[2])
    return hours * 3600 + minutes * 60 + secs
