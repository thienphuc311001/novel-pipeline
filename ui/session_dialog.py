"""Choose a saved work session without starting pipeline operations."""
from datetime import datetime

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout


class SessionDialog(QDialog):
    def __init__(self, sessions, parent=None):
        super().__init__(parent)
        self.session_id = None
        self.new_session = False
        self.setWindowTitle("Phiên làm việc")
        self.resize(650, 390)
        layout = QVBoxLayout(self)
        note = QLabel("Chọn phiên để tiếp tục từ bước đã lưu. File âm thanh và video được dùng lại từ thư mục cũ.")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.items = QListWidget()
        for row in sessions:
            try:
                date = datetime.fromisoformat(row["updated_at"]).astimezone().strftime("%d/%m/%Y %H:%M")
            except ValueError:
                date = row["updated_at"]
            item = QListWidgetItem(f"{row['title']}\nBước {row['step']} · Lưu lúc {date}")
            item.setData(Qt.ItemDataRole.UserRole, row["id"])
            self.items.addItem(item)
        layout.addWidget(self.items)
        buttons = QHBoxLayout()
        open_button = QPushButton("Mở phiên")
        open_button.setEnabled(bool(sessions))
        open_button.clicked.connect(self.open_selected)
        self.items.itemDoubleClicked.connect(self.open_selected)
        new_button = QPushButton("Phiên mới")
        new_button.clicked.connect(self.create_new)
        cancel_button = QPushButton("Đóng")
        cancel_button.clicked.connect(self.reject)
        for button in (open_button, new_button, cancel_button):
            buttons.addWidget(button)
        layout.addLayout(buttons)
        if sessions:
            self.items.setCurrentRow(0)

    def open_selected(self, *_):
        item = self.items.currentItem()
        if item:
            self.session_id = item.data(Qt.ItemDataRole.UserRole)
            self.accept()

    def create_new(self):
        self.new_session = True
        self.accept()
