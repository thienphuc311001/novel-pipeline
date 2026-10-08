"""Validate edits identically for local HTTP and desktop settings controls."""
from __future__ import annotations

import codecs

from chapters.patterns import validate_custom_regex
from config.settings import Settings

# The desktop spin boxes expose these same ranges.
INTEGER_RANGES = {
    "zero_pad": (0, 12), "min_chunk_chars": (50, 20000), "max_chunk_chars": (50, 20000),
    "tts_max_concurrency": (1, 100), "tts_timeout_seconds": (10, 600), "tts_retry_count": (1, 10),
    "thumbnail_jpeg_quality": (70, 100), "font_size": (7, 32), "max_log_lines": (100, 100000),
}


def validate_settings(data: dict) -> Settings:
    defaults = Settings().to_dict()
    unknown = set(data) - set(defaults)
    if unknown:
        raise ValueError("Unknown settings: " + ", ".join(sorted(unknown)))
    values = {**defaults, **data}
    for name, value in values.items():
        if type(value) is not type(defaults[name]):
            raise ValueError(f"Invalid type for setting: {name}")
    for name, (minimum, maximum) in INTEGER_RANGES.items():
        if not minimum <= values[name] <= maximum:
            raise ValueError(f"{name} must be between {minimum} and {maximum}.")
    if not values["encoding_chain"]:
        raise ValueError("Encoding fallback order cannot be empty.")
    for encoding in values["encoding_chain"]:
        try:
            codecs.lookup(encoding)
        except (LookupError, TypeError) as error:
            raise ValueError(f"Unknown encoding: {encoding}") from error
    if any(not isinstance(pair, str) or len(pair) != 2 for pair in values["bracket_pairs"]):
        raise ValueError("Every bracket pair must contain exactly two characters.")
    if not all(isinstance(rule, dict) for rule in values["custom_rules"]):
        raise ValueError("Custom rules must be a JSON list of objects.")
    if not all(isinstance(key, str) and isinstance(value, str) for key, value in values["symbol_map"].items()):
        raise ValueError("Symbol replacements must map text to text.")
    if values["min_chunk_chars"] > values["max_chunk_chars"]:
        raise ValueError("Minimum chunk size cannot exceed maximum chunk size.")
    voice = values["tts_voice"].strip()
    if not voice:
        raise ValueError("TTS voice cannot be empty (for example: vi-VN-HoaiMyNeural).")
    if values["quote_mode"] not in {"keep", "strip", "remove"} or values["bracket_mode"] not in {"keep", "strip", "remove"}:
        raise ValueError("Quote/bracket mode must be keep, strip or remove.")
    if values["use_custom_chapter_regex"]:
        validate_custom_regex(values["custom_chapter_regex"])
    from cleaning.tts_text_preprocessor import TTSPreprocessConfig
    try:
        TTSPreprocessConfig(**values["tts_preprocessing"])
    except TypeError as error:
        raise ValueError(f"Invalid TTS preprocessing options: {error}") from error
    settings = Settings.from_dict(values)
    settings.tts_voice = voice
    return settings
