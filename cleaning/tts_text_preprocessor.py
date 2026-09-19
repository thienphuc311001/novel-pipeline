"""Conservative, in-memory TTS sanitization. No Qt, network, or LLM calls."""
from __future__ import annotations

import html
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from typing import Any

from .tts_boundaries import (DEFAULT_ABBREVIATIONS, EMAIL_RE, URL_RE,
                             boundary_positions, protection_mask)

PREPROCESSOR_VERSION = "tts-preprocess-v2"


@dataclass
class TTSPreprocessConfig:
    enabled: bool = True
    url_policy: str = "remove"
    email_policy: str = "keep"
    remove_emoji: bool = True
    remove_html: bool = True
    remove_markdown_formatting: bool = True
    sentence_per_line: bool = False
    max_blank_lines: int = 1
    abbreviations: list[str] = field(default_factory=lambda: list(DEFAULT_ABBREVIATIONS))
    boilerplate_patterns: list[str] = field(default_factory=list)
    footnote_patterns: list[str] = field(default_factory=list)

    def __post_init__(self):
        for name in ("url_policy", "email_policy"):
            if getattr(self, name) not in {"remove", "keep", "replace"}:
                raise ValueError(f"Invalid {name}: {getattr(self, name)}")
        if not isinstance(self.max_blank_lines, int) or not 0 <= self.max_blank_lines <= 10:
            raise ValueError("max_blank_lines must be between 0 and 10")
        for name in ("abbreviations", "boilerplate_patterns", "footnote_patterns"):
            values = getattr(self, name)
            if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
                raise ValueError(f"{name} must be a list of strings")
        for pattern in self.boilerplate_patterns + self.footnote_patterns:
            re.compile(pattern)

    @classmethod
    def from_settings(cls, settings):
        values = dict(getattr(settings, "tts_preprocessing", {}) or {})
        return cls(**{k: v for k, v in values.items() if k in cls.__dataclass_fields__})


@dataclass
class TTSPreprocessResult:
    text: str
    warnings: list[str] = field(default_factory=list)
    statistics: dict[str, int] = field(default_factory=dict)
    diagnostics: list[dict[str, Any]] = field(default_factory=list)

    def summary(self):
        return "TTS preprocessing: " + ", ".join(f"{k}={v}" for k, v in self.statistics.items() if v)


# Only recognized HTML tags are stripped; <test>, arithmetic and unknown
# angle-bracket prose are retained. Structural tags never glue paragraphs.
TAG_RE = re.compile(r"</?(br|p|div|span|strong|em|b|i|u|a|li|ul|ol|h[1-6]|section|article|table|tr|td|script|style|code|pre)(?:[ \t]+[\w:-]+[ \t]*=[ \t]*(?:\"[^\"]*\"|'[^']*'|[^\s<>]+))*[ \t]*/?>", re.I | re.S)
BLOCK_TAGS = {"br", "p", "div", "li", "ul", "ol", "section", "article", "table", "tr", "pre", "h1", "h2", "h3", "h4", "h5", "h6"}
ENTITY_RE = re.compile(r"&(?:(?:amp|#0*38|#x0*26);)*(?:#[0-9]+|#x[0-9a-fA-F]+|[A-Za-z][A-Za-z0-9]+);", re.I)
DECORATION_RE = re.compile(r"^[ \t]*[-—–*=~#■◆◇★☆█•●▪_│|]{3,}[ \t]*$", re.M)
HEADING_RE = re.compile(r"^(?:Chương|Chuong|Chapter|Hồi|Quyển)\s+\d+\b", re.I)
FULLWIDTH = str.maketrans({"。": ".", "！": "!", "？": "?", "，": ",", "；": ";", "：": ":", "（": "(", "）": ")", "＂": '"', "＇": "'"})
INVISIBLE_RE = re.compile(r"[\ufeff\u200b\u2060-\u2064\u061c\u00ad\u200e\u200f\u202a-\u202e\u2066-\u2069]")
CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\U00020000-\U000323af]")
OTHER_SCRIPT_RE = re.compile(r"[\u0370-\u052f\u0590-\u05ff\u0e00-\u0eff\u1780-\u17ff\u3040-\u30ff\uac00-\ud7af\u0600-\u06ff\u0900-\u097f]")
# A valid Vietnamese ``Â`` is commonly followed by an ASCII letter (for
# example ``Ân``).  The old ``Â.`` rule therefore reported every such name as
# mojibake.  Each rule below requires a characteristic continuation sequence
# produced by a UTF-8 -> Latin-1/CP1252 decoding error instead of matching a
# single suspicious-looking character.
MOJIBAKE_RULES = (
    ("latin1-utf8", re.compile(r"[ÃÄÅÆÂ][\x80-\xBF]")),
    ("latin1-vietnamese", re.compile(r"á»[\x80-\xBF]")),
    ("cp1252-punctuation", re.compile(r"â(?:€[™œž\x80-\x9F]|[\x80-\x9F])")),
    ("utf8-bom", re.compile(r"ï»¿")),
    ("utf8-emoji", re.compile(r"ðŸ[\u0080-\u02FF]{1,2}")),
)
MOJIBAKE_RE = re.compile("|".join(f"(?:{pattern.pattern})" for _, pattern in MOJIBAKE_RULES))
REPLACEMENT_RE = re.compile("\ufffd")
EMOJI_RE = re.compile(r"[\U0001f000-\U0001faff\u2600-\u27bf\U0001f1e6-\U0001f1ff](?:[\ufe0e\ufe0f\U0001f3fb-\U0001f3ff]|\u200d[\U0001f000-\U0001faff\u2600-\u27bf])*|[0-9#*]\ufe0f?\u20e3")
ELLIPSIS_RE = re.compile(r"(?:\.(?:[ \t]*\.){2,}|…)(?:[ \t]*(?:\.|…))*")
SPACE_RE = re.compile(r"[^\S\n]{2,}|[^\S\n ]")


