"""
Real-time Hardware Audio Spectrum & WASAPI Loopback Engine.
Captures bit-exact audio PCM output from the default Windows playback device,
computes 2048-point Hann-windowed FFTs at 60 FPS, and extracts calibrated
logarithmic frequency bands (sub-bass to brilliance) with studio ballistics.
"""

import time
import math
import threading
from typing import List, Tuple, Optional
from ctypes import (
    POINTER, c_uint, c_int, c_ulonglong, c_void_p, c_ushort,
    Structure, byref, cast, c_float, c_byte, c_ulong, c_short
)

import numpy as np
import comtypes
from comtypes import IUnknown, GUID, COMMETHOD, HRESULT

try:
    from pycaw.pycaw import AudioUtilities
    HAS_PYCAW = True
except ImportError:
    HAS_PYCAW = False


class WAVEFORMATEX(Structure):
    _fields_ = [
        ("wFormatTag", c_ushort),
        ("nChannels", c_ushort),
        ("nSamplesPerSec", c_uint),
        ("nAvgBytesPerSec", c_uint),
        ("nBlockAlign", c_ushort),
        ("wBitsPerSample", c_ushort),
        ("cbSize", c_ushort),
    ]


class IAudioCaptureClient(IUnknown):
    _iid_ = GUID("{C8ADBD64-E71E-48a0-A4DE-185C395CD317}")
    _methods_ = [
        COMMETHOD([], HRESULT, "GetBuffer",
                  (["out"], POINTER(POINTER(c_byte)), "ppData"),
                  (["out"], POINTER(c_uint), "pNumFramesToRead"),
                  (["out"], POINTER(c_ulong), "pdwFlags"),
                  (["out"], POINTER(c_ulonglong), "pu64DevicePosition"),
                  (["out"], POINTER(c_ulonglong), "pu64QPCPosition")),
        COMMETHOD([], HRESULT, "ReleaseBuffer",
                  (["in"], c_uint, "NumFramesRead")),
        COMMETHOD([], HRESULT, "GetNextPacketSize",
                  (["out"], POINTER(c_uint), "pNumFramesInNextPacket"))
    ]


class IAudioClient(IUnknown):
    _iid_ = GUID("{1CB9AD4C-DBFA-4c32-B178-C2F568A703B2}")
    _methods_ = [
        COMMETHOD([], HRESULT, "Initialize",
                  (["in"], c_int, "ShareMode"),
                  (["in"], c_uint, "StreamFlags"),
                  (["in"], c_ulonglong, "hnsBufferDuration"),
                  (["in"], c_ulonglong, "hnsPeriodicity"),
                  (["in"], POINTER(WAVEFORMATEX), "pFormat"),
                  (["in"], c_void_p, "AudioSessionGuid")),
        COMMETHOD([], HRESULT, "GetBufferSize",
                  (["out"], POINTER(c_uint), "pNumBufferFrames")),
        COMMETHOD([], HRESULT, "GetStreamLatency",
                  (["out"], POINTER(c_ulonglong), "phnsLatency")),
        COMMETHOD([], HRESULT, "GetCurrentPadding",
                  (["out"], POINTER(c_uint), "pNumPaddingFrames")),
        COMMETHOD([], HRESULT, "IsFormatSupported",
                  (["in"], c_int, "ShareMode"),
                  (["in"], POINTER(WAVEFORMATEX), "pFormat"),
                  (["out"], POINTER(POINTER(WAVEFORMATEX)), "ppClosestMatch")),
        COMMETHOD([], HRESULT, "GetMixFormat",
                  (["out"], POINTER(POINTER(WAVEFORMATEX)), "ppDeviceFormat")),
        COMMETHOD([], HRESULT, "GetDevicePeriod",
                  (["out"], POINTER(c_ulonglong), "phnsDefaultDevicePeriod"),
                  (["out"], POINTER(c_ulonglong), "phnsMinimumDevicePeriod")),
        COMMETHOD([], HRESULT, "Start"),
        COMMETHOD([], HRESULT, "Stop"),
        COMMETHOD([], HRESULT, "Reset"),
        COMMETHOD([], HRESULT, "SetEventHandle",
                  (["in"], c_void_p, "eventHandle")),
        COMMETHOD([], HRESULT, "GetService",
                  (["in"], POINTER(GUID), "riid"),
                  (["out"], POINTER(POINTER(IUnknown)), "ppv"))
    ]


