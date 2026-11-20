# WinDin Dynamic Island — UI/UX Updates & Visual Polish Specification

This document outlines targeted visual fixes for the current expanded music player layout alongside the new UI states, micro-interactions, and rendering upgrades for `ui/island_widget.py`, `ui/styles.py`, and `ui/components/`.

---

## 1. Immediate Visual & Typography Fixes (Current Expanded Player)

Based on your current build (`6:39 PM` expanded state), apply these layout and rendering refinements to eliminate clipping and improve visual hierarchy:

1. **Title & Artist Descender Clipping Fix**:
   * **Issue**: In the expanded music card, the bounding box height for the track title (`"Pampa Ganapathy"`) and artist label (`"Vidyasagar"`) clips the bottom descenders of `"y"` and `"g"`.
   * **Fix**: Increase the `QFontMetrics` line height / `QRect` vertical allocation by `+4 px` (from `18 px` to `22 px` for the title, and `15 px` to `19 px` for the subtitle) and enable `Qt.TextFlag.TextSingleLine` with `Qt.AlignmentFlag.AlignVCenter`.
2. **Album Art Rounded Squircle Clipping**:
   * **Issue**: The album cover currently renders with sharp `90°` corners inside a heavily rounded inner card.
   * **Fix**: Apply a `QPainterPath.addRoundedRect(..., 10.0, 10.0)` clip path before `drawPixmap()`, plus a subtle `1 px` `rgba(255, 255, 255, 0.14)` inner specular border to match Apple Music's card framing.
3. **Interactive Scrubbing & Hover Glow**:
   * **Upgrade**: Expand the hit-test area of the `00:52 — 05:11` timeline bar to `14 px` vertically. On mouse hover (`underMouse()`), thicken the track from `3 px` to `5 px` and render a `10 px` glowing thumb circle (`#FFC107`) that tracks cursor scrubbing in real time.
4. **Top Header Status Strip Balance**:
   * **Upgrade**: Next to the `⚡ 100%` laptop battery indicator in the top-right bezel ear, reserve a dynamic slot for **Phone Battery (`📱 84%`)** and **Hardware Privacy LEDs** (`6 px` glowing orange mic dot / green camera dot) when active.

---

## 2. Dynamic Visual & Shader Upgrades (`QPainter` Pipeline)

### 2.1 Album-Art Reactive Aurora Plasma ($\mathbf{V}_1, \mathbf{V}_2$)
* **Current Behavior**: Your golden-amber and violet aurora plasma looks great on warm covers, but remains static across different tracks.
* **UI Update**: Extract the primary vibrant swatch and secondary muted swatch from the active album art thumbnail (`MediaService`) and smoothly interpolate the `QRadialGradient` color stops of $\mathbf{V}_1(t)$ and $\mathbf{V}_2(t)$ over **400 ms** (`QEasingCurve.Type.InOutCubic`) whenever the song changes.
* **Accent Synchronization**: Bind the 26-bar equalizer gradient, scrub bar fill, and center Play/Pause pill (`#FFC107` in your screenshot) to the extracted vibrant cover accent (with an automatic luminance floor so dark covers still produce readable, bright controls).

### 2.2 True Audio-Reactive Equalizer Ballistics
* Drive the 26-bar center equalizer (`visualizer.py`) using live 26-band logarithmic FFT magnitudes with asymmetric attack/decay smoothing (`attack = 0.65`, `decay = 0.82`) and rounded pill caps (`rx = 1.1 px`), keeping the symmetrical center-weighted envelope seen in your screenshot.

---

## 3. New Dynamic Island UI States & Geometry Matrix

Add these four new morphing states to your existing geometry state machine in `ui/styles.py` and `ui/island_widget.py`:

| UI State | Dimensions ($w \times h$) | Radii ($r_{\text{top}} / r_{\text{bot}}$) | Visual Layout & Interactive Elements |
| :--- | :--- | :--- | :--- |
| **`osd_hud`** *(Volume / Brightness / Caps)* | `220 × 36 px` | `18 / 18 px` | Compact liquid-glass pill inside the top bezel; left glyph icon, animated horizontal fill bar with specular sheen, right percentage readout. Auto-collapses after `1.8 s`. |
| **`call_live`** *(Incoming Phone Call)* | `420 × 74 px` | `18 / 24 px` | Left circular caller avatar with pulsing green ring; center caller name + `"iPhone • Incoming Call"` subtitle; right circular **Decline (`#FF3B30`)** and **Answer (`#34C759`)** vector buttons. |
| **`otp_pill`** *(2FA Code Detected)* | `360 × 54 px` | `18 / 20 px` | Left app badge (Messages/WhatsApp); center `"Verification Code: 482 910"` in monospaced tabular numerals; right pill button `"Copied • Paste"` with checkmark transition. |
| **`file_shelf`** *(Drag-and-Drop Tray)* | `460 × 126 px` | `18 / 26 px` | Triggered when dragging files to $y < 40\text{ px}$; dashed luminous drop zone (`rgba(255,255,255,0.22)`), horizontal stack of dragged file icons/thumbnails, and a `"Clear"` pill. |

---

## 4. 3D Accessory Connection Sheet UI Enhancements (`370 × 360 px`)

Upgrade your existing 3D device showcase card with live hardware telemetry:
1. **Segmented Battery Ring & Percentage Badge**:
   * Directly below the floating 3D hero model (`175 × 175 px`) and contact shadow, render a frosted pill badge showing a circular battery arc (`#38EF7D` above 20%, `#FF453A` below 20%) alongside exact percentage text (`"Battery • 86%"`).
2. **Inline Audio Routing Pill**:
   * Add a secondary compact capsule above the `"Done"` button allowing one-click switching between connected playback outputs (`AirPods Pro` ↔ `PC Speakers`) with a smooth slide indicator.

---

## 5. Micro-Interactions & Motion Polish

* **Directional Tilt on Hover**: Apply a subtle `±1.5°` perspective/offset shift to the inner content card (`QPainter.translate`) when the cursor moves across the expanded `500 × 170 px` surface, reinforcing the physical "liquid glass" depth.
* **Sub-2px Download Progress Hairline**: When an active download is detected in `~/Downloads`, stroke a glowing `2 px` accent path strictly along the bottom quadratic Bézier curve ($Q_0 \to Q_2$) proportional to completion percentage (`0.0 → 1.0`).
* **Smart Auto-Hide / Peek Mode**: Add a `4 px` translucent tab handle at $y = 0$ when "Auto-Hide Notch" is enabled in tray settings, expanding smoothly via `OutBack` spring physics (`s = 1.70158`) on cursor hover.