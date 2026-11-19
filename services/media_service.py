"""
Media Service for Windows 10/11 Glass Overlay.
Uses Windows Runtime (winrt / winsdk) GSMTC APIs in a dedicated background
asyncio thread, bridged to PyQt6 via pyqtSignal.
Extracts live album artwork and streams playback info cleanly without package IDs.
"""

import os
import asyncio
import threading
import queue
import time
from typing import Optional, Dict, Any
from PyQt6.QtCore import QObject, pyqtSignal

# Import Windows Media GSMTC and Storage Streams
HAS_WINRT = False
try:
    import winrt.windows.media.control as wmc
    import winrt.windows.storage.streams as streams
    HAS_WINRT = True
except ImportError:
    try:
        import winsdk.windows.media.control as wmc
        import winsdk.windows.storage.streams as streams
        HAS_WINRT = True
    except ImportError:
        wmc = None
        streams = None

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COVERS_DIR = os.path.join(BASE_DIR, "assets", "covers")
os.makedirs(COVERS_DIR, exist_ok=True)

MOCK_PLAYLIST = [
    {
        "title": "Starboy",
        "artist": "The Weeknd ft. Daft Punk",
        "album": "Starboy",
        "cover": os.path.join(COVERS_DIR, "mock_0.jpg"),
        "duration": 230,
    },
    {
        "title": "Blinding Lights",
        "artist": "The Weeknd",
        "album": "After Hours",
        "cover": os.path.join(COVERS_DIR, "mock_1.jpg"),
        "duration": 200,
    },
    {
        "title": "Midnight City",
        "artist": "M83",
        "album": "Hurry Up, We're Dreaming",
        "cover": os.path.join(COVERS_DIR, "mock_2.jpg"),
        "duration": 244,
    },
    {
        "title": "Get Lucky",
        "artist": "Daft Punk ft. Pharrell",
        "album": "Random Access Memories",
        "cover": os.path.join(COVERS_DIR, "mock_3.jpg"),
        "duration": 248,
    },
]


