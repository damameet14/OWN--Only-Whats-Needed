"""Subtitle data models — words, segments, and tracks."""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Optional
import copy
import json
import uuid


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
class MediaSegment:
    """A segment of a video or audio track on the timeline."""
    start: float         # Start time on the timeline
    end: float           # End time on the timeline
    source_start: float  # Start time in the original media
    source_end: float    # End time in the original media

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> MediaSegment:
        return cls(**d)


@dataclass
class SubtitleStyle:
    """Visual style for subtitle text."""
    # ── Font ──────────────────────────────────────────────────────────────
    font_family: str = "Noto Sans Devanagari"
    font_size: int = 48
    font_weight: int = 400          # 100–900 (400=normal, 700=bold)
    font_style: str = "normal"      # normal / italic / oblique
    text_transform: str = "none"    # none / uppercase / lowercase / capitalize

    # ── Fill ──────────────────────────────────────────────────────────────
    fill_type: str = "solid"        # solid / gradient
    text_color: str = "#FFFFFF"     # solid fill color
    gradient_color1: str = "#FFFFFF"
    gradient_color2: str = "#FFD700"
    gradient_angle: int = 0         # degrees (0 = left-to-right)
    gradient_type: str = "linear"   # linear / radial

    # ── Stroke ────────────────────────────────────────────────────────────
    stroke_enabled: bool = True
    outline_color: str = "#000000"
    outline_width: int = 2

    # ── Shadow ────────────────────────────────────────────────────────────
    shadow_enabled: bool = True
    shadow_color: str = "#80000000"
    shadow_blur: int = 0            # blur radius (px)
    shadow_offset_x: int = 2
    shadow_offset_y: int = 2

    # ── Spacing ───────────────────────────────────────────────────────────
    letter_spacing: float = 0       # px
    word_spacing: float = 0         # px
    line_height: float = 1.2        # multiplier

    # ── Opacity ───────────────────────────────────────────────────────────
    text_opacity: float = 1.0       # 0.0–1.0

    # ── Legacy / Layout ───────────────────────────────────────────────────
    bg_color: str = ""              # empty = no background
    bg_padding: int = 8
    alignment: str = "center"       # left / center / right
    rotation: int = 0               # angle in degrees

    def copy(self) -> SubtitleStyle:
        return copy.deepcopy(self)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> SubtitleStyle:
        data = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        # Backwards compatibility: map legacy bold/italic to new fields
        if "bold" in d and "font_weight" not in d:
            data["font_weight"] = 700 if d["bold"] else 400
        if "italic" in d and "font_style" not in d:
            data["font_style"] = "italic" if d["italic"] else "normal"
        # Legacy: shadow_color presence implied shadow_enabled
        if "shadow_enabled" not in d and "shadow_color" in d:
            data["shadow_enabled"] = bool(d["shadow_color"])
        # Legacy: outline presence implied stroke_enabled
        if "stroke_enabled" not in d and "outline_color" in d:
            data["stroke_enabled"] = bool(d["outline_color"]) and d.get("outline_width", 0) > 0
        return cls(**data)


@dataclass
class SpecialGroup:
    """A group of special words with shared styling."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    style: SubtitleStyle = field(default_factory=SubtitleStyle)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "style": self.style.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> SpecialGroup:
        return cls(
            id=d.get("id", str(uuid.uuid4())),
            name=d.get("name", ""),
            style=SubtitleStyle.from_dict(d.get("style", {})),
        )


@dataclass
class StyledWord:
    """A word with timing and optional per-word style override."""
    word: str
    start_time: float
    end_time: float
    confidence: float = 1.0
    style_override: Optional[SubtitleStyle] = None   # None = use segment style
    is_special: bool = False                         # Marked as special
    group_id: Optional[str] = None                   # Group ID if part of a group

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
            "is_special": self.is_special,
        }
        if self.group_id:
            d["group_id"] = self.group_id
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
            is_special=d.get("is_special", False),
            group_id=d.get("group_id"),
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
    video_segments: list[MediaSegment] = field(default_factory=list)
    audio_segments: list[MediaSegment] = field(default_factory=list)
    global_style: SubtitleStyle = field(default_factory=SubtitleStyle)
    special_groups: dict[str, SpecialGroup] = field(default_factory=dict)  # group_id -> SpecialGroup
    words_per_line: int = 4
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

    def get_group_style(self, group_id: str) -> Optional[SubtitleStyle]:
        """Get the style for a group by ID."""
        group = self.special_groups.get(group_id)
        return group.style if group else None

    def create_group(self, name: str = "") -> str:
        """Create a new group and return its ID."""
        group_id = str(uuid.uuid4())
        self.special_groups[group_id] = SpecialGroup(id=group_id, name=name, style=self.global_style.copy())
        return group_id

    def delete_group(self, group_id: str) -> None:
        """Delete a group and remove all words from it."""
        if group_id in self.special_groups:
            del self.special_groups[group_id]
            # Remove group_id from all words
            for seg in self.segments:
                for word in seg.words:
                    if word.group_id == group_id:
                        word.group_id = None
                        word.is_special = False

    def get_group_members(self, group_id: str) -> list[tuple[int, int]]:
        """Get all (segment_index, word_index) pairs for words in a group."""
        members = []
        for seg_idx, seg in enumerate(self.segments):
            for word_idx, word in enumerate(seg.words):
                if word.group_id == group_id:
                    members.append((seg_idx, word_idx))
        return members

    def to_dict(self) -> dict:
        return {
            "segments": [s.to_dict() for s in self.segments],
            "video_segments": [s.to_dict() for s in self.video_segments],
            "audio_segments": [s.to_dict() for s in self.audio_segments],
            "global_style": self.global_style.to_dict(),
            "special_groups": {gid: g.to_dict() for gid, g in self.special_groups.items()},
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
        video_segments = [MediaSegment.from_dict(s) for s in d.get("video_segments", [])]
        audio_segments = [MediaSegment.from_dict(s) for s in d.get("audio_segments", [])]
        global_style = SubtitleStyle.from_dict(d.get("global_style", {}))

        special_groups = {}
        for gid, g_data in d.get("special_groups", {}).items():
            special_groups[gid] = SpecialGroup.from_dict(g_data)

        return cls(
            segments=segments,
            video_segments=video_segments,
            audio_segments=audio_segments,
            global_style=global_style,
            special_groups=special_groups,
            words_per_line=d.get("words_per_line", 4),
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
