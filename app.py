#!/usr/bin/env python3
"""Entry point for the novel pipeline desktop application."""

import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer

from config.settings import Settings
from ui.main_window import MainWindow


def main():
    """Launch the application."""
    app = QApplication(sys.argv)
    app.setApplicationName("Novel Pipeline v2")
    app.setOrganizationName("NovelTools")
    
    settings = Settings.load()
    window = MainWindow(settings, enable_sessions=True)
    window.show()
    if window._session_store.list_sessions():
        QTimer.singleShot(0, window._choose_session)
    
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
