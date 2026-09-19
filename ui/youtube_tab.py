"""YouTube review/upload UI; all authentication and API work runs off-thread."""

from __future__ import annotations

import threading
from datetime import timezone

from PyQt6.QtCore import QObject, QDateTime, QThread, QUrl, Qt, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDateTimeEdit, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QProgressBar,
    QPushButton, QScrollArea, QTextEdit, QVBoxLayout, QWidget,
)

from pipeline.document import PipelineStateError
from ui.copy_controls import add_copy_button


class _YouTubeWorker(QObject):
    completed = pyqtSignal(object)
    failed = pyqtSignal(str)
    progress = pyqtSignal(object)
    message = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, action):
        super().__init__()
        self.action = action

    def run(self):
        try:
            self.completed.emit(self.action(self))
        except Exception as error:
            # Only our explicitly sanitized errors may reach the user. HTTP
            # exceptions can contain bearer session URLs or OAuth responses.
            from media.youtube import YouTubeUploadError
            from media.youtube_auth import YouTubeAuthError

            self.failed.emit(
                str(error) if isinstance(error, (YouTubeUploadError, YouTubeAuthError))
                else "YouTube operation failed. Check the connection and local job access, then retry."
            )
        finally:
            self.finished.emit()


def _size(value: float) -> str:
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{value:.1f} {unit}"
        value /= 1024
    return "0 B"


