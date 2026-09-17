"""Main application window with pipeline stages."""

from __future__ import annotations

import os
from pathlib import Path

from PyQt6.QtCore import QObject, QProcess, QThread, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QPixmap
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
    QProgressBar,
    QSizePolicy,
    QSplitter,
    QSpinBox,
    QStackedWidget,
)

from config.settings import DEFAULT_TTS_VOICE, Settings
from pipeline.document import (
    PipelineDocument,
    PipelineStateError,
    StageKey,
    derive_chapters_from_text,
    render_chapters_text,
)


class _TtsWorker(QObject):
    """Run network-bound TTS work outside the Qt UI thread."""

    progress = pyqtSignal(int, int, str)
    completed = pyqtSignal(object, object)
    failed = pyqtSignal(str)

    def __init__(self, processor, output_path):
        super().__init__()
        self.processor = processor
        self.output_path = output_path
        # Bridge the Qt-free processor callback to a queued Qt signal.
        self.processor.progress = self.progress.emit

    def run(self):
        try:
            result = self.processor.run()
            if not result.failures and not result.cancelled:
                self.processor.merge(result, self.output_path)
            self.completed.emit(self.processor, result)
        except Exception as error:
            self.failed.emit(str(error))


class _MergeWorker(QObject):
    """Run the potentially large FFmpeg final merge off the UI thread."""

    completed = pyqtSignal(object, object)
    failed = pyqtSignal(str)

    def __init__(self, processor, result, output_path):
        super().__init__()
        self.processor = processor
        self.result = result
        self.output_path = output_path

    def run(self):
        try:
            self.processor.merge(self.result, self.output_path, skip_failed=True)
            self.completed.emit(self.processor, self.result)
        except Exception as error:
            self.failed.emit(str(error))


class _VideoDetectionWorker(QObject):
    """Run system inspection and real encoder probes away from the UI thread."""

    completed = pyqtSignal(object)
    failed = pyqtSignal(str)

    def run(self) -> None:
        try:
            from media.video import detect_video_capabilities

            self.completed.emit(detect_video_capabilities())
        except Exception as error:
            self.failed.emit(str(error))


class _VideoRenderSession(QObject):
    """Drive ordered FFmpeg encoder attempts through an asynchronous QProcess."""

    progress = pyqtSignal(object)
    status = pyqtSignal(str)
    completed = pyqtSignal(object)
    failed = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(self, capabilities, media, duration: float, *, audio_copy: bool, parent=None):
        super().__init__(parent)
        self.capabilities = capabilities
        self.media = media
        self.duration = float(duration)
        self.audio_copy = bool(audio_copy)
        self.candidates = list(capabilities.verified_candidates)
        self.attempt_index = -1
        self.process: QProcess | None = None
        self.partial_path = Path(media.video_path).with_name(
            f".{Path(media.video_path).stem}.part.mp4"
        )
        self._progress_buffer = ""
        self._progress_state = {}
        self._stderr = ""
        self._last_progress = {"elapsed": 0.0, "percentage": 0.0, "speed": 0.0, "eta": 0.0}
        self._cancel_requested = False
        self._attempt_handled = False
        self.attempt_errors: list[str] = []

    def start(self) -> None:
        if not self.candidates:
            self.failed.emit("No verified H.264 encoder is available.")
            return
        self.partial_path.parent.mkdir(parents=True, exist_ok=True)
        self._start_next_attempt()

    def _start_next_attempt(self) -> None:
        from media.video import build_video_command

        self.attempt_index += 1
        if self.attempt_index >= len(self.candidates):
            details = "\n\n".join(self.attempt_errors) or "All verified encoders failed."
            self.failed.emit(details)
            return
        candidate = self.candidates[self.attempt_index]
        self.partial_path.unlink(missing_ok=True)
        self._progress_buffer = ""
        self._progress_state = {}
        self._stderr = ""
        self._attempt_handled = False
        self._last_progress = {"elapsed": 0.0, "percentage": 0.0, "speed": 0.0, "eta": 0.0}
        self.progress.emit(dict(self._last_progress))
        self.status.emit(
            f"Rendering with {candidate.name} ({self.attempt_index + 1}/{len(self.candidates)})…"
        )
        command = build_video_command(
            self.capabilities.ffmpeg_path,
            candidate,
            Path(self.media.thumbnail_path),
            Path(self.media.audiobook_path),
            self.partial_path,
            audio_copy=self.audio_copy,
        )
        process = QProcess(self)
        process.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        process.readyReadStandardOutput.connect(lambda current=process: self._read_progress(current))
        process.readyReadStandardError.connect(lambda current=process: self._read_error(current))
        process.finished.connect(
            lambda code, status, current=process: self._on_finished(current, code, status)
        )
        process.errorOccurred.connect(
            lambda error, current=process: self._on_process_error(current, error)
        )
        self.process = process
        process.start(command[0], command[1:])

    def _read_progress(self, process: QProcess) -> None:
        from media.video import parse_progress_line

        if process is not self.process:
            return
        self._progress_buffer += bytes(process.readAllStandardOutput()).decode("utf-8", "replace")
        lines = self._progress_buffer.split("\n")
        self._progress_buffer = lines.pop()
        for line in lines:
            update = parse_progress_line(self._progress_state, line, self.duration)
            if update is not None:
                self._last_progress = update
                self.progress.emit(dict(update))

    def _read_error(self, process: QProcess) -> None:
        if process is not self.process:
            return
        self._stderr += bytes(process.readAllStandardError()).decode("utf-8", "replace")
        self._stderr = self._stderr[-30000:]

    def _on_process_error(self, process: QProcess, error) -> None:
        if process is not self.process:
            return
        if error == QProcess.ProcessError.FailedToStart:
            self._handle_attempt_failure("FFmpeg process could not be started.")

    def _on_finished(self, process: QProcess, exit_code: int, _exit_status) -> None:
        if process is not self.process:
            return
        if self._attempt_handled:
            return
        self._attempt_handled = True
        if self._cancel_requested:
            self.partial_path.unlink(missing_ok=True)
            self.cancelled.emit()
            return
        candidate = self.candidates[self.attempt_index]
        if exit_code != 0:
            self._handle_attempt_failure(
                self._stderr.strip() or f"FFmpeg exited with status {exit_code}."
            )
            return
        try:
            from media.video import VideoRenderResult, validate_rendered_video

            duration = validate_rendered_video(
                self.partial_path, self.duration, self.capabilities.ffprobe_path
            )
            final_path = Path(self.media.video_path)
            os.replace(self.partial_path, final_path)
            result = VideoRenderResult(
                output_path=str(final_path),
                duration=duration,
                file_size=final_path.stat().st_size,
                encoder=candidate.name,
                backend=candidate.backend,
                render_speed=float(self._last_progress.get("speed") or 0.0),
                audio_mode="copy" if self.audio_copy else "aac-192k",
                attempt_errors=list(self.attempt_errors),
            )
            self.completed.emit(result)
        except Exception as error:
            self._handle_attempt_failure(str(error))

    def _handle_attempt_failure(self, message: str) -> None:
        if self._attempt_handled and self.process is not None and self.process.state() != QProcess.ProcessState.NotRunning:
            return
        self._attempt_handled = True
        self.partial_path.unlink(missing_ok=True)
        if self._cancel_requested:
            self.cancelled.emit()
            return
        candidate = self.candidates[self.attempt_index]
        detail = f"{candidate.name} failed: {message}"
        self.attempt_errors.append(detail)
        fatal_markers = (
            "no space left on device",
            "permission denied",
            "read-only file system",
            "no such file or directory",
            "error opening input",
            "invalid data found when processing input",
        )
        if any(marker in message.lower() for marker in fatal_markers):
            self.failed.emit(detail)
            return
        if self.attempt_index + 1 < len(self.candidates):
            next_name = self.candidates[self.attempt_index + 1].name
            summary = message.strip().splitlines()[0] if message.strip() else "unknown error"
            self.status.emit(
                f"{candidate.name} failed: {summary}\nFalling back to {next_name}…"
            )
            QTimer.singleShot(0, self._start_next_attempt)
        else:
            self.failed.emit("\n\n".join(self.attempt_errors))

    def cancel(self) -> None:
        self._cancel_requested = True
        process = self.process
        if process is None or process.state() == QProcess.ProcessState.NotRunning:
            self.partial_path.unlink(missing_ok=True)
            self.cancelled.emit()
            return
        process.terminate()
        QTimer.singleShot(
            3000,
            lambda: process.kill() if process.state() != QProcess.ProcessState.NotRunning else None,
        )


