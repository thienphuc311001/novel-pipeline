"""Detection and unwrapping of JSON translation artifacts.

Scraped / machine translated novels are frequently exported as JSON where the
chapter text is nested inside translation objects::

    {"chapters": [{"number": 12, "original": "第一二章…",
                   "translated": "Chương 12…", "text": "…"}]}

The chapter cleaner must see plain chapter text, so the JSON wrapper is
unwrapped.  Every unwrap decision is reported (which field won, which fields
were skipped and how many characters they held) so no text disappears silently.
The parsed structure is kept so translated JSON export can preserve it.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

TEXT_KEYS: Sequence[str] = (
    "translated_text",
    "translated",
    "translation",
    "vi",
    "vietnamese",
    "tieng_viet",
    "tiếng_việt",
    "noi_dung",
    "noidung",
    "text",
    "content",
    "chapter_text",
    "chaptertext",
    "body",
    "value",
    "result",
    "output",
    "original_text",
    "original",
    "source",
    "source_text",
    "raw",
    "raw_text",
    "zh",
    "chinese",
)

TRANSLATION_KEYS = {
    "translated_text",
    "translated",
    "translation",
    "vi",
    "vietnamese",
    "tieng_viet",
    "tiếng_việt",
    "noi_dung",
    "noidung",
}

ORIGINAL_KEYS = {"original_text", "original", "source", "source_text", "zh", "chinese", "raw", "raw_text"}
TITLE_KEYS = ("title", "chapter_title", "chaptertitle", "name", "ten", "tên", "tieu_de", "tiêu_đề")
NUMBER_KEYS = ("number", "chapter", "chapter_number", "chap", "index", "stt", "id")
CONTAINER_KEYS = ("chapters", "chapter", "data", "items", "results", "list", "content", "payload", "output")
SKIP_KEYS = ("meta", "metadata", "info", "stats", "usage", "prompt", "tokens")


@dataclass
class UnwrapArtifact:
    """A JSON node that was unwrapped or deliberately skipped."""

    path: str
    key: str
    chars: int
    action: str  # "used" | "skipped" | "preferred-over"
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"path": self.path, "key": self.key, "chars": self.chars, "action": self.action, "reason": self.reason}


@dataclass
class JSONUnwrapResult:
    text: str
    is_json: bool = False
    structure: Any = None
    artifacts: List[UnwrapArtifact] = field(default_factory=list)
    blocks: List[Dict[str, Any]] = field(default_factory=list)
    original_chars: int = 0
    notes: List[str] = field(default_factory=list)

    @property
    def unwrapped_chars(self) -> int:
        return len(self.text)

    def skipped_chars(self) -> int:
        return sum(a.chars for a in self.artifacts if a.action == "skipped")


_LEADING_HEADER = re.compile(
    r"^\s*(?:Chương|Chuong|Hồi|Hoi|Quyển|Quyen|Phần|Phan|Chapter|Chap|第)",
    re.IGNORECASE,
)


def looks_like_json(text: str) -> bool:
    """Cheap structural check: does *text* start like JSON and parse?"""
    if not text:
        return False
    stripped = text.strip()
    if not stripped or stripped[0] not in "[{":
        return False
    return parse_json(stripped) is not None


def parse_json(text: str) -> Any:
    """Parse *text* as JSON, tolerating trailing junk after the root value."""
    if text is None:
        return None
    stripped = text.strip()
    if not stripped:
        return None
    try:
        return json.loads(stripped)
    except (ValueError, TypeError):
        pass
    try:
        value, _end = json.JSONDecoder().raw_decode(stripped)
        return value
    except (ValueError, TypeError):
        return None


def _key_kind(key: str) -> str:
    lowered = key.strip().lower()
    if lowered in TRANSLATION_KEYS:
        return "translation"
    if lowered in ORIGINAL_KEYS:
        return "original"
    return "text"


def _is_text_key(key: str) -> bool:
    lowered = key.strip().lower()
    if lowered in TEXT_KEYS:
        return True
    return lowered.endswith("_text") or lowered.endswith("_content")


def _text_score(key: str, value: str, prefer_translation: bool) -> Tuple[int, int, int]:
    """Rank a candidate text field: (is_translation_first, length, key_priority)."""
    lowered = key.strip().lower()
    try:
        priority = len(TEXT_KEYS) - list(TEXT_KEYS).index(lowered)
    except ValueError:
        priority = 0
    kind = _key_kind(key)
    if prefer_translation:
        first = 1 if kind == "translation" else (0 if kind == "text" else -1)
    else:
        first = 1 if kind == "original" else (0 if kind == "text" else -1)
    return (first, len(value), priority)


class _Unwrapper:
    def __init__(self, *, prefer_translation: bool = True, include_headers: bool = True) -> None:
        self.prefer_translation = prefer_translation
        self.include_headers = include_headers
        self.artifacts: List[UnwrapArtifact] = []
        self.blocks: List[Dict[str, Any]] = []

    # ------------------------------------------------------------- helpers
    def _first(self, data: Dict[str, Any], keys: Iterable[str]) -> Optional[str]:
        lowered = {str(k).strip().lower(): k for k in data}
        for wanted in keys:
            actual = lowered.get(wanted)
            if actual is not None and data[actual] not in (None, ""):
                return actual
        return None

    def _visit(self, node: Any, path: str) -> None:
        if isinstance(node, str):
            if node.strip():
                self._add_text_block(path, "", node, {})
            return
        if isinstance(node, (int, float, bool)) or node is None:
            return
        if isinstance(node, list):
            for index, item in enumerate(node):
                self._visit(item, f"{path}[{index}]")
            return
        if isinstance(node, dict):
            self._visit_dict(node, path)
            return

    def _visit_dict(self, node: Dict[str, Any], path: str) -> None:
        candidates = [
            (key, value)
            for key, value in node.items()
            if _is_text_key(key) and isinstance(value, str) and value.strip()
        ]
        number_key = self._first(node, NUMBER_KEYS)
        title_key = self._first(node, TITLE_KEYS)
        title = str(node[title_key]).strip() if title_key else ""
        number = node.get(number_key) if number_key else None

        if candidates:
            ranked = sorted(
                candidates,
                key=lambda item: _text_score(item[0], item[1], self.prefer_translation),
                reverse=True,
            )
            winner_key, winner_value = ranked[0]
            for key, value in ranked[1:]:
                self.artifacts.append(
                    UnwrapArtifact(
                        path=path,
                        key=key,
                        chars=len(value),
                        action="skipped",
                        reason=f"Đã dùng trường '{winner_key}' (ưu tiên bản dịch).",
                    )
                )
            self.artifacts.append(
                UnwrapArtifact(
                    path=path,
                    key=winner_key,
                    chars=len(winner_value),
                    action="used",
                    reason="Trường văn bản chương được giải bọc.",
                )
            )
            self._add_text_block(path, winner_key, winner_value, {"title": title, "number": number})
            for key, value in node.items():
                if key in (winner_key, number_key, title_key):
                    continue
                if isinstance(value, (dict, list)):
                    self._visit(value, f"{path}.{key}")
                elif isinstance(value, str) and value.strip() and not _is_text_key(key):
                    lowered = str(key).strip().lower()
                    if lowered in SKIP_KEYS:
                        self.artifacts.append(
                            UnwrapArtifact(
                                path=f"{path}.{key}",
                                key=key,
                                chars=len(value),
                                action="skipped",
                                reason="Trường metadata, không phải nội dung chương.",
                            )
                        )
            return

        for key, value in node.items():
            lowered = str(key).strip().lower()
            if isinstance(value, str) and value.strip():
                if lowered in SKIP_KEYS:
                    self.artifacts.append(
                        UnwrapArtifact(
                            path=f"{path}.{key}",
                            key=key,
                            chars=len(value),
                            action="skipped",
                            reason="Trường metadata, không phải nội dung chương.",
                        )
                    )
                    continue
                self._add_text_block(f"{path}.{key}", key, value, {"number": number, "title": title})
                continue
            self._visit(value, f"{path}.{key}" if path else str(key))

    def _add_text_block(self, path: str, key: str, value: str, meta: Dict[str, Any]) -> None:
        self.blocks.append({"path": path, "key": key, "text": value, "meta": meta})

    # ------------------------------------------------------------- output
    def build_text(self) -> str:
        parts: List[str] = []
        for block in self.blocks:
            text = block["text"]
            meta = block.get("meta") or {}
            title = str(meta.get("title") or "").strip()
            number = meta.get("number")
            header = ""
            already_headed = bool(_LEADING_HEADER.match(text)) or bool(_LEADING_HEADER.match(title))
            if self.include_headers and title and not already_headed:
                header = f"Chương {number}: {title}" if number is not None else title
            elif self.include_headers and number is not None and not already_headed:
                try:
                    header = f"Chương {int(number)}"
                except (TypeError, ValueError):
                    header = ""
            piece = f"{header}\n{text}" if header else text
            parts.append(piece.strip("\n"))
        return "\n\n".join(part for part in parts if part.strip())


def unwrap_json_text(
    text: str,
    *,
    prefer_translation: bool = True,
    include_headers: bool = True,
) -> JSONUnwrapResult:
    """Unwrap JSON translation artifacts into plain chapter text."""
    original_chars = len(text or "")
    structure = parse_json(text or "")
    if structure is None or isinstance(structure, (int, float, bool)):
        return JSONUnwrapResult(text=text or "", is_json=False, original_chars=original_chars)

    unwrapper = _Unwrapper(prefer_translation=prefer_translation, include_headers=include_headers)
    root_path = "$"
    if isinstance(structure, dict):
        container_key = None
        for key in structure:
            if str(key).strip().lower() in CONTAINER_KEYS and isinstance(structure[key], (list, dict)):
                container_key = key
                break
        if container_key is not None and all(
            not _is_text_key(str(k)) or not isinstance(v, str) for k, v in structure.items()
        ):
            unwrapper._visit(structure[container_key], f"$.{container_key}")
            for key, value in structure.items():
                if key == container_key:
                    continue
                if isinstance(value, str) and value.strip() and str(key).strip().lower() in SKIP_KEYS:
                    unwrapper.artifacts.append(
                        UnwrapArtifact(
                            path=f"$.{key}",
                            key=str(key),
                            chars=len(value),
                            action="skipped",
                            reason="Trường metadata cấp gốc.",
                        )
                    )
        else:
            unwrapper._visit(structure, root_path)
    else:
        unwrapper._visit(structure, root_path)

    plain = unwrapper.build_text()
    notes: List[str] = []
    if plain:
        notes.append(
            f"Đã giải bọc JSON: {len(unwrapper.blocks)} khối văn bản, "
            f"{original_chars} -> {len(plain)} ký tự."
        )
    skipped = sum(a.chars for a in unwrapper.artifacts if a.action == "skipped")
    if skipped:
        notes.append(f"Bỏ qua {skipped} ký tự metadata/trường không dùng (xem chi tiết trong báo cáo).")
    return JSONUnwrapResult(
        text=plain,
        is_json=True,
        structure=structure,
        artifacts=unwrapper.artifacts,
        blocks=unwrapper.blocks,
        original_chars=original_chars,
        notes=notes,
    )
