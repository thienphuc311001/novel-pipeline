"""Group checklists and sequential media batches (never implicit group zero)."""
from __future__ import annotations

import copy
import threading
from dataclasses import asdict
from pathlib import Path

from PyQt6.QtCore import QObject, QThread, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
                            QLabel, QPushButton, QProgressBar, QTextEdit, QFileDialog,
                            QDialog, QDialogButtonBox, QMessageBox, QLineEdit)

from media.groups import (prepare_tts, record_media, save_job_state, edit_failed_chunk,
                         record_video, record_tts_provenance)
from pipeline.document import PipelineStateError


class ActionWorker(QObject):
    progress = pyqtSignal(object)
    message = pyqtSignal(str)
    completed = pyqtSignal(object)
    failed = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, action):
        super().__init__()
        self.action = action

    def run(self):
        try:
            self.completed.emit(self.action(self))
        except Exception as error:
            from media.youtube import YouTubeUploadError
            from media.youtube_auth import YouTubeAuthError
            # Never leak an OAuth response/session URL through arbitrary HTTP
            # exceptions. TTS/FFmpeg exceptions carry useful local diagnostics.
            if getattr(self.action, "youtube", False) and not isinstance(error, (YouTubeUploadError, YouTubeAuthError, ValueError, PipelineStateError)):
                self.failed.emit("YouTube operation failed; check connection and job permissions.")
            else:
                self.failed.emit(str(error))
        finally:
            self.finished.emit()


