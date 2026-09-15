"""Han character detection and Chinese segment extraction.

Han ideographs are covered across the whole Unicode plane set used by web
novels: CJK Unified Ideographs, Extension A/B/C/D/E, compatibility ideographs
and the common CJK punctuation.  Extension characters are treated as text (they
are never deleted) so rare-name glyphs survive cleaning.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

HAN_RANGES: Sequence[Tuple[int, int]] = (
    (0x3400, 0x4DBF),    # CJK Extension A
    (0x4E00, 0x9FFF),    # CJK Unified Ideographs
    (0xF900, 0xFAFF),    # CJK Compatibility Ideographs
    (0x20000, 0x2A6DF),  # Extension B
    (0x2A700, 0x2B73F),  # Extension C
    (0x2B740, 0x2B81F),  # Extension D
    (0x2B820, 0x2CEAF),  # Extension E
    (0x2CEB0, 0x2EBEF),  # Extension F
    (0x30000, 0x3134F),  # Extension G
    (0x2F800, 0x2FA1F),  # Compatibility Ideographs Supplement
)

CJK_PUNCTUATION = "　、。〃〄々〆〇〈〉《》「」『』【】〔〕〖〗〘〙〚〛〜〝〞〟〰〾〿–—‘’‛“”„‟…‧﹏"
FULLWIDTH_PUNCTUATION = "！？｡。＂＃＄％＆＇（）＊＋，－／：；＜＝＞［＼］＾＿｀｛｜｝～｟｠､、〃》「」『』【】〔〕〖〗〙〚〛〜〝〞〟〰〾〿–—‘’‛“”„‟…‧﹏"
CHINESE_PUNCTUATION = set(CJK_PUNCTUATION + FULLWIDTH_PUNCTUATION)


def is_han(char: str) -> bool:
    """True when *char* is a Han ideograph (any supported extension)."""
    if not char:
        return False
    code = ord(char)
    for start, end in HAN_RANGES:
        if start <= code <= end:
            return True
    return False


def is_chinese_punctuation(char: str) -> bool:
    return char in CHINESE_PUNCTUATION


def has_han(text: str) -> bool:
    return any(is_han(char) for char in text or "")


def han_count(text: str) -> int:
    return sum(1 for char in text or "" if is_han(char))


def han_ratio(text: str) -> float:
    stripped = re.sub(r"\s+", "", text or "")
    if not stripped:
        return 0.0
    return han_count(stripped) / len(stripped)


@dataclass
class Segment:
    """One continuous Chinese run found in a string."""

    text: str
    start: int
    end: int


@dataclass
class LocatedSegment:
    """A segment with its source location."""

    text: str
    file: str = ""
    line: int = 0
    path: str = ""
    chapter: Optional[int] = None
    column: int = 0
    context: str = ""

    def location_label(self) -> str:
        bits = []
        if self.file:
            bits.append(self.file)
        if self.path:
            bits.append(self.path)
        if self.line:
            bits.append(f"dòng {self.line}")
        if self.chapter is not None:
            bits.append(f"chương {self.chapter}")
        return " · ".join(bits)

    def to_dict(self) -> Dict[str, object]:
        return {
            "text": self.text,
            "file": self.file,
            "line": self.line,
            "path": self.path,
            "chapter": self.chapter,
            "column": self.column,
            "context": self.context,
        }


SEGMENT_SPLIT_RE = re.compile(
    r"[\s\u3000" + re.escape("".join(sorted(CHINESE_PUNCTUATION))) + r"]+"
)


def chinese_segments(text: str) -> List[Segment]:
    """Return every continuous run of Han characters (punctuation splits)."""
    segments: List[Segment] = []
    if not text:
        return segments
    start: Optional[int] = None
    for index, char in enumerate(text):
        if is_han(char):
            if start is None:
                start = index
            continue
        if start is not None:
            segments.append(Segment(text[start:index], start, index))
            start = None
    if start is not None:
        segments.append(Segment(text[start:], start, len(text)))
    return segments


def split_segments(text: str, *, min_len: int = 1, max_len: int = 0) -> List[Segment]:
    segments = [s for s in chinese_segments(text) if len(s.text) >= min_len]
    if max_len <= 0:
        return segments
    trimmed: List[Segment] = []
    for segment in segments:
        if len(segment.text) <= max_len:
            trimmed.append(segment)
            continue
        # Long Han runs are usually several sentences without spaces: keep whole
        # runs but never drop them, splitting only for table readability.
        for offset in range(0, len(segment.text), max_len):
            piece = segment.text[offset: offset + max_len]
            trimmed.append(Segment(piece, segment.start + offset, segment.start + offset + len(piece)))
    return trimmed


def extract_located_segments(
    text: str,
    *,
    mode: str = "segments",
    file: str = "",
    path: str = "",
    chapter: Optional[int] = None,
    line_offset: int = 0,
    context_chars: int = 0,
    min_len: int = 1,
    max_len: int = 0,
) -> List[LocatedSegment]:
    """Extract Chinese occurrences from *text* with source locations.

    ``mode='segments'`` returns only the Chinese runs; ``mode='line'`` returns
    the whole containing line for every line that has Chinese text.
    """
    located: List[LocatedSegment] = []
    if not text:
        return located
    if mode == "line":
        for index, line in enumerate(text.split("\n")):
            if not has_han(line):
                continue
            located.append(
                LocatedSegment(
                    text=line,
                    file=file,
                    line=line_offset + index + 1,
                    path=path,
                    chapter=chapter,
                    context=line,
                )
            )
        return located

    for index, line in enumerate(text.split("\n")):
        for segment in split_segments(line, min_len=min_len, max_len=max_len):
            context = ""
            if context_chars:
                start = max(0, segment.start - context_chars)
                end = min(len(line), segment.end + context_chars)
                context = line[start:end]
            located.append(
                LocatedSegment(
                    text=segment.text,
                    file=file,
                    line=line_offset + index + 1,
                    path=path,
                    chapter=chapter,
                    column=segment.start,
                    context=context,
                )
            )
    return located


def latin_of(text: str) -> str:
    """Return only the non-Han part of a string (used to detect translated text)."""
    return "".join(char for char in text or "" if not is_han(char))