def _diagnostic_context(text: str, start: int, end: int, radius: int = 24) -> str:
    """Return a short, log-safe context while preserving the source value."""
    context = text[max(0, start - radius):min(len(text), end + radius)]
    return context.replace("\r", "\\r").replace("\n", "\\n")


def _collect_pattern_diagnostics(text: str, rules) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    seen_spans: set[tuple[int, int]] = set()
    for rule, pattern in rules:
        for match in pattern.finditer(text):
            start, end = match.span()
            if (start, end) in seen_spans:
                continue
            seen_spans.add((start, end))
            line = text.count("\n", 0, start) + 1
            line_start = text.rfind("\n", 0, start) + 1
            diagnostics.append({
                "rule": rule,
                "value": match.group(),
                "start": start,
                "end": end,
                "line": line,
                "column": start - line_start + 1,
                "position": start + 1,
                "context": _diagnostic_context(text, start, end),
            })
    diagnostics.sort(key=lambda item: item["position"])
    return diagnostics


def format_diagnostic_matches(diagnostics: list[dict[str, Any]], subject: str = "mojibake") -> list[str]:
    """Aggregate repeated suspicious values into concise, actionable warnings."""
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for detail in diagnostics:
        key = (str(detail.get("rule", "unknown")), str(detail.get("value", "")))
        item = grouped.setdefault(key, {"rule": key[0], "value": key[1], "items": []})
        item["items"].append(detail)

    messages = []
    for item in grouped.values():
        entries = item["items"]
        locations = ", ".join(
            f"{entry.get('section') + ' ' if entry.get('section') else ''}"
            f"line {entry['line']}, char {entry['column']} (pos {entry['position']})"
            for entry in entries
        )
        contexts = []
        for entry in entries:
            context = entry.get("context", "")
            if context and context not in contexts:
                contexts.append(context)
            if len(contexts) >= 3:
                break
        context_text = "; ".join(repr(value) for value in contexts)
        label = "possible mojibake" if subject == "mojibake" else subject
        message = (
            f'{label} rule={item["rule"]} value={item["value"]!r} '
            f'x{len(entries)} at {locations}'
        )
        if context_text:
            message += f"; context={context_text}"
        messages.append(message)
    return messages


def _decode_entities(text):
    def decode(match):
        value = match.group()
        # Decode only nested entity tokens, not the entire document repeatedly.
        while True:
            decoded = html.unescape(value)
            if decoded == value:
                return value
            value = decoded
    return ENTITY_RE.sub(decode, text)


