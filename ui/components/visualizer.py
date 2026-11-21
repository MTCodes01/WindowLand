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
    - Dynamic Automatic Gain Control (AGC) with musical contrast expansion
    - Floating peak-hold cap indicators that drift down with gravity
    - Asymmetric attack/decay ballistics (explosive rise, silky organic decay)
    - Album-art reactive dynamic linear gradients
    - Automatic bar centering across variable widget widths
    """
    def __init__(self, num_bars: int = 22, bar_width: float = 2.5, bar_spacing: float = 2.5, parent=None):
        super().__init__(parent)
        self.num_bars = num_bars
        self.bar_width = bar_width
        self.bar_spacing = bar_spacing
        self._is_playing = False
        self._has_audio = False
        self._audio_silent_ticks = 0

        self._heights = [0.10] * self.num_bars
        self._target_heights = [0.10] * self.num_bars
        self._peak_caps = [0.10] * self.num_bars
        self._cap_hold = [0] * self.num_bars

        # Dynamic Automatic Gain Control (AGC) state
        self._gain_peak = 0.35

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
                self._target_heights[i] = max(0.04, 0.14 * env)
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
                        self._has_audio = True
                        self._audio_silent_ticks = 0

                        # Dynamic Automatic Gain Control (AGC)
                        # Fast attack (0.35) to absorb loud peaks without clipping;
                        # Gentle decay (0.015) so quiet acoustic or vocal sections expand naturally.
                        if max_mag > self._gain_peak:
                            self._gain_peak += (max_mag - self._gain_peak) * 0.35
                        else:
                            self._gain_peak += (max_mag - self._gain_peak) * 0.015

                        gain = 1.0 / max(0.12, min(1.0, self._gain_peak))

                        for i in range(self.num_bars):
                            raw_val = bands[i] * gain
                            # Perceptual contrast expansion
                            curved = math.pow(max(0.0, min(1.0, raw_val)), 0.95)
                            norm = max(0.04, min(1.0, curved))
                            self._target_heights[i] = norm

                            # Floating peak cap tracking
                            if norm >= self._peak_caps[i]:
                                self._peak_caps[i] = norm
                                self._cap_hold[i] = 12
                            else:
                                if self._cap_hold[i] > 0:
                                    self._cap_hold[i] -= 1
                                else:
                                    self._peak_caps[i] = max(norm, self._peak_caps[i] - 0.028)
                    else:
                        self._audio_silent_ticks += 1
                        if self._audio_silent_ticks > 40:
                            self._has_audio = False
            except Exception:
                has_real_data = False

        # 2. Ambient physics fallback if loopback is quiet or initializing
        if not has_real_data:
            self._time += 0.08
            mid = (self.num_bars - 1) / 2.0
            sigma = self.num_bars / 3.2
            is_active = self._is_playing or self._has_audio

            for i in range(self.num_bars):
                envelope = math.exp(-0.5 * ((i - mid) / sigma) ** 2)
                if is_active:
                    f = self._frequencies[i]
                    w = math.sin(self._time * f + self._phases[i])
                    self._target_heights[i] = max(0.06, min(0.65, 0.10 + 0.40 * envelope * (w + 1.0) / 2.0))
                else:
                    self._target_heights[i] = max(0.04, 0.12 * envelope)

                self._peak_caps[i] = max(self._target_heights[i], self._peak_caps[i] - 0.02)

        # 3. Asymmetric ballistics: explosive rise (0.86), silky organic decay (0.24)
        for i in range(self.num_bars):
            diff = self._target_heights[i] - self._heights[i]
            if abs(diff) > 0.001:
                lerp_speed = 0.86 if diff > 0 else 0.24
                self._heights[i] += diff * lerp_speed
                changed = True

        if changed or self._is_playing or has_real_data or self._has_audio:
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        w_widget = float(self.width())
        h_max = float(self.height())
        rx = 1.25  # Rounded pill caps

        # Dynamically center bars within the widget's available width
        total_bars_w = self.num_bars * self.bar_width + (self.num_bars - 1) * self.bar_spacing
        start_x = max(0.0, (w_widget - total_bars_w) / 2.0)

        is_active = self._is_playing or self._has_audio
        min_bar_h = 3.0 if is_active else 2.5
        usable_h = max(2.0, h_max - min_bar_h - 4.0)

        for i in range(self.num_bars):
            val = self._heights[i]
            bar_h = min_bar_h + val * usable_h
            x = start_x + i * (self.bar_width + self.bar_spacing)
            y = (h_max - bar_h) / 2.0

            rect = QRectF(x, y, self.bar_width, bar_h)

            if is_active and val > 0.06:
                grad = QLinearGradient(x, y, x, y + bar_h)
                grad.setColorAt(0.0, self._color_active_top)
                grad.setColorAt(1.0, self._color_active_bottom)
                painter.setBrush(QBrush(grad))
            else:
                painter.setBrush(QBrush(self._color_inactive))

            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(rect, rx, rx)

            # Floating Studio Peak Cap Indicator (Apple Music / Studio EQ signature)
            if is_active and val > 0.10:
                cap_val = self._peak_caps[i]
                cap_h = min_bar_h + cap_val * usable_h
                cap_y = max(1.0, (h_max - cap_h) / 2.0 - 2.5)
                cap_rect = QRectF(x, cap_y, self.bar_width, 1.4)
                painter.setBrush(QBrush(self._color_cap))
                painter.drawRoundedRect(cap_rect, 0.7, 0.7)
