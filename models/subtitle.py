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
class StyledWord:
    """A word with timing and optional per-word style override.
    
    marker: 'standard' | 'highlight' | 'spotlight'
        Determines which style pool this word draws from.
        'standard'  → segment/global style
        'highlight' → track.highlight_style (or style_override if apply-all=false)
        'spotlight' → track.spotlight_style (or style_override if apply-all=false)
    style_override: individual per-word style (used when apply-all=false for highlight/spotlight)
    position_preset: optional 3×3 grid position for this word (e.g. 'top-center')
    word_animation_type: optional per-word animation override
    word_animation_duration: optional per-word animation duration override
    """
    word: str
    start_time: float
    end_time: float
    confidence: float = 1.0
    marker: str = "standard"                          # standard / highlight / spotlight
    style_override: Optional[SubtitleStyle] = None   # None = use marker's pool style
    position_preset: Optional[str] = None            # None = use segment position; e.g. 'top-center'
    word_animation_type: Optional[str] = None        # None = use segment/track word animation
    word_animation_duration: Optional[float] = None  # None = use segment/track word duration
    word_native: Optional[str] = None                # Original native-script text (set when transliterated)

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
            "marker": self.marker,
        }
        if self.style_override:
            d["style_override"] = self.style_override.to_dict()
        if self.position_preset is not None:
            d["position_preset"] = self.position_preset
        if self.word_animation_type is not None:
            d["word_animation_type"] = self.word_animation_type
        if self.word_animation_duration is not None:
            d["word_animation_duration"] = self.word_animation_duration
        if self.word_native is not None:
            d["word_native"] = self.word_native
        return d

    @classmethod
    def from_dict(cls, d: dict) -> StyledWord:
        style = None
        if d.get("style_override"):
            style = SubtitleStyle.from_dict(d["style_override"])

        # Backwards compat: old is_special=True → keep as standard (fresh start per spec)
        marker = d.get("marker", "standard")
        # Validate marker value
        if marker not in ("standard", "highlight", "spotlight"):
            marker = "standard"

        return cls(
            word=d["word"],
            start_time=d["start_time"],
            end_time=d["end_time"],
            confidence=d.get("confidence", 1.0),
            marker=marker,
            style_override=style,
            position_preset=d.get("position_preset"),
            # Backwards compat: old animation_type → word_animation_type
            word_animation_type=d.get("word_animation_type", d.get("animation_type")),
            word_animation_duration=d.get("word_animation_duration", d.get("animation_duration")),
            word_native=d.get("word_native"),
        )


@dataclass
class SubtitleSegment:
    """A group of styled words that appear together as one subtitle block.
    
    apply_for_all: when True, this segment follows global style changes.
        When False, this segment has independent style/position/animation.
    position_x/y: per-segment position overrides (None = use track position).
    line_animation_type/duration: per-segment line animation overrides (None = use track).
    word_animation_type/duration: per-segment word animation overrides (None = use track).
    """
    words: list[StyledWord] = field(default_factory=list)
    style: SubtitleStyle = field(default_factory=SubtitleStyle)
    apply_for_all: bool = True
    position_x: Optional[float] = None   # None = use track.position_x
    position_y: Optional[float] = None   # None = use track.position_y
    line_animation_type: Optional[str] = None       # None = use track.line_animation_type
    line_animation_duration: Optional[float] = None # None = use track.line_animation_duration
    word_animation_type: Optional[str] = None       # None = use track.word_animation_type
    word_animation_duration: Optional[float] = None # None = use track.word_animation_duration

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
        d = {
            "words": [w.to_dict() for w in self.words],
            "style": self.style.to_dict(),
            "apply_for_all": self.apply_for_all,
        }
        if self.position_x is not None:
            d["position_x"] = self.position_x
        if self.position_y is not None:
            d["position_y"] = self.position_y
        if self.line_animation_type is not None:
            d["line_animation_type"] = self.line_animation_type
        if self.line_animation_duration is not None:
            d["line_animation_duration"] = self.line_animation_duration
        if self.word_animation_type is not None:
            d["word_animation_type"] = self.word_animation_type
        if self.word_animation_duration is not None:
            d["word_animation_duration"] = self.word_animation_duration
        return d

    @classmethod
    def from_dict(cls, d: dict) -> SubtitleSegment:
        words = [StyledWord.from_dict(w) for w in d.get("words", [])]
        style = SubtitleStyle.from_dict(d.get("style", {}))
        return cls(
            words=words,
            style=style,
            apply_for_all=d.get("apply_for_all", True),
            position_x=d.get("position_x"),
            position_y=d.get("position_y"),
            # Backwards compat: old animation_type → line_animation_type
            line_animation_type=d.get("line_animation_type", d.get("animation_type")),
            line_animation_duration=d.get("line_animation_duration", d.get("animation_duration")),
            word_animation_type=d.get("word_animation_type"),
            word_animation_duration=d.get("word_animation_duration"),
        )


