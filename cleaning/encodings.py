"""Encoding detection with a deterministic fallback chain.

Order: UTF-8 BOM, UTF-8, UTF-16 LE/BE BOM, UTF-32 BOM, cp1258 (Vietnamese),
cp1252, latin-1.  The chain never mangles Vietnamese diacritics: a decoding
that produces replacement characters or control noise is rejected in favour of
the next candidate, and the chosen encoding is reported to the user.
"""

from __future__ import annotations

import codecs
import unicodedata
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence, Tuple

BOMS: Sequence[Tuple[bytes, str]] = (
    (codecs.BOM_UTF32_LE, "utf-32"),
    (codecs.BOM_UTF32_BE, "utf-32"),
    (codecs.BOM_UTF8, "utf-8-sig"),
    (codecs.BOM_UTF16_LE, "utf-16"),
    (codecs.BOM_UTF16_BE, "utf-16"),
)

DEFAULT_CHAIN: Sequence[str] = (
    "utf-8-sig",
    "utf-8",
    "utf-16",
    "utf-32",
    "cp1258",
    "cp1252",
    "latin-1",
)

_CONTROL_ALLOWED = {"\n", "\r", "\t", "\u3000"}


@dataclass
class EncodingResult:
    text: str
    encoding: str
    bom: str = ""
    had_decoding_errors: bool = False
    rejected: List[str] = None  # type: ignore[assignment]
    note: str = ""

    def __post_init__(self) -> None:
        if self.rejected is None:
            self.rejected = []


def _mojibake_score(text: str) -> float:
    """Heuristic penalty for a decoded text (lower is better)."""
    if not text:
        return 0.0
    bad = 0
    for char in text:
        if char == "\ufffd":
            bad += 12
        elif unicodedata.category(char) in ("Co", "Cn", "Cs"):
            bad += 8
        elif unicodedata.category(char) == "Cc" and char not in _CONTROL_ALLOWED:
            bad += 6
        elif char in "\u00c2\u00c3\u00e2\u20ac":  # typical cp1252-mojibake indicators
            bad += 1
    return bad / max(1, len(text)) * 1000


def _vietnamese_score(text: str) -> float:
    """Mojibake penalty specific to Vietnamese diacritics."""
    suspicious = sum(text.count(token) for token in ("Ã", "á»", "áº", "Ä‘", "Ã¢", "Ã´"))
    return suspicious / max(1, len(text)) * 1000


def _bom_for(data: bytes) -> Tuple[str, str]:
    for bom_bytes, encoding in BOMS:
        if data.startswith(bom_bytes):
            label = {
                codecs.BOM_UTF32_LE: "UTF-32 LE BOM",
                codecs.BOM_UTF32_BE: "UTF-32 BE BOM",
                codecs.BOM_UTF8: "UTF-8 BOM",
                codecs.BOM_UTF16_LE: "UTF-16 LE BOM",
                codecs.BOM_UTF16_BE: "UTF-16 BE BOM",
            }[bom_bytes]
            return encoding, label
    return "", ""


def detect_encoding(data: bytes, chain: Optional[Iterable[str]] = None) -> EncodingResult:
    """Decode *data* using the fallback chain and report the chosen encoding."""
    if not data:
        return EncodingResult(text="", encoding="utf-8", note="Tệp rỗng.")

    bom_encoding, bom_label = _bom_for(data)
    candidates: List[Tuple[str, bool]] = []
    if bom_encoding:
        candidates.append((bom_encoding, True))
    for encoding in chain or DEFAULT_CHAIN:
        if encoding not in [c[0] for c in candidates]:
            candidates.append((encoding, False))

    best: Optional[Tuple[float, str, str, bool, List[str]]] = None
    rejected: List[str] = []
    for encoding, from_bom in candidates:
        try:
            text = data.decode(encoding)
            strict = True
        except (UnicodeDecodeError, LookupError):
            try:
                text = data.decode(encoding, errors="replace")
                strict = False
            except (UnicodeDecodeError, LookupError):
                rejected.append(encoding)
                continue
        if "\ufffd" in text and strict:
            rejected.append(encoding)
            continue
        if "\ufffd" in text:
            rejected.append(f"{encoding} (thay thế ký tự lỗi)")
            continue
        score = _mojibake_score(text) + _vietnamese_score(text)
        if from_bom:
            score -= 0.5  # BOM markers win unless clearly broken
        if best is None or score < best[0]:
            best = (score, encoding, bom_label if from_bom else "", strict, list(rejected))

    if best is None:  # pragma: no cover - latin-1 always succeeds
        text = data.decode("latin-1", errors="replace")
        return EncodingResult(
            text=text,
            encoding="latin-1",
            had_decoding_errors=True,
            rejected=rejected,
            note="Không giải mã chắc chắn; dùng latin-1 và có thể mất dấu tiếng Việt.",
        )

    _score, encoding, bom_label, strict, rejected_before = best
    text = data.decode(encoding)
    note = ""
    if encoding == "cp1258":
        note = "Đã dùng bảng mã tiếng Việt cp1258."
    if rejected:
        note = (note + " " if note else "") + "Đã bỏ qua: " + ", ".join(sorted(set(rejected)))
    return EncodingResult(
        text=text,
        encoding=encoding,
        bom=bom_label,
        had_decoding_errors=not strict,
        rejected=sorted(set(rejected)),
        note=note.strip(),
    )


def decode_bytes(data: bytes, chain: Optional[Iterable[str]] = None) -> EncodingResult:
    return detect_encoding(data, chain)

