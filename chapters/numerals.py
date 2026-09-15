"""Chinese numeral conversion.

Supports 零一二两三四五六七八九十百千万亿 plus Arabic digits (as pass
through) and mixed forms.  Malformed forms such as ``一二``, ``十十`` or a
bare digit followed by ``零`` are rejected (return ``None``) instead of being
guessed, so chapter numbering never silently drifts.
"""

from __future__ import annotations

import re
from typing import Optional

DIGITS = {
    "零": 0,
    "〇": 0,
    "洞": 0,  # rare variant used in some web novels
    "一": 1,
    "壹": 1,
    "二": 2,
    "两": 2,
    "貳": 2,
    "贰": 2,
    "三": 3,
    "叁": 3,
    "四": 4,
    "肆": 4,
    "五": 5,
    "伍": 5,
    "六": 6,
    "陆": 6,
    "七": 7,
    "柒": 7,
    "八": 8,
    "捌": 8,
    "九": 9,
    "玖": 9,
}

SMALL_UNITS = {"十": 10, "拾": 10, "百": 100, "佰": 100, "千": 1000, "仟": 1000}
BIG_UNITS = {"万": 10_000, "萬": 10_000, "亿": 100_000_000, "億": 100_000_000}

NUMERAL_CHARS = set(DIGITS) | set(SMALL_UNITS) | set(BIG_UNITS)

ARABIC_RE = re.compile(r"^[0-9]+$")
FULLWIDTH_TRANSLATION = str.maketrans("０１２３４５６７８９", "0123456789")


def normalize_digits(text: str) -> str:
    """Convert full-width Arabic digits and strip grouping separators."""
    return text.translate(FULLWIDTH_TRANSLATION).replace(",", "").replace("，", "")


def is_numeral_text(text: str) -> bool:
    """True when *text* is made only of numeral characters (CN or Arabic)."""
    stripped = normalize_digits(text).strip()
    if not stripped:
        return False
    return all(ch in NUMERAL_CHARS or ch.isdigit() for ch in stripped)


def chinese_to_int(text: str) -> Optional[int]:
    """Convert a Chinese numeral string to an int.

    Returns ``None`` for malformed input rather than guessing a value.

    >>> chinese_to_int("九十八")
    98
    >>> chinese_to_int("一二") is None
    True
    """
    if text is None:
        return None
    original = normalize_digits(text).strip()
    if not original:
        return None
    body = original
    # tolerante: 第 / 章 markers and spaces are stripped by the caller, but a
    # lone "两" style prefix or trailing punctuation is handled here.
    if body in ("零", "〇", "洞"):
        return 0

    total = 0
    section = 0
    number = 0
    pending_digit = False
    prev_kind: Optional[str] = None
    last_small_unit = 0
    saw_any = False

    for ch in body:
        if ch.isdigit():
            digit = int(ch)
            if pending_digit:
                # 1 2 -> "一二": two digits in a row without a unit
                return None
            number = digit
            pending_digit = True
            prev_kind = "zero" if digit == 0 else "digit"
            saw_any = True
            continue

        if ch in DIGITS:
            digit = DIGITS[ch]
            if digit == 0:
                if prev_kind == "zero":
                    return None  # 零零
                if prev_kind == "digit" and number != 0:
                    return None  # 一零 -> reject
                if prev_kind is None and len(body) > 1:
                    return None  # leading 零 inside a longer numeral
                number = 0
                pending_digit = True
                prev_kind = "zero"
                saw_any = True
                continue
            if pending_digit and prev_kind == "digit":
                return None  # 一二
            number = digit
            pending_digit = True
            prev_kind = "digit"
            saw_any = True
            continue

        if ch in SMALL_UNITS:
            unit = SMALL_UNITS[ch]
            if prev_kind in ("small_unit", "big_unit") and number == 0:
                return None  # 十十 / 百十之类的重复单位
            if prev_kind is None:
                # leading 十 is allowed (十五 = 15); other units are not
                if unit != 10:
                    return None
                number = 1
            elif not pending_digit and number == 0:
                # e.g. 一百十 -> implied 10, accepted by colloquial usage
                number = 1
            if last_small_unit and unit >= last_small_unit:
                return None  # 十百 / 一百二十三千: units must decrease
            section += number * unit
            last_small_unit = unit
            number = 0
            pending_digit = False
            prev_kind = "small_unit"
            saw_any = True
            continue

        if ch in BIG_UNITS:
            big = BIG_UNITS[ch]
            if prev_kind is None:
                return None  # lone 万
            if prev_kind == "big_unit" and number == 0 and section == 0:
                return None
            section += number
            number = 0
            pending_digit = False
            if section == 0:
                return None  # 零万
            if big == 10_000:
                total += section * 10_000
                section = 0
            else:
                total = (total + section) * 100_000_000
                section = 0
            last_small_unit = 0
            prev_kind = "big_unit"
            saw_any = True
            continue

        return None  # unknown character

    if not saw_any:
        return None
    total += section + number
    return total


def parse_number_token(token: str) -> Optional[int]:
    """Parse an Arabic, full-width or Chinese numeral token."""
    if token is None:
        return None
    text = normalize_digits(token).strip().strip("　 ")
    text = text.strip("\u3000")
    if not text:
        return None
    if ARABIC_RE.match(text):
        try:
            return int(text)
        except ValueError:
            return None
    if not is_numeral_text(text):
        return None
    return chinese_to_int(text)


ROMAN_VALUES = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}


def roman_to_int(text: str) -> Optional[int]:
    """Convert a roman numeral (used by 'Chapter IV' style headers)."""
    if not text:
        return None
    body = text.strip().upper()
    if not re.fullmatch(r"[IVXLCDM]+", body):
        return None
    total = 0
    previous = 0
    for char in reversed(body):
        value = ROMAN_VALUES[char]
        if value < previous:
            total -= value
        else:
            total += value
            previous = value
    return total or None

