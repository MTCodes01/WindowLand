<div align="center">

# 🏝️ Dynamic Island for Windows
### An Organic, Curvy Hardware Notch Overlay for Windows 10 & 11

[![Platform](https://img.shields.io/badge/Platform-Windows%2010%20%7C%2011-0078D6?style=for-the-badge&logo=windows)](https://github.com)
[![FPS](https://img.shields.io/badge/Animation-60%20FPS-FFD600?style=for-the-badge)](#)
[![Build](https://img.shields.io/badge/Build-Standalone%20EXE-FF8C00?style=for-the-badge)](#)

*An ultra-compact, hardware-inspired notch sitting seamlessly flush against your top monitor bezel (`y = 0`).*

</div>

---

## ✨ Overview

**Dynamic Island for Windows** brings a fluid, macOS/iOS-inspired interactive notch directly to your Windows desktop. Engineered with anti-aliased custom vector graphics, 60 FPS ambient animations, and intelligent full-screen awareness, it stays out of your way until you need it—and looks effortless when you do.

---

## 🚀 Key Features

### 🎛️ Bespoke Vector Playback Controls
* **Zero System Emojis:** Every control is drawn using crisp, anti-aliased vector geometry—eliminating inconsistent OS emoji rendering.
* **Golden Capsule Play/Pause:** A smooth capsule pill (`58×34px`) styled with a warm gold gradient (`#FFD600` → `#FFAC00`) and centered solid black vector glyphs (`▶` / `❚❚`).
* **Frosted Glass Secondary Pills:** Previous and Next track controls rendered as dark translucent glass pills (`42×30px`) with sharp white vector icons (`|◀` and `▶|`).

### 🌊 60 FPS Living Gradient Mesh
* **Dynamic Liquid Flow:** Powered by `_gradient_shift`, an ambient mesh gradient continuously undulates across the canvas at a locked 60 FPS, creating an ethereal, living light backdrop beneath the frosted album artwork.

### 🎵 26-Bar High-Resolution Audio Visualizer
* **Musical Waveform Physics:** 26 precision vertical bars span the center of the media card, driven by multi-frequency response physics (punchy bass/mids and harmonic treble flutter).
* **Golden-Amber Caps:** Topped with glowing gradient caps (`#FFEA33` → `#FF8C00`) for clear, at-a-glance rhythmic feedback.

### 🧹 Distraction-Free Minimalist UI
* **Zero Unwanted Labels:** Completely strips away clutter like `"SPOTIFY"`, `"NOW PLAYING"`, `"MEDIA"`, or raw package names.
* **Streamlined Header:** Displays only essential glanceable info (**Time** and **Battery**), removing redundant status dots and extra icons.

### 🖱️ Fluid Hover-to-Expand Interaction
* **Instant Access:** Hover your cursor over the top-bezel notch to smoothly expand the interactive media dashboard.
* **Smart Auto-Retract:** Move the cursor away to automatically collapse after `450ms`, or press **`Esc`** to dismiss immediately.

### 🎧 Apple iOS Style Accessory Connection Pop-up
* **Automatic Hardware Recognition:** Real-time CoreAudio background detection recognizes external playback devices immediately upon connection.
* **Multi-Category Dynamic Pop-ups:**
  * **AirPods & TWS Earbuds:** Displays a 3D Apple-style white open charging case with earbuds and glowing status LED.
  * **Over-Ear Headphones:** Renders sleek anodized overhead headphones (Sony XM4/XM5, Bose, AirPods Max).
  * **Bluetooth Speakers:** Renders woven fabric cylindrical speaker with passive bass radiators (JBL, SoundMX, Marshall).
  * **Audiophile IEMs & DACs:** Displays crystal-clear resin monitor shells with braided silver cable and 3.5mm gold jack (Moondrop, Tangzu, Fiio).
* **Authentic iOS Modal Sheet:** Rounded card (`border-radius: 28px`), pure white surface, bold title, subtitle, close button (`×`), and signature blue Apple pill button (`"Done"`).
* **Spring Animation & Smart Auto-Dismiss:** Fluid slide-in easing, 5-second auto-dismiss with hover pause, and synchronous Dynamic Island notch glow.

### ⚙️ Standalone & System-Integrated
* **Single Windowless Binary:** Compiled as a lightweight standalone executable (`dist/DynamicIsland.exe`) with no console clutter.
* **Silent Windows Auto-Start:** Registers cleanly to `HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Run` for seamless background startup on boot.
* **Context-Aware Visibility:**
  * **Auto-Hide:** Remains completely invisible when idle; wakes smoothly when media plays or notifications arrive.
  * **Full-Screen Suppression:** Automatically hides during full-screen games (DirectX/Vulkan) and videos (YouTube, Netflix, VLC).
  * **Multi-Monitor Ready:** Dynamically recalculates position and auto-centers when displays or screen resolutions change.
* **System Tray Controls:** Right-click the tray icon anytime to toggle *Start with Windows*, recenter the notch, trigger shortcuts, or exit.

---

## 📦 Quick Start

1. **Download** the latest release (`DynamicIsland.exe`).
2. **Run** `dist/DynamicIsland.exe` — the notch will automatically anchor to the top center of your primary display.
3. **Play Music** in your favorite media player (Spotify, browser, local player) to see the island come alive.
4. **Customize** startup behavior or recenter anytime via the **System Tray** icon.

---

## ⌨️ Controls & Shortcuts

| Action | Trigger |
| :--- | :--- |
| **Expand Dashboard** | Hover cursor over the top notch |
| **Collapse Dashboard** | Move cursor away (`450ms` delay) or press `Esc` |
| **Play / Pause / Skip** | Click the vector controls inside the expanded card |
| **Settings & Exit** | Right-click the **Dynamic Island** icon in the Windows System Tray |

---

## 👨‍💻 Developer

Crafted with precision by **pase**.
