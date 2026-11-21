# Dynamic Island for Windows — Implementation Checklist & Roadmap

This document tracks the technical architecture, implemented features, and upcoming development roadmap for **Dynamic Island for Windows**.

---

## Architecture & Core Lifecycle

- [x] **Single-Instance Mutex & IPC:** Windows named mutex (`WinDinDynamicIsland_SingleInstanceMutex`) prevents duplicate instances and signals the active process via Win32 messages / `/api/wake`.
- [x] **Silent Windows Auto-Start:** Automated registry persistence under `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` with system tray toggle.
- [x] **Crash Safety & Telemetry:** Global unhandled exception logging to `~/DynamicIsland_crash.log`.
- [x] **Explorer Restart Recovery:** Native Windows `TaskbarCreated` message listener automatically restores the tray icon and window anchors if Windows Explorer crashes or restarts.
- [x] **Standalone Binary Packaging:** Custom PyInstaller spec (`DynamicIsland.spec`) bundling runtime assets and dependencies into a lightweight (~54 MB) windowless executable.

---

## Multi-Edge Docking & Fluid Geometry

- [x] **Mathematical Bézier Curves:** Flared inverse fillets (`r = 14px`) and organic bottom corners (`r = 22px`) calculated dynamically in vector space.
- [x] **Magnetic Screen Snapping:** Multi-edge docking engine supporting:
  - **Top Bezel Notch** (`y = 0` flush anchor with concave ear fillets)
  - **Bottom Taskbar Edge** (anchored above Windows taskbar)
  - **Side Bezel Pills** (vertical pill flush against left/right screen edges)
  - **Screen Corner Reverse-L Brackets** (`⌈` dual-arm geometry for top-left, top-right, bottom-left, and bottom-right corners)
  - **Free-Floating Capsule** (unanchored draggable pill anywhere on screen)
- [x] **Topological Parametric Morphing:** Smooth continuous vector path interpolation ($p \in [0.0, 1.0]$) when transitioning between compact edge anchors and expanded dashboard cards.
- [x] **Context-Aware Full-Screen Suppression:** Detects foreground full-screen apps and games via Win32 API to stay out of the way during gaming and video playback.
- [x] **Multi-Monitor & DPI Awareness:** Dynamic repositioning and centering on display geometry and resolution changes.
- [x] **Smart Auto-Hide Peek Mode:** Collapses to a subtle translucent tab handle at the screen edge; springs into view via hover physics.

---

## Dynamic Island UI States

### 1. Compact Mode (`compact`)
- [x] **Top Notch:** Subpixel-aligned clock, scrolling marquee ticker for media metadata, squircle album thumbnail, and 4-bar mini equalizer.
- [x] **Corner Reverse-L (`⌈`):**
  - **Horizontal Arm:** Track title, artist, interactive progress scrubber with timestamps (`[01:32] ──●── [03:46]`).
  - **Corner Hub:** $26\times 26\text{ px}$ album squircle with glass specular rim (or vinyl disc fallback).
  - **Vertical Arm:** Real-time 10-band vertical frequency ladder and stacked digital clock (`hh` over `mm`).
- [x] **Side Bezel Pill:**
  - **Top:** $22\times 22\text{ px}$ album squircle with specular glass rim.
  - **Center:** Responsive 12-band vertical audio spectrum ladder.
  - **Bottom:** Stacked digital clock safely positioned in the straight pill body to prevent clipping.

### 2. Expanded Media Dashboard (`expanded`)
- [x] **Smooth Hover-to-Expand:** 450 ms collapse grace delay and `Esc` dismiss.
- [x] **3D Directional Tilt Physics:** Cursor coordinates drive real-time perspective shifts (`_tilt_x`, `_tilt_y`).
- [x] **26-Bar Center Equalizer:** Real-time WASAPI FFT loopback spectrum analysis with asymmetric attack/decay ballistics.
- [x] **Interactive Waveform Scrubber:** 14 px hit-test area, hover expansion, and real-time seek synchronization.
- [x] **Bespoke Vector Controls:** Pure vector geometry for Play/Pause gold capsule pill (`▶` / `❚❚`) and frosted glass secondary pills (`|◀` / `▶|`).
- [x] **Dynamic Swatch Extraction:** Dynamically synchronizes plasma glow, scrubber bar, and equalizer to live album cover art palette.

### 3. Notification Toast (`toast`)
- [x] Liquid glass card (`420×68px`) with squircle app badge and category glyphs.
- [x] Native Windows toast notification listener via WinRT `UserNotificationListener`.

