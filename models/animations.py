"""Animation definitions for subtitle rendering."""

from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Optional
from models.subtitle import SubtitleSegment


class AnimationType(Enum):
    NONE = "none"
    FADE = "fade"
    SLIDE_UP = "slide_up"
    SLIDE_DOWN = "slide_down"
    TYPEWRITER = "typewriter"
    KARAOKE = "karaoke"
    POP = "pop"


ANIMATION_LABELS = {
    AnimationType.NONE: "None",
    AnimationType.FADE: "Fade In/Out",
    AnimationType.SLIDE_UP: "Slide Up",
    AnimationType.SLIDE_DOWN: "Slide Down",
    AnimationType.TYPEWRITER: "Typewriter",
    AnimationType.KARAOKE: "Karaoke Highlight",
    AnimationType.POP: "Pop / Scale",
}


@dataclass
class AnimationState:
    """Current visual state produced by an animation at a given time."""
    opacity: float = 1.0           # 0.0–1.0
    offset_x: float = 0.0         # pixel offset
    offset_y: float = 0.0         # pixel offset
    scale: float = 1.0            # 1.0 = normal
    visible_char_count: int = -1  # -1 = show all chars (typewriter)
    highlight_word_index: int = -1  # -1 = no highlight (karaoke)


def _ease_in_out(t: float) -> float:
    """Smooth ease-in-out curve (0→1)."""
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def compute_animation_state(
    anim_type: AnimationType,
    segment: SubtitleSegment,
    current_time: float,
    anim_duration: float = 0.3,
    frame_height: float = 1080.0,
) -> AnimationState:
    """Compute the animation state for a subtitle segment at the given time.

    Args:
        anim_type: Which animation to apply.
        segment: The subtitle segment being rendered.
        current_time: Current playback time in seconds.
        anim_duration: Duration of the intro/outro animation in seconds.
        frame_height: Video frame height (used for slide offset calculations).

    Returns:
        AnimationState describing how to render the segment.
    """
    state = AnimationState()

    seg_start = segment.start_time
    seg_end = segment.end_time
    seg_duration = seg_end - seg_start

    if current_time < seg_start or current_time > seg_end:
        state.opacity = 0.0
        return state

    # Progress within the segment (0→1)
    progress = (current_time - seg_start) / seg_duration if seg_duration > 0 else 1.0

    # Time since segment start / before segment end
    time_in = current_time - seg_start
    time_out = seg_end - current_time

    if anim_type == AnimationType.NONE:
        pass  # defaults are fine

    elif anim_type == AnimationType.FADE:
        if time_in < anim_duration:
            state.opacity = _ease_in_out(time_in / anim_duration)
        elif time_out < anim_duration:
            state.opacity = _ease_in_out(time_out / anim_duration)

    elif anim_type == AnimationType.SLIDE_UP:
        slide_dist = frame_height * 0.05
        if time_in < anim_duration:
            t = _ease_in_out(time_in / anim_duration)
            state.offset_y = slide_dist * (1 - t)
            state.opacity = t
        elif time_out < anim_duration:
            t = _ease_in_out(time_out / anim_duration)
            state.offset_y = -slide_dist * (1 - t)
            state.opacity = t

    elif anim_type == AnimationType.SLIDE_DOWN:
        slide_dist = frame_height * 0.05
        if time_in < anim_duration:
            t = _ease_in_out(time_in / anim_duration)
            state.offset_y = -slide_dist * (1 - t)
            state.opacity = t
        elif time_out < anim_duration:
            t = _ease_in_out(time_out / anim_duration)
            state.offset_y = slide_dist * (1 - t)
            state.opacity = t

    elif anim_type == AnimationType.TYPEWRITER:
        total_chars = len(segment.text)
        if total_chars > 0:
            # Reveal characters linearly over the segment duration
            # leaving last 20% for full display
            reveal_progress = min(progress / 0.8, 1.0)
            state.visible_char_count = int(reveal_progress * total_chars)

    elif anim_type == AnimationType.KARAOKE:
        # Highlight the word that is currently being spoken
        for i, w in enumerate(segment.words):
            if w.start_time <= current_time <= w.end_time:
                state.highlight_word_index = i
                break

    elif anim_type == AnimationType.POP:
        if time_in < anim_duration:
            t = _ease_in_out(time_in / anim_duration)
            state.scale = 0.5 + 0.5 * t  # scale from 0.5 → 1.0
            state.opacity = t
        elif time_out < anim_duration:
            t = _ease_in_out(time_out / anim_duration)
            state.scale = 0.5 + 0.5 * t
            state.opacity = t

    return state