class GroupBatchPanel(QWidget):
    busy_changed = pyqtSignal(bool)
    diagnostic = pyqtSignal(str)

    def __init__(self, document_provider, settings, parent=None):
        super().__init__(parent)
        self.document_provider, self.settings = document_provider, settings
        self.queue = []
        self.selection = []
        self.current_id = None
        self.summary = []
        self.cancel_event = threading.Event()
        self.running = False
        self.paused = False
        self.thread = None
        self.worker = None
        self._after_thread = None
        self.layout_main = QVBoxLayout(self)
        self.groups = QListWidget()
        self.groups.setMaximumHeight(155)
        self.groups.currentItemChanged.connect(self.show_selected)
        self.layout_main.addWidget(self.groups)
        actions = QHBoxLayout()
        self.select_all_btn = QPushButton("Select All")
        self.deselect_all_btn = QPushButton("Deselect All")
        self.start_btn = QPushButton("Start")
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setEnabled(False)
        for button in (self.select_all_btn, self.deselect_all_btn, self.start_btn, self.cancel_btn):
            actions.addWidget(button)
        self.select_all_btn.clicked.connect(lambda: self.check_all(True))
        self.deselect_all_btn.clicked.connect(lambda: self.check_all(False))
        self.start_btn.clicked.connect(lambda: self.start_batch())
        self.cancel_btn.clicked.connect(self.cancel)
        self.layout_main.addLayout(actions)
        self.details = QTextEdit()
        self.details.setReadOnly(True)
        self.details.setMaximumHeight(160)
        # Keep sources and the checklist side-by-side so previews/progress
        # remain useful even with a large diagnostics panel below the tabs.
        self.layout_main.removeWidget(self.groups)
        overview = QWidget()
        overview_layout = QHBoxLayout(overview)
        overview_layout.setContentsMargins(0, 0, 0, 0)
        overview_layout.addWidget(self.groups, 1)
        overview_layout.addWidget(self.details, 2)
        overview.setMaximumHeight(150)
        overview.setMinimumHeight(100)
        self.layout_main.insertWidget(0, overview)
        self.content_layout = QVBoxLayout()
        self.layout_main.addLayout(self.content_layout, 1)
        self.status = QLabel("Select chapter groups to begin.")
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.layout_main.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setValue(0)
        self.progress.setFormat("0.0%")
        self.overall_progress = QProgressBar()
        self.overall_progress.setRange(0, 1000)
        self.overall_progress.setValue(0)
        self.overall_progress.setFormat("0.0%")
        self.layout_main.addWidget(QLabel("Current group"))
        self.layout_main.addWidget(self.progress)
        self.layout_main.addWidget(QLabel("Overall batch"))
        self.layout_main.addWidget(self.overall_progress)
        self.result = QTextEdit()
        self.result.setReadOnly(True)
        self.result.setMaximumHeight(95)
        self.layout_main.addWidget(self.result)

    @property
    def busy(self):
        return self.running or self.thread is not None

    def enter(self):
        self.document_provider().require_chapter_groups()
        self.refresh()

    def status_for(self, group):
        return group.state.get("tts_status", "Ready")

    def refresh(self):
        checked = set(self.checked_ids())
        selected = self.selected_id()
        self.groups.blockSignals(True)
        self.groups.clear()
        for group in self.document_provider().chapter_groups:
            item = QListWidgetItem(f"{group.label} — {self.status_for(group)}")
            item.setData(Qt.ItemDataRole.UserRole, group.group_id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if group.group_id in checked else Qt.CheckState.Unchecked)
            self.groups.addItem(item)
            if group.group_id == selected:
                self.groups.setCurrentItem(item)
        if self.groups.currentRow() < 0 and self.groups.count():
            self.groups.setCurrentRow(0)
        self.groups.blockSignals(False)
        self.show_selected()

    def selected_id(self):
        item = self.groups.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def checked_ids(self):
        return [self.groups.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.groups.count())
                if self.groups.item(i).checkState() == Qt.CheckState.Checked]

    def check_all(self, selected):
        if self.running:
            return
        for index in range(self.groups.count()):
            self.groups.item(index).setCheckState(Qt.CheckState.Checked if selected else Qt.CheckState.Unchecked)

    def show_selected(self, *_):
        group_id = self.selected_id()
        if not group_id:
            self.details.clear()
            return
        try:
            group = self.document_provider().require_group_artifacts(group_id)
            self.details.setPlainText(f"{group.label}\nTXT: {group.txt_path}\nJSON: {group.json_path}\nFolder: {group.output_dir}")
        except Exception as error:
            self.details.setPlainText(str(error))

    def start_batch(self, ids=None):
        if self.busy:
            return
        ids = list(ids if ids is not None else self.checked_ids())
        if not ids:
            self.status.setText("Select at least one chapter group.")
            return
        try:
            for group_id in ids:
                self.document_provider().require_group_artifacts(group_id)
        except Exception as error:
            self.status.setText(str(error))
            return
        self.batch_settings = copy.deepcopy(self.settings)
        self.selection, self.queue = list(ids), list(ids)
        self.summary = []
        self.result.clear()
        self.cancel_event.clear()
        self.running, self.paused = True, False
        self.set_busy(True)
        self.next_group()

    def set_busy(self, busy):
        self.groups.setEnabled(not busy)
        self.start_btn.setEnabled(not busy)
        self.select_all_btn.setEnabled(not busy)
        self.deselect_all_btn.setEnabled(not busy)
        self.cancel_btn.setEnabled(busy)
        if hasattr(self, "continue_btn"):
            self.continue_btn.setEnabled(not busy)
        self.busy_changed.emit(busy)

    def next_group(self):
        if self.cancel_event.is_set() or not self.queue:
            self.finish_batch()
            return
        self.current_id = self.queue.pop(0)
        try:
            group = self.document_provider().require_group_artifacts(self.current_id)
            self.progress.setValue(0)
            self.status.setText(f"Group {len(self.summary) + 1} / {len(self.selection)} — {group.label}")
            for i in range(self.groups.count()):
                if self.groups.item(i).data(Qt.ItemDataRole.UserRole) == self.current_id:
                    self.groups.setCurrentRow(i)
            self.process_group(group)
        except Exception as error:
            self.group_failed(str(error))

    def update_progress(self, fraction, message):
        fraction = max(0.0, min(1.0, fraction))
        self.progress.setValue(round(1000 * fraction))
        self.progress.setFormat(f"{fraction * 100:.1f}%")
        total = max(1, len(self.selection))
        overall = (len(self.summary) + fraction) / total
        self.overall_progress.setValue(round(1000 * overall))
        self.overall_progress.setFormat(f"{overall * 100:.1f}%")
        self.status.setText(f"Group {len(self.summary) + 1} / {total}\n{message}")

    def launch(self, action, completed):
        self.thread = QThread(self)
        self.worker = ActionWorker(action)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self.on_worker_progress)
        self.worker.message.connect(self.diagnostic.emit)
        def deliver(value):
            try:
                completed(value)
            except Exception as error:
                self.group_failed(str(error))
        self.worker.completed.connect(deliver)
        self.worker.failed.connect(self.group_failed)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread_finished)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

    def on_worker_progress(self, update):
        self.update_progress(float(update.get("fraction", 0)), str(update.get("message", "")))

    def thread_finished(self):
        self.thread, self.worker = None, None
        action, self._after_thread = self._after_thread, None
        if action:
            QTimer.singleShot(0, action)

    def group_done(self, status):
        group = next((g for g in self.document_provider().chapter_groups if g.group_id == self.current_id), None)
        if group is None:
            self.cancel_event.set()
            self.finish_batch()
            return
        self.update_progress(1, status)
        self.summary.append(f"{group.label}: {status}")
        self.result.setPlainText("\n".join(self.summary))
        self.refresh()
        if self.thread is not None:
            self._after_thread = self.next_group
        else:
            QTimer.singleShot(0, self.next_group)

    def group_failed(self, message):
        group = next((g for g in self.document_provider().chapter_groups if g.group_id == self.current_id), None)
        if group is None:
            self.diagnostic.emit(message)
            self.cancel_event.set()
            self.finish_batch()
            return
        group.state["last_error"] = message
        try:
            save_job_state(group)
        except OSError:
            message += " (Cannot save job state; check disk space/permissions.)"
        self.diagnostic.emit(f"{group.label}: {message}")
        self.group_done("Failed — " + message)

    def finish_batch(self):
        self.running = False
        self.queue = []
        self.current_id = None
        self.set_busy(False)
        self.status.setText("Batch cancelled; completed files retained." if self.cancel_event.is_set() else "Batch finished. See completed/incomplete groups below.")
        self.overall_progress.setValue(round(1000 * len(self.summary) / max(1, len(self.selection))))
        self.overall_progress.setFormat(f"{100 * len(self.summary) / max(1, len(self.selection)):.1f}%")
        self.refresh()

    def cancel(self):
        self.cancel_event.set()
        self.queue = []
        self.status.setText("Đang hủy… các tệp đã hoàn thành được giữ lại.")


