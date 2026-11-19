"""
Interactive Reminders & To-Do Checklist Component for Dynamic Island Dashboard.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QScrollArea, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QColor

from ui.styles import get_microlabel_font, get_subtext_font


class ReminderItemWidget(QFrame):
    """Single interactive reminder row."""
    toggled = pyqtSignal(str)
    deleted = pyqtSignal(str)

    def __init__(self, item_data: dict, parent=None):
        super().__init__(parent)
        self.item_id = item_data["id"]
        self.is_completed = item_data.get("completed", False)
        self.text = item_data.get("text", "")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(8)

        # Checkbox toggle button
        self.chk_btn = QPushButton(self)
        self.chk_btn.setFixedSize(18, 18)
        self.chk_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chk_btn.clicked.connect(lambda: self.toggled.emit(self.item_id))

        # Text label
        self.label = QLabel(self.text, self)
        self.label.setFont(get_subtext_font(11))
        self.label.setWordWrap(True)

        # Delete button
        self.del_btn = QPushButton("✕", self)
        self.del_btn.setFixedSize(18, 18)
        self.del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.del_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #666672;
                border: none;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                color: #FF416C;
            }
        """)
        self.del_btn.clicked.connect(lambda: self.deleted.emit(self.item_id))

        layout.addWidget(self.chk_btn)
        layout.addWidget(self.label, 1)
        layout.addWidget(self.del_btn)

        self._update_appearance()

    def _update_appearance(self):
        if self.is_completed:
            self.chk_btn.setStyleSheet("""
                QPushButton {
                    background-color: #38EF7D;
                    border: 1px solid #38EF7D;
                    border-radius: 9px;
                    color: #0A0A0C;
                    font-size: 10px;
                    font-weight: bold;
                }
            """)
            self.chk_btn.setText("✓")
            self.label.setStyleSheet("color: #666672; text-decoration: line-through;")
        else:
            self.chk_btn.setStyleSheet("""
                QPushButton {
                    background-color: rgba(255, 255, 255, 0.06);
                    border: 1px solid rgba(255, 255, 255, 0.25);
                    border-radius: 9px;
                    color: transparent;
                }
                QPushButton:hover {
                    border: 1px solid #8E2DE2;
                    background-color: rgba(142, 45, 226, 0.15);
                }
            """)
            self.chk_btn.setText("")
            self.label.setStyleSheet("color: #E2E2EA;")


class ReminderListWidget(QWidget):
    """Checklist view and quick-add input."""
    reminder_added = pyqtSignal(str)
    reminder_toggled = pyqtSignal(str)
    reminder_deleted = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(6)

        # Header micro-label
        self.header_label = QLabel("REMINDERS & TASKS", self)
        self.header_label.setFont(get_microlabel_font())
        self.header_label.setStyleSheet("color: #A0A0AB; letter-spacing: 1px;")
        main_layout.addWidget(self.header_label)

        # Scrollable container
        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("background: transparent; border: none;")
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.container = QWidget()
        self.container.setStyleSheet("background: transparent;")
        self.items_layout = QVBoxLayout(self.container)
        self.items_layout.setContentsMargins(0, 0, 4, 0)
        self.items_layout.setSpacing(3)
        self.items_layout.addStretch()

        self.scroll.setWidget(self.container)
        main_layout.addWidget(self.scroll, 1)

        # Quick Add Input Bar
        input_box = QHBoxLayout()
        input_box.setSpacing(6)

        self.input_field = QLineEdit(self)
        self.input_field.setPlaceholderText("Add a quick reminder... (Enter)")
        self.input_field.returnPressed.connect(self._on_add)

        self.add_btn = QPushButton("+", self)
        self.add_btn.setFixedSize(28, 28)
        self.add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_btn.setStyleSheet("""
            QPushButton {
                background-color: #8E2DE2;
                color: #FFFFFF;
                border: none;
                border-radius: 14px;
                font-weight: bold;
                font-size: 15px;
            }
            QPushButton:hover {
                background-color: #A044F0;
            }
            QPushButton:pressed {
                background-color: #7216C6;
            }
        """)
        self.add_btn.clicked.connect(self._on_add)

        input_box.addWidget(self.input_field, 1)
        input_box.addWidget(self.add_btn)
        main_layout.addLayout(input_box)

    def set_reminders(self, reminders: list):
        # Clear existing items
        while self.items_layout.count() > 1:
            child = self.items_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        # Update count in header
        pending_count = sum(1 for r in reminders if not r.get("completed", False))
        self.header_label.setText(f"REMINDERS & TASKS ({pending_count} PENDING)")

        # Populate items
        for r in reminders:
            item_widget = ReminderItemWidget(r, self.container)
            item_widget.toggled.connect(self.reminder_toggled.emit)
            item_widget.deleted.connect(self.reminder_deleted.emit)
            self.items_layout.insertWidget(self.items_layout.count() - 1, item_widget)

    def _on_add(self):
        text = self.input_field.text().strip()
        if text:
            self.reminder_added.emit(text)
            self.input_field.clear()

    def focus_input(self):
        self.input_field.setFocus()
