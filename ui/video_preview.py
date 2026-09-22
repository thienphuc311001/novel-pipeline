"""Full-frame preview of a Step 4 page: both required pictures plus the real text.

The preview calls the same :func:`media.video_pages.render_page` the video uses, so
what the dialog shows is exactly the 1920×1080 still that will be encoded — side
pictures included.  Nothing here re-implements or approximates the layout.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from media.video import VideoValidationError
from media.video_pages import DEFAULT_STYLE, page_chapter_label, render_page

# Shown when the job has no TTS plan yet: a real page needs real narration text.
SAMPLE_TEXT = ("Hắn bước vào căn phòng.\n\nÁnh sáng dịu dàng chiếu qua cửa sổ, phủ lên tấm thảm cũ kỹ "
               "một màu vàng nhạt.\n\nBên ngoài, tiếng mưa rơi đều đều trên mái ngói.")


def first_page_text(job_dir):
    """``(chapter_label, text, source_note)`` of the job's first planned page."""
    try:
        plan = json.loads((Path(job_dir) / "tts_chunks.json").read_text(encoding="utf-8"))
        chunks = plan.get("chunks") or []
        if chunks:
            return (page_chapter_label(chunks[0].get("chapter"), ""),
                    str(chunks[0].get("text") or ""), "chunk 1")
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        pass
    return "", SAMPLE_TEXT, "sample text (no TTS plan yet)"


def build_page_preview(output_dir, *, thumbnail, title, chapter, text, cover_image, qr_image,
                       style=DEFAULT_STYLE):
    """Render one real page exactly like the video will and return ``(path, note)``.

    A chunk that no longer fits its planned page falls back to the sample
    paragraph, so the preview still shows the whole design and says why.
    """
    target = Path(output_dir) / "page_preview.png"
    try:
        render_page(thumbnail, target, title=title, chapter=chapter, text=text, style=style,
                    left_image=cover_image, right_image=qr_image)
        return target, ""
    except VideoValidationError as error:
        render_page(thumbnail, target, title=title, chapter=chapter or "Chương 1", text=SAMPLE_TEXT,
                    style=style, left_image=cover_image, right_image=qr_image)
        return target, f"sample paragraph shown — {error}"


class VideoPreviewDialog(QDialog):
    """Modeless window that renders the whole page through a caller callback."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Video page preview — 1920×1080")
        self.setSizeGripEnabled(True)
        self.resize(1040, 760)
        layout = QVBoxLayout(self)

        hint = QLabel("Toàn bộ frame 1920×1080 sẽ được render: 2 ảnh input, tiêu đề/chương và chữ "
                      "của chunk đầu tiên — đúng như video sẽ ghi.")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.image_label = QLabel("Chưa có preview.")
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setMinimumSize(640, 360)
        layout.addWidget(self.image_label, 1)

        self.caption = QLabel("")
        self.caption.setWordWrap(True)
        self.caption.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.caption)

        buttons = QHBoxLayout()
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setToolTip("Render lại frame với ảnh và chữ hiện tại")
        self.refresh_btn.clicked.connect(self.refresh_preview)
        buttons.addWidget(self.refresh_btn)
        buttons.addStretch()
        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.hide)
        buttons.addWidget(self.close_btn)
        layout.addLayout(buttons)

        self.render_callback = None
        self._pixmap = QPixmap()
        self._work_dir = None

    def work_dir(self) -> Path:
        """Folder that owns this dialog's rendered preview (created on demand)."""
        if self._work_dir is None:
            self._work_dir = Path(tempfile.mkdtemp(prefix="video-page-preview-"))
        return self._work_dir

    def open_for(self, render_callback) -> None:
        """Show the window and render through ``render_callback() -> (path, caption)``."""
        self.render_callback = render_callback
        self.show()
        self.raise_()
        self.activateWindow()
        self.refresh_preview()

    def refresh_preview(self) -> None:
        if self.render_callback is None:
            return
        try:
            path, caption = self.render_callback()
        except Exception as error:  # the dialog must never take the window down
            self._pixmap = QPixmap()
            self.image_label.setText("Preview failed — xem thông báo bên dưới.")
            self.caption.setText(f"Không render được preview: {error}")
            return
        self._load(Path(path), caption)

    def _load(self, path: Path, caption: str) -> None:
        pixmap = QPixmap(str(path))
        self.caption.setText(caption)
        if pixmap.isNull() or pixmap.width() < 1:
            self._pixmap = QPixmap()
            self.image_label.setText("Could not display the rendered preview.")
            return
        self._pixmap = pixmap
        self.image_label.setText("")
        self._fit()

    def _fit(self) -> None:
        if self._pixmap.isNull():
            return
        self.image_label.setPixmap(self._pixmap.scaled(
            self.image_label.size(), Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._fit()
