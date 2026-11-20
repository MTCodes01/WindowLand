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
    OSD_HUD_WIDTH, OSD_HUD_HEIGHT, OSD_HUD_R_TOP, OSD_HUD_R_BOT,
    CALL_LIVE_WIDTH, CALL_LIVE_HEIGHT, CALL_LIVE_R_TOP, CALL_LIVE_R_BOT,
    OTP_PILL_WIDTH, OTP_PILL_HEIGHT, OTP_PILL_R_TOP, OTP_PILL_R_BOT,
    FILE_SHELF_WIDTH, FILE_SHELF_HEIGHT, FILE_SHELF_R_TOP, FILE_SHELF_R_BOT,
    DEVICE_POPUP_WIDTH, DEVICE_POPUP_HEIGHT,
    NOTCH_RADIUS_TOP, NOTCH_RADIUS_BOT, EXPANDED_RADIUS,
    COLOR_BEZEL, COLOR_CANVAS, COLOR_TEXT_PRIMARY,
    COLOR_TEXT_SECONDARY, COLOR_TEXT_MUTED, COLOR_ACCENT_YELLOW,
    GLOW_STATES, get_microlabel_font, get_display_font,
    get_subtext_font, get_monospaced_font, DASHBOARD_STYLESHEET
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
    if seconds < 0:
        seconds = 0
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
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
        Detects if the foreground window is running in true exclusive full-screen mode
        (games, full-screen video in Chrome/Edge/Firefox/YouTube/VLC/Netflix).
        """
        try:
            # 1. Direct3D / exclusive fullscreen game / presentation check (Windows Shell API)
            qstate = ctypes.c_int()
            if _shell32.SHQueryUserNotificationState(ctypes.byref(qstate)) == 0:
                if qstate.value in (2, 3, 4):  # QUNS_BUSY, QUNS_RUNNING_D3D_FULL_SCREEN, QUNS_PRESENTATION_MODE
                    return True

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
            # True fullscreen F11 / video covers entire physical monitor and obscures the taskbar
            # Standard maximized windows leave the taskbar visible (rect.bottom <= mi.rcWork.bottom)
            if rect.left <= rc.left and rect.top <= rc.top and rect.right >= rc.right and rect.bottom >= rc.bottom:
                if mi.rcWork.bottom < rc.bottom and rect.bottom >= rc.bottom:
                    return True
        except Exception:
            pass
        return False
except Exception:
    def is_fullscreen_app_active(self_hwnd=None) -> bool:
        return False


def extract_album_swatches(image_path_or_pixmap) -> tuple[QColor, QColor]:
    """
    Extracts the vibrant accent color and secondary harmonizing swatch
    from an album cover, enforcing an automatic luminance floor.
    """
    default_vibrant = QColor("#FFD600")
    default_secondary = QColor("#FF8C00")

    if not image_path_or_pixmap or not os.path.exists(str(image_path_or_pixmap)):
        return default_vibrant, default_secondary

    try:
        from PIL import Image
        import colorsys

        img = Image.open(str(image_path_or_pixmap)).convert("RGB")
        img = img.resize((32, 32), Image.Resampling.BOX)

        pixels = list(img.getdata())
        scored = []
        for r, g, b in pixels:
            rf, gf, bf = r / 255.0, g / 255.0, b / 255.0
            h, s, v = colorsys.rgb_to_hsv(rf, gf, bf)
            # Filter near-black, near-white, or washed-out grays
            if v < 0.15 or s < 0.18:
                continue
            score = (s ** 1.3) * (v ** 0.8)
            scored.append((score, h, s, v, r, g, b))

        if not scored:
            return default_vibrant, default_secondary

        scored.sort(key=lambda item: item[0], reverse=True)
        _, h1, s1, v1, r1, g1, b1 = scored[0]

        # Automatic luminance floor: guarantee brightness >= 0.72 so dark covers stay vivid
        v_floor = max(0.72, v1)
        s_floor = max(0.65, min(1.0, s1 * 1.15))
        rf, gf, bf = colorsys.hsv_to_rgb(h1, s_floor, v_floor)
        c_vibrant = QColor(int(rf * 255), int(gf * 255), int(bf * 255))

        # Secondary swatch: complementary or harmonic hue shift
        h2 = (h1 + 0.12) % 1.0  # 43 degree hue shift for harmonic dual-vortex
        rf2, gf2, bf2 = colorsys.hsv_to_rgb(h2, max(0.55, s1), max(0.55, v1 * 0.85))
        c_secondary = QColor(int(rf2 * 255), int(gf2 * 255), int(bf2 * 255))

        return c_vibrant, c_secondary
    except Exception:
        return default_vibrant, default_secondary


class CoverArtWidget(QWidget):
    """
    Apple-inspired media thumbnail card supporting:
    - 16:9 widescreen video thumbnail (92x52px, radius 8px) for YouTube & video.
    - 1:1 squircle cover art (52x52px, radius 12px) for music & audio tracks.
    Smooth bilinear transform and 1px inner specular border.
    """
    def __init__(self, size=52, parent=None):
        super().__init__(parent)
        self.card_size = size
        self._is_video = False
        self.setFixedSize(size, size)
        self._pixmap: Optional[QPixmap] = None

    def set_video_mode(self, is_video: bool):
        if self._is_video != is_video:
            self._is_video = is_video
            if is_video:
                # 16:9 widescreen ratio: 52 * 16 / 9 ≈ 92.4px -> 92x52px
                self.setFixedSize(92, 52)
            else:
                self.setFixedSize(self.card_size, self.card_size)
            self.updateGeometry()
            self.update()

    def set_pixmap(self, pixmap: Optional[QPixmap]):
        self._pixmap = pixmap
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        w = float(self.width())
        h = float(self.height())
        rect = QRectF(0, 0, w, h)
        radius = 8.0 if self._is_video else 12.0

        # 1. Rounded squircle clip
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        painter.save()
        painter.setClipPath(path)

        if self._pixmap and not self._pixmap.isNull():
            painter.drawPixmap(
                rect.toRect(),
                self._pixmap.scaled(
                    int(w), int(h),
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation
                )
            )
        else:
            painter.fillRect(rect, QColor(22, 24, 32))
            cx, cy = w / 2.0, h / 2.0
            if self._is_video:
                # Minimalist video play glyph
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(255, 255, 255, 60))
                tri = QPainterPath()
                tri.moveTo(cx - 5.0, cy - 7.0)
                tri.lineTo(cx + 7.0, cy)
                tri.lineTo(cx - 5.0, cy + 7.0)
                tri.closeSubpath()
                painter.drawPath(tri)
            else:
                # Minimalist vector musical note when idle
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(255, 255, 255, 60))
                note_path = QPainterPath()
                note_path.addEllipse(QPointF(cx - 5.0, cy + 3.0), 3.5, 2.5)
                note_path.addEllipse(QPointF(cx + 4.0, cy + 0.5), 3.5, 2.5)
                painter.drawPath(note_path)
                painter.setPen(QPen(QColor(255, 255, 255, 60), 1.8))
                painter.drawLine(QPointF(cx - 2.5, cy + 3.0), QPointF(cx - 2.5, cy - 6.0))
                painter.drawLine(QPointF(cx + 6.5, cy + 0.5), QPointF(cx + 6.5, cy - 8.5))
                painter.drawLine(QPointF(cx - 2.5, cy - 6.0), QPointF(cx + 6.5, cy - 8.5))

        painter.restore()

        # 2. Subtle 1px inner specular border
        painter.setPen(QPen(QColor(255, 255, 255, 35), 1.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)


class TimelineScrubber(QWidget):
    """
    Apple-inspired interactive scrubbing timeline bar.
    Hit-test area: 14px vertically for comfortable seeking.
    Subtle 3.5px track expanding to 4.5px with a clean white thumb on hover/scrub.
    """
    seek_requested = pyqtSignal(float)  # Normalized position 0.0 to 1.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(14)
        self.setMouseTracking(True)
        self._progress = 0.0  # 0.0 to 1.0
        self._hovered = False
        self._scrubbing = False
        self._scrub_progress = 0.0
        self._accent_color = QColor(255, 255, 255)

    def set_accent_color(self, col: QColor):
        self._accent_color = QColor(col)
        self.update()

    def set_progress(self, progress: float):
        if not self._scrubbing:
            self._progress = max(0.0, min(1.0, progress))
            self.update()

    def enterEvent(self, event):
        self._hovered = True
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        if not self._scrubbing:
            self._hovered = False
            self.unsetCursor()
            self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._scrubbing = True
            self._hovered = True
            pos_x = event.position().x()
            self._scrub_progress = max(0.0, min(1.0, pos_x / max(1.0, float(self.width()))))
            self.update()
            self.seek_requested.emit(self._scrub_progress)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._hovered or self._scrubbing:
            pos_x = event.position().x()
            self._scrub_progress = max(0.0, min(1.0, pos_x / max(1.0, float(self.width()))))
            if self._scrubbing:
                self.seek_requested.emit(self._scrub_progress)
            self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._scrubbing:
            self._scrubbing = False
            self._progress = self._scrub_progress
            self.seek_requested.emit(self._progress)
            if not self.rect().contains(event.position().toPoint()):
                self._hovered = False
                self.unsetCursor()
            self.update()
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        w = float(self.width())
        h = float(self.height())
        cy = h / 2.0

        is_active = self._hovered or self._scrubbing
        track_h = 4.0 if is_active else 3.0
        disp_progress = self._scrub_progress if is_active else self._progress

        # Track background
        track_rect = QRectF(0, cy - track_h / 2.0, w, track_h)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(255, 255, 255, 36))
        painter.drawRoundedRect(track_rect, track_h / 2.0, track_h / 2.0)

        # Track filled (clean white)
        fill_w = max(0.0, min(w, w * disp_progress))
        if fill_w > 0:
            fill_rect = QRectF(0, cy - track_h / 2.0, fill_w, track_h)
            painter.setBrush(QColor(255, 255, 255, 230))
            painter.drawRoundedRect(fill_rect, track_h / 2.0, track_h / 2.0)

        # Clean, refined thumb circle (8px) on hover/scrub
        if is_active:
            thumb_radius = 4.5
            thumb_x = max(thumb_radius, min(w - thumb_radius, fill_w))

            # Subtle contact shadow
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(0, 0, 0, 90))
            painter.drawEllipse(QRectF(thumb_x - thumb_radius, cy - thumb_radius + 1.0, thumb_radius * 2.0, thumb_radius * 2.0))

            # Solid white thumb
            painter.setBrush(QColor("#FFFFFF"))
            painter.drawEllipse(QRectF(thumb_x - thumb_radius, cy - thumb_radius, thumb_radius * 2.0, thumb_radius * 2.0))


class VectorMediaButton(QPushButton):
    """
    Apple-inspired tactile playback control button.
    Renders clean, anti-aliased vector glyphs in pure white on subtle translucent glass.
    """
    def __init__(self, mode="play", is_primary=False, parent=None):
        super().__init__(parent)
        self.mode = mode
        self.is_primary = is_primary
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        if is_primary:
            self.setFixedSize(54, 36)
        else:
            self.setFixedSize(38, 32)

    def set_accent_color(self, col: QColor):
        pass  # Kept for signature compatibility

    def set_mode(self, mode: str):
        if self.mode != mode:
            self.mode = mode
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        w = float(self.width())
        h = float(self.height())
        cx = w / 2.0
        cy = h / 2.0

        rect = QRectF(0, 0, w, h)
        rad = h / 2.0

        is_down = self.isDown()
        is_hover = self.underMouse()

        if self.is_primary:
            # Clean Apple frosted capsule: subtle white glass with sharp white glyph
            bg_alpha = 55 if is_down else (42 if is_hover else 26)
            border_alpha = 80 if is_hover else 40
            painter.setPen(QPen(QColor(255, 255, 255, border_alpha), 1.0))
            painter.setBrush(QColor(255, 255, 255, bg_alpha))
            painter.drawRoundedRect(rect, rad, rad)

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(255, 255, 255, 245))
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
            bg_alpha = 42 if is_down else (28 if is_hover else 14)
            border_alpha = 60 if is_hover else 25
            painter.setPen(QPen(QColor(255, 255, 255, border_alpha), 1.0))
            painter.setBrush(QColor(255, 255, 255, bg_alpha))
            painter.drawRoundedRect(rect, rad, rad)

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(255, 255, 255, 220))
            if self.mode == "prev":
                painter.drawRoundedRect(QRectF(cx - 6.5, cy - 5.5, 2.0, 11.0), 1.0, 1.0)
                tri = QPainterPath()
                tri.moveTo(cx + 4.5, cy - 5.5)
                tri.lineTo(cx - 3.5, cy)
                tri.lineTo(cx + 4.5, cy + 5.5)
                tri.closeSubpath()
                painter.drawPath(tri)
            elif self.mode == "next":
                painter.drawRoundedRect(QRectF(cx + 4.5, cy - 5.5, 2.0, 11.0), 1.0, 1.0)
                tri = QPainterPath()
                tri.moveTo(cx - 4.5, cy - 5.5)
                tri.lineTo(cx + 3.5, cy)
                tri.lineTo(cx - 4.5, cy + 5.5)
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

        # Liquid Edge Docking & Dragging Physics
        self._dock_edge = "top"          # "top", "bottom", "left", "right", "floating"
        self._dock_morph = 1.0           # 1.0 = fully notched ears, 0.0 = pure liquid floating capsule
        self._target_morph = 1.0
        self._dock_ratio_x = 0.5         # Horizontal center ratio along screen (0.0 to 1.0)
        self._dock_ratio_y = 0.5         # Vertical center ratio along screen (0.0 to 1.0)
        self._is_dragging = False
        self._drag_start_global = None
        self._drag_start_pos = None
        self._drag_last_pos = None
        self._liquid_vx = 0.0            # Fluid drag velocity x
        self._liquid_vy = 0.0            # Fluid drag velocity y

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

        # New UI States Data Caches & Timers (OSD, Live Call, 2FA OTP, File Shelf)
        self._osd_info: Dict[str, Any] = {"glyph": "🔊", "value": 0.5, "label": "50%", "type": "volume"}
        self._osd_dismiss_timer = QTimer(self)
        self._osd_dismiss_timer.setSingleShot(True)
        self._osd_dismiss_timer.timeout.connect(self._on_osd_timeout)

        self._call_info: Dict[str, Any] = {"name": "Mom", "status": "iPhone • Incoming Call", "avatar": "👤"}
        self._call_pulse = 0.0

        self._otp_info: Dict[str, Any] = {"code": "482 910", "app": "Messages", "copied": False}
        self._otp_dismiss_timer = QTimer(self)
        self._otp_dismiss_timer.setSingleShot(True)
        self._otp_dismiss_timer.timeout.connect(self._on_otp_timeout)

        self._shelf_files: list[Dict[str, Any]] = []
        self._shelf_hover_clear = False

        # 3D Accessory Connection Sheet Enhancements
        self._device_route = "device"  # "device" (e.g. AirPods) ↔ "speakers"
        self._device_route_pos = 0.0   # 0.0 to 1.0 slide indicator

        # Micro-Interactions & Hardware Status
        self._tilt_x = 0.0
        self._tilt_y = 0.0
        self._tilt_target_x = 0.0
        self._tilt_target_y = 0.0
        self._download_progress = 0.0
        self._auto_hide_enabled = False
        self._active_vibrant_c = QColor("#FFD600")
        self._active_secondary_c = QColor("#FF8C00")

        self._phone_battery = 84
        self._phone_connected = False
        self._privacy_mic = False
        self._privacy_cam = False

        # Theme & Visual Customization Matrix
        self._bg_style = "ambient"  # "ambient", "solid", "gradient"
        self._solid_color = QColor("#08080C")
        self._gradient_c1 = QColor(14, 14, 18, 252)
        self._gradient_c2 = QColor(2, 2, 4, 255)
        self._ambient_enabled = True
        self._ambient_opacity = 0.24

        self._flash_timer = QTimer(self)
        self._flash_timer.setSingleShot(True)
        self._flash_timer.timeout.connect(self._on_flash_timeout)
        self._flash_message: Optional[str] = None

        # Music idle debounce timer (smooth hide without flicker)
        self._music_idle_timer = QTimer(self)
        self._music_idle_timer.setSingleShot(True)
        self._music_idle_timer.setInterval(1200)
        self._music_idle_timer.timeout.connect(self._on_music_idle_timeout)

        # Live playback progress tracking (real-time position ticker)
        self._live_pos = 0.0
        self._live_dur = 0.0
        self._last_live_time = time.time()
        self._live_progress_timer = QTimer(self)
        self._live_progress_timer.setInterval(250)
        self._live_progress_timer.timeout.connect(self._tick_live_progress)
        self._live_progress_timer.start()

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

        # Always visible at launch in compact mode
        self.show()
        self.raise_()
        self._apply_geometry_for_state("compact", animate=False)

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
        if not self._is_music_active() and self._island_state not in ("toast", "expanded", "device_popup"):
            self._apply_geometry_for_state("compact", animate=True)
            self.update()

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
                # Exited fullscreen game/video: restore immediately!
                if not self.isVisible():
                    self.show()
                    self.raise_()

    def wake_up(self):
        """Forces the Dynamic Island to become visible, raise to top, and expand."""
        self._is_fullscreen_suppressed = False
        self.show()
        self.raise_()
        self.activateWindow()
        self.set_island_state("expanded")
        self.set_glow_state("notification", duration_sec=3.0)

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
        self.setAcceptDrops(True)

    def _get_target_rect(self, state: str) -> tuple[int, int, int, int]:
        cur_center = self.geometry().center()
        screen = QGuiApplication.screenAt(cur_center) or QGuiApplication.primaryScreen()
        screen_geo = screen.geometry() if screen else QRectF(0, 0, 1920, 1080).toRect()

        if state == "compact":
            if self._is_music_active() or self._media_info.get("has_media", False):
                w = COMPACT_MUSIC_WIDTH
            else:
                w = COMPACT_IDLE_WIDTH
            h = COMPACT_HEIGHT
        elif state == "toast":
            w = TOAST_WIDTH
            h = TOAST_HEIGHT
        elif state == "device_popup":
            w = DEVICE_POPUP_WIDTH
            h = DEVICE_POPUP_HEIGHT
        elif state == "osd_hud":
            w = OSD_HUD_WIDTH
            h = OSD_HUD_HEIGHT
        elif state == "call_live":
            w = CALL_LIVE_WIDTH
            h = CALL_LIVE_HEIGHT
        elif state == "otp_pill":
            w = OTP_PILL_WIDTH
            h = OTP_PILL_HEIGHT
        elif state == "file_shelf":
            w = FILE_SHELF_WIDTH
            h = FILE_SHELF_HEIGHT
        else:  # expanded
            w = EXPANDED_WIDTH
            h = EXPANDED_HEIGHT

        edge = getattr(self, "_dock_edge", "top")
        ratio_x = getattr(self, "_dock_ratio_x", 0.5)
        ratio_y = getattr(self, "_dock_ratio_y", 0.5)

        if edge == "top":
            center_x = screen_geo.x() + screen_geo.width() * ratio_x
            x = int(center_x - w / 2)
            x = max(int(screen_geo.left()), min(int(screen_geo.right() - w), x))
            if getattr(self, "_auto_hide_enabled", False) and state == "compact" and not self._hovered:
                # 4px translucent tab handle at y = 0
                y = int(screen_geo.top() - h + 4)
            else:
                y = int(screen_geo.top())

        elif edge == "bottom":
            center_x = screen_geo.x() + screen_geo.width() * ratio_x
            x = int(center_x - w / 2)
            x = max(int(screen_geo.left()), min(int(screen_geo.right() - w), x))
            y = int(screen_geo.bottom() - h + 1)

        elif edge == "left":
            x = int(screen_geo.left())
            center_y = screen_geo.y() + screen_geo.height() * ratio_y
            y = int(center_y - h / 2)
            y = max(int(screen_geo.top()), min(int(screen_geo.bottom() - h), y))

        elif edge == "right":
            x = int(screen_geo.right() - w + 1)
            center_y = screen_geo.y() + screen_geo.height() * ratio_y
            y = int(center_y - h / 2)
            y = max(int(screen_geo.top()), min(int(screen_geo.bottom() - h), y))

        else:  # floating
            old_center = getattr(self, "_floating_center", cur_center)
            x = int(old_center.x() - w / 2)
            y = int(old_center.y() - h / 2)
            x = max(int(screen_geo.left() + 10), min(int(screen_geo.right() - w - 10), x))
            y = max(int(screen_geo.top() + 10), min(int(screen_geo.bottom() - h - 10), y))

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
            self._geo_animation.setDuration(340)
            self._geo_animation.setEasingCurve(QEasingCurve.Type.OutBack)
        else:
            self._geo_animation.setDuration(280)
            self._geo_animation.setEasingCurve(QEasingCurve.Type.OutBack)

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
        edge = getattr(self, "_dock_edge", "top")
        m_top = int(NOTCH_RADIUS_TOP + 2) if edge == "top" else 10
        m_bot = int(NOTCH_RADIUS_TOP + 2) if edge == "bottom" else 10
        m_left = 16
        m_right = 16
        self.dashboard_container.setGeometry(
            m_left, m_top,
            max(10, self.width() - m_left - m_right),
            max(10, self.height() - m_top - m_bot)
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

    # -------------------------------------------------------------
    # Theme & Visual Customization Controls
    # -------------------------------------------------------------
    def set_theme_ambient(self, opacity: float = 0.24):
        self._bg_style = "ambient"
        self._ambient_enabled = True
        self._ambient_opacity = opacity
        self.update()

    def set_theme_solid(self, color: QColor):
        self._bg_style = "solid"
        self._solid_color = QColor(color)
        self.update()

    def set_theme_gradient(self, color1: QColor, color2: QColor):
        self._bg_style = "gradient"
        self._gradient_c1 = QColor(color1)
        self._gradient_c2 = QColor(color2)
        self.update()

    def set_ambient_opacity(self, opacity: float):
        self._ambient_opacity = max(0.0, min(1.0, opacity))
        self._ambient_enabled = (self._ambient_opacity > 0.0)
        self.update()

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
        self._toast_dismiss_timer.start(4500)

    def _on_toast_timeout(self):
        if self._island_state == "toast":
            self.collapse_to_compact()

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
    # Frosted Glass Album Art Generator & Accent Extractor
    # -------------------------------------------------------------
    def _update_album_art(self, art_path: Optional[str]):
        if not art_path or not os.path.exists(art_path):
            if self._album_art_pixmap is not None or self._glass_bg_pixmap is not None:
                self._album_art_pixmap = None
                self._glass_bg_pixmap = None
                self._current_art_path = None
                if hasattr(self, "cover_art"):
                    self.cover_art.set_pixmap(None)
                self.update()
            return

        if art_path == self._current_art_path and self._album_art_pixmap is not None:
            return

        self._current_art_path = art_path
        try:
            pix = QPixmap(art_path)
            if not pix.isNull():
                self._album_art_pixmap = pix
                if hasattr(self, "cover_art"):
                    self.cover_art.set_pixmap(pix)

            # Dynamic Accent Extraction & Color Synchronization (400ms transition)
            vibrant_c, secondary_c = extract_album_swatches(art_path)
            self._active_vibrant_c = vibrant_c
            self._active_secondary_c = secondary_c

            if self._glow_state == "music" or self._media_info.get("is_playing", False):
                self._target_glow_c1 = vibrant_c
                self._target_glow_c2 = secondary_c

            if hasattr(self, "visualizer"):
                self.visualizer.set_accent_colors(vibrant_c, secondary_c)
            if hasattr(self, "timeline_scrubber"):
                self.timeline_scrubber.set_accent_color(vibrant_c)
            if hasattr(self, "btn_play"):
                self.btn_play.set_accent_color(vibrant_c)

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
    # Curvy Dashboard UI (Apple-Grade Clean Layout, Zero Nested Cards)
    # -------------------------------------------------------------
    def _init_dashboard_ui(self):
        self.dashboard_container = QWidget(self)
        self.dashboard_container.hide()

        # Placeholders for status ticks if called
        self.lbl_exp_clock = None
        self.lbl_exp_battery = None

        main_layout = QVBoxLayout(self.dashboard_container)
        main_layout.setContentsMargins(14, 10, 14, 12)
        main_layout.setSpacing(10)

        # 1. Main Track & Visualizer Row
        track_row = QHBoxLayout()
        track_row.setContentsMargins(0, 0, 0, 0)
        track_row.setSpacing(12)

        # Album Art (52x52 squircle)
        self.cover_art = CoverArtWidget(size=52, parent=self.dashboard_container)
        track_row.addWidget(self.cover_art)

        # Track Info Box (Title & Artist)
        track_info_box = QVBoxLayout()
        track_info_box.setSpacing(3)
        track_info_box.setContentsMargins(0, 4, 0, 4)

        self.lbl_exp_title = QLabel("No Media Playing", self.dashboard_container)
        self.lbl_exp_title.setFont(get_display_font(12.5))
        self.lbl_exp_title.setFixedHeight(22)
        self.lbl_exp_title.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        self.lbl_exp_title.setStyleSheet("color: #FFFFFF; font-weight: 600; border: none; background: transparent; padding: 0px;")

        self.lbl_exp_artist = QLabel("Ready", self.dashboard_container)
        self.lbl_exp_artist.setFont(get_subtext_font(10.5))
        self.lbl_exp_artist.setFixedHeight(18)
        self.lbl_exp_artist.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        self.lbl_exp_artist.setStyleSheet("color: rgba(255, 255, 255, 0.60); border: none; background: transparent; padding: 0px;")

        track_info_box.addWidget(self.lbl_exp_title)
        track_info_box.addWidget(self.lbl_exp_artist)
        track_row.addLayout(track_info_box, 1)

        # 12-Bar Waveform Visualizer on the right side of the track row (compact Apple-grade visualizer)
        self.visualizer = AudioVisualizerWidget(num_bars=12, bar_width=2.5, bar_spacing=2.0, parent=self.dashboard_container)
        self.visualizer.setFixedHeight(24)
        track_row.addWidget(self.visualizer, alignment=Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)

        main_layout.addLayout(track_row)

        # 2. Timeline Scrubber with Underneath Timestamp Readouts
        scrub_layout = QVBoxLayout()
        scrub_layout.setContentsMargins(0, 2, 0, 0)
        scrub_layout.setSpacing(2)

        self.timeline_scrubber = TimelineScrubber(self.dashboard_container)
        self.timeline_scrubber.seek_requested.connect(self._on_seek_requested)
        scrub_layout.addWidget(self.timeline_scrubber)

        times_row = QHBoxLayout()
        times_row.setContentsMargins(2, 0, 2, 0)

        self.lbl_time_pos = QLabel("0:00", self.dashboard_container)
        self.lbl_time_pos.setFont(get_microlabel_font())
        self.lbl_time_pos.setStyleSheet("color: rgba(255, 255, 255, 0.45); border: none; background: transparent;")

        self.lbl_time_dur = QLabel("0:00", self.dashboard_container)
        self.lbl_time_dur.setFont(get_microlabel_font())
        self.lbl_time_dur.setStyleSheet("color: rgba(255, 255, 255, 0.45); border: none; background: transparent;")

        times_row.addWidget(self.lbl_time_pos)
        times_row.addStretch()
        times_row.addWidget(self.lbl_time_dur)
        scrub_layout.addLayout(times_row)

        main_layout.addLayout(scrub_layout)

        # 3. Centered Playback Controls Row
        controls_layout = QHBoxLayout()
        controls_layout.setContentsMargins(0, 2, 0, 0)
        controls_layout.setSpacing(16)
        controls_layout.addStretch()

        self.btn_prev = VectorMediaButton(mode="prev", is_primary=False, parent=self.dashboard_container)
        self.btn_prev.clicked.connect(self.media_service.previous_track)

        self.btn_play = VectorMediaButton(mode="play", is_primary=True, parent=self.dashboard_container)
        self.btn_play.clicked.connect(self.media_service.toggle_play_pause)

        self.btn_next = VectorMediaButton(mode="next", is_primary=False, parent=self.dashboard_container)
        self.btn_next.clicked.connect(self.media_service.next_track)

        controls_layout.addWidget(self.btn_prev)
        controls_layout.addWidget(self.btn_play)
        controls_layout.addWidget(self.btn_next)
        controls_layout.addStretch()

        main_layout.addLayout(controls_layout)

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
        if hasattr(self, "lbl_exp_battery") and self.lbl_exp_battery is not None:
            self.lbl_exp_battery.setText(f"{icon} {pct}%")
        self.update()

    def _tick_live_progress(self):
        if not self._media_info.get("has_media", False) or not self._media_info.get("is_playing", False):
            self._last_live_time = time.time()
            return
        if getattr(self, "timeline_scrubber", None) and self.timeline_scrubber._scrubbing:
            return

        now = time.time()
        elapsed = now - getattr(self, "_last_live_time", now)
        self._last_live_time = now

        dur = getattr(self, "_live_dur", 0.0)
        if dur <= 0:
            return

        cur_pos = getattr(self, "_live_pos", 0.0) + elapsed
        cur_pos = min(dur, max(0.0, cur_pos))
        self._live_pos = cur_pos

        prog_ratio = cur_pos / dur if dur > 0 else 0.0
        if hasattr(self, "timeline_scrubber"):
            self.timeline_scrubber.set_progress(prog_ratio)
        if hasattr(self, "lbl_time_pos"):
            self.lbl_time_pos.setText(format_seconds(int(cur_pos)))
        if hasattr(self, "lbl_time_dur"):
            self.lbl_time_dur.setText(format_seconds(int(dur)))

    def _on_seek_requested(self, ratio: float):
        dur = getattr(self, "_live_dur", 210.0) or 210.0
        pos = ratio * dur
        self._live_pos = pos
        self._last_live_time = time.time()
        self.media_service.seek(pos)
        self._media_info["position"] = int(pos)
        self.lbl_time_pos.setText(format_seconds(int(pos)))

    def _on_media_updated(self, info: dict):
        prev_has_media = self._media_info.get("has_media", False)
        self._media_info = info
        is_playing = info.get("is_playing", False)
        has_media = info.get("has_media", False)
        is_video = info.get("is_video", False)
        title = info.get("title", "")
        artist = info.get("artist", "")
        pos = float(info.get("position", 0.0))
        dur = float(info.get("duration", 210.0) or 210.0)

        self._live_pos = pos
        self._live_dur = dur
        self._last_live_time = time.time()

        # 1. 16:9 Thumbnail for Video vs 1:1 Squircle for Music
        if hasattr(self, "cover_art"):
            self.cover_art.set_video_mode(is_video)

        # 2. Visualizer only for Music (Hidden for Video)
        if hasattr(self, "visualizer"):
            if is_video:
                self.visualizer.hide()
                self.visualizer.set_playing(False)
            else:
                self.visualizer.show()
                self.visualizer.set_playing(is_playing)

        # 3. Dynamic Text Elision
        avail_w = max(220, self.lbl_exp_title.width() if self.lbl_exp_title.width() > 50 else (300 if is_video else 250))
        fm_t = QFontMetrics(self.lbl_exp_title.font())
        self.lbl_exp_title.setText(fm_t.elidedText(title, Qt.TextElideMode.ElideRight, avail_w))
        self.lbl_exp_title.setToolTip(title)

        avail_a_w = max(220, self.lbl_exp_artist.width() if self.lbl_exp_artist.width() > 50 else (300 if is_video else 250))
        fm_a = QFontMetrics(self.lbl_exp_artist.font())
        self.lbl_exp_artist.setText(fm_a.elidedText(artist, Qt.TextElideMode.ElideRight, avail_a_w))
        self.lbl_exp_artist.setToolTip(artist)

        self.btn_play.set_mode("pause" if is_playing else "play")

        prog_ratio = float(pos / dur) if dur > 0 else 0.0
        self.timeline_scrubber.set_progress(prog_ratio)
        self.lbl_time_pos.setText(format_seconds(int(pos)))
        self.lbl_time_dur.setText(format_seconds(int(dur)))

        # Update Frosted Glass Album Cover & Accent
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
        if hasattr(self, "lbl_exp_clock") and self.lbl_exp_clock is not None:
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

        # Liquid morphing interpolation (lerp factor 0.18 for viscous fluid morphing)
        lerp_morph = 0.18
        old_morph = self._dock_morph
        self._dock_morph += (self._target_morph - self._dock_morph) * lerp_morph
        if abs(self._dock_morph - old_morph) > 0.001:
            self.update()

        # Fluid velocity dampening
        self._liquid_vx *= 0.82
        self._liquid_vy *= 0.82

        # Pulse Phase for Live Call & Device Audio Route Slider
        self._call_pulse += 0.08
        target_route_pos = 1.0 if getattr(self, "_device_route", "device") == "speakers" else 0.0
        self._device_route_pos += (target_route_pos - self._device_route_pos) * 0.22

        # Throttled Download Progress Hairline Checker (~1 Hz)
        now = time.time()
        if now - getattr(self, "_last_dl_check", 0) > 1.2:
            self._last_dl_check = now
            dl_dir = os.path.expanduser("~/Downloads")
            try:
                if os.path.exists(dl_dir):
                    part_files = [
                        os.path.join(dl_dir, f) for f in os.listdir(dl_dir)
                        if f.endswith(".crdownload") or f.endswith(".part")
                    ]
                    # Only actively progressing downloads modified in the last 20 seconds
                    active_parts = [
                        f for f in part_files
                        if (now - os.path.getmtime(f)) < 20.0
                    ]
                    if active_parts:
                        latest = max(active_parts, key=os.path.getmtime)
                        sz = os.path.getsize(latest)
                        self._download_progress = min(0.95, (sz % (10 * 1024 * 1024)) / (10 * 1024 * 1024))
                    elif not getattr(self, "_sim_download_active", False):
                        self._download_progress = 0.0
            except Exception:
                pass

        self.update()

    def _on_ticker_tick(self):
        if not self.isVisible():
            return
        if self._island_state == "compact" and self._media_info.get("has_media", False):
            self._ticker_offset += 1.2
            self.update()

    # -------------------------------------------------------------
    # Mouse Interaction: Liquid Drag-and-Drop & Morphing
    # -------------------------------------------------------------
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position()

            # 1. Check OTP Copy button (Spec 3.3)
            if self._island_state == "otp_pill" and hasattr(self, "_otp_copy_rect"):
                if self._otp_copy_rect.contains(pos):
                    code = self._otp_info.get("code", "482 910")
                    app_inst = QGuiApplication.instance()
                    if app_inst:
                        app_inst.clipboard().setText(code.replace(" ", ""))
                    self._otp_info["copied"] = True
                    self.update()
                    QTimer.singleShot(1500, self.collapse_to_compact)
                    return

            # 2. Check Live Call Answer / Decline buttons (Spec 3.2)
            if self._island_state == "call_live":
                if hasattr(self, "_call_decline_rect") and self._call_decline_rect.contains(pos):
                    self._call_info["status"] = "Call Declined"
                    self.update()
                    QTimer.singleShot(600, self.collapse_to_compact)
                    return
                elif hasattr(self, "_call_answer_rect") and self._call_answer_rect.contains(pos):
                    self._call_info["status"] = "Connected • 00:01"
                    self.update()
                    QTimer.singleShot(2500, self.collapse_to_compact)
                    return

            # 3. Check File Shelf Clear button (Spec 3.4)
            if self._island_state == "file_shelf" and hasattr(self, "_shelf_clear_rect"):
                if self._shelf_clear_rect.contains(pos):
                    self._shelf_files.clear()
                    self.update()
                    return

            # 4. Check Device Audio Route Toggle (Spec 4.2)
            if self._island_state == "device_popup" and hasattr(self, "_device_route_rect"):
                if self._device_route_rect.contains(pos):
                    cur = getattr(self, "_device_route", "device")
                    self._device_route = "speakers" if cur == "device" else "device"
                    self.update()
                    return

            # 5. Check Device Done / Close
            if self._island_state == "device_popup":
                if hasattr(self, "_device_done_rect") and self._device_done_rect.contains(pos):
                    self.collapse_to_compact()
                    return
                elif hasattr(self, "_device_close_rect") and self._device_close_rect.contains(pos):
                    self.collapse_to_compact()
                    return

            # 6. Check Toast Close
            if self._island_state == "toast" and hasattr(self, "_toast_close_rect"):
                if self._toast_close_rect.contains(pos):
                    self.collapse_to_compact()
                    return

            self._drag_start_global = event.globalPosition().toPoint()
            self._drag_start_pos = self.pos()
            self._drag_last_pos = event.globalPosition().toPoint()
            self._is_dragging = False

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        # 1. Fluid Drag & Edge Snapping
        if event.buttons() & Qt.MouseButton.LeftButton and self._drag_start_global is not None:
            cur_pt = event.globalPosition().toPoint()
            delta = cur_pt - self._drag_start_global
            dist = delta.manhattanLength()

            if not self._is_dragging and dist >= 5:
                self._is_dragging = True
                self.setCursor(QCursor(Qt.CursorShape.ClosedHandCursor))

            if self._is_dragging:
                last_pt = getattr(self, "_drag_last_pos", cur_pt)
                vx = float(cur_pt.x() - last_pt.x())
                vy = float(cur_pt.y() - last_pt.y())
                self._liquid_vx = self._liquid_vx * 0.7 + vx * 0.3
                self._liquid_vy = self._liquid_vy * 0.7 + vy * 0.3
                self._drag_last_pos = cur_pt

                screen = QGuiApplication.screenAt(cur_pt) or QGuiApplication.primaryScreen()
                s_geo = screen.geometry() if screen else QRectF(0, 0, 1920, 1080).toRect()

                raw_x = self._drag_start_pos.x() + delta.x()
                raw_y = self._drag_start_pos.y() + delta.y()
                w = self.width()
                h = self.height()

                d_top = abs(raw_y - s_geo.top())
                d_bot = abs(s_geo.bottom() - (raw_y + h))
                d_left = abs(raw_x - s_geo.left())
                d_right = abs(s_geo.right() - (raw_x + w))

                SNAP_DIST = 52
                min_d = min(d_top, d_bot, d_left, d_right)

                if min_d <= SNAP_DIST:
                    if min_d == d_top:
                        target_edge = "top"
                        raw_y = s_geo.top()
                    elif min_d == d_bot:
                        target_edge = "bottom"
                        raw_y = s_geo.bottom() - h + 1
                    elif min_d == d_left:
                        target_edge = "left"
                        raw_x = s_geo.left()
                    else:
                        target_edge = "right"
                        raw_x = s_geo.right() - w + 1
                    self._target_morph = 1.0
                else:
                    target_edge = "floating"
                    self._target_morph = 0.0

                if self._dock_edge != target_edge:
                    self._dock_edge = target_edge

                self.move(int(raw_x), int(raw_y))
                self._floating_center = self.geometry().center()
                self.update()
                return

        # 2. Interactive Hovers
        pos = event.position()
        if self._island_state == "otp_pill" and hasattr(self, "_otp_copy_rect"):
            if self._otp_copy_rect.contains(pos):
                self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                return
            else:
                self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
        elif self._island_state == "call_live":
            if (hasattr(self, "_call_decline_rect") and self._call_decline_rect.contains(pos)) or \
               (hasattr(self, "_call_answer_rect") and self._call_answer_rect.contains(pos)):
                self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                return
            else:
                self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
        elif self._island_state == "file_shelf" and hasattr(self, "_shelf_clear_rect"):
            old_c = getattr(self, "_shelf_hover_clear", False)
            self._shelf_hover_clear = self._shelf_clear_rect.contains(pos)
            if old_c != self._shelf_hover_clear:
                self.update()
            if self._shelf_hover_clear:
                self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                return
            else:
                self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
        elif self._island_state == "device_popup":
            old_d = getattr(self, "_device_done_hovered", False)
            old_c = getattr(self, "_device_close_hovered", False)
            if hasattr(self, "_device_done_rect"):
                self._device_done_hovered = self._device_done_rect.contains(pos)
            else:
                self._device_done_hovered = False
            if hasattr(self, "_device_close_rect"):
                self._device_close_hovered = self._device_close_rect.contains(pos)
            else:
                self._device_close_hovered = False

            if old_d != self._device_done_hovered or old_c != self._device_close_hovered:
                self.update()
            if self._device_done_hovered or self._device_close_hovered or \
               (hasattr(self, "_device_route_rect") and self._device_route_rect.contains(pos)):
                self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            elif not self._is_dragging:
                self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
        elif self._island_state == "compact" and not self._is_dragging:
            self.setCursor(QCursor(Qt.CursorShape.OpenHandCursor))

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._is_dragging:
                self._is_dragging = False
                self._drag_start_global = None

                screen = QGuiApplication.screenAt(self.geometry().center()) or QGuiApplication.primaryScreen()
                s_geo = screen.geometry() if screen else QRectF(0, 0, 1920, 1080).toRect()
                w = self.width()
                h = self.height()

                if self._dock_edge in ("top", "bottom"):
                    self._dock_ratio_x = max(0.08, min(0.92, (self.x() + w / 2.0 - s_geo.left()) / s_geo.width()))
                elif self._dock_edge in ("left", "right"):
                    self._dock_ratio_y = max(0.08, min(0.92, (self.y() + h / 2.0 - s_geo.top()) / s_geo.height()))
                else:
                    self._floating_center = self.geometry().center()

                # Settle cleanly into docked position with liquid spring easing
                self._apply_geometry_for_state(self._island_state, animate=True)
                if self._island_state == "compact":
                    self.setCursor(QCursor(Qt.CursorShape.OpenHandCursor))
                else:
                    self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
                self.update()
                return

            self._drag_start_global = None
            if self._island_state == "device_popup":
                return
            elif self._island_state in ("compact", "toast"):
                self.set_island_state("expanded")
        super().mouseReleaseEvent(event)

    # -------------------------------------------------------------
    # Drag and Drop File Shelf Handlers (Spec 3.4)
    # -------------------------------------------------------------
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            if self._island_state != "file_shelf":
                self.set_island_state("file_shelf")
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            files = []
            for url in event.mimeData().urls():
                lp = url.toLocalFile()
                if lp and os.path.exists(lp):
                    name = os.path.basename(lp)
                    size = os.path.getsize(lp)
                    files.append({"name": name, "path": lp, "size": size})
            if files:
                self._shelf_files.extend(files)
            event.acceptProposedAction()
            self.update()
        else:
            super().dropEvent(event)

    # -------------------------------------------------------------
    # Organic Curvy Hardware Notch Path Generator
    # -------------------------------------------------------------
    def _create_notch_path(self, w: float, h: float) -> QPainterPath:
        morph = max(0.0, min(1.0, getattr(self, "_dock_morph", 1.0)))
        edge = getattr(self, "_dock_edge", "top")
        r_cap = min(h / 2.0, 22.0)

        if self._island_state == "compact":
            r_bot = NOTCH_RADIUS_BOT
            base_r_ear = NOTCH_RADIUS_TOP
        elif self._island_state == "device_popup":
            r_bot = 32.0
            base_r_ear = NOTCH_RADIUS_TOP
        elif self._island_state == "osd_hud":
            r_bot = OSD_HUD_R_BOT
            base_r_ear = OSD_HUD_R_TOP
        elif self._island_state == "call_live":
            r_bot = CALL_LIVE_R_BOT
            base_r_ear = CALL_LIVE_R_TOP
        elif self._island_state == "otp_pill":
            r_bot = OTP_PILL_R_BOT
            base_r_ear = OTP_PILL_R_TOP
        elif self._island_state == "file_shelf":
            r_bot = FILE_SHELF_R_BOT
            base_r_ear = FILE_SHELF_R_TOP
        else:
            r_bot = EXPANDED_RADIUS
            base_r_ear = NOTCH_RADIUS_TOP

        path = QPainterPath()

        if edge == "top":
            r_ear = base_r_ear * morph
            if r_ear > 0.5:
                path.moveTo(0, 0)
                path.cubicTo(r_ear * 0.4, 0, r_ear, r_ear * 0.4, r_ear, r_ear)
                path.lineTo(r_ear, h - r_bot)
                path.quadTo(r_ear, h, r_ear + r_bot, h)
                path.lineTo(w - r_ear - r_bot, h)
                path.quadTo(w - r_ear, h, w - r_ear, h - r_bot)
                path.lineTo(w - r_ear, r_ear)
                path.cubicTo(w - r_ear, r_ear * 0.4, w - r_ear * 0.4, 0, w, 0)
                path.lineTo(0, 0)
            else:
                path.addRoundedRect(QRectF(0, 0, w, h), r_cap, r_cap)

        elif edge == "bottom":
            r_ear = base_r_ear * morph
            if r_ear > 0.5:
                path.moveTo(0, h)
                path.cubicTo(r_ear * 0.4, h, r_ear, h - r_ear * 0.4, r_ear, h - r_ear)
                path.lineTo(r_ear, r_bot)
                path.quadTo(r_ear, 0, r_ear + r_bot, 0)
                path.lineTo(w - r_ear - r_bot, 0)
                path.quadTo(w - r_ear, 0, w - r_ear, r_bot)
                path.lineTo(w - r_ear, h - r_ear)
                path.cubicTo(w - r_ear, h - r_ear * 0.4, w - r_ear * 0.4, h, w, h)
                path.lineTo(0, h)
            else:
                path.addRoundedRect(QRectF(0, 0, w, h), r_cap, r_cap)

        elif edge == "left":
            # Docks cleanly against left screen border; right side is a smooth capsule tab
            r_dock = r_cap * (1.0 - morph)
            r_free = r_cap
            path.moveTo(0, r_dock)
            if r_dock > 0.5:
                path.quadTo(0, 0, r_dock, 0)
            else:
                path.lineTo(0, 0)
            path.lineTo(w - r_free, 0)
            path.quadTo(w, 0, w, r_free)
            path.lineTo(w, h - r_free)
            path.quadTo(w, h, w - r_free, h)
            if r_dock > 0.5:
                path.lineTo(r_dock, h)
                path.quadTo(0, h, 0, h - r_dock)
            else:
                path.lineTo(0, h)
            path.lineTo(0, r_dock)

        elif edge == "right":
            # Docks cleanly against right screen border; left side is a smooth capsule tab
            r_dock = r_cap * (1.0 - morph)
            r_free = r_cap
            path.moveTo(w, r_dock)
            if r_dock > 0.5:
                path.quadTo(w, 0, w - r_dock, 0)
            else:
                path.lineTo(w, 0)
            path.lineTo(r_free, 0)
            path.quadTo(0, 0, 0, r_free)
            path.lineTo(0, h - r_free)
            path.quadTo(0, h, r_free, h)
            if r_dock > 0.5:
                path.lineTo(w - r_dock, h)
                path.quadTo(w, h, w, h - r_dock)
            else:
                path.lineTo(w, h)
            path.lineTo(w, r_dock)

        else:  # "floating" pure liquid capsule
            path.addRoundedRect(QRectF(0, 0, w, h), r_cap, r_cap)

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

        # 3. Canvas Surface Fill (Solid / Gradient / Ambient Base)
        bg_style = getattr(self, "_bg_style", "ambient")
        if bg_style == "solid":
            painter.fillRect(0, 0, int(w), int(h), getattr(self, "_solid_color", QColor("#08080C")))
        elif bg_style == "gradient":
            c_grad = QLinearGradient(0, 0, 0, h)
            c_grad.setColorAt(0.0, getattr(self, "_gradient_c1", QColor(14, 14, 18, 252)))
            c_grad.setColorAt(1.0, getattr(self, "_gradient_c2", QColor(2, 2, 4, 255)))
            painter.fillRect(0, 0, int(w), int(h), c_grad)
        else:  # "ambient" (Deep Liquid Obsidian Glass Base)
            canvas_grad = QLinearGradient(0, 0, 0, h)
            canvas_grad.setColorAt(0.0, QColor(14, 14, 18, 252))
            canvas_grad.setColorAt(0.4, QColor(8, 8, 12, 255))
            canvas_grad.setColorAt(1.0, QColor(2, 2, 4, 255))
            painter.fillRect(0, 0, int(w), int(h), canvas_grad)

        # Ambient diffuse album art atmospheric glow when media is playing
        ambient_on = getattr(self, "_ambient_enabled", True)
        ambient_op = getattr(self, "_ambient_opacity", 0.24)
        if ambient_on and ambient_op > 0 and has_media and self._glass_bg_pixmap and not self._glass_bg_pixmap.isNull() and self._island_state == "expanded":
            painter.save()
            painter.setOpacity(ambient_op)
            painter.drawPixmap(0, 0, int(w), int(h), self._glass_bg_pixmap)
            painter.restore()

        # 4. Subtle Specular Highlight Rim
        edge = getattr(self, "_dock_edge", "top")
        morph = getattr(self, "_dock_morph", 1.0)

        if edge == "top" and morph > 0.15:
            r_top = NOTCH_RADIUS_TOP * morph
            meniscus_grad = QLinearGradient(0, 0, w, 0)
            meniscus_grad.setColorAt(0.0, QColor(255, 255, 255, 0))
            meniscus_grad.setColorAt(r_top / w, QColor(255, 255, 255, 25))
            meniscus_grad.setColorAt(0.5, QColor(255, 255, 255, 60 if self._hovered else 35))
            meniscus_grad.setColorAt((w - r_top) / w, QColor(255, 255, 255, 25))
            meniscus_grad.setColorAt(1.0, QColor(255, 255, 255, 0))
            painter.setPen(QPen(QBrush(meniscus_grad), 1.0))
            painter.drawLine(QPointF(0, 0.75), QPointF(w, 0.75))

        elif edge == "bottom" and morph > 0.15:
            r_top = NOTCH_RADIUS_TOP * morph
            meniscus_grad = QLinearGradient(0, h, w, h)
            meniscus_grad.setColorAt(0.0, QColor(255, 255, 255, 0))
            meniscus_grad.setColorAt(r_top / w, QColor(255, 255, 255, 25))
            meniscus_grad.setColorAt(0.5, QColor(255, 255, 255, 60 if self._hovered else 35))
            meniscus_grad.setColorAt((w - r_top) / w, QColor(255, 255, 255, 25))
            meniscus_grad.setColorAt(1.0, QColor(255, 255, 255, 0))
            painter.setPen(QPen(QBrush(meniscus_grad), 1.0))
            painter.drawLine(QPointF(0, h - 0.75), QPointF(w, h - 0.75))

        # 5. State-Specific Content
        if self._island_state == "compact":
            self._paint_compact_notch(painter, w, h)
        elif self._island_state == "toast":
            self._paint_toast_notch(painter, w, h)
        elif self._island_state == "device_popup":
            self._paint_device_popup_notch(painter, w, h)
        elif self._island_state == "osd_hud":
            self._paint_osd_hud(painter, w, h)
        elif self._island_state == "call_live":
            self._paint_call_live(painter, w, h)
        elif self._island_state == "otp_pill":
            self._paint_otp_pill(painter, w, h)
        elif self._island_state == "file_shelf":
            self._paint_file_shelf(painter, w, h)

        # 6. Subtle Download Progress Hairline (Spec 5.2)
        if getattr(self, "_download_progress", 0.0) > 0.01:
            dl_w = w * self._download_progress
            painter.setPen(QPen(QColor(56, 239, 125, 220), 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawLine(QPointF(0, h - 1.0), QPointF(dl_w, h - 1.0))

        painter.restore()

        # 7. Hardware Bezel Stroke
        bezel_pen = QPen(COLOR_BEZEL, 1.5)
        painter.setPen(bezel_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(notch_path)

        # 8. Subtle Milled Edge Inner Highlight
        highlight_alpha = 24 if self._hovered else 14
        painter.setPen(QPen(QColor(255, 255, 255, highlight_alpha), 1.0))
        painter.drawPath(notch_path)

        # 9. Smart Auto-Hide Peek Tab Handle (Spec 5.3)
        if getattr(self, "_auto_hide_enabled", False) and self._island_state == "compact" and not self._hovered:
            handle_w = 48.0
            handle_rect = QRectF((w - handle_w) / 2.0, h - 3.0, handle_w, 2.5)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(255, 255, 255, 60)))
            painter.drawRoundedRect(handle_rect, 1.25, 1.25)

    def _paint_compact_notch(self, painter: QPainter, w: float, h: float):
        """
        Renders the compact curvy notch with smooth subpixel text.
        """
        is_playing = self._media_info.get("is_playing", False)
        edge = getattr(self, "_dock_edge", "top")
        morph = getattr(self, "_dock_morph", 1.0)

        if edge in ("top", "bottom"):
            r_top = NOTCH_RADIUS_TOP * morph
            content_left = r_top + 12.0
            content_right = w - r_top - 12.0
        elif edge == "left":
            content_left = 12.0
            content_right = w - 18.0
        elif edge == "right":
            content_left = 18.0
            content_right = w - 12.0
        else:  # floating
            content_left = 14.0
            content_right = w - 14.0

        # ── Left: Time ───────────────────────────────────────────
        time_parts = self._time_str.split(" ")
        hhmm = time_parts[0]
        ampm = time_parts[1] if len(time_parts) > 1 else ""

        # Draw HH:MM using QRectF for subpixel-accurate vertical centering
        time_font = get_display_font(10.5)
        painter.setFont(time_font)
        painter.setPen(COLOR_TEXT_PRIMARY)
        fm_time = QFontMetrics(time_font)
        tw = fm_time.horizontalAdvance(hhmm)

        text_h = fm_time.height()
        time_rect = QRectF(content_left, (h - text_h) / 2.0, tw + 2.0, text_h)
        painter.drawText(time_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, hhmm)

        # Draw AM/PM suffix
        ampm_font = get_microlabel_font()
        painter.setFont(ampm_font)
        painter.setPen(COLOR_TEXT_MUTED)
        fm_ampm = QFontMetrics(ampm_font)
        ampm_w = fm_ampm.horizontalAdvance(ampm)
        ampm_rect = QRectF(content_left + tw + 3.0, (h - fm_ampm.height()) / 2.0, ampm_w + 2.0, fm_ampm.height())
        painter.drawText(ampm_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, ampm)

        has_media = bool(self._media_info.get("has_media", False))
        if not has_media:
            # ── Idle Mode: Minimalist Battery Status ────────
            right_offset = content_right
            pct = self._battery_info.get("percent", 100)
            plugged = self._battery_info.get("is_plugged", False)
            batt_text = f"{pct}% ⚡" if plugged else f"{pct}%"

            batt_font = get_microlabel_font()
            painter.setFont(batt_font)
            painter.setPen(QColor(255, 255, 255, 180))
            fm_b = QFontMetrics(batt_font)
            bw = fm_b.horizontalAdvance(batt_text)
            batt_rect = QRectF(right_offset - bw, (h - fm_b.height()) / 2.0, bw + 2.0, fm_b.height())
            painter.drawText(batt_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, batt_text)
            return

        # ── Album Art Squircle (20×20 for music, 28×16 for video) ───
        is_video = bool(self._media_info.get("is_video", False))
        if is_video:
            art_w = 28.0
            art_h = 16.0
            art_rad = 3.5
        else:
            art_w = 20.0
            art_h = 20.0
            art_rad = 5.0

        art_x = content_left + tw + ampm_w + 10.0
        art_y = (h - art_h) / 2.0
        art_rect = QRectF(art_x, art_y, art_w, art_h)

        painter.save()
        art_path = QPainterPath()
        art_path.addRoundedRect(art_rect, art_rad, art_rad)
        painter.setClipPath(art_path)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        if self._album_art_pixmap and not self._album_art_pixmap.isNull():
            painter.drawPixmap(art_rect.toRect(), self._album_art_pixmap.scaled(
                int(art_w), int(art_h),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation
            ))
        else:
            painter.fillRect(art_rect, QColor(25, 27, 36))

        painter.restore()

        painter.setPen(QPen(QColor(255, 255, 255, 25), 1.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(art_rect, art_rad, art_rad)

        # ── Mini 4-Bar Equalizer (Far Right in Pure White - ONLY for Music) ────────
        if not is_video:
            eq_w = 16.0
            eq_x = content_right - eq_w
            eq_cy = h / 2.0
            bar_w = 2.0
            bar_gap = 2.0
            for idx in range(4):
                bx = eq_x + idx * (bar_w + bar_gap)
                bh = max(2.5, self._mini_eq_heights[idx] * 12.0) if is_playing else 2.5
                by = eq_cy - bh / 2.0
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(255, 255, 255, 220) if is_playing else QColor(255, 255, 255, 45))
                painter.drawRoundedRect(QRectF(bx, by, bar_w, bh), 1.0, 1.0)
            right_limit = eq_x - 8.0
        else:
            right_limit = content_right

        # ── Center: Track title + artist (smooth scrolling) ──────
        text_x = art_x + art_w + 8.0
        text_avail_w = max(10.0, right_limit - text_x)
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
        Draws the flagship Apple accessory showcase modal inside the Dynamic Island.
        Combines the iconic vertical Apple card hierarchy (large 3D hero model,
        crystal typography, full-width Apple action button) with true liquid obsidian
        glass morphism, fluid aurora plasma, and top screen bezel notch ears.
        """
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        cat = self._device_info.get("category", "airpods")
        title = self._device_info.get("display_title") or self._device_info.get("name") or "Audio Device"
        subtitle = self._device_info.get("display_subtitle") or "Connected to Windows • Audio Ready"

        r_top = NOTCH_RADIUS_TOP

        # Theme accent & button palette based on device category
        if cat == "airpods":
            cat_label = "● AIRPODS PRO"
            accent_col = QColor("#38EF7D")       # Apple Green LED
            btn_grad_top = QColor("#0071E3")     # Apple Signature Blue
            btn_grad_bot = QColor("#005BB5")
        elif cat == "headphones":
            cat_label = "● OVER-EAR HEADPHONES"
            accent_col = QColor("#56CCF2")       # Cyan rim light
            btn_grad_top = QColor("#2F80ED")
            btn_grad_bot = QColor("#1B5DBB")
        elif cat == "speaker":
            cat_label = "● BLUETOOTH SPEAKER"
            accent_col = QColor("#00D2FF")       # Electric Aqua LED ring
            btn_grad_top = QColor("#00A8FF")
            btn_grad_bot = QColor("#0077B6")
        elif cat == "iem":
            cat_label = "● HI-FI IN-EAR MONITORS"
            accent_col = QColor("#B388FF")       # Smoked Sapphire / Amethyst resin
            btn_grad_top = QColor("#7C4DFF")
            btn_grad_bot = QColor("#5322D4")
        else:
            cat_label = "● AUDIO ACCESSORY"
            accent_col = QColor("#38EF7D")
            btn_grad_top = QColor("#0071E3")
            btn_grad_bot = QColor("#005BB5")

        # ── 1. Base Obsidian Liquid Glass Canvas Fill ────────────────
        canvas_grad = QLinearGradient(0, 0, 0, h)
        canvas_grad.setColorAt(0.0, QColor(22, 24, 34, 252))
        canvas_grad.setColorAt(0.4, QColor(14, 15, 23, 255))
        canvas_grad.setColorAt(1.0, QColor(7, 8, 12, 255))
        painter.fillRect(QRectF(0, 0, w, h), canvas_grad)

        # ── 2. Fluid Dynamic Aurora Plasma (Liquid Color Glow) ───────
        t = getattr(self, "_gradient_shift", 0.0)
        cx = w * 0.5 + math.cos(t * 0.8) * 20.0
        cy = h * 0.48 + math.sin(t * 0.6) * 15.0
        aurora = QRadialGradient(QPointF(cx, cy), w * 0.58)
        aurora.setColorAt(0.0, QColor(accent_col.red(), accent_col.green(), accent_col.blue(), 65))
        aurora.setColorAt(0.52, QColor(accent_col.red(), accent_col.green(), accent_col.blue(), 18))
        aurora.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(aurora))
        painter.drawRect(QRectF(0, 0, w, h))

        # ── 3. Diagonal Liquid Glass Sheen & Top Meniscus ────────────
        sheen = QLinearGradient(0, 0, w * 0.6, h * 0.7)
        sheen.setColorAt(0.0, QColor(255, 255, 255, 30))
        sheen.setColorAt(0.35, QColor(255, 255, 255, 10))
        sheen.setColorAt(0.7, QColor(255, 255, 255, 0))
        painter.fillRect(QRectF(0, 0, w, h), sheen)

        # Top Specular Meniscus Line across curved notch ears
        meniscus = QLinearGradient(0, 0, w, 0)
        meniscus.setColorAt(0.0, QColor(255, 255, 255, 0))
        meniscus.setColorAt(r_top / w, QColor(255, 255, 255, 50))
        meniscus.setColorAt(0.5, QColor(255, 255, 255, 120))
        meniscus.setColorAt((w - r_top) / w, QColor(255, 255, 255, 50))
        meniscus.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.setPen(QPen(QBrush(meniscus), 1.5))
        painter.drawLine(QPointF(0, 0.75), QPointF(w, 0.75))

        # ── 4. Header: Frosted Close Button '✕' ─────────────────────
        close_x = w - r_top - 28.0
        close_y = 20.0
        self._device_close_rect = QRectF(close_x, close_y, 26.0, 26.0)

        is_close_hov = getattr(self, "_device_close_hovered", False)
        close_bg = QColor(255, 255, 255, 36 if is_close_hov else 16)
        close_border = QColor(255, 255, 255, 60 if is_close_hov else 28)

        painter.setPen(QPen(close_border, 1.0))
        painter.setBrush(QBrush(close_bg))
        painter.drawEllipse(self._device_close_rect)

        f_close = get_display_font(9)
        painter.setFont(f_close)
        painter.setPen(QColor(255, 255, 255, 220 if is_close_hov else 160))
        painter.drawText(self._device_close_rect, Qt.AlignmentFlag.AlignCenter, "✕")

        # ── 5. Header: Clean Title & Connection Status ───────────────
        header_x = r_top + 18.0
        header_w = close_x - header_x - 12.0

        # Device Title (Bold Crisp White, 16pt)
        f_title = get_display_font(16)
        f_title.setBold(True)
        painter.setFont(f_title)
        painter.setPen(QColor("#FFFFFF"))
        fm_t = painter.fontMetrics()
        elided_title = fm_t.elidedText(title, Qt.TextElideMode.ElideRight, int(header_w))
        painter.drawText(QRectF(header_x, 32.0, header_w, 28.0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, elided_title)

        # Subtitle (Muted Secondary)
        f_sub = get_subtext_font(10)
        painter.setFont(f_sub)
        painter.setPen(QColor(255, 255, 255, 160))
        fm_s = painter.fontMetrics()
        elided_sub = fm_s.elidedText(subtitle, Qt.TextElideMode.ElideRight, int(header_w))
        painter.drawText(QRectF(header_x, 60.0, header_w, 18.0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, elided_sub)

        # ── 6. Center Stage: Hero Device Model (Static, Crisp, No Jitter) ────────
        art_size = 125.0
        art_cx = w * 0.5
        art_cy = 145.0
        dev_cy = art_cy

        # Soft 3D Contact Shadow
        shadow = QRadialGradient(QPointF(art_cx, dev_cy + 58.0), 50.0)
        shadow.setColorAt(0.0, QColor(0, 0, 0, 140))
        shadow.setColorAt(0.55, QColor(0, 0, 0, 45))
        shadow.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(shadow))
        painter.drawEllipse(QRectF(art_cx - 52.0, dev_cy + 52.0, 104.0, 14.0))

        # Render 3D Device Art
        pix = self._device_pixmaps.get(cat)
        if pix and not pix.isNull():
            scaled_dev = pix.scaled(
                int(art_size), int(art_size),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            ix = art_cx - scaled_dev.width() / 2.0
            iy = dev_cy - scaled_dev.height() / 2.0
            painter.drawPixmap(int(ix), int(iy), scaled_dev)

        # ── 7. Segmented Battery Ring & Percentage Badge ──
        badge_w = 142.0
        badge_h = 26.0
        badge_x = (w - badge_w) / 2.0
        badge_y = 224.0
        badge_rect = QRectF(badge_x, badge_y, badge_w, badge_h)

        painter.setPen(QPen(QColor(255, 255, 255, 24), 1.0))
        painter.setBrush(QBrush(QColor(20, 22, 32, 200)))
        painter.drawRoundedRect(badge_rect, 13.0, 13.0)

        dev_batt = self._device_info.get("battery", 86)
        arc_cx = badge_x + 16.0
        arc_cy = badge_y + 13.0
        arc_r = 6.0
        arc_rect = QRectF(arc_cx - arc_r, arc_cy - arc_r, arc_r * 2.0, arc_r * 2.0)

        # Battery track
        painter.setPen(QPen(QColor(255, 255, 255, 28), 1.8))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(arc_rect)

        # Active battery arc
        arc_col = QColor("#38EF7D") if dev_batt >= 20 else QColor("#FF453A")
        painter.setPen(QPen(arc_col, 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        span_angle = int(-dev_batt * 360 * 16 / 100)
        painter.drawArc(arc_rect, 90 * 16, span_angle)

        f_batt_txt = get_microlabel_font()
        f_batt_txt.setBold(True)
        painter.setFont(f_batt_txt)
        painter.setPen(COLOR_TEXT_PRIMARY)
        painter.drawText(QRectF(arc_cx + 10.0, badge_y, badge_w - 32.0, badge_h), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, f"Battery • {dev_batt}%")

        # Battery track
        painter.setPen(QPen(QColor(255, 255, 255, 30), 2.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(arc_rect)

        # Active battery arc
        arc_col = QColor("#38EF7D") if dev_batt >= 20 else QColor("#FF453A")
        painter.setPen(QPen(arc_col, 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        span_angle = int(-dev_batt * 360 * 16 / 100)
        painter.drawArc(arc_rect, 90 * 16, span_angle)

        f_batt_txt = get_microlabel_font()
        f_batt_txt.setBold(True)
        painter.setFont(f_batt_txt)
        painter.setPen(COLOR_TEXT_PRIMARY)
        painter.drawText(QRectF(arc_cx + 10.0, badge_y, badge_w - 32.0, badge_h), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, f"Battery • {dev_batt}%")

        # ── 9. Inline Audio Routing Pill (Spec 4.2) ──────────────────
        btn_w = w - (r_top * 2 + 28.0)
        btn_h = 42.0
        btn_x = (w - btn_w) / 2.0
        btn_y = 302.0

        route_w = btn_w
        route_h = 34.0
        route_x = btn_x
        route_y = 260.0
        self._device_route_rect = QRectF(route_x, route_y, route_w, route_h)

        # Base capsule
        painter.setPen(QPen(QColor(255, 255, 255, 26), 1.0))
        painter.setBrush(QBrush(QColor(16, 18, 26, 230)))
        painter.drawRoundedRect(self._device_route_rect, 17.0, 17.0)

        # Slide indicator
        seg_w = (route_w - 4.0) / 2.0
        slide_x = route_x + 2.0 + getattr(self, "_device_route_pos", 0.0) * seg_w
        ind_rect = QRectF(slide_x, route_y + 2.0, seg_w, route_h - 4.0)
        painter.setPen(QPen(QColor(255, 255, 255, 42), 1.0))
        painter.setBrush(QBrush(QColor(255, 255, 255, 32)))
        painter.drawRoundedRect(ind_rect, 15.0, 15.0)

        is_dev = (getattr(self, "_device_route", "device") == "device")

        # Seg 1: Device (Vector Headphone + Title)
        hx = route_x + 18.0
        hy = route_y + route_h / 2.0
        painter.setPen(QPen(COLOR_TEXT_PRIMARY if is_dev else COLOR_TEXT_MUTED, 1.4))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawArc(QRectF(hx - 5.0, hy - 6.0, 10.0, 9.0), 0, 180 * 16)
        painter.setBrush(QBrush(COLOR_TEXT_PRIMARY if is_dev else COLOR_TEXT_MUTED))
        painter.drawRoundedRect(QRectF(hx - 6.0, hy - 2.0, 2.5, 6.0), 1.0, 1.0)
        painter.drawRoundedRect(QRectF(hx + 3.5, hy - 2.0, 2.5, 6.0), 1.0, 1.0)

        f_r = get_microlabel_font()
        f_r.setBold(True)
        painter.setFont(f_r)
        painter.setPen(COLOR_TEXT_PRIMARY if is_dev else COLOR_TEXT_MUTED)
        fm_seg1 = painter.fontMetrics()
        short_t = fm_seg1.elidedText(title, Qt.TextElideMode.ElideRight, int(seg_w - 38.0))
        painter.drawText(QRectF(route_x + 28.0, route_y, seg_w - 32.0, route_h), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, short_t)

        # Seg 2: PC Speakers (Vector PC + "PC Speakers")
        sx = route_x + 2.0 + seg_w + 18.0
        sy = route_y + route_h / 2.0
        painter.setPen(QPen(COLOR_TEXT_PRIMARY if not is_dev else COLOR_TEXT_MUTED, 1.2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(QRectF(sx - 6.0, sy - 5.0, 12.0, 8.0), 1.0, 1.0)
        painter.drawLine(QPointF(sx - 8.0, sy + 4.5), QPointF(sx + 8.0, sy + 4.5))

        painter.setPen(COLOR_TEXT_PRIMARY if not is_dev else COLOR_TEXT_MUTED)
        painter.drawText(QRectF(route_x + 2.0 + seg_w + 28.0, route_y, seg_w - 32.0, route_h), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, "PC Speakers")

        # ── 10. Bottom Action Button: Hero Wide Pill ('Done') ────────
        self._device_done_rect = QRectF(btn_x, btn_y, btn_w, btn_h)

        is_done_hov = getattr(self, "_device_done_hovered", False)
        top_col = btn_grad_top.lighter(118) if is_done_hov else btn_grad_top
        bot_col = btn_grad_bot.lighter(118) if is_done_hov else btn_grad_bot

        btn_grad = QLinearGradient(btn_x, btn_y, btn_x, btn_y + btn_h)
        btn_grad.setColorAt(0.0, top_col)
        btn_grad.setColorAt(1.0, bot_col)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(btn_grad))
        painter.drawRoundedRect(self._device_done_rect, 21.0, 21.0)

        # Button Top Specular Rim Highlight Line
        btn_rim = QLinearGradient(btn_x, btn_y, btn_x + btn_w, btn_y)
        btn_rim.setColorAt(0.0, QColor(255, 255, 255, 25))
        btn_rim.setColorAt(0.5, QColor(255, 255, 255, 125 if is_done_hov else 85))
        btn_rim.setColorAt(1.0, QColor(255, 255, 255, 25))
        painter.setPen(QPen(QBrush(btn_rim), 1.2))
        painter.drawLine(QPointF(btn_x + 18.0, btn_y + 0.8), QPointF(btn_x + btn_w - 18.0, btn_y + 0.8))

        # Button Text
        f_btn = get_display_font(12)
        f_btn.setBold(True)
        painter.setFont(f_btn)
        painter.setPen(QColor("#FFFFFF"))
        painter.drawText(self._device_done_rect, Qt.AlignmentFlag.AlignCenter, "Done")

    # -------------------------------------------------------------
    # New UI States QPainter Rendering Engines (Spec Section 3)
    # -------------------------------------------------------------
    def _paint_osd_hud(self, painter: QPainter, w: float, h: float):
        """
        Renders compact 220x36 liquid-glass OSD HUD for volume, brightness, caps.
        """
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        glyph = self._osd_info.get("glyph", "🔊")
        val = max(0.0, min(1.0, float(self._osd_info.get("value", 0.5))))
        label = self._osd_info.get("label", f"{int(val * 100)}%")

        # Left glyph icon
        f_glyph = get_display_font(12)
        painter.setFont(f_glyph)
        painter.setPen(COLOR_TEXT_PRIMARY)
        painter.drawText(QRectF(14.0, 0.0, 24.0, h), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignCenter, glyph)

        # Center fill bar with specular sheen
        bar_x = 44.0
        bar_w = w - bar_x - 52.0
        bar_h = 6.0
        bar_y = (h - bar_h) / 2.0

        bar_bg = QRectF(bar_x, bar_y, bar_w, bar_h)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(255, 255, 255, 28))
        painter.drawRoundedRect(bar_bg, 3.0, 3.0)

        fill_w = bar_w * val
        if fill_w > 0:
            fill_r = QRectF(bar_x, bar_y, fill_w, bar_h)
            grad = QLinearGradient(bar_x, bar_y, bar_x + fill_w, bar_y)
            grad.setColorAt(0.0, QColor("#FFFFFF"))
            grad.setColorAt(1.0, QColor("#E0E0EB"))
            painter.setBrush(QBrush(grad))
            painter.drawRoundedRect(fill_r, 3.0, 3.0)

        # Right percentage readout
        f_val = get_display_font(10)
        painter.setFont(f_val)
        painter.setPen(COLOR_TEXT_SECONDARY)
        painter.drawText(QRectF(w - 48.0, 0.0, 38.0, h), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, label)

    def _paint_call_live(self, painter: QPainter, w: float, h: float):
        """
        Renders live phone call card (420x74) with pulsing avatar and vector Answer/Decline buttons.
        """
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        name = self._call_info.get("name", "Incoming Call")
        subtitle = self._call_info.get("status", "iPhone • Incoming Call")

        # 1. Left circular avatar with pulsing green ring
        av_x = 24.0
        av_y = (h - 42.0) / 2.0
        av_size = 42.0
        av_cx = av_x + av_size / 2.0
        av_cy = av_y + av_size / 2.0

        # Pulsing green ring
        pulse = (math.sin(getattr(self, "_call_pulse", 0.0) * 2.0) + 1.0) / 2.0
        ring_r = av_size / 2.0 + 3.0 + pulse * 6.0
        ring_alpha = int(140 * (1.0 - pulse * 0.7))
        painter.setPen(QPen(QColor(52, 199, 89, ring_alpha), 2.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QPointF(av_cx, av_cy), ring_r, ring_r)

        # Avatar circle
        painter.setPen(Qt.PenStyle.NoPen)
        av_grad = QLinearGradient(av_x, av_y, av_x, av_y + av_size)
        av_grad.setColorAt(0.0, QColor("#3A3D52"))
        av_grad.setColorAt(1.0, QColor("#222433"))
        painter.setBrush(QBrush(av_grad))
        painter.drawEllipse(QRectF(av_x, av_y, av_size, av_size))

        painter.setFont(get_display_font(15))
        painter.setPen(QColor("#FFFFFF"))
        painter.drawText(QRectF(av_x, av_y, av_size, av_size), Qt.AlignmentFlag.AlignCenter, "👤")

        # 2. Center caller name + subtitle
        text_x = av_x + av_size + 14.0
        text_w = w - text_x - 110.0

        f_name = get_display_font(13)
        f_name.setBold(True)
        painter.setFont(f_name)
        painter.setPen(COLOR_TEXT_PRIMARY)
        painter.drawText(QRectF(text_x, av_y + 3.0, text_w, 18.0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, name)

        f_sub = get_subtext_font(10)
        painter.setFont(f_sub)
        painter.setPen(COLOR_TEXT_SECONDARY)
        painter.drawText(QRectF(text_x, av_y + 22.0, text_w, 16.0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, subtitle)

        # 3. Right vector buttons: Decline (#FF3B30) and Answer (#34C759)
        btn_r = 18.0
        btn_y = (h - btn_r * 2.0) / 2.0

        dec_x = w - 95.0
        ans_x = w - 48.0
        self._call_decline_rect = QRectF(dec_x, btn_y, btn_r * 2.0, btn_r * 2.0)
        self._call_answer_rect = QRectF(ans_x, btn_y, btn_r * 2.0, btn_r * 2.0)

        # Decline Button (#FF3B30)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#FF3B30"))
        painter.drawEllipse(self._call_decline_rect)
        painter.setFont(get_display_font(12))
        painter.setPen(QColor("#FFFFFF"))
        painter.drawText(self._call_decline_rect, Qt.AlignmentFlag.AlignCenter, "✕")

        # Answer Button (#34C759)
        painter.setBrush(QColor("#34C759"))
        painter.drawEllipse(self._call_answer_rect)
        painter.setFont(get_display_font(12))
        painter.setPen(QColor("#FFFFFF"))
        painter.drawText(self._call_answer_rect, Qt.AlignmentFlag.AlignCenter, "📞")

    def _paint_otp_pill(self, painter: QPainter, w: float, h: float):
        """
        Renders 2FA verification code pill (360x54) with monospaced tabular numerals and copy button.
        """
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        code = self._otp_info.get("code", "482 910")
        app_name = self._otp_info.get("app", "Messages")
        is_copied = self._otp_info.get("copied", False)

        # Left app badge
        badge_size = 32.0
        badge_x = 16.0
        badge_y = (h - badge_size) / 2.0
        badge_rect = QRectF(badge_x, badge_y, badge_size, badge_size)

        painter.setPen(QPen(QColor(255, 255, 255, 30), 1.0))
        painter.setBrush(QBrush(QColor(86, 204, 242, 45)))
        painter.drawRoundedRect(badge_rect, 8.0, 8.0)

        painter.setFont(get_display_font(13))
        painter.setPen(QColor("#56CCF2"))
        painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, "💬")

        # Center: Title + Code in Monospaced Tabular Numerals
        text_x = badge_x + badge_size + 12.0
        text_w = w - text_x - 105.0

        f_lbl = get_microlabel_font()
        painter.setFont(f_lbl)
        painter.setPen(QColor(255, 255, 255, 160))
        painter.drawText(QRectF(text_x, 8.0, text_w, 14.0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, f"{app_name.upper()} • 2FA CODE")

        f_code = get_monospaced_font(13)
        painter.setFont(f_code)
        painter.setPen(COLOR_TEXT_PRIMARY)
        painter.drawText(QRectF(text_x, 24.0, text_w, 22.0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, code)

        # Right Action Button: "Copy Code" -> "Copied ✓"
        btn_w = 90.0
        btn_h = 28.0
        btn_x = w - btn_w - 14.0
        btn_y = (h - btn_h) / 2.0
        self._otp_copy_rect = QRectF(btn_x, btn_y, btn_w, btn_h)

        if is_copied:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#34C759"))
            painter.drawRoundedRect(self._otp_copy_rect, 14.0, 14.0)
            painter.setFont(get_display_font(10))
            painter.setPen(QColor("#FFFFFF"))
            painter.drawText(self._otp_copy_rect, Qt.AlignmentFlag.AlignCenter, "Copied ✓")
        else:
            painter.setPen(QPen(QColor(255, 255, 255, 45), 1.0))
            painter.setBrush(QColor(255, 255, 255, 24))
            painter.drawRoundedRect(self._otp_copy_rect, 14.0, 14.0)
            painter.setFont(get_display_font(10))
            painter.setPen(COLOR_TEXT_PRIMARY)
            painter.drawText(self._otp_copy_rect, Qt.AlignmentFlag.AlignCenter, "Copy Code")

    def _paint_file_shelf(self, painter: QPainter, w: float, h: float):
        """
        Renders drag-and-drop file shelf tray (460x126) with dashed drop zone and stashed file cards.
        """
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        r_top = NOTCH_RADIUS_TOP
        f_head = get_microlabel_font()
        f_head.setBold(True)
        painter.setFont(f_head)
        painter.setPen(QColor("#56CCF2"))
        painter.drawText(QRectF(r_top + 14.0, 6.0, 160.0, 16.0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, "📁 FILE STASH SHELF")

        # Clear Button
        clear_w = 48.0
        clear_h = 18.0
        clear_x = w - r_top - clear_w - 12.0
        clear_y = 5.0
        self._shelf_clear_rect = QRectF(clear_x, clear_y, clear_w, clear_h)
        is_clear_hov = getattr(self, "_shelf_hover_clear", False)
        painter.setPen(QPen(QColor(255, 255, 255, 50 if is_clear_hov else 25), 1.0))
        painter.setBrush(QBrush(QColor(255, 255, 255, 35 if is_clear_hov else 15)))
        painter.drawRoundedRect(self._shelf_clear_rect, 9.0, 9.0)
        painter.setFont(get_microlabel_font())
        painter.setPen(QColor("#FFFFFF" if is_clear_hov else "#A0A0AB"))
        painter.drawText(self._shelf_clear_rect, Qt.AlignmentFlag.AlignCenter, "Clear")

        # Dashed Luminous Drop Zone
        zone_rect = QRectF(14.0, 26.0, w - 28.0, h - 38.0)
        dash_pen = QPen(QColor(255, 255, 255, 55), 1.2, Qt.PenStyle.DashLine)
        dash_pen.setDashPattern([4, 4])
        painter.setPen(dash_pen)
        painter.setBrush(QBrush(QColor(255, 255, 255, 8)))
        painter.drawRoundedRect(zone_rect, 14.0, 14.0)

        if not self._shelf_files:
            painter.setFont(get_subtext_font(11))
            painter.setPen(QColor(255, 255, 255, 160))
            painter.drawText(zone_rect, Qt.AlignmentFlag.AlignCenter, "📎  Drag & drop files here to stash temporarily")
        else:
            card_w = 88.0
            card_h = 72.0
            gap = 8.0
            start_x = zone_rect.left() + 10.0
            for idx, f in enumerate(self._shelf_files[:4]):
                cx = start_x + idx * (card_w + gap)
                cy = zone_rect.top() + (zone_rect.height() - card_h) / 2.0
                card_r = QRectF(cx, cy, card_w, card_h)

                painter.setPen(QPen(QColor(255, 255, 255, 30), 1.0))
                painter.setBrush(QBrush(QColor(30, 32, 45, 200)))
                painter.drawRoundedRect(card_r, 10.0, 10.0)

                painter.setFont(get_display_font(14))
                painter.setPen(QColor("#56CCF2"))
                painter.drawText(QRectF(cx, cy + 4.0, card_w, 24.0), Qt.AlignmentFlag.AlignCenter, "📄")

                painter.setFont(get_microlabel_font())
                painter.setPen(COLOR_TEXT_PRIMARY)
                fm = painter.fontMetrics()
                short_name = fm.elidedText(f["name"], Qt.TextElideMode.ElideMiddle, int(card_w - 8.0))
                painter.drawText(QRectF(cx + 4.0, cy + 30.0, card_w - 8.0, 16.0), Qt.AlignmentFlag.AlignCenter, short_name)

                sz_str = f"{f['size'] // 1024} KB" if f['size'] > 1024 else f"{f['size']} B"
                painter.setFont(get_microlabel_font())
                painter.setPen(COLOR_TEXT_MUTED)
                painter.drawText(QRectF(cx + 4.0, cy + 48.0, card_w - 8.0, 14.0), Qt.AlignmentFlag.AlignCenter, sz_str)

    # -------------------------------------------------------------
    # State Trigger Methods for External Events & Telemetry
    # -------------------------------------------------------------
    def trigger_osd(self, glyph: str = "🔊", value: float = 0.68, label: str = "68%", osd_type: str = "volume"):
        if self._is_fullscreen_suppressed:
            return
        self._osd_info = {
            "glyph": glyph,
            "value": max(0.0, min(1.0, value)),
            "label": label,
            "type": osd_type
        }
        self.set_glow_state("notification", duration_sec=1.8)
        if not self.isVisible():
            self.show()
            self.raise_()
        self.set_island_state("osd_hud")
        self._osd_dismiss_timer.start(1800)

    def _on_osd_timeout(self):
        if self._island_state == "osd_hud":
            self.collapse_to_compact()

    def trigger_call(self, name: str = "Mom", number: str = "", status: str = "iPhone • Incoming Call", avatar: str = "👤"):
        if self._is_fullscreen_suppressed:
            return
        self._call_info = {
            "name": name,
            "number": number,
            "status": status,
            "avatar": avatar
        }
        self.set_glow_state("success", duration_sec=10.0)
        if not self.isVisible():
            self.show()
            self.raise_()
        self.set_island_state("call_live")

    def trigger_otp(self, code: str = "482 910", app: str = "Messages"):
        if self._is_fullscreen_suppressed:
            return
        self._otp_info = {
            "code": code,
            "app": app,
            "copied": False
        }
        self.set_glow_state("notification", duration_sec=6.0)
        if not self.isVisible():
            self.show()
            self.raise_()
        self.set_island_state("otp_pill")
        self._otp_dismiss_timer.start(5500)

    def _on_otp_timeout(self):
        if self._island_state == "otp_pill":
            self.collapse_to_compact()

    def trigger_file_shelf(self):
        if not self.isVisible():
            self.show()
            self.raise_()
        self.set_glow_state("notification", duration_sec=6.0)
        self.set_island_state("file_shelf")

    def set_download_progress(self, progress: float):
        self._download_progress = max(0.0, min(1.0, progress))
        self.update()

    def toggle_auto_hide(self, enabled: Optional[bool] = None):
        if enabled is None:
            self._auto_hide_enabled = not getattr(self, "_auto_hide_enabled", False)
        else:
            self._auto_hide_enabled = bool(enabled)
        self._apply_geometry_for_state(self._island_state, animate=True)
        self.update()

    def set_phone_battery(self, pct: int):
        self._phone_battery = pct
        self._phone_connected = True
        if hasattr(self, "lbl_exp_phone_battery"):
            self.lbl_exp_phone_battery.setText(f"📱 {pct}%")
            self.lbl_exp_phone_battery.setVisible(True)
        self.update()

    def set_privacy_leds(self, mic: Optional[bool] = None, cam: Optional[bool] = None):
        if mic is not None:
            self._privacy_mic = mic
            if hasattr(self, "led_mic"):
                self.led_mic.setVisible(mic)
        if cam is not None:
            self._privacy_cam = cam
            if hasattr(self, "led_cam"):
                self.led_cam.setVisible(cam)
        self.update()
