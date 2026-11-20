"""
High-Resolution Dynamic Audio Visualizer Component.
Faithfully renders 26 organic, responsive waveform bars with musical frequency physics,
logarithmic FFT simulation, asymmetric attack/decay ballistics, and rounded pill caps.
"""

import math
import random
from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QTimer, QRectF
from PyQt6.QtGui import QPainter, QColor, QBrush, QLinearGradient


class AudioVisualizerWidget(QWidget):
    """
    Fluid, organic music visualizer with multi-frequency response,
    logarithmic FFT magnitudes, asymmetric attack/decay smoothing,
    and album-art reactive dynamic gradients.
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
        self._bar_multipliers = [random.uniform(0.78, 1.25) for _ in range(self.num_bars)]
        # Logarithmic frequency spacing across 26 bands (sub-bass 30Hz to brilliance 16kHz)
        self._frequencies = [
            2.0 + 5.5 * math.log10(1.0 + (i / float(self.num_bars)) * 9.0)
            for i in range(self.num_bars)
        ]
        self._time = 0.0
        self._peak_fn = None
        self._smoothed_peak = 0.0
        self._beat_energy = 0.0

        # Minimalist studio waveform (Crisp white gradients matching Apple Music)
        self._color_active_top = QColor(255, 255, 255, 245)
        self._color_active_bottom = QColor(255, 255, 255, 160)
        self._color_inactive = QColor(255, 255, 255, 30)

        # 60 FPS animation timer
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._update_physics)
        self._timer.start()

        total_w = int(math.ceil(self.num_bars * self.bar_width + (self.num_bars - 1) * self.bar_spacing))
        self.setFixedWidth(total_w)
        self.setFixedHeight(30)

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
        self.update()

    def set_peak_provider(self, fn):
        """Connects a live hardware peak metering function."""
        self._peak_fn = fn

    def set_playing(self, playing: bool):
        self._is_playing = playing
        if not playing:
            mid = (self.num_bars - 1) / 2.0
            sigma = self.num_bars / 3.4
            for i in range(self.num_bars):
                env = math.exp(-0.5 * ((i - mid) / sigma) ** 2)
                self._target_heights[i] = max(0.06, 0.18 * env)

    def _update_physics(self):
        changed = False

        # Live audio peak from hardware
        live_peak = 0.0
        if self._peak_fn:
            try:
                live_peak = self._peak_fn()
            except Exception:
                live_peak = 0.0

        # Transient / Kick beat detector: captures drum hits and rhythm energy
        delta = max(0.0, live_peak - self._smoothed_peak)
        if delta > 0.012:
            self._beat_energy = min(1.0, self._beat_energy + delta * 9.5)
        else:
            self._beat_energy *= 0.85  # Snappy punchy decay for tight beat response

        # Fast attack, smooth decay for master audio peak
        if live_peak > self._smoothed_peak:
            self._smoothed_peak += (live_peak - self._smoothed_peak) * 0.60
        else:
            self._smoothed_peak += (live_peak - self._smoothed_peak) * 0.14

        # Non-linear AGC perceptual volume
        if self._smoothed_peak > 0.002:
            perceptual_vol = min(1.0, math.pow(self._smoothed_peak, 0.35) * 1.80)
        else:
            perceptual_vol = 0.0

        # Dynamic pace: animation speed accelerates with beat energy & loudness!
        pace_factor = 0.10 + self._beat_energy * 0.20 + perceptual_vol * 0.10
        self._time += pace_factor

        mid = (self.num_bars - 1) / 2.0
        sigma = self.num_bars / 3.0

        for i in range(self.num_bars):
            envelope = math.exp(-0.5 * ((i - mid) / sigma) ** 2)

            if self._is_playing:
                ratio = i / float(max(1, self.num_bars - 1))
                f = self._frequencies[i]
                
                # Multi-band frequency dynamics with rich jagged contrasts:
                if ratio < 0.30:
                    # Bass band: massive kick bounce + sub-bass oscillation
                    w1 = math.sin(self._time * 4.2 + self._phases[i])
                    w2 = math.cos(self._time * 2.1 + i * 0.8)
                    band_val = self._beat_energy * 0.70 + perceptual_vol * 0.50 * (w1 * 0.5 + w2 * 0.5 + 1.0)
                elif ratio < 0.72:
                    # Mid band: vocal/melody rhythm
                    w1 = math.sin(self._time * f * 1.1 + self._phases[i])
                    w2 = math.cos(self._time * (f * 1.6) + i * 0.55)
                    band_val = perceptual_vol * 0.80 * ((w1 + w2 + 2.0) / 4.0) + self._beat_energy * 0.35
                else:
                    # Treble band: shimmering hi-hats and cymbals
                    w1 = math.sin(self._time * (f * 2.0) + self._phases[i] * 2.2)
                    flicker = math.sin(self._time * 16.0 + i * 1.3)
                    band_val = perceptual_vol * 0.70 * ((w1 + flicker + 2.0) / 4.0) + self._beat_energy * 0.25

                # Lively bar-to-bar jagged dynamics (creates crisp dancing contrast across bars)
                bar_contrast = self._bar_multipliers[i] * (0.65 + 0.45 * math.sin(self._time * 3.0 + i * 1.7))
                
                if perceptual_vol > 0.03:
                    norm = 0.12 + 0.88 * envelope * (band_val * bar_contrast)
                else:
                    # Gentle idle wave when quiet
                    norm = 0.12 + 0.30 * envelope * (math.sin(self._time * 2.2 + i * 0.45) + 1.0) / 2.0

                self._target_heights[i] = max(0.12, min(1.0, norm))
            else:
                self._target_heights[i] = max(0.08, 0.20 * envelope)

            diff = self._target_heights[i] - self._heights[i]
            if abs(diff) > 0.003:
                # Fast explosive attack (0.82) for punchy snap, silky decay (0.20)
                lerp_speed = 0.82 if diff > 0 else 0.20
                self._heights[i] += diff * lerp_speed
                changed = True

        if changed or self._is_playing:
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        h_max = float(self.height())
        rx = 1.25

        for i in range(self.num_bars):
            val = self._heights[i]
            bar_h = max(4.0, val * (h_max - 2))
            x = i * (self.bar_width + self.bar_spacing)
            y = (h_max - bar_h) / 2.0

            rect = QRectF(x, y, self.bar_width, bar_h)

            if self._is_playing:
                grad = QLinearGradient(x, y, x, y + bar_h)
                grad.setColorAt(0.0, self._color_active_top)
                grad.setColorAt(1.0, self._color_active_bottom)
                painter.setBrush(QBrush(grad))
            else:
                painter.setBrush(QBrush(self._color_inactive))

            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(rect, rx, rx)
