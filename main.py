"""
Hardware Notch Desktop Overlay for Windows 11/10
Main Entry Point, System Tray Icon, and Application Lifecycle.
"""

import sys
import os
import time
import ctypes
from ctypes import wintypes
import traceback

from PyQt6.QtWidgets import (
    QApplication, QSystemTrayIcon, QMenu,
    QColorDialog, QMessageBox
)
from PyQt6.QtCore import Qt, QRectF, QAbstractNativeEventFilter, QUrl
from PyQt6.QtGui import (
    QIcon, QPixmap, QPainter, QColor, QPen,
    QBrush, QAction, QActionGroup, QGuiApplication,
    QDesktopServices
)

# -------------------------------------------------------------
# Single Instance Lock & Wakeup via Windows Named Mutex & IPC
# If the app is already running, notify the active instance to
# reveal & expand the Dynamic Island immediately, then exit.
# -------------------------------------------------------------
MUTEX_NAME = "Global\\WinDinDynamicIsland_SingleInstanceMutex"
_kernel32 = ctypes.windll.kernel32
_user32 = ctypes.windll.user32
WM_SHOW_DYNAMIC_ISLAND = _user32.RegisterWindowMessageW("WinDin_ShowDynamicIsland")

_mutex_handle = _kernel32.CreateMutexW(None, True, MUTEX_NAME)
ERROR_ALREADY_EXISTS = 183
if _kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
    # Another instance is already running!
    # 1. Wake up running instance via local phone bridge HTTP endpoint (<10ms)
    try:
        import urllib.request
        req = urllib.request.Request("http://127.0.0.1:54321/api/wake")
        urllib.request.urlopen(req, timeout=1.0)
    except Exception:
        pass
    # 2. Also broadcast native Windows message
    HWND_BROADCAST = 0xFFFF
    _user32.PostMessageW(HWND_BROADCAST, WM_SHOW_DYNAMIC_ISLAND, 0, 0)
    sys.exit(0)

# Unhandled Exception Safety Hook
def _exception_hook(exctype, value, tb):
    err_str = "".join(traceback.format_exception(exctype, value, tb))
    log_file = os.path.join(os.path.expanduser("~"), "DynamicIsland_crash.log")
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"\n--- {time.ctime()} ---\n{err_str}\n")
    except Exception:
        pass

sys.excepthook = _exception_hook


class AppNativeEventFilter(QAbstractNativeEventFilter):
    """
    Handles native Windows broadcasts:
    1. TaskbarCreated: Restores system tray icon if Windows Explorer restarts.
    2. WinDin_ShowDynamicIsland: Reveals/expands island when user launches the app.
    """
    def __init__(self, island, tray_icon: QSystemTrayIcon):
        super().__init__()
        self.island = island
        self.tray_icon = tray_icon
        self.wm_taskbar_created = _user32.RegisterWindowMessageW("TaskbarCreated")
        self.wm_show_island = WM_SHOW_DYNAMIC_ISLAND

    def nativeEventFilter(self, event_type, message):
        if event_type == b"windows_generic_MSG":
            try:
                msg = wintypes.MSG.from_address(int(message))
                if msg.message == self.wm_taskbar_created:
                    self.tray_icon.hide()
                    self.tray_icon.show()
                elif msg.message == self.wm_show_island:
                    # User clicked app or launched again: reveal Dynamic Island!
                    self.island.wake_up()
            except Exception:
                pass
        return False, 0

from services.media_service import MediaService
from services.system_service import SystemService
from services.device_listener import DeviceService
from services.autostart_service import is_autostart_enabled, set_autostart
from services.phone_bridge import PhoneBridgeService
from ui.island_widget import DynamicIslandWidget
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtCore import QUrl


def resource_path(relative_path: str) -> str:
    """Get absolute path to resource, works for dev and for PyInstaller"""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)


def create_tray_icon() -> QIcon:
    ico_path = resource_path(os.path.join("assets", "app_icon.ico"))
    if os.path.exists(ico_path):
        return QIcon(ico_path)

    pix = QPixmap(64, 64)
    pix.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    notch_rect = QRectF(12, 16, 40, 20)
    painter.setPen(QPen(QColor("#0A0A0C"), 1.5))
    painter.setBrush(QBrush(QColor("#0E0E14")))
    painter.drawRoundedRect(notch_rect, 6, 6)

    glow_rect = QRectF(34, 22, 8, 8)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(QColor("#0071E3")))
    painter.drawEllipse(glow_rect)

    painter.end()
    return QIcon(pix)


