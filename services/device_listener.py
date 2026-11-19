"""
Device Listener Service for Windows.
Monitors external audio playback device connections:
- AirPods / True Wireless Earbuds
- Overhead / Over-Ear Headphones
- Bluetooth & External Speakers
- IEMs (In-Ear Monitors) & Audiophile USB DACs
"""

import time
import re
import threading
from typing import Dict, Any, Optional, Set

from PyQt6.QtCore import QObject, pyqtSignal

try:
    import comtypes
    from pycaw.pycaw import AudioUtilities, AudioDeviceState
    HAS_PYCAW = True
except Exception:
    HAS_PYCAW = False


# Devices to ignore for auto-popup on startup (internal motherboard audio)
INTERNAL_AUDIO_PATTERNS = [
    r"^speaker\s*\(\s*realtek",
    r"^speakers\s*\(\s*realtek",
    r"intel.*smart\s*sound",
    r"nvidia\s*output",
    r"high\s*definition\s*audio\s*device$",
]


def is_internal_system_audio(friendly_name: str) -> bool:
    """Returns True if the device is a standard built-in PC speaker or GPU display audio."""
    fn = friendly_name.strip().lower()
    for pat in INTERNAL_AUDIO_PATTERNS:
        if re.search(pat, fn):
            return True
    return False


