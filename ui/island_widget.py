"""
Curvy Hardware Notch Overlay Window & QPainter Rendering Engine.
Features:
- Complete auto-hide when there is no music playing
- Auto pop-up when notifications arrive (with 4-second dismiss & re-hide)
- Smooth hover-to-expand at top screen bezel with auto-retract
- Moving animated gradient effect flowing across the canvas
- Custom vector playback buttons (zero ugly emoji boxes)
- Proper high-resolution 26-bar audio visualizer
- Clean typography: zero green active dot, zero top-right options, zero unwanted text.
"""

import os
import sys
import math
import time
import ctypes
from ctypes import wintypes
from typing import Optional, Dict, Any
from PIL import Image, ImageFilter, ImageEnhance

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QProgressBar
)
from PyQt6.QtCore import (
    Qt, QRectF, QPointF, QTimer, QPropertyAnimation,
    QEasingCurve, pyqtSignal, QEvent
)
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QBrush, QPainterPath,
    QRadialGradient, QLinearGradient, QFontMetrics, QFont,
    QGuiApplication, QShortcut, QKeySequence, QCursor,
    QPixmap, QImage
)

from ui.styles import (
    COMPACT_IDLE_WIDTH, COMPACT_MUSIC_WIDTH, COMPACT_HEIGHT,
    TOAST_WIDTH, TOAST_HEIGHT,
    EXPANDED_WIDTH, EXPANDED_HEIGHT,
    NOTCH_RADIUS_TOP, NOTCH_RADIUS_BOT, EXPANDED_RADIUS,
    COLOR_BEZEL, COLOR_CANVAS, COLOR_TEXT_PRIMARY,
    COLOR_TEXT_SECONDARY, COLOR_TEXT_MUTED, COLOR_ACCENT_YELLOW,
    GLOW_STATES, get_microlabel_font, get_display_font,
    get_subtext_font, DASHBOARD_STYLESHEET
)
from ui.components.visualizer import AudioVisualizerWidget
from ui.device_popup import DeviceConnectionPopup
from services.media_service import MediaService
from services.system_service import SystemService


def resource_path(relative_path: str) -> str:
    """Get absolute path to resource, works for dev and for PyInstaller"""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)


def format_seconds(seconds: int) -> str:
    m = seconds // 60
    s = seconds % 60
    return f"{m:02d}:{s:02d}"


# -------------------------------------------------------------
# Windows Fullscreen Detection (Games, Full-Screen Videos, etc.)
# -------------------------------------------------------------
try:
    _user32 = ctypes.windll.user32
    _shell32 = ctypes.windll.shell32

    class _MONITORINFO(ctypes.Structure):
        _fields_ = [
            ('cbSize', wintypes.DWORD),
            ('rcMonitor', wintypes.RECT),
            ('rcWork', wintypes.RECT),
            ('dwFlags', wintypes.DWORD)
        ]

    def is_fullscreen_app_active(self_hwnd=None) -> bool:
        """
        Detects if the foreground window is running in full-screen mode
        (games, full-screen video in Chrome/Edge/Firefox/YouTube/VLC/Netflix).
        """
        try:
            hwnd = _user32.GetForegroundWindow()
            if not hwnd or (self_hwnd and hwnd == self_hwnd):
                return False

            class_buf = ctypes.create_unicode_buffer(256)
            _user32.GetClassNameW(hwnd, class_buf, 256)
            cls = class_buf.value
            if cls in ('Progman', 'WorkerW', 'Shell_TrayWnd', 'Shell_SecondaryTrayWnd'):
                return False

            rect = wintypes.RECT()
            if not _user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                return False

            hmon = _user32.MonitorFromWindow(hwnd, 1)  # MONITOR_DEFAULTTONEAREST
            if not hmon:
                return False

            mi = _MONITORINFO()
            mi.cbSize = ctypes.sizeof(_MONITORINFO)
            if not _user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
                return False

            rc = mi.rcMonitor
            # Check if window covers the entire monitor
            if rect.left <= rc.left and rect.top <= rc.top and rect.right >= rc.right and rect.bottom >= rc.bottom:
                style = _user32.GetWindowLongW(hwnd, -16)  # GWL_STYLE
                WS_CAPTION = 0x00C00000
                if (style & WS_CAPTION) != WS_CAPTION or (style & 0x80000000) or mi.rcWork.bottom < rc.bottom:
                    return True

            # Direct3D / exclusive fullscreen game check
            qstate = ctypes.c_int()
            if _shell32.SHQueryUserNotificationState(ctypes.byref(qstate)) == 0:
                if qstate.value in (2, 3):  # QUNS_BUSY, QUNS_RUNNING_D3D_FULL_SCREEN
                    return True
        except Exception:
            pass
        return False
except Exception:
    def is_fullscreen_app_active(self_hwnd=None) -> bool:
        return False


class VectorMediaButton(QPushButton):
    """
    Sleek custom-painted vector playback button.
    Renders pure vector geometric shapes (no system emoji squares).
    """
    def __init__(self, mode="play", is_primary=False, parent=None):
        super().__init__(parent)
        self.mode = mode
        self.is_primary = is_primary
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        if is_primary:
            self.setFixedSize(58, 34)
        else:
            self.setFixedSize(42, 30)

    def set_mode(self, mode: str):
        if self.mode != mode:
            self.mode = mode
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = float(self.width())
        h = float(self.height())
        cx = w / 2.0
        cy = h / 2.0

        rect = QRectF(0, 0, w, h)
        rad = h / 2.0

        is_down = self.isDown()
        is_hover = self.underMouse()

        if self.is_primary:
            grad = QLinearGradient(0, 0, 0, h)
            if is_down:
                grad.setColorAt(0.0, QColor("#E6C000"))
                grad.setColorAt(1.0, QColor("#CC9C00"))
            elif is_hover:
                grad.setColorAt(0.0, QColor("#FFE24D"))
                grad.setColorAt(1.0, QColor("#FFBC1A"))
            else:
                grad.setColorAt(0.0, QColor("#FFD600"))
                grad.setColorAt(1.0, QColor("#FFAC00"))

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(grad))
            painter.drawRoundedRect(rect, rad, rad)

            painter.setBrush(QColor("#0A0A0C"))
            if self.mode == "pause":
                bar_w = 3.5
                bar_h = 13.0
                gap = 3.5
                painter.drawRoundedRect(QRectF(cx - gap - bar_w / 2.0, cy - bar_h / 2.0, bar_w, bar_h), 1.2, 1.2)
                painter.drawRoundedRect(QRectF(cx + gap - bar_w / 2.0, cy - bar_h / 2.0, bar_w, bar_h), 1.2, 1.2)
            else:
                tri = QPainterPath()
                tri.moveTo(cx - 4.5, cy - 6.5)
                tri.lineTo(cx + 6.5, cy)
                tri.lineTo(cx - 4.5, cy + 6.5)
                tri.closeSubpath()
                painter.drawPath(tri)
        else:
            bg_alpha = 45 if is_hover else (60 if is_down else 24)
            border_alpha = 70 if is_hover else 32
            painter.setPen(QPen(QColor(255, 255, 255, border_alpha), 1.0))
            painter.setBrush(QColor(255, 255, 255, bg_alpha))
            painter.drawRoundedRect(rect, rad, rad)

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#FFFFFF"))
            if self.mode == "prev":
                painter.drawRoundedRect(QRectF(cx - 6.0, cy - 5.5, 2.0, 11.0), 1.0, 1.0)
                tri = QPainterPath()
                tri.moveTo(cx + 5.0, cy - 5.5)
                tri.lineTo(cx - 3.0, cy)
                tri.lineTo(cx + 5.0, cy + 5.5)
                tri.closeSubpath()
                painter.drawPath(tri)
            elif self.mode == "next":
                painter.drawRoundedRect(QRectF(cx + 4.0, cy - 5.5, 2.0, 11.0), 1.0, 1.0)
                tri = QPainterPath()
                tri.moveTo(cx - 5.0, cy - 5.5)
                tri.lineTo(cx + 3.0, cy)
                tri.lineTo(cx - 5.0, cy + 5.5)
                tri.closeSubpath()
                painter.drawPath(tri)


