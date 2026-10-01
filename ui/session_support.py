"""Session persistence shared by the main window's existing stage widgets."""
from dataclasses import asdict
from datetime import datetime

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog

from config.settings import Settings
from pipeline.document import PipelineDocument, PipelineStateError
from pipeline.sessions import SessionError, missing_artifacts


# Account configuration and general application preferences remain global.
GLOBAL_SETTINGS = {"youtube_client_secrets_path", "title_history", "youtube_title_tags", "window_geometry",
                   "font_size", "max_log_lines", "last_input_dir"}


class SessionSupport:
    def _session_busy(self):
        return (
            any(panel.busy for panel in (self.group4, self.group5, self.group6))
            or self.stage6_widget.busy or self._video_render_session is not None
            or any(thread is not None for thread in (
                self._tts_prepare_thread, self._tts_thread, self._merge_thread,
                self._video_detection_thread,
            ))
        )

    def _session_ui_state(self):
        panels = {}
        for name in ("group4", "group5", "group6"):
            panel = getattr(self, name)
            panels[name] = {"selected": panel.selected_id(), "checked": panel.checked_ids()}
        return {
            "tab": self.tabs.currentIndex(), "group_size": self.stage3_group_size.currentIndex(),
            "custom_size": self.stage3_custom_size.value(), "panels": panels,
            "cover_image": self.group5.cover_image, "qr_image": self.group5.qr_image,
            "upload_titles": dict(self.group6.titles),
            "upload_metadata": asdict(self.stage6_widget._metadata()),
            "group_upload_metadata": asdict(self.group6.editor._metadata()),
        }

    def _save_session(self, *, report=False, allow_busy=False):
        if self._restoring_session:
            return True
        if not (self.document.original_input_text or self.document.source_files or self.document.chapter_groups):
            return True
        if self._session_busy() and not allow_busy:
            if report:
                self._log("Chờ thao tác hiện tại kết thúc trước khi lưu hoặc chuyển phiên.")
            return False
        try:
            settings = {key: value for key, value in self.settings.to_dict().items() if key not in GLOBAL_SETTINGS}
            self._session_id = self._session_store.save(
                self.document, settings, self._session_ui_state(), self._session_id,
            )
        except SessionError as error:
            self.session_status.setText("Không lưu được phiên")
            if report:
                self._error(str(error))
            elif str(error) != self._session_save_error:
                self._log(str(error))
            self._session_save_error = str(error)
            return False
        self._session_save_error = ""
        self.session_status.setText("Đã lưu phiên " + datetime.now().strftime("%H:%M:%S"))
        self.setWindowTitle(f"Novel Pipeline v2 — {self.document.job_title or 'Phiên làm việc'}")
        return True

    def _autosave_session(self):
        if self._sessions_enabled:
            self._save_session()

    def _choose_session(self):
        if self._session_busy():
            self._log("Chờ thao tác hiện tại kết thúc trước khi chuyển phiên.")
            return
        if not self._save_session(report=True):
            return
        from ui.session_dialog import SessionDialog
        dialog = SessionDialog(self._session_store.list_sessions(), self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        if dialog.new_session:
            self._apply_session(PipelineDocument(), {}, {})
            self._session_id = None
            self.session_status.setText("Phiên mới")
            self.setWindowTitle("Novel Pipeline v2")
        elif dialog.session_id:
            self._open_session(dialog.session_id)

    def _open_session(self, session_id):
        if self._session_busy() or not self._save_session(report=True):
            return False
        try:
            document, settings, ui = self._session_store.load(session_id)
        except SessionError as error:
            self._error(str(error))
            return False
        self._apply_session(document, settings, ui)
        self._session_id = session_id
        self.session_status.setText("Đã mở phiên")
        self.setWindowTitle(f"Novel Pipeline v2 — {document.job_title or 'Phiên làm việc'}")
        missing = missing_artifacts(document)
        if missing:
            self.session_status.setText(f"Đã mở phiên · Thiếu {len(missing)} file kết quả (xem Log)")
            self._log("Phiên đã mở nhưng thiếu file kết quả; các bước vẫn kiểm tra file trước khi chạy:\n" + "\n".join(missing))
        self._log(f"Đã mở phiên ở bước {self.tabs.currentIndex() + 1}: {document.job_title}")
        return True

    def _apply_session(self, document, saved_settings, ui):
        self._restoring_session = True
        try:
            merged = self.settings.to_dict()
            merged.update({key: value for key, value in saved_settings.items() if key not in GLOBAL_SETTINGS})
            restored_settings = Settings.from_dict(merged)
            for name in self.settings.__dataclass_fields__:
                setattr(self.settings, name, getattr(restored_settings, name))
            self.document = document
            self._video_media = None
            self._video_audio_probe = None
            self._set_job_editors(document.job_title, document.job_chapter)
            for widget, value in ((self.stage3_group_size, ui.get("group_size", 0)),
                                  (self.stage3_custom_size, ui.get("custom_size", 10))):
                widget.blockSignals(True)
                if widget is self.stage3_group_size:
                    widget.setCurrentIndex(max(0, min(widget.count() - 1, int(value))))
                else:
                    widget.setValue(int(value))
                widget.blockSignals(False)
            self.stage3_custom_size.setVisible(self.stage3_group_size.currentData() is None)
            self._set_editor_text(self.stage1_output, document.normalized_text if document.normalized_text is not None else document.original_input_text)
            self.stage1_output.setReadOnly(document.normalized_text is None)
            self._set_editor_text(self.stage3_output, "")
            self._set_editor_text(self.stage4_output, "")
            self.stage3_continue_btn.setEnabled(bool(document.chapter_groups or document.step3_artifacts))
            self.group5.cover_image = ui.get("cover_image", "")
            self.group5.qr_image = ui.get("qr_image", "")
            self.group5._picked_by_user = bool(self.group5.cover_image or self.group5.qr_image)
            self.group6.titles = dict(ui.get("upload_titles", {}))
            for panel in (self.group4, self.group5, self.group6):
                panel.queue, panel.selection, panel.summary = [], [], []
                panel.current_id = None
                panel.paused = False
                panel.result.clear()
                panel.status.setText("Ready")
                panel.progress.setValue(0)
                panel.groups.clear()
            self.group6.resume_batch_btn.setEnabled(False)
            from media.youtube import UploadMetadata
            for editor, key in ((self.stage6_widget, "upload_metadata"), (self.group6.editor, "group_upload_metadata")):
                editor.media = None
                editor.title_edit.clear()
                editor.privacy_combo.setCurrentIndex(0)
                editor.category_combo.setCurrentIndex(max(0, editor.category_combo.findData("22")))
                editor.playlist_combo.setCurrentIndex(0)
                editor.state = {"metadata": ui.get(key, asdict(UploadMetadata("")))}
                editor._identity = None
                editor.video_label.setText("—")
                editor.thumbnail_label.setText("—")
                editor._restore_metadata()
                editor._story_title = document.job_title
                editor._tags_manually_edited = bool(ui.get(key, {}).get("tags"))
                editor.state = {}
                editor._show_state()
            self._refresh_group_preview()
            self._refresh_stage4_ui()
            try:
                if not document.group_manifest_path:
                    self._video_media = document.require_step4_outputs()
            except PipelineStateError:
                pass
            self._refresh_stage5_ui()
            for name, selection in ui.get("panels", {}).items():
                if name not in ("group4", "group5", "group6"):
                    continue
                panel = getattr(self, name)
                panel.groups.blockSignals(True)
                for index in range(panel.groups.count()):
                    item = panel.groups.item(index)
                    group_id = item.data(Qt.ItemDataRole.UserRole)
                    item.setCheckState(Qt.CheckState.Checked if group_id in selection.get("checked", []) else Qt.CheckState.Unchecked)
                    if group_id == selection.get("selected"):
                        panel.groups.setCurrentItem(item)
                panel.groups.blockSignals(False)
                panel.show_selected()
            self._update_status()
            tab = max(0, min(4, int(ui.get("tab", 0))))
            self.tabs.blockSignals(True)
            self.tabs.setCurrentIndex(tab)
            self.tabs.blockSignals(False)
            # Reopen the saved page without resuming a batch.
            # Local video capability detection is needed to enable rendering at Step 4.
            if tab == 3 and not missing_artifacts(document):
                self._enter_stage5()
            if not document.group_manifest_path and document.step3_artifacts:
                try:
                    editor = self.stage6_widget
                    editor.media = document.require_step5_outputs()
                    from media.youtube import load_upload_state
                    editor.state = load_upload_state(editor.media.output_dir)
                    editor._identity = (editor.media.output_dir, tuple(sorted(editor.media.video_fingerprint.items())))
                    editor.video_label.setText(editor.media.video_path)
                    editor.thumbnail_label.setText(editor.media.thumbnail_path)
                    if editor.state:
                        editor._restore_metadata()
                    editor._show_state()
                except (PipelineStateError, RuntimeError):
                    pass
            if tab == 4 and not missing_artifacts(document):
                self._enter_stage6()
        finally:
            self._restoring_session = False