class TtsBatchPanel(GroupBatchPanel):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.start_btn.setText("Start TTS")
        self.cover_path = ""
        self.cover_btn = QPushButton("Select shared cover / Generate selected thumbnails")
        self.cover_btn.clicked.connect(self.select_cover)
        self.content_layout.addWidget(self.cover_btn)
        self.first_chapter = QTextEdit()
        self.first_chapter.setReadOnly(True)
        self.first_chapter.setMaximumHeight(115)
        self.content_layout.addWidget(self.first_chapter)
        self.thumbnail = QLabel()
        self.thumbnail.setMinimumWidth(210)
        self.first_chapter.setMinimumHeight(90)
        self.content_layout.removeWidget(self.first_chapter)
        preview_row = QHBoxLayout()
        preview_row.addWidget(self.first_chapter, 3)
        preview_row.addWidget(self.thumbnail, 1)
        self.content_layout.addLayout(preview_row, 1)
        actions = QHBoxLayout()
        self.failed_btn = QPushButton("View Failed Chunks")
        self.retry_btn = QPushButton("Retry Failed Chunks")
        self.edit_btn = QPushButton("Edit Text and Retry")
        self.resume_btn = QPushButton("Resume TTS")
        self.partial_btn = QPushButton("Merge with Missing Chunks")
        for button in (self.failed_btn, self.retry_btn, self.edit_btn, self.resume_btn, self.partial_btn):
            actions.addWidget(button)
        self.failed_btn.clicked.connect(self.view_failures)
        self.retry_btn.clicked.connect(lambda: self.start_batch([self.selected_id()] if self.selected_id() else []))
        self.resume_btn.clicked.connect(lambda: self.start_batch([self.selected_id()] if self.selected_id() else []))
        self.edit_btn.clicked.connect(self.edit_failure)
        self.partial_btn.clicked.connect(self.merge_partial)
        self.content_layout.addLayout(actions)

    def set_busy(self, busy):
        super().set_busy(busy)
        for button in (self.cover_btn, self.failed_btn, self.retry_btn, self.edit_btn, self.resume_btn, self.partial_btn):
            button.setEnabled(not busy)

    def show_selected(self, *_):
        super().show_selected()
        if not hasattr(self, "first_chapter") or not self.selected_id():
            return
        try:
            doc = self.document_provider()
            group = doc.require_group_artifacts(self.selected_id())
            text = Path(group.txt_path).read_bytes().decode("utf-8")
            row = group.chapters[0]
            self.first_chapter.setPlainText(text[row["start"] - group.start:row["end"] - group.start])
            pixmap = QPixmap(group.state.get("thumbnail", {}).get("path", ""))
            self.thumbnail.setPixmap(pixmap.scaled(210, 100, Qt.AspectRatioMode.KeepAspectRatio) if not pixmap.isNull() else pixmap)
            failures = group.state.get("failures", [])
            self.details.append(f"TTS: {group.state.get('tts_status', 'Not started')}\nFailed chunks: {len(failures)}\n{group.state.get('last_error', '')}\n" + "\n".join(f"Chunk {f['chunk_number']}: {f['original_text']}\n{f['error_type']}: {f['error_message']}" for f in failures))
        except Exception as error:
            self.status.setText(str(error))

    def select_cover(self):
        if self.busy:
            return
        ids = self.checked_ids()
        if not ids:
            self.status.setText("Select groups before choosing a shared cover.")
            return
        path, _ = QFileDialog.getOpenFileName(self, "Shared cover", self.document_provider().input_directory, "Images (*.jpg *.jpeg *.png *.webp *.bmp)")
        if not path:
            return
        self.cover_path = path
        try:
            from media.thumbnail import generate_thumbnail
            for group_id in ids:
                group = self.document_provider().require_group_artifacts(group_id)
                result = generate_thumbnail(Path(path), Path(group.output_dir), title=group.title, chapter=group.label,
                                            banner_height=self.settings.thumbnail_bottom_height, quality=self.settings.thumbnail_jpeg_quality)
                target = Path(group.output_dir) / "thumbnail.jpg"
                Path(result).replace(target)
                record_media(group, "thumbnail", target)
            self.status.setText(f"Đã tạo {len(ids)} thumbnail.")
            self.refresh()
        except Exception as error:
            self.status.setText(str(error))

    def processor_for(self, group, settings):
        from media.tts import TtsProcessor
        _, chunks = prepare_tts(self.document_provider(), group.group_id, settings)
        return TtsProcessor(chunks, Path(group.output_dir) / "audio_chunks", voice=settings.tts_voice,
                            max_concurrency=settings.tts_max_concurrency, timeout_seconds=settings.tts_timeout_seconds,
                            retry_count=settings.tts_retry_count, fallback_retry_count=settings.tts_fallback_retry_count,
                            cancel_event=self.cancel_event)

    def process_group(self, group):
        processor = self.processor_for(group, self.batch_settings)
        self.processor = processor
        group.state.update(tts_status="Generating", failures=[])
        group.state.pop("last_error", None)
        # A new plan withdraws authority for an old MP3, without deleting it.
        group.state.pop("audiobook", None)
        group.state.pop("video", None)
        save_job_state(group)
        output = Path(group.output_dir) / f"{group.slug}_audiobook.mp3"

        def action(worker):
            processor.progress = lambda done, total, message: worker.progress.emit({"fraction": done / max(1, total), "message": f"{group.label}\nTTS chunks: {done} / {total}\n{message}"})
            worker.message.emit(f"{group.label}: Voice {processor.voice}")
            result = processor.run()
            if not result.failures and not result.cancelled:
                processor.merge(result, output)
            return result
        self.launch(action, self.tts_completed)

    def tts_completed(self, result):
        group = self.document_provider().require_group_artifacts(self.current_id)
        group.state.update(failures=[asdict(f) for f in result.failures], successful_orders=result.successful_orders,
                           tts_status="Cancelled" if result.cancelled else "TTS Incomplete" if result.failures else "Completed")
        if group.state["tts_status"] == "Completed":
            group.state.pop("excluded_chunks", None)
        if result.audiobook_path:
            record_tts_provenance(group, self.processor)
            record_media(group, "audiobook", result.audiobook_path)
        save_job_state(group)
        self.group_done(group.state["tts_status"])

    def group_failed(self, message):
        if self.current_id:
            group = next((g for g in self.document_provider().chapter_groups if g.group_id == self.current_id), None)
            if group:
                group.state["tts_status"] = "TTS Incomplete"
        super().group_failed(message)

    def view_failures(self):
        self.show_selected()
        if not self.selected_id():
            return
        group = self.document_provider().require_group_artifacts(self.selected_id())
        dialog = QDialog(self)
        dialog.setWindowTitle(f"{group.label} — Failed chunks")
        dialog.resize(800, 550)
        layout = QVBoxLayout(dialog)
        text = QTextEdit()
        text.setReadOnly(True)
        text.setPlainText("\n\n".join(f"Chunk {f['chunk_number']}\n{f['original_text']}\nFailed part: {f.get('failed_part_text', '')}\n{f['error_type']}: {f['error_message']}" for f in group.state.get("failures", [])) or "No failed chunks.")
        layout.addWidget(text)
        dialog.exec()

    def edit_failure(self):
        if self.busy or not self.selected_id():
            return
        group = self.document_provider().require_group_artifacts(self.selected_id())
        failures = group.state.get("failures", [])
        if not failures:
            self.status.setText("No failed chunks to edit.")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Edit failed TTS chunk (canonical TXT stays unchanged)")
        dialog.resize(750, 500)
        layout = QVBoxLayout(dialog)
        choices = QListWidget()
        for failure in failures:
            item = QListWidgetItem(f"Chunk {failure['chunk_number']}")
            item.setData(Qt.ItemDataRole.UserRole, failure)
            choices.addItem(item)
        layout.addWidget(choices)
        editor = QTextEdit()
        layout.addWidget(editor)
        error_label = QLabel()
        layout.addWidget(error_label)
        choices.currentItemChanged.connect(lambda item, old: editor.setPlainText(item.data(Qt.ItemDataRole.UserRole)["original_text"]) if item else None)
        choices.setCurrentRow(0)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        layout.addWidget(buttons)
        buttons.rejected.connect(dialog.reject)

        def save():
            try:
                edit_failed_chunk(self.document_provider(), group.group_id, self.settings,
                                  choices.currentItem().data(Qt.ItemDataRole.UserRole)["chunk_number"], editor.toPlainText())
                dialog.accept()
            except Exception as error:
                error_label.setText(str(error))
        buttons.accepted.connect(save)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.start_batch([group.group_id])

    def merge_partial(self):
        if self.busy or not self.selected_id():
            return
        from media.tts import TtsResult, TtsFailure
        group = self.document_provider().require_group_artifacts(self.selected_id())
        try:
            processor = self.processor_for(group, self.settings)
            processor._load_manifest()
            successful = [c.order for c in processor.chunks if processor._is_resumable(c)]
            missing = [c.order for c in processor.chunks if c.order not in successful]
            if not successful or not missing:
                raise PipelineStateError("Partial merge requires both valid audio chunks and missing chunks.")
            if QMessageBox.question(self, "Merge with Missing Chunks", f"Exclude chunks {missing} and create a partial audiobook?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
                return
            result = TtsResult(processor.audio_dir, processor.audio_dir / "manifest.json", skipped=successful,
                               failures=[TtsFailure(n, "", "", "Missing", "Explicitly excluded", 0) for n in missing])
            self.selection = [group.group_id]
            self.queue, self.summary, self.current_id = [], [], group.group_id
            self.cancel_event.clear()
            self.running = True
            self.set_busy(True)
            def action(worker):
                processor.merge(result, Path(group.output_dir) / f"{group.slug}_audiobook.mp3", skip_failed=True)
                return result
            def completed(value):
                group.state.update(tts_status="Partial", excluded_chunks=missing)
                import json
                from media.artifacts import atomic_write_json
                manifest = json.loads(processor.manifest_path.read_text(encoding="utf-8"))
                manifest.update(partial_audiobook=True, excluded_chunks=missing, audiobook_path=value.audiobook_path)
                atomic_write_json(processor.manifest_path, manifest)
                record_tts_provenance(group, processor)
                record_media(group, "audiobook", value.audiobook_path)
                save_job_state(group)
                self.group_done(f"Partial — excluded {missing}")
            self.launch(action, completed)
        except Exception as error:
            self.status.setText(str(error))


class VideoBatchPanel(GroupBatchPanel):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.start_btn.setText("Create Videos")
        self.capabilities = None
        self.session = None
        self.capability_label = QLabel("GPU/FFmpeg: detection starts when Step 5 opens.")
        self.capability_label.setWordWrap(True)
        self.content_layout.addWidget(self.capability_label)

    def status_for(self, group):
        return group.state.get("video", {}).get("status", "Video not created") + (" (partial audio)" if group.state.get("tts_status") == "Partial" else "")

    def enter(self):
        super().enter()
        if self.capabilities is None and self.thread is None:
            from media.video import detect_video_capabilities
            self.running = True
            self.set_busy(True)
            self.current_id = self.selected_id()
            self.launch(lambda worker: detect_video_capabilities(), self.detected)

    def detected(self, capabilities):
        self.capabilities = capabilities
        selected = capabilities.selected
        self.capability_label.setText("\n".join([
            "GPU: " + (", ".join(d.model for d in capabilities.devices) or "CPU fallback"),
            "Driver: " + ", ".join(d.driver for d in capabilities.devices),
            f"FFmpeg: {capabilities.ffmpeg_version}",
            f"Selected encoder: {selected.name if selected else 'None'} · backend: {selected.backend if selected else 'None'} · device: {selected.device if selected else 'None'}",
            "Status: " + ("Hardware encoding available" if selected and selected.hardware else "Verified CPU fallback"),
            "Tested: " + "; ".join(f"{c.name}: {'verified' if c.verified else c.error}" for c in capabilities.candidates)]))
        for message in capabilities.diagnostics:
            self.diagnostic.emit(message)
        def ready():
            self.finish_batch()
            self.status.setText("GPU/FFmpeg detection complete. Select groups to create videos.")
        self._after_thread = ready

    def group_failed(self, message):
        if self.capabilities is None and not self.selection:
            self.capability_label.setText(message)
            self._after_thread = self.finish_batch
            self.diagnostic.emit(message)
            return
        super().group_failed(message)

    def show_selected(self, *_):
        super().show_selected()
        if not self.selected_id():
            return
        try:
            media = self.document_provider().require_step4_outputs(self.selected_id())
            self.details.append(f"Thumbnail: {media.thumbnail_path}\nAudio: {media.audiobook_path}\nOutput: {media.video_path}\nResolution: 1920×1080")
        except Exception as error:
            self.details.append(str(error))

    def process_group(self, group):
        from media.video import probe_audio, mp3_copy_is_safe, validate_rendered_video
        if self.capabilities is None:
            raise PipelineStateError("Wait for verified encoder detection before starting.")
        media = self.document_provider().require_step4_outputs(group.group_id)
        caps = self.capabilities
        def prepare(worker):
            audio = probe_audio(Path(media.audiobook_path), caps.ffprobe_path)
            try:
                video = self.document_provider().require_step5_outputs(group.group_id)
                validate_rendered_video(Path(video.video_path), audio.duration, caps.ffprobe_path)
                return media, audio, None
            except (PipelineStateError, ValueError, OSError, RuntimeError):
                pass
            copy_audio = mp3_copy_is_safe(Path(media.audiobook_path), caps.ffmpeg_path, caps.ffprobe_path, temp_dir=Path(group.output_dir))
            return media, audio, copy_audio
        self.launch(prepare, self.prepared)

    def prepared(self, value):
        media, audio, copy_audio = value
        self.details.append(f"Estimated duration: {audio.duration:.1f}s\nAudio: {'MP3 copy' if copy_audio else 'AAC 192k'}")
        if copy_audio is None:
            self.group_done("Skipped — current verified MP4")
            return
        self._after_thread = lambda: self.render(media, audio, copy_audio)

    def render(self, media, audio, copy_audio):
        if self.cancel_event.is_set():
            self.finish_batch()
            return
        from ui.main_window import _VideoRenderSession
        self.session = _VideoRenderSession(self.capabilities, media, audio.duration, audio_copy=copy_audio, parent=self)
        self.session.progress.connect(lambda p: self.update_progress(p["percentage"] / 100, f"{media.chapter}\nElapsed: {p['elapsed']:.1f}s / {audio.duration:.1f}s · speed {p['speed']:.1f}x · remaining {p['eta']:.1f}s"))
        self.session.status.connect(self.diagnostic.emit)
        self.session.completed.connect(self.rendered)
        self.session.failed.connect(self.render_failed)
        self.session.cancelled.connect(self.finish_batch)
        self.session.start()

    def rendered(self, result):
        try:
            record_video(self.document_provider(), self.current_id, result)
        except Exception as error:
            self.render_failed(str(error))
            return
        self.session.deleteLater()
        self.session = None
        self.group_done(f"Video created — duration {result.duration:.1f}s · {result.encoder} · {result.render_speed:.1f}x · {result.file_size} bytes · {result.output_path}")

    def render_failed(self, message):
        if self.session:
            self.session.deleteLater()
            self.session = None
        self.group_failed(message)

    def cancel(self):
        super().cancel()
        if self.session:
            self.session.cancel()


class GroupDocumentView:
    """Compatibility view with an explicit group ID, not mutable global media."""
    def __init__(self, provider, group_id):
        self.provider, self.group_id = provider, group_id

    def require_step5_outputs(self):
        return self.provider().require_step5_outputs(self.group_id())

    def set_youtube_upload_state(self, state):
        group = self.provider().require_group_artifacts(self.group_id())
        group.state["youtube"] = copy.deepcopy(state)
        save_job_state(group)


class UploadBatchPanel(GroupBatchPanel):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from ui.youtube_tab import YouTubeTab
        self.start_btn.setText("Start Uploads")
        self.titles = {}
        self._changing_title = False
        self.editor = YouTubeTab(lambda: GroupDocumentView(self.document_provider, self.selected_id), self.settings, self)
        self.editor.group_mode = True
        self.editor.diagnostic.connect(self.diagnostic.emit)
        self.editor.busy_changed.connect(self.auth_busy)
        for button in (self.editor.upload_btn, self.editor.cancel_btn, self.editor.again_btn,
                       self.editor.retry_thumbnail_btn, self.editor.retry_playlist_btn):
            button.hide()
        self.editor.progress.hide()
        self.editor.status_label.hide()
        self.editor.result.hide()
        self.content_layout.addWidget(self.editor)
        self.editor.title_edit.textChanged.connect(self.title_changed)
        actions = QHBoxLayout()
        self.again_btn = QPushButton("Upload Again (selected group)")
        self.update_btn = QPushButton("Edit Uploaded Video Metadata")
        self.resume_batch_btn = QPushButton("Resume Paused Batch")
        self.resume_batch_btn.setEnabled(False)
        self.again_btn.clicked.connect(self.upload_again)
        self.update_btn.clicked.connect(self.edit_uploaded_metadata)
        self.resume_batch_btn.clicked.connect(self.resume_batch)
        for button in (self.again_btn, self.update_btn, self.resume_batch_btn):
            actions.addWidget(button)
        self.content_layout.addLayout(actions)

    @property
    def busy(self):
        return super().busy or (hasattr(self, "editor") and self.editor.busy)

    def set_busy(self, busy):
        super().set_busy(busy)
        if hasattr(self, "editor"):
            self.editor.metadata_widget.setEnabled(not busy)
            self.editor.connect_btn.setEnabled(not busy)
            self.editor.disconnect_btn.setEnabled(not busy and bool(self.editor.account))
            for button in (self.again_btn, self.update_btn):
                button.setEnabled(not busy)

    def auth_busy(self, busy):
        if not self.running:
            self.set_busy(busy)
        if not busy:
            self.status.setText(self.editor.status_label.text())
            self.resume_batch_btn.setEnabled(self.paused and bool(self.editor.account))

    def enter(self):
        super().enter()
        configured = str(self.settings.youtube_client_secrets_path or "").strip()
        if self.editor._auth_path != configured:
            self.editor.auth, self.editor.account = None, None
            self.editor._auth_path = configured
            self.editor._restore_attempted = False
        if not self.editor._restore_attempted and not self.editor.busy:
            self.editor._restore_attempted = True
            self.editor._start("restore", lambda worker: self.editor._get_auth().restore())

    def status_for(self, group):
        from media.youtube import load_upload_state
        try:
            state = load_upload_state(group.output_dir)
            status = state.get("status", "Not uploaded")
            return status + (" — using saved metadata" if state and state.get("status") != "rejected" else "")
        except Exception as error:
            return str(error)

    def title_changed(self, text):
        if not self._changing_title and self.selected_id() and not self.running:
            self.titles[self.selected_id()] = text

    def show_selected(self, *_):
        super().show_selected()
        if not hasattr(self, "editor") or not self.selected_id():
            return
        from media.youtube import load_upload_state
        try:
            group = self.document_provider().require_group_artifacts(self.selected_id())
            state = load_upload_state(group.output_dir)
            self.editor.state = state
            self._changing_title = True
            title = self.titles.get(group.group_id, f"{group.title} | {group.label}")
            if state and state.get("status") != "rejected":
                title = state.get("updated_metadata", state.get("metadata", {})).get("title", title)
            self.editor.title_edit.setText(title)
            self.editor.title_edit.setReadOnly(bool(state and state.get("status") != "rejected"))
            self._changing_title = False
            media = self.document_provider().require_step5_outputs(group.group_id)
            self.editor.media = media
            self.editor.video_label.setText(media.video_path)
            self.editor.thumbnail_label.setText(media.thumbnail_path)
            self.details.append(f"Video: {media.video_path}\nThumbnail: {media.thumbnail_path}\n{self.status_for(group)}")
            if state.get("metadata"):
                import json
                self.details.append("Metadata actually used:\n" + json.dumps(state["metadata"], ensure_ascii=False))
        except Exception as error:
            self.editor.media = None
            self.details.append(str(error))
        self.editor._update_controls()
        self.editor.metadata_widget.setEnabled(not self.running)
        self.editor.connect_btn.setEnabled(not self.running and not self.editor.busy)
        self.editor.disconnect_btn.setEnabled(not self.running and not self.editor.busy and bool(self.editor.account))
        for button in (self.editor.upload_btn, self.editor.cancel_btn, self.editor.again_btn,
                       self.editor.retry_thumbnail_btn, self.editor.retry_playlist_btn):
            button.hide()

    def start_batch(self, ids=None, *, allow_duplicate=False):
        if self.busy:
            return
        if not self.editor.account:
            self.status.setText("Connect a YouTube account before starting.")
            return
        from media.youtube import UploadMetadata, load_upload_state
        ids = list(ids if ids is not None else self.checked_ids())
        try:
            shared = asdict(self.editor._metadata())
            metadata = {}
            for group_id in ids:
                group = self.document_provider().require_group_artifacts(group_id)
                state = load_upload_state(group.output_dir)
                row = dict(shared, title=self.titles.get(group_id, f"{group.title} | {group.label}"))
                if state and state.get("status") != "rejected" and not allow_duplicate:
                    row = state.get("metadata", row)
                value = UploadMetadata(**row)
                value.validate(require_future=not (state and state.get("status") != "rejected" and not allow_duplicate))
                metadata[group_id] = value
        except Exception as error:
            self.status.setText(str(error))
            return
        self.batch_metadata = metadata
        self.allow_duplicate = allow_duplicate
        self.batch_channel = self.editor.account["channel_id"]
        super().start_batch(ids)

    def process_group(self, group):
        from media.youtube import load_upload_state, YouTubeUploader
        state = load_upload_state(group.output_dir)
        if state.get("status") == "completed" and state.get("video_id") and not self.allow_duplicate:
            self.group_done("Skipped — already uploaded")
            return
        media = self.document_provider().require_step5_outputs(group.group_id)
        metadata = self.batch_metadata[group.group_id]
        auth = self.editor._get_auth()
        channel = self.batch_channel
        def action(worker):
            uploader = YouTubeUploader(auth.session(), auth.secret_store, cancel_event=self.cancel_event,
                                       progress=worker.progress.emit, log=worker.message.emit)
            if state.get("video_id") and not self.allow_duplicate:
                result = state
                if not result.get("thumbnail_uploaded"):
                    result = uploader.retry_thumbnail(media.output_dir, media.thumbnail_path, channel)
                if result.get("playlist_id") and not result.get("playlist_added"):
                    result = uploader.retry_playlist(media.output_dir, channel)
                return result
            return uploader.upload(media.video_path, media.thumbnail_path, media.output_dir,
                                   metadata, channel, allow_duplicate=self.allow_duplicate)
        action.youtube = True
        self.launch(action, self.upload_completed)

    def on_worker_progress(self, update):
        if "percent" in update:
            group = next((g for g in self.document_provider().chapter_groups if g.group_id == self.current_id), None)
            self.update_progress(float(update["percent"]) / 100,
                                 f"{group.label if group else ''}\n{update.get('bytes_sent', 0)} / {update.get('total_bytes', 0)} bytes · {float(update.get('speed_bps', 0)) / 1048576:.1f} MiB/s")
        else:
            super().on_worker_progress(update)

    def upload_completed(self, state):
        group = self.document_provider().require_group_artifacts(self.current_id)
        group.state["youtube"] = state
        save_job_state(group)
        if self.editor.auth is not None and self.editor.auth.account is None and not self.cancel_event.is_set():
            self.pause_for_auth()
            return
        self.group_done(state.get("status", "Finished"))

    def group_failed(self, message):
        if (self.editor.auth is not None and self.editor.auth.account is None) or "authentication" in message.lower():
            if not self.cancel_event.is_set():
                self.pause_for_auth()
                return
        super().group_failed(message)

    def pause_for_auth(self):
        self.queue.insert(0, self.current_id)
        self.running, self.paused = False, True
        self.editor.account = None
        self.editor._show_account()
        def paused():
            self.set_busy(False)
            self.status.setText("Authentication failed: batch paused. Reconnect, then Resume Paused Batch. Pending groups use saved metadata.")
            self.resume_batch_btn.setEnabled(False)
            self.refresh()
        if self.thread:
            self._after_thread = paused
        else:
            paused()

    def resume_batch(self):
        if self.busy or not self.paused or not self.editor.account:
            return
        if self.editor.account["channel_id"] != self.batch_channel:
            self.status.setText("Reconnect the original batch channel to resume.")
            return
        from media.youtube import UploadMetadata, load_upload_state
        try:
            shared = asdict(self.editor._metadata())
            for group_id in self.queue:
                group = self.document_provider().require_group_artifacts(group_id)
                state = load_upload_state(group.output_dir)
                if not state or state.get("status") == "rejected":
                    value = UploadMetadata(**dict(shared, title=self.titles.get(group_id, f"{group.title} | {group.label}")))
                    value.validate()
                    self.batch_metadata[group_id] = value
                elif state.get("metadata"):
                    self.batch_metadata[group_id] = UploadMetadata(**state["metadata"])
        except Exception as error:
            self.status.setText(str(error))
            return
        self.running, self.paused = True, False
        self.set_busy(True)
        self.resume_batch_btn.setEnabled(False)
        self.next_group()

    def cancel(self):
        super().cancel()
        if self.paused:
            self.paused = False
            self.finish_batch()

    def upload_again(self):
        if self.busy or not self.selected_id():
            return
        if QMessageBox.question(self, "Upload Again", "Check YouTube Studio first. Explicitly create another video for this group? This may create a duplicate.", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            from PyQt6.QtWidgets import QInputDialog
            title, accepted = QInputDialog.getText(self, "New upload title", "Title for this explicitly requested new upload:", text=self.editor.title_edit.text())
            if not accepted:
                return
            # Upload Again is the one operation allowed to establish new
            # insertion metadata for an already-started row.
            self.titles[self.selected_id()] = title
            self.start_batch([self.selected_id()], allow_duplicate=True)

    def edit_uploaded_metadata(self):
        if self.busy or not self.selected_id() or not self.editor.account:
            return
        from media.youtube import load_upload_state, UploadMetadata, YouTubeUploader
        from PyQt6.QtWidgets import QFormLayout, QComboBox, QCheckBox
        group = self.document_provider().require_group_artifacts(self.selected_id())
        state = load_upload_state(group.output_dir)
        if not state.get("video_id"):
            self.status.setText("Upload this group before editing its video metadata.")
            return
        old = state.get("updated_metadata", state["metadata"])
        dialog = QDialog(self)
        dialog.setWindowTitle("Update uploaded video — thumbnail/playlist unchanged")
        dialog.resize(650, 450)
        form = QFormLayout(dialog)
        title = QLineEdit(old["title"])
        description = QTextEdit(old.get("description", ""))
        tags = QLineEdit(", ".join(old.get("tags", [])))
        category = QLineEdit(old.get("category_id", "22"))
        privacy = QComboBox()
        privacy.addItems(["private", "unlisted", "public"])
        privacy.setCurrentText(old.get("privacy", "private"))
        kids = QCheckBox("Made for kids")
        kids.setChecked(old.get("made_for_kids", False))
        schedule = QLineEdit(old.get("publish_at") or "")
        schedule.setPlaceholderText("Optional future ISO timestamp; blank removes schedule")
        for name, widget in (("Title", title), ("Description", description), ("Tags", tags), ("Category ID", category), ("Visibility", privacy), ("", kids), ("Publish time", schedule)):
            form.addRow(name, widget)
        error_label = QLabel()
        form.addRow(error_label)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        form.addRow(buttons)
        buttons.rejected.connect(dialog.reject)
        accepted = []
        def validate():
            try:
                metadata = UploadMetadata(title.text(), description.toPlainText(), [t.strip() for t in tags.text().split(",") if t.strip()], category.text(), privacy.currentText(), kids.isChecked(), old.get("playlist_id"), schedule.text().strip() or None)
                metadata.validate()
                accepted.append(metadata)
                dialog.accept()
            except ValueError as error:
                error_label.setText(str(error))
        buttons.accepted.connect(validate)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        auth, channel = self.editor._get_auth(), self.editor.account["channel_id"]
        self.selection, self.summary, self.queue, self.current_id = [group.group_id], [], [], group.group_id
        self.cancel_event.clear()
        self.running = True
        self.set_busy(True)
        def action(worker):
            return YouTubeUploader(auth.session(), auth.secret_store, cancel_event=self.cancel_event).update_video_metadata(group.output_dir, channel, accepted[0])
        action.youtube = True
        self.launch(action, self.upload_completed)
