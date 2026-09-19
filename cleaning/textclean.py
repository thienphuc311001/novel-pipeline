"""Text cleaning rules shared by the normalize, clean and export stages.

Two clearly separated concerns live here:

* :func:`restore_escaped_newlines`, :func:`normalize_spacing` and
  :func:`enforce_sentence_endings` - conservative normalization used on novel
  text.  They never delete narrative, dialogue or paragraphs.
* :func:`clean_text` - the TTS cleaning pass (control characters, HTML, quotes
  and bracket pairs, symbol words, user rules).  Every removal is counted and
  returned in a :class:`CleanReport` so the UI can show what changed.
"""

from __future__ import annotations

import html
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from config.settings import DEFAULT_BRACKET_PAIRS, DEFAULT_SYMBOL_MAP

# --------------------------------------------------------------- constants

CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
ZERO_WIDTH_RE = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2060\ufeff]")
HTML_TAG_RE = re.compile(r"</?[a-zA-Z][^<>]{0,200}?>")
HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
HTML_BLOCK_TAG_RE = re.compile(
    r"<\s*/?\s*(?:p|br|div|li|tr|h[1-6]|section|article)\b[^<>]*>", re.IGNORECASE
)

MULTISPACE_RE = re.compile(r"[ \t\u00a0\u3000]{2,}")
SPACE_BEFORE_PUNCT_RE = re.compile(r"\s+([,.;:!?%…)\]}»”’])")
SPACE_AFTER_OPEN_RE = re.compile(r"([(\[{«“‘])\s+")
BLANK_LINES_RE = re.compile(r"\n{3,}")
TRAILING_SPACE_RE = re.compile(r"[ \t\u3000]+$", re.MULTILINE)

SENTENCE_END_CHARS = "。！？!?…；;." 
CLOSING_QUOTES = "\"')]}»”’」』】》〉"
PROSE_LINE_RE = re.compile(r"[A-Za-zÀ-ỹ0-9\u4e00-\u9fff]")

ESCAPED_NEWLINE_PATTERNS: Sequence[Tuple[re.Pattern[str], str]] = (
    (re.compile(r"\\r\\n"), "\n"),
    (re.compile(r"\\n"), "\n"),
    (re.compile(r"\\r"), "\n"),
)
SERIALIZED_ESCAPE_RE = re.compile(r"(?:\\r\\n|\\n|\\r){1,}")

UNWANTED_FILE_PREFIXES = ("__macosx/", "._", ".ds_store")


@dataclass
class CleaningOptions:
    """Options for the TTS cleaning pass."""

    remove_control_chars: bool = True
    remove_html: bool = True
    unescape_html_entities: bool = True
    quote_mode: str = "strip"  # keep | strip (pairs only) | remove (all quotes)
    bracket_mode: str = "strip"
    bracket_pairs: List[str] = field(default_factory=lambda: list(DEFAULT_BRACKET_PAIRS))
    custom_quote_chars: str = ""
    symbol_map_enabled: bool = True
    symbol_map: Dict[str, str] = field(default_factory=lambda: dict(DEFAULT_SYMBOL_MAP))
    custom_rules: List[Dict[str, str]] = field(default_factory=list)
    drop_empty_lines: bool = False
    normalize_spacing: bool = True
    enforce_period: bool = False
    strip_zero_width: bool = True

    @classmethod
    def from_settings(cls, settings) -> "CleaningOptions":
        return cls(
            remove_control_chars=getattr(settings, "remove_control_chars", True),
            remove_html=getattr(settings, "remove_html", True),
            unescape_html_entities=getattr(settings, "unescape_html_entities", True),
            quote_mode=getattr(settings, "quote_mode", "strip"),
            bracket_mode=getattr(settings, "bracket_mode", "strip"),
            bracket_pairs=list(getattr(settings, "bracket_pairs", DEFAULT_BRACKET_PAIRS)),
            custom_quote_chars=getattr(settings, "custom_quote_chars", ""),
            symbol_map_enabled=getattr(settings, "symbol_map_enabled", True),
            symbol_map=dict(getattr(settings, "symbol_map", DEFAULT_SYMBOL_MAP)),
            custom_rules=[dict(r) for r in getattr(settings, "custom_rules", [])],
            drop_empty_lines=getattr(settings, "drop_empty_lines", False),
            normalize_spacing=getattr(settings, "normalize_spacing", True),
            enforce_period=getattr(settings, "enforce_period", False),
        )


    @classmethod
    def for_tts(cls, settings) -> "CleaningOptions":
        """Keep structure for the dedicated sanitizer; explicit user rules remain."""
        options = cls.from_settings(settings)
        options.quote_mode = options.bracket_mode = "keep"
        options.symbol_map_enabled = options.enforce_period = False
        options.remove_html = options.unescape_html_entities = False
        options.remove_control_chars = options.strip_zero_width = False
        options.normalize_spacing = options.drop_empty_lines = False
        return options


