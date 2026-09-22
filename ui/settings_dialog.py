"""Editable application settings grouped by pipeline stage."""

from __future__ import annotations

import codecs
import json
from pathlib import Path
from typing import Any, Callable, Dict

from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from chapters.patterns import validate_custom_regex
from config.settings import Settings


class SettingsDialog(QDialog):
    """A complete editor for user-facing :class:`Settings` fields."""

    HIDDEN_FIELDS = {
        "window_geometry",
        "tts_engine",
        "tts_rate",
        "tts_fallback_retry_count",
        "title_history",
    }

    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self._source = settings.clone()
        self._result = settings.clone()
        self.controls: Dict[str, QWidget] = {}
        self._readers: Dict[str, Callable[[], Any]] = {}
        self._writers: Dict[str, Callable[[Any], None]] = {}

        self.setWindowTitle("Application Settings")
        self.resize(820, 720)

        layout = QVBoxLayout(self)
        intro = QLabel(
            "Changes are saved locally and apply to subsequent pipeline actions. "
            "UI settings apply immediately."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        self._build_tabs()

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.RestoreDefaults
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        restore = self.buttons.button(QDialogButtonBox.StandardButton.RestoreDefaults)
        restore.clicked.connect(self._restore_defaults)
        layout.addWidget(self.buttons)

    # --------------------------------------------------------------- tabs
    def _tab(self, title: str) -> QFormLayout:
        content = QWidget()
        form = QFormLayout(content)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        self.tabs.addTab(scroll, title)
        return form

    def _build_tabs(self) -> None:
        form = self._tab("Input")
        self._path(form, "last_input_dir", "Last input folder")
        self._list(form, "encoding_chain", "Encoding fallback order")
        self._bool(form, "auto_insert_headers", "Insert missing chapter headers")
        self._text(form, "auto_insert_prefix", "Inserted header template")
        self._bool(form, "continuous_numbering", "Continuous numbering")
        self._bool(form, "merge_order_notes", "Record merge-order notes")

        form = self._tab("Chapters")
        self._text(form, "chapter_prefix", "Canonical chapter template")
        self._int(form, "zero_pad", "Number zero padding", 0, 12)
        self._text(form, "header_separator", "Header/title separator")
        self._bool(form, "keep_original_headers", "Keep original header style")
        self._bool(form, "detect_vietnamese", "Detect Vietnamese headers")
        self._bool(form, "detect_english", "Detect English headers")
        self._bool(form, "detect_chinese", "Detect Chinese headers")
        self._bool(form, "detect_plain_numbered", "Detect plain numbered headers (only if file has no Chương/Chapter prefix, e.g. bare '1.')")
        self._bool(form, "use_custom_chapter_regex", "Enable custom chapter regex")
        self._text(form, "custom_chapter_regex", "Custom regex")
        self._bool(form, "dedupe_chapters", "Remove duplicate chapters")
        self._bool(form, "prefer_vietnamese", "Prefer Vietnamese duplicates")
        self._bool(form, "enforce_period", "Enforce prose periods")
        self._bool(form, "normalize_spacing", "Normalize spacing")

        form = self._tab("Cleaning")
        self._bool(form, "remove_control_chars", "Remove control characters")
        self._bool(form, "remove_html", "Remove HTML")
        self._bool(form, "unescape_html_entities", "Decode HTML entities")
        self._combo(form, "quote_mode", "Quote handling", {"Keep": "keep", "Strip": "strip", "Remove": "remove"})
        self._combo(form, "bracket_mode", "Bracket handling", {"Keep": "keep", "Strip": "strip", "Remove": "remove"})
        self._list(form, "bracket_pairs", "Bracket pairs (one per line)")
        self._text(form, "custom_quote_chars", "Custom quote characters")
        self._bool(form, "symbol_map_enabled", "Replace symbols with words")
        self._json(form, "symbol_map", "Symbol replacements (JSON object)", height=190)
        self._json(form, "custom_rules", "Custom rules (JSON list)", height=160)
        self._bool(form, "drop_empty_lines", "Remove empty lines")

        form = self._tab("Chunk & Export")
        self._int(form, "min_chunk_chars", "Minimum chunk characters", 50, 20000)
        self._int(form, "max_chunk_chars", "Maximum chunk characters", 50, 20000)
        self._bool(form, "chunk_by_chapters", "Keep chunks inside chapters")
        self._combo(form, "export_encoding", "Export encoding", {"UTF-8": "utf-8", "UTF-8 with BOM": "utf-8-sig", "UTF-16": "utf-16"})
        self._text(form, "filename_template", "Filename template")
        self._bool(form, "zip_include_manifest", "Include ZIP manifest")
        self._bool(form, "zip_folder_per_range", "Folder per ZIP range")

        form = self._tab("TTS, Thumbnail & UI")
        form.addRow("TTS engine", QLabel("Edge-TTS (online)"))
        self._tts_preprocessing(form)
        self._text(form, "tts_voice", "TTS voice")
        self._int(form, "tts_max_concurrency", "Maximum concurrent requests", 1, 100)
        self._int(form, "tts_timeout_seconds", "Chunk timeout (seconds)", 10, 600)
        self._int(form, "tts_retry_count", "Attempts per chunk", 1, 10)
        self._bool(form, "channel_intro_enabled", "Play fixed channel intro first")
        self._text(form, "channel_intro_text", "Channel intro text (fixed)")
        self._text(form, "channel_intro_voice", "Channel intro voice (empty = follow TTS voice)")
        form.addRow("Step 3 chunk target", QLabel("700 characters · full-chunk retries"))
        self._int(form, "thumbnail_jpeg_quality", "Thumbnail JPEG quality", 70, 100)
        self._file_path(form, "qr_image_path", "Suggested QR image (Create Video step)",
                        "Images (*.png *.jpg *.jpeg *.webp *.bmp)")
        self._int(form, "font_size", "Application font size", 7, 32)
        self._int(form, "max_log_lines", "Maximum diagnostic lines", 100, 100000)

        form = self._tab("YouTube")
        note = QLabel(
            "Enable YouTube Data API v3 in your Google Cloud project and create an "
            "OAuth client of type Desktop app. Choose its downloaded JSON once. "
            "Sign-in tokens are stored in your operating system credential store."
        )
        note.setWordWrap(True)
        form.addRow(note)
        self._text(form, "youtube_client_secrets_path", "Desktop OAuth client JSON")
        browse = QPushButton("Choose OAuth client JSON…")
        browse.clicked.connect(self._browse_youtube_client)
        form.addRow("", browse)

    def _browse_youtube_client(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Desktop OAuth client configuration", "", "JSON files (*.json)"
        )
        if path:
            self.controls["youtube_client_secrets_path"].setText(path)

    # ------------------------------------------------------------ controls
    def _register(
        self,
        form: QFormLayout,
        name: str,
        label: str,
        widget: QWidget,
        reader: Callable[[], Any],
        writer: Callable[[Any], None],
    ) -> None:
        self.controls[name] = widget
        self._readers[name] = reader
        self._writers[name] = writer
        writer(getattr(self._source, name))
        form.addRow(label, widget)

    def _bool(self, form: QFormLayout, name: str, label: str) -> None:
        widget = QCheckBox()
        self._register(form, name, label, widget, widget.isChecked, widget.setChecked)

    def _int(self, form: QFormLayout, name: str, label: str, minimum: int, maximum: int) -> None:
        widget = QSpinBox()
        widget.setRange(minimum, maximum)
        self._register(form, name, label, widget, widget.value, widget.setValue)

    def _text(self, form: QFormLayout, name: str, label: str, *, password: bool = False) -> None:
        widget = QLineEdit()
        if password:
            widget.setEchoMode(QLineEdit.EchoMode.Password)
        self._register(form, name, label, widget, widget.text, lambda value: widget.setText(str(value or "")))

    def _combo(self, form: QFormLayout, name: str, label: str, choices: Dict[str, str]) -> None:
        widget = QComboBox()
        for display, value in choices.items():
            widget.addItem(display, value)

        def write(value: Any) -> None:
            index = widget.findData(value)
            if index < 0:
                widget.addItem(str(value), value)
                index = widget.count() - 1
            widget.setCurrentIndex(index)

        self._register(form, name, label, widget, widget.currentData, write)

    def _list(self, form: QFormLayout, name: str, label: str) -> None:
        widget = QTextEdit()
        widget.setMaximumHeight(110)

        def read() -> list[str]:
            return [line.strip() for line in widget.toPlainText().splitlines() if line.strip()]

        self._register(
            form,
            name,
            label,
            widget,
            read,
            lambda value: widget.setPlainText("\n".join(str(item) for item in (value or []))),
        )

    def _json(self, form: QFormLayout, name: str, label: str, *, height: int) -> None:
        widget = QTextEdit()
        widget.setMaximumHeight(height)

        def read() -> Any:
            raw = widget.toPlainText().strip()
            return json.loads(raw) if raw else None

        self._register(
            form,
            name,
            label,
            widget,
            read,
            lambda value: widget.setPlainText(json.dumps(value, ensure_ascii=False, indent=2)),
        )

    def _path(self, form: QFormLayout, name: str, label: str) -> None:
        container = QWidget()
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        editor = QLineEdit()
        browse = QPushButton("Browse…")
        browse.clicked.connect(lambda: self._browse_directory(editor, label))
        row.addWidget(editor)
        row.addWidget(browse)
        self._register(
            form,
            name,
            label,
            container,
            editor.text,
            lambda value: editor.setText(str(value or "")),
        )

    def _browse_directory(self, editor: QLineEdit, label: str) -> None:
        current = Path(editor.text()).expanduser() if editor.text().strip() else Path.home()
        selected = QFileDialog.getExistingDirectory(self, label, str(current))
        if selected:
            editor.setText(selected)

    def _file_path(self, form: QFormLayout, name: str, label: str, file_filter: str) -> None:
        container = QWidget()
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        editor = QLineEdit()
        browse = QPushButton("Browse…")
        browse.clicked.connect(lambda: self._browse_file(editor, label, file_filter))
        row.addWidget(editor)
        row.addWidget(browse)
        self._register(
            form,
            name,
            label,
            container,
            editor.text,
            lambda value: editor.setText(str(value or "")),
        )

    def _browse_file(self, editor: QLineEdit, label: str, file_filter: str) -> None:
        current = Path(editor.text()).expanduser() if editor.text().strip() else Path.home()
        selected, _ = QFileDialog.getOpenFileName(self, label, str(current), file_filter)
        if selected:
            editor.setText(selected)

    def _tts_preprocessing(self, form):
        from dataclasses import asdict
        from cleaning.tts_text_preprocessor import TTSPreprocessConfig
        container = QWidget()
        layout = QFormLayout(container)
        enabled, emoji, sentences = QCheckBox(), QCheckBox(), QCheckBox()
        url, email = QComboBox(), QComboBox()
        for combo in (url, email):
            for policy in ("remove", "keep", "replace"):
                combo.addItem(policy, policy)
        advanced = QTextEdit()
        advanced.setMaximumHeight(110)
        for label, widget in (("Enable text preprocessing", enabled), ("URL policy", url),
                              ("Email policy", email), ("Remove decorative emoji", emoji),
                              ("One sentence per line", sentences), ("Advanced options (JSON)", advanced)):
            layout.addRow(label, widget)
        basic = {"enabled", "remove_emoji", "sentence_per_line", "url_policy", "email_policy"}
        def write(values):
            config = TTSPreprocessConfig(**values)
            enabled.setChecked(config.enabled)
            emoji.setChecked(config.remove_emoji)
            sentences.setChecked(config.sentence_per_line)
            url.setCurrentIndex(url.findData(config.url_policy))
            email.setCurrentIndex(email.findData(config.email_policy))
            advanced.setPlainText(json.dumps({k: v for k, v in asdict(config).items() if k not in basic}, ensure_ascii=False, indent=2))
        def read():
            values = json.loads(advanced.toPlainText())
            if not isinstance(values, dict):
                raise ValueError("Preprocessing options must be a JSON object")
            values.update(enabled=enabled.isChecked(), remove_emoji=emoji.isChecked(),
                          sentence_per_line=sentences.isChecked(), url_policy=url.currentData(), email_policy=email.currentData())
            return asdict(TTSPreprocessConfig(**values))
        self._register(form, "tts_preprocessing", "TTS text preparation", container, read, write)

    # ---------------------------------------------------------- validation
    def _collect(self) -> Settings:
        data = self._source.to_dict()
        for name, reader in self._readers.items():
            try:
                data[name] = reader()
            except (TypeError, ValueError, json.JSONDecodeError) as error:
                raise ValueError(f"Invalid value for {name}: {error}") from error

        if not isinstance(data.get("symbol_map"), dict):
            raise ValueError("Symbol replacements must be a JSON object.")
        if not isinstance(data.get("custom_rules"), list) or not all(
            isinstance(rule, dict) for rule in data["custom_rules"]
        ):
            raise ValueError("Custom rules must be a JSON list of objects.")

        settings = Settings.from_dict(data)
        if not settings.encoding_chain:
            raise ValueError("Encoding fallback order cannot be empty.")
        for encoding in settings.encoding_chain:
            try:
                codecs.lookup(encoding)
            except LookupError as error:
                raise ValueError(f"Unknown encoding: {encoding}") from error
        invalid_pairs = [pair for pair in settings.bracket_pairs if len(pair) != 2]
        if invalid_pairs:
            raise ValueError("Every bracket pair must contain exactly two characters.")
        if settings.min_chunk_chars > settings.max_chunk_chars:
            raise ValueError("Minimum chunk size cannot exceed maximum chunk size.")
        voice = str(data.get("tts_voice") or "").strip()
        if not voice:
            raise ValueError("TTS voice cannot be empty (for example: vi-VN-HoaiMyNeural).")
        settings.tts_voice = voice
        if settings.use_custom_chapter_regex:
            validate_custom_regex(settings.custom_chapter_regex)
        return settings

    def accept(self) -> None:
        try:
            self._result = self._collect()
        except ValueError as error:
            QMessageBox.warning(self, "Invalid Settings", str(error))
            return
        super().accept()

    def updated_settings(self) -> Settings:
        return self._result.clone()

    def _restore_defaults(self) -> None:
        defaults = Settings()
        for name, writer in self._writers.items():
            writer(getattr(defaults, name))

    def editable_fields(self) -> set[str]:
        return set(self.controls)
