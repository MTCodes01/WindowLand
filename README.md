<div align="center">

# 🏝️ Dynamic Island for Windows
### An Organic, Curvy Hardware Notch Overlay for Windows 10 & 11

[![Platform](https://img.shields.io/badge/Platform-Windows%2010%20%7C%2011-0078D6?style=for-the-badge&logo=windows)](https://github.com)
[![FPS](https://img.shields.io/badge/Animation-60%20FPS-FFD600?style=for-the-badge)](#)
[![Build](https://img.shields.io/badge/Build-Standalone%20EXE-FF8C00?style=for-the-badge)](#)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?style=for-the-badge&logo=python)](#)
[![UI Framework](https://img.shields.io/badge/UI-PyQt6-41CD52?style=for-the-badge&logo=qt)](#)

*An ultra-compact, hardware-inspired notch sitting seamlessly flush against your top monitor bezel (`y = 0`) with fluid morphing states, liquid glass morphism, and iOS-grade micro-interactions.*

</div>

---

## ✨ Overview

**Dynamic Island for Windows** brings a fluid, macOS/iOS-inspired interactive notch directly to your Windows desktop. Engineered with anti-aliased custom vector graphics, 60 FPS ambient animations, intelligent full-screen awareness, and a Wi-Fi phone sync bridge, it stays out of your way until you need it—and looks effortless when you do.

---

## 🚀 Key Features

### 🎛️ Bespoke Vector Playback Controls
* **Zero System Emojis:** Every control is drawn using crisp, anti-aliased vector geometry—eliminating inconsistent OS emoji rendering.
* **Golden Capsule Play/Pause:** Smooth capsule pill (`58×34px`) styled with a warm gold gradient (`#FFD600` → `#FFAC00`) and centered solid black vector glyphs (`▶` / `❚❚`).
* **Frosted Glass Secondary Pills:** Previous and Next track controls rendered as dark translucent glass pills (`42×30px`) with sharp white vector icons (`|◀` and `▶|`).

### 🌊 60 FPS Living Gradient Mesh
* **Dynamic Liquid Flow:** Powered by `_gradient_shift`, an ambient dual-vortex mesh gradient continuously undulates across the canvas at a locked 60 FPS with iridescent chromatic dispersion.
* **Album Art Color Extraction:** Extracts vibrant and muted swatches from live cover art to dynamically synchronize aurora plasma, scrubber glow, and equalizer colors.

### 🎵 26-Bar High-Resolution Audio Visualizer
* **Musical Waveform Physics:** 26 precision vertical bars span the center of the media card, driven by multi-frequency logarithmic FFT simulation with asymmetric attack/decay ballistics (`attack = 0.65`, `decay = 0.82`).
* **Dynamic Gradient Caps:** Topped with glowing gradient caps matching the current song's palette for real-time rhythmic feedback.

### 📱 Local Wi-Fi Phone Bridge & Companion
* **Lightweight Embedded Server:** Built-in local HTTP server (`http://<local-ip>:54321`) running on background thread.
* **Universal Mobile Pairing:** Works with iOS Shortcuts and Android automation (MacroDroid / Tasker / Webhooks) over local Wi-Fi.
* **Smart Notification Routing:** Automatically routes incoming calls to `call_live` state and verification codes to `otp_pill` state.

### 🎧 Apple iOS Style Accessory Connection Pop-up
* **Automatic Hardware Recognition:** Real-time CoreAudio background detection recognizes external playback devices immediately upon connection.
* **Multi-Category Dynamic Pop-ups:**
  * **AirPods & TWS Earbuds:** Displays a 3D Apple-style white open charging case with earbuds and glowing status LED.
  * **Over-Ear Headphones:** Renders sleek anodized overhead headphones (Sony XM4/XM5, Bose, AirPods Max).
  * **Bluetooth Speakers:** Renders woven fabric cylindrical speaker with passive bass radiators (JBL, Marshall).
  * **Audiophile IEMs & DACs:** Displays crystal-clear resin monitor shells with braided silver cable and 3.5mm gold jack (Moondrop, Tangzu, Fiio).
* **Authentic iOS Modal Sheet:** Rounded card, hero 3D model with ambient halo, segmented battery ring, inline audio routing capsule, and signature blue Apple pill button (`"Done"`).

### ⚙️ Standalone & System-Integrated
* **Single Windowless Binary:** Compiles cleanly to a standalone executable (`dist/DynamicIsland.exe`) via PyInstaller.
* **Silent Windows Auto-Start:** Cleanly registers to `HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Run` for background startup on boot.
* **Full-Screen Suppression:** Automatically detects foreground full-screen games (DirectX/Vulkan) and media players (YouTube, Netflix, VLC) to prevent intrusive overlay.
* **Liquid Drag & Snap Docking:** Freely drag anywhere or snap to the top bezel, bottom taskbar edge, or float anywhere with organic shape morphing.

---

## 📋 Implementation Checklist & Roadmap

### ✅ Completed & Implemented

#### 🏗️ Architecture & Lifecycle
- [x] **Single Instance Mutex & IPC:** Windows named mutex (`WinDinDynamicIsland_SingleInstanceMutex`) prevents duplicate processes and triggers instant wakeup (`/api/wake` & `WM_SHOW_DYNAMIC_ISLAND`).
- [x] **Windows Auto-Start Service:** Persistent registry entry under `HKCU\...\CurrentVersion\Run` with tray toggle.
- [x] **Crash Safety Hook:** Global unhandled exception logging to `~/DynamicIsland_crash.log`.
- [x] **Explorer Restart Recovery:** Native Windows `TaskbarCreated` message listener restores the tray icon if Windows Explorer crashes or restarts.
- [x] **PyInstaller Standalone Build Spec:** `DynamicIsland.spec` bundle configuration generating windowless `dist/DynamicIsland.exe`.

#### 🏝️ Geometry, Docking & Window Behavior
- [x] **Curvy Hardware Notch Path Generation:** Mathematical Bézier curves with flared top inverse fillets (`r = 14px`) and soft rounded bottom corners (`r = 22px`).
- [x] **Magnetic Edge Snapping & Docking:** Multi-edge docking engine supporting Top Bezel (default `y = 0`), Bottom Taskbar Edge, and Free-Floating Pill.
- [x] **Context-Aware Full-Screen Suppression:** Detects foreground full-screen apps and games via Win32 API to stay out of the way during gaming and video playback.
- [x] **Multi-Monitor & DPI Awareness:** Dynamic repositioning and centering on display geometry and screen resolution changes.
- [x] **Smart Auto-Hide Peek Mode:** Collapses to a subtle translucent tab handle at screen edge; springs into view via hover physics.

#### 🎛️ Dynamic Island UI States
- [x] **Compact Mode (`compact`):**
  - [x] Subpixel-aligned clock display (time + AM/PM label).
  - [x] Scrolling marquee ticker for track title and artist.
  - [x] 4-bar mini equalizer on the right.
  - [x] 24×24px squircle album art with smooth clipping.
  - [x] Header status strip reserving slots for PC Battery, Phone Battery (`📱 84%`), and Hardware Privacy LEDs (Mic & Camera).
- [x] **Expanded Media Dashboard (`expanded`):**
  - [x] Smooth hover-to-expand with 450ms collapse delay and `Esc` dismiss.
  - [x] 3D directional tilt physics: mouse coordinates create realistic perspective shift (`_tilt_x`, `_tilt_y`).
  - [x] Descender clipping fix: QRect height expanded to 22px/18px with `AlignVCenter` to prevent `"y"` and `"g"` truncation.
  - [x] Album art card: squircle clip (`10px` radius) with 1px inner specular border (`rgba(255, 255, 255, 0.14)`).
  - [x] 26-bar center equalizer (`visualizer.py`): logarithmic FFT simulation across 26 bands with asymmetric attack (`0.65`) and decay (`0.82`) ballistics.
  - [x] Interactive timeline scrubber (`TimelineScrubber`): 14px hit-test area, 3px → 5px hover expansion, 10px glowing thumb circle, and real-time seeking.
  - [x] Bespoke vector controls: Play/Pause gold pill (`▶` / `❚❚`) and Next/Prev frosted glass pills (`|◀` / `▶|`).
  - [x] Dynamic album art swatch extraction (`extract_album_swatches`): synchronizes plasma glow, scrubber bar, and equalizer to cover art colors.
- [x] **Notification Toast State (`toast`):**
  - [x] Liquid glass card (`420×68px`) with squircle app badge and glowing category glyphs.
  - [x] Native Windows toast listener via WinRT `UserNotificationListener`.
- [x] **Live Phone Call State (`call_live`):**
  - [x] Card geometry (`420×74px`) with pulsing green avatar ring (`#34C759`).
  - [x] Caller name and status readout.
  - [x] Vector Decline (`#FF3B30`) and Answer (`#34C759`) circular buttons with click handlers.
- [x] **2FA Verification Code Pill (`otp_pill`):**
  - [x] Pill geometry (`360×54px`) with app badge (Messages / WhatsApp).
  - [x] Monospaced tabular numerals for verification code display.
  - [x] Interactive `"Copy Code"` button transitioning smoothly to `"Copied ✓"` and writing code to Windows clipboard.
- [x] **Temporary File Shelf Tray (`file_shelf`):**
  - [x] Tray geometry (`460×126px`) with luminous dashed drop zone.
  - [x] Drag-and-drop acceptance: drops files into shelf and displays file cards (icon, elided name, size in KB).
  - [x] Clear stash button.
- [x] **OSD Volume/Brightness HUD (`osd_hud`):**
  - [x] Compact pill geometry (`220×36px`) with left glyph, center fill bar with specular sheen, and percentage readout.
  - [x] Auto-collapse timer (1.8s).

#### 🎧 Accessory Pairing & Showcase Modal
- [x] **Hardware Audio Detection:** Real-time CoreAudio background detection classifying devices (AirPods, Headphones, Speakers, IEMs/DACs).
- [x] **Flagship 3D Showcase Modal:**
  - [x] Floating 3D device render with bobbing animation, pedestal halo, and contact shadow.
  - [x] Category badge, device title, and subtitle.
  - [x] Segmented circular battery ring and percentage readout.
  - [x] Inline audio routing pill with animated slide indicator (`AirPods Pro` ↔ `PC Speakers`).
  - [x] Apple signature blue pill button (`"Done"`) with specular rim highlight.

#### 🌐 Phone Sync Bridge & System Tools
- [x] **Embedded HTTP Phone Bridge:** Runs on port `54321` with REST endpoints (`/api/notify`, `/api/wake`, `/api/status`, `/pair`).
- [x] **Mobile Web Companion:** Dark liquid-glass web interface accessible at `http://<ip>:54321` with preset alerts and setup guide for iOS Shortcuts and Android MacroDroid/Tasker.
- [x] **Screen Capture:** Instant screenshot tool saving to `~/Pictures/Screenshots` and copying to clipboard.
- [x] **Do Not Disturb (DND):** System toggle suppressing toast alerts.
- [x] **Windows System Volume:** Native mute/unmute control via `pycaw`.

---

### ⏳ Remaining to Implement & Roadmap

#### 1. Real-time Telemetry & Hardware Hooks
- [ ] **Native OSD HUD Event Binding:**
  - Hook live Windows volume key presses (Volume Up / Down / Mute) to automatically show `osd_hud` in real time rather than just text flashes.
  - Hook Windows Brightness (WmiMonitorBrightness) and Caps Lock toggle events to trigger `osd_hud`.
- [ ] **Live Hardware Privacy LEDs Detection:**
  - Implement a Windows Registry/CoreAudio watcher (`SOFTWARE\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore`) to automatically light the Mic (orange) and Camera (green) LEDs when apps actively record audio/video.
- [ ] **Real Bluetooth Device Battery Telemetry:**
  - Query actual battery levels for connected Bluetooth accessories (AirPods / headphones / speakers) via Windows GATT Battery Service or PnP Hands-Free Profile rather than default percentages.
- [ ] **Live Phone Battery Telemetry over Phone Bridge:**
  - Add a dedicated `/api/battery` endpoint to the phone bridge to sync real phone battery percentage and charging state directly from iOS Shortcuts / Tasker.

#### 2. Visual & Interaction Refinements
- [ ] **Active Drawing of Download Progress Hairline (Spec 5.2):**
  - Stroke the 2px glowing accent path along the bottom quadratic curve ($Q_0 \to Q_2$) inside `paintEvent` when downloads are in progress in `~/Downloads` (`_download_progress`).
- [ ] **Two-Way Drag-and-Drop for File Shelf (Spec 3.4):**
  - Implement outbound drag (`QDrag`) so files stored on the file shelf can be dragged directly out into Windows Explorer, Discord, Slack, or email composers.
- [ ] **Functional Audio Routing Backend (Spec 4.2):**
  - Connect the inline audio routing pill click handler to Windows `IPolicyConfig` / CoreAudio API to physically switch the default audio output between headphones and PC speakers.
- [ ] **Outbound Call Action Callbacks (Spec 3.2):**
  - Send an HTTP webhook back to the phone bridge when the user clicks "Answer" or "Decline" on `call_live` to dismiss/answer the call on the paired smartphone.

#### 3. Dashboard Integration & User Experience
- [ ] **Reminders & Quick Actions Re-integration:**
  - Re-integrate the local JSON-backed `ReminderListWidget` and `QuickActionsWidget` (currently built in `ui/components/`) into the expanded dashboard via a tabbed switcher or expandable secondary tray.
- [ ] **Visual Settings Dialog:**
  - Create a dedicated liquid glass settings dialog to configure animations, hotkeys, auto-hide timings, glow colors, and paired devices without navigating only through tray menus.
- [ ] **Media Position Seeking over GSMTC:**
  - Complete two-way timeline scrubbing synchronization to seek within native WinRT GSMTC sessions where supported by players.

---

## 📦 Quick Start

### Running from Pre-Compiled Binary
1. Download the latest release (`DynamicIsland.exe`).
2. Run `dist/DynamicIsland.exe` — the notch will automatically anchor to the top center of your primary display.
3. Play music in your favorite media player (Spotify, YouTube, browser, local player) to see the island come alive.

### Running from Source
```bash
# Clone the repository
git clone https://github.com/WindowLand/DynamicIsland.git
cd WindowLand

# Install dependencies
pip install -r requirements.txt

# Run application
python main.py
```

### Building Standalone Executable
```bash
pyinstaller DynamicIsland.spec
```
The compiled standalone executable will be generated at `dist/DynamicIsland.exe`.

---

## ⌨️ Controls & Shortcuts

| Action | Trigger |
| :--- | :--- |
| **Expand Dashboard** | Hover cursor over the top notch or press `Alt + Space` |
| **Collapse Dashboard** | Move cursor away (`450ms` delay) or press `Esc` |
| **Play / Pause / Skip** | Click the vector controls inside the expanded card |
| **Seek Playback** | Click or drag on the interactive timeline scrubber |
| **Stash Files** | Drag and drop any files directly onto the notch |
| **Copy 2FA Code** | Click "Copy Code" inside the OTP pill alert |
| **Dock Positioning** | Drag the notch or right-click Tray &rarr; *Dock Position* (Top, Bottom, Floating) |
| **Settings & Exit** | Right-click the **Dynamic Island** icon in the Windows System Tray |

---

## 👨‍💻 Developer

Crafted with precision by **pase**.
