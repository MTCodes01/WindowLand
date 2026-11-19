# Curvy Hardware Notch Overlay for Windows 11 / 10 🏝

An ultra-compact, organic curvy hardware notch overlay for Windows sitting flush against the top monitor bezel (`y = 0`).

---

## ✨ Features & What's New

### 1. 🎛️ Custom Vector Playback Buttons
* **Zero System Emojis:** Custom vector-drawn playback controls with crisp anti-aliased geometry.
* **Golden Capsule Play/Pause:** Smooth capsule pill (`58x34px`, `#FFD600` to `#FFAC00`) with centered solid black vector play triangle `▶` or pause bars `❚❚`.
* **Glass Secondary Pills:** Previous and Next buttons rendered as dark glass pills (`42x30px`) with sharp white vector glyphs (`|◀` and `▶|`).

### 2. 🌊 Moving Animated Gradient Effect
* **Dynamic Liquid Mesh:** Ambient mesh gradient continuously undulates and drifts across the canvas at 60 FPS (`_gradient_shift`), producing an ethereal living light flow underneath the frosted glass album art.

### 3. 🎵 High-Resolution 26-Bar Audio Visualizer
* **Proper Musical Waveform:** 26 vertical bars spanning the center of the media card with multi-frequency musical physics (responsive bass/mid punch and harmonic flutter) and golden-amber gradient caps (`#FFEA33` to `#FF8C00`).

### 4. 🧹 Ultra-Clean Typography & Zero Clutter
* **Green Dot Removed:** Eliminated the green active dot completely.
* **Top-Right Options Removed:** Cleaned up the expanded header to only display Time and Battery — all extra icons (`🔊 📸 🌙 🎵 ▲`) removed.
* **Zero Unwanted Text:** Completely eliminated all `"SPOTIFY"`, `"NOW PLAYING"`, `"MEDIA"`, and package name strings.

### 5. 🖱️ Hover-to-Expand
* Move your cursor over the notch at the top of your screen to smoothly expand the dashboard.
* Move away to auto-retract after 450ms (or press **`Esc`**).

### 6. 🚀 Standalone Application & Windows Auto-Start
* **Standalone Executable:** Compiled as a single windowless binary: `dist/DynamicIsland.exe`.
* **Automatic Silent Startup:** Automatically registers to `HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Run` so it launches silently in the background on system boot.
* **Auto-Hide:** Stays completely hidden when no music is playing. Automatically pops up when music starts or notifications arrive.
* **Full-Screen Suppression:** Completely hides itself during full-screen games and videos (YouTube, VLC, Netflix, DirectX/Vulkan games).
* **Multi-Monitor & Resolution Awareness:** Auto-centers dynamically when displays or resolutions change.
* **System Tray Control:** Right-click the tray icon to toggle "Start with Windows", recenter, trigger shortcuts, or exit anytime.