def clean_device_name(friendly_name: str, properties: Dict[str, Any]) -> str:
    """Extract clean consumer device name from friendly name or property bag."""
    # Check Property Bag for the direct Bluetooth / device name
    # {B3F8FA53-0004-438E-9003-51A46E139BFC} 6 or {026E516E-B814-414B-83CD-856D6FEF4822} 2
    for k, v in properties.items():
        if isinstance(k, tuple) and len(k) == 2 and k[1] == 6:
            v_str = str(v).strip()
            if v_str and not is_internal_system_audio(v_str):
                return v_str
        if isinstance(k, tuple) and len(k) == 2 and k[1] == 2:
            v_str = str(v).strip()
            if v_str and v_str not in ("Headphones", "Speakers", "Headphone", "Headset") and not is_internal_system_audio(v_str):
                return v_str

    # Fallback: strip "Headphones (...)" or "Speakers (...)"
    m = re.match(r"^(?:Headphones?|Speakers?|Headset)\s*\((.*?)\)$", friendly_name.strip(), re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return friendly_name.strip()


def classify_device(friendly_name: str, properties: Dict[str, Any]) -> tuple[str, bool]:
    """
    Categorizes the device into:
    - 'airpods': AirPods and TWS earbuds
    - 'headphones': Over-ear / overhead headphones
    - 'speaker': Bluetooth and external portable speakers
    - 'iem': In-ear monitors and external DACs
    Returns (category, is_bluetooth)
    """
    lower_name = friendly_name.lower()

    # Check bluetooth flag from properties
    is_bt = False
    for v in properties.values():
        v_str = str(v).lower()
        if any(b in v_str for b in ("bth", "bluetooth", "microsoft_bluetooth", "bthenum")):
            is_bt = True
            break

    # 1. AirPods / TWS Earbuds
    airpods_kw = [
        "airpod", "buds", "earbuds", "earbud", "freebuds", "galaxy buds",
        "pixel buds", "tws", "tune", "wave", "linkbuds", "wf-", "air 3", "liberty"
    ]
    if any(k in lower_name for k in airpods_kw):
        return "airpods", is_bt

    # 2. IEMs / DACs
    iem_kw = [
        "iem", "in-ear", "dac", "fiio", "moondrop", "tangzu", "salnotes",
        "zero", "chu", "aria", "kato", "blon", "kz ", "cca", "shure",
        "westone", "tin hifi", "qudelix", "topping", "ifi", "dragonfly",
        "hidizs", "audioquest"
    ]
    if any(k in lower_name for k in iem_kw):
        return "iem", is_bt

    # 3. Bluetooth / External Speakers
    speaker_kw = [
        "soundmx", "soundbar", "soundlink", "charge", "flip", "boom",
        "clip", "go 3", "jbl", "marshall", "emberton", "soundcore",
        "tribit", "echo", "nest", "pebble", "wonderboom", "megaboom"
    ]
    if any(k in lower_name for k in speaker_kw):
        return "speaker", is_bt

    # 4. Over-Ear Headphones
    headphones_kw = [
        "wh-", "xm4", "xm5", "xm3", "qc35", "qc45", "quietcomfort",
        "headphone", "headset", "sennheiser", "momentum", "bose", "beats",
        "dt 770", "dt 990", "dt 1990", "m50x", "arctis", "hyperx",
        "cloud", "corsair", "razer", "cyomi", "audio-technica"
    ]
    if any(k in lower_name for k in headphones_kw):
        return "headphones", is_bt

    # Fallbacks based on category strings
    if "speaker" in lower_name:
        return "speaker", is_bt
    if "headphone" in lower_name or "headset" in lower_name or "earphone" in lower_name:
        return "headphones", is_bt

    return "speaker", is_bt


class DeviceService(QObject):
    """
    Background polling service that detects external audio device connections and
    emits `device_connected` with detailed classification and metadata.
    """
    device_connected = pyqtSignal(dict)
    device_disconnected = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        # State tracking
        self._known_active_device_ids: Set[str] = set()
        self._last_default_id: Optional[str] = None
        self._last_notified_device_id: Optional[str] = None
        self._last_notified_time: float = 0.0

    def start(self):
        if not HAS_PYCAW:
            return
        if self._running:
            return
        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True, name="DeviceServiceMonitor")
        self._thread.start()

    def stop(self):
        self._running = False
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._thread = None

    def trigger_simulated_device(self, category: str, custom_name: Optional[str] = None):
        """Allows testing any device type on demand."""
        names = {
            "airpods": custom_name or "Manu’s AirPods Pro #2",
            "headphones": custom_name or "Sony WH-1000XM5",
            "speaker": custom_name or "Zeb SoundMX",
            "iem": custom_name or "Moondrop Chu II / Fiio DAC",
        }
        subtitles = {
            "airpods": "Connected to Windows • Audio Ready",
            "headphones": "Wireless Headphones Connected",
            "speaker": "Bluetooth Speaker Connected",
            "iem": "Hi-Res Audio Output Active",
        }
        name = names.get(category, "Audio Device")
        data = {
            "category": category,
            "name": name,
            "raw_name": name,
            "is_bluetooth": category in ("airpods", "headphones", "speaker"),
            "display_title": name,
            "display_subtitle": subtitles.get(category, "Connected to Windows"),
            "timestamp": time.time(),
        }
        self.device_connected.emit(data)

    def _monitor_loop(self):
        """Worker thread loop polling Windows CoreAudio."""
        try:
            comtypes.CoInitialize()
        except Exception:
            pass

        # 1. Establish initial baseline
        try:
            spk = AudioUtilities.GetSpeakers()
            if spk and spk.id:
                self._last_default_id = spk.id
            for d in AudioUtilities.GetAllDevices():
                if d.state == AudioDeviceState.Active and "{0.0.0." in d.id:
                    self._known_active_device_ids.add(d.id)
        except Exception:
            pass

        # Main polling loop
        while not self._stop_event.is_set():
            time.sleep(1.2)
            if self._stop_event.is_set():
                break

            try:
                # 1. Check default playback speaker
                current_spk = AudioUtilities.GetSpeakers()
                curr_default_id = current_spk.id if current_spk else None

                # 2. Check all active playback endpoints
                current_active_ids = set()
                current_devices_by_id = {}
                for d in AudioUtilities.GetAllDevices():
                    if d.state == AudioDeviceState.Active and "{0.0.0." in d.id:
                        current_active_ids.add(d.id)
                        current_devices_by_id[d.id] = d

                # Detect newly appeared devices
                new_device_ids = current_active_ids - self._known_active_device_ids
                
                # Check if default changed to an external audio device
                default_changed = (
                    curr_default_id is not None
                    and curr_default_id != self._last_default_id
                    and curr_default_id in current_devices_by_id
                )

                target_device = None
                if new_device_ids:
                    # Pick the newly connected device
                    for nid in new_device_ids:
                        d = current_devices_by_id.get(nid)
                        if d and not is_internal_system_audio(d.FriendlyName):
                            target_device = d
                            break
                elif default_changed:
                    d = current_devices_by_id.get(curr_default_id)
                    if d and not is_internal_system_audio(d.FriendlyName):
                        target_device = d

                # If an external device connected, notify!
                if target_device:
                    now = time.time()
                    if (target_device.id != self._last_notified_device_id) or (now - self._last_notified_time > 5.0):
                        clean_name = clean_device_name(target_device.FriendlyName, target_device.properties)
                        cat, is_bt = classify_device(target_device.FriendlyName, target_device.properties)

                        subtitles = {
                            "airpods": "Connected to Windows • Audio Ready",
                            "headphones": "Wireless Headphones Connected",
                            "speaker": "Bluetooth Speaker Connected",
                            "iem": "Hi-Res Audio Output Active",
                        }

                        payload = {
                            "category": cat,
                            "name": clean_name,
                            "raw_name": target_device.FriendlyName,
                            "is_bluetooth": is_bt,
                            "display_title": clean_name,
                            "display_subtitle": subtitles.get(cat, "Connected to Windows"),
                            "timestamp": now,
                        }

                        self._last_notified_device_id = target_device.id
                        self._last_notified_time = now
                        self.device_connected.emit(payload)

                # Update baseline
                self._known_active_device_ids = current_active_ids
                if curr_default_id:
                    self._last_default_id = curr_default_id

            except Exception:
                pass

        try:
            comtypes.CoUninitialize()
        except Exception:
            pass
