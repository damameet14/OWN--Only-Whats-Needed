"""Transliteration engine — convert Indian scripts to Roman (ITRANS).

Uses the `indic-transliteration` library (pure Python, no ML model)
so it bundles cleanly into a PyInstaller executable.
"""

from __future__ import annotations

import re
from typing import Optional

from indic_transliteration import sanscript
from indic_transliteration.sanscript import transliterate


# ── Script detection via Unicode block ranges ─────────────────────────────────

# Map of (start, end) Unicode code-point ranges → sanscript scheme constant
_SCRIPT_RANGES: list[tuple[int, int, str]] = [
    (0x0900, 0x097F, sanscript.DEVANAGARI),   # Hindi, Marathi, Sanskrit, Nepali
    (0x0980, 0x09FF, sanscript.BENGALI),       # Bengali, Assamese
    (0x0A00, 0x0A7F, sanscript.GURMUKHI),      # Punjabi
    (0x0A80, 0x0AFF, sanscript.GUJARATI),       # Gujarati
    (0x0B00, 0x0B7F, sanscript.ORIYA),          # Odia
    (0x0B80, 0x0BFF, sanscript.TAMIL),          # Tamil
    (0x0C00, 0x0C7F, sanscript.TELUGU),         # Telugu
    (0x0C80, 0x0CFF, sanscript.KANNADA),        # Kannada
    (0x0D00, 0x0D7F, sanscript.MALAYALAM),      # Malayalam
]


def detect_script(text: str) -> Optional[str]:
    """Detect the dominant Indic script in *text*.

    Returns the `sanscript` scheme constant (e.g. ``sanscript.DEVANAGARI``)
    or ``None`` if no Indic characters are found.
    """
    votes: dict[str, int] = {}
    for ch in text:
        cp = ord(ch)
        for start, end, scheme in _SCRIPT_RANGES:
            if start <= cp <= end:
                votes[scheme] = votes.get(scheme, 0) + 1
                break
    if not votes:
        return None
    return max(votes, key=votes.get)


def is_indic(text: str) -> bool:
    """Return True if *text* contains at least one Indic character."""
    return detect_script(text) is not None


# ── Core transliteration ─────────────────────────────────────────────────────

def transliterate_word(word: str, source_script: Optional[str] = None) -> str:
    """Transliterate a single word from an Indian script to ITRANS (Roman).

    If *source_script* is ``None``, the script is auto-detected.
    Non-Indic words (already Roman, numbers, punctuation) are returned as-is.

    Parameters
    ----------
    word : str
        The word to transliterate.
    source_script : str, optional
        A ``sanscript`` scheme constant.  Auto-detected when omitted.

    Returns
    -------
    str
        The Roman (ITRANS) transliteration, or the original word if no Indic
        characters are found.
    """
    if not word or not word.strip():
        return word

    # Separate leading/trailing punctuation so transliteration is clean
    leading, core, trailing = _split_punctuation(word)

    if not core:
        return word

    script = source_script or detect_script(core)
    if script is None:
        # Already Roman / numeric — return unchanged
        return word

    roman = transliterate(core, script, sanscript.ITRANS)
    return f"{leading}{roman}{trailing}"


def transliterate_words(
    words: list[dict],
    indices: list[int] | str = "all",
    source_script: Optional[str] = None,
) -> list[dict]:
    """Transliterate selected words from a word-list.

    Parameters
    ----------
    words : list[dict]
        Each dict must have a ``"word"`` key.  Additional keys are passed through.
    indices : list[int] | ``"all"``
        Which word indices to transliterate.  ``"all"`` means every word.
    source_script : str, optional
        Force a specific source script; auto-detected per word when omitted.

    Returns
    -------
    list[dict]
        One entry per transliterated word: ``{"index", "original", "roman"}``.
    """
    if indices == "all":
        indices = list(range(len(words)))

    results = []
    for idx in indices:
        if idx < 0 or idx >= len(words):
            continue
        original = words[idx].get("word", "")
        roman = transliterate_word(original, source_script)
        results.append({
            "index": idx,
            "original": original,
            "roman": roman,
        })
    return results


# ── Helpers ───────────────────────────────────────────────────────────────────

# Regex to strip leading/trailing ASCII punctuation while keeping the core word
# We only strip ASCII punctuation to avoid stripping Indic combining marks (matras)
_PUNCT_RE = re.compile(
    r'^([\x00-\x2F\x3A-\x40\x5B-\x60\x7B-\x7F]*)'   # leading ASCII punctuation
    r'(.*?)'                                            # core word (non-greedy)
    r'([\x00-\x2F\x3A-\x40\x5B-\x60\x7B-\x7F]*)$',   # trailing ASCII punctuation
    re.UNICODE,
)


def _split_punctuation(text: str) -> tuple[str, str, str]:
    """Split *text* into (leading_punct, core, trailing_punct)."""
    m = _PUNCT_RE.match(text)
    if m:
        return m.group(1), m.group(2), m.group(3)
    return "", text, ""
