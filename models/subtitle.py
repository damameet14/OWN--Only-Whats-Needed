"""Subtitle data models — words, segments, and tracks."""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Optional
import copy
import json


@dataclass
class WordTiming:
    """A single recognised word with its time span."""
    word: str
    start_time: float  # seconds
    end_time: float    # seconds
    confidence: float = 1.0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> WordTiming:
        return cls(**d)


@dataclass
class SubtitleStyle:
    """Visual style for subtitle text."""
    font_family: str = "Noto Sans Devanagari"
    font_size: int = 48
    text_color: str = "#FFFFFF"
    outline_color: str = "#000000"
    outline_width: int = 2
    shadow_color: str = "#80000000"
    shadow_offset_x: int = 2
    shadow_offset_y: int = 2
    bg_color: str = ""           # empty = no background
    bg_padding: int = 8
    bold: bool = False
    italic: bool = False
    alignment: str = "center"    # left / center / right
    rotation: int = 0            # angle in degrees

    def copy(self) -> SubtitleStyle:
        return copy.deepcopy(self)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> SubtitleStyle:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class StyledWord:
    """A word with timing and optional per-word style override."""
    word: str
    start_time: float
    end_time: float
    confidence: float = 1.0
    style_override: Optional[SubtitleStyle] = None   # None = use segment style

    @classmethod
    def from_word_timing(cls, wt: WordTiming) -> StyledWord:
        return cls(
            word=wt.word,
            start_time=wt.start_time,
            end_time=wt.end_time,
            confidence=wt.confidence,
        )

    def to_dict(self) -> dict:
        d = {
            "word": self.word,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "confidence": self.confidence,
        }
        if self.style_override:
            d["style_override"] = self.style_override.to_dict()
        return d

    @classmethod
    def from_dict(cls, d: dict) -> StyledWord:
        style = None
        if d.get("style_override"):
            style = SubtitleStyle.from_dict(d["style_override"])
        return cls(
            word=d["word"],
            start_time=d["start_time"],
            end_time=d["end_time"],
            confidence=d.get("confidence", 1.0),
            style_override=style,
        )


@dataclass
class SubtitleSegment:
    """A group of styled words that appear together as one subtitle block."""
    words: list[StyledWord] = field(default_factory=list)
    style: SubtitleStyle = field(default_factory=SubtitleStyle)

    @property
    def start_time(self) -> float:
        return self.words[0].start_time if self.words else 0.0

    @property
    def end_time(self) -> float:
        return self.words[-1].end_time if self.words else 0.0

    @property
    def text(self) -> str:
        return " ".join(w.word for w in self.words)

    def to_dict(self) -> dict:
        return {
            "words": [w.to_dict() for w in self.words],
            "style": self.style.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> SubtitleSegment:
        words = [StyledWord.from_dict(w) for w in d.get("words", [])]
        style = SubtitleStyle.from_dict(d.get("style", {}))
        return cls(words=words, style=style)


@dataclass
class SubtitleTrack:
    """Complete subtitle track for a video."""
    segments: list[SubtitleSegment] = field(default_factory=list)
    global_style: SubtitleStyle = field(default_factory=SubtitleStyle)
    words_per_line: int = 5
    position_x: float = 0.5   # 0.0–1.0 normalised (0.5 = center)
    position_y: float = 0.9   # 0.0–1.0 normalised (0.9 = near bottom)
    animation_type: str = "none"
    animation_duration: float = 0.3  # seconds
    video_rotation: int = 0  # angle in degrees

    def segment_at(self, time_sec: float) -> Optional[SubtitleSegment]:
        """Return the segment visible at the given timestamp."""
        for seg in self.segments:
            if seg.start_time <= time_sec <= seg.end_time:
                return seg
        return None

    def rebuild_segments(self, word_timings: list[WordTiming]) -> None:
        """Re-group word timings into segments based on words_per_line."""
        self.segments.clear()
        for i in range(0, len(word_timings), self.words_per_line):
            chunk = word_timings[i : i + self.words_per_line]
            styled = [StyledWord.from_word_timing(wt) for wt in chunk]
            self.segments.append(SubtitleSegment(
                words=styled,
                style=self.global_style.copy(),
            ))

    def to_dict(self) -> dict:
        return {
            "segments": [s.to_dict() for s in self.segments],
            "global_style": self.global_style.to_dict(),
            "words_per_line": self.words_per_line,
            "position_x": self.position_x,
            "position_y": self.position_y,
            "animation_type": self.animation_type,
            "animation_duration": self.animation_duration,
            "video_rotation": self.video_rotation,
        }

    @classmethod
    def from_dict(cls, d: dict) -> SubtitleTrack:
        segments = [SubtitleSegment.from_dict(s) for s in d.get("segments", [])]
        global_style = SubtitleStyle.from_dict(d.get("global_style", {}))
        return cls(
            segments=segments,
            global_style=global_style,
            words_per_line=d.get("words_per_line", 5),
            position_x=d.get("position_x", 0.5),
            position_y=d.get("position_y", 0.9),
            animation_type=d.get("animation_type", "none"),
            animation_duration=d.get("animation_duration", 0.3),
            video_rotation=d.get("video_rotation", 0),
        )

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_json(cls, s: str) -> SubtitleTrack:
        """Deserialize from JSON string."""
        return cls.from_dict(json.loads(s))
