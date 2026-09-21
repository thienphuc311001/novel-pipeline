"""Shared status and diagnostics log window for every pipeline step."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from ui.copy_controls import add_copy_button


class LogDialog(QDialog):
    """Modeless window that displays the log shared by every pipeline step.

    The main window creates a single instance and only hides it when the user
    closes it, so the accumulated text survives closing/reopening and stays
    readable from any step while a job keeps running.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Status & Diagnostics")
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowMinMaxButtonsHint)
        self.setSizeGripEnabled(True)
        self.resize(900, 540)

        layout = QVBoxLayout(self)

        hint = QLabel(
            "Shared log for every step. It keeps updating while a job runs, and "
            "opening or closing it never changes the active step."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        add_copy_button(layout, self.log_text, button_attr="copy_btn")

        controls = QHBoxLayout()
        self.autoscroll_check = QCheckBox("Auto-scroll to newest line")
        self.autoscroll_check.setChecked(True)
        controls.addWidget(self.autoscroll_check)
        controls.addStretch()

        self.clear_btn = QPushButton("Clear")
        self.clear_btn.setToolTip("Clear the shared log")
        self.clear_btn.clicked.connect(self.clear_log)
        controls.addWidget(self.clear_btn)

        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.hide)
        controls.addWidget(self.close_btn)
        layout.addLayout(controls)

        self.status_label = QLabel("Log is empty.")
        layout.addWidget(self.status_label)

    # ------------------------------------------------------------------- api
    def set_max_lines(self, count: int) -> None:
        """Bound the retained log like ``Settings.max_log_lines``."""
        self.log_text.document().setMaximumBlockCount(max(100, int(count or 2000)))

    def append_line(self, message: str) -> None:
        """Append one entry and keep the newest line visible while following."""
        scrollbar = self.log_text.verticalScrollBar()
        at_bottom = scrollbar.value() >= scrollbar.maximum() - 4
        self.log_text.append(str(message))
        if self.autoscroll_check.isChecked() or at_bottom:
            scrollbar.setValue(scrollbar.maximum())
        self._refresh_status()

    def lines_text(self) -> str:
        """Return the complete retained log as plain text."""
        return self.log_text.toPlainText()

    def clear_log(self) -> None:
        self.log_text.clear()
        self._refresh_status()

    def open_window(self) -> None:
        """Show the shared log without blocking the running pipeline."""
        self.show()
        self.raise_()
        self.activateWindow()

    def _refresh_status(self) -> None:
        if not self.log_text.toPlainText().strip():
            self.status_label.setText("Log is empty.")
            return
        self.status_label.setText(
            f"Showing {self.log_text.document().blockCount()} line(s) of the shared log."
        )