def main():
    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
    os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"
    app = QApplication(sys.argv)
    app.setApplicationName("Hardware Notch Overlay")
    app.setQuitOnLastWindowClosed(False)

    # Global smooth font rendering
    from PyQt6.QtGui import QFont
    default_font = QFont("Segoe UI", 10)
    default_font.setStyleStrategy(
        QFont.StyleStrategy.PreferAntialias |
        QFont.StyleStrategy.PreferQuality
    )
    app.setFont(default_font)

    media_service = MediaService()
    system_service = SystemService()
    device_service = DeviceService()
    phone_service = PhoneBridgeService(port=54321)

    island = DynamicIslandWidget(media_service, system_service, device_service)
    # Always present on launch: smoothly sit flush at top screen bezel in compact mode
    island.show()
    island.raise_()
    island.set_island_state("compact")
    island.set_glow_state("notification", duration_sec=3.5)

    media_service.start()
    system_service.start()
    device_service.start()

    # Wire phone notifications and remote wakeups to Dynamic Island with smart state routing
    import re

    def on_phone_notification(data: dict):
        app = data.get("app", "")
        title = data.get("title", "")
        msg = data.get("message", "")
        phone_type = data.get("phone", "iPhone")

        # 1. Incoming Call Detection -> call_live state (Spec 3.2)
        if "call" in app.lower() or "call" in title.lower() or "incoming" in msg.lower():
            caller = title if title and "call" not in title.lower() else (msg.split(" ")[0] if msg else "Mom")
            island.trigger_call(name=caller, number="", status=f"{phone_type} • Incoming Call")
            return

        # 2. 2FA Verification Code Detection -> otp_pill state (Spec 3.3)
        code_match = re.search(r'\b\d{3}[ -]\d{3}\b', msg) or re.search(r'\b\d{4,8}\b', msg)
        if ("otp" in msg.lower() or "code" in msg.lower() or "verification" in msg.lower() or "2fa" in msg.lower() or "code" in title.lower()) and code_match:
            clean_app = app.replace("📱", "").strip() or "Messages"
            island.trigger_otp(code=code_match.group(0), app=clean_app)
            return

        # 3. Default Notification Toast
        island.trigger_toast(app, title, msg)

    phone_service.notification_received.connect(on_phone_notification)
    phone_service.wake_requested.connect(island.wake_up)
    phone_service.device_paired.connect(
        lambda d: island.set_glow_state("success", duration_sec=2.5)
    )
    phone_service.start()

    # ── System Tray ──────────────────────────────────────────────
    tray_icon = QSystemTrayIcon(create_tray_icon(), app)
    app.setWindowIcon(create_tray_icon())
    tray_icon.setToolTip("Hardware Notch Overlay")

    # Native event filter: Restores tray icon on Explorer restart & reveals island on launch
    event_filter = AppNativeEventFilter(island, tray_icon)
    app.installNativeEventFilter(event_filter)

    # Ensure autostart is enabled permanently across Windows boot
    set_autostart(True)

    tray_menu = QMenu()
    tray_menu.setStyleSheet("""
        QMenu {
            background-color: #14151D;
            color: #EEEEF2;
            border: 1px solid rgba(255, 255, 255, 0.12);
            border-radius: 9px;
            padding: 5px;
            font-family: 'Segoe UI', -apple-system, sans-serif;
            font-size: 11.5px;
        }
        QMenu::item {
            padding: 5px 22px 5px 12px;
            border-radius: 5px;
            margin: 1px 0px;
        }
        QMenu::item:selected {
            background-color: #0A84FF;
            color: #FFFFFF;
        }
        QMenu::item:disabled {
            color: #585A66;
        }
        QMenu::separator {
            height: 1px;
            background-color: rgba(255, 255, 255, 0.08);
            margin: 4px 4px;
        }
    """)

    # ── 1. Primary Controls ──────────────────────────────────────
    act_toggle = QAction("Expand Island  (Alt+Space)", tray_menu)
    def on_toggle():
        island.toggle_expanded()
        act_toggle.setText("Collapse Island  (Alt+Space)" if island._island_state == "expanded" else "Expand Island  (Alt+Space)")
    act_toggle.triggered.connect(on_toggle)
    tray_menu.addAction(act_toggle)

    def set_dock(edge: str):
        island._dock_edge = edge
        island._target_morph = 1.0 if edge != "floating" else 0.0
        island._dock_ratio_x = 0.5
        island._dock_ratio_y = 0.5
        island._apply_geometry_for_state(island._island_state, animate=True)
        island.update()

    act_recenter = QAction("Recenter to Top Bezel", tray_menu)
    act_recenter.triggered.connect(lambda: set_dock("top"))
    tray_menu.addAction(act_recenter)

    tray_menu.addSeparator()

    # ── 2. Appearance & Theme Controls ───────────────────────────
    menu_appearance = tray_menu.addMenu("Appearance")

    # Mode: Ambient Reactive vs Obsidian Solid
    group_mode = QActionGroup(tray_menu)
    group_mode.setExclusive(True)

    act_mode_ambient = QAction("Ambient Reactive (Dynamic Cover Art Glow)", menu_appearance)
    act_mode_ambient.setCheckable(True)
    act_mode_ambient.setChecked(True)
    act_mode_ambient.triggered.connect(lambda: island.set_theme_ambient(0.24))
    group_mode.addAction(act_mode_ambient)
    menu_appearance.addAction(act_mode_ambient)

    act_mode_obsidian = QAction("OLED Obsidian (Deep Black Glass)", menu_appearance)
    act_mode_obsidian.setCheckable(True)
    act_mode_obsidian.triggered.connect(lambda: island.set_theme_solid(QColor("#08080C")))
    group_mode.addAction(act_mode_obsidian)
    menu_appearance.addAction(act_mode_obsidian)

    act_mode_titanium = QAction("Frosted Titanium (Dark Translucent Glass)", menu_appearance)
    act_mode_titanium.setCheckable(True)
    act_mode_titanium.triggered.connect(lambda: island.set_theme_solid(QColor("#181A22")))
    group_mode.addAction(act_mode_titanium)
    menu_appearance.addAction(act_mode_titanium)

    menu_appearance.addSeparator()

    # Solid Colors Submenu
    menu_solid = menu_appearance.addMenu("Solid Colors")
    solids = [
        ("Obsidian Black", QColor("#08080C")),
        ("Midnight Blue", QColor("#0B132B")),
        ("Space Gray", QColor("#1C1C1E")),
        ("Deep Emerald", QColor("#081C15")),
        ("Royal Amethyst", QColor("#180F2A")),
        ("Slate Titanium", QColor("#1A1D24")),
    ]
    for name, col in solids:
        act = QAction(name, menu_solid)
        act.triggered.connect(lambda checked=False, c=col: (island.set_theme_solid(c), act_mode_obsidian.setChecked(True)))
        menu_solid.addAction(act)

    menu_solid.addSeparator()
    def pick_custom_color():
        c = QColorDialog.getColor(QColor("#08080C"), None, "Select Island Color")
        if c.isValid():
            island.set_theme_solid(c)
            act_mode_obsidian.setChecked(True)
    act_custom_solid = QAction("Custom Color...", menu_solid)
    act_custom_solid.triggered.connect(pick_custom_color)
    menu_solid.addAction(act_custom_solid)

    # Gradients Submenu
    menu_gradients = menu_appearance.addMenu("Gradients")
    gradients = [
        ("Obsidian Noir", QColor(24, 25, 32), QColor(4, 4, 6)),
        ("Sunset Ember", QColor(45, 19, 38), QColor(10, 5, 16)),
        ("Oceanic Depth", QColor(11, 32, 50), QColor(3, 10, 18)),
        ("Emerald Aurora", QColor(12, 37, 28), QColor(4, 14, 10)),
        ("Cosmic Violet", QColor(29, 16, 53), QColor(7, 3, 18)),
        ("Titanium Minimal", QColor(36, 38, 46), QColor(14, 16, 20)),
    ]
    for name, c1, c2 in gradients:
        act = QAction(name, menu_gradients)
        act.triggered.connect(lambda checked=False, col1=c1, col2=c2: (island.set_theme_gradient(col1, col2), act_mode_obsidian.setChecked(True)))
        menu_gradients.addAction(act)

    menu_appearance.addSeparator()

    # Ambient Backlight Opacity Submenu
    menu_ambient = menu_appearance.addMenu("Ambient Glow Intensity")
    glow_levels = [
        ("Subtle (15%)", 0.15),
        ("Balanced (25%)", 0.25),
        ("Vibrant (40%)", 0.40),
        ("Disabled (0%)", 0.0),
    ]
    group_glow = QActionGroup(tray_menu)
    group_glow.setExclusive(True)
    for name, val in glow_levels:
        act = QAction(name, menu_ambient)
        act.setCheckable(True)
        if val == 0.25:
            act.setChecked(True)
        act.triggered.connect(lambda checked=False, v=val: island.set_ambient_opacity(v))
        group_glow.addAction(act)
        menu_ambient.addAction(act)

    # ── 3. Position & Docking ────────────────────────────────────
    menu_dock = tray_menu.addMenu("Position & Docking")
    group_dock = QActionGroup(tray_menu)
    group_dock.setExclusive(True)

    act_dock_top = QAction("Top Bezel (Default)", menu_dock)
    act_dock_top.setCheckable(True)
    act_dock_top.setChecked(True)
    act_dock_top.triggered.connect(lambda: set_dock("top"))
    group_dock.addAction(act_dock_top)
    menu_dock.addAction(act_dock_top)

    act_dock_bottom = QAction("Bottom Taskbar Edge", menu_dock)
    act_dock_bottom.setCheckable(True)
    act_dock_bottom.triggered.connect(lambda: set_dock("bottom"))
    group_dock.addAction(act_dock_bottom)
    menu_dock.addAction(act_dock_bottom)

    act_dock_floating = QAction("Free Floating Anywhere", menu_dock)
    act_dock_floating.setCheckable(True)
    act_dock_floating.triggered.connect(lambda: set_dock("floating"))
    group_dock.addAction(act_dock_floating)
    menu_dock.addAction(act_dock_floating)

    menu_dock.addSeparator()
    act_dock_center = QAction("Snap to Screen Center", menu_dock)
    act_dock_center.triggered.connect(lambda: set_dock("top"))
    menu_dock.addAction(act_dock_center)

    tray_menu.addSeparator()

    # ── 4. Preferences ───────────────────────────────────────────
    act_autohide = QAction("Auto-Hide when Idle", tray_menu)
    act_autohide.setCheckable(True)
    act_autohide.setChecked(False)
    act_autohide.toggled.connect(island.toggle_auto_hide)
    tray_menu.addAction(act_autohide)

    act_autostart = QAction("Start with Windows", tray_menu)
    act_autostart.setCheckable(True)
    act_autostart.setChecked(is_autostart_enabled())
    act_autostart.toggled.connect(set_autostart)
    tray_menu.addAction(act_autostart)

    tray_menu.addSeparator()

    # ── 5. Tools & Accessories ───────────────────────────────────
    menu_tools = tray_menu.addMenu("Tools & Accessories")

    act_phone = QAction("Phone Companion Dashboard", menu_tools)
    act_phone.triggered.connect(lambda: QDesktopServices.openUrl(QUrl(phone_service.pairing_url)))
    menu_tools.addAction(act_phone)

    act_copy_ip = QAction("Copy Companion Address", menu_tools)
    def copy_phone_url():
        clip = QGuiApplication.clipboard()
        if clip:
            clip.setText(phone_service.pairing_url)
    act_copy_ip.triggered.connect(copy_phone_url)
    menu_tools.addAction(act_copy_ip)

    menu_tools.addSeparator()

    act_screenshot = QAction("Take Screenshot", menu_tools)
    act_screenshot.triggered.connect(system_service.take_screenshot)
    menu_tools.addAction(act_screenshot)

    act_mute = QAction("Toggle Audio Mute", menu_tools)
    act_mute.triggered.connect(system_service.toggle_mute)
    menu_tools.addAction(act_mute)

    act_dnd = QAction("Toggle Do Not Disturb", menu_tools)
    act_dnd.triggered.connect(system_service.toggle_dnd)
    menu_tools.addAction(act_dnd)

    # ── 6. Diagnostics & Preview ─────────────────────────────────
    menu_sim = tray_menu.addMenu("Diagnostics & Preview")
    act_test_toast = QAction("Simulate Calendar Notification", menu_sim)
    act_test_toast.triggered.connect(lambda: system_service.trigger_test_notification(
        app="Calendar",
        title="12:30 PM Standup",
        message="Sprint Architecture Review starts in 5 minutes"
    ))
    menu_sim.addAction(act_test_toast)

    act_sim_osd = QAction("Simulate Volume HUD", menu_sim)
    act_sim_osd.triggered.connect(lambda: island.trigger_osd("Volume", 0.72, "72%", "volume"))
    menu_sim.addAction(act_sim_osd)

    act_sim_call = QAction("Simulate Incoming Call", menu_sim)
    act_sim_call.triggered.connect(lambda: island.trigger_call("Mom", "+1 (555) 234-5678", "iPhone • Incoming Call"))
    menu_sim.addAction(act_sim_call)

    act_sim_otp = QAction("Simulate Two-Factor OTP", menu_sim)
    act_sim_otp.triggered.connect(lambda: island.trigger_otp("482 910", "Messages"))
    menu_sim.addAction(act_sim_otp)

    act_sim_shelf = QAction("Simulate File Shelf", menu_sim)
    act_sim_shelf.triggered.connect(island.trigger_file_shelf)
    menu_sim.addAction(act_sim_shelf)

    act_sim_dl = QAction("Simulate Download Hairline", menu_sim)
    act_sim_dl.triggered.connect(lambda: island.set_download_progress(0.75))
    menu_sim.addAction(act_sim_dl)

    act_test_mock = QAction("Toggle Demo Audio Track", menu_sim)
    act_test_mock.triggered.connect(media_service.toggle_mock_mode)
    menu_sim.addAction(act_test_mock)

    menu_sim.addSeparator()
    act_sim_airpods = QAction("Simulate AirPods Pro Popup", menu_sim)
    act_sim_airpods.triggered.connect(lambda: device_service.trigger_simulated_device("airpods", "Manu's AirPods Pro"))
    menu_sim.addAction(act_sim_airpods)

    act_sim_headphones = QAction("Simulate Over-Ear Headphones", menu_sim)
    act_sim_headphones.triggered.connect(lambda: device_service.trigger_simulated_device("headphones", "Sony WH-1000XM5"))
    menu_sim.addAction(act_sim_headphones)

    tray_menu.addSeparator()

    # ── 7. About & Exit ──────────────────────────────────────────
    def show_about():
        QMessageBox.about(
            None,
            "About WindowLand",
            "<h3>WindowLand Dynamic Island</h3>"
            "<p>Apple-inspired hardware notch and interactive desktop overlay for Windows 11/10.</p>"
            "<p><b>Version:</b> 2.0.0<br><b>Shortcut:</b> Alt+Space</p>"
        )
    act_about = QAction("About WindowLand", tray_menu)
    act_about.triggered.connect(show_about)
    tray_menu.addAction(act_about)

    act_quit = QAction("Quit WindowLand", tray_menu)
    def on_quit():
        media_service.stop()
        system_service.stop()
        device_service.stop()
        phone_service.stop()
        app.quit()
    act_quit.triggered.connect(on_quit)
    tray_menu.addAction(act_quit)

    tray_icon.setContextMenu(tray_menu)
    # Single-click tray icon → expand/collapse island
    tray_icon.activated.connect(
        lambda reason: island.toggle_expanded()
        if reason == QSystemTrayIcon.ActivationReason.Trigger else None
    )
    tray_icon.show()
    tray_icon.showMessage(
        "Dynamic Island Active",
        "Running in background at top of screen. Press Alt+Space to expand.",
        QSystemTrayIcon.MessageIcon.Information,
        3000
    )

    app.aboutToQuit.connect(media_service.stop)
    app.aboutToQuit.connect(system_service.stop)
    app.aboutToQuit.connect(device_service.stop)
    app.aboutToQuit.connect(phone_service.stop)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