@dataclass
class SubtitleTrack:
    """Complete subtitle track for a video."""
    segments: list[SubtitleSegment] = field(default_factory=list)
    video_segments: list[MediaSegment] = field(default_factory=list)
    audio_segments: list[MediaSegment] = field(default_factory=list)
    global_style: SubtitleStyle = field(default_factory=SubtitleStyle)
    highlight_style: SubtitleStyle = field(default_factory=lambda: SubtitleStyle(
        text_color="#FFD700",
        font_weight=700,
        stroke_enabled=True,
        outline_color="#000000",
        outline_width=3,
    ))
    spotlight_style: SubtitleStyle = field(default_factory=lambda: SubtitleStyle(
        text_color="#00FFFF",
        font_weight=700,
        stroke_enabled=True,
        outline_color="#005588",
        outline_width=3,
    ))
    words_per_line: int = 4
    position_x: float = 0.5   # 0.0–1.0 normalised (0.5 = center)
    position_y: float = 0.9   # 0.0–1.0 normalised (0.9 = near bottom)
    text_box_width: float = 0.8  # 0.0–1.0 — fraction of video width for text wrapping
    line_animation_type: str = "none"
    line_animation_duration: float = 0.3  # seconds
    word_animation_type: str = "none"
    word_animation_duration: float = 0.3  # seconds
    video_rotation: int = 0  # angle in degrees
    sentence_mode: bool = False  # if True, segments are defined by \n in full text
    is_transliterated: bool = False  # True when any words have been transliterated

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

    def get_word_effective_style(self, word: StyledWord) -> SubtitleStyle:
        """Resolve the effective style for a word based on its marker."""
        if word.style_override is not None:
            return word.style_override
        if word.marker == "highlight":
            return self.highlight_style
        if word.marker == "spotlight":
            return self.spotlight_style
        # Standard — caller should use segment style
        return None

    def to_dict(self) -> dict:
        return {
            "segments": [s.to_dict() for s in self.segments],
            "video_segments": [s.to_dict() for s in self.video_segments],
            "audio_segments": [s.to_dict() for s in self.audio_segments],
            "global_style": self.global_style.to_dict(),
            "highlight_style": self.highlight_style.to_dict(),
            "spotlight_style": self.spotlight_style.to_dict(),
            "words_per_line": self.words_per_line,
            "position_x": self.position_x,
            "position_y": self.position_y,
            "text_box_width": self.text_box_width,
            "line_animation_type": self.line_animation_type,
            "line_animation_duration": self.line_animation_duration,
            "word_animation_type": self.word_animation_type,
            "word_animation_duration": self.word_animation_duration,
            "video_rotation": self.video_rotation,
            "sentence_mode": self.sentence_mode,
            "is_transliterated": self.is_transliterated,
        }

    @classmethod
    def from_dict(cls, d: dict) -> SubtitleTrack:
        segments = [SubtitleSegment.from_dict(s) for s in d.get("segments", [])]
        video_segments = [MediaSegment.from_dict(s) for s in d.get("video_segments", [])]
        audio_segments = [MediaSegment.from_dict(s) for s in d.get("audio_segments", [])]
        global_style = SubtitleStyle.from_dict(d.get("global_style", {}))
        highlight_style = SubtitleStyle.from_dict(d.get("highlight_style", {
            "text_color": "#FFD700", "font_weight": 700,
            "stroke_enabled": True, "outline_color": "#000000", "outline_width": 3,
        }))
        spotlight_style = SubtitleStyle.from_dict(d.get("spotlight_style", {
            "text_color": "#00FFFF", "font_weight": 700,
            "stroke_enabled": True, "outline_color": "#005588", "outline_width": 3,
        }))

        return cls(
            segments=segments,
            video_segments=video_segments,
            audio_segments=audio_segments,
            global_style=global_style,
            highlight_style=highlight_style,
            spotlight_style=spotlight_style,
            words_per_line=d.get("words_per_line", 4),
            position_x=d.get("position_x", 0.5),
            position_y=d.get("position_y", 0.9),
            text_box_width=d.get("text_box_width", 0.8),
            # Backwards compat: old animation_type → line_animation_type
            line_animation_type=d.get("line_animation_type", d.get("animation_type", "none")),
            line_animation_duration=d.get("line_animation_duration", d.get("animation_duration", 0.3)),
            word_animation_type=d.get("word_animation_type", "none"),
            word_animation_duration=d.get("word_animation_duration", 0.3),
            video_rotation=d.get("video_rotation", 0),
            sentence_mode=d.get("sentence_mode", False),
            is_transliterated=d.get("is_transliterated", False),
        )

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_json(cls, s: str) -> SubtitleTrack:
        """Deserialize from JSON string."""
        return cls.from_dict(json.loads(s))
