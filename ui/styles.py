"""
Hardware Notch Overlay Visual Styling & Theme Constants.
Ultra-compact curvy hardware notch design sitting flush at the top bezel (y = 0).
Soft organic curvature with zero unwanted text clutter.
"""

from PyQt6.QtGui import QColor, QFont

# Geometry Constants for Compact Curvy Top Notch
COMPACT_IDLE_WIDTH = 200
COMPACT_MUSIC_WIDTH = 320
COMPACT_HEIGHT = 34

TOAST_WIDTH = 380
TOAST_HEIGHT = 48

EXPANDED_WIDTH = 420
EXPANDED_HEIGHT = 180

NOTCH_RADIUS_TOP = 14.0   # Curvy flaring inverse fillets at top bezel
NOTCH_RADIUS_BOT = 22.0   # Curvy soft bottom corners
EXPANDED_RADIUS = 28.0    # Curvy bottom corners in expanded mode

# Base Theme Colors
COLOR_BEZEL = QColor("#0A0A0E")
COLOR_CANVAS = QColor("#08080C")
COLOR_TEXT_PRIMARY = QColor("#FFFFFF")
COLOR_TEXT_SECONDARY = QColor("#A0A0AB")
COLOR_TEXT_MUTED = QColor("#666672")
COLOR_ACCENT_YELLOW = QColor("#FFD600")

# Dynamic Glow Palettes
GLOW_STATES = {
    "idle": {
        "color1": QColor(255, 179, 71),
        "color2": QColor(255, 204, 51),
        "opacity": 0.22,
        "name": "Amber"
    },
    "music": {
        "color1": QColor(255, 214, 0),
        "color2": QColor(255, 107, 0),
        "opacity": 0.32,
        "name": "Amber Gold"
    },
    "notification": {
        "color1": QColor(86, 204, 242),
        "color2": QColor(47, 128, 237),
        "opacity": 0.35,
        "name": "Cyan"
    },
    "reminders": {
        "color1": QColor(142, 45, 226),
        "color2": QColor(74, 0, 224),
        "opacity": 0.35,
        "name": "Violet"
    },
    "success": {
        "color1": QColor(17, 153, 142),
        "color2": QColor(56, 239, 125),
        "opacity": 0.35,
        "name": "Emerald"
    }
}

# Typography – smooth, subpixel-rendered fonts
def _apply_smooth(font: QFont) -> QFont:
    """Apply maximum subpixel antialiasing and hinting to a font."""
    font.setStyleStrategy(
        QFont.StyleStrategy.PreferAntialias |
        QFont.StyleStrategy.PreferQuality
    )
    font.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
    return font

def get_microlabel_font():
    font = QFont("Segoe UI", 8, QFont.Weight.DemiBold)
    font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.6)
    return _apply_smooth(font)

def get_display_font(size=12):
    font = QFont("Segoe UI", size, QFont.Weight.Bold)
    return _apply_smooth(font)

def get_subtext_font(size=10):
    font = QFont("Segoe UI", size, QFont.Weight.Normal)
    return _apply_smooth(font)

# Modern Curvy Dark Glass QSS Stylesheet
DASHBOARD_STYLESHEET = """
QToolTip {
    background-color: #14141A;
    color: #FFFFFF;
    border: 1px solid rgba(255, 255, 255, 0.15);
    border-radius: 8px;
    padding: 3px 6px;
    font-family: 'Segoe UI';
    font-size: 11px;
}

QPushButton.action-pill {
    background-color: rgba(25, 25, 34, 0.70);
    color: #D8D8DF;
    border: 1px solid rgba(255, 255, 255, 0.10);
    border-radius: 12px;
    padding: 2px 6px;
    font-family: 'Segoe UI';
    font-size: 10px;
    font-weight: 600;
}

QPushButton.action-pill:hover {
    background-color: rgba(50, 50, 68, 0.85);
    color: #FFFFFF;
    border: 1px solid rgba(255, 255, 255, 0.25);
}

QPushButton.action-pill:checked {
    background-color: rgba(255, 214, 0, 0.20);
    color: #FFD600;
    border: 1px solid #FFD600;
}

/* Curvy Reference Playback Buttons */
QPushButton.media-control-primary {
    background-color: #FFD600;
    color: #0A0A0C;
    border: none;
    border-radius: 16px;
    font-size: 13px;
    font-weight: bold;
    padding: 0px;
}

QPushButton.media-control-primary:hover {
    background-color: #FFE24D;
}

QPushButton.media-control-primary:pressed {
    background-color: #E6C000;
}

QPushButton.media-control-secondary {
    background-color: rgba(255, 255, 255, 0.08);
    color: #E0E0E6;
    border: 1px solid rgba(255, 255, 255, 0.10);
    border-radius: 14px;
    font-size: 11px;
    font-weight: bold;
}

QPushButton.media-control-secondary:hover {
    background-color: rgba(255, 255, 255, 0.18);
    color: #FFFFFF;
    border: 1px solid rgba(255, 255, 255, 0.25);
}

QPushButton.media-control-secondary:pressed {
    background-color: rgba(255, 255, 255, 0.26);
}
"""
