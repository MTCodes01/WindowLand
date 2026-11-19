"""
High-Resolution Dynamic Audio Visualizer Component.
Faithfully renders 26 organic, responsive waveform bars with musical frequency physics.
"""

import math
import random
from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QTimer, QRectF
from PyQt6.QtGui import QPainter, QColor, QBrush, QLinearGradient


class AudioVisualizerWidget(QWidget):
    """
    Fluid, organic music visualizer with multi-frequency response,
    dynamic peak heights, and golden amber gradients.
    """
    def __init__(self, num_bars=26, bar_width=3, bar_spacing=3, parent=None):
        super().__init__(parent)
        self.num_bars = num_bars
        self.bar_width = bar_width
        self.bar_spacing = bar_spacing
        self._is_playing = False

        self._heights = [0.12] * self.num_bars
        self._target_heights = [0.12] * self.num_bars
        self._phases = [random.uniform(0, 2 * math.pi) for _ in range(self.num_bars)]
        self._frequencies = [random.uniform(2.5, 6.0) for _ in range(self.num_bars)]
        self._time = 0.0

        # Golden Amber Gradients
        self._color_active_top = QColor("#FFEA33")
        self._color_active_bottom = QColor("#FF8C00")
        self._color_inactive = QColor(255, 255, 255, 32)

        # 60 FPS animation timer
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._update_physics)
        self._timer.start()

        total_w = self.num_bars * self.bar_width + (self.num_bars - 1) * self.bar_spacing
        self.setFixedWidth(total_w)
        self.setFixedHeight(30)

    def set_playing(self, playing: bool):
        self._is_playing = playing
        if not playing:
            mid = (self.num_bars - 1) / 2.0
            sigma = self.num_bars / 3.4
            for i in range(self.num_bars):
                env = math.exp(-0.5 * ((i - mid) / sigma) ** 2)
                self._target_heights[i] = max(0.08, 0.22 * env)

    def _update_physics(self):
        self._time += 0.07
        changed = False

        mid = (self.num_bars - 1) / 2.0
        sigma = self.num_bars / 3.4

        for i in range(self.num_bars):
            if self._is_playing:
                # Bell-shaped envelope centered in middle, higher on bass/mids
                envelope = math.exp(-0.5 * ((i - mid) / sigma) ** 2)
                
                # Composite multi-frequency waves for natural audio fluctuation
                w1 = math.sin(self._time * self._frequencies[i] + self._phases[i])
                w2 = math.cos(self._time * (self._frequencies[i] * 0.65) + self._phases[i] * 1.6)
                w3 = math.sin(self._time * 1.8 + i * 0.4)
                
                combo = (w1 * 0.50 + w2 * 0.30 + w3 * 0.20 + 1.0) / 2.0
                norm = 0.14 + 0.86 * envelope * (0.35 + 0.65 * combo)
                self._target_heights[i] = max(0.10, min(1.0, norm))
            else:
                envelope = math.exp(-0.5 * ((i - mid) / sigma) ** 2)
                self._target_heights[i] = max(0.08, 0.22 * envelope)

            diff = self._target_heights[i] - self._heights[i]
            if abs(diff) > 0.005:
                # Snappy attack, smooth decay
                lerp_speed = 0.28 if diff > 0 else 0.18
                self._heights[i] += diff * lerp_speed
                changed = True

        if changed or self._is_playing:
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        h_max = float(self.height())
        radius = self.bar_width / 2.0

        for i in range(self.num_bars):
            val = self._heights[i]
            bar_h = max(3.5, val * (h_max - 2))
            x = i * (self.bar_width + self.bar_spacing)
            y = (h_max - bar_h) / 2.0

            rect = QRectF(x, y, self.bar_width, bar_h)

            if self._is_playing and val > 0.12:
                grad = QLinearGradient(x, y, x, y + bar_h)
                grad.setColorAt(0.0, self._color_active_top)
                grad.setColorAt(1.0, self._color_active_bottom)
                painter.setBrush(QBrush(grad))
            else:
                painter.setBrush(QBrush(self._color_inactive))

            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(rect, radius, radius)
