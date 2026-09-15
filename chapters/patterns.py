"""Chapter header patterns for multi-language detection.

Supports Vietnamese, English, Chinese with all variants including:
- Chinese: 第1章, 第001章, 第一章, 第十章, 第一百二十三章, 第1回, 第1节, 第1集
- Vietnamese: Chương 1, CHƯƠNG 1, Hồi 1, Tập 1, Quyển 1, Phần 1
- English: Chapter 1, Part 1, Book 1
- Decorative brackets: 【第1章】, [第1章], （第1章）, ★第1章, #第1章

Pattern precedence:
1. Vietnamese - highest priority for duplicate resolution
2. English
3. Chinese
4. Plain numbered
5. Custom regex (user-supplied)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Pattern

# Number token: supports Arabic, full-width, and Chinese numerals
NUMBER_TOKEN = (
    r"(?:[0-9０-９][0-9０-９,，]*"
    r"|[零〇洞一二两三四五六七八九十百千万亿壹贰叁肆伍陆柒捌玖拾佰仟萬億]{1,12})"
)

# Vietnamese chapter prefixes (case-insensitive)
VI_PREFIXES = (
    r"(?:Chương|Chuong|CHƯƠNG|CHUONG|Chương hồi|Hồi|Hoi|HỒI|HOI|"
    r"Quyển|Quyen|QUYỂN|QUYEN|Phần|Phan|PHẦN|PHAN|Tập|Tap|TẬP|TAP)"
)

# English chapter prefixes
EN_PREFIXES = (
    r"(?:Chapter|CHAPTER|Chap\.?|Chap|CHAP|Book|BOOK|Part|PART|"
    r"Volume|VOLUME|Vol\.?|Episode|EPISODE|Ep\.?)"
)

# Chinese units (章/節/节/回/卷/話/话/囘/集)
CN_UNITS = r"[章節节回卷話话囘集]"

# Decorative characters (brackets, stars, etc.)
DECORATIVE = r"[\s\u3000>»\-–—*#【\[（\(★\]】）\)〔〕《》〈〉「」『』]"

ARABIC_RE = re.compile(r"^[0-9]+$")


@dataclass
class ChapterPattern:
    """One named chapter header pattern."""

    name: str
    language: str
    regex: Pattern[str]
    priority: int
    strong: bool = False
    label: str = ""
    title_group: str = "title"

    def match(self, text: str) -> Optional[re.Match[str]]:
        return self.regex.match(text)

    def search(self, text: str) -> Optional[re.Match[str]]:
        return self.regex.search(text)


def _compile(pattern: str, flags: int = 0) -> Pattern[str]:
    return re.compile(pattern, flags)


# Vietnamese pattern: Chương 1, Hồi 1, Tập 1, etc.
VIETNAMESE = ChapterPattern(
    name="vietnamese",
    language="vi",
    priority=0,
    strong=True,
    label="Tiếng Việt (Chương/Hồi/Tập/Quyển/Phần)",
    regex=_compile(
        rf"^{DECORATIVE}*"
        rf"(?P<prefix>{VI_PREFIXES})"
        rf"(?:\s+|[.,:：\-–—]*\s*)*"
        rf"(?P<number>{NUMBER_TOKEN})"
        rf"(?:\s*[.:：\-–—、,，]\s*(?P<title>.*))?$",
        re.IGNORECASE,
    ),
)

# English pattern: Chapter 1, Part 1, etc.
ENGLISH = ChapterPattern(
    name="english",
    language="en",
    priority=1,
    strong=True,
    label="Tiếng Anh (Chapter/Part/Book/Volume)",
    regex=_compile(
        rf"^{DECORATIVE}*"
        rf"(?P<prefix>{EN_PREFIXES})"
        rf"(?:\s+|[.,:：\-–—]*\s*)*"
        rf"(?P<number>{NUMBER_TOKEN})"
        rf"(?:\s*[.:：\-–—、,，]\s*(?P<title>.*))?$",
        re.IGNORECASE,
    ),
)

# Chinese pattern: 第1章, 第一章, 第1回, 第1节, 第1集, etc.
CHINESE = ChapterPattern(
    name="chinese",
    language="zh",
    priority=2,
    strong=True,
    label="Tiếng Trung (第N章/回/节/集)",
    regex=_compile(
        rf"^{DECORATIVE}*"
        rf"第\s*(?P<number>{NUMBER_TOKEN})\s*{CN_UNITS}"
        rf"(?:\s*[.:：\-–—、,，]\s*(?P<title>.*?))?$"
    ),
)

# Plain numbered pattern: 12., 12:, #12, etc.
PLAIN_NUMBERED = ChapterPattern(
    name="plain",
    language="vi",
    priority=3,
    strong=False,
    label="Số đơn giản (12. / 12: / #12)",
    regex=_compile(
        rf"^{DECORATIVE}*#?\s*(?P<number>{NUMBER_TOKEN})"
        rf"\s*(?P<sep>[.:：、)]|\s-\s|\s–\s|\s—\s)\s*(?P<title>.*)$"
    ),
)

DEFAULT_PATTERNS: List[ChapterPattern] = [
    VIETNAMESE,
    ENGLISH,
    CHINESE,
    PLAIN_NUMBERED,
]


class CustomRegexError(ValueError):
    """Raised when a user supplied chapter regex is not usable."""


def validate_custom_regex(pattern: str) -> None:
    """Validate a user supplied chapter regex.

    The regex must compile and must expose a ``(?P<number>...)`` group.
    """
    if not pattern or not pattern.strip():
        raise CustomRegexError("Regex tuỳ chỉnh đang trống.")
    try:
        compiled = re.compile(pattern.strip())
    except re.error as error:
        raise CustomRegexError(f"Regex không hợp lệ: {error}") from error
    if "number" not in compiled.groupindex:
        raise CustomRegexError(
            "Regex tuỳ chỉnh phải có nhóm tên (?P<number>...) để lấy số chương."
        )


def build_custom_pattern(pattern: str) -> ChapterPattern:
    """Build a custom chapter pattern from user regex."""
    validate_custom_regex(pattern)
    return ChapterPattern(
        name="custom",
        language="custom",
        priority=-1,
        strong=True,
        label="Regex tuỳ chỉnh",
        regex=re.compile(pattern.strip()),
    )


@dataclass
class PatternSet:
    """Collection of active chapter patterns."""

    patterns: List[ChapterPattern] = field(default_factory=list)
    custom: Optional[ChapterPattern] = None

    def all(self) -> List[ChapterPattern]:
        """Return all patterns sorted by priority."""
        items = list(self.patterns)
        if self.custom is not None:
            items.insert(0, self.custom)
        return sorted(items, key=lambda p: p.priority)

    def strong(self) -> List[ChapterPattern]:
        """Return only strong patterns (Vietnamese, English, Chinese)."""
        return [p for p in self.all() if p.strong]


def build_patterns(settings) -> PatternSet:
    """Build the active pattern set from application settings."""
    patterns: List[ChapterPattern] = []
    
    if getattr(settings, "detect_vietnamese", True):
        patterns.append(VIETNAMESE)
    if getattr(settings, "detect_english", True):
        patterns.append(ENGLISH)
    if getattr(settings, "detect_chinese", True):
        patterns.append(CHINESE)
    if getattr(settings, "detect_plain_numbered", True):
        patterns.append(PLAIN_NUMBERED)
    
    custom = None
    if getattr(settings, "use_custom_chapter_regex", False):
        regex_text = getattr(settings, "custom_chapter_regex", "")
        if regex_text:
            custom = build_custom_pattern(regex_text)
    
    return PatternSet(patterns=patterns, custom=custom)


# Glued header detection patterns (for splitting headers from body)
GLUED_HEADS: dict[str, Pattern[str]] = {
    "vietnamese": _compile(
        rf"^{DECORATIVE}*(?P<prefix>{VI_PREFIXES})"
        rf"(?:\s+|[.,:：\-–—]*\s*)*(?P<number>{NUMBER_TOKEN})",
        re.IGNORECASE,
    ),
    "english": _compile(
        rf"^{DECORATIVE}*(?P<prefix>{EN_PREFIXES})"
        rf"(?:\s+|[.,:：\-–—]*\s*)*(?P<number>{NUMBER_TOKEN})",
        re.IGNORECASE,
    ),
    "chinese": _compile(
        rf"^{DECORATIVE}*第\s*(?P<number>{NUMBER_TOKEN})\s*{CN_UNITS}"
    ),
    "custom": None,  # type: ignore[dict-item]
}


def glued_head(pattern: ChapterPattern) -> Optional[Pattern[str]]:
    """Return regex that matches only the header portion of a glued line.

    A glued line is a chapter header immediately followed by narrative with
    no line break: "Chương 12Đêm ấy trời mưa"
    
    The header must be split from the body instead of discarding the body.
    """
    if pattern.name == "custom":
        source = pattern.regex.pattern
        for marker in ("$", "\\Z"):
            if source.endswith(marker):
                source = source[: -len(marker)]
        try:
            return re.compile(source, pattern.regex.flags)
        except re.error:
            return None
    
    head = GLUED_HEADS.get(pattern.name)
    return head if isinstance(head, re.Pattern) else None
