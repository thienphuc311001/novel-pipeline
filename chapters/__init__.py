"""Chapter detection, numeral conversion, header normalization, dedupe."""

from .numerals import chinese_to_int, parse_number_token
from .patterns import ChapterPattern, build_patterns, validate_custom_regex
from .detector import ChapterHit, detect_chapters, detect_headers_in_text
from .duplicates import DuplicateReport, resolve_duplicates
from .normalizer import NormalizeOptions, normalize_chapters

__all__ = [
    "chinese_to_int",
    "parse_number_token",
    "ChapterPattern",
    "build_patterns",
    "validate_custom_regex",
    "ChapterHit",
    "detect_chapters",
    "detect_headers_in_text",
    "DuplicateReport",
    "resolve_duplicates",
    "NormalizeOptions",
    "normalize_chapters",
]