class _FailedChunksDialog(QDialog):
    """Review every failed chunk before deciding whether to skip it."""

    def __init__(self, failures, *, allow_merge: bool, parent=None):
        super().__init__(parent)
        self.failures = [self._as_dict(item) for item in failures]
        self.setWindowTitle("Failed TTS Chunks")
        self.resize(900, 650)

        layout = QVBoxLayout(self)
        summary = QLabel(
            f"{len(self.failures)} chunk(s) failed. Review the complete text and error "
            "before deciding whether to merge without them."
        )
        summary.setWordWrap(True)
        layout.addWidget(summary)

        self.failure_selector = QComboBox()
        for failure in self.failures:
            number = failure.get("chunk_number", "?")
            part = failure.get("failed_part", "whole")
            self.failure_selector.addItem(f"Chunk {number} — {part}")
        self.failure_selector.currentIndexChanged.connect(self._show_failure)
        layout.addWidget(self.failure_selector)

        self.failure_details = QLabel("")
        self.failure_details.setWordWrap(True)
        layout.addWidget(self.failure_details)

        self.failure_text = QTextEdit()
        self.failure_text.setReadOnly(True)
        layout.addWidget(self.failure_text, 1)

        buttons = QHBoxLayout()
        buttons.addStretch()
        self.merge_button = None
        if allow_merge:
            self.merge_button = QPushButton("1 — Merge and skip failed chunks")
            self.merge_button.clicked.connect(self.accept)
            buttons.addWidget(self.merge_button)
            cancel = QPushButton("2 — Cancel merge")
        else:
            cancel = QPushButton("Close")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        layout.addLayout(buttons)
        self._show_failure(0)

    @staticmethod
    def _as_dict(item) -> dict:
        if isinstance(item, dict):
            return dict(item)
        return dict(getattr(item, "__dict__", {}))

    def _show_failure(self, index: int) -> None:
        if index < 0 or index >= len(self.failures):
            self.failure_details.setText("")
            self.failure_text.setPlainText("")
            return
        failure = self.failures[index]
        details = [
            f"Chunk: {failure.get('chunk_number', '?')}",
            f"Failed part: {failure.get('failed_part', 'whole')}",
            f"Attempts: {failure.get('attempts', '?')}",
            f"Error: {failure.get('error_type', 'Error')}: "
            f"{failure.get('error_message', 'Unknown error')}",
        ]
        if failure.get("main_error_message"):
            details.append(
                f"Main request error: {failure.get('main_error_type', 'Error')}: "
                f"{failure['main_error_message']}"
            )
        self.failure_details.setText("\n".join(details))

        sections = ["ORIGINAL CHUNK TEXT:\n" + str(failure.get("original_text", ""))]
        failed_part_text = str(failure.get("failed_part_text", "") or "")
        if failed_part_text:
            sections.append("FAILED PART TEXT:\n" + failed_part_text)
        self.failure_text.setPlainText("\n\n".join(sections))


