"""Main application window with pipeline stages."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTabWidget,
    QTextEdit,
    QPushButton,
    QLabel,
    QFileDialog,
    QMessageBox,
    QComboBox,
    QLineEdit,
    QGroupBox,
    QFormLayout,
)

from config.settings import Settings
from pipeline.document import (
    PipelineDocument,
    PipelineStateError,
    StageKey,
    derive_chapters_from_text,
    render_chapters_text,
)


class MainWindow(QMainWindow):
    """Main window with four-stage pipeline tabs."""

    def __init__(self, settings: Settings, parent=None, *, master_dictionary=None):
        super().__init__(parent)
        self.settings = settings
        self.document = PipelineDocument()
        self._updating_widgets = False
        self._updating_review_widgets = False
        self._manual_edit_mode = False
        self._master_dictionary = master_dictionary
        self._dictionary_attempted = master_dictionary is not None
        self._dictionary_error = ""
        
        self.setWindowTitle("Novel Pipeline v2")
        self.resize(1400, 900)
        
        self._setup_ui()
        self._apply_runtime_settings()
        self._update_status()

    def _setup_ui(self):
        """Build the main layout."""
        central = QWidget()
        self.setCentralWidget(central)
        
        layout = QVBoxLayout(central)
        
        # Top toolbar
        toolbar = QHBoxLayout()
        
        self.load_btn = QPushButton("📁 Load Files")
        self.load_btn.clicked.connect(self._on_load)
        toolbar.addWidget(self.load_btn)
        
        self.settings_btn = QPushButton("⚙ Settings")
        self.settings_btn.clicked.connect(self._on_open_settings)
        toolbar.addWidget(self.settings_btn)
        
        toolbar.addStretch()
        
        self.status_label = QLabel("Ready")
        toolbar.addWidget(self.status_label)
        
        layout.addLayout(toolbar)
        
        # Pipeline tabs
        self.tabs = QTabWidget()
        
        # Stage 1: Input & Normalize
        self.stage1_widget = self._create_stage1_tab()
        self.tabs.addTab(self.stage1_widget, "1️⃣ Input & Normalize")
        
        # Stage 2: Chinese Review
        self.stage2_widget = self._create_stage2_tab()
        self.tabs.addTab(self.stage2_widget, "2️⃣ Chinese Review")
        
        # Stage 3: Clean & Chunk
        self.stage3_widget = self._create_stage3_tab()
        self.tabs.addTab(self.stage3_widget, "3️⃣ Clean & Chunk")
        
        # Stage 4: Filter & Export
        self.stage4_widget = self._create_stage4_tab()
        self.tabs.addTab(self.stage4_widget, "4️⃣ Filter & Export")
        self.tabs.currentChanged.connect(self._on_tab_changed)
        
        layout.addWidget(self.tabs)
        
        # Bottom status panel
        self.status_text = QTextEdit()
        self.status_text.setReadOnly(True)
        self.status_text.setMaximumHeight(150)
        layout.addWidget(QLabel("Status & Diagnostics:"))
        layout.addWidget(self.status_text)

    def _create_stage1_tab(self) -> QWidget:
        """Input loading and chapter normalization."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        btn_layout = QHBoxLayout()
        
        load_txt_btn = QPushButton("Load TXT/ZIP")
        load_txt_btn.clicked.connect(self._on_load)
        btn_layout.addWidget(load_txt_btn)
        
        normalize_btn = QPushButton("▶️ Normalize Chapters")
        normalize_btn.clicked.connect(self._on_normalize)
        btn_layout.addWidget(normalize_btn)

        continue_btn = QPushButton("Next / Continue to Step 2 →")
        continue_btn.clicked.connect(self._continue_to_stage2)
        btn_layout.addWidget(continue_btn)
        
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
        
        self.stage1_output = QTextEdit()
        self.stage1_output.setReadOnly(True)
        self.stage1_output.textChanged.connect(self._on_stage1_text_changed)
        layout.addWidget(self.stage1_output)
        
        return widget

    def _create_stage2_tab(self) -> QWidget:
        """Sentence-based Chinese residue review."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        btn_layout = QHBoxLayout()
        
        self.stage2_scan_btn = QPushButton("🔍 Rescan Chinese")
        self.stage2_scan_btn.clicked.connect(self._on_scan_chinese)
        btn_layout.addWidget(self.stage2_scan_btn)

        self.stage2_continue_btn = QPushButton("Continue to Step 3 →")
        self.stage2_continue_btn.setEnabled(False)
        self.stage2_continue_btn.clicked.connect(self._continue_to_stage3)
        btn_layout.addWidget(self.stage2_continue_btn)
        
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        self.stage2_source_label = QLabel("Source: No input loaded")
        layout.addWidget(self.stage2_source_label)

        self.stage2_dictionary_label = QLabel("Master dictionary: not initialized")
        self.stage2_dictionary_label.setWordWrap(True)
        layout.addWidget(self.stage2_dictionary_label)

        self.stage2_progress_label = QLabel("Total sentences: 0    Resolved: 0    Remaining: 0")
        layout.addWidget(self.stage2_progress_label)

        self.stage2_input_preview = QTextEdit()
        self.stage2_input_preview.setReadOnly(True)
        self.stage2_input_preview.setPlaceholderText("The exact Step 2 input will appear here.")
        self.stage2_input_preview.setMaximumHeight(170)
        layout.addWidget(self.stage2_input_preview)

        review_group = QGroupBox("Current review sentence")
        review_layout = QVBoxLayout(review_group)

        nav_layout = QHBoxLayout()
        self.stage2_previous_btn = QPushButton("← Previous")
        self.stage2_previous_btn.clicked.connect(self._on_review_previous)
        nav_layout.addWidget(self.stage2_previous_btn)
        self.stage2_position_label = QLabel("No Chinese residue")
        self.stage2_position_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        nav_layout.addWidget(self.stage2_position_label, 1)
        self.stage2_next_btn = QPushButton("Next →")
        self.stage2_next_btn.clicked.connect(self._on_review_next)
        nav_layout.addWidget(self.stage2_next_btn)
        review_layout.addLayout(nav_layout)

        self.stage2_sentence_text = QTextEdit()
        self.stage2_sentence_text.setReadOnly(True)
        self.stage2_sentence_text.setMaximumHeight(105)
        review_layout.addWidget(self.stage2_sentence_text)

        form = QFormLayout()
        self.stage2_fragment_combo = QComboBox()
        self.stage2_fragment_combo.currentIndexChanged.connect(self._on_fragment_changed)
        form.addRow("Chinese:", self.stage2_fragment_combo)

        self.stage2_fragment_status = QLabel("")
        form.addRow("Status:", self.stage2_fragment_status)

        self.stage2_suggestion_combo = QComboBox()
        self.stage2_suggestion_combo.currentIndexChanged.connect(self._on_suggestion_changed)
        form.addRow("Suggestion:", self.stage2_suggestion_combo)

        self.stage2_suggestion_message = QLabel("")
        self.stage2_suggestion_message.setWordWrap(True)
        form.addRow("", self.stage2_suggestion_message)

        self.stage2_replacement_edit = QLineEdit()
        self.stage2_replacement_edit.setReadOnly(True)
        self.stage2_replacement_edit.textChanged.connect(self._update_review_buttons)
        form.addRow("Replacement:", self.stage2_replacement_edit)
        review_layout.addLayout(form)

        action_layout = QHBoxLayout()
        self.stage2_confirm_btn = QPushButton("Confirm")
        self.stage2_confirm_btn.clicked.connect(self._on_review_confirm)
        action_layout.addWidget(self.stage2_confirm_btn)
        self.stage2_edit_btn = QPushButton("Edit")
        self.stage2_edit_btn.clicked.connect(self._on_review_edit)
        action_layout.addWidget(self.stage2_edit_btn)
        self.stage2_skip_btn = QPushButton("Skip")
        self.stage2_skip_btn.clicked.connect(self._on_review_skip)
        action_layout.addWidget(self.stage2_skip_btn)
        self.stage2_replace_all_btn = QPushButton("Replace All")
        self.stage2_replace_all_btn.clicked.connect(self._on_review_replace_all)
        action_layout.addWidget(self.stage2_replace_all_btn)
        action_layout.addStretch()
        review_layout.addLayout(action_layout)
        layout.addWidget(review_group)

        self.stage2_output = QTextEdit()
        self.stage2_output.setReadOnly(True)
        self.stage2_output.setMaximumHeight(130)
        layout.addWidget(self.stage2_output)
        
        return widget

    def _create_stage3_tab(self) -> QWidget:
        """Text cleaning and chunking."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        btn_layout = QHBoxLayout()
        
        clean_btn = QPushButton("🧹 Clean & Chunk")
        clean_btn.clicked.connect(self._on_clean_chunk)
        btn_layout.addWidget(clean_btn)
        
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
        
        self.stage3_output = QTextEdit()
        self.stage3_output.setReadOnly(True)
        layout.addWidget(self.stage3_output)
        
        return widget

    def _create_stage4_tab(self) -> QWidget:
        """Chapter filtering and export."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        btn_layout = QHBoxLayout()
        
        export_btn = QPushButton("💾 Export")
        export_btn.clicked.connect(self._on_export)
        btn_layout.addWidget(export_btn)
        
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
        
        self.stage4_output = QTextEdit()
        self.stage4_output.setReadOnly(True)
        layout.addWidget(self.stage4_output)
        
        return widget

    def _on_load(self):
        """Load input files."""
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Select TXT or ZIP files", self.settings.resolved_input_dir(),
            "Text Files (*.txt *.zip);;All Files (*)"
        )
        if not paths:
            return
        self.settings.last_input_dir = str(Path(paths[0]).expanduser().resolve().parent)
        try:
            self.settings.save()
        except OSError as error:
            self._log(f"Could not remember input folder: {error}")
        self._log(f"Loading {len(paths)} file(s)...")
        try:
            from chapters import build_patterns, detect_headers_in_text
            from pipeline.loader import insert_missing_headers, load_paths
            result = load_paths(paths, chain=self.settings.encoding_chain, sort_mode="natural")
            if self.settings.auto_insert_headers:
                patterns = build_patterns(self.settings)

                def header_numbers(text: str) -> list[int]:
                    return [item[1] for item in detect_headers_in_text(text, patterns)]

                result.files, inserted = insert_missing_headers(
                    result.files,
                    has_header=lambda text: bool(header_numbers(text)),
                    prefix=self.settings.auto_insert_prefix,
                    continuous=self.settings.continuous_numbering,
                    detect_max_number=lambda text: max(header_numbers(text), default=None),
                )
                result.diagnostics.extend(inserted)
            self.document.source_files = result.files
            self.document.load_original_input(result.text)
            self.document.diagnostics.extend(result.diagnostics)
            self._log(f"✓ {result.summary()}")
            self._set_editor_text(self.stage1_output, result.text)
            self.stage1_output.setReadOnly(True)
            self.stage2_source_label.setText("Source: Original File — Step 1 not run")
            self.stage2_dictionary_label.setText("Master dictionary: not initialized")
            self._set_editor_text(self.stage2_input_preview, "")
            self._set_editor_text(self.stage2_output, "")
            self._set_editor_text(self.stage2_sentence_text, "")
            self.stage2_progress_label.setText(
                "Total sentences: 0    Resolved: 0    Remaining: 0"
            )
            self.stage2_continue_btn.setEnabled(False)
            self._set_editor_text(self.stage3_output, "")
            self._set_editor_text(self.stage4_output, "")
            self._update_status()
        except Exception as error:
            self._error(f"Load failed: {error}")
    
    def _on_normalize(self):
        if not self.document.original_input_text:
            self._error("No text loaded. Load files first.")
            return
        self._log("Normalizing chapters...")
        try:
            from chapters import build_patterns, normalize_chapters, NormalizeOptions
            patterns = build_patterns(self.settings)
            options = NormalizeOptions.from_settings(self.settings)
            chapters, report, diagnostics = normalize_chapters(
                self.document.original_input_text, patterns, options, source_name="merged"
            )
            normalized_text = self.document.set_normalized_output(chapters)
            self.document.diagnostics.extend(diagnostics)
            self.document.stage("normalize").touch(
                f"{len(self.document.source_files)} sources",
                f"{len(chapters)} chapters", report.to_dict()
            )
            self._log(f"✓ Detected {len(chapters)} chapters")
            self._set_editor_text(self.stage1_output, normalized_text)
            self.stage1_output.setReadOnly(False)
            self.stage2_continue_btn.setEnabled(False)
            self.stage2_source_label.setText("Source: Step 1 ready — open Step 2 to review")
            self._update_status()
        except Exception as error:
            # Do not leave a previous successful normalized output eligible
            # after a failed rerun; Step 2 must fail closed or use the
            # explicitly labelled pre-normalization fallback.
            self.document.normalized_text = None
            self.document.chinese_review_text = None
            self.document.step2_confirmed_output = None
            self.document.chinese_review_session = None
            self.document.cleaned_text = None
            self.document.filtered_output = None
            self.document.chunks = []
            self.document.stage(StageKey.NORMALIZE).fail(str(error))
            self._set_editor_text(self.stage1_output, "")
            self.stage1_output.setReadOnly(True)
            self.stage2_continue_btn.setEnabled(False)
            self._error(f"Normalize failed: {error}")
            import traceback
            traceback.print_exc()
    
    def _on_scan_chinese(self):
        self._log("Scanning Step 2 working copy for Chinese residue...")
        try:
            session = self._ensure_review_session(rescan=True)
            self._sync_review_document(session)
            self._refresh_stage2_ui()
            self._log(f"✓ {session.progress_text()}")
            self._update_status()
        except Exception as error:
            self._error(f"Scan failed: {error}")
            import traceback
            traceback.print_exc()
    
    def _on_translate(self):
        """Compatibility helper: apply explicitly supplied mappings as confirmed.

        The user-facing workflow is occurrence based.  This method remains for
        callers that already populate ``document.translations``; it routes those
        mappings through the same review session and never bypasses Step 2.
        """
        try:
            from chinese.review import ReviewStatus

            session = self._ensure_review_session()
            applied = 0
            while True:
                target = None
                for sentence_id in session.review_sentence_ids:
                    for fragment in session.sentences[sentence_id].fragments:
                        replacement = self.document.translations.get(fragment.text, "").strip()
                        if replacement:
                            target = (fragment.id, replacement)
                            break
                    if target:
                        break
                if target is None:
                    break
                applied += session.apply(
                    target[0], target[1], ReviewStatus.CONFIRMED, replace_all=True
                )
            self._sync_review_document(session)
            self._refresh_stage2_ui()
            self._log(f"✓ Applied {applied} confirmed replacement(s).")
            self._update_status()
        except PipelineStateError as error:
            self._error(str(error))
        except Exception as error:
            self._error(f"Translation failed: {error}")
    
    def _on_clean_chunk(self):
        self._log("Cleaning and chunking...")
        try:
            from chunking import split_chapters
            from chapters import build_patterns
            from cleaning import CleaningOptions, clean_text
            source_text = self.document.require_step2_confirmed_output()
            patterns = build_patterns(self.settings)
            chapters = derive_chapters_from_text(source_text, patterns, source_name="pipeline")
            if not chapters:
                self._error("No chapter boundaries found in the current pipeline output.")
                return
            cleaning_options = CleaningOptions.from_settings(self.settings)
            clean_reports = []
            for chapter in chapters:
                cleaned, clean_report = clean_text(chapter.text, cleaning_options)
                chapter.text = cleaned
                chapter.char_count = len(cleaned)
                clean_reports.append(clean_report)
            cleaned_text = render_chapters_text(chapters)
            self.document.chapters = chapters
            self.document.set_cleaned_output(cleaned_text)
            limit = self.settings.clamp_chunk_size()
            chunks, plan, diagnostics = split_chapters(
                chapters,
                limit,
                include_header=False,
                min_chunk=max(50, int(self.settings.min_chunk_chars or 200)),
            )
            self.document.chunks = chunks
            self.document.diagnostics.extend(diagnostics)
            self.document.stage("clean_chunk").touch(
                f"{len(self.document.chapters)} chapters", f"{len(chunks)} chunks",
                {
                    "total_chunks": len(chunks),
                    "cleaned_before": sum(report.before_chars for report in clean_reports),
                    "cleaned_after": sum(report.after_chars for report in clean_reports),
                }
            )
            self._log(f"✓ Created {len(chunks)} chunks")
            self.stage3_output.setPlainText(
                f"Created {len(chunks)} chunks:\n\n" +
                "\n".join(f"• Ch {c.chapter} part {c.part}/{c.parts}: {c.char_count} chars" for c in chunks[:50])
            )
            self._update_status()
        except PipelineStateError as error:
            self._error(str(error))
        except Exception as error:
            self._error(f"Clean/chunk failed: {error}")
            import traceback
            traceback.print_exc()
    
    def _on_export(self):
        if not self.document.chunks:
            self._error("No chunks. Run clean & chunk first.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export chunks as JSON",
            str(self.settings.resolved_output_dir() / self._default_export_filename()),
            "JSON Files (*.json);;All Files (*)",
        )
        if not path:
            return
        try:
            import json
            output = {
                "chapters": [c.to_dict() for c in self.document.chapters],
                "chunks": [c.to_dict() for c in self.document.chunks],
                "summary": self.document.summary(),
            }
            serialized = json.dumps(output, ensure_ascii=False, indent=2)
            self.document.set_filtered_output(serialized)
            self.document.stage(StageKey.FILTER_EXPORT).touch(
                f"{len(self.document.chunks)} chunks",
                f"exported {len(self.document.chunks)} chunks",
            )
            output_path = Path(path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(serialized, encoding=self.settings.export_encoding)
            self._log(f"✓ Exported to {path}")
            self.stage4_output.setPlainText(f"Exported {len(self.document.chunks)} chunks to:\n{path}")
        except Exception as error:
            self._error(f"Export failed: {error}")
    
    def _on_save_settings(self):
        try:
            path = self.settings.save()
            self._log(f"✓ Settings saved to {path}")
        except Exception as error:
            self._error(f"Save failed: {error}")

    def _on_open_settings(self) -> None:
        from ui.settings_dialog import SettingsDialog

        dialog = SettingsDialog(self.settings, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        updated = dialog.updated_settings()
        for name in self.settings.__dataclass_fields__:
            setattr(self.settings, name, getattr(updated, name))
        try:
            path = self.settings.save()
            self._apply_runtime_settings()
            self._log(f"✓ Settings saved to {path}")
        except Exception as error:
            self._error(f"Save failed: {error}")

    def _apply_runtime_settings(self) -> None:
        font = self.font()
        font.setPointSize(max(7, int(self.settings.font_size or 10)))
        app = QApplication.instance()
        if app is not None:
            app.setFont(font)
        self.setFont(font)
        self.status_text.document().setMaximumBlockCount(
            max(100, int(self.settings.max_log_lines or 2000))
        )

    def _default_export_filename(self) -> str:
        try:
            name = self.settings.filename_template.format(tag="export")
        except (KeyError, IndexError, ValueError):
            name = "novel_export"
        name = (name or "novel_export").strip()
        return name if name.lower().endswith(".json") else f"{name}.json"
    
    def _log(self, message: str):
        self.status_text.append(message)
    
    def _error(self, message: str):
        QMessageBox.critical(self, "Error", message)
        self._log(f"❌ {message}")
    
    def _update_status(self):
        summary = self.document.summary()
        self.status_label.setText(
            f"📄 {summary['chapter_count']} chapters · "
            f"📦 {summary['chunk_count']} chunks · "
            f"📝 {summary['characters']:,} chars"
        )

    def _set_editor_text(self, editor: QTextEdit, text: str) -> None:
        """Update an editor without treating programmatic changes as edits."""
        self._updating_widgets = True
        try:
            editor.blockSignals(True)
            editor.setPlainText(text or "")
        finally:
            editor.blockSignals(False)
            self._updating_widgets = False

    def _on_stage1_text_changed(self) -> None:
        if self._updating_widgets or self.document.normalized_text is None:
            return
        if self.document.set_normalized_edit(self.stage1_output.toPlainText()):
            self.stage2_continue_btn.setEnabled(False)
            self.stage2_source_label.setText("Source: Step 1 changed — rescan required")
            self._update_status()

    def _continue_to_stage2(self) -> None:
        if self._enter_stage2():
            self.tabs.setCurrentIndex(1)

    def _continue_to_stage3(self) -> None:
        try:
            self.document.require_step2_confirmed_output()
        except PipelineStateError as error:
            self._error(str(error))
            return
        self.tabs.setCurrentIndex(2)

    def _on_tab_changed(self, index: int) -> None:
        if index == 1:
            self._enter_stage2()
        elif index == 2:
            try:
                self.document.require_step2_confirmed_output()
            except PipelineStateError as error:
                self.tabs.blockSignals(True)
                self.tabs.setCurrentIndex(1)
                self.tabs.blockSignals(False)
                self._enter_stage2()
                self._error(str(error))

    def _enter_stage2(self) -> bool:
        try:
            session = self._ensure_review_session()
            self._sync_review_document(session)
            self._refresh_stage2_ui()
            self._update_status()
            return True
        except PipelineStateError as error:
            self._error(str(error))
            return False
        except Exception as error:
            self._error(f"Step 2 failed: {error}")
            return False

    # ------------------------------------------------------- Step 2 review
    def _ensure_master_dictionary(self):
        from chinese.master_dictionary import MasterDictionary, MasterDictionaryError

        if self._master_dictionary is None:
            self._master_dictionary = MasterDictionary()
        self.stage2_dictionary_label.setText("Master dictionary: validating/indexing fixed assets…")
        QApplication.processEvents()
        try:
            health = self._master_dictionary.ensure_ready()
        except MasterDictionaryError as error:
            self._dictionary_error = str(error)
            self.stage2_dictionary_label.setText(f"Master dictionary error: {error}")
            self.stage2_dictionary_label.setStyleSheet("color: #b00020;")
            self._log(f"❌ Master dictionary unavailable: {error}")
            return None
        self._dictionary_error = ""
        self.stage2_dictionary_label.setStyleSheet("")
        warning = health.warning_summary()
        summary = (
            f"Master dictionary: {health.indexed_entries:,} phrase alternatives · "
            f"{health.indexed_rules:,} rules · {health.indexed_phonetics:,} phonetics"
        )
        if warning:
            summary += f" · {warning}"
        self.stage2_dictionary_label.setText(summary)
        return self._master_dictionary

    def _ensure_review_session(self, *, rescan: bool = False):
        from chinese.detector import has_han
        from chinese.review import ChineseReviewSession

        step2_input, source_label = self.document.begin_chinese_review()
        self.stage2_source_label.setText(source_label)
        dictionary = self._ensure_master_dictionary() if has_han(step2_input) else None
        session = self.document.chinese_review_session
        if (
            session is None
            or session.source_revision != self.document.normalized_revision
            or session.source_text != self.document._chinese_review_source_text
        ):
            session = ChineseReviewSession(
                step2_input,
                dictionary,
                source_revision=self.document.normalized_revision,
            )
            self.document.chinese_review_session = session
        elif rescan:
            session.dictionary = dictionary
            session.scan_all()
        return session

    def _sync_review_document(self, session) -> None:
        working = session.working_text
        self.document.set_chinese_review_output(working)
        counts = {
            "total_sentences": session.total_sentences,
            "resolved_sentences": session.resolved_sentences,
            "remaining_sentences": session.remaining_sentences,
            "actions": len(session.actions),
        }
        status = self.document.stage(StageKey.CHINESE)
        if session.is_complete:
            self.document.complete_chinese_review(working)
            status.touch(
                f"{len(session.source_text)} characters",
                "Chinese residue review complete",
                counts,
            )
        else:
            status.ran = True
            status.ok = False
            status.input_summary = f"{len(session.source_text)} characters"
            status.result_summary = session.progress_text()
            status.counts = counts
            status.error = ""

    def _refresh_stage2_ui(self) -> None:
        session = self.document.chinese_review_session
        if session is None:
            self.stage2_progress_label.setText(
                "Total sentences: 0    Resolved: 0    Remaining: 0"
            )
            self.stage2_continue_btn.setEnabled(False)
            return

        self._set_editor_text(self.stage2_input_preview, session.working_text)
        self.stage2_progress_label.setText(session.progress_text())
        self.stage2_continue_btn.setEnabled(session.is_complete)
        lines = []
        for number, sentence_id in enumerate(session.review_sentence_ids[:100], 1):
            sentence = session.sentences[sentence_id]
            state = "Resolved" if not sentence.unresolved else "Remaining"
            fragments = ", ".join(
                f"{fragment.text} [{fragment.status.value}]" for fragment in sentence.fragments
            ) or "No Han characters"
            actions = "; ".join(
                (
                    f"{action.fragment} [Skipped]"
                    if action.status.value == "Skipped"
                    else f"{action.fragment} → {action.replacement} [{action.status.value}]"
                )
                for action in session.actions_for_sentence(sentence_id)
            )
            audit = f"\n   Actions: {actions}" if actions else ""
            lines.append(
                f"{number}. {state}: {fragments}\n   {sentence.display_text}{audit}"
            )
        if not lines:
            lines.append("No Chinese Han characters remain in the Step 2 working copy.")
        self._set_editor_text(self.stage2_output, "\n\n".join(lines))
        self._render_review_sentence()

    def _render_review_sentence(self) -> None:
        session = self.document.chinese_review_session
        sentence = session.current_sentence if session is not None else None
        self._updating_review_widgets = True
        try:
            self.stage2_fragment_combo.blockSignals(True)
            self.stage2_fragment_combo.clear()
            if sentence is None:
                self.stage2_position_label.setText("No Chinese residue")
                self._set_editor_text(self.stage2_sentence_text, "")
            else:
                self.stage2_position_label.setText(
                    f"Sentence {session.current_position + 1} of {session.total_sentences}"
                )
                self._set_editor_text(self.stage2_sentence_text, sentence.display_text)
                for fragment in sentence.fragments:
                    self.stage2_fragment_combo.addItem(
                        f"{fragment.text} — {fragment.status.value}", fragment.id
                    )
            self.stage2_fragment_combo.blockSignals(False)
        finally:
            self._updating_review_widgets = False
        self._render_review_fragment()
        self.stage2_previous_btn.setEnabled(
            bool(session and session.review_sentence_ids and session.current_position > 0)
        )
        self.stage2_next_btn.setEnabled(
            bool(
                session
                and session.review_sentence_ids
                and session.current_position < len(session.review_sentence_ids) - 1
            )
        )

    def _selected_review_fragment(self):
        session = self.document.chinese_review_session
        if session is None:
            return None
        fragment_id = self.stage2_fragment_combo.currentData()
        return session.fragment_by_id(str(fragment_id)) if fragment_id else None

    def _render_review_fragment(self) -> None:
        fragment = self._selected_review_fragment()
        self._updating_review_widgets = True
        self._manual_edit_mode = False
        try:
            self.stage2_suggestion_combo.blockSignals(True)
            self.stage2_suggestion_combo.clear()
            self.stage2_suggestion_combo.addItem("Select a suggestion…", None)
            self.stage2_replacement_edit.blockSignals(True)
            self.stage2_replacement_edit.setReadOnly(True)
            self.stage2_replacement_edit.clear()
            if fragment is None:
                self.stage2_fragment_status.setText("Resolved" if self.document.chinese_review_session else "")
                session = self.document.chinese_review_session
                sentence = session.current_sentence if session is not None else None
                actions = session.actions_for_sentence(sentence.id) if sentence is not None else []
                self.stage2_suggestion_message.setText(
                    "; ".join(
                        f"{action.fragment} → {action.replacement} [{action.status.value}]"
                        for action in actions
                        if action.status.value != "Skipped"
                    )
                )
            else:
                self.stage2_fragment_status.setText(fragment.status.value)
                for index, suggestion in enumerate(fragment.suggestions):
                    self.stage2_suggestion_combo.addItem(suggestion.display_text, index)
                if not fragment.suggestions:
                    self.stage2_suggestion_message.setText(
                        "No suggestion found. Click Edit to enter a manual replacement."
                    )
                elif len(fragment.suggestions) > 1:
                    self.stage2_suggestion_message.setText(
                        "Multiple dictionary alternatives found. Select one or enter a manual replacement."
                    )
                else:
                    suggestion = fragment.suggestions[0]
                    self.stage2_suggestion_message.setText(
                        f"{suggestion.kind.title()} suggestion from {suggestion.source_label}."
                    )
                    self.stage2_suggestion_combo.setCurrentIndex(1)
                    self.stage2_replacement_edit.setText(suggestion.value)
            self.stage2_replacement_edit.blockSignals(False)
            self.stage2_suggestion_combo.blockSignals(False)
        finally:
            self._updating_review_widgets = False
        self._update_review_buttons()

    def _on_fragment_changed(self, _index: int) -> None:
        if not self._updating_review_widgets:
            self._render_review_fragment()

    def _on_suggestion_changed(self, _index: int) -> None:
        if self._updating_review_widgets:
            return
        fragment = self._selected_review_fragment()
        suggestion_index = self.stage2_suggestion_combo.currentData()
        self._manual_edit_mode = False
        self.stage2_replacement_edit.setReadOnly(True)
        if fragment is None or suggestion_index is None:
            self.stage2_replacement_edit.clear()
        else:
            self.stage2_replacement_edit.setText(
                fragment.suggestions[int(suggestion_index)].value
            )
        self._update_review_buttons()

    def _on_review_edit(self) -> None:
        if self._selected_review_fragment() is None:
            return
        self._manual_edit_mode = True
        self.stage2_replacement_edit.setReadOnly(False)
        self.stage2_replacement_edit.setFocus()
        self.stage2_replacement_edit.selectAll()
        self._update_review_buttons()

    def _on_review_confirm(self) -> None:
        self._apply_review_replacement(replace_all=False)

    def _on_review_replace_all(self) -> None:
        self._apply_review_replacement(replace_all=True)

    def _apply_review_replacement(self, *, replace_all: bool) -> None:
        from chinese.review import ReviewStatus

        session = self.document.chinese_review_session
        fragment = self._selected_review_fragment()
        if session is None or fragment is None:
            return
        replacement = self.stage2_replacement_edit.text().strip()
        suggestion_selected = self.stage2_suggestion_combo.currentData() is not None
        if not replacement or (not self._manual_edit_mode and not suggestion_selected):
            self._error("Select a suggestion or enter a manual replacement first.")
            return
        status = ReviewStatus.MANUAL if self._manual_edit_mode else ReviewStatus.CONFIRMED
        try:
            count = session.apply(
                fragment.id, replacement, status, replace_all=replace_all
            )
            self._sync_review_document(session)
            self._refresh_stage2_ui()
            self._update_status()
            self._log(
                f"✓ Replaced {count} occurrence(s) of {fragment.text} with {replacement}."
            )
        except ValueError as error:
            self._error(str(error))

    def _on_review_skip(self) -> None:
        session = self.document.chinese_review_session
        fragment = self._selected_review_fragment()
        if session is None or fragment is None:
            return
        try:
            session.skip(fragment.id)
            self._sync_review_document(session)
            self._refresh_stage2_ui()
            self._update_status()
        except ValueError as error:
            self._error(str(error))

    def _on_review_previous(self) -> None:
        session = self.document.chinese_review_session
        if session is not None:
            session.previous()
            self._render_review_sentence()

    def _on_review_next(self) -> None:
        session = self.document.chinese_review_session
        if session is not None:
            session.next()
            self._render_review_sentence()

    def _update_review_buttons(self, *_args) -> None:
        fragment = self._selected_review_fragment()
        has_replacement = bool(self.stage2_replacement_edit.text().strip())
        selected = self.stage2_suggestion_combo.currentData() is not None
        can_apply = bool(
            fragment and has_replacement and (self._manual_edit_mode or selected)
        )
        self.stage2_confirm_btn.setEnabled(can_apply)
        self.stage2_replace_all_btn.setEnabled(can_apply)
        self.stage2_edit_btn.setEnabled(fragment is not None)
        self.stage2_skip_btn.setEnabled(fragment is not None)