class AudioSpectrumEngine:
    """
    High-performance, multi-threaded WASAPI loopback FFT analyzer.
    Extracts real-time, 60 FPS multi-band audio spectrum with zero lag.
    """
    def __init__(self, num_bars: int = 22):
        self.num_bars = num_bars
        self._bands = [0.0] * num_bars
        self._peak_caps = [0.0] * num_bars
        self._peak_cap_decay = [0.0] * num_bars
        self._overall_peak = 0.0
        self._bass_energy = 0.0
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def start(self):
        if not HAS_PYCAW or self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True, name="WindowLand_AudioSpectrum")
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=0.6)

    def get_spectrum(self) -> List[float]:
        """Returns thread-safe copy of 22 normalized frequency band magnitudes [0.0 .. 1.0]."""
        with self._lock:
            return list(self._bands)

    def get_peak_caps(self) -> List[float]:
        """Returns thread-safe floating peak cap positions [0.0 .. 1.0]."""
        with self._lock:
            return list(self._peak_caps)

    def get_peak(self) -> float:
        """Returns instantaneous master audio volume [0.0 .. 1.0]."""
        with self._lock:
            return float(self._overall_peak)

    def get_bass(self) -> float:
        """Returns instant bass/kick transient energy [0.0 .. 1.0]."""
        with self._lock:
            return float(self._bass_energy)

    def _capture_loop(self):
        while self._running:
            try:
                comtypes.CoInitialize()
            except Exception:
                pass

            ac = None
            try:
                device = AudioUtilities.GetSpeakers()._dev
                if not device:
                    time.sleep(1.0)
                    continue

                ac = device.Activate(IAudioClient._iid_, comtypes.CLSCTX_ALL, None).QueryInterface(IAudioClient)
                pwfx = ac.GetMixFormat()
                wfx = pwfx.contents
                rate = int(wfx.nSamplesPerSec)
                channels = int(wfx.nChannels)
                bits = int(wfx.wBitsPerSample)

                AUDCLNT_STREAMFLAGS_LOOPBACK = 0x00020000
                # 10ms buffer duration (100,000 hns)
                ac.Initialize(0, AUDCLNT_STREAMFLAGS_LOOPBACK, 1000000, 0, pwfx, None)
                capture = ac.GetService(byref(IAudioCaptureClient._iid_)).QueryInterface(IAudioCaptureClient)
                ac.Start()

                n_fft = 2048
                window = np.hanning(n_fft).astype(np.float32)
                freqs = np.fft.rfftfreq(n_fft, d=1.0 / rate)

                # 22 Logarithmic Bands from 35 Hz to 16,000 Hz
                edges = np.logspace(np.log10(35.0), np.log10(16000.0), self.num_bars + 1)
                bin_indices = []
                tilt_weights = []

                for i in range(self.num_bars):
                    idx = np.where((freqs >= edges[i]) & (freqs < edges[i + 1]))[0]
                    if len(idx) == 0:
                        idx = np.array([np.argmin(np.abs(freqs - edges[i]))])
                    bin_indices.append(idx)
                    # Equal loudness tilt: human ear requires higher energy at low frequencies;
                    # high frequencies naturally carry less acoustic power.
                    center_f = np.sqrt(edges[i] * edges[i + 1])
                    weight = (center_f / 100.0) ** 0.44
                    tilt_weights.append(weight)

                ring_buf = np.zeros(n_fft * 2, dtype=np.float32)
                smoothed = np.zeros(self.num_bars, dtype=np.float32)
                caps = np.zeros(self.num_bars, dtype=np.float32)
                cap_hold = np.zeros(self.num_bars, dtype=np.int32)
                master_peak = 0.0

                while self._running:
                    pkt = capture.GetNextPacketSize()
                    has_data = False

                    while pkt > 0:
                        pData, nFrames, flags, devPos, qpcPos = capture.GetBuffer()
                        if nFrames > 0:
                            total = nFrames * channels
                            if bits == 32:
                                float_ptr = cast(pData, POINTER(c_float))
                                raw = np.ctypeslib.as_array(float_ptr, shape=(total,))
                            elif bits == 16:
                                short_ptr = cast(pData, POINTER(c_short))
                                raw = np.ctypeslib.as_array(short_ptr, shape=(total,)).astype(np.float32) / 32768.0
                            else:
                                raw = np.zeros(total, dtype=np.float32)

                            if channels == 2:
                                mono = 0.5 * (raw[0::2] + raw[1::2])
                            else:
                                mono = raw

                            if len(mono) > 0:
                                ring_buf = np.roll(ring_buf, -len(mono))
                                ring_buf[-len(mono):] = mono
                                has_data = True

                        capture.ReleaseBuffer(nFrames)
                        pkt = capture.GetNextPacketSize()

                    if has_data:
                        # RMS amplitude
                        curr_rms = float(np.sqrt(np.mean(ring_buf[-1024:] ** 2)))
                        master_peak += (curr_rms - master_peak) * 0.45

                        # 2048-point Windowed FFT
                        chunk = ring_buf[-n_fft:] * window
                        fft_mag = np.abs(np.fft.rfft(chunk))
                        norm_factor = 2.0 / n_fft

                        # Sub-bass / Kick detection (bins 0-3: 35Hz-90Hz)
                        sub_bass = float(np.mean(fft_mag[bin_indices[0]] + fft_mag[bin_indices[1]])) * norm_factor * 12.0
                        b_energy = min(1.0, sub_bass)

                        for i in range(self.num_bars):
                            mag = float(np.mean(fft_mag[bin_indices[i]])) * norm_factor
                            val = mag * tilt_weights[i]
                            # Perceptual logarithmic compression
                            compressed = math.pow(max(0.0, val), 0.46) * 3.1
                            target = max(0.0, min(1.0, compressed))

                            # Asymmetric ballistics: instant rise (0.82), smooth fluid decay (0.20)
                            if target > smoothed[i]:
                                smoothed[i] += (target - smoothed[i]) * 0.82
                            else:
                                smoothed[i] += (target - smoothed[i]) * 0.20

                            # Floating Peak Caps: hold for 14 ticks then drift down
                            if smoothed[i] >= caps[i]:
                                caps[i] = smoothed[i]
                                cap_hold[i] = 14
                            else:
                                if cap_hold[i] > 0:
                                    cap_hold[i] -= 1
                                else:
                                    caps[i] = max(0.0, caps[i] - 0.024)

                        with self._lock:
                            self._bands = [float(x) for x in smoothed]
                            self._peak_caps = [float(x) for x in caps]
                            self._overall_peak = float(master_peak)
                            self._bass_energy = float(b_energy)

                    else:
                        # Natural decay to silence when no audio frames arrive
                        smoothed *= 0.88
                        caps = np.maximum(0.0, caps - 0.03)
                        with self._lock:
                            self._bands = [float(x) for x in smoothed]
                            self._peak_caps = [float(x) for x in caps]
                            self._overall_peak *= 0.85
                            self._bass_energy *= 0.85

                    time.sleep(0.016)  # 60 FPS

                try:
                    ac.Stop()
                except Exception:
                    pass

            except Exception:
                time.sleep(1.0)
            finally:
                try:
                    comtypes.CoUninitialize()
                except Exception:
                    pass