### 4. Live Call Alert (`call_live`)
- [x] Card geometry (`420×74px`) with pulsing green avatar ring (`#34C759`).
- [x] Caller name and status readout.
- [x] Vector Decline (`#FF3B30`) and Answer (`#34C759`) circular buttons.

### 5. 2FA Verification Code Pill (`otp_pill`)
- [x] Pill geometry (`360×54px`) with app badge (Messages / WhatsApp).
- [x] Monospaced tabular numerals for verification code display.
- [x] Interactive `"Copy Code"` button transitioning smoothly to `"Copied ✓"` and writing code to Windows clipboard.

### 6. Temporary File Shelf Tray (`file_shelf`)
- [x] Tray geometry (`460×126px`) with luminous dashed drop zone.
- [x] Drag-and-drop acceptance: drops files into shelf and displays file cards (icon, elided name, size).
- [x] Clear stash button.

### 7. OSD Volume / Brightness HUD (`osd_hud`)
- [x] Compact pill geometry (`220×36px`) with left glyph, center fill bar with specular sheen, and percentage readout.
- [x] Auto-collapse timer (1.8s).

---

## Accessory Pairing & Showcase Modal

- [x] **Hardware Audio Detection:** Real-time CoreAudio background detection classifying devices:
  - **AirPods & TWS Earbuds:** 3D Apple-style white open charging case with earbuds and glowing status LED.
  - **Over-Ear Headphones:** Sleek anodized overhead headphones (Sony XM4/XM5, Bose, AirPods Max).
  - **Bluetooth Speakers:** Woven fabric cylindrical speaker with passive bass radiators.
  - **Audiophile IEMs & DACs:** Crystal-clear resin monitor shells with braided silver cable and gold jack.
- [x] **Flagship 3D Showcase Modal:**
  - Floating 3D device render with bobbing animation, pedestal halo, and contact shadow.
  - Segmented circular battery ring and percentage readout.
  - Inline audio routing pill with animated slide indicator (`AirPods Pro` ↔ `PC Speakers`).
  - Apple signature blue pill button (`"Done"`).

---

## Local Wi-Fi Phone Bridge & Companion

- [x] **Embedded HTTP Server:** Background lightweight server running on port `54321` (`/api/notify`, `/api/wake`, `/api/status`, `/pair`).
- [x] **Mobile Web Companion:** Liquid-glass web dashboard accessible from iOS Shortcuts and Android automation (MacroDroid / Tasker / Webhooks).
- [x] **Desktop Utilities:** Instant screen capture (`~/Pictures/Screenshots`), Do Not Disturb (DND) toggle, and native Windows volume controls.

---

## Future Roadmap & Planned Features

### 1. Real-time Telemetry & Hardware Hooks
- [ ] **Native OSD Event Hooking:**
  - Hook Windows media keys (Volume Up / Down / Mute) to trigger `osd_hud` automatically without delay.
  - Hook Windows Brightness (`WmiMonitorBrightness`) and Caps Lock toggles to trigger `osd_hud`.
- [ ] **Live Privacy LED Detection:**
  - Windows Registry watcher (`SOFTWARE\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore`) to illuminate microphone (orange) and camera (green) indicators when apps actively capture data.
- [ ] **Bluetooth Accessory Battery Telemetry:**
  - Query actual battery levels for connected Bluetooth accessories via Windows GATT Battery Service or PnP Hands-Free Profile.
- [ ] **Live Phone Battery over Wi-Fi Bridge:**
  - Sync real phone battery percentage and charging state via `/api/battery` directly from iOS Shortcuts / Tasker.

### 2. Interaction & System Refinements
- [ ] **Download Progress Hairline:**
  - Render an active 2px accent progress stroke along the bottom curve during active browser downloads.
- [ ] **Two-Way File Shelf Drag:**
  - Implement outbound drag (`QDrag`) so files dropped on the file shelf can be dragged out into Windows Explorer, Discord, Slack, or email clients.
- [ ] **Hardware Audio Routing Execution:**
  - Connect the audio routing pill click handler to Windows `IPolicyConfig` / CoreAudio API to switch default playback endpoints.
- [ ] **Two-Way Call Webhook Callbacks:**
  - Send HTTP webhook response back to phone bridge when clicking "Answer" or "Decline" on `call_live`.

### 3. Dashboard Integration
- [ ] **Reminders & Quick Actions Tray:**
  - Re-integrate JSON-backed reminder checklists and quick system shortcuts into secondary dashboard tabs.
- [ ] **Liquid Glass Settings Dialog:**
  - Native visual configuration panel for animations, hotkeys, auto-hide timings, and dock behaviors.

---

[Return to README](README.md)