def _markdown(text):
    # Remove paired delimiters (longest first), preserving their contents.
    text = re.sub(r"(?m)^[ \t]*```[^\n]*\n", "", text)
    text = re.sub(r"(?m)^[ \t]*```[ \t]*$", "", text)
    text = re.sub(r"(?m)^[ \t]*(?:#{1,6}[ \t]+|>[ \t]?)", "", text)
    text = re.sub(r"\[([^\]\n]+)\]\(([^)\n]+)\)", r"\1 (\2)", text)
    # Pair runs with a stack: nested delimiters and four-or-more markers
    # are removed in one pass. Arithmetic and intraword underscores stay.
    if not any(marker in text for marker in ('*', '_', '`')):
        return text
    deleted = bytearray(len(text))
    for marker in ('*', '_', '`'):
        stack = []
        for match in re.finditer(re.escape(marker) + '+', text):
            start, end = match.span()
            prev = text[start - 1] if start else ' '
            following = text[end] if end < len(text) else ' '
            if prev.isalnum() and following.isalnum():
                continue
            remaining = end - start
            if not prev.isspace() and not following.isalnum():
                consumed = 0
                while stack and remaining >= stack[-1][1] - stack[-1][0]:
                    left, right = stack.pop()
                    width = right - left
                    deleted[left:right] = b'\1' * width
                    deleted[start + consumed:start + consumed + width] = b'\1' * width
                    consumed += width
                    remaining -= width
                if consumed:
                    continue
            if not following.isspace() and not prev.isalnum():
                stack.append((start, end))
    text = ''.join(c for index, c in enumerate(text) if not deleted[index])
    return text


def _spacing(text, config, stats):
    mask = protection_mask(text, config.abbreviations)
    # Horizontal whitespace only: a newline is a meaningful prose boundary.
    text = re.sub(r"[ \t]+([,.;:!?…%\)\]\}”’»])", lambda m: m.group() if mask[m.start()] else m.group(1), text)
    mask = protection_mask(text, config.abbreviations)
    pattern = re.compile(r'''[.,!?…:;]+["'”’»\)\]\}」』】》〉]*(?=[^\W_]|[“«(\[])''')
    def insert(match):
        if any(mask[match.start():match.end()]):
            return match.group()
        stats["fixed_missing_spaces"] = stats.get("fixed_missing_spaces", 0) + 1
        return match.group() + " "
    return pattern.sub(insert, text)


def _cleanup(text, max_blank_lines):
    text = SPACE_RE.sub(" ", text)
    text = "\n".join(line.strip(" ") for line in text.split("\n"))
    text = re.sub(r"\n{" + str(max_blank_lines + 2) + r",}", "\n" * (max_blank_lines + 1), text)
    return unicodedata.normalize("NFC", text.strip())


