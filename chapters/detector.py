"""Multilingual chapter detection with glued header splitting.

Detects chapter headers in Vietnamese, English, and Chinese formats.
Handles glued headers (headers immediately followed by narrative without
a line break) by splitting them rather than discarding the body content.

Key behaviors:
- Detects Chinese: 第1章, 第001章, 第一章, 第十章, 第一百二十三章, 第1回, etc.
- Detects Vietnamese: Chương 1, Hồi 1, Tập 1, etc.
- Detects English: Chapter 1, Part 1, etc.
- Handles decorative brackets: 【第1章】, [第1章], （第1章）, ★第1章
- Splits glued headers from body content instead of discarding
- Preserves ALL Vietnamese content on the same line as a chapter header
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from .numerals import parse_number_token
from .patterns import ChapterPattern, PatternSet, glued_head

# Maximum reasonable length for a chapter header line
MAX_HEADER_LINE_CHARS = 200

# Pattern to detect glued title/body boundaries
# Only splits when uppercase/Han character is glued to previous word
GLUED_TITLE_RE = re.compile(
    r"^(?P<title>.*?[^\W_])(?P<body>[A-Z\u4e00-\u9fff].*)$", re.DOTALL
)

# A Chinese chapter marker may be followed by a closing decorative bracket
# before its same-line title, e.g. ``[第327章] 流民不可怕``.
CHINESE_CLOSING_DECORATIONS = "]】）)〕》〉」』〗"
CHINESE_SEPARATOR_CHARS = ":：-–—、,，"
HAN_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
LATIN_RE = re.compile(r"[A-Za-zÀ-ỹà-ỹ]")

# Countdown/clock display lines such as 【4:59:50】, 【00:18】 or
# 【12:09:57 — rương báu】 are narrative content, never chapter headers.
MAX_CLOCK_LINE_CHARS = 40
CLOCK_VALUE_RE = re.compile(
    r"^[0-9]{1,3}:[0-9]{2}(?::[0-9]{2})?(?:\s*[—–-]\s*\S.*)?$"
)
TIME_EXPRESSION_RE = re.compile(r"^[0-9]{1,3}:[0-9]{2}")
DECORATIVE_TRIM_CHARS = " \t\u3000【】[]〔〕（）()《》〈〉「」『』★#*·・,.;:!?…–—-"


def _is_clock_only_line(line: str) -> bool:
    """Return whether *line* only displays a clock/countdown value.

    Samples: ``【4:59:50】``, ``【00:18】``, ``【12:09:57 — rương báu】``.
    Those lines are story content; reading them as headers invents chapters
    and splits the body of the chapter they belong to.
    """
    stripped = line.strip()
    if not stripped or len(stripped) > MAX_CLOCK_LINE_CHARS:
        return False
    core = stripped.strip(DECORATIVE_TRIM_CHARS).strip()
    if not core or len(core) > MAX_CLOCK_LINE_CHARS:
        return False
    return bool(CLOCK_VALUE_RE.match(core))


def _is_chinese_only_title(value: str) -> bool:
    """Return whether a same-line suffix is a Chinese-only chapter title."""
    candidate = (value or "").strip()
    return bool(HAN_RE.search(candidate)) and not LATIN_RE.search(candidate)


def _structural_chinese_header(stripped: str, title_start: int) -> str:
    """Return the marker portion before a Chinese title suffix."""
    header = stripped[:title_start].rstrip()
    return header.rstrip(CHINESE_SEPARATOR_CHARS).rstrip()


def _split_chinese_remainder(remainder: str) -> Tuple[str, str]:
    """Split closing bracket/separators from a Chinese header remainder.

    Returns ``(closing_marker, content)``.  The closing marker belongs to the
    structural header; content is then classified as title or body.
    """
    value = (remainder or "").lstrip()
    closing = ""
    while value and value[0] in CHINESE_CLOSING_DECORATIONS:
        closing += value[0]
        value = value[1:].lstrip()
    value = value.lstrip(CHINESE_SEPARATOR_CHARS).lstrip()
    return closing, value.strip()


def split_glued_title(title: str) -> Tuple[str, str]:
    """Split a glued title like "Chạy trốnNàng vội..." into (title, body).

    Only splits when there's clear evidence of a missing line break:
    - Lowercase letter directly followed by uppercase or Han character
    - The remainder looks like a sentence (has spaces, not just one word)

    Returns (title, "") when the text doesn't look glued.
    Preserves text when uncertain to avoid data loss.
    """
    if not title:
        return title, ""
    
    match = GLUED_TITLE_RE.match(title)
    if not match:
        return title, ""
    
    head = match.group("title").strip()
    body = match.group("body").strip()
    
    # Reject if head is too short, body is too short, or body has no spaces
    if not head or len(head) < 2 or len(body) < 6 or " " not in body:
        return title, ""
    
    # Reject if the last character of head is already whitespace
    if head[-1].isspace():
        return title, ""
    
    return head, body


@dataclass
class ChapterHit:
    """One detected chapter header with its body content."""
    
    number: int
    pattern_name: str
    language: str
    line_index: int
    header_line: str
    title: str
    body_lines: List[str] = field(default_factory=list)
    glued: bool = False
    glued_remainder: str = ""
    raw_line: str = ""
    parse_note: str = ""

    @property
    def body(self) -> str:
        """Return the complete chapter body as a single string."""
        return "\n".join(self.body_lines).strip("\n")


def _parse_number(raw: Optional[str]) -> Optional[int]:
    """Parse a chapter number from the matched group."""
    if raw is None:
        return None
    return parse_number_token(raw)


def _title_from_match(match: re.Match[str]) -> str:
    """Extract the chapter title from the regex match.

    Tries 'title' group first, then 'title2' group as fallback.
    Strips common separators and whitespace.
    """
    for group in ("title", "title2"):
        try:
            value = match.group(group)
        except (IndexError, re.error):
            value = None
        if value:
            value = value.strip().strip(":：-–—").strip()
            if value:
                return value
    return ""


def _try_line_header(
    line: str, pattern_set: PatternSet
) -> Optional[Tuple[int, str, str, str, ChapterPattern]]:
    """Try to parse *line* as a complete chapter header.

    Returns (number, title, header_text, glued_body, pattern) on success.
    Returns None if the line is not a chapter header.
    """
    stripped = line.strip()
    
    # Skip empty lines and overly long lines (likely prose, not headers)
    if not stripped or len(stripped) > MAX_HEADER_LINE_CHARS:
        return None

    # A line that only shows a clock/countdown value is never a header.
    if _is_clock_only_line(stripped):
        return None
    
    for pattern in pattern_set.all():
        match = pattern.match(stripped)
        if not match:
            continue
        
        # A plain numbered line whose number starts a clock value is prose,
        # not a header ("10:30 sáng hôm đó…").
        if pattern.name == "plain" and TIME_EXPRESSION_RE.match(
            stripped[match.start("number"):]
        ):
            continue

        # Parse chapter number
        number = _parse_number(match.groupdict().get("number"))
        if number is None:
            continue
        
        # Extract title
        title = _title_from_match(match)
        glued_body = ""

        if pattern.name == "chinese" and title:
            # For Chinese headers, only a Chinese-only suffix is a title to
            # remove. Mixed/Latin content is narrative and must remain in the
            # chapter body.
            title_start = match.start("title")
            header = _structural_chinese_header(stripped, title_start)
            if _is_chinese_only_title(title):
                return number, title, header, "", pattern
            return number, "", header, title, pattern
        
        # Check if title has glued body content
        if title:
            title, glued_body = split_glued_title(title)
        
        # Construct header text (without glued body)
        header = stripped
        if glued_body:
            header = stripped[: len(stripped) - len(glued_body)].strip()
        
        return number, title, header, glued_body, pattern
    
    return None


def _try_glued_header(
    line: str, pattern_set: PatternSet
) -> Optional[Tuple[int, str, str, str, ChapterPattern]]:
    """Try to split a chapter header that is glued to narrative on the same line.

    Example: "第327章流民不可怕Đêm ấy..." -> splits into header and remainder
    
    Returns (number, title, header, remainder, pattern) on success.
    Returns None if no glued header is found.
    """
    stripped = line.strip()
    
    if not stripped or len(stripped) < 4:
        return None

    # A line that only shows a clock/countdown value is never a header.
    if _is_clock_only_line(stripped):
        return None
    
    for pattern in pattern_set.all():
        # Skip plain numbered pattern for glued detection (too ambiguous)
        if pattern.name == "plain":
            continue
        
        head = glued_head(pattern)
        if head is None:
            continue
        
        match = head.match(stripped)
        if not match:
            continue
        
        # Parse chapter number
        number = _parse_number(match.groupdict().get("number"))
        if number is None:
            continue
        
        # Split header from remainder
        end = match.end()
        remainder = stripped[end:]
        closing, content = _split_chinese_remainder(remainder) if pattern.name == "chinese" else ("", remainder.strip())

        # A closing bracket alone is part of the header, not body content.
        if pattern.name == "chinese" and not content:
            return number, "", f"{stripped[:end].strip()}{closing}", "", pattern

        # Must have actual remainder content
        if not content:
            continue

        header = f"{stripped[:end].strip()}{closing}" if pattern.name == "chinese" else stripped[:end].strip()
        
        # Reject if "header" swallowed an entire prose line
        if len(header) > MAX_HEADER_LINE_CHARS:
            continue

        if pattern.name == "chinese" and _is_chinese_only_title(content):
            return number, content, header, "", pattern
        
        return number, "", header, content, pattern
    
    return None


def detect_chapters(
    text: str,
    pattern_set: PatternSet,
    *,
    source_name: str = "",
) -> Tuple[List[ChapterHit], List[str], List[dict]]:
    """Detect all chapter headers in *text*.

    Returns:
        hits: List of detected chapter headers with their bodies
        preamble_lines: Lines before the first chapter
        notes: Diagnostic notes about glued splits and rejected candidates

    Key behaviors:
    - Headers glued to narrative are split, never dropped
    - Vietnamese content on same line as header is preserved
    - Chinese headers with subtitles are detected and will be normalized later
    """
    lines = text.split("\n")
    hits: List[ChapterHit] = []
    notes: List[dict] = []
    current: Optional[ChapterHit] = None
    preamble: List[str] = []

    for index, line in enumerate(lines):
        # Try to parse as a complete header line first
        found = _try_line_header(line, pattern_set)
        glued_remainder = ""
        
        # If not a complete header, try to split a glued header
        if found is None:
            glued = _try_glued_header(line, pattern_set)
            if glued is not None:
                number, title, header, glued_remainder, pattern = glued
                found = (number, title, header, "", pattern)
                notes.append(
                    {
                        "kind": "glued",
                        "line": index + 1,
                        "number": number,
                        "pattern": pattern.name,
                        "snippet": line.strip()[:160],
                    }
                )
        
        if found is not None:
            number, title, header, glued_body, pattern = found
            
            # Create new chapter hit
            current = ChapterHit(
                number=number,
                pattern_name=pattern.name,
                language=pattern.language,
                line_index=index,
                header_line=header,
                title=title,
                raw_line=line,
                glued=bool(glued_remainder or glued_body),
                glued_remainder=glued_remainder or glued_body,
            )
            
            # Add glued content to body
            if glued_remainder:
                current.body_lines.append(glued_remainder)
            
            if glued_body:
                current.body_lines.append(glued_body)
                if not glued_remainder:  # Only log once
                    notes.append(
                        {
                            "kind": "glued",
                            "line": index + 1,
                            "number": number,
                            "pattern": pattern.name,
                            "snippet": line.strip()[:160],
                        }
                    )
            
            hits.append(current)
            continue
        
        # Not a header - add to preamble or current chapter body
        if current is None:
            preamble.append(line)
        else:
            current.body_lines.append(line)

    return hits, preamble, notes


def detect_headers_in_text(
    text: str, pattern_set: PatternSet
) -> List[Tuple[int, int, str, str]]:
    """Detect only headers without splitting bodies (used by repair actions).

    Returns a list of (line_index, number, raw_line, pattern_name).
    """
    headers: List[Tuple[int, int, str, str]] = []
    
    for index, line in enumerate(text.split("\n")):
        found = _try_line_header(line, pattern_set)
        if found is None:
            continue
        
        number, _title, _header, _note, pattern = found
        headers.append((index, number, line.strip(), pattern.name))
    
    return headers


def strip_trailing_blank_lines(lines: List[str]) -> None:
    """Remove trailing blank lines from a list (in-place)."""
    while lines and not lines[-1].strip():
        lines.pop()
