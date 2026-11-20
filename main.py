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

from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PyQt6.QtCore import Qt, QRectF, QAbstractNativeEventFilter
from PyQt6.QtGui import (
    QIcon, QPixmap, QPainter, QColor, QPen,
    QBrush, QAction, QGuiApplication
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
        req = urllib.request.Request("http://127.0.0.1:54321/api/wake", data=b"{}", headers={"Content-Type": "application/json"})
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
                    if not self.island.isVisible():
                        self.island.show()
                    self.island.raise_()
                    self.island.set_glow_state("notification", duration_sec=3.0)
                    self.island.set_island_state("expanded")
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
    painter.setBrush(QBrush(QColor("#FFD600")))
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

    # Wire phone notifications and remote wakeups to Dynamic Island
    phone_service.notification_received.connect(
        lambda data: island.trigger_toast(data["app"], data["title"], data["message"])
    )
    phone_service.wake_requested.connect(
        lambda: (island.show(), island.raise_(), island.set_glow_state("notification", duration_sec=3.0), island.set_island_state("expanded"))
    )
    phone_service.device_paired.connect(
        lambda d: island.set_glow_state("success", duration_sec=3.0)
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
            background-color: #14141C;
            color: #FFFFFF;
            border: 1px solid rgba(255, 255, 255, 0.15);
            border-radius: 8px;
            padding: 4px;
            font-family: 'Segoe UI';
            font-size: 11px;
        }
        QMenu::item {
            padding: 5px 16px 5px 8px;
            border-radius: 4px;
        }
        QMenu::item:selected {
            background-color: #FFD600;
            color: #000000;
        }
        QMenu::item:disabled {
            color: #666672;
        }
        QMenu::separator {
            height: 1px;
            background-color: rgba(255, 255, 255, 0.1);
            margin: 3px 0px;
        }
    """)

    act_header = QAction("⬛  Notch Overlay", tray_menu)
    act_header.setEnabled(False)
    tray_menu.addAction(act_header)
    tray_menu.addSeparator()

    act_phone = QAction(f"📱  Connect Phone (http://{phone_service.local_ip}:{phone_service.port})", tray_menu)
    act_phone.triggered.connect(lambda: QDesktopServices.openUrl(QUrl(phone_service.pairing_url)))
    tray_menu.addAction(act_phone)

    act_toggle = QAction("⤢  Expand / Collapse  (Alt+Space)", tray_menu)
    act_toggle.triggered.connect(island.toggle_expanded)
    tray_menu.addAction(act_toggle)

    menu_dock = tray_menu.addMenu("📍  Dock Position")
    def set_dock(edge: str):
        island._dock_edge = edge
        island._target_morph = 1.0 if edge != "floating" else 0.0
        island._dock_ratio_x = 0.5
        island._dock_ratio_y = 0.5
        island._apply_geometry_for_state(island._island_state, animate=True)
        island.update()

    act_dock_top = QAction("⬆  Top Bezel (Default)", menu_dock)
    act_dock_top.triggered.connect(lambda: set_dock("top"))
    menu_dock.addAction(act_dock_top)

    act_dock_bottom = QAction("⬇  Bottom Taskbar Edge", menu_dock)
    act_dock_bottom.triggered.connect(lambda: set_dock("bottom"))
    menu_dock.addAction(act_dock_bottom)

    act_dock_floating = QAction("⚬  Float Freely Anywhere", menu_dock)
    act_dock_floating.triggered.connect(lambda: set_dock("floating"))
    menu_dock.addAction(act_dock_floating)

    act_center = QAction("⊙  Recenter Notch", tray_menu)
    act_center.triggered.connect(lambda: set_dock("top"))
    tray_menu.addAction(act_center)

    tray_menu.addSeparator()

    act_screenshot = QAction("📸  Screenshot", tray_menu)
    act_screenshot.triggered.connect(system_service.take_screenshot)
    tray_menu.addAction(act_screenshot)

    act_mute = QAction("🔇  Toggle Mute", tray_menu)
    act_mute.triggered.connect(system_service.toggle_mute)
    tray_menu.addAction(act_mute)

    act_dnd = QAction("🌙  Do Not Disturb", tray_menu)
    act_dnd.triggered.connect(system_service.toggle_dnd)
    tray_menu.addAction(act_dnd)

    tray_menu.addSeparator()

    act_autostart = QAction("🚀  Start with Windows", tray_menu)
    act_autostart.setCheckable(True)
    act_autostart.setChecked(is_autostart_enabled())
    act_autostart.toggled.connect(set_autostart)
    tray_menu.addAction(act_autostart)

    tray_menu.addSeparator()

    # Test / simulate submenu (kept for debugging, hidden from main view)
    menu_sim = tray_menu.addMenu("🧪  Test & Simulate")
    act_test_toast = QAction("🔔 Test Notification", menu_sim)
    act_test_toast.triggered.connect(lambda: system_service.trigger_test_notification(
        app="Calendar",
        title="12:30 PM Standup",
        message="Sprint Architecture Review starts in 5 minutes"
    ))
    menu_sim.addAction(act_test_toast)

    act_sim_phone = QAction("📱 Test Phone Notification (WhatsApp)", menu_sim)
    act_sim_phone.triggered.connect(lambda: island.trigger_toast(
        "📱 WHATSAPP", "Sarah Jenkins (iPhone)", "Hey! Are you joining the design sync now?"
    ))
    menu_sim.addAction(act_sim_phone)

    act_test_mock = QAction("🎵 Demo Track (Toggle)", menu_sim)
    act_test_mock.triggered.connect(media_service.toggle_mock_mode)
    menu_sim.addAction(act_test_mock)

    menu_sim.addSeparator()
    act_sim_airpods = QAction("🎧 AirPods Pro (Pop-up)", menu_sim)
    act_sim_airpods.triggered.connect(lambda: device_service.trigger_simulated_device("airpods", "Manu’s AirPods Pro #2"))
    menu_sim.addAction(act_sim_airpods)

    act_sim_headphones = QAction("🎧 Over-Ear Headphones (Pop-up)", menu_sim)
    act_sim_headphones.triggered.connect(lambda: device_service.trigger_simulated_device("headphones", "Sony WH-1000XM5"))
    menu_sim.addAction(act_sim_headphones)

    act_sim_speaker = QAction("🔊 Bluetooth Speaker (Pop-up)", menu_sim)
    act_sim_speaker.triggered.connect(lambda: device_service.trigger_simulated_device("speaker", "Zeb SoundMX"))
    menu_sim.addAction(act_sim_speaker)

    act_sim_iem = QAction("🎵 In-Ear Monitors / DAC (Pop-up)", menu_sim)
    act_sim_iem.triggered.connect(lambda: device_service.trigger_simulated_device("iem", "Moondrop Chu II / Fiio DAC"))
    menu_sim.addAction(act_sim_iem)

    tray_menu.addSeparator()

    act_quit = QAction("✕  Exit", tray_menu)
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
