"""Tests for core.transliterator — Indian script → Roman transliteration."""

import pytest
from core.transliterator import (
    detect_script,
    is_indic,
    transliterate_word,
    transliterate_words,
    _split_punctuation,
)
from indic_transliteration import sanscript


# ── detect_script ─────────────────────────────────────────────────────────────

def test_detect_devanagari():
    assert detect_script("नमस्ते") == sanscript.DEVANAGARI

def test_detect_tamil():
    assert detect_script("வணக்கம்") == sanscript.TAMIL

def test_detect_telugu():
    assert detect_script("నమస్కారం") == sanscript.TELUGU

def test_detect_none_for_latin():
    assert detect_script("hello") is None

def test_detect_none_for_numbers():
    assert detect_script("12345") is None


# ── is_indic ──────────────────────────────────────────────────────────────────

def test_is_indic_true():
    assert is_indic("नमस्ते") is True

def test_is_indic_false():
    assert is_indic("hello world") is False


# ── transliterate_word ────────────────────────────────────────────────────────

def test_transliterate_hindi_word():
    result = transliterate_word("नमस्ते")
    assert isinstance(result, str)
    assert len(result) > 0
    # Should be plain ASCII (ITRANS)
    assert result.isascii() or all(ord(c) < 256 for c in result)

def test_transliterate_already_roman():
    assert transliterate_word("hello") == "hello"

def test_transliterate_empty_string():
    assert transliterate_word("") == ""

def test_transliterate_whitespace():
    assert transliterate_word("  ") == "  "

def test_transliterate_preserves_leading_punctuation():
    result = transliterate_word("(नमस्ते)")
    assert result.startswith("(")
    assert result.endswith(")")

def test_transliterate_with_explicit_script():
    result = transliterate_word("नमस्ते", source_script=sanscript.DEVANAGARI)
    assert isinstance(result, str)
    assert len(result) > 0


# ── transliterate_words ──────────────────────────────────────────────────────

def test_transliterate_words_all():
    words = [
        {"word": "नमस्ते"},
        {"word": "दुनिया"},
        {"word": "hello"},
    ]
    results = transliterate_words(words, "all")
    assert len(results) == 3
    # The third word should remain unchanged (already Roman)
    assert results[2]["roman"] == "hello"
    assert results[2]["original"] == "hello"
    # The first two should be transliterated
    for r in results[:2]:
        assert r["roman"] != r["original"]

def test_transliterate_words_specific_indices():
    words = [
        {"word": "नमस्ते"},
        {"word": "दुनिया"},
        {"word": "hello"},
    ]
    results = transliterate_words(words, [0, 2])
    assert len(results) == 2
    assert results[0]["index"] == 0
    assert results[1]["index"] == 2

def test_transliterate_words_invalid_index():
    words = [{"word": "नमस्ते"}]
    results = transliterate_words(words, [0, 5, -1])
    assert len(results) == 1  # Only index 0 is valid


# ── _split_punctuation ────────────────────────────────────────────────────────

def test_split_punctuation_no_punct():
    leading, core, trailing = _split_punctuation("hello")
    assert leading == ""
    assert core == "hello"
    assert trailing == ""

def test_split_punctuation_with_brackets():
    leading, core, trailing = _split_punctuation("(hello)")
    assert leading == "("
    assert core == "hello"
    assert trailing == ")"


# ── Switch-back data model test ──────────────────────────────────────────────

def test_switch_back_roundtrip():
    """Simulate transliterate → switch-back and verify original is restored."""
    original = "नमस्ते"
    roman = transliterate_word(original)

    # Simulate data model: word becomes roman, word_native stores original
    word_data = {"word": roman, "word_native": original}

    # Switch back
    word_data["word"] = word_data["word_native"]
    word_data["word_native"] = None

    assert word_data["word"] == original
    assert word_data["word_native"] is None