def preprocess_with_diagnostics(text: str, config: TTSPreprocessConfig | None = None) -> TTSPreprocessResult:
    config = config or TTSPreprocessConfig()
    text = text or ""
    stats = {"input_chars": len(text)}
    warnings = []
    # Diagnose encoding damage before removing C1 control characters.
    normalized_source = unicodedata.normalize(
        "NFC", text.replace("\r\n", "\n").replace("\r", "\n").replace("\u2028", "\n")
        .replace("\u2029", "\n\n").replace("\x85", "\n")
    )
    diagnostic_source = _decode_entities(normalized_source)
    mojibake_diagnostics = _collect_pattern_diagnostics(diagnostic_source, MOJIBAKE_RULES)
    replacement_diagnostics = _collect_pattern_diagnostics(diagnostic_source, (("replacement-char", REPLACEMENT_RE),))
    mojibake = len(mojibake_diagnostics)
    if not config.enabled:
        return TTSPreprocessResult(text, [], {**stats, "output_chars": len(text)})

    # Keep suspicious source sequences byte-for-byte intact while the safe TTS
    # cleanup runs. This prevents a C1 byte such as ``\x9d`` or a non-breaking
    # space in a detected sequence from being silently removed/normalized.
    protected_mojibake: dict[str, str] = {}
    protected_replacements = []
    for index, detail in enumerate(mojibake_diagnostics):
        token = f"\ue000mojibake{index}\ue001"
        protected_mojibake[token] = detail["value"]
        protected_replacements.append((detail["start"], detail["end"], token))

    def sub_count(name, pattern, replacement, value):
        output, count = pattern.subn(replacement, value)
        stats[name] = stats.get(name, 0) + count
        return output

    text = diagnostic_source
    if protected_replacements:
        pieces, cursor = [], 0
        for start, end, token in protected_replacements:
            pieces.extend((text[cursor:start], token))
            cursor = end
        pieces.append(text[cursor:])
        text = "".join(pieces)
    text = sub_count("removed_invisible_chars", INVISIBLE_RE, "", text)
    text = sub_count("removed_control_chars", CONTROL_RE, "", text)
    if config.remove_emoji:
        text = sub_count("removed_emoji", EMOJI_RE, "", text)
    # Preserve ZWJ/ZWNJ with a linguistic role in non-Latin scripts.
    joiner_re = re.compile(r"[\u200c\u200d]")
    def joiner(match):
        neighbors = text[max(0, match.start() - 1):match.start()] + text[match.end():match.end() + 1]
        if not config.remove_emoji and any(0x2600 <= ord(c) <= 0x27bf or 0x1f000 <= ord(c) <= 0x1faff for c in neighbors):
            return match.group()
        if any(unicodedata.category(c).startswith('L') and 'LATIN' not in unicodedata.name(c, '') for c in neighbors):
            stats["preserved_script_joiners"] = stats.get("preserved_script_joiners", 0) + 1
            return match.group()
        stats["removed_invisible_chars"] = stats.get("removed_invisible_chars", 0) + 1
        return ""
    text = joiner_re.sub(joiner, text)
    text = sub_count("normalized_spaces", SPACE_RE, " ", text)
    if config.remove_html:
        # Scan comments once; an unclosed comment is preserved rather than
        # repeatedly scanning every nested opener to the end of a large novel.
        pieces, cursor = [], 0
        while True:
            start = text.find('<!--', cursor)
            if start < 0:
                break
            end = text.find('-->', start + 4)
            if end < 0:
                break
            pieces.append(text[cursor:start])
            cursor = end + 3
            stats['removed_html_comments'] = stats.get('removed_html_comments', 0) + 1
        pieces.append(text[cursor:])
        text = ''.join(pieces)
        text = sub_count("removed_html_tags", TAG_RE,
                         lambda m: "\n" if (m.group(1) or "").lower() in BLOCK_TAGS else "", text)
    text = sub_count("removed_decorative_lines", DECORATION_RE, "", text)
    if config.remove_markdown_formatting:
        text = _markdown(text)
    for pattern, policy, label, name in ((URL_RE, config.url_policy, "[đường dẫn]", "urls"), (EMAIL_RE, config.email_policy, "[email]", "emails")):
        if policy == "keep":
            continue
        def replace(match):
            value = match.group()
            end = len(value)
            while end and value[end - 1] in '.!?…,;:)]}':
                end -= 1
            return (label if policy == "replace" else " ") + value[end:]
        text = sub_count("removed_" + name if policy == "remove" else "replaced_" + name, pattern, replace, text)
    text = sub_count("removed_metadata_lines", re.compile(r"(?m)^[ \t]*(?:chapter_id|source_url)\s*=.*$"), "", text)
    for pattern in config.boilerplate_patterns:
        text = sub_count("removed_boilerplate_lines", re.compile(pattern, re.M), "", text)
    for pattern in config.footnote_patterns:
        text = sub_count("removed_footnotes", re.compile(pattern), "", text)
    text = re.sub(r"(?m)^[ \t]*[•●▪][ \t]*(.+)$", lambda m: m.group(1) if m.group(1)[-1] in '.!?…' else m.group(1) + '.', text)
    text = text.translate(FULLWIDTH)
    text = sub_count("normalized_spaces", SPACE_RE, " ", text)
    mask = protection_mask(text, config.abbreviations)
    def ellipsis(match):
        if any(mask[match.start():match.end()]):
            return match.group()
        if match.group() != "…":
            stats["normalized_ellipsis"] = stats.get("normalized_ellipsis", 0) + 1
        return "…"
    text = ELLIPSIS_RE.sub(ellipsis, text)
    mask = protection_mask(text, config.abbreviations)
    def double_period(match):
        if any(mask[match.start():match.end()]):
            return match.group()
        stats["normalized_double_period"] = stats.get("normalized_double_period", 0) + 1
        return "."
    text = re.sub(r"(?<!\.)\.[ \t]*\.(?!\.)", double_period, text)
    mask = protection_mask(text, config.abbreviations)
    def repeated(match):
        if any(mask[match.start():match.end()]):
            return match.group()
        value = match.group()
        output = "?!" if '?' in value and '!' in value else value[0]
        if value != output:
            stats["collapsed_punctuation"] = stats.get("collapsed_punctuation", 0) + 1
        return output
    text = re.sub(r"[?!](?:[ \t]*[?!])+", repeated, text)
    before = len(text)
    text = _spacing(text, config, stats)
    stats["spacing_char_delta"] = len(text) - before
    text = re.sub(r"(?m)^ *[-–—] *(?=[^\W\d_]|[\"“])", "— ", text)
    # Only a recognizable heading with an explicit terminal and following
    # uppercase prose is repaired. Unpunctuated ambiguous titles stay intact.
    lines = []
    for line in text.split("\n"):
        line = line.strip(" ")
        if HEADING_RE.match(line):
            cuts = boundary_positions(line, abbreviations=config.abbreviations)
            cut = next((c for c in cuts if line[c:].lstrip() and line[c:].lstrip()[0].isupper()), None)
            if cut:
                lines.append(line[:cut].rstrip('.…') + "\n\n" + line[cut:].lstrip())
                stats["repaired_heading_boundaries"] = stats.get("repaired_heading_boundaries", 0) + 1
                continue
        lines.append(line)
    text = "\n".join(lines)
    if config.sentence_per_line:
        cuts = boundary_positions(text, abbreviations=config.abbreviations)
        pieces, previous = [], 0
        for cut in cuts:
            pieces.append(text[previous:cut])
            if cut < len(text):
                tail = cut
                while tail < len(text) and text[tail] == ' ':
                    tail += 1
                if tail < len(text) and text[tail] != '\n':
                    pieces.append('\n')
                    cut = tail
            previous = cut
        pieces.append(text[previous:])
        text = "".join(pieces)
    text = _cleanup(text, config.max_blank_lines)
    for token, value in protected_mojibake.items():
        text = text.replace(token, value)
    diagnostics = mojibake_diagnostics + replacement_diagnostics
    for name, count in (("detected_cjk_chars", len(CJK_RE.findall(text))),
                        ("detected_other_script_chars", len(OTHER_SCRIPT_RE.findall(text))),
                        ("detected_cjk_punctuation", len(re.findall(r"[\u3001-\u303f]", text))),
                        ("detected_replacement_chars", text.count('\ufffd')),
                        ("detected_mojibake_patterns", mojibake),
                        ("preserved_script_joiners", stats.get("preserved_script_joiners", 0))):
        stats[name] = count
        if count:
            if name == "detected_mojibake_patterns":
                warnings.extend(format_diagnostic_matches(mojibake_diagnostics))
            elif name == "detected_replacement_chars":
                warnings.extend(format_diagnostic_matches(replacement_diagnostics, "replacement character"))
            else:
                warnings.append(f"{name}: {count}; preserved, review before TTS.")
    stats["output_chars"] = len(text)
    return TTSPreprocessResult(text, warnings, stats, diagnostics)


def preprocess_for_tts(text: str, config: TTSPreprocessConfig | None = None) -> str:
    return preprocess_with_diagnostics(text, config).text


def preprocessing_identity(settings):
    from .tts_boundaries import CHUNKER_VERSION
    from .textclean import CleaningOptions
    from chunking.splitter import TTS_CHUNK_TARGET
    return {"preprocessor_version": PREPROCESSOR_VERSION,
            "chunker_version": CHUNKER_VERSION,
            "preprocessing": asdict(TTSPreprocessConfig.from_settings(settings)),
            "clean_profile": "safe-tts-v1",
            "cleaning": asdict(CleaningOptions.for_tts(settings)),
            "chunk_limit": TTS_CHUNK_TARGET,
            "min_chunk_chars": settings.min_chunk_chars}
