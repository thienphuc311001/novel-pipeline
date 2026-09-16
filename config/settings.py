"""Local configuration for the unified novel pipeline application.

Everything is stored in a small JSON file under the user config directory.
No mandatory cloud dependency. Normalization and review work offline;
AI translation, Edge-TTS, and YouTube upload use network services when invoked.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

APP_DIR_NAME = "novel-pipeline-v2"
CONFIG_FILE_NAME = "config.json"
DEFAULT_TTS_VOICE = "vi-VN-HoaiMyNeural"

# ---------------------------------------------------------------- constants

ENCODING_CHAIN: List[str] = [
    "utf-8-sig",
    "utf-8",
    "utf-16",
    "utf-32",
    "cp1258",  # Vietnamese
    "cp1252",
    "latin-1",
]

DEFAULT_SYMBOL_MAP: Dict[str, str] = {
    "&": " và ",
    "<": " nhỏ hơn ",
    ">": " lớn hơn ",
    "%": " phần trăm ",
    "+": " cộng ",
    "=": " bằng ",
    "*": " sao ",
    "@": " a còng ",
    "#": " thăng ",
    "$": " đô la ",
    "~": " xấp xỉ ",
    "^": " mũ ",
    "|": " sổ dọc ",
    "\\": " gạch chéo ngược ",
    "/": " trên ",
    "_": " gạch dưới ",
    "©": " bản quyền ",
    "®": " đã đăng ký ",
    "™": " thương hiệu ",
    "€": " euro ",
    "£": " bảng Anh ",
    "°": " độ ",
    "±": " cộng trừ ",
    "×": " nhân ",
    "÷": " chia ",
    "→": " đến ",
    "←": " từ ",
}

DEFAULT_BRACKET_PAIRS: List[str] = [
    "()",
    "[]",
    "{}",
    "（）",
    "【】",
    "「」",
    "『』",
    "《》",
    "〈〉",
    "〔〕",
    "[]",
    "“”",
    "‘’",
    "\"\"",
    "''",
]

# ---------------------------------------------------------------- helpers


def config_dir() -> Path:
    """Return the directory used to persist settings and the API key."""
    override = os.environ.get("NOVEL_PIPELINE_CONFIG_DIR")
    if override:
        return Path(override).expanduser()
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg).expanduser() / APP_DIR_NAME
    home = Path.home()
    if os.access(str(home), os.W_OK):
        return home / ".config" / APP_DIR_NAME
    return Path(tempfile.gettempdir()) / APP_DIR_NAME


def config_path() -> Path:
    return config_dir() / CONFIG_FILE_NAME


# ---------------------------------------------------------------- settings


@dataclass
class Settings:
    """Shared settings for every stage of the pipeline."""

    # --- input / encoding -------------------------------------------------
    encoding_chain: List[str] = field(default_factory=lambda: list(ENCODING_CHAIN))
    last_input_dir: str = ""
    auto_insert_headers: bool = False
    auto_insert_prefix: str = "Chương {n}"
    continuous_numbering: bool = True
    merge_order_notes: bool = True

    # --- chapter normalization -------------------------------------------
    chapter_prefix: str = "Chương {n}"
    zero_pad: int = 0
    header_separator: str = ": "
    keep_original_headers: bool = False
    detect_vietnamese: bool = True
    detect_english: bool = True
    detect_chinese: bool = True
    detect_plain_numbered: bool = True
    use_custom_chapter_regex: bool = False
    custom_chapter_regex: str = ""
    dedupe_chapters: bool = True
    prefer_vietnamese: bool = True
    enforce_period: bool = True
    normalize_spacing: bool = True

    # --- text cleaning for TTS -------------------------------------------
    remove_control_chars: bool = True
    remove_html: bool = True
    unescape_html_entities: bool = True
    quote_mode: str = "strip"  # "keep" | "strip" | "remove"
    bracket_mode: str = "strip"
    bracket_pairs: List[str] = field(default_factory=lambda: list(DEFAULT_BRACKET_PAIRS))
    custom_quote_chars: str = ""
    symbol_map_enabled: bool = True
    symbol_map: Dict[str, str] = field(default_factory=lambda: dict(DEFAULT_SYMBOL_MAP))
    custom_rules: List[Dict[str, Any]] = field(default_factory=list)
    drop_empty_lines: bool = False

    # --- chinese review ---------------------------------------------------
    chinese_extraction_mode: str = "segments"  # "segments" | "line"
    chinese_context_chars: int = 0
    dictionary_enabled: bool = True
    dictionary_paths: List[str] = field(default_factory=list)

    # --- translation ------------------------------------------------------
    ai_enabled: bool = False
    gemini_model: str = "gemini-2.0-flash"
    gemini_api_key: str = ""
    ai_batch_size: int = 40
    ai_target_language: str = "Vietnamese"
    ai_timeout: int = 60

    # --- chunking ---------------------------------------------------------
    max_chunk_chars: int = 1200
    min_chunk_chars: int = 200
    chunk_by_chapters: bool = True

    # --- export -----------------------------------------------------------
    output_dir: str = ""
    export_encoding: str = "utf-8"
    filename_template: str = "novel_{tag}"
    zip_include_manifest: bool = True
    zip_folder_per_range: bool = False

    # --- tts --------------------------------------------------------------
    tts_engine: str = "edge-tts"
    tts_voice: str = DEFAULT_TTS_VOICE
    tts_rate: int = 175
    tts_max_concurrency: int = 60
    tts_timeout_seconds: int = 120
    tts_retry_count: int = 5
    tts_fallback_retry_count: int = 3

    # --- thumbnail --------------------------------------------------------
    thumbnail_bottom_height: int = 145
    thumbnail_jpeg_quality: int = 95

    # OAuth desktop client configuration only; tokens live in the OS keyring.
    youtube_client_secrets_path: str = ""

    # --- ui ---------------------------------------------------------------
    font_size: int = 10
    max_log_lines: int = 2000
    title_history: List[str] = field(default_factory=list)
    window_geometry: str = ""

    # ---------------------------------------------------------------- io
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Settings":
        known = {f for f in cls.__dataclass_fields__}
        kwargs = {k: v for k, v in (data or {}).items() if k in known}
        settings = cls(**kwargs)
        if not isinstance(settings.symbol_map, dict):
            settings.symbol_map = dict(DEFAULT_SYMBOL_MAP)
        if not isinstance(settings.bracket_pairs, list):
            settings.bracket_pairs = list(DEFAULT_BRACKET_PAIRS)
        if not isinstance(settings.custom_rules, list):
            settings.custom_rules = []
        if not isinstance(settings.encoding_chain, list) or not settings.encoding_chain:
            settings.encoding_chain = list(ENCODING_CHAIN)
        if not isinstance(settings.title_history, list):
            settings.title_history = []
        settings.title_history = list(dict.fromkeys(
            str(title).strip() for title in settings.title_history if str(title).strip()
        ))
        settings.tts_voice = str(settings.tts_voice or "").strip() or DEFAULT_TTS_VOICE
        return settings

    @classmethod
    def load(cls, path: Path | None = None) -> "Settings":
        path = path or config_path()
        try:
            with open(path, "r", encoding="utf-8") as handle:
                return cls.from_dict(json.load(handle))
        except (OSError, ValueError):
            return cls()

    def to_dict(self) -> Dict[str, Any]:
        data = {name: getattr(self, name) for name in self.__dataclass_fields__}
        data["tts_voice"] = str(data.get("tts_voice") or "").strip() or DEFAULT_TTS_VOICE
        return data

    def save(self, path: Path | None = None) -> Path:
        path = path or config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as handle:
            handle.write(payload)
        os.replace(tmp, path)
        try:  # the file holds an API key
            os.chmod(path, 0o600)
        except OSError:
            pass
        return path

    def clone(self) -> "Settings":
        return Settings.from_dict(json.loads(json.dumps(self.to_dict(), ensure_ascii=False)))

    # ------------------------------------------------------------ helpers
    def resolved_output_dir(self, input_dir: str | Path | None = None) -> Path:
        """Return the output root, preferring an explicit user override.

        When no override is configured, artifacts belong beside the current
        Step 1 input.  The historical home-directory fallback remains useful
        for callers that do not yet have a loaded document.
        """
        if self.output_dir:
            return Path(self.output_dir).expanduser()
        if input_dir:
            return Path(input_dir).expanduser()
        return Path.home() / "novel-pipeline-output"

    def resolved_input_dir(self) -> str:
        """Return the last usable input folder for a file picker."""
        if not self.last_input_dir:
            return ""
        path = Path(self.last_input_dir).expanduser()
        return str(path) if path.is_dir() else ""

    def clamp_chunk_size(self) -> int:
        minimum = max(50, int(self.min_chunk_chars or 200))
        size = int(self.max_chunk_chars or 3000)
        return max(minimum, min(size, 20000))
