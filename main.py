"""
Hardware Notch Desktop Overlay for Windows 11/10
Main Entry Point, System Tray Icon, and Application Lifecycle.
"""

import sys
import os

from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import (
    QIcon, QPixmap, QPainter, QColor, QPen,
    QBrush, QAction, QGuiApplication
)

from services.media_service import MediaService
from services.system_service import SystemService
from services.device_listener import DeviceService
from services.autostart_service import is_autostart_enabled, set_autostart
from ui.island_widget import DynamicIslandWidget


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

    island = DynamicIslandWidget(media_service, system_service, device_service)
    # Island starts hidden; it shows itself when music plays or a notification arrives
    island.hide()

    media_service.start()
    system_service.start()
    device_service.start()

    # ── System Tray ──────────────────────────────────────────────

    # ── System Tray ──────────────────────────────────────────────
    tray_icon = QSystemTrayIcon(create_tray_icon(), app)
    app.setWindowIcon(create_tray_icon())
    tray_icon.setToolTip("Hardware Notch Overlay")

    # Ensure autostart is enabled by default if not set yet
    if not is_autostart_enabled():
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

    act_toggle = QAction("⤢  Expand / Collapse  (Alt+Space)", tray_menu)
    act_toggle.triggered.connect(island.toggle_expanded)
    tray_menu.addAction(act_toggle)

    act_center = QAction("⊙  Recenter Notch", tray_menu)
    act_center.triggered.connect(lambda: island._apply_geometry_for_state(island._island_state, animate=True))
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

    app.aboutToQuit.connect(media_service.stop)
    app.aboutToQuit.connect(system_service.stop)
    app.aboutToQuit.connect(device_service.stop)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
