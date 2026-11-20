"""
High-Resolution Studio Dynamic Audio Visualizer Component.
Faithfully renders 22 organic, responsive waveform bars with real-time 
WASAPI loopback FFT spectrum analysis, floating peak hold caps, 
asymmetric attack/decay ballistics, and album-art reactive dynamic gradients.
"""

import math
import random
from typing import Optional, Callable, Tuple, List
from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QTimer, QRectF
from PyQt6.QtGui import QPainter, QColor, QBrush, QLinearGradient, QPen


class AudioVisualizerWidget(QWidget):
    """
    Studio-grade music visualizer driven by real-time hardware audio spectrum (FFT).
    Features:
    - 22 Logarithmic frequency response bars (35 Hz sub-bass to 16 kHz air)
    - Real-time WASAPI audio loopback synchronization
    - Floating peak-hold cap indicators that drift down with gravity
    - Asymmetric attack/decay ballistics (explosive rise, silky organic decay)
    - Fluid album-art reactive dynamic linear gradients
    """
    def __init__(self, num_bars: int = 22, bar_width: float = 2.5, bar_spacing: float = 2.5, parent=None):
        super().__init__(parent)
        self.num_bars = num_bars
        self.bar_width = bar_width
        self.bar_spacing = bar_spacing
        self._is_playing = False

        self._heights = [0.12] * self.num_bars
        self._target_heights = [0.12] * self.num_bars
        self._peak_caps = [0.12] * self.num_bars
        self._cap_hold = [0] * self.num_bars

        # Ambient fallback phases and frequencies
        self._phases = [random.uniform(0, 2 * math.pi) for _ in range(self.num_bars)]
        self._frequencies = [
            2.0 + 5.5 * math.log10(1.0 + (i / float(self.num_bars)) * 9.0)
            for i in range(self.num_bars)
        ]
        self._time = 0.0

        # Spectrum / Peak data providers
        self._spectrum_fn: Optional[Callable[[], Tuple[List[float], List[float]]]] = None
        self._peak_fn: Optional[Callable[[], float]] = None

        # Studio Styling & Color Gradients
        self._color_active_top = QColor(255, 255, 255, 245)
        self._color_active_bottom = QColor(255, 255, 255, 160)
        self._color_cap = QColor(255, 255, 255, 230)
        self._color_inactive = QColor(255, 255, 255, 30)

        # 60 FPS animation timer
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._update_physics)
        self._timer.start()

        total_w = int(math.ceil(self.num_bars * self.bar_width + (self.num_bars - 1) * self.bar_spacing))
        self.setFixedWidth(total_w)
        self.setFixedHeight(28)

    def set_spectrum_provider(self, fn: Callable[[], Tuple[List[float], List[float]]]):
        """Connects real-time hardware WASAPI loopback FFT spectrum provider."""
        self._spectrum_fn = fn

    def set_peak_provider(self, fn: Callable[[], float]):
        """Connects fallback volume peak provider."""
        self._peak_fn = fn

    def set_accent_colors(self, color_top: QColor, color_bottom: QColor):
        """Dynamically binds equalizer colors to extracted album swatches with studio white blending."""
        r1 = int(255 * 0.65 + color_top.red() * 0.35)
        g1 = int(255 * 0.65 + color_top.green() * 0.35)
        b1 = int(255 * 0.65 + color_top.blue() * 0.35)
        self._color_active_top = QColor(r1, g1, b1, 245)

        r2 = int(255 * 0.55 + color_bottom.red() * 0.45)
        g2 = int(255 * 0.55 + color_bottom.green() * 0.45)
        b2 = int(255 * 0.55 + color_bottom.blue() * 0.45)
        self._color_active_bottom = QColor(r2, g2, b2, 175)

        self._color_cap = QColor(
            min(255, int(r1 * 1.1)),
            min(255, int(g1 * 1.1)),
            min(255, int(b1 * 1.1)),
            240
        )
        self.update()

    def set_playing(self, playing: bool):
        self._is_playing = playing
        if not playing:
            mid = (self.num_bars - 1) / 2.0
            sigma = self.num_bars / 3.4
            for i in range(self.num_bars):
                env = math.exp(-0.5 * ((i - mid) / sigma) ** 2)
                self._target_heights[i] = max(0.06, 0.16 * env)
                self._peak_caps[i] = self._target_heights[i]

    def _update_physics(self):
        changed = False
        has_real_data = False

        # 1. Query real-time WASAPI loopback spectrum
        if self._spectrum_fn:
            try:
                bands, caps = self._spectrum_fn()
                if bands and len(bands) >= self.num_bars:
                    max_mag = max(bands)
                    if max_mag > 0.005:
                        has_real_data = True
                        for i in range(self.num_bars):
                            raw_val = bands[i]
                            # Responsive baseline + dynamic range
                            norm = max(0.10, min(1.0, 0.08 + raw_val * 0.92))
                            self._target_heights[i] = norm

                            # Floating peak cap logic
                            if norm >= self._peak_caps[i]:
                                self._peak_caps[i] = norm
                                self._cap_hold[i] = 14
                            else:
                                if self._cap_hold[i] > 0:
                                    self._cap_hold[i] -= 1
                                else:
                                    self._peak_caps[i] = max(norm, self._peak_caps[i] - 0.024)
            except Exception:
                has_real_data = False

        # 2. Ambient physics fallback if loopback is quiet or initializing
        if not has_real_data:
            self._time += 0.08
            mid = (self.num_bars - 1) / 2.0
            sigma = self.num_bars / 3.2

            for i in range(self.num_bars):
                envelope = math.exp(-0.5 * ((i - mid) / sigma) ** 2)
                if self._is_playing:
                    f = self._frequencies[i]
                    w = math.sin(self._time * f + self._phases[i])
                    self._target_heights[i] = max(0.10, min(0.60, 0.12 + 0.35 * envelope * (w + 1.0) / 2.0))
                else:
                    self._target_heights[i] = max(0.06, 0.16 * envelope)

                self._peak_caps[i] = max(self._target_heights[i], self._peak_caps[i] - 0.02)

        # 3. Asymmetric ballistics: instant rise (0.84), silky smooth decay (0.22)
        for i in range(self.num_bars):
            diff = self._target_heights[i] - self._heights[i]
            if abs(diff) > 0.002:
                lerp_speed = 0.84 if diff > 0 else 0.22
                self._heights[i] += diff * lerp_speed
                changed = True

        if changed or self._is_playing or has_real_data:
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        h_max = float(self.height())
        rx = 1.25  # Rounded pill caps

        for i in range(self.num_bars):
            val = self._heights[i]
            bar_h = max(4.0, val * (h_max - 4.0))
            x = i * (self.bar_width + self.bar_spacing)
            y = (h_max - bar_h) / 2.0

            rect = QRectF(x, y, self.bar_width, bar_h)

            if self._is_playing and val > 0.08:
                grad = QLinearGradient(x, y, x, y + bar_h)
                grad.setColorAt(0.0, self._color_active_top)
                grad.setColorAt(1.0, self._color_active_bottom)
                painter.setBrush(QBrush(grad))
            else:
                painter.setBrush(QBrush(self._color_inactive))

            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(rect, rx, rx)

            # Floating Studio Peak Cap Indicator (Apple Music / Studio EQ signature)
            if self._is_playing and val > 0.12:
                cap_val = self._peak_caps[i]
                cap_h = max(4.0, cap_val * (h_max - 4.0))
                cap_y = max(0.0, (h_max - cap_h) / 2.0 - 2.0)
                cap_rect = QRectF(x, cap_y, self.bar_width, 1.4)
                painter.setBrush(QBrush(self._color_cap))
                painter.drawRoundedRect(cap_rect, 0.7, 0.7)
