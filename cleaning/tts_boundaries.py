"""Shared, deterministic technical-token and prose boundary recognition.

Offsets always refer to the original string. Splitting retains separators;
no placeholder strings can leak into narration or collide with user text.
"""
from __future__ import annotations

import re
import unicodedata

CHUNKER_VERSION = "tts-boundaries-v2-sentence-pack"
DEFAULT_ABBREVIATIONS = (
    "Mr.", "Dr.", "Prof.", "P.S.", "U.S.", "v.v.", "v.d.",
    "TP.HCM", "P.GS", "TS.", "ThS.",
)
URL_RE = re.compile(r"(?<![\w])(?i:https?://|ftp://|sftp://|file://|wss?://|www\.)[^\s<>\"“”]+", re.I)
EMAIL_RE = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
TOKEN_RE = re.compile(
    r"(?<![\w])(?i:https?://|ftp://|sftp://|file://|wss?://|www\.)[^\s<>\"“”]+"
    r"|(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)+"
    r"|[A-Za-z]:\\[^\s<>\"“”]+"
    r"|\{[^{}\n]*\"[^{}\n]*:[^{}\n]*\}"
    r"|\b[vV]?\d+(?:[.,:/-]\d+)+(?:%)?"
    r"|\b\w+:[\w/\\]+\b"
    r"|\b[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.(?:com|net|org|vn|io|edu|gov|co|uk|dev|app|info)(?!\w)"
)
ENDING_RE = re.compile(r'''[.!?…。！？]+["'”’»\)\]\}」』】》〉]*''')
CLAUSE_RE = re.compile(r"[,;:，；：]+")
CLOSERS = '\"\'”’»)]}」』】》〉'
QUOTE_RE = re.compile(r'“[^“”]*”|«[^«»]*»|"[^"\n]*"|‘[^‘’]*’')


def protected_spans(text: str, abbreviations=DEFAULT_ABBREVIATIONS):
    """Yield technical tokens. Trailing sentence punctuation is not a URL."""
    for match in TOKEN_RE.finditer(text):
        end = match.end()
        if '://' in match.group() or match.group().lower().startswith('www.') or '\\' in match.group():
            while end > match.start() and text[end - 1] in '.!?…,;:)]}':
                end -= 1
        yield match.start(), end
    # Balanced JSON objects, including nested objects and escaped quotes.
    # A single scanner visits each character at most once.
    stack, in_string, escaped, object_start = [], False, False, None
    for index, char in (enumerate(text) if '{' in text else ()):
        if not stack:
            if char == '{':
                stack.append(index)
                object_start = index
            continue
        if in_string:
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char == '{':
            stack.append(index)
        elif char == '}':
            stack.pop()
            if not stack:
                prefix = object_start + 1
                while prefix < index and text[prefix].isspace():
                    prefix += 1
                if prefix < index and text[prefix] == '"':
                    yield object_start, index + 1
                object_start = None
    if abbreviations:
        pattern = re.compile(r"(?<!\w)(?:" + "|".join(re.escape(a) for a in sorted(abbreviations, key=len, reverse=True)) + r")(?!\w)", re.I)
        for match in pattern.finditer(text):
            yield match.span()
    for match in re.finditer(r"\b(?:[A-Z]\.){2,}", text):
        yield match.span()


def protection_mask(text: str, abbreviations=DEFAULT_ABBREVIATIONS, *, quote_limit=0):
    mask = bytearray(len(text))
    for start, end in protected_spans(text, abbreviations):
        mask[start:end] = b'\1' * (end - start)
    if quote_limit:
        for match in QUOTE_RE.finditer(text):
            if len(match.group()) <= quote_limit:
                mask[match.start():match.end()] = b'\1' * len(match.group())
    return mask


def boundary_positions(text: str, kind="sentence", abbreviations=DEFAULT_ABBREVIATIONS, *, quote_limit=0):
    """Return offsets after punctuation/closers, excluding technical tokens."""
    mask = protection_mask(text, abbreviations, quote_limit=quote_limit)
    pattern = ENDING_RE if kind == "sentence" else CLAUSE_RE
    return [m.end() for m in pattern.finditer(text) if not any(mask[m.start():m.end()])]


def split_units(text: str, kind="sentence", abbreviations=DEFAULT_ABBREVIATIONS, *, quote_limit=0):
    previous = 0
    result = []
    for cut in boundary_positions(text, kind, abbreviations, quote_limit=quote_limit):
        # Keep whitespace with the following unit, so packing is lossless.
        result.append(text[previous:cut])
        previous = cut
    if previous < len(text):
        result.append(text[previous:])
    return result or [text]


def meaningful_text(text: str) -> bool:
    return any(c.isalnum() for c in text)


def safe_half_split(text: str) -> tuple[str, str]:
    """Retry split without altering text or cutting a technical token."""
    midpoint = len(text) // 2
    meaningful = [i for i, c in enumerate(text) if c.isalnum()]
    if len(meaningful) < 2 or re.match(r"^(?:Chương|Chuong|Chapter|Hồi|Quyển)\s+\d+\b", text, re.I):
        return text, ""
    first_letter, last_letter = meaningful[0], meaningful[-1]
    for kind in ("sentence", "clause"):
        cuts = [c for c in boundary_positions(text, kind, quote_limit=len(text) // 2)
                if first_letter < c <= last_letter]
        if cuts:
            cut = min(cuts, key=lambda c: abs(c - midpoint))
            return text[:cut].strip(), text[cut:].strip()
    mask = protection_mask(text)
    cuts = [m.start() for m in re.finditer(r"\s+", text)
            if not mask[m.start()] and 0 < m.start() < len(text) - 1]
    if cuts:
        cut = min(cuts, key=lambda c: abs(c - midpoint))
        return text[:cut].strip(), text[cut:].strip()
    # A single ordinary oversized word can be split; protected tokens cannot.
    if any(mask):
        return text, ""
    cut = max(1, midpoint)
    while cut < len(text) and unicodedata.combining(text[cut]):
        cut += 1
    return text[:cut], text[cut:]