class MediaService(QObject):
    """
    Background media worker and coordinator for Windows Media controls.
    Emits signals safely to the Qt GUI thread.
    """
    media_updated = pyqtSignal(dict)
    status_message = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._command_queue = queue.Queue()
        self._mock_mode = False
        self._mock_index = 0
        self._mock_playing = True
        self._mock_position = 45
        self._last_state: Dict[str, Any] = {}
        self._last_art_signature = ""

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="MediaServiceWorker")
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread and self._thread.is_alive():
            self._command_queue.put(("QUIT", None))

    def toggle_play_pause(self):
        self._command_queue.put(("TOGGLE_PLAY_PAUSE", None))

    def next_track(self):
        self._command_queue.put(("NEXT", None))

    def previous_track(self):
        self._command_queue.put(("PREV", None))

    def set_mock_mode(self, enabled: bool):
        self._command_queue.put(("SET_MOCK", enabled))

    def toggle_mock_mode(self):
        self.set_mock_mode(not self._mock_mode)

    def _run_loop(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._async_monitor())
        finally:
            loop.close()

    async def _async_monitor(self):
        manager = None
        if HAS_WINRT and wmc:
            try:
                manager = await wmc.GlobalSystemMediaTransportControlsSessionManager.request_async()
            except Exception:
                manager = None

        poll_interval = 0.5
        last_poll = 0

        while self._running:
            while not self._command_queue.empty():
                try:
                    cmd, arg = self._command_queue.get_nowait()
                    if cmd == "QUIT":
                        return
                    elif cmd == "SET_MOCK":
                        self._mock_mode = bool(arg)
                        self._emit_mock_state()
                    elif cmd == "TOGGLE_PLAY_PAUSE":
                        await self._handle_toggle(manager)
                    elif cmd == "NEXT":
                        await self._handle_next(manager)
                    elif cmd == "PREV":
                        await self._handle_prev(manager)
                except queue.Empty:
                    break
                except Exception:
                    pass

            now = time.time()
            if now - last_poll >= poll_interval:
                last_poll = now
                if self._mock_mode or manager is None:
                    if self._mock_mode:
                        if self._mock_playing:
                            self._mock_position = (self._mock_position + 1) % MOCK_PLAYLIST[self._mock_index]["duration"]
                        self._emit_mock_state()
                    else:
                        if HAS_WINRT and wmc and manager is None:
                            try:
                                manager = await wmc.GlobalSystemMediaTransportControlsSessionManager.request_async()
                            except Exception:
                                pass
                        await self._poll_windows_media(manager)
                else:
                    await self._poll_windows_media(manager)

            await asyncio.sleep(0.1)

    async def _poll_windows_media(self, manager):
        if manager is None:
            state = {
                "has_media": False,
                "is_playing": False,
                "title": "",
                "artist": "",
                "album": "",
                "is_mock": False,
                "album_art_path": None,
                "position": 0,
                "duration": 0,
            }
            self._emit_state_if_changed(state)
            return

        try:
            current_session = manager.get_current_session()
            if current_session is None:
                state = {
                    "has_media": False,
                    "is_playing": False,
                    "title": "",
                    "artist": "",
                    "album": "",
                    "is_mock": False,
                    "album_art_path": None,
                    "position": 0,
                    "duration": 0,
                }
                self._emit_state_if_changed(state)
                return

            props = await current_session.try_get_media_properties_async()
            playback = current_session.get_playback_info()
            timeline = current_session.get_timeline_properties()

            playback_status = getattr(playback, "playback_status", 0)
            # WinRT GlobalSystemMediaTransportControlsSessionPlaybackStatus:
            # 4 = PLAYING, 5 = PAUSED, 3 = STOPPED, 0 = CLOSED
            if hasattr(wmc, "GlobalSystemMediaTransportControlsSessionPlaybackStatus"):
                is_playing = (playback_status == wmc.GlobalSystemMediaTransportControlsSessionPlaybackStatus.PLAYING)
            else:
                is_playing = (int(playback_status) == 4)

            title = getattr(props, "title", "") if props else ""
            artist = getattr(props, "artist", "") if props else ""
            album = getattr(props, "album_title", "") if props else ""

            pos_sec = 0
            dur_sec = 0
            try:
                if timeline:
                    pos_sec = int(timeline.position.total_seconds())
                    dur_sec = int(timeline.end_time.total_seconds())
            except Exception:
                pass

            # Extract Album Artwork
            art_path = None
            art_signature = f"{title}_{artist}_{album}"
            cache_file = os.path.join(COVERS_DIR, "live_cover.jpg")

            if props and getattr(props, "thumbnail", None) and streams:
                try:
                    if art_signature != self._last_art_signature or not os.path.exists(cache_file):
                        stream = await props.thumbnail.open_read_async()
                        size = stream.size
                        if size > 0:
                            reader = streams.DataReader(stream)
                            await reader.load_async(size)
                            buf = bytearray(size)
                            reader.read_bytes(buf)
                            with open(cache_file, "wb") as f:
                                f.write(buf)
                            self._last_art_signature = art_signature
                    if os.path.exists(cache_file):
                        art_path = cache_file
                except Exception:
                    if os.path.exists(cache_file):
                        art_path = cache_file
            elif os.path.exists(cache_file):
                art_path = cache_file

            has_media = bool(title or artist or is_playing)

            state = {
                "has_media": has_media,
                "is_playing": is_playing,
                "title": title or "Playing Audio",
                "artist": artist or "",
                "album": album or "",
                "is_mock": False,
                "album_art_path": art_path,
                "position": pos_sec,
                "duration": dur_sec or 210,
            }
            self._emit_state_if_changed(state)

        except Exception:
            pass

    async def _handle_toggle(self, manager):
        if self._mock_mode or manager is None:
            self._mock_playing = not self._mock_playing
            self._emit_mock_state()
            return

        try:
            cur = manager.get_current_session()
            if cur:
                await cur.try_toggle_play_pause_async()
                await asyncio.sleep(0.12)
                await self._poll_windows_media(manager)
            else:
                self._mock_mode = True
                self._mock_playing = True
                self._emit_mock_state()
        except Exception:
            self._mock_mode = True
            self._mock_playing = not self._mock_playing
            self._emit_mock_state()

    async def _handle_next(self, manager):
        if self._mock_mode or manager is None:
            self._mock_index = (self._mock_index + 1) % len(MOCK_PLAYLIST)
            self._mock_position = 0
            self._emit_mock_state()
            return

        try:
            cur = manager.get_current_session()
            if cur:
                await cur.try_skip_next_async()
                await asyncio.sleep(0.2)
                await self._poll_windows_media(manager)
            else:
                self._mock_mode = True
                self._mock_index = (self._mock_index + 1) % len(MOCK_PLAYLIST)
                self._mock_position = 0
                self._emit_mock_state()
        except Exception:
            self._mock_mode = True
            self._mock_index = (self._mock_index + 1) % len(MOCK_PLAYLIST)
            self._mock_position = 0
            self._emit_mock_state()

    async def _handle_prev(self, manager):
        if self._mock_mode or manager is None:
            self._mock_index = (self._mock_index - 1) % len(MOCK_PLAYLIST)
            self._mock_position = 0
            self._emit_mock_state()
            return

        try:
            cur = manager.get_current_session()
            if cur:
                await cur.try_skip_previous_async()
                await asyncio.sleep(0.2)
                await self._poll_windows_media(manager)
            else:
                self._mock_mode = True
                self._mock_index = (self._mock_index - 1) % len(MOCK_PLAYLIST)
                self._mock_position = 0
                self._emit_mock_state()
        except Exception:
            self._mock_mode = True
            self._mock_index = (self._mock_index - 1) % len(MOCK_PLAYLIST)
            self._mock_position = 0
            self._emit_mock_state()

    def _emit_mock_state(self):
        track = MOCK_PLAYLIST[self._mock_index]
        state = {
            "has_media": True,
            "is_playing": self._mock_playing,
            "title": track["title"],
            "artist": track["artist"],
            "album": track["album"],
            "is_mock": True,
            "album_art_path": track["cover"],
            "position": self._mock_position,
            "duration": track["duration"],
        }
        self._emit_state_if_changed(state)

    def _emit_state_if_changed(self, state: Dict[str, Any]):
        if (state.get("title") != self._last_state.get("title") or
            state.get("artist") != self._last_state.get("artist") or
            state.get("is_playing") != self._last_state.get("is_playing") or
            state.get("album_art_path") != self._last_state.get("album_art_path") or
            state.get("has_media") != self._last_state.get("has_media")):
            self._last_state = dict(state)
            self.media_updated.emit(state)
        else:
            self._last_state["position"] = state.get("position", 0)
            self.media_updated.emit(state)