class MainWindow(QMainWindow):
    """Main window with the complete six-stage pipeline."""

    def __init__(self, settings: Settings, parent=None, *, master_dictionary=None):
        super().__init__(parent)
        self.settings = settings
        self.document = PipelineDocument()
        self._updating_widgets = False
        self._updating_review_widgets = False
        self._updating_job_widgets = False
        self._manual_edit_mode = False
        self._master_dictionary = master_dictionary
        self._dictionary_attempted = master_dictionary is not None
        self._dictionary_error = ""
        self._tts_thread = None
        self._tts_worker = None
        self._tts_processor = None
        self._merge_thread = None
        self._merge_worker = None
        self._video_detection_thread = None
        self._video_detection_worker = None
        self._video_capabilities = None
        self._video_detection_error = ""
        self._video_media = None
        self._video_audio_probe = None
        self._video_render_session = None
        
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
        self.tabs.addTab(self.stage3_widget, "3️⃣ Detect Chapters & Group")
        
        # Stage 4: Thumbnail & Audiobook
        self.stage4_widget = self._create_stage4_tab()
        from ui.grouped_pipeline import TtsBatchPanel, VideoBatchPanel, UploadBatchPanel
        self.group4 = TtsBatchPanel(lambda: self.document, self.settings, self)
        self.stage4_stack = QStackedWidget()
        self.stage4_stack.addWidget(self.group4)
        self.stage4_stack.addWidget(self.stage4_widget)
        self.tabs.addTab(self.stage4_stack, "4️⃣ Thumbnail & Audiobook")

        # Stage 5: hardware-adaptive static-image video
        self.stage5_widget = self._create_stage5_tab()
        self.group5 = VideoBatchPanel(lambda: self.document, self.settings, self)
        self.stage5_stack = QStackedWidget()
        self.stage5_stack.addWidget(self.group5)
        self.stage5_stack.addWidget(self.stage5_widget)
        self.tabs.addTab(self.stage5_stack, "5️⃣ Create Video")
        from ui.youtube_tab import YouTubeTab

        self.stage6_widget = YouTubeTab(lambda: self.document, self.settings, self)
        self.stage6_widget.busy_changed.connect(self._set_youtube_busy)
        self.stage6_widget.diagnostic.connect(self._log)
        self.group6 = UploadBatchPanel(lambda: self.document, self.settings, self)
        self.stage6_stack = QStackedWidget()
        self.stage6_stack.addWidget(self.group6)
        self.stage6_stack.addWidget(self.stage6_widget)
        self.tabs.addTab(self.stage6_stack, "6️⃣ YouTube Upload")
        for index, panel in ((3, self.group4), (4, self.group5), (5, self.group6)):
            panel.busy_changed.connect(lambda busy, stage=index: self._set_group_batch_busy(stage, busy))
            panel.diagnostic.connect(self._log)
        self.group4.groups_changed.connect(self._refresh_group_panels)
        for panel, action, label in ((self.group4, self._continue_to_stage5, "Continue to Step 5 →"),
                                      (self.group5, self._continue_to_stage6, "Continue to Step 6 →")):
            button = QPushButton(label)
            panel.continue_btn = button
            button.clicked.connect(action)
            panel.layout_main.addWidget(button)
        self.tabs.currentChanged.connect(self._on_tab_changed)
        
        # Pipeline workspace and diagnostics share a draggable vertical split.
        self.main_splitter = QSplitter(Qt.Orientation.Vertical)
        self.main_splitter.setChildrenCollapsible(False)
        self.main_splitter.setHandleWidth(8)
        self.tabs.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Ignored)
        self.main_splitter.addWidget(self.tabs)

        diagnostics_widget = QWidget()
        diagnostics_widget.setMinimumHeight(180)
        diagnostics_layout = QVBoxLayout(diagnostics_widget)
        diagnostics_layout.setContentsMargins(0, 0, 0, 0)
        self.status_text = QTextEdit()
        self.status_text.setReadOnly(True)
        diagnostics_layout.addWidget(QLabel("Status & Diagnostics:"))
        diagnostics_layout.addWidget(self.status_text)
        self.main_splitter.addWidget(diagnostics_widget)
        self.main_splitter.setStretchFactor(0, 1)
        self.main_splitter.setStretchFactor(1, 0)
        self.main_splitter.setSizes([640, 260])
        layout.addWidget(self.main_splitter, 1)

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

        job_group = QGroupBox("Novel Title / Chapter Groups")
        job_form = QFormLayout(job_group)
        title_container = QWidget()
        title_layout = QHBoxLayout(title_container)
        title_layout.setContentsMargins(0, 0, 0, 0)
        self.stage3_title_combo = QComboBox()
        self.stage3_title_combo.setEditable(True)
        self.stage3_title_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.stage3_title_combo.addItems(self.settings.title_history)
        self.stage3_title_edit = self.stage3_title_combo.lineEdit()
        self.stage3_title_edit.setPlaceholderText("Novel Title")
        self.stage3_title_combo.currentTextChanged.connect(self._on_job_identity_changed)
        self.stage3_title_edit.editingFinished.connect(self._remember_current_title)
        title_layout.addWidget(self.stage3_title_combo, 1)
        self.stage3_remove_title_btn = QPushButton("Remove")
        self.stage3_remove_title_btn.setToolTip("Remove the current title from saved title history")
        self.stage3_remove_title_btn.clicked.connect(self._on_remove_saved_title)
        title_layout.addWidget(self.stage3_remove_title_btn)
        job_form.addRow("Title", title_container)
        self.stage3_chapter_edit = QLineEdit()
        self.stage3_chapter_edit.setPlaceholderText("Chapter Number")
        self.stage3_chapter_edit.textChanged.connect(self._on_job_identity_changed)
        # Legacy single-job label remains available to older callers, but is
        # not an input to grouped jobs. Group ranges are detected, never typed.
        self.stage3_chapter_edit.hide()
        grouping_row = QWidget()
        grouping_layout = QHBoxLayout(grouping_row)
        grouping_layout.setContentsMargins(0, 0, 0, 0)
        self.stage3_group_size = QComboBox()
        for size in (10, 20, 25, 50):
            self.stage3_group_size.addItem(str(size), size)
        self.stage3_group_size.addItem("Custom", None)
        self.stage3_group_size.setCurrentIndex(1)
        self.stage3_custom_size = QSpinBox()
        self.stage3_custom_size.setRange(1, 1000000)
        self.stage3_custom_size.setValue(20)
        self.stage3_custom_size.setVisible(False)
        self.stage3_group_size.currentIndexChanged.connect(self._on_grouping_changed)
        self.stage3_custom_size.valueChanged.connect(self._on_grouping_changed)
        grouping_layout.addWidget(self.stage3_group_size)
        grouping_layout.addWidget(self.stage3_custom_size)
        job_form.addRow("Chapters per group", grouping_row)
        self.stage3_detection_label = QLabel("Detected chapters: —")
        self.stage3_detection_label.setWordWrap(True)
        self.stage3_detection_label.setTextFormat(Qt.TextFormat.PlainText)
        job_form.addRow(self.stage3_detection_label)
        layout.addWidget(job_group)
        
        btn_layout = QHBoxLayout()
        
        clean_btn = QPushButton("Create Group Files")
        self.stage3_create_groups_btn = clean_btn
        clean_btn.clicked.connect(self._on_create_group_files)
        btn_layout.addWidget(clean_btn)
        restore_btn = QPushButton("Restore Matching Groups")
        self.stage3_restore_groups_btn = restore_btn
        restore_btn.clicked.connect(lambda: self._on_create_group_files(restore=True))
        btn_layout.addWidget(restore_btn)

        self.stage3_continue_btn = QPushButton("Continue to Step 4 →")
        self.stage3_continue_btn.setEnabled(False)
        self.stage3_continue_btn.clicked.connect(self._continue_to_stage4)
        btn_layout.addWidget(self.stage3_continue_btn)
        
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
        
        self.stage3_output = QTextEdit()
        self.stage3_output.setReadOnly(True)
        layout.addWidget(self.stage3_output)
        
        return widget

    def _create_stage4_tab(self) -> QWidget:
        """Step 3 bundle preview, thumbnail, and resumable audiobook."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        self.stage4_source_label = QLabel("Source: Run Step 3 first")
        self.stage4_source_label.setWordWrap(True)
        layout.addWidget(self.stage4_source_label)

        config_group = QGroupBox("Title / Chapter")
        config_form = QFormLayout(config_group)
        self.stage4_title_label = QLabel("—")
        self.stage4_chapter_label = QLabel("—")
        config_form.addRow("Title", self.stage4_title_label)
        config_form.addRow("Chapter", self.stage4_chapter_label)
        layout.addWidget(config_group)

        layout.addWidget(QLabel("First chapter from Step 3 TXT:"))
        self.stage4_first_chapter = QTextEdit()
        self.stage4_first_chapter.setReadOnly(True)
        self.stage4_first_chapter.setMaximumHeight(190)
        layout.addWidget(self.stage4_first_chapter)

        thumbnail_group = QGroupBox("YouTube Thumbnail")
        thumbnail_layout = QVBoxLayout(thumbnail_group)
        thumbnail_row = QHBoxLayout()
        self.stage4_thumbnail_btn = QPushButton("🖼 Select Image & Generate Thumbnail")
        self.stage4_thumbnail_btn.clicked.connect(self._on_generate_thumbnail)
        thumbnail_row.addWidget(self.stage4_thumbnail_btn)
        thumbnail_row.addStretch()
        thumbnail_layout.addLayout(thumbnail_row)
        self.stage4_thumbnail_preview = QLabel("No thumbnail generated")
        self.stage4_thumbnail_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.stage4_thumbnail_preview.setMinimumHeight(170)
        thumbnail_layout.addWidget(self.stage4_thumbnail_preview)
        self.stage4_thumbnail_path = QLabel("")
        self.stage4_thumbnail_path.setWordWrap(True)
        thumbnail_layout.addWidget(self.stage4_thumbnail_path)
        layout.addWidget(thumbnail_group)

        tts_group = QGroupBox("TXT → Edge-TTS Audiobook")
        tts_layout = QVBoxLayout(tts_group)
        tts_actions = QHBoxLayout()
        self.stage4_tts_btn = QPushButton("🔊 Generate / Resume Audiobook")
        self.stage4_tts_btn.clicked.connect(self._on_generate_audiobook)
        tts_actions.addWidget(self.stage4_tts_btn)
        self.stage4_cancel_tts_btn = QPushButton("Cancel TTS")
        self.stage4_cancel_tts_btn.setEnabled(False)
        self.stage4_cancel_tts_btn.clicked.connect(self._on_cancel_tts)
        tts_actions.addWidget(self.stage4_cancel_tts_btn)
        self.stage4_failed_chunks_btn = QPushButton("Review Failed Chunks")
        self.stage4_failed_chunks_btn.setEnabled(False)
        self.stage4_failed_chunks_btn.clicked.connect(self._on_review_failed_chunks)
        tts_actions.addWidget(self.stage4_failed_chunks_btn)
        tts_actions.addStretch()
        tts_layout.addLayout(tts_actions)
        self.stage4_tts_progress = QProgressBar()
        self.stage4_tts_progress.setRange(0, 1)
        self.stage4_tts_progress.setValue(0)
        self.stage4_tts_progress.setTextVisible(True)
        self.stage4_tts_progress.setFormat("%v / %m chunks (%p%)")
        tts_layout.addWidget(self.stage4_tts_progress)
        self.stage4_tts_status = QLabel("Ready")
        self.stage4_tts_status.setWordWrap(True)
        tts_layout.addWidget(self.stage4_tts_status)
        layout.addWidget(tts_group)

        self.stage4_output = QTextEdit()
        self.stage4_output.setReadOnly(True)
        layout.addWidget(self.stage4_output)

        self.stage4_continue_btn = QPushButton("Continue to Step 5 →")
        self.stage4_continue_btn.setEnabled(False)
        self.stage4_continue_btn.clicked.connect(self._continue_to_stage5)
        layout.addWidget(self.stage4_continue_btn)
        
        return widget

    def _create_stage5_tab(self) -> QWidget:
        """Create an MP4 from the authoritative Step 4 thumbnail and audio."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        inputs_group = QGroupBox("Step 4 Inputs")
        inputs_form = QFormLayout(inputs_group)
        self.stage5_thumbnail_label = QLabel("—")
        self.stage5_audio_label = QLabel("—")
        self.stage5_output_label = QLabel("—")
        for label in (
            self.stage5_thumbnail_label,
            self.stage5_audio_label,
            self.stage5_output_label,
        ):
            label.setWordWrap(True)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        inputs_form.addRow("Thumbnail", self.stage5_thumbnail_label)
        inputs_form.addRow("Audio", self.stage5_audio_label)
        inputs_form.addRow("Output", self.stage5_output_label)
        layout.addWidget(inputs_group)

        capabilities_group = QGroupBox("GPU & FFmpeg Detection")
        capabilities_layout = QVBoxLayout(capabilities_group)
        self.stage5_capabilities = QTextEdit()
        self.stage5_capabilities.setReadOnly(True)
        self.stage5_capabilities.setMaximumHeight(220)
        self.stage5_capabilities.setPlainText("Open Step 5 to detect video capabilities.")
        capabilities_layout.addWidget(self.stage5_capabilities)
        layout.addWidget(capabilities_group)

        render_group = QGroupBox("Video Rendering")
        render_layout = QVBoxLayout(render_group)
        render_info = QFormLayout()
        self.stage5_resolution_label = QLabel("1920×1080 · 1 fps")
        self.stage5_duration_label = QLabel("—")
        render_info.addRow("Resolution", self.stage5_resolution_label)
        render_info.addRow("Estimated duration", self.stage5_duration_label)
        render_layout.addLayout(render_info)

        actions = QHBoxLayout()
        self.stage5_create_btn = QPushButton("🎬 Create Video")
        self.stage5_create_btn.setEnabled(False)
        self.stage5_create_btn.clicked.connect(self._on_create_video)
        actions.addWidget(self.stage5_create_btn)
        self.stage5_cancel_btn = QPushButton("Cancel")
        self.stage5_cancel_btn.setEnabled(False)
        self.stage5_cancel_btn.clicked.connect(self._on_cancel_video)
        actions.addWidget(self.stage5_cancel_btn)
        self.stage5_continue_btn = QPushButton("Continue to Step 6 →")
        self.stage5_continue_btn.setEnabled(False)
        self.stage5_continue_btn.clicked.connect(self._continue_to_stage6)
        actions.addWidget(self.stage5_continue_btn)
        actions.addStretch()
        render_layout.addLayout(actions)

        self.stage5_progress = QProgressBar()
        self.stage5_progress.setRange(0, 1000)
        self.stage5_progress.setValue(0)
        self.stage5_progress.setFormat("0.0%")
        render_layout.addWidget(self.stage5_progress)
        self.stage5_status = QLabel("Ready")
        self.stage5_status.setWordWrap(True)
        render_layout.addWidget(self.stage5_status)
        layout.addWidget(render_group)

        self.stage5_result = QTextEdit()
        self.stage5_result.setReadOnly(True)
        layout.addWidget(self.stage5_result)
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
            first_path = Path(paths[0]).expanduser().resolve()
            self.document.load_original_input(
                result.text,
                source_path=str(first_path),
                input_directory=str(first_path.parent),
            )
            default_title = Path(paths[0]).stem or "Novel Title"
            self._set_job_editors(default_title, "")
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
            self.stage3_continue_btn.setEnabled(False)
            self._set_editor_text(self.stage3_output, "")
            self._set_editor_text(self.stage4_output, "")
            self._refresh_stage4_ui()
            self._video_media = None
            self._video_audio_probe = None
            self._refresh_stage5_ui()
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
            self._video_media = None
            self._video_audio_probe = None
            self.document.diagnostics.extend(diagnostics)
            self.document.stage("normalize").touch(
                f"{len(self.document.source_files)} sources",
                f"{len(chapters)} chapters", report.to_dict()
            )
            self._log(f"✓ Detected {len(chapters)} chapters")
            self._set_editor_text(self.stage1_output, normalized_text)
            self.stage1_output.setReadOnly(False)
            if not self.document.job_chapter and chapters:
                self._set_job_editors(self.document.job_title or "Novel Title", chapters[0].header_line)
            self.stage2_continue_btn.setEnabled(False)
            self.stage2_source_label.setText("Source: Step 1 ready — open Step 2 to review")
            self._refresh_stage4_ui()
            self._refresh_stage5_ui()
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
            self._video_media = None
            self._video_audio_probe = None
            self._refresh_stage4_ui()
            self._refresh_stage5_ui()
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
            from media.artifacts import write_step3_artifacts

            source_text = self.document.require_step2_confirmed_output()
            patterns = build_patterns(self.settings)
            chapters = derive_chapters_from_text(source_text, patterns, source_name="pipeline")
            if not chapters:
                self._error("No chapter boundaries found in the current pipeline output.")
                return
            title = self.stage3_title_edit.text().strip() or self.document.job_title
            chapter_label = self.stage3_chapter_edit.text().strip() or self.document.job_chapter
            if not title:
                source_name = self.document.source_files[0].name if self.document.source_files else ""
                title = Path(source_name).stem or "Novel Title"
            if not chapter_label:
                chapter_label = chapters[0].header_line
            if title != self.stage3_title_edit.text().strip() or chapter_label != self.stage3_chapter_edit.text().strip():
                self._set_job_editors(title, chapter_label)
            self.document.set_job_identity(title, chapter_label)
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
                include_header=True,
                min_chunk=max(50, int(self.settings.min_chunk_chars or 200)),
            )
            self.document.chunks = chunks
            self.document.diagnostics.extend(diagnostics)
            bundle = write_step3_artifacts(
                self.document,
                self.settings.resolved_output_dir(self.document.input_directory),
                title=title,
                chapter=chapter_label,
                chunk_limit=limit,
            )
            self.document.set_step3_artifacts(bundle)
            self._video_media = None
            self._video_audio_probe = None
            self.document.stage("clean_chunk").touch(
                f"{len(self.document.chapters)} chapters", f"{len(chunks)} chunks",
                {
                    "total_chunks": len(chunks),
                    "cleaned_before": sum(report.before_chars for report in clean_reports),
                    "cleaned_after": sum(report.after_chars for report in clean_reports),
                }
            )
            self._log(f"✓ Created {len(chunks)} chunks and Step 3 TXT/JSON bundle")
            self.stage3_output.setPlainText(
                f"TXT: {bundle.txt_path}\nJSON: {bundle.json_path}\n\nCreated {len(chunks)} chunks:\n\n" +
                "\n".join(f"• Ch {c.chapter} part {c.part}/{c.parts}: {c.char_count} chars" for c in chunks[:50])
            )
            self.stage3_continue_btn.setEnabled(True)
            self._refresh_stage4_ui()
            self._refresh_stage5_ui()
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
            str(
                self.settings.resolved_output_dir(self.document.input_directory)
                / self._default_export_filename()
            ),
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

    # ------------------------------------------------------- Step 3/4 job
    def _selected_group_size(self) -> int:
        return self.stage3_group_size.currentData() or self.stage3_custom_size.value()

    def _on_grouping_changed(self, *_):
        self.stage3_custom_size.setVisible(self.stage3_group_size.currentData() is None)
        self.document._clear_step3_artifacts()
        self.stage3_continue_btn.setEnabled(False)
        self._refresh_group_preview()
        if hasattr(self, "group4"):
            self._refresh_group_panels()

    def _refresh_group_preview(self):
        from media.groups import analyze_grouping, preview_groups
        try:
            text = self.document.require_step2_confirmed_output()
            size = self._selected_group_size()
            analysis = analyze_grouping(text, self.settings, size)
            headings, diagnostics = analysis.headings, analysis.diagnostics
            has_title = bool(self.stage3_title_edit.text().strip())
            if analysis.requires_numeric_boundaries:
                self.stage3_detection_label.setText(
                    f"Expected range: Chương {headings[0].number}-{headings[-1].number}\n"
                    f"Expected chapters: {analysis.expected_count}\n"
                    f"Detected chapter headings: {len(headings)}\n"
                    f"First chapter: {headings[0].heading}\nLast chapter: {headings[-1].heading}"
                )
                if analysis.numeric_unavailable_reason:
                    self.stage3_output.setPlainText(
                        "Some chapter numbers are missing.\n\n"
                        "Automatic numeric-boundary grouping is unavailable: " + analysis.numeric_unavailable_reason +
                        "\n\nCorrect the required chapter headings in Step 1/2 and review the document manually."
                    )
                    self.stage3_create_groups_btn.setEnabled(False)
                    self.stage3_restore_groups_btn.setEnabled(False)
                    return
                groups = analysis.numeric_groups
                self.stage3_output.setPlainText(
                    "Some chapter numbers are missing.\n\n"
                    f"Expected range: Chương {headings[0].number}-{headings[-1].number}\n"
                    f"Expected chapters: {analysis.expected_count}\n"
                    f"Detected chapter headings: {len(headings)}\n\n"
                    "The normal chapter-count grouping may produce incorrect ranges.\n\n"
                    "I can instead group by numeric chapter boundaries:\n\n" +
                    "\n".join(item["range_label"] for item in groups) +
                    "\n\nThis method ignores missing chapter headings inside each range and splits using the available boundary chapter headings."
                )
                self.stage3_create_groups_btn.setEnabled(has_title)
                self.stage3_restore_groups_btn.setEnabled(has_title)
                return

            headings, groups, diagnostics = preview_groups(text, self.settings, size)
            self.stage3_detection_label.setText(f"Detected chapters: {len(headings)}\nFirst chapter: {headings[0].heading}\nLast chapter: {headings[-1].heading}")
            self.stage3_output.setPlainText(
                f"Total chapters: {len(headings)}\nChapters per group: {size}\nOutput groups: {len(groups)}\n\n" +
                "\n".join(f"{g['order']}. {g['label']} ({len(g['chapters'])} chapters)" for g in groups) +
                ("\n\nNumbering diagnostics:\n" + "\n".join(diagnostics) if diagnostics else ""))
            self.stage3_create_groups_btn.setEnabled(has_title)
            self.stage3_restore_groups_btn.setEnabled(has_title)
        except PipelineStateError as error:
            self.stage3_detection_label.setText("Detected chapters: 0 / unavailable")
            self.stage3_output.setPlainText(str(error))
            self.stage3_create_groups_btn.setEnabled(False)
            self.stage3_restore_groups_btn.setEnabled(False)

    def _confirm_numeric_grouping(self, analysis) -> bool:
        headings = analysis.headings
        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setWindowTitle("Use Numeric Chapter Boundaries")
        dialog.setText("Some chapter numbers are missing.")
        dialog.setInformativeText(
            f"Expected range: Chương {headings[0].number}-{headings[-1].number}\n"
            f"Expected chapters: {analysis.expected_count}\n"
            f"Detected chapter headings: {len(headings)}\n\n"
            "The normal chapter-count grouping may produce incorrect ranges.\n\n"
            "I can instead group by numeric chapter boundaries:\n\n" +
            "\n".join(item["range_label"] for item in analysis.numeric_groups) +
            "\n\nThis method ignores missing chapter headings inside each range and splits using the available boundary chapter headings."
        )
        use_numeric = dialog.addButton("Use Numeric Boundaries", QMessageBox.ButtonRole.AcceptRole)
        cancel = dialog.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        dialog.setDefaultButton(cancel)
        dialog.exec()
        return dialog.clickedButton() is use_numeric

    def _on_create_group_files(self, _checked=False, *, restore=False):
        from media.groups import (GROUPING_METHOD_NUMERIC, analyze_grouping,
                                  write_groups, restore_groups)
        try:
            title = self.stage3_title_edit.text().strip()
            size = self._selected_group_size()
            if restore:
                groups = restore_groups(self.document, self.settings, title, size)
            else:
                text = self.document.require_step2_confirmed_output()
                analysis = analyze_grouping(text, self.settings, size)
                if analysis.requires_numeric_boundaries:
                    if analysis.numeric_unavailable_reason:
                        raise PipelineStateError(
                            "Automatic numeric-boundary grouping is unavailable: " + analysis.numeric_unavailable_reason
                        )
                    if not self._confirm_numeric_grouping(analysis):
                        return
                    groups = write_groups(
                        self.document, self.settings, title, size,
                        method=GROUPING_METHOD_NUMERIC,
                        confirmation_fingerprint=analysis.numeric_identity_fingerprint,
                    )
                else:
                    groups = write_groups(self.document, self.settings, title, size)
            self._remember_current_title()
            self.stage3_continue_btn.setEnabled(True)
            self._refresh_group_preview()
            self.stage3_output.append("\nGroup manifest: " + self.document.group_manifest_path + "\n" + "\n".join(g.txt_path for g in groups))
            self._refresh_group_panels()
            self.document.stage(StageKey.CLEAN_CHUNK).touch("Step 2 confirmed output", f"{len(groups)} exact chapter groups")
            self._log(f"✓ Created/restored {len(groups)} chapter groups; canonical TXT is unchanged Step 2 text.")
        except Exception as error:
            self._error(str(error))

    def _refresh_group_panels(self):
        legacy = not self.document.group_manifest_path and self.document.step3_artifacts is not None
        for stack, panel in ((self.stage4_stack, self.group4), (self.stage5_stack, self.group5), (self.stage6_stack, self.group6)):
            stack.setCurrentIndex(1 if legacy else 0)
            if not panel.busy:
                panel.refresh()

    def _set_group_batch_busy(self, index: int, busy: bool):
        self.load_btn.setEnabled(not busy)
        self.settings_btn.setEnabled(not busy)
        self.tabs.blockSignals(True)
        try:
            if busy:
                self.tabs.setCurrentIndex(index)
            for tab in range(self.tabs.count()):
                self.tabs.setTabEnabled(tab, not busy or tab == index)
        finally:
            self.tabs.blockSignals(False)

    def _set_job_editors(self, title: str, chapter: str) -> None:
        self._updating_job_widgets = True
        try:
            self.stage3_title_combo.blockSignals(True)
            self.stage3_chapter_edit.blockSignals(True)
            self.stage3_title_combo.setEditText(title or "")
            self.stage3_chapter_edit.setText(chapter or "")
        finally:
            self.stage3_title_combo.blockSignals(False)
            self.stage3_chapter_edit.blockSignals(False)
            self._updating_job_widgets = False
        self.document.set_job_identity(title, chapter)

    def _populate_title_history(self, current: str = "") -> None:
        self.stage3_title_combo.blockSignals(True)
        try:
            self.stage3_title_combo.clear()
            self.stage3_title_combo.addItems(self.settings.title_history)
            self.stage3_title_combo.setEditText(current)
        finally:
            self.stage3_title_combo.blockSignals(False)

    def _remember_current_title(self) -> None:
        title = self.stage3_title_combo.currentText().strip()
        if not title:
            return
        history = [item for item in self.settings.title_history if item != title]
        self.settings.title_history = [title, *history]
        self._populate_title_history(title)
        try:
            self.settings.save()
            self._log(f"Remembered title: {title}")
        except OSError as error:
            self._log(f"Could not save title history: {error}")

    def _on_remove_saved_title(self) -> None:
        title = self.stage3_title_combo.currentText().strip()
        if not title:
            return
        self.settings.title_history = [item for item in self.settings.title_history if item != title]
        self._populate_title_history("")
        self._on_job_identity_changed()
        try:
            self.settings.save()
            self._log(f"Removed saved title: {title}")
        except OSError as error:
            self._log(f"Could not save title history: {error}")

    def _on_job_identity_changed(self) -> None:
        if self._updating_job_widgets:
            return
        changed = self.document.set_job_identity(
            self.stage3_title_edit.text(), self.stage3_chapter_edit.text()
        )
        if changed:
            self.stage3_continue_btn.setEnabled(False)
            self._video_media = None
            self._video_audio_probe = None
            self._refresh_stage4_ui()
            self._refresh_stage5_ui()
            if hasattr(self, "stage3_group_size"):
                self._refresh_group_preview()

    def _refresh_stage4_ui(self) -> None:
        if hasattr(self, "group4"):
            self._refresh_group_panels()
        bundle = self.document.step3_artifacts
        if bundle is None:
            self.stage4_source_label.setText("Source: Run Step 3 first")
            self.stage4_title_label.setText("—")
            self.stage4_chapter_label.setText("—")
            self._set_editor_text(self.stage4_first_chapter, "")
            self.stage4_thumbnail_btn.setEnabled(False)
            self.stage4_tts_btn.setEnabled(False)
            self.stage4_failed_chunks_btn.setEnabled(False)
            self.stage4_continue_btn.setEnabled(False)
            self.stage4_thumbnail_path.setText("")
            return
        self.stage4_source_label.setText(f"TXT: {bundle.txt_path}\nJSON: {bundle.json_path}")
        self.stage4_title_label.setText(bundle.title)
        self.stage4_chapter_label.setText(bundle.chapter)
        first = self.document.chapters[0].body(include_header=True) if self.document.chapters else ""
        self._set_editor_text(self.stage4_first_chapter, first)
        tts_running = self._tts_thread is not None and self._tts_thread.isRunning()
        running = tts_running or (self._merge_thread is not None and self._merge_thread.isRunning())
        self.stage4_thumbnail_btn.setEnabled(True)
        self.stage4_tts_btn.setEnabled(not running)
        self.stage4_cancel_tts_btn.setEnabled(tts_running)
        self.stage4_failed_chunks_btn.setEnabled(bool(self.document.tts_failures))
        try:
            self.document.require_step4_outputs()
            step5_ready = True
        except PipelineStateError:
            step5_ready = False
        self.stage4_continue_btn.setEnabled(step5_ready and not running)
        if self.document.thumbnail_path and Path(self.document.thumbnail_path).is_file():
            self._show_thumbnail(Path(self.document.thumbnail_path))
        else:
            self.stage4_thumbnail_preview.setPixmap(QPixmap())
            self.stage4_thumbnail_preview.setText("No thumbnail generated")
            self.stage4_thumbnail_path.setText("")
        details = []
        if self.document.audiobook_path:
            details.append(f"Audiobook: {self.document.audiobook_path}")
        if self.document.audio_chunks_dir:
            details.append(f"Audio chunks: {self.document.audio_chunks_dir}")
        if self.document.tts_failures:
            details.append(f"Failed chunks: {len(self.document.tts_failures)}")
            first = self.document.tts_failures[0]
            error_type = first.get("error_type", "Error")
            error_message = first.get("error_message", "Unknown TTS error")
            details.append(f"Failure: {error_type}: {error_message}")
        self._set_editor_text(self.stage4_output, "\n".join(details))

    def _show_thumbnail(self, path: Path) -> None:
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            self.stage4_thumbnail_preview.setText("Could not display generated thumbnail")
            return
        self.stage4_thumbnail_preview.setText("")
        self.stage4_thumbnail_preview.setPixmap(
            pixmap.scaled(
                480, 270,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        self.stage4_thumbnail_path.setText(f"Saved thumbnail: {path}")

    def _on_generate_thumbnail(self) -> None:
        try:
            bundle = self.document.require_step3_artifacts()
        except PipelineStateError as error:
            self._error(str(error))
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select thumbnail image",
            self.settings.resolved_input_dir(),
            "Images (*.png *.jpg *.jpeg *.webp *.bmp);;All Files (*)",
        )
        if not path:
            return
        try:
            from media.thumbnail import generate_thumbnail

            output = generate_thumbnail(
                Path(path), Path(bundle.output_dir), title=bundle.title,
                chapter=bundle.chapter,
                banner_height=self.settings.thumbnail_bottom_height,
                quality=self.settings.thumbnail_jpeg_quality,
            )
            self.document.set_thumbnail_output(str(output))
            self._show_thumbnail(output)
            self._log(f"✓ Đã tạo thumbnail: {output}")
            self._video_media = None
            self._video_audio_probe = None
            self._refresh_stage4_ui()
            self._refresh_stage5_ui()
        except Exception as error:
            self._error(f"Thumbnail failed: {error}")

    def _on_generate_audiobook(self) -> None:
        try:
            from media.artifacts import artifact_paths, load_bundle_json
            from media.tts import TtsChunk, TtsProcessor

            bundle = self.document.require_step3_artifacts()
            data = load_bundle_json(bundle)
            chunks = [
                TtsChunk(
                    order=int(item["order"]),
                    chapter=int(item.get("chapter", 0)),
                    text=str(item["text"]),
                    text_sha256=str(item.get("text_sha256", "")),
                )
                for item in data.get("chunks", [])
            ]
            if not chunks:
                raise ValueError("Step 3 JSON contains no chunks.")
            paths = artifact_paths(Path(bundle.output_dir).parent, bundle.title, bundle.chapter)
            voice = str(self.settings.tts_voice or "").strip() or DEFAULT_TTS_VOICE
            self.settings.tts_voice = voice
            processor = TtsProcessor(
                chunks,
                paths["audio_dir"],
                voice=voice,
                max_concurrency=self.settings.tts_max_concurrency,
                timeout_seconds=self.settings.tts_timeout_seconds,
                retry_count=self.settings.tts_retry_count,
                fallback_retry_count=self.settings.tts_fallback_retry_count,
            )
            # Detect a missing dependency or invalid voice before launching
            # hundreds of concurrent chunk tasks.
            processor.validate_dependencies()
            self.document.set_tts_output(
                audio_chunks_dir=str(paths["audio_dir"]),
                manifest_path=str(paths["manifest"]),
                audiobook_path="",
                failures=[],
            )
            self._tts_processor = processor
            self.stage4_tts_progress.setRange(0, len(chunks))
            self.stage4_tts_progress.setValue(0)
            message = f"Đang tạo audiobook với giọng: {voice}"
            self.stage4_tts_status.setText(message)
            self._log(message)
            self._refresh_stage4_ui()
            self.stage4_tts_btn.setEnabled(False)
            self.stage4_cancel_tts_btn.setEnabled(True)
            thread = QThread(self)
            worker = _TtsWorker(processor, paths["audiobook"])
            worker.moveToThread(thread)
            thread.started.connect(worker.run)
            worker.progress.connect(self._on_tts_progress)
            worker.completed.connect(self._on_tts_completed)
            worker.failed.connect(self._on_tts_failed)
            worker.completed.connect(thread.quit)
            worker.failed.connect(thread.quit)
            thread.finished.connect(worker.deleteLater)
            thread.finished.connect(self._on_tts_thread_finished)
            self._tts_thread = thread
            self._tts_worker = worker
            thread.start()
        except Exception as error:
            self._error(f"Không thể tạo audiobook: {error}")

    def _on_tts_progress(self, complete: int, total: int, message: str) -> None:
        self.stage4_tts_progress.setRange(0, max(total, 1))
        self.stage4_tts_progress.setValue(complete)
        self.stage4_tts_status.setText(message)
        self._log(message)

    def _on_cancel_tts(self) -> None:
        if self._tts_processor is not None:
            self._tts_processor.cancel_event.set()
            self.stage4_tts_status.setText("Đang hủy; các MP3 đã hoàn tất sẽ được giữ lại…")

    def _on_review_failed_chunks(self) -> None:
        if not self.document.tts_failures:
            return
        _FailedChunksDialog(
            self.document.tts_failures,
            allow_merge=False,
            parent=self,
        ).exec()

    def _on_tts_completed(self, processor, result) -> None:
        from media.artifacts import artifact_paths

        if result.cancelled:
            self.stage4_tts_status.setText("Đã hủy. Các đoạn MP3 hoàn tất được giữ để tiếp tục sau.")
        elif result.failures:
            if not result.successful_orders:
                first = result.failures[0]
                message = (
                    "❌ Không tạo được đoạn MP3 nào; không thể gộp audiobook. "
                    f"Lỗi: {first.error_type}: {first.error_message}"
                )
                self.stage4_tts_status.setText(message)
                self._log(message)
                self._record_tts_result(processor, result)
                self._refresh_stage4_ui()
                _FailedChunksDialog(result.failures, allow_merge=False, parent=self).exec()
                return
            dialog = _FailedChunksDialog(result.failures, allow_merge=True, parent=self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                try:
                    bundle = self.document.require_step3_artifacts()
                    paths = artifact_paths(Path(bundle.output_dir).parent, bundle.title, bundle.chapter)
                    self._record_tts_result(processor, result)
                    self._start_merge_worker(processor, result, paths["audiobook"])
                    self.stage4_tts_status.setText("Đang gộp audiobook, bỏ qua các đoạn lỗi…")
                    self._refresh_stage4_ui()
                    return
                except Exception as error:
                    self._error(f"Merge failed: {error}")
            else:
                self.stage4_tts_status.setText("Đã hủy gộp. Có thể chạy lại để tiếp tục các đoạn lỗi.")
        else:
            self.stage4_tts_status.setText("✓ Đã tạo audiobook hoàn chỉnh.")

        self._record_tts_result(processor, result)
        self._refresh_stage4_ui()

    def _record_tts_result(self, processor, result) -> None:
        from media.artifacts import artifact_paths

        bundle = self.document.step3_artifacts
        if bundle is None:
            return
        paths = artifact_paths(Path(bundle.output_dir).parent, bundle.title, bundle.chapter)
        self.document.set_tts_output(
            audio_chunks_dir=str(paths["audio_dir"]),
            manifest_path=str(paths["manifest"]),
            audiobook_path=result.audiobook_path,
            failures=[item.__dict__ for item in result.failures],
        )
        self._video_media = None
        self._video_audio_probe = None
        if result.audiobook_path:
            self.document.stage(StageKey.FILTER_EXPORT).touch(
                f"{len(result.successful_orders)} audio chunks",
                "Audiobook created",
                {"failed_chunks": len(result.failures)},
            )

    def _start_merge_worker(self, processor, result, output_path) -> None:
        thread = QThread(self)
        worker = _MergeWorker(processor, result, output_path)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.completed.connect(self._on_merge_completed)
        worker.failed.connect(self._on_merge_failed)
        worker.completed.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(lambda: self._on_merge_thread_finished(thread))
        self._merge_thread = thread
        self._merge_worker = worker
        self.stage4_tts_btn.setEnabled(False)
        thread.start()

    def _on_merge_completed(self, processor, result) -> None:
        self.stage4_tts_status.setText("Đã gộp audiobook, bỏ qua các đoạn lỗi.")
        self._record_tts_result(processor, result)
        self._refresh_stage4_ui()

    def _on_merge_failed(self, message: str) -> None:
        self.stage4_tts_status.setText(f"❌ Merge failed: {message}")
        self._log(f"❌ Merge failed: {message}")

    def _on_merge_thread_finished(self, thread) -> None:
        if self._merge_thread is thread:
            self._merge_thread = None
            self._merge_worker = None
            self.stage4_tts_btn.setEnabled(self.document.step3_artifacts is not None)

    def _on_tts_failed(self, message: str) -> None:
        self.stage4_tts_status.setText(f"❌ {message}")
        self._log(f"❌ TTS failed: {message}")

    def _on_tts_thread_finished(self) -> None:
        merge_running = self._merge_thread is not None and self._merge_thread.isRunning()
        self.stage4_tts_btn.setEnabled(self.document.step3_artifacts is not None and not merge_running)
        self.stage4_cancel_tts_btn.setEnabled(False)
        self._tts_thread = None
        self._tts_worker = None
        self._tts_processor = None

    # -------------------------------------------------------------- Step 5
    def _enter_stage5(self) -> bool:
        if self.document.group_manifest_path:
            try:
                self._refresh_group_panels()
                self.group5.enter()
                return True
            except Exception as error:
                self._error(str(error))
                return False
        try:
            self._video_media = self.document.require_step4_outputs()
        except PipelineStateError as error:
            self._error(str(error))
            return False
        self._refresh_stage5_ui()
        if self._video_capabilities is None and self._video_detection_thread is None:
            self._start_video_detection()
        elif self._video_capabilities is not None:
            self._update_video_audio_probe()
            self._refresh_stage5_ui()
        return True

    def _start_video_detection(self) -> None:
        self._video_detection_error = ""
        self.stage5_capabilities.setPlainText(
            "Detecting GPU devices, FFmpeg backends, and testing H.264 encoders…"
        )
        self.stage5_status.setText("Detecting video capabilities…")
        self.stage5_create_btn.setEnabled(False)
        thread = QThread(self)
        worker = _VideoDetectionWorker()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.completed.connect(self._on_video_detection_completed)
        worker.failed.connect(self._on_video_detection_failed)
        worker.completed.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(self._on_video_detection_finished)
        self._video_detection_thread = thread
        self._video_detection_worker = worker
        thread.start()

    def _on_video_detection_completed(self, capabilities) -> None:
        self._video_capabilities = capabilities
        self._video_detection_error = ""
        selected = capabilities.selected
        if selected is not None:
            self._log(
                f"✓ Video encoder verified: {selected.name} ({selected.backend})"
                + (f" on {selected.device}" if selected.device else "")
            )
        for candidate in capabilities.candidates:
            if not candidate.verified:
                detail = (candidate.error or "probe failed").splitlines()[0]
                self._log(f"Video probe skipped/failed: {candidate.name}: {detail}")
        self._update_video_audio_probe()
        self.stage5_status.setText("Video capabilities ready.")
        self._refresh_stage5_ui()

    def _on_video_detection_failed(self, message: str) -> None:
        self._video_capabilities = None
        self._video_detection_error = message
        self.stage5_status.setText(f"❌ {message}")
        self._log(f"❌ Video capability detection failed: {message}")
        self._refresh_stage5_ui()

    def _on_video_detection_finished(self) -> None:
        self._video_detection_thread = None
        self._video_detection_worker = None

    def _update_video_audio_probe(self) -> None:
        if self._video_media is None or self._video_capabilities is None:
            self._video_audio_probe = None
            return
        try:
            from media.video import probe_audio

            self._video_audio_probe = probe_audio(
                Path(self._video_media.audiobook_path),
                self._video_capabilities.ffprobe_path,
            )
        except Exception as error:
            self._video_audio_probe = None
            self.stage5_status.setText(f"❌ Audiobook validation failed: {error}")
            self._log(f"❌ Audiobook validation failed: {error}")

    def _capability_summary(self) -> str:
        capabilities = self._video_capabilities
        if capabilities is None:
            if self._video_detection_error:
                return f"Detection failed: {self._video_detection_error}"
            return "Detecting GPU devices and testing encoders…"
        selected = capabilities.selected
        devices = capabilities.devices
        gpu = ", ".join(device.model for device in devices) or "No GPU identified"
        drivers = ", ".join(
            dict.fromkeys(device.driver for device in devices if device.driver)
        ) or "Unknown"
        lines = [
            f"GPU: {gpu}",
            f"Driver: {drivers}",
            f"FFmpeg: {capabilities.ffmpeg_version}",
            f"Hardware backends: {', '.join(capabilities.hwaccels) or 'None reported'}",
            "Listed H.264 encoders: "
            + (", ".join(capabilities.listed_h264_encoders) or "None reported"),
            f"Hardware backend: {selected.backend if selected else 'None'}",
            f"Selected encoder: {selected.name if selected else 'None'}",
            f"Device: {(selected.device or 'default') if selected else '—'}",
            "Status: " + (
                "Hardware encoding available"
                if selected and selected.hardware
                else ("CPU fallback available" if selected else "No verified encoder")
            ),
            "",
            "Real test encodes:",
        ]
        for candidate in capabilities.candidates:
            marker = "✓" if candidate.verified else "✕"
            detail = "passed" if candidate.verified else (candidate.error or "failed").splitlines()[0]
            lines.append(f"{marker} {candidate.name} ({candidate.backend}): {detail}")
        if devices:
            lines.extend(["", "Detected GPU devices:"])
            for device in devices:
                lines.append(
                    f"• {device.vendor} · {device.model} · driver {device.driver or 'unknown'}"
                    + (f" · {device.device}" if device.device else "")
                )
        return "\n".join(lines)

    def _refresh_stage5_ui(self) -> None:
        if self._video_media is not None and self._video_render_session is None:
            try:
                self._video_media = self.document.require_step4_outputs()
            except PipelineStateError:
                self._video_media = None
                self._video_audio_probe = None
        media = self._video_media
        if media is None:
            self.stage5_thumbnail_label.setText("—")
            self.stage5_audio_label.setText("—")
            self.stage5_output_label.setText("—")
            self.stage5_duration_label.setText("—")
        else:
            self.stage5_thumbnail_label.setText(media.thumbnail_path)
            self.stage5_audio_label.setText(media.audiobook_path)
            self.stage5_output_label.setText(media.video_path)
            if self._video_audio_probe is not None:
                from media.video import format_duration

                self.stage5_duration_label.setText(format_duration(self._video_audio_probe.duration))
            else:
                self.stage5_duration_label.setText("Waiting for FFprobe…")
        self.stage5_capabilities.setPlainText(self._capability_summary())
        running = self._video_render_session is not None
        ready = (
            media is not None
            and self._video_capabilities is not None
            and self._video_capabilities.selected is not None
            and self._video_audio_probe is not None
        )
        self.stage5_create_btn.setEnabled(bool(ready and not running))
        self.stage5_cancel_btn.setEnabled(running)
        try:
            self.document.require_step5_outputs()
            upload_ready = True
        except PipelineStateError:
            upload_ready = False
        self.stage5_continue_btn.setEnabled(upload_ready and not running)
        if self.document.video_path:
            metadata = self.document.video_metadata
            self.stage5_result.setPlainText(
                "Video created successfully\n"
                f"Duration: {metadata.get('duration_display', '—')}\n"
                f"File size: {metadata.get('file_size_display', '—')}\n"
                f"Encoder used: {metadata.get('encoder', '—')}\n"
                f"Render speed: {metadata.get('render_speed_display', '—')}\n"
                f"Saved to: {self.document.video_path}"
            )

    def _on_create_video(self) -> None:
        try:
            from media.video import mp3_copy_is_safe, probe_audio

            media = self.document.require_step4_outputs()
            capabilities = self._video_capabilities
            if capabilities is None or capabilities.selected is None:
                raise PipelineStateError("Video encoder detection has not completed successfully.")
            audio_probe = probe_audio(Path(media.audiobook_path), capabilities.ffprobe_path)
            audio_copy = mp3_copy_is_safe(
                Path(media.audiobook_path),
                capabilities.ffmpeg_path,
                capabilities.ffprobe_path,
                temp_dir=Path(media.output_dir),
            )
        except Exception as error:
            self._error(f"Cannot start video rendering: {error}")
            return

        self._video_media = media
        self._video_audio_probe = audio_probe
        self.stage5_progress.setValue(0)
        self.stage5_progress.setFormat("0.0%")
        self.stage5_result.setPlainText("")
        self.stage5_status.setText(
            "Starting FFmpeg · audio: " + ("MP3 stream copy" if audio_copy else "AAC 192k")
        )
        session = _VideoRenderSession(
            capabilities,
            media,
            audio_probe.duration,
            audio_copy=audio_copy,
            parent=self,
        )
        session.progress.connect(self._on_video_progress)
        session.status.connect(self._on_video_status)
        session.completed.connect(self._on_video_completed)
        session.failed.connect(self._on_video_failed)
        session.cancelled.connect(self._on_video_cancelled)
        self._video_render_session = session
        self._set_video_busy(True)
        self._refresh_stage5_ui()
        session.start()

    def _set_video_busy(self, busy: bool) -> None:
        self.load_btn.setEnabled(not busy)
        self.settings_btn.setEnabled(not busy)
        for index in range(min(4, self.tabs.count())):
            self.tabs.setTabEnabled(index, not busy)
        if self.tabs.count() > 4:
            self.tabs.setTabEnabled(4, True)
        if self.tabs.count() > 5:
            self.tabs.setTabEnabled(5, not busy)

    def _set_youtube_busy(self, busy: bool) -> None:
        self.load_btn.setEnabled(not busy)
        self.settings_btn.setEnabled(not busy)
        # Disabling the current tab can cause Qt to select each intermediate
        # tab. Block those transition handlers while securing the active job.
        self.tabs.blockSignals(True)
        try:
            if busy:
                self.tabs.setCurrentIndex(5)
            for index in range(5):
                self.tabs.setTabEnabled(index, not busy)
            self.tabs.setTabEnabled(5, True)
        finally:
            self.tabs.blockSignals(False)

    def closeEvent(self, event) -> None:
        for panel in (self.group4, self.group5, self.group6):
            if panel.busy:
                panel.cancel()
                if panel is self.group6 and panel.editor.busy:
                    panel.editor.cancel()
                self._log("Stopping the active group operation; close again after it stops. Recovery files are retained.")
                event.ignore()
                return
        if self.stage6_widget.busy:
            self.stage6_widget.cancel()
            self._log("Cancelling YouTube operation. Close the application after it stops.")
            event.ignore()
            return
        if self._video_render_session is not None:
            self._on_cancel_video()
            event.ignore()
            return
        if self._video_detection_thread is not None and self._video_detection_thread.isRunning():
            self._log("Please wait for the active encoder check to finish before closing.")
            event.ignore()
            return
        super().closeEvent(event)

    def _on_video_progress(self, update: dict) -> None:
        from media.video import format_duration

        percentage = float(update.get("percentage") or 0.0)
        speed = float(update.get("speed") or 0.0)
        elapsed = float(update.get("elapsed") or 0.0)
        eta = float(update.get("eta") or 0.0)
        self.stage5_progress.setValue(max(0, min(1000, int(round(percentage * 10)))))
        self.stage5_progress.setFormat(f"{percentage:.1f}%")
        self.stage5_status.setText(
            f"Elapsed: {format_duration(elapsed)} · Speed: {speed:.2f}x · "
            f"Estimated remaining: {format_duration(eta)}"
        )

    def _on_video_status(self, message: str) -> None:
        self.stage5_status.setText(message)
        self._log(message)

    def _on_video_completed(self, result) -> None:
        from media.video import format_duration

        metadata = result.to_dict()
        metadata["duration_display"] = format_duration(result.duration)
        metadata["file_size_display"] = f"{result.file_size / (1024 * 1024):.2f} MiB"
        metadata["render_speed_display"] = (
            f"{result.render_speed:.2f}x" if result.render_speed > 0 else "not reported"
        )
        self.document.set_video_output(result.output_path, metadata)
        self.document.stage(StageKey.VIDEO).touch(
            f"{format_duration(result.duration)} audiobook",
            "Video created",
            {"encoder": result.encoder, "file_size": result.file_size},
        )
        self.stage5_progress.setValue(1000)
        self.stage5_progress.setFormat("100.0%")
        self.stage5_status.setText("Video created successfully")
        for failure in result.attempt_errors:
            self._log(f"Video encoder fallback: {failure}")
        self._log(f"✓ Video created successfully: {result.output_path}")
        self._video_render_session = None
        self._set_video_busy(False)
        self._refresh_stage5_ui()

    def _on_video_failed(self, message: str) -> None:
        self.stage5_status.setText("❌ Video rendering failed")
        self.stage5_result.setPlainText(message)
        self._log(f"❌ Video rendering failed: {message}")
        self._video_render_session = None
        self._set_video_busy(False)
        self._refresh_stage5_ui()

    def _on_cancel_video(self) -> None:
        if self._video_render_session is not None:
            self.stage5_status.setText("Cancelling FFmpeg…")
            self._video_render_session.cancel()

    def _on_video_cancelled(self) -> None:
        self.stage5_status.setText("Video rendering cancelled; Step 3/4 files were preserved.")
        self._log("Video rendering cancelled.")
        self._video_render_session = None
        self._set_video_busy(False)
        self._refresh_stage5_ui()
    
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
        from media.groups import grouping_config
        from cleaning.textclean import CleaningOptions
        from dataclasses import asdict
        audio_config = lambda values: (asdict(CleaningOptions.from_settings(values)), values.max_chunk_chars, values.min_chunk_chars, values.tts_voice)
        old_audio = audio_config(self.settings)
        old_thumbnail = (self.settings.thumbnail_bottom_height, self.settings.thumbnail_jpeg_quality)
        grouping_method = self.document.grouping_config.get("grouping_method", "detected_chapters")
        old_grouping = grouping_config(self.settings, self._selected_group_size(), grouping_method)
        old_root = self.settings.resolved_output_dir(self.document.input_directory)
        for name in self.settings.__dataclass_fields__:
            setattr(self.settings, name, getattr(updated, name))
        if (old_grouping != grouping_config(self.settings, self._selected_group_size(), grouping_method) or
                old_root != self.settings.resolved_output_dir(self.document.input_directory)):
            self.document._clear_step3_artifacts()
            self.stage3_continue_btn.setEnabled(False)
            self._refresh_group_preview()
            self._refresh_group_panels()
        try:
            from media.groups import save_job_state
            for group in self.document.chapter_groups:
                changed = False
                if old_audio != audio_config(self.settings):
                    group.state["tts_status"] = "TTS Incomplete"
                    group.state.pop("video", None)
                    changed = True
                if old_thumbnail != (self.settings.thumbnail_bottom_height, self.settings.thumbnail_jpeg_quality):
                    group.state.pop("thumbnail", None)
                    group.state.pop("video", None)
                    changed = True
                if changed:
                    save_job_state(group)
            path = self.settings.save()
            self._apply_runtime_settings()
            self._refresh_group_panels()
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
            self._video_media = None
            self._video_audio_probe = None
            self.stage2_continue_btn.setEnabled(False)
            self.stage2_source_label.setText("Source: Step 1 changed — rescan required")
            self._refresh_stage5_ui()
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

    def _continue_to_stage4(self) -> None:
        try:
            if self.document.group_manifest_path:
                self.document.require_chapter_groups(validate_files=False, allow_empty=True)
            else:
                self.document.require_step3_artifacts()
        except PipelineStateError as error:
            self._error(str(error))
            return
        self.tabs.setCurrentIndex(3)

    def _continue_to_stage5(self) -> None:
        if self._enter_stage5():
            self.tabs.blockSignals(True)
            self.tabs.setCurrentIndex(4)
            self.tabs.blockSignals(False)

    def _enter_stage6(self) -> bool:
        try:
            self._refresh_group_panels()
            if self.document.group_manifest_path:
                self.group6.enter()
            else:
                self.stage6_widget.enter()
            return True
        except Exception as error:
            from media.youtube import YouTubeUploadError

            if isinstance(error, (PipelineStateError, YouTubeUploadError)):
                self._error(str(error))
            else:
                self._error("Cannot open Step 6. Verify the current job outputs and upload state.")
            return False

    def _continue_to_stage6(self) -> None:
        if self._enter_stage6():
            self.tabs.blockSignals(True)
            self.tabs.setCurrentIndex(5)
            self.tabs.blockSignals(False)

    def _on_tab_changed(self, index: int) -> None:
        if index == 1:
            self._enter_stage2()
        elif index == 2:
            try:
                self.document.require_step2_confirmed_output()
                self._refresh_group_preview()
            except PipelineStateError as error:
                self.tabs.blockSignals(True)
                self.tabs.setCurrentIndex(1)
                self.tabs.blockSignals(False)
                self._enter_stage2()
                self._error(str(error))
        elif index == 3:
            try:
                if self.document.group_manifest_path:
                    self.group4.enter()
                else:
                    self.document.require_step3_artifacts()
                self._refresh_stage4_ui()
            except PipelineStateError as error:
                self.tabs.blockSignals(True)
                self.tabs.setCurrentIndex(2)
                self.tabs.blockSignals(False)
                self._error(str(error))
        elif index == 4:
            if not self._enter_stage5():
                self.tabs.blockSignals(True)
                self.tabs.setCurrentIndex(3)
                self.tabs.blockSignals(False)
        elif index == 5:
            if not self._enter_stage6():
                self.tabs.blockSignals(True)
                self.tabs.setCurrentIndex(4)
                self.tabs.blockSignals(False)

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