@dataclass
class CleanReport:
    """Counts of everything the cleaning pass touched."""

    before_chars: int = 0
    after_chars: int = 0
    control_chars: int = 0
    zero_width: int = 0
    html_tags: int = 0
    html_entities: int = 0
    quotes_removed: int = 0
    brackets_removed: int = 0
    bracket_pairs_removed: int = 0
    symbols_replaced: int = 0
    custom_rule_hits: int = 0
    periods_added: int = 0
    blank_lines_collapsed: int = 0
    details: List[Dict[str, object]] = field(default_factory=list)

    @property
    def lost_chars(self) -> int:
        return self.before_chars - self.after_chars

    def to_dict(self) -> Dict[str, object]:
        data = {
            "before_chars": self.before_chars,
            "after_chars": self.after_chars,
            "lost_chars": self.lost_chars,
            "control_chars": self.control_chars,
            "zero_width": self.zero_width,
            "html_tags": self.html_tags,
            "html_entities": self.html_entities,
            "quotes_removed": self.quotes_removed,
            "brackets_removed": self.brackets_removed,
            "bracket_pairs_removed": self.bracket_pairs_removed,
            "symbols_replaced": self.symbols_replaced,
            "custom_rule_hits": self.custom_rule_hits,
            "periods_added": self.periods_added,
            "blank_lines_collapsed": self.blank_lines_collapsed,
        }
        return data

    def summary(self) -> str:
        bits = [f"{self.before_chars} -> {self.after_chars} ký tự"]
        for label, value in (
            ("ký tự điều khiển", self.control_chars),
            ("ký tự ẩn", self.zero_width),
            ("thẻ HTML", self.html_tags),
            ("entity HTML", self.html_entities),
            ("dấu nháy", self.quotes_removed),
            ("cặp ngoặc", self.bracket_pairs_removed),
            ("ngoặc lẻ", self.brackets_removed),
            ("ký hiệu", self.symbols_replaced),
            ("quy tắc riêng", self.custom_rule_hits),
            ("dấu chấm thêm", self.periods_added),
        ):
            if value:
                bits.append(f"{label}: {value}")
        return ", ".join(bits)

    def add_detail(self, action: str, count: int, sample: str = "", note: str = "") -> None:
        if count:
            self.details.append({"action": action, "count": count, "sample": sample, "note": note})


# ------------------------------------------------------------ escaped text


def has_escaped_newlines(text: str) -> bool:
    return bool(SERIALIZED_ESCAPE_RE.search(text or ""))


def restore_escaped_newlines(text: str) -> Tuple[str, int]:
    """Turn literal ``\\n`` / ``\\r\\n`` sequences into real line breaks.

    Returns ``(text, replacements)``.  A backslash that is followed by ``n``
    inside a word (``C:\\notes``) is left alone: only sequences that look like
    serialized line breaks are restored, and a file with no literal escapes is
    returned untouched.
    """
    if not text or "\\" not in text:
        return text, 0
    replacements = 0
    result = text
    for pattern, replacement in ESCAPED_NEWLINE_PATTERNS:
        result, count = pattern.subn(replacement, result)
        replacements += count
    return result, replacements


# ---------------------------------------------------------------- spacing


def normalize_spacing(text: str) -> str:
    """Collapse repeated spaces, fix space-before-punctuation, tidy blanks."""
    if not text:
        return text
    result = text.replace("\r\n", "\n").replace("\r", "\n")
    result = result.replace("\u00a0", " ")
    result = MULTISPACE_RE.sub(" ", result)
    result = SPACE_BEFORE_PUNCT_RE.sub(r"\1", result)
    result = SPACE_AFTER_OPEN_RE.sub(r"\1", result)
    result = TRAILING_SPACE_RE.sub("", result)
    result = BLANK_LINES_RE.sub("\n\n", result)
    return result.strip("\n")


def enforce_sentence_endings(text: str, *, skip_dialogue_only: bool = False) -> Tuple[str, int]:
    """Add a period to prose lines that end without terminal punctuation."""
    if not text:
        return text, 0
    added = 0
    lines = text.split("\n")
    for index, line in enumerate(lines):
        stripped = line.rstrip()
        if not stripped.strip():
            continue
        tail = stripped[-1]
        if tail in SENTENCE_END_CHARS or tail in CLOSING_QUOTES:
            continue
        if tail in ",:;、，":
            continue
        if not PROSE_LINE_RE.search(stripped):
            continue
        if len(stripped.strip()) <= 1:
            continue
        lines[index] = stripped + "."
        added += 1
    return "\n".join(lines), added


# ------------------------------------------------------------------ helpers


