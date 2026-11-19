"""
Quick Action Compact Pill Buttons for Hardware Notch Overlay.
"""

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QPushButton
from PyQt6.QtCore import Qt, pyqtSignal


class QuickActionsWidget(QWidget):
    """Compact row of interactive pill action buttons."""
    mute_triggered = pyqtSignal()
    screenshot_triggered = pyqtSignal()
    dnd_triggered = pyqtSignal()
    demo_media_triggered = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # 1. Mute Button
        self.btn_mute = QPushButton("🔊", self)
        self.btn_mute.setProperty("class", "action-pill")
        self.btn_mute.setFixedSize(28, 22)
        self.btn_mute.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_mute.setToolTip("Toggle System Audio Mute")
        self.btn_mute.clicked.connect(self.mute_triggered.emit)

        # 2. Screenshot Button
        self.btn_screenshot = QPushButton("📸", self)
        self.btn_screenshot.setProperty("class", "action-pill")
        self.btn_screenshot.setFixedSize(28, 22)
        self.btn_screenshot.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_screenshot.setToolTip("Capture Screen & Copy to Clipboard")
        self.btn_screenshot.clicked.connect(self.screenshot_triggered.emit)

        # 3. DND Button
        self.btn_dnd = QPushButton("🌙", self)
        self.btn_dnd.setProperty("class", "action-pill")
        self.btn_dnd.setCheckable(True)
        self.btn_dnd.setFixedSize(28, 22)
        self.btn_dnd.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_dnd.setToolTip("Toggle Do Not Disturb")
        self.btn_dnd.clicked.connect(self.dnd_triggered.emit)

        # 4. Demo Spotify Button
        self.btn_demo = QPushButton("🎵", self)
        self.btn_demo.setProperty("class", "action-pill")
        self.btn_demo.setFixedSize(28, 22)
        self.btn_demo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_demo.setToolTip("Cycle Demo Spotify Tracks")
        self.btn_demo.clicked.connect(self.demo_media_triggered.emit)

        layout.addWidget(self.btn_mute)
        layout.addWidget(self.btn_screenshot)
        layout.addWidget(self.btn_dnd)
        layout.addWidget(self.btn_demo)

    def set_mute_state(self, is_muted: bool):
        if is_muted:
            self.btn_mute.setText("🔇")
            self.btn_mute.setStyleSheet("background-color: rgba(255, 65, 108, 0.25); color: #FF416C; border: 1px solid #FF416C;")
        else:
            self.btn_mute.setText("🔊")
            self.btn_mute.setStyleSheet("")

    def set_dnd_state(self, is_dnd: bool):
        self.btn_dnd.setChecked(is_dnd)
        if is_dnd:
            self.btn_dnd.setStyleSheet("background-color: rgba(142, 45, 226, 0.25); color: #BB6BD9; border: 1px solid #8E2DE2;")
        else:
            self.btn_dnd.setStyleSheet("")