class YouTubeTab(QWidget):
    """The document, never file selectors, supplies the upload media."""

    busy_changed = pyqtSignal(bool)
    diagnostic = pyqtSignal(str)

    def __init__(self, document_provider, settings, parent=None, *, auth_factory=None):
        super().__init__(parent)
        self.document_provider = document_provider
        self.settings = settings
        self.auth_factory = auth_factory
        self.auth = None
        self.account = None
        self.media = None
        self.state = {}
        self._identity = None
        self._auth_path = None
        self._restore_attempted = False
        self._thread = None
        self._worker = None
        self._cancel = threading.Event()
        self._mode = ""
        self._build_ui()

    @property
    def busy(self):
        return self._thread is not None

    def _build_ui(self):
        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        layout = QVBoxLayout(content)
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)

        account_actions = QHBoxLayout()
        self.connect_btn = QPushButton("Connect YouTube Account")
        self.disconnect_btn = QPushButton("Disconnect")
        self.connect_btn.clicked.connect(self.connect_account)
        self.disconnect_btn.clicked.connect(self.disconnect_account)
        account_actions.addWidget(self.connect_btn)
        account_actions.addWidget(self.disconnect_btn)
        account_actions.addStretch()
        layout.addLayout(account_actions)
        account_form = QFormLayout()
        self.account_label = QLabel("Not connected")
        self.channel_label = QLabel("—")
        self.video_label = QLabel("—")
        self.thumbnail_label = QLabel("—")
        for label in (self.account_label, self.channel_label, self.video_label, self.thumbnail_label):
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setWordWrap(True)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        for name, label in (("Account", self.account_label), ("Channel", self.channel_label),
                            ("Video", self.video_label), ("Thumbnail", self.thumbnail_label)):
            account_form.addRow(name, label)
        layout.addLayout(account_form)

        self.metadata_widget = QWidget()
        form = QFormLayout(self.metadata_widget)
        self.title_edit = QLineEdit()
        self.description_edit = QTextEdit()
        self.description_edit.setMaximumHeight(100)
        self.tags_edit = QLineEdit()
        self.tags_edit.setPlaceholderText("Comma-separated tags")
        self.category_combo = QComboBox()
        self.category_combo.addItem("People & Blogs", "22")
        self.privacy_combo = QComboBox()
        for label, value in (("Private", "private"), ("Unlisted", "unlisted"), ("Public", "public")):
            self.privacy_combo.addItem(label, value)
        self.kids_check = QCheckBox("Yes, this video is made for kids")
        self.playlist_combo = QComboBox()
        self.playlist_combo.addItem("Not selected", None)
        self.schedule_check = QCheckBox("Schedule publishing (requires Private)")
        self.schedule_edit = QDateTimeEdit(QDateTime.currentDateTime().addDays(1))
        self.schedule_edit.setDisplayFormat("yyyy-MM-dd HH:mm t")
        self.schedule_edit.setCalendarPopup(True)
        self.schedule_edit.setEnabled(False)
        self.schedule_check.toggled.connect(self.schedule_edit.setEnabled)
        for name, widget in (("Title", self.title_edit), ("Description", self.description_edit),
                             ("Tags", self.tags_edit), ("Category", self.category_combo),
                             ("Visibility", self.privacy_combo), ("Made for kids", self.kids_check),
                             ("Playlist", self.playlist_combo), ("", self.schedule_check),
                             ("Publish time (local)", self.schedule_edit)):
            form.addRow(name, widget)
        layout.addWidget(self.metadata_widget)

        actions = QHBoxLayout()
        self.upload_btn = QPushButton("Upload to YouTube")
        self.cancel_btn = QPushButton("Cancel")
        self.again_btn = QPushButton("Upload Again")
        self.upload_btn.clicked.connect(self.upload)
        self.cancel_btn.clicked.connect(self.cancel)
        self.again_btn.clicked.connect(self.upload_again)
        for btn in (self.upload_btn, self.cancel_btn, self.again_btn):
            actions.addWidget(btn)
        actions.addStretch()
        outer.addLayout(actions)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setValue(0)
        self.progress.setFormat("0.0%")
        outer.addWidget(self.progress)
        self.status_label = QLabel("Ready")
        self.status_label.setTextFormat(Qt.TextFormat.PlainText)
        self.status_label.setWordWrap(True)
        outer.addWidget(self.status_label)
        self.result = QTextEdit()
        self.result.setReadOnly(True)
        self.result.setMinimumHeight(120)
        self.result.setMaximumHeight(180)
        self.result.setVisible(False)
        self.result_copy_btn = add_copy_button(outer, self.result, button_attr="copy_btn")
        retry_actions = QHBoxLayout()
        self.retry_thumbnail_btn = QPushButton("Retry Thumbnail")
        self.retry_playlist_btn = QPushButton("Retry Playlist")
        self.open_btn = QPushButton("Open YouTube Video")
        self.copy_btn = QPushButton("Copy URL")
        self.retry_thumbnail_btn.clicked.connect(lambda: self.retry_stage("thumbnail"))
        self.retry_playlist_btn.clicked.connect(lambda: self.retry_stage("playlist"))
        self.open_btn.clicked.connect(self.open_video)
        self.copy_btn.clicked.connect(self.copy_url)
        for btn in (self.retry_thumbnail_btn, self.retry_playlist_btn, self.open_btn, self.copy_btn):
            retry_actions.addWidget(btn)
        outer.addLayout(retry_actions)
        self._update_controls()

    def enter(self):
        """Both direct tab navigation and Continue use this same gate."""
        from media.youtube import load_upload_state

        self.media = self.document_provider().require_step5_outputs()
        identity = (self.media.output_dir, tuple(sorted(self.media.video_fingerprint.items())))
        self.video_label.setText(self.media.video_path)
        self.thumbnail_label.setText(self.media.thumbnail_path)
        self.state = load_upload_state(self.media.output_dir)
        if identity != self._identity:
            self._identity = identity
            self.title_edit.setText(f"{self.media.title} | {self.media.chapter}")
            self.description_edit.clear()
            self.tags_edit.clear()
            self.privacy_combo.setCurrentIndex(0)
            self.kids_check.setChecked(False)
            self.schedule_check.setChecked(False)
            self.playlist_combo.setCurrentIndex(0)
            if self.state:
                self._restore_metadata()
        self._show_state()
        configured = str(self.settings.youtube_client_secrets_path or "").strip()
        if configured != self._auth_path:
            self.auth = None
            self.account = None
            self._restore_attempted = False
            self._auth_path = configured
            self._show_account()
        if not self._restore_attempted and not self.busy:
            self._restore_attempted = True
            self._start("restore", lambda worker: self._get_auth().restore())
        self._update_controls()

    def _get_auth(self):
        if self.auth is None:
            from media.youtube_auth import YouTubeAuth

            factory = self.auth_factory or YouTubeAuth
            self.auth = factory(self.settings.youtube_client_secrets_path)
        return self.auth

    def connect_account(self):
        if not self.settings.youtube_client_secrets_path:
            self._show_error("Choose your Desktop OAuth client JSON in Settings → YouTube first.")
            return
        self._start("connect", lambda worker: self._get_auth().connect(cancel_event=self._cancel))

    def disconnect_account(self):
        self._start("disconnect", lambda worker: self._get_auth().disconnect())

    def _show_account(self):
        account = self.account or {}
        self.account_label.setText(account.get("email") or "Not connected")
        self.channel_label.setText(
            f"{account.get('channel_title', '')} ({account.get('channel_id', '')})" if account else "—"
        )
        playlist = self.playlist_combo.currentData()
        category = self.category_combo.currentData()
        self.playlist_combo.clear()
        self.playlist_combo.addItem("Not selected", None)
        for item in account.get("playlists", []):
            self.playlist_combo.addItem(item["title"], item["id"])
        self.playlist_combo.setCurrentIndex(max(0, self.playlist_combo.findData(playlist)))
        if account.get("categories"):
            self.category_combo.clear()
            for item in account["categories"]:
                self.category_combo.addItem(item["title"], item["id"])
            self.category_combo.setCurrentIndex(max(0, self.category_combo.findData(category)))
        # A resumed session must preserve the metadata sent at initiation.
        if self.state and self.state.get("session_key") and not getattr(self, "group_mode", False):
            self._restore_metadata()

    def _restore_metadata(self):
        metadata = self.state.get("metadata") or {}
        self.title_edit.setText(metadata.get("title", self.state.get("title", self.title_edit.text())))
        self.description_edit.setPlainText(metadata.get("description", ""))
        self.tags_edit.setText(", ".join(metadata.get("tags", [])))
        self.kids_check.setChecked(bool(metadata.get("made_for_kids", False)))
        for combo, key in ((self.privacy_combo, "privacy"), (self.category_combo, "category_id"),
                           (self.playlist_combo, "playlist_id")):
            value = metadata.get(key)
            if value is not None:
                index = combo.findData(value)
                if index < 0:
                    combo.addItem(str(value), value)
                    index = combo.count() - 1
                combo.setCurrentIndex(index)
        publish_at = metadata.get("publish_at")
        self.schedule_check.setChecked(bool(publish_at))
        if publish_at:
            self.schedule_edit.setDateTime(QDateTime.fromString(publish_at, Qt.DateFormat.ISODate).toLocalTime())

    def _metadata(self):
        from media.youtube import UploadMetadata

        publish_at = None
        if self.schedule_check.isChecked():
            publish_at = self.schedule_edit.dateTime().toPyDateTime().astimezone(timezone.utc).isoformat()
        return UploadMetadata(
            title=self.title_edit.text().strip(), description=self.description_edit.toPlainText(),
            tags=[tag.strip() for tag in self.tags_edit.text().split(",") if tag.strip()],
            category_id=str(self.category_combo.currentData() or ""),
            privacy=self.privacy_combo.currentData(), made_for_kids=self.kids_check.isChecked(),
            playlist_id=self.playlist_combo.currentData(), publish_at=publish_at,
        )

    def upload(self, _checked=False, *, allow_duplicate=False):
        if self.busy or not self.account:
            return
        try:
            self.media = self.document_provider().require_step5_outputs()
            bundle = self.document_provider().require_step3_artifacts()
            step4_media = self.document_provider().require_step4_outputs()
            metadata = self._metadata()
            metadata.validate()
        except (PipelineStateError, ValueError) as error:
            self._show_error(str(error))
            return
        media = self.media
        channel_id = self.account["channel_id"]

        def action(worker):
            from media.artifacts import publish_job_file_names

            worker.message.emit("Preparing the final job files…")
            publish_job_file_names(bundle, step4_media, self._cancel)
            return self._uploader(worker).upload(
                media.video_path, media.thumbnail_path, media.output_dir,
                metadata, channel_id, allow_duplicate=allow_duplicate,
            )
        self._start("upload", action)

    def upload_again(self):
        if self.busy:
            return
        answer = QMessageBox.question(
            self, "Create another YouTube upload?",
            ("This job has already been uploaded. Create another copy explicitly?"
             if self.state.get("video_id") else
             "Check YouTube Studio first to determine whether the interrupted upload completed. "
             "Choose Yes only after checking its outcome and explicitly deciding to start a new upload. "
             "This can create a duplicate if the previous upload completed."),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.upload(allow_duplicate=True)

    def retry_stage(self, stage):
        if self.busy or not self.account:
            return
        try:
            media = self.document_provider().require_step5_outputs()
        except PipelineStateError as error:
            self._show_error(str(error))
            return
        channel_id = self.account["channel_id"]

        def action(worker):
            uploader = self._uploader(worker)
            if stage == "thumbnail":
                return uploader.retry_thumbnail(media.output_dir, media.thumbnail_path, channel_id)
            return uploader.retry_playlist(media.output_dir, channel_id)
        self._start(stage, action)

    def _uploader(self, worker):
        from media.youtube import YouTubeUploader

        auth = self._get_auth()
        return YouTubeUploader(
            auth.session(), auth.secret_store, cancel_event=self._cancel,
            progress=worker.progress.emit, log=worker.message.emit,
        )

    def _start(self, mode, action):
        if self.busy:
            return
        self._mode = mode
        self._cancel.clear()
        self._thread = QThread(self)
        self._worker = _YouTubeWorker(action)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.completed.connect(self._completed)
        self._worker.failed.connect(self._failed)
        self._worker.progress.connect(self._progress)
        self._worker.message.connect(self.diagnostic.emit)
        self._worker.finished.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread_finished)
        self._thread.finished.connect(self._thread.deleteLater)
        self.status_label.setText({
            "restore": "Checking saved YouTube connection…",
            "connect": "Sign in using your system browser…",
            "disconnect": "Disconnecting…", "upload": "Uploading…",
            "thumbnail": "Retrying thumbnail…", "playlist": "Retrying playlist…",
        }.get(mode, "Working…"))
        self.busy_changed.emit(True)
        self._update_controls()
        self._thread.start()

    def _completed(self, result):
        if self._mode in ("connect", "restore", "disconnect"):
            self.account = result if self._mode != "disconnect" else None
            self._show_account()
            self.status_label.setText("YouTube account connected" if self.account else "Connect a YouTube account to upload.")
        else:
            self.state = result or {}
            if self.auth is not None and self.auth.account is None:
                self.account = None
                self._show_account()
            self.document_provider().set_youtube_upload_state(self.state)
            self._show_state()
            self.diagnostic.emit("YouTube: " + self.status_label.text())

    def _failed(self, message):
        if self.auth is not None and self.auth.account is None:
            self.account = None
            self._show_account()
        if self.media:
            from media.youtube import load_upload_state

            try:
                self.state = load_upload_state(self.media.output_dir)
                self.document_provider().set_youtube_upload_state(self.state)
                self._show_state()
            except Exception:
                pass
        self._show_error(message)

    def _show_error(self, message):
        self.status_label.setText(message)
        self.diagnostic.emit("YouTube: " + message)

    def _thread_finished(self):
        self._thread = None
        self._worker = None
        self.busy_changed.emit(False)
        self._update_controls()

    def cancel(self):
        self._cancel.set()
        self.status_label.setText("Cancelling… The current request will stop at its next safe boundary; recovery state is retained.")
        self.cancel_btn.setEnabled(False)

    def _progress(self, update):
        sent = int(update.get("bytes_sent", 0))
        total = int(update.get("total_bytes", 0))
        percent = float(update.get("percent", 100 * sent / total if total else 0))
        self.progress.setValue(max(0, min(1000, round(percent * 10))))
        self.progress.setFormat(f"{percent:.1f}%")
        self.status_label.setText(
            f"Uploading… {_size(sent)} / {_size(total)} · {percent:.1f}%\n"
            f"Upload speed: {_size(float(update.get('speed_bps', 0)))}/s"
        )

    def _show_state(self):
        state = self.state
        self.result.setVisible(bool(state))
        self.result_copy_btn.setVisible(bool(state))
        video_id = state.get("video_id")
        if video_id:
            complete = state.get("status") == "completed"
            self.status_label.setText("Upload completed" if complete else "Video uploaded; follow-up steps remain.")
            self.progress.setValue(1000)
            self.progress.setFormat("100.0%")
            lines = [
                "This job has already been uploaded.", f"Video ID: {video_id}",
                f"YouTube URL: {self._video_url()}", f"Title: {state.get('title', '')}",
                f"Visibility: {state.get('privacy', '')}",
                "✓ Video uploaded",
                "✓ Thumbnail: Uploaded" if state.get("thumbnail_uploaded") else "✗ Thumbnail: " + (state.get("thumbnail_error") or "Pending"),
                "Playlist: Not selected" if not state.get("playlist_id") else (
                    "✓ Playlist: Added" if state.get("playlist_added") else "✗ Playlist: " + (state.get("playlist_error") or "Pending")
                ),
            ]
            self.result.setPlainText("\n".join(lines))
        elif state:
            self.status_label.setText(state.get("error") or "Interrupted upload found. Resume will check the server position first.")
            self.result.setPlainText(
                f"Status: {state.get('status', 'unknown')}\n"
                f"Uploaded: {_size(state.get('bytes_sent', 0))} / {_size(state.get('total_bytes', 0))}"
            )
        else:
            self.status_label.setText("Ready")
            self.result.clear()
            self.progress.setValue(0)
            self.progress.setFormat("0.0%")
        self._update_controls()

    def _update_controls(self):
        busy = self.busy
        connected = bool(self.account)
        video_id = bool(self.state.get("video_id"))
        same_channel = connected and self.state.get("channel_id", self.account["channel_id"]) == self.account["channel_id"]
        ready = connected and self.media is not None and not busy
        self.connect_btn.setEnabled(not busy)
        self.disconnect_btn.setEnabled(connected and not busy)
        self.metadata_widget.setEnabled(not busy)
        self.upload_btn.setEnabled(ready and not video_id)
        self.upload_btn.setText("Resume Upload" if self.state and not video_id else "Upload to YouTube")
        self.cancel_btn.setEnabled(busy)
        self.again_btn.setVisible(bool(self.state))
        self.again_btn.setEnabled(ready and bool(self.state))
        self.retry_thumbnail_btn.setEnabled(ready and same_channel and video_id and not self.state.get("thumbnail_uploaded"))
        self.retry_playlist_btn.setEnabled(ready and same_channel and video_id and bool(self.state.get("playlist_id")) and not self.state.get("playlist_added"))
        self.open_btn.setEnabled(video_id)
        self.copy_btn.setEnabled(video_id)
        if getattr(self, "group_mode", False):
            for button in (self.upload_btn, self.cancel_btn, self.again_btn,
                           self.retry_thumbnail_btn, self.retry_playlist_btn):
                button.hide()
            owner = self.parent()
            if getattr(owner, "running", False):
                self.metadata_widget.setEnabled(False)
                self.connect_btn.setEnabled(False)
                self.disconnect_btn.setEnabled(False)

    def _video_url(self):
        # Build a known YouTube URL; never open arbitrary text from a job file.
        import re

        video_id = str(self.state.get("video_id") or "")
        return f"https://www.youtube.com/watch?v={video_id}" if re.fullmatch(r"[A-Za-z0-9_-]+", video_id) else ""

    def open_video(self):
        if self._video_url():
            QDesktopServices.openUrl(QUrl(self._video_url()))

    def copy_url(self):
        QApplication.clipboard().setText(self._video_url())