class DynamicIslandWidget(QWidget):
    """
    Curvy hardware notch desktop overlay with moving gradient effect,
    hover-to-expand, and auto-hide when there is no music.
    """
    state_changed = pyqtSignal(str)

    def __init__(self, media_service: MediaService, system_service: SystemService, device_service: Optional[Any] = None):
        super().__init__()
        self.media_service = media_service
        self.system_service = system_service
        self.device_service = device_service

        # States: "compact", "toast", "expanded", "device_popup"
        self._island_state = "compact"
        self._glow_state = "idle"

        # Device Connection Pop-up Cache & Auto-Dismiss Timer (Native Dynamic Island Pop-up)
        self._device_info: Dict[str, Any] = {}
        self._device_pixmaps: Dict[str, QPixmap] = {}
        self._device_close_hovered = False
        self._device_done_hovered = False
        self._load_device_pixmaps()

        self._device_dismiss_timer = QTimer(self)
        self._device_dismiss_timer.setSingleShot(True)
        self._device_dismiss_timer.timeout.connect(self._on_device_dismiss_timeout)

        # Hover-to-expand / Hover-to-retract timers
        self._hover_expand_timer = QTimer(self)
        self._hover_expand_timer.setSingleShot(True)
        self._hover_expand_timer.timeout.connect(self._on_hover_expand_triggered)

        self._hover_collapse_timer = QTimer(self)
        self._hover_collapse_timer.setSingleShot(True)
        self._hover_collapse_timer.timeout.connect(self._on_hover_collapse_triggered)

        # Ambient Glow Engine
        idle_glow = GLOW_STATES["idle"]
        self._current_glow_c1 = QColor(idle_glow["color1"])
        self._current_glow_c2 = QColor(idle_glow["color2"])
        self._current_glow_opacity = idle_glow["opacity"]
        self._target_glow_c1 = QColor(idle_glow["color1"])
        self._target_glow_c2 = QColor(idle_glow["color2"])
        self._target_glow_opacity = idle_glow["opacity"]

        # Moving Gradient Phase (Undulating liquid light effect)
        self._gradient_shift = 0.0

        # Album Art & Frosted Glass
        self._album_art_pixmap: Optional[QPixmap] = None
        self._glass_bg_pixmap: Optional[QPixmap] = None
        self._current_art_path: Optional[str] = None

        # Battery Status
        self._battery_info = self.system_service.get_battery_info()

        # Mini Equalizer Physics for Compact Mode
        self._mini_eq_heights = [0.2, 0.4, 0.6, 0.3]
        self._mini_eq_phase = 0.0

        # Animation & Physics
        self._geo_animation: Optional[QPropertyAnimation] = None
        self._ticker_offset = 0.0
        self._hovered = False

        # Current Data Cache
        self._time_str = "12:37 PM"
        self._date_str = "Today"
        self._media_info: Dict[str, Any] = {
            "has_media": False,
            "is_playing": False,
            "title": "",
            "artist": "",
            "album": "",
            "position": 0,
            "duration": 210,
            "album_art_path": None
        }
        self._toast_info: Dict[str, Any] = {
            "app": "",
            "title": "",
            "message": "",
            "time": 0
        }
        self._toast_dismiss_timer = QTimer(self)
        self._toast_dismiss_timer.setSingleShot(True)
        self._toast_dismiss_timer.timeout.connect(self._on_toast_timeout)

        self._flash_timer = QTimer(self)
        self._flash_timer.setSingleShot(True)
        self._flash_timer.timeout.connect(self._on_flash_timeout)
        self._flash_message: Optional[str] = None

        # Music idle debounce timer (smooth hide without flicker)
        self._music_idle_timer = QTimer(self)
        self._music_idle_timer.setSingleShot(True)
        self._music_idle_timer.setInterval(1200)
        self._music_idle_timer.timeout.connect(self._on_music_idle_timeout)

        # Fullscreen detection timer (completely hide in games & full-screen videos)
        self._is_fullscreen_suppressed = False
        self._fullscreen_timer = QTimer(self)
        self._fullscreen_timer.setInterval(350)
        self._fullscreen_timer.timeout.connect(self._check_fullscreen_mode)
        self._fullscreen_timer.start()

        # Setup Window Flags & Attributes
        self._setup_window_flags()

        # Build Interactive Dashboard Layout (Expanded State)
        self._init_dashboard_ui()

        # 60 FPS Render Timer
        self._render_timer = QTimer(self)
        self._render_timer.setInterval(16)
        self._render_timer.timeout.connect(self._on_render_tick)
        self._render_timer.start()

        # Ticker Timer
        self._ticker_timer = QTimer(self)
        self._ticker_timer.setInterval(35)
        self._ticker_timer.timeout.connect(self._on_ticker_tick)
        self._ticker_timer.start()

        # Connect Service Signals
        self._connect_signals()

        # Keyboard Shortcuts
        self._shortcut = QShortcut(QKeySequence("Alt+Space"), self)
        self._shortcut.activated.connect(self.toggle_expanded)
        self._esc_shortcut = QShortcut(QKeySequence("Esc"), self)
        self._esc_shortcut.activated.connect(self.collapse_to_compact)

        # Initial Positioning
        self._apply_geometry_for_state("compact", animate=False)

        # Multi-monitor & Resolution Awareness
        app = QGuiApplication.instance()
        if app:
            app.screenAdded.connect(self._on_screens_changed)
            app.screenRemoved.connect(self._on_screens_changed)
            primary = app.primaryScreen()
            if primary:
                primary.geometryChanged.connect(self._on_screens_changed)

        # Auto-hide if no music actively playing at launch
        if not self._is_music_active():
            self.hide()

    def _load_device_pixmaps(self):
        """Preloads device artwork for instant display."""
        for cat in ["airpods", "headphones", "speaker", "iem"]:
            p = resource_path(os.path.join("assets", "devices", f"{cat}.png"))
            if not os.path.exists(p):
                p = resource_path(os.path.join("assets", "devices", f"{cat}_white.png"))
            if os.path.exists(p):
                pix = QPixmap(p)
                if not pix.isNull():
                    self._device_pixmaps[cat] = pix

    def _on_device_dismiss_timeout(self):
        """Auto-collapse the device pop-up after timeout."""
        if self._island_state == "device_popup":
            self.collapse_to_compact()

    def _is_music_active(self) -> bool:
        """True only if media session exists AND is actively playing."""
        return bool(self._media_info.get("has_media", False) and self._media_info.get("is_playing", False))

    def _on_music_idle_timeout(self):
        """Called when music has been stopped/paused after grace duration."""
        if not self._is_music_active() and self._island_state not in ("toast", "expanded"):
            if self.isVisible():
                self.hide()

    def _on_screens_changed(self, *args):
        """Auto-recenter when monitor resolution changes or displays are plugged/unplugged."""
        self._apply_geometry_for_state(self._island_state, animate=False)

    def _check_fullscreen_mode(self):
        """
        Periodically checks if a full-screen game, video, or presentation is active.
        Completely hides the island if so, and restores when exiting.
        """
        try:
            self_hwnd = int(self.winId()) if self.effectiveWinId() else None
        except Exception:
            self_hwnd = None

        is_fs = is_fullscreen_app_active(self_hwnd)
        if is_fs != self._is_fullscreen_suppressed:
            self._is_fullscreen_suppressed = is_fs
            if is_fs:
                # Fullscreen game or video is active: completely hide!
                if self.isVisible():
                    self.hide()
            else:
                # Exited fullscreen game/video: restore if music is actively playing
                if self._is_music_active() and not self.isVisible():
                    self.show()
                    self.raise_()

    # -------------------------------------------------------------
    # Window Flags & Positioning Flush at Top (y = 0)
    # -------------------------------------------------------------
    def _setup_window_flags(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet(DASHBOARD_STYLESHEET)
        self.setMouseTracking(True)

    def _get_target_rect(self, state: str) -> tuple[int, int, int, int]:
        screen = QGuiApplication.primaryScreen()
        screen_geo = screen.geometry() if screen else QRectF(0, 0, 1920, 1080)

        if state == "compact":
            w = COMPACT_MUSIC_WIDTH
            h = COMPACT_HEIGHT
        elif state == "toast":
            w = TOAST_WIDTH
            h = TOAST_HEIGHT
        elif state == "device_popup":
            w = 460
            h = 132
        else:  # expanded
            w = EXPANDED_WIDTH
            h = EXPANDED_HEIGHT

        x = int(screen_geo.x() + (screen_geo.width() - w) / 2)
        y = int(screen_geo.y())
        return x, y, w, h

    def _apply_geometry_for_state(self, state: str, animate=True):
        x, y, w, h = self._get_target_rect(state)

        if not animate:
            self.setGeometry(x, y, w, h)
            self._update_child_visibility(state)
            return

        if self._geo_animation and self._geo_animation.state() == QPropertyAnimation.State.Running:
            self._geo_animation.stop()

        self._geo_animation = QPropertyAnimation(self, b"geometry")

        if state in ("expanded", "device_popup"):
            self._geo_animation.setDuration(320)
            self._geo_animation.setEasingCurve(QEasingCurve.Type.OutBack)
        else:
            self._geo_animation.setDuration(260)
            self._geo_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._geo_animation.setStartValue(self.geometry())
        self._geo_animation.setEndValue(QRectF(x, y, w, h).toRect())
        self._geo_animation.finished.connect(lambda: self._update_child_visibility(state))
        self._geo_animation.start()

    def _update_child_visibility(self, state: str):
        if state == "expanded":
            self.dashboard_container.show()
            self.dashboard_container.raise_()
        else:
            self.dashboard_container.hide()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.dashboard_container.setGeometry(
            int(NOTCH_RADIUS_TOP + 4), 6,
            max(10, self.width() - int(2 * NOTCH_RADIUS_TOP + 8)),
            max(10, self.height() - 12)
        )

    def changeEvent(self, event):
        if event.type() == QEvent.Type.ActivationChange:
            if not self.isActiveWindow() and self._island_state == "expanded":
                self.collapse_to_compact()
        super().changeEvent(event)

    # -------------------------------------------------------------
    # Hover-to-Expand & Retract Logic
    # -------------------------------------------------------------
    def enterEvent(self, event):
        if self._is_fullscreen_suppressed:
            return
        self._hovered = True
        self._hover_collapse_timer.stop()
        if self._island_state == "device_popup":
            self._device_dismiss_timer.stop()
        elif self._island_state == "compact":
            self._hover_expand_timer.start(100)
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self._device_close_hovered = False
        self._device_done_hovered = False
        self._hover_expand_timer.stop()
        if self._island_state == "device_popup":
            self._device_dismiss_timer.start(2500)
        elif self._island_state == "expanded":
            self._hover_collapse_timer.start(450)
        self.update()
        super().leaveEvent(event)

    def _on_hover_expand_triggered(self):
        if self._hovered and self._island_state == "compact":
            self.set_island_state("expanded")

    def _on_hover_collapse_triggered(self):
        if not self._hovered and self._island_state == "expanded":
            self.set_island_state("compact")
            # If no music is actively playing, completely hide!
            if not self._is_music_active():
                self.hide()

    # -------------------------------------------------------------
    # State Management & Auto-Hide
    # -------------------------------------------------------------
    def set_island_state(self, state: str):
        if self._island_state == state:
            return
        old_state = self._island_state
        self._island_state = state

        if old_state == "toast" and state != "toast":
            self._toast_dismiss_timer.stop()
        if old_state == "device_popup" and state != "device_popup":
            self._device_dismiss_timer.stop()

        if state == "compact":
            self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        else:
            self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))

        self._apply_geometry_for_state(state, animate=True)
        self._evaluate_glow_state()
        self.state_changed.emit(state)

    def toggle_expanded(self):
        if self._is_fullscreen_suppressed:
            return
        if self._island_state == "expanded":
            self.set_island_state("compact")
            if not self._is_music_active():
                self.hide()
        else:
            if not self.isVisible():
                self.show()
                self.raise_()
            self.set_island_state("expanded")

    def collapse_to_compact(self):
        self._hover_collapse_timer.stop()
        self._device_dismiss_timer.stop()
        if self._island_state != "compact":
            self.set_island_state("compact")
        if not self._is_music_active():
            self.hide()

    def trigger_toast(self, app: str, title: str, message: str):
        """
        Pops up the notch immediately on incoming notification toast,
        unless currently suppressed by a full-screen game or video!
        """
        if self._is_fullscreen_suppressed:
            return
        self._toast_info = {
            "app": app,
            "title": title,
            "message": message,
            "time": time.time()
        }
        self.set_glow_state("notification")
        if not self.isVisible():
            self.show()
            self.raise_()
        self.set_island_state("toast")
        self._toast_dismiss_timer.start(4000)

    def _on_toast_timeout(self):
        if self._island_state == "toast":
            self.set_island_state("compact")
            # If there is no music actively playing, re-hide completely!
            if not self._is_music_active():
                self.hide()

    def set_glow_state(self, glow_name: str, duration_sec: Optional[float] = None):
        if glow_name not in GLOW_STATES:
            glow_name = "idle"

        self._glow_state = glow_name
        cfg = GLOW_STATES[glow_name]
        self._target_glow_c1 = QColor(cfg["color1"])
        self._target_glow_c2 = QColor(cfg["color2"])
        self._target_glow_opacity = cfg["opacity"]

        if duration_sec and duration_sec > 0:
            self._flash_timer.start(int(duration_sec * 1000))

    def _on_flash_timeout(self):
        self._flash_message = None
        self._evaluate_glow_state()

    def _evaluate_glow_state(self):
        if self._flash_timer.isActive():
            return
        if self._island_state == "toast":
            self.set_glow_state("notification")
        elif self._media_info.get("is_playing", False):
            self.set_glow_state("music")
        elif self._island_state == "expanded":
            self.set_glow_state("reminders")
        else:
            self.set_glow_state("idle")

    # -------------------------------------------------------------
    # Frosted Glass Album Art Generator
    # -------------------------------------------------------------
    def _update_album_art(self, art_path: Optional[str]):
        if not art_path or not os.path.exists(art_path):
            if self._album_art_pixmap is not None or self._glass_bg_pixmap is not None:
                self._album_art_pixmap = None
                self._glass_bg_pixmap = None
                self._current_art_path = None
                self.lbl_cover_art.hide()
                self.update()
            return

        if art_path == self._current_art_path and self._album_art_pixmap is not None:
            return

        self._current_art_path = art_path
        try:
            pix = QPixmap(art_path)
            if not pix.isNull():
                self._album_art_pixmap = pix
                self.lbl_cover_art.setPixmap(pix.scaled(
                    48, 48,
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation
                ))
                self.lbl_cover_art.show()

            im = Image.open(art_path)
            w = max(440, EXPANDED_WIDTH)
            h = max(200, EXPANDED_HEIGHT)
            bg = im.resize((w, h), Image.Resampling.BILINEAR)
            blurred = bg.filter(ImageFilter.GaussianBlur(radius=24))
            darkened = ImageEnhance.Brightness(blurred).enhance(0.40)
            rgba = darkened.convert("RGBA")
            qimg = QImage(
                rgba.tobytes("raw", "RGBA"),
                rgba.width,
                rgba.height,
                QImage.Format.Format_RGBA8888
            ).copy()
            self._glass_bg_pixmap = QPixmap.fromImage(qimg)
            self.update()
        except Exception:
            pass

    # -------------------------------------------------------------
    # Curvy Dashboard UI
    # -------------------------------------------------------------
    def _init_dashboard_ui(self):
        self.dashboard_container = QWidget(self)
        self.dashboard_container.hide()

        main_layout = QVBoxLayout(self.dashboard_container)
        main_layout.setContentsMargins(6, 4, 6, 6)
        main_layout.setSpacing(6)

        # 1. Clean Top Bar
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(4, 0, 4, 0)

        self.lbl_exp_clock = QLabel(self._time_str, self.dashboard_container)
        self.lbl_exp_clock.setFont(get_display_font(12))
        self.lbl_exp_clock.setStyleSheet("color: #FFFFFF; letter-spacing: 0.5px;")

        self.lbl_exp_battery = QLabel("🔋 99%", self.dashboard_container)
        self.lbl_exp_battery.setFont(get_microlabel_font())
        self.lbl_exp_battery.setStyleSheet("color: #38EF7D;")

        top_bar.addWidget(self.lbl_exp_clock)
        top_bar.addStretch()
        top_bar.addWidget(self.lbl_exp_battery)

        main_layout.addLayout(top_bar)

        # 2. Main Media Card
        self.card_media = QFrame(self.dashboard_container)
        self.card_media.setStyleSheet("""
            QFrame {
                background: rgba(14, 14, 20, 0.65);
                border: 1px solid rgba(255, 255, 255, 0.10);
                border-radius: 18px;
            }
        """)
        media_card_layout = QVBoxLayout(self.card_media)
        media_card_layout.setContentsMargins(12, 8, 12, 8)
        media_card_layout.setSpacing(6)

        # Track Row
        track_row = QHBoxLayout()
        track_row.setSpacing(10)

        self.lbl_cover_art = QLabel(self.card_media)
        self.lbl_cover_art.setFixedSize(46, 46)
        self.lbl_cover_art.setStyleSheet("""
            QLabel {
                border-radius: 12px;
                background-color: rgba(255, 255, 255, 0.06);
                border: 1px solid rgba(255, 255, 255, 0.15);
            }
        """)
        self.lbl_cover_art.setScaledContents(True)
        track_row.addWidget(self.lbl_cover_art)

        track_info_box = QVBoxLayout()
        track_info_box.setSpacing(2)

        self.lbl_exp_title = QLabel("", self.card_media)
        self.lbl_exp_title.setFont(get_display_font(13))
        self.lbl_exp_title.setStyleSheet("color: #FFFFFF; border: none; background: transparent;")

        self.lbl_exp_artist = QLabel("", self.card_media)
        self.lbl_exp_artist.setFont(get_subtext_font(11))
        self.lbl_exp_artist.setStyleSheet("color: #A0A0AB; border: none; background: transparent;")

        track_info_box.addWidget(self.lbl_exp_title)
        track_info_box.addWidget(self.lbl_exp_artist)
        track_row.addLayout(track_info_box, 1)

        media_card_layout.addLayout(track_row)

        # 26-Bar Equalizer
        self.visualizer = AudioVisualizerWidget(num_bars=26, bar_width=3, bar_spacing=3, parent=self.card_media)
        self.visualizer.setFixedHeight(28)
        media_card_layout.addWidget(self.visualizer, alignment=Qt.AlignmentFlag.AlignCenter)

        # Progress Row
        prog_row = QHBoxLayout()
        prog_row.setSpacing(8)

        self.lbl_time_pos = QLabel("00:00", self.card_media)
        self.lbl_time_pos.setFont(get_microlabel_font())
        self.lbl_time_pos.setStyleSheet("color: #A0A0AB; border: none; background: transparent;")

        self.prog_bar = QProgressBar(self.card_media)
        self.prog_bar.setFixedHeight(3)
        self.prog_bar.setTextVisible(False)
        self.prog_bar.setRange(0, 100)
        self.prog_bar.setValue(0)
        self.prog_bar.setStyleSheet("""
            QProgressBar {
                background: rgba(255, 255, 255, 0.12);
                border: none;
                border-radius: 1px;
            }
            QProgressBar::chunk {
                background: #FFD600;
                border-radius: 1px;
            }
        """)

        self.lbl_time_dur = QLabel("00:00", self.card_media)
        self.lbl_time_dur.setFont(get_microlabel_font())
        self.lbl_time_dur.setStyleSheet("color: #A0A0AB; border: none; background: transparent;")

        prog_row.addWidget(self.lbl_time_pos)
        prog_row.addWidget(self.prog_bar, 1)
        prog_row.addWidget(self.lbl_time_dur)
        media_card_layout.addLayout(prog_row)

        # Vector Playback Controls
        controls_layout = QHBoxLayout()
        controls_layout.setSpacing(12)
        controls_layout.addStretch()

        self.btn_prev = VectorMediaButton(mode="prev", is_primary=False, parent=self.card_media)
        self.btn_prev.clicked.connect(self.media_service.previous_track)

        self.btn_play = VectorMediaButton(mode="play", is_primary=True, parent=self.card_media)
        self.btn_play.clicked.connect(self.media_service.toggle_play_pause)

        self.btn_next = VectorMediaButton(mode="next", is_primary=False, parent=self.card_media)
        self.btn_next.clicked.connect(self.media_service.next_track)

        controls_layout.addWidget(self.btn_prev)
        controls_layout.addWidget(self.btn_play)
        controls_layout.addWidget(self.btn_next)
        controls_layout.addStretch()
        media_card_layout.addLayout(controls_layout)

        main_layout.addWidget(self.card_media)

    # -------------------------------------------------------------
    # Signal Connections & Auto-Hide on No Music
    # -------------------------------------------------------------
    def _connect_signals(self):
        self.media_service.media_updated.connect(self._on_media_updated)
        self.system_service.time_tick.connect(self._on_time_tick)
        self.system_service.battery_tick.connect(self._on_battery_tick)
        self.system_service.volume_changed.connect(self._on_volume_changed)
        self.system_service.screenshot_taken.connect(self._on_screenshot_taken)
        self.system_service.dnd_changed.connect(self._on_dnd_changed)
        self.system_service.notification_received.connect(self._on_notification_received)
        self.system_service.status_alert.connect(self._on_status_alert)
        if hasattr(self, "device_service") and self.device_service:
            self.device_service.device_connected.connect(self._on_device_connected)

    def _on_battery_tick(self, info: dict):
        self._battery_info = info
        pct = info.get("percent", 99)
        plugged = info.get("is_plugged", False)
        icon = "🗲" if plugged else "🔋"
        self.lbl_exp_battery.setText(f"{icon} {pct}%")
        self.update()

    def _on_media_updated(self, info: dict):
        prev_has_media = self._media_info.get("has_media", False)
        self._media_info = info
        is_playing = info.get("is_playing", False)
        has_media = info.get("has_media", False)
        title = info.get("title", "")
        artist = info.get("artist", "")
        pos = info.get("position", 0)
        dur = info.get("duration", 210) or 210

        self.visualizer.set_playing(is_playing)
        self.lbl_exp_title.setText(title)
        self.lbl_exp_artist.setText(artist)
        self.btn_play.set_mode("pause" if is_playing else "play")

        pct = int((pos / dur) * 100) if dur > 0 else 0
        self.prog_bar.setValue(min(100, max(0, pct)))
        self.lbl_time_pos.setText(format_seconds(pos))
        self.lbl_time_dur.setText(format_seconds(dur))

        # Update Frosted Glass Album Cover
        art_path = info.get("album_art_path")
        self._update_album_art(art_path)

        # Dynamic Visibility & Sizing: Completely hide when there is no music or in full screen
        if self._is_fullscreen_suppressed:
            if self.isVisible():
                self.hide()
            return

        music_active = self._is_music_active()
        if music_active:
            self._music_idle_timer.stop()
            if not self.isVisible():
                self.show()
                self.raise_()
            if self._island_state == "compact" and not prev_has_media:
                self._apply_geometry_for_state("compact", animate=True)
        else:
            # Music paused or ended: smoothly hide if in compact mode
            if self._island_state == "compact":
                if self.isVisible() and not self._music_idle_timer.isActive():
                    self._music_idle_timer.start()

        self._ticker_offset = 0.0
        self._evaluate_glow_state()
        self.update()

    def _on_time_tick(self, time_str: str, date_str: str):
        self._time_str = time_str
        self._date_str = date_str
        self.lbl_exp_clock.setText(time_str)
        self.update()

    def _on_volume_changed(self, is_muted: bool, level: float):
        state_name = "Muted" if is_muted else f"Vol {int(level * 100)}%"
        self._flash_message = f"{state_name}"
        self.set_glow_state("notification", duration_sec=2.0)
        self.update()

    def _on_screenshot_requested(self):
        self.system_service.take_screenshot()

    def _on_screenshot_taken(self, filepath: str):
        self._flash_message = "SAVED!"
        self.set_glow_state("success", duration_sec=3.0)
        self.trigger_toast("Screen Capture", "Screenshot Saved!", "Copied to clipboard")
        self.update()

    def _on_dnd_changed(self, is_dnd: bool):
        self._flash_message = "DND: ON" if is_dnd else "DND: OFF"
        self.set_glow_state("reminders", duration_sec=2.0)
        self.update()

    def _on_notification_received(self, notif: dict):
        if not self.system_service.is_dnd:
            if self._island_state == "device_popup":
                return
            self.trigger_toast(
                app=notif.get("app", "Alert"),
                title=notif.get("title", "Incoming Alert"),
                message=notif.get("message", "")
            )

    def _on_status_alert(self, category: str, message: str):
        self._flash_message = message.upper()
        if category == "success":
            self.set_glow_state("success", duration_sec=2.5)
        else:
            self.set_glow_state("notification", duration_sec=2.0)
        self.update()

    def _on_device_connected(self, data: dict):
        """Triggered when an external audio device connects."""
        self.trigger_device_popup(data)

    def trigger_device_popup(self, data: dict):
        """Pops up and expands the Dynamic Island into the Apple device accessory card."""
        if self._is_fullscreen_suppressed:
            return
        self._device_info = data
        self.set_glow_state("notification", duration_sec=4.5)
        if not self.isVisible():
            self.show()
            self.raise_()
        self.set_island_state("device_popup")
        self._device_dismiss_timer.start(4500)

    # -------------------------------------------------------------
    # 60 FPS Render Tick
    # -------------------------------------------------------------
    def _on_render_tick(self):
        if not self.isVisible():
            return

        self._gradient_shift += 0.025

        lerp_factor = 0.14
        r = self._current_glow_c1.red() + (self._target_glow_c1.red() - self._current_glow_c1.red()) * lerp_factor
        g = self._current_glow_c1.green() + (self._target_glow_c1.green() - self._current_glow_c1.green()) * lerp_factor
        b = self._current_glow_c1.blue() + (self._target_glow_c1.blue() - self._current_glow_c1.blue()) * lerp_factor
        self._current_glow_c1 = QColor(int(r), int(g), int(b))

        r2 = self._current_glow_c2.red() + (self._target_glow_c2.red() - self._current_glow_c2.red()) * lerp_factor
        g2 = self._current_glow_c2.green() + (self._target_glow_c2.green() - self._current_glow_c2.green()) * lerp_factor
        b2 = self._current_glow_c2.blue() + (self._target_glow_c2.blue() - self._current_glow_c2.blue()) * lerp_factor
        self._current_glow_c2 = QColor(int(r2), int(g2), int(b2))

        self._current_glow_opacity += (self._target_glow_opacity - self._current_glow_opacity) * lerp_factor

        if self._island_state == "compact" and self._media_info.get("is_playing", False):
            self._mini_eq_phase += 0.18
            self._mini_eq_heights[0] = 0.2 + 0.7 * abs(math.sin(self._mini_eq_phase))
            self._mini_eq_heights[1] = 0.3 + 0.65 * abs(math.sin(self._mini_eq_phase * 1.3 + 1.0))
            self._mini_eq_heights[2] = 0.25 + 0.75 * abs(math.cos(self._mini_eq_phase * 0.9 + 2.0))
            self._mini_eq_heights[3] = 0.2 + 0.6 * abs(math.sin(self._mini_eq_phase * 1.5 + 0.5))

        self.update()

    def _on_ticker_tick(self):
        if not self.isVisible():
            return
        if self._island_state == "compact" and self._media_info.get("has_media", False):
            self._ticker_offset += 1.2
            self.update()

    # -------------------------------------------------------------
    # Mouse Interaction
    # -------------------------------------------------------------
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._island_state == "device_popup":
                self.collapse_to_compact()
                return
            elif self._island_state in ("compact", "toast"):
                self.set_island_state("expanded")
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._island_state == "device_popup":
            pos = event.position()
            old_d = getattr(self, "_device_done_hovered", False)
            if hasattr(self, "_device_done_rect"):
                self._device_done_hovered = self._device_done_rect.contains(pos)
            else:
                self._device_done_hovered = False

            if old_d != self._device_done_hovered:
                self.update()
            if self._device_done_hovered:
                self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            else:
                self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
        super().mouseMoveEvent(event)

    # -------------------------------------------------------------
    # Organic Curvy Hardware Notch Path Generator
    # -------------------------------------------------------------
    def _create_notch_path(self, w: float, h: float) -> QPainterPath:
        r_top = NOTCH_RADIUS_TOP
        r_bot = NOTCH_RADIUS_BOT if self._island_state == "compact" else EXPANDED_RADIUS

        path = QPainterPath()
        path.moveTo(0, 0)
        path.cubicTo(r_top * 0.4, 0, r_top, r_top * 0.4, r_top, r_top)
        path.lineTo(r_top, h - r_bot)
        path.quadTo(r_top, h, r_top + r_bot, h)
        path.lineTo(w - r_top - r_bot, h)
        path.quadTo(w - r_top, h, w - r_top, h - r_bot)
        path.lineTo(w - r_top, r_top)
        path.cubicTo(w - r_top, r_top * 0.4, w - r_top * 0.4, 0, w, 0)
        path.lineTo(0, 0)
        path.closeSubpath()
        return path

    def paintEvent(self, event):
        painter = QPainter(self)
        # Maximum quality rendering hints for smooth text and graphics
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        w = float(self.width())
        h = float(self.height())
        has_media = bool(self._media_info.get("has_media", False))

        notch_path = self._create_notch_path(w, h)

        # 1. Soft shadow along bottom and sides
        shadow_steps = 4
        for i in range(1, shadow_steps + 1):
            alpha = int(32 * ((shadow_steps - i + 1) / shadow_steps) ** 1.8)
            painter.setPen(QPen(QColor(0, 0, 0, alpha), i * 1.5))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(notch_path)

        # 2. Clip inside notch
        painter.save()
        painter.setClipPath(notch_path)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        # 3. Canvas Surface Fill (True Liquid Obsidian Glass)
        if has_media and self._glass_bg_pixmap and not self._glass_bg_pixmap.isNull() and self._island_state != "device_popup":
            painter.drawPixmap(0, 0, int(w), int(h), self._glass_bg_pixmap)

            scrim = QLinearGradient(0, 0, 0, h)
            scrim.setColorAt(0.0, QColor(16, 18, 28, 130))
            scrim.setColorAt(0.5, QColor(10, 11, 18, 168))
            scrim.setColorAt(1.0, QColor(6, 7, 10, 205))
            painter.fillRect(0, 0, int(w), int(h), scrim)
        else:
            canvas_grad = QLinearGradient(0, 0, 0, h)
            canvas_grad.setColorAt(0.0, QColor(24, 26, 38, 238))
            canvas_grad.setColorAt(0.35, QColor(14, 15, 23, 248))
            canvas_grad.setColorAt(0.75, QColor(9, 10, 15, 252))
            canvas_grad.setColorAt(1.0, QColor(5, 5, 8, 255))
            painter.fillRect(0, 0, int(w), int(h), canvas_grad)

        # 4. Liquid Glass Sheen & Top Meniscus
        sheen_grad = QLinearGradient(0, 0, w * 0.55, h * 0.85)
        sheen_grad.setColorAt(0.0, QColor(255, 255, 255, 28))
        sheen_grad.setColorAt(0.35, QColor(255, 255, 255, 10))
        sheen_grad.setColorAt(0.70, QColor(255, 255, 255, 0))
        painter.fillRect(QRectF(0, 0, w, h), sheen_grad)

        # Top specular meniscus along curved top rim
        r_top = NOTCH_RADIUS_TOP
        meniscus_grad = QLinearGradient(0, 0, w, 0)
        meniscus_grad.setColorAt(0.0, QColor(255, 255, 255, 0))
        meniscus_grad.setColorAt(r_top / w, QColor(255, 255, 255, 45))
        meniscus_grad.setColorAt(0.5, QColor(255, 255, 255, 130 if self._hovered else 85))
        meniscus_grad.setColorAt((w - r_top) / w, QColor(255, 255, 255, 45))
        meniscus_grad.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.setPen(QPen(QBrush(meniscus_grad), 1.5))
        painter.drawLine(QPointF(0, 0.75), QPointF(w, 0.75))

        # 5. Animated Moving Gradient Effect (Dual-Vortex Liquid Aurora)
        self._paint_moving_gradient(painter, w, h)

        # 6. State-Specific Content
        if self._island_state == "compact":
            self._paint_compact_notch(painter, w, h)
        elif self._island_state == "toast":
            self._paint_toast_notch(painter, w, h)
        elif self._island_state == "device_popup":
            self._paint_device_popup_notch(painter, w, h)

        painter.restore()

        # 7. Hardware Bezel Stroke
        bezel_pen = QPen(COLOR_BEZEL, 2.0)
        painter.setPen(bezel_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(notch_path)

        # 8. Subtle Milled Edge Inner Highlight
        highlight_alpha = 28 if self._hovered else 16
        painter.setPen(QPen(QColor(255, 255, 255, highlight_alpha), 1.0))
        painter.drawPath(notch_path)

    def _paint_moving_gradient(self, painter: QPainter, w: float, h: float):
        t = self._gradient_shift

        # Vortex 1: Primary dynamic glow (amber gold / cyan / emerald)
        cx1 = w * 0.5 + math.cos(t * 0.75) * (w * 0.35)
        cy1 = h * 0.45 + math.sin(t * 0.55) * (h * 0.32)
        r1 = max(w, h) * 0.88
        grad1 = QRadialGradient(QPointF(cx1, cy1), r1)

        c1 = QColor(self._current_glow_c1)
        c1.setAlphaF(min(1.0, self._current_glow_opacity * 0.90))

        c2 = QColor(self._current_glow_c2)
        c2.setAlphaF(min(1.0, self._current_glow_opacity * 0.45))

        grad1.setColorAt(0.0, c1)
        grad1.setColorAt(0.42, c2)
        grad1.setColorAt(1.0, QColor(0, 0, 0, 0))

        # Vortex 2: Fluid Chromatic Dispersion (iridescent liquid sheen)
        cx2 = w * 0.5 - math.sin(t * 0.90) * (w * 0.30)
        cy2 = h * 0.55 - math.cos(t * 0.70) * (h * 0.28)
        r2 = max(w, h) * 0.72
        grad2 = QRadialGradient(QPointF(cx2, cy2), r2)

        prism_r = int(120 + 75 * math.sin(t * 0.6))
        prism_g = int(80 + 70 * math.cos(t * 0.8))
        prism_b = int(215 + 40 * math.sin(t * 0.5))
        c_prism = QColor(prism_r, prism_g, prism_b, 50)

        grad2.setColorAt(0.0, c_prism)
        grad2.setColorAt(0.50, QColor(prism_r, prism_g, prism_b, 16))
        grad2.setColorAt(1.0, QColor(0, 0, 0, 0))

        painter.save()
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(grad1))
        painter.drawRect(QRectF(0, 0, w, h))
        painter.setBrush(QBrush(grad2))
        painter.drawRect(QRectF(0, 0, w, h))
        painter.restore()

    def _paint_compact_notch(self, painter: QPainter, w: float, h: float):
        """
        Renders the compact curvy notch with smooth subpixel text.
        """
        is_playing = self._media_info.get("is_playing", False)
        r_top = NOTCH_RADIUS_TOP

        content_left = r_top + 12.0
        content_right = w - r_top - 12.0

        # ── Left: Time ───────────────────────────────────────────
        time_parts = self._time_str.split(" ")
        hhmm = time_parts[0]
        ampm = time_parts[1] if len(time_parts) > 1 else ""

        # Draw HH:MM using QRectF for subpixel-accurate vertical centering
        time_font = get_display_font(11)
        painter.setFont(time_font)
        painter.setPen(COLOR_TEXT_PRIMARY)
        fm_time = QFontMetrics(time_font)
        tw = fm_time.horizontalAdvance(hhmm)

        # Vertically centered rect for the time text
        text_h = fm_time.height()
        time_rect = QRectF(content_left, (h - text_h) / 2.0, tw + 2.0, text_h)
        painter.drawText(time_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, hhmm)

        # Draw AM/PM suffix
        ampm_font = get_microlabel_font()
        painter.setFont(ampm_font)
        painter.setPen(COLOR_TEXT_MUTED)
        fm_ampm = QFontMetrics(ampm_font)
        ampm_w = fm_ampm.horizontalAdvance(ampm)
        ampm_rect = QRectF(content_left + tw + 2.0, (h - fm_ampm.height()) / 2.0, ampm_w + 2.0, fm_ampm.height())
        painter.drawText(ampm_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, ampm)

        # ── Separator ────────────────────────────────────────────
        sep_x = content_left + tw + ampm_w + 10.0
        painter.setPen(QPen(QColor(255, 255, 255, 24), 1.0))
        painter.drawLine(QPointF(sep_x, 7.0), QPointF(sep_x, h - 7.0))

        # ── Album Art Squircle (24×24) ───────────────────────────
        art_size = 24.0
        art_x = sep_x + 8.0
        art_y = (h - art_size) / 2.0
        art_rect = QRectF(art_x, art_y, art_size, art_size)

        painter.save()
        art_path = QPainterPath()
        art_path.addRoundedRect(art_rect, 7.0, 7.0)
        painter.setClipPath(art_path)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        if self._album_art_pixmap and not self._album_art_pixmap.isNull():
            painter.drawPixmap(art_rect.toRect(), self._album_art_pixmap.scaled(
                int(art_size), int(art_size),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation
            ))
        else:
            painter.fillRect(art_rect, QColor(30, 30, 40))

        painter.restore()

        painter.setPen(QPen(QColor(255, 255, 255, 30), 1.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(art_rect, 7.0, 7.0)

        # ── Mini 4-Bar Equalizer (far right) ─────────────────────
        eq_w = 18.0
        eq_x = content_right - eq_w
        eq_cy = h / 2.0
        bar_w = 2.2
        bar_gap = 2.0
        for idx in range(4):
            bx = eq_x + idx * (bar_w + bar_gap)
            bh = max(2.5, self._mini_eq_heights[idx] * 14.0) if is_playing else 2.5
            by = eq_cy - bh / 2.0
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(COLOR_ACCENT_YELLOW if is_playing else QColor(255, 255, 255, 45))
            painter.drawRoundedRect(QRectF(bx, by, bar_w, bh), 1.0, 1.0)

        # ── Center: Track title + artist (smooth scrolling) ──────
        text_x = art_x + art_size + 8.0
        text_avail_w = eq_x - text_x - 8.0
        clip_rect = QRectF(text_x, 0.0, text_avail_w, h)

        painter.save()
        painter.setClipRect(clip_rect)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        title = self._media_info.get("title", "")
        artist = self._media_info.get("artist", "")
        title_text = f"{title}  —  {artist}" if artist else title

        track_font = get_display_font(10)
        painter.setFont(track_font)
        fm_title = QFontMetrics(track_font)
        tw = fm_title.horizontalAdvance(title_text)
        track_h = fm_title.height()

        # Vertically centered row for track text
        text_top = (h - track_h) / 2.0

        if tw > text_avail_w:
            # Smooth float-coord scrolling — no integer snapping jitter
            scroll_cycle = tw + 44.0
            x1 = text_x - (self._ticker_offset % scroll_cycle)
            x2 = x1 + scroll_cycle
            painter.setPen(COLOR_TEXT_PRIMARY)
            r1 = QRectF(x1, text_top, tw + 4.0, track_h)
            r2 = QRectF(x2, text_top, tw + 4.0, track_h)
            painter.drawText(r1, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, title_text)
            painter.drawText(r2, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, title_text)
        else:
            painter.setPen(COLOR_TEXT_PRIMARY)
            r = QRectF(text_x, text_top, text_avail_w, track_h)
            painter.drawText(r, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, title_text)

        painter.restore()

    def _paint_toast_notch(self, painter: QPainter, w: float, h: float):
        """
        Redesigned liquid glass notification toast with frosted squircle app badge,
        categorized glowing glyphs, crisp typography, and dismissal controls.
        """
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        r_top = NOTCH_RADIUS_TOP
        app_name = (self._toast_info.get("app") or "NOTIFICATION").upper()
        title    = self._toast_info.get("title") or "Incoming Alert"
        message  = self._toast_info.get("message") or ""

        # Dynamic category iconography & palette
        app_lower = app_name.lower()
        if any(k in app_lower for k in ("message", "chat", "slack", "teams", "whatsapp", "telegram", "discord")):
            icon_char = "💬"
            accent_col = QColor("#56CCF2")
        elif any(k in app_lower for k in ("mail", "outlook", "gmail", "thunderbird")):
            icon_char = "✉️"
            accent_col = QColor("#4A90E2")
        elif any(k in app_lower for k in ("calendar", "meeting", "reminder", "alarm", "clock")):
            icon_char = "📅"
            accent_col = QColor("#B388FF")
        elif any(k in app_lower for k in ("music", "spotify", "apple music", "ytmusic")):
            icon_char = "🎵"
            accent_col = QColor("#FFD600")
        else:
            icon_char = "🔔"
            accent_col = QColor("#56CCF2")

        # ── 1. Frosted Glass App Icon Badge ─────────────────────────
        badge_size = 42.0
        badge_x = r_top + 10.0
        badge_y = (h - badge_size) / 2.0
        badge_rect = QRectF(badge_x, badge_y, badge_size, badge_size)

        # Soft ambient aura behind badge
        badge_glow = QRadialGradient(QPointF(badge_x + badge_size * 0.5, badge_y + badge_size * 0.5), badge_size * 0.75)
        glow_c = QColor(accent_col)
        glow_c.setAlpha(45)
        badge_glow.setColorAt(0.0, glow_c)
        badge_glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(badge_glow))
        painter.drawEllipse(QRectF(badge_x - 6.0, badge_y - 6.0, badge_size + 12.0, badge_size + 12.0))

        # Badge glass container
        badge_grad = QLinearGradient(badge_x, badge_y, badge_x, badge_y + badge_size)
        badge_grad.setColorAt(0.0, QColor(255, 255, 255, 28))
        badge_grad.setColorAt(1.0, QColor(255, 255, 255, 12))
        painter.setPen(QPen(QColor(255, 255, 255, 48), 1.0))
        painter.setBrush(QBrush(badge_grad))
        painter.drawRoundedRect(badge_rect, 12.0, 12.0)

        # Badge icon
        icon_font = get_display_font(15)
        painter.setFont(icon_font)
        painter.setPen(accent_col)
        painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, icon_char)

        # Tiny glowing badge indicator dot
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(accent_col))
        painter.drawEllipse(QRectF(badge_x + badge_size - 7.0, badge_y + 3.0, 5.0, 5.0))

        # ── 2. Information Column ───────────────────────────────────
        text_x = badge_x + badge_size + 13.0
        btn_w = 26.0
        text_w = w - text_x - btn_w - 18.0

        # Row 1: App Name & "now" timestamp
        label_font = get_microlabel_font()
        painter.setFont(label_font)
        painter.setPen(accent_col)
        painter.drawText(QRectF(text_x, badge_y + 1.0, text_w - 52.0, 14.0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, app_name)

        time_font = get_microlabel_font()
        painter.setFont(time_font)
        painter.setPen(QColor(255, 255, 255, 125))
        painter.drawText(QRectF(text_x + text_w - 50.0, badge_y + 1.0, 50.0, 14.0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, "now")

        # Row 2: Title (Bold crisp white)
        title_font = get_display_font(11)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.setPen(COLOR_TEXT_PRIMARY)
        fm_title = painter.fontMetrics()
        elided_title = fm_title.elidedText(title, Qt.TextElideMode.ElideRight, int(text_w))
        painter.drawText(QRectF(text_x, badge_y + 15.0, text_w, 17.0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, elided_title)

        # Row 3: Message Body (Smooth elided secondary text)
        body_font = get_subtext_font(10)
        painter.setFont(body_font)
        painter.setPen(COLOR_TEXT_SECONDARY)
        fm_body = painter.fontMetrics()
        elided_body = fm_body.elidedText(message, Qt.TextElideMode.ElideRight, int(text_w))
        painter.drawText(QRectF(text_x, badge_y + 31.0, text_w, 15.0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, elided_body)

        # ── 3. Frosted Dismiss Button ───────────────────────────────
        close_x = w - r_top - 20.0
        close_y = (h - 22.0) / 2.0
        close_rect = QRectF(close_x, close_y, 22.0, 22.0)
        self._toast_close_rect = close_rect

        painter.setPen(QPen(QColor(255, 255, 255, 28), 1.0))
        painter.setBrush(QBrush(QColor(255, 255, 255, 14)))
        painter.drawEllipse(close_rect)

        painter.setFont(get_display_font(9))
        painter.setPen(QColor(255, 255, 255, 170))
        painter.drawText(close_rect, Qt.AlignmentFlag.AlignCenter, "✕")

    def _paint_device_popup_notch(self, painter: QPainter, w: float, h: float):
        """
        Draws the sleek dark liquid glassy Dynamic Island accessory showcase.
        Features a prominent, floating 3D device render, ambient aura, soft contact
        shadow, live 12-bar audio equalizer waveform, and frosted glass Done button.
        """
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        cat = self._device_info.get("category", "airpods")
        title = self._device_info.get("display_title") or self._device_info.get("name") or "Audio Device"
        subtitle = self._device_info.get("display_subtitle") or "Connected  •  Audio Output Ready"

        r_top = NOTCH_RADIUS_TOP

        # Theme accent based on device category
        if cat == "airpods":
            cat_label = "● AIRPODS PRO"
            accent_col = QColor("#38EF7D")  # Green LED
            eq_col = QColor("#FFD600")
        elif cat == "headphones":
            cat_label = "● OVER-EAR HEADPHONES"
            accent_col = QColor("#56CCF2")  # Cyan rim light
            eq_col = QColor("#56CCF2")
        elif cat == "speaker":
            cat_label = "● BLUETOOTH SPEAKER"
            accent_col = QColor("#00D2FF")  # Cyan LED ring
            eq_col = QColor("#00D2FF")
        elif cat == "iem":
            cat_label = "● HI-FI IN-EAR MONITORS"
            accent_col = QColor("#B388FF")  # Sapphire / violet resin
            eq_col = QColor("#FFD600")
        else:
            cat_label = "● AUDIO ACCESSORY"
            accent_col = QColor("#38EF7D")
            eq_col = QColor("#FFD600")

        # ── 1. Top Bar: Clock & Battery ──────────────────────────────
        time_font = get_display_font(11)
        painter.setFont(time_font)
        painter.setPen(COLOR_TEXT_PRIMARY)
        painter.drawText(QRectF(r_top + 10.0, 4.0, 90.0, 18.0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self._time_str)

        batt_font = get_microlabel_font()
        painter.setFont(batt_font)
        painter.setPen(QColor("#38EF7D"))
        pct = self._battery_info.get("percent", 100)
        plugged = self._battery_info.get("is_plugged", False)
        icon = "⚡" if plugged else "🔋"
        painter.drawText(QRectF(w - r_top - 100.0, 4.0, 90.0, 18.0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, f"{icon} {pct}%")

        # ── 2. Inner Liquid Glass Card ───────────────────────────────
        card_x = 14.0
        card_y = 25.0
        card_w = w - 28.0
        card_h = h - 35.0
        card_rect = QRectF(card_x, card_y, card_w, card_h)

        # Inner card base fill & dual-tone specular border
        card_grad = QLinearGradient(card_x, card_y, card_x, card_y + card_h)
        card_grad.setColorAt(0.0, QColor(22, 24, 36, 195))
        card_grad.setColorAt(1.0, QColor(12, 13, 20, 215))

        painter.setPen(QPen(QColor(255, 255, 255, 36), 1.0))
        painter.setBrush(QBrush(card_grad))
        painter.drawRoundedRect(card_rect, 18.0, 18.0)

        # Inner card top specular highlight line
        inner_meniscus = QLinearGradient(card_x, card_y, card_x + card_w, card_y)
        inner_meniscus.setColorAt(0.0, QColor(255, 255, 255, 0))
        inner_meniscus.setColorAt(0.2, QColor(255, 255, 255, 45))
        inner_meniscus.setColorAt(0.5, QColor(255, 255, 255, 80))
        inner_meniscus.setColorAt(0.8, QColor(255, 255, 255, 45))
        inner_meniscus.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.setPen(QPen(QBrush(inner_meniscus), 1.0))
        painter.drawLine(QPointF(card_x + 18.0, card_y + 0.5), QPointF(card_x + card_w - 18.0, card_y + 0.5))

        # ── 3. Floating 3D Device Art Showcase ───────────────────────
        dev_box_w = 92.0
        dev_cx = card_x + dev_box_w * 0.5
        dev_cy = card_y + card_h * 0.5
        art_size = 76.0

        # Ambient Aura Glow beneath floating 3D device
        pedestal_glow = QRadialGradient(QPointF(dev_cx, dev_cy + 8.0), 48.0)
        pedestal_c = QColor(accent_col)
        pedestal_c.setAlpha(55)
        pedestal_glow.setColorAt(0.0, pedestal_c)
        pedestal_glow.setColorAt(0.55, QColor(accent_col.red(), accent_col.green(), accent_col.blue(), 18))
        pedestal_glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(pedestal_glow))
        painter.drawEllipse(QRectF(dev_cx - 45.0, dev_cy - 28.0, 90.0, 72.0))

        # Soft 3D Contact Shadow
        shadow_grad = QRadialGradient(QPointF(dev_cx, dev_cy + 25.0), 30.0)
        shadow_grad.setColorAt(0.0, QColor(0, 0, 0, 140))
        shadow_grad.setColorAt(0.6, QColor(0, 0, 0, 45))
        shadow_grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setBrush(QBrush(shadow_grad))
        painter.drawEllipse(QRectF(dev_cx - 30.0, dev_cy + 20.0, 60.0, 11.0))

        # Render floating 3D Device
        pix = self._device_pixmaps.get(cat)
        if pix and not pix.isNull():
            smooth_pix = pix.scaled(
                int(art_size), int(art_size),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            ix = dev_cx - smooth_pix.width() / 2.0
            iy = dev_cy - smooth_pix.height() / 2.0 - 2.0  # Floating slightly above shadow
            painter.drawPixmap(int(ix), int(iy), smooth_pix)

        # ── 4. Device Information Column ─────────────────────────────
        text_x = card_x + dev_box_w + 8.0
        btn_w = 64.0
        btn_h = 32.0
        btn_x = card_x + card_w - btn_w - 14.0
        text_w = btn_x - text_x - 10.0

        # Row 1: Category Tag (e.g. ● AIRPODS PRO)
        cat_font = get_microlabel_font()
        painter.setFont(cat_font)
        painter.setPen(accent_col)
        painter.drawText(QRectF(text_x, card_y + 10.0, text_w, 14.0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, cat_label)

        # Row 2: Device Title (Large bold white)
        title_font = get_display_font(13)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.setPen(COLOR_TEXT_PRIMARY)
        fm_t = painter.fontMetrics()
        elided_title = fm_t.elidedText(title, Qt.TextElideMode.ElideRight, int(text_w))
        painter.drawText(QRectF(text_x, card_y + 25.0, text_w, 22.0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, elided_title)

        # Row 3: Subtitle
        sub_font = get_subtext_font(9.5)
        painter.setFont(sub_font)
        painter.setPen(QColor(255, 255, 255, 175))
        fm_s = painter.fontMetrics()
        elided_sub = fm_s.elidedText(subtitle, Qt.TextElideMode.ElideRight, int(text_w))
        painter.drawText(QRectF(text_x, card_y + 47.0, text_w, 16.0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, elided_sub)

        # Row 4: 12-Bar Live Waveform + Connected Badge
        wave_x = text_x
        wave_y = card_y + 68.0
        phase = getattr(self, "_mini_eq_phase", 0.0)
        for idx in range(12):
            bar_h = 3.5 + 13.0 * (math.sin(phase * 1.6 + idx * 0.52) ** 2)
            bx = wave_x + idx * 4.6
            by = wave_y + (16.0 - bar_h) / 2.0
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(eq_col))
            painter.drawRoundedRect(QRectF(bx, by, 2.4, bar_h), 1.2, 1.2)

        status_font = get_microlabel_font()
        painter.setFont(status_font)
        painter.setPen(QColor("#38EF7D"))
        painter.drawText(QRectF(wave_x + 12 * 4.6 + 8.0, wave_y, 85.0, 16.0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, "● READY")

        # ── 5. Frosted Glass "Done" Button ───────────────────────────
        btn_y = card_y + (card_h - btn_h) / 2.0
        self._device_done_rect = QRectF(btn_x, btn_y, btn_w, btn_h)

        is_hovered = getattr(self, "_device_done_hovered", False)
        btn_border_alpha = 90 if is_hovered else 45
        btn_bg_alpha = 48 if is_hovered else 24

        painter.setPen(QPen(QColor(255, 255, 255, btn_border_alpha), 1.2))
        painter.setBrush(QBrush(QColor(255, 255, 255, btn_bg_alpha)))
        painter.drawRoundedRect(self._device_done_rect, 16.0, 16.0)

        btn_font = get_display_font(11)
        btn_font.setBold(True)
        painter.setFont(btn_font)
        painter.setPen(QColor("#FFFFFF"))
        painter.drawText(self._device_done_rect, Qt.AlignmentFlag.AlignCenter, "Done")
