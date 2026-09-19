"""Small reusable controls for copying app-generated text output."""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtWidgets import QApplication, QHBoxLayout, QPushButton, QTextEdit, QWidget


def copy_text(text: str) -> None:
    """Copy *text* as plain text to the system clipboard."""
    clipboard = QApplication.clipboard()
    if clipboard is not None:
        clipboard.setText(text or "")


def add_copy_button(
    layout,
    source: QTextEdit,
    *,
    label: str = "Copy all",
    button_attr: str | None = None,
) -> QPushButton:
    """Add a copy button beside a read-only text output and return it.

    The source widget remains the same object so existing callers can continue
    to update it with ``setPlainText``/``append`` without knowing about the
    surrounding control row.
    """
    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    row.addWidget(source, 1)
    button = QPushButton(label)
    button.setToolTip("Copy all displayed text")
    button.clicked.connect(lambda: copy_text(source.toPlainText()))
    row.addWidget(button)
    layout.addLayout(row)
    if button_attr:
        setattr(source, button_attr, button)
    return button


def add_copyable_text(
    layout,
    *,
    read_only: bool = True,
    minimum_height: int | None = None,
    maximum_height: int | None = None,
    placeholder: str = "",
    button_attr: str | None = None,
) -> tuple[QTextEdit, QPushButton]:
    """Create a text output and place it with a ``Copy all`` button."""
    editor = QTextEdit()
    editor.setReadOnly(read_only)
    if minimum_height is not None:
        editor.setMinimumHeight(minimum_height)
    if maximum_height is not None:
        editor.setMaximumHeight(maximum_height)
    if placeholder:
        editor.setPlaceholderText(placeholder)
    button = add_copy_button(layout, editor, button_attr=button_attr)
    return editor, button


def add_copyable_label(
    layout,
    source: QWidget,
    getter: Callable[[], str],
    *,
    label: str = "Copy all",
) -> QPushButton:
    """Add a copy button for a display-only text block backed by labels.

    This is used for compact path/status panels where a QTextEdit would add
    unnecessary editing affordances.
    """
    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    row.addWidget(source, 1)
    button = QPushButton(label)
    button.setToolTip("Copy all displayed text")
    button.clicked.connect(lambda: copy_text(getter()))
    row.addWidget(button)
    layout.addLayout(row)
    return button
