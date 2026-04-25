"""Animation definitions for subtitle rendering."""

from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Optional
from models.subtitle import SubtitleSegment, StyledWord


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


@dataclass
class WordAnimationState:
    """Current visual state for a single word's animation."""
    opacity: float = 1.0
    offset_x: float = 0.0
    offset_y: float = 0.0
    scale: float = 1.0
    visible: bool = True          # False = word not yet revealed (typewriter)
    is_highlighted: bool = False  # True = currently active word (karaoke)


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
    """Compute the LINE animation state for a subtitle segment at the given time.

    This handles per-line animations: how the entire segment block
    appears and disappears as a whole.

    Args:
        anim_type: Which line animation to apply.
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

    elif anim_type == AnimationType.POP:
        if time_in < anim_duration:
            t = _ease_in_out(time_in / anim_duration)
            state.scale = 0.5 + 0.5 * t  # scale from 0.5 → 1.0
            state.opacity = t
        elif time_out < anim_duration:
            t = _ease_in_out(time_out / anim_duration)
            state.scale = 0.5 + 0.5 * t
            state.opacity = t

    # Typewriter and Karaoke are word-level now — they don't affect line state
    # but we keep them here for backwards compat with old projects
    elif anim_type == AnimationType.TYPEWRITER:
        total_chars = len(segment.text)
        if total_chars > 0:
            reveal_progress = min(progress / 0.8, 1.0)
            state.visible_char_count = int(reveal_progress * total_chars)

    elif anim_type == AnimationType.KARAOKE:
        for i, w in enumerate(segment.words):
            if w.start_time <= current_time <= w.end_time:
                state.highlight_word_index = i
                break

    return state


def compute_word_animation_state(
    anim_type: AnimationType,
    word: StyledWord,
    current_time: float,
    anim_duration: float = 0.3,
    frame_height: float = 1080.0,
) -> WordAnimationState:
    """Compute the per-WORD animation state at the given time.

    Per-word animations animate each word sequentially based on
    the word's own start_time / end_time.

    Args:
        anim_type: Which word animation to apply.
        word: The word being rendered.
        current_time: Current playback time in seconds.
        anim_duration: Duration of the word's intro animation in seconds.
        frame_height: Video frame height.

    Returns:
        WordAnimationState for this specific word.
    """
    state = WordAnimationState()

    if anim_type == AnimationType.NONE:
        return state

    w_start = word.start_time
    w_end = word.end_time
    time_since_start = current_time - w_start

    if anim_type == AnimationType.TYPEWRITER:
        # Word is invisible until its start_time
        if current_time < w_start:
            state.visible = False
            state.opacity = 0.0
        else:
            state.visible = True
            state.opacity = 1.0
        return state

    if anim_type == AnimationType.KARAOKE:
        # All words are visible; the current word is highlighted
        state.visible = True
        state.is_highlighted = (w_start <= current_time <= w_end)
        state.opacity = 1.0
        return state

    # For all other animation types, word animates in at its start_time
    if current_time < w_start:
        # Word hasn't appeared yet
        state.opacity = 0.0
        state.visible = False
        if anim_type == AnimationType.SLIDE_UP:
            state.offset_y = frame_height * 0.03
        elif anim_type == AnimationType.SLIDE_DOWN:
            state.offset_y = -frame_height * 0.03
        elif anim_type == AnimationType.POP:
            state.scale = 0.5
        return state

    # Word is appearing or fully visible
    state.visible = True

    if time_since_start < anim_duration:
        t = _ease_in_out(time_since_start / anim_duration)

        if anim_type == AnimationType.FADE:
            state.opacity = t

        elif anim_type == AnimationType.SLIDE_UP:
            slide_dist = frame_height * 0.03
            state.offset_y = slide_dist * (1 - t)
            state.opacity = t

        elif anim_type == AnimationType.SLIDE_DOWN:
            slide_dist = frame_height * 0.03
            state.offset_y = -slide_dist * (1 - t)
            state.opacity = t

        elif anim_type == AnimationType.POP:
            state.scale = 0.5 + 0.5 * t
            state.opacity = t

    # After anim_duration: fully visible, defaults are fine
    return state
