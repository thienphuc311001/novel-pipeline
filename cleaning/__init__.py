"""Text cleaning, encoding detection and JSON unwrapping helpers."""

from .encodings import EncodingResult, decode_bytes, detect_encoding
from .json_artifacts import JSONUnwrapResult, looks_like_json, unwrap_json_text
from .textclean import (
    CleaningOptions,
    CleanReport,
    clean_text,
    enforce_sentence_endings,
    normalize_spacing,
    restore_escaped_newlines,
)

__all__ = [
    "EncodingResult",
    "decode_bytes",
    "detect_encoding",
    "JSONUnwrapResult",
    "looks_like_json",
    "unwrap_json_text",
    "CleaningOptions",
    "CleanReport",
    "clean_text",
    "enforce_sentence_endings",
    "normalize_spacing",
    "restore_escaped_newlines",
]
