"""
Apple iOS Style Accessory Connection Pop-up.
Recreates the iconic Apple accessory pairing/connection card (iOS style)
when Bluetooth AirPods, Over-ear Headphones, Speakers, or IEMs connect to Windows.
"""

import os
import sys
from typing import Optional, Dict, Any

from PyQt6.QtWidgets import QWidget, QApplication
from PyQt6.QtCore import (
    Qt, QRectF, QPointF, QTimer, QPropertyAnimation,
    QEasingCurve, pyqtProperty, pyqtSignal
)
from PyQt6.QtGui import (
    QPainter, QColor, QFont, QPen, QBrush,
    QPixmap, QPainterPath, QLinearGradient, QCursor
)


def get_asset_path(filename: str) -> str:
    """Resolve asset paths for both dev and PyInstaller standalone builds."""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, "assets", "devices", filename)


class DeviceConnectionPopup(QWidget):
    """
    Floating Apple-style accessory connection card.
    Slides up from the bottom of the screen with smooth spring easing,
    auto-dismisses after 5 seconds, and pauses when hovered.
    """
    closed = pyqtSignal()

    CARD_WIDTH = 340
    CARD_HEIGHT = 380
    CORNER_RADIUS = 28.0

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setMouseTracking(True)

        self._anim_progress = 0.0      # 0.0 = fully hidden, 1.0 = fully shown
        self._target_y = 0
        self._start_y = 0

        # Device info
        self._category = "airpods"
        self._title = "AirPods Pro"
        self._subtitle = "Connected to Windows"
        self._is_bluetooth = True

        # Preloaded pixmaps cache
        self._pixmaps: Dict[str, QPixmap] = {}
        self._load_device_pixmaps()

        # Close button rect & hover
        self._close_rect = QRectF(self.CARD_WIDTH - 42, 18, 24, 24)
        self._close_hovered = False

        # Action button rect & hover
        self._action_rect = QRectF(24, self.CARD_HEIGHT - 62, self.CARD_WIDTH - 48, 42)
        self._action_hovered = False
        self._action_pressed = False

        # Auto-dismiss timer (5 seconds)
        self._dismiss_timer = QTimer(self)
        self._dismiss_timer.setSingleShot(True)
        self._dismiss_timer.setInterval(5000)
        self._dismiss_timer.timeout.connect(self.hide_animated)

        # Slide & Fade animation
        self._anim = QPropertyAnimation(self, b"anim_progress")
        self._anim.setDuration(450)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self.resize(self.CARD_WIDTH, self.CARD_HEIGHT)

    def _load_device_pixmaps(self):
        """Loads and caches device preview images."""
        categories = ["airpods", "headphones", "speaker", "iem"]
        for cat in categories:
            # Prefer white background renders because card background is white #FFFFFF
            white_path = get_asset_path(f"{cat}_white.png")
            std_path = get_asset_path(f"{cat}.png")

            chosen_path = white_path if os.path.exists(white_path) else std_path
            if os.path.exists(chosen_path):
                pix = QPixmap(chosen_path)
                if not pix.isNull():
                    self._pixmaps[cat] = pix

    # ── Animation Property ──────────────────────────────────────────
    def get_anim_progress(self) -> float:
        return self._anim_progress

    def set_anim_progress(self, val: float):
        self._anim_progress = val
        # Interpolate position
        current_y = int(self._start_y + (self._target_y - self._start_y) * val)
        self.move(self.x(), current_y)
        self.update()

    anim_progress = pyqtProperty(float, get_anim_progress, set_anim_progress)

    # ── Display Trigger ─────────────────────────────────────────────
    def show_device(self, data: Dict[str, Any]):
        """
        Activates and slides in the popup with device connection details.
        data: {
            'category': 'airpods' | 'headphones' | 'speaker' | 'iem',
            'name': 'Manu’s AirPods Pro #2',
            'display_title': '...',
            'display_subtitle': '...',
            'is_bluetooth': True/False
        }
        """
        self._category = data.get("category", "airpods")
        self._title = data.get("display_title") or data.get("name") or "Audio Device"
        self._subtitle = data.get("display_subtitle") or "Connected to Windows"
        self._is_bluetooth = data.get("is_bluetooth", True)

        screen = QApplication.primaryScreen()
        if not screen:
            return

        avail = screen.availableGeometry()
        screen_geo = screen.geometry()

        # Position at bottom-center right above taskbar
        x = avail.x() + (avail.width() - self.CARD_WIDTH) // 2
        # Target sitting comfortably above taskbar with 24px margin
        self._target_y = avail.y() + avail.height() - self.CARD_HEIGHT - 24
        # Start 80px lower for smooth slide-up
        self._start_y = screen_geo.height()

        self.setGeometry(x, self._start_y, self.CARD_WIDTH, self.CARD_HEIGHT)
        self.show()

        # Animate in
        self._anim.stop()
        self._anim.setStartValue(self._anim_progress)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.start()

        # Start 5.0 second auto dismiss
        self._dismiss_timer.start(5000)

    def hide_animated(self):
        """Slides down and fades out."""
        self._dismiss_timer.stop()
        self._anim.stop()
        self._anim.setStartValue(self._anim_progress)
        self._anim.setEndValue(0.0)
        self._anim.setEasingCurve(QEasingCurve.Type.InCubic)

        def on_finished():
            if self._anim_progress <= 0.01:
                self.hide()
                self.closed.emit()

        try:
            self._anim.finished.disconnect()
        except Exception:
            pass
        self._anim.finished.connect(on_finished)
        self._anim.start()

    # ── Mouse Interaction ───────────────────────────────────────────
    def enterEvent(self, event):
        # Pause auto-dismiss when mouse hovers over card
        self._dismiss_timer.stop()
        super().enterEvent(event)

    def leaveEvent(self, event):
        # Resume auto-dismiss with 2.5s remaining when mouse leaves
        if self._anim_progress > 0.5:
            self._dismiss_timer.start(2500)
        self._close_hovered = False
        self._action_hovered = False
        self.update()
        super().leaveEvent(event)

    def mouseMoveEvent(self, event):
        pos = event.position()
        old_close = self._close_hovered
        old_act = self._action_hovered

        self._close_hovered = self._close_rect.contains(pos)
        self._action_hovered = self._action_rect.contains(pos)

        if old_close != self._close_hovered or old_act != self._action_hovered:
            self.update()

        if self._close_hovered or self._action_hovered:
            self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        else:
            self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))

        super().mouseMoveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position()
            if self._close_rect.contains(pos):
                self.hide_animated()
                return
            if self._action_rect.contains(pos):
                self._action_pressed = True
                self.update()
                return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._action_pressed:
                self._action_pressed = False
                self.update()
                pos = event.position()
                if self._action_rect.contains(pos):
                    # Clicked "Done" / "Connect"
                    self.hide_animated()
                    return
        super().mouseReleaseEvent(event)

    # ── Paint Logic ─────────────────────────────────────────────────
    def paintEvent(self, event):
        if self._anim_progress <= 0.001:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.setOpacity(max(0.0, min(1.0, self._anim_progress)))

        w = float(self.CARD_WIDTH)
        h = float(self.CARD_HEIGHT)
        rect = QRectF(0, 0, w, h)

        # 1. Subtle Outer Drop Shadow
        self._draw_shadow(painter, rect)

        # 2. Main Card Surface (Apple Pure Crisp White #FFFFFF)
        path = QPainterPath()
        path.addRoundedRect(rect.adjusted(2, 2, -2, -2), self.CORNER_RADIUS, self.CORNER_RADIUS)

        painter.save()
        painter.setClipPath(path)

        # Background Fill
        painter.fillPath(path, QBrush(QColor(255, 255, 255, 255)))

        # 3. Top-Right Close Button ('✕')
        self._draw_close_button(painter)

        # 4. Header Titles
        self._draw_header(painter, w)

        # 5. Device Center Artwork
        self._draw_device_art(painter, w)

        # 6. Action Button ("Done" / Apple Blue Pill)
        self._draw_action_button(painter)

        painter.restore()

        # 7. Subtle 1px Border Frame
        painter.setPen(QPen(QColor(0, 0, 0, 22), 1.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect.adjusted(2, 2, -2, -2), self.CORNER_RADIUS, self.CORNER_RADIUS)

        painter.end()

    def _draw_shadow(self, painter: QPainter, rect: QRectF):
        """Draws subtle multi-layer drop shadow around the card."""
        shadow_colors = [
            QColor(0, 0, 0, 18),
            QColor(0, 0, 0, 12),
            QColor(0, 0, 0, 8),
            QColor(0, 0, 0, 4)
        ]
        for i, col in enumerate(shadow_colors):
            offset = (i + 1) * 2.5
            p = QPainterPath()
            p.addRoundedRect(rect.adjusted(-offset, -offset, offset, offset), self.CORNER_RADIUS + offset, self.CORNER_RADIUS + offset)
            painter.setPen(QPen(col, 1.5))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(p)

    def _draw_close_button(self, painter: QPainter):
        """Draws subtle iOS circular '×' close button."""
        btn_rect = self._close_rect
        center = btn_rect.center()

        # Circle background
        bg_color = QColor(230, 230, 235) if self._close_hovered else QColor(242, 242, 247)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(bg_color))
        painter.drawEllipse(btn_rect)

        # '✕' icon
        pen_color = QColor(60, 60, 67, 220) if self._close_hovered else QColor(142, 142, 147)
        painter.setPen(QPen(pen_color, 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        r = 4.5
        painter.drawLine(QPointF(center.x() - r, center.y() - r), QPointF(center.x() + r, center.y() + r))
        painter.drawLine(QPointF(center.x() + r, center.y() - r), QPointF(center.x() - r, center.y() + r))

    def _draw_header(self, painter: QPainter, w: float):
        """Draws Title and Subtitle in authentic Apple typography."""
        # Title (e.g. "AirPods Pro" / "Manu's AirPods Pro #2")
        title_font = QFont("Segoe UI", 16)
        title_font.setBold(True)
        title_font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias | QFont.StyleStrategy.PreferQuality)
        painter.setFont(title_font)
        painter.setPen(QPen(QColor(29, 29, 31)))  # Apple dark gray/black #1D1D1F

        title_rect = QRectF(28, 22, w - 56, 28)
        # Elide title if too long
        fm = painter.fontMetrics()
        elided_title = fm.elidedText(self._title, Qt.TextElideMode.ElideRight, int(w - 75))
        painter.drawText(title_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, elided_title)

        # Subtitle (e.g. "Connected to Windows • Audio Output")
        sub_font = QFont("Segoe UI", 10)
        sub_font.setWeight(QFont.Weight.Medium)
        sub_font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias | QFont.StyleStrategy.PreferQuality)
        painter.setFont(sub_font)
        painter.setPen(QPen(QColor(134, 134, 139)))  # Apple subtitle gray #86868B

        sub_rect = QRectF(24, 48, w - 48, 20)
        painter.drawText(sub_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, self._subtitle)

    def _draw_device_art(self, painter: QPainter, w: float):
        """Draws the rendered 3D device visual centered on the card."""
        pix = self._pixmaps.get(self._category)
        art_size = 190.0
        art_x = (w - art_size) / 2.0
        art_y = 80.0
        art_rect = QRectF(art_x, art_y, art_size, art_size)

        if pix and not pix.isNull():
            painter.drawPixmap(art_rect.toRect(), pix)
        else:
            # Fallback procedural vector art if image is missing
            self._draw_fallback_art(painter, art_rect)

    def _draw_fallback_art(self, painter: QPainter, rect: QRectF):
        """Procedural Apple-style vector rendering fallback."""
        painter.save()
        c = rect.center()

        if self._category == "airpods":
            # AirPods Case
            case_rect = QRectF(c.x() - 44, c.y() - 32, 88, 64)
            painter.setPen(QPen(QColor(220, 220, 225), 1.5))
            painter.setBrush(QBrush(QColor(250, 250, 252)))
            painter.drawRoundedRect(case_rect, 22, 22)
            # Lid seam
            painter.setPen(QPen(QColor(210, 210, 215), 1.0))
            painter.drawLine(QPointF(case_rect.left() + 2, c.y() - 10), QPointF(case_rect.right() - 2, c.y() - 10))
            # Green status LED
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(52, 199, 89)))
            painter.drawEllipse(QRectF(c.x() - 3, c.y() + 2, 6, 6))

        elif self._category == "headphones":
            # Over-Ear Headband
            painter.setPen(QPen(QColor(180, 180, 190), 5.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawArc(QRectF(c.x() - 48, c.y() - 48, 96, 96).toRect(), 30 * 16, 120 * 16)
            # Earcups
            painter.setPen(QPen(QColor(160, 160, 170), 1.5))
            painter.setBrush(QBrush(QColor(70, 70, 75)))
            painter.drawRoundedRect(QRectF(c.x() - 50, c.y() - 12, 22, 40), 10, 10)
            painter.drawRoundedRect(QRectF(c.x() + 28, c.y() - 12, 22, 40), 10, 10)

        elif self._category == "speaker":
            # Cylinder Speaker
            spk_rect = QRectF(c.x() - 48, c.y() - 24, 96, 48)
            painter.setPen(QPen(QColor(180, 180, 185), 1.5))
            painter.setBrush(QBrush(QColor(50, 50, 55)))
            painter.drawRoundedRect(spk_rect, 14, 14)
            # Volume +
            painter.setPen(QPen(QColor(255, 255, 255, 180), 2.0))
            painter.drawLine(QPointF(c.x() - 12, c.y()), QPointF(c.x() - 4, c.y()))
            painter.drawLine(QPointF(c.x() - 8, c.y() - 4), QPointF(c.x() - 8, c.y() + 4))

        else:
            # IEM monitor shells
            iem_rect = QRectF(c.x() - 36, c.y() - 20, 72, 40)
            painter.setPen(QPen(QColor(0, 122, 255, 160), 2.0))
            painter.setBrush(QBrush(QColor(235, 245, 255, 180)))
            painter.drawRoundedRect(iem_rect, 16, 16)

        painter.restore()

    def _draw_action_button(self, painter: QPainter):
        """Draws the Apple signature blue 'Done' pill button."""
        rect = self._action_rect
        if self._action_pressed:
            rect = rect.adjusted(1, 1, -1, -1)

        # Apple Blue background #0071E3
        if self._action_hovered:
            btn_bg = QColor(20, 130, 245)
        else:
            btn_bg = QColor(0, 113, 227)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(btn_bg))
        painter.drawRoundedRect(rect, 20.0, 20.0)

        # Button Text
        btn_font = QFont("Segoe UI", 12)
        btn_font.setBold(True)
        btn_font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias | QFont.StyleStrategy.PreferQuality)
        painter.setFont(btn_font)
        painter.setPen(QPen(QColor(255, 255, 255)))

        btn_text = "Done"
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, btn_text)