def normalize_bracket_pairs(pairs: Iterable[str]) -> List[Tuple[str, str]]:
    normalized: List[Tuple[str, str]] = []
    for pair in pairs:
        if not pair:
            continue
        if len(pair) == 2:
            normalized.append((pair[0], pair[1]))
            continue
        # A pair written as "«»" may arrive with whitespace or as separate items.
        stripped = pair.strip()
        if len(stripped) == 2:
            normalized.append((stripped[0], stripped[1]))
    return normalized


def _apply_pair_mode(
    text: str, open_char: str, close_char: str, mode: str
) -> Tuple[str, int]:
    if mode == "keep" or not open_char or not close_char:
        return text, 0
    if mode == "remove":
        open_count = text.count(open_char)
        close_count = text.count(close_char)
        if not open_count and not close_count:
            return text, 0
        return text.replace(open_char, "").replace(close_char, ""), open_count + close_count
    # strip: only balanced pairs lose their delimiters, the content stays put
    if open_char not in text:
        return text, 0
    pattern = re.compile(
        re.escape(open_char) + r"([^" + re.escape(open_char + close_char) + r"]*)"
        + re.escape(close_char)
    )
    removed = 0

    def _replace(match: re.Match[str]) -> str:
        nonlocal removed
        removed += 2
        return match.group(1)

    return pattern.sub(_replace, text), removed


def _quote_chars(options: CleaningOptions) -> Tuple[str, str]:
    if options.custom_quote_chars:
        chars = options.custom_quote_chars
        return chars, chars
    return "\"“”‘’«»„‟", "\"“”‘’«»„‟"


# -------------------------------------------------------------- main pass


def clean_text(text: str, options: Optional[CleaningOptions] = None) -> Tuple[str, CleanReport]:
    """Run the TTS cleaning pass and report every change."""
    options = options or CleaningOptions()
    report = CleanReport(before_chars=len(text or ""))
    result = text or ""

    if options.remove_control_chars:
        result, count = CONTROL_CHARS_RE.subn("", result)
        report.control_chars += count
    if options.strip_zero_width:
        result, count = ZERO_WIDTH_RE.subn("", result)
        report.zero_width += count

    if options.remove_html:
        result, count = HTML_COMMENT_RE.subn("", result)
        report.html_tags += count
        result, count = HTML_BLOCK_TAG_RE.subn("\n", result)
        report.html_tags += count
        result, count = HTML_TAG_RE.subn("", result)
        report.html_tags += count

    if options.unescape_html_entities:
        entity_hits = len(re.findall(r"&(?:#\d+|#x[0-9a-fA-F]+|[a-zA-Z]+);", result))
        if entity_hits:
            decoded = html.unescape(result)
            decoded = decoded.replace("\u00a0", " ")
            if decoded != result:
                report.html_entities += entity_hits
            result = decoded

    for pair in normalize_bracket_pairs(options.bracket_pairs):
        result, count = _apply_pair_mode(result, pair[0], pair[1], options.bracket_mode)
        report.bracket_pairs_removed += count // 2
        report.brackets_removed += count

    open_quotes, close_quotes = _quote_chars(options)
    if options.quote_mode != "keep":
        for char in set(open_quotes + close_quotes):
            count = result.count(char)
            if count:
                result = result.replace(char, "")
                report.quotes_removed += count

    if options.symbol_map_enabled and options.symbol_map:
        # longest key first so multi-character symbols win over single chars
        for symbol in sorted(options.symbol_map, key=len, reverse=True):
            if not symbol:
                continue
            count = result.count(symbol)
            if count:
                result = result.replace(symbol, options.symbol_map[symbol])
                report.symbols_replaced += count

    for rule in options.custom_rules:
        pattern = (rule or {}).get("pattern", "")
        if not pattern:
            continue
        replacement = (rule or {}).get("replacement", "")
        use_regex = bool((rule or {}).get("regex", True))
        if use_regex:
            try:
                result, count = re.subn(pattern, replacement, result)
                report.custom_rule_hits += count
            except re.error:
                continue
        else:
            count = result.count(pattern)
            if count:
                result = result.replace(pattern, replacement)
                report.custom_rule_hits += count

    if options.normalize_spacing:
        before = result
        result = normalize_spacing(result)
        collapsed = before.count("\n\n\n") - result.count("\n\n\n")
        report.blank_lines_collapsed += max(0, collapsed)

    if options.drop_empty_lines:
        lines = [line for line in result.split("\n") if line.strip()]
        result = "\n".join(lines)

    if options.enforce_period:
        result, added = enforce_sentence_endings(result)
        report.periods_added += added

    report.after_chars = len(result)
    report.add_detail("clean", report.lost_chars, note="Số ký tự đã loại bỏ trong bước làm sạch.")
    return result, report
