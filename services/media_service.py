"""
Media Service for Windows 10/11 Glass Overlay.
Uses Windows Runtime (winrt / winsdk) GSMTC APIs in a dedicated background
asyncio thread, bridged to PyQt6 via pyqtSignal.
Extracts live album artwork and streams playback info cleanly without package IDs.
"""

import os
import sys
import glob
import hashlib
import asyncio
import threading
import queue
import time
import datetime
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

# Writable directory for dynamic album covers (works in dev and PyInstaller .exe)
LOCAL_APPDATA = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
COVERS_DIR = os.path.join(LOCAL_APPDATA, "DynamicIsland", "covers")
os.makedirs(COVERS_DIR, exist_ok=True)

# Base directory for bundled mock assets
if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    BUNDLE_DIR = sys._MEIPASS
else:
    BUNDLE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_COVERS_DIR = os.path.join(BUNDLE_DIR, "assets", "covers")

MOCK_PLAYLIST = [
    {
        "title": "Starboy",
        "artist": "The Weeknd ft. Daft Punk",
        "album": "Starboy",
        "cover": os.path.join(STATIC_COVERS_DIR, "mock_0.jpg"),
        "duration": 230,
    },
    {
        "title": "Blinding Lights",
        "artist": "The Weeknd",
        "album": "After Hours",
        "cover": os.path.join(STATIC_COVERS_DIR, "mock_1.jpg"),
        "duration": 200,
    },
    {
        "title": "Midnight City",
        "artist": "M83",
        "album": "Hurry Up, We're Dreaming",
        "cover": os.path.join(STATIC_COVERS_DIR, "mock_2.jpg"),
        "duration": 244,
    },
    {
        "title": "Get Lucky",
        "artist": "Daft Punk ft. Pharrell",
        "album": "Random Access Memories",
        "cover": os.path.join(STATIC_COVERS_DIR, "mock_3.jpg"),
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
        self._active_session_id: Optional[str] = None
        self._last_playing_time = 0.0
        self._skip_grace_until = 0.0

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

    def seek(self, position_seconds: float):
        self._command_queue.put(("SEEK", position_seconds))

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
                    elif cmd == "SEEK":
                        await self._handle_seek(manager, arg)
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

    def _resolve_active_session(self, manager):
        """
        Intelligently resolves the active media session:
        1. Prioritizes any session that is actively PLAYING.
        2. Applies hysteresis during track skips so background media doesn't flicker in.
        3. Sticks to the active session rather than fluctuating to idle browser tabs.
        """
        if not manager:
            return None
        try:
            sessions = list(manager.get_sessions())
            if not sessions:
                cur = manager.get_current_session()
                if cur:
                    self._active_session_id = cur.source_app_user_model_id
                return cur

            now = time.time()

            # 1. Look for any session that is actively PLAYING
            for s in sessions:
                try:
                    pb = s.get_playback_info()
                    status = getattr(pb, "playback_status", 0)
                    if int(status) == 4:  # PLAYING
                        self._active_session_id = s.source_app_user_model_id
                        self._last_playing_time = now
                        return s
                except Exception:
                    pass

            # 2. Skip grace window: keep showing the active session during track change
            in_grace = (now < self._skip_grace_until) or (now - self._last_playing_time < 2.2)
            if in_grace and self._active_session_id:
                for s in sessions:
                    try:
                        if s.source_app_user_model_id == self._active_session_id:
                            return s
                    except Exception:
                        pass

            # 3. Fallback to system default or first session
            cur = manager.get_current_session()
            if cur:
                self._active_session_id = cur.source_app_user_model_id
                return cur
            self._active_session_id = sessions[0].source_app_user_model_id
            return sessions[0]
        except Exception:
            try:
                return manager.get_current_session()
            except Exception:
                return None

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
            current_session = self._resolve_active_session(manager)
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

            pos_sec = 0.0
            dur_sec = 0.0
            try:
                if timeline:
                    raw_pos = timeline.position.total_seconds() if timeline.position else 0.0
                    raw_dur = timeline.end_time.total_seconds() if timeline.end_time else 0.0
                    dur_sec = max(0.0, raw_dur)
                    if is_playing and hasattr(timeline, "last_updated_time") and timeline.last_updated_time:
                        now_utc = datetime.datetime.now(datetime.timezone.utc)
                        delta = (now_utc - timeline.last_updated_time).total_seconds()
                        pos_sec = raw_pos + max(0.0, delta)
                    else:
                        pos_sec = raw_pos
                    if dur_sec > 0:
                        pos_sec = min(dur_sec, max(0.0, pos_sec))
                    else:
                        pos_sec = max(0.0, pos_sec)
            except Exception:
                pass

            # Extract Album Artwork (track-specific hashed filename to prevent stale caching)
            art_path = None
            art_signature = f"{title}_{artist}_{album}"
            art_hash = hashlib.md5(art_signature.encode("utf-8", errors="ignore")).hexdigest()[:10]
            cache_file = os.path.join(COVERS_DIR, f"cover_{art_hash}.jpg")

            if props and getattr(props, "thumbnail", None) and streams:
                try:
                    if not os.path.exists(cache_file):
                        stream = await props.thumbnail.open_read_async()
                        if stream and stream.size > 0:
                            reader = streams.DataReader(stream)
                            await reader.load_async(stream.size)
                            buf = bytearray(stream.size)
                            reader.read_bytes(buf)
                            with open(cache_file, "wb") as f:
                                f.write(buf)
                    if os.path.exists(cache_file):
                        art_path = cache_file
                except Exception:
                    if os.path.exists(cache_file):
                        art_path = cache_file
            elif os.path.exists(cache_file):
                art_path = cache_file

            # Video vs Music Classification
            playback_type_int = 0
            try:
                if props and hasattr(props, "playback_type") and props.playback_type is not None:
                    playback_type_int = int(props.playback_type)
            except Exception:
                pass

            app_id = getattr(current_session, "source_app_user_model_id", "").lower()
            browser_apps = ("chrome", "msedge", "edge", "firefox", "brave", "opera", "vivaldi")
            is_browser = any(b in app_id for b in browser_apps)
            video_apps = ("vlc", "mpc", "potplayer", "netflix", "prime", "disney", "hulu", "movies & tv", "video")
            is_video_app = any(v in app_id for v in video_apps)
            music_apps = ("spotify", "applemusic", "itunes", "tidal", "deezer", "amazon music", "foobar", "aimp", "music")
            is_music_app = any(m in app_id for m in music_apps)

            aspect_ratio = 1.0
            if art_path and os.path.exists(art_path):
                try:
                    from PIL import Image
                    with Image.open(art_path) as im:
                        if im.height > 0:
                            aspect_ratio = im.width / float(im.height)
                except Exception:
                    pass

            is_video = False
            if playback_type_int == 2 or is_video_app:
                is_video = True
            elif is_music_app:
                is_video = False
            elif aspect_ratio >= 1.30:  # Standard 16:9 widescreen video thumbnail
                is_video = True
            elif is_browser:
                is_video = (aspect_ratio >= 1.25)

            has_media = bool(title or artist or is_playing)

            state = {
                "has_media": has_media,
                "is_playing": is_playing,
                "is_video": is_video,
                "title": title or ("Playing Video" if is_video else "Playing Audio"),
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

    def _send_media_key(self, vk_code: int):
        try:
            import ctypes
            ctypes.windll.user32.keybd_event(vk_code, 0, 0, 0)
            ctypes.windll.user32.keybd_event(vk_code, 0, 2, 0)
        except Exception:
            pass

    async def _handle_toggle(self, manager):
        if self._mock_mode:
            self._mock_playing = not self._mock_playing
            self._emit_mock_state()
            return

        cur = self._resolve_active_session(manager)
        success = False
        if cur:
            try:
                success = await cur.try_toggle_play_pause_async()
            except Exception:
                success = False

        if not success:
            self._send_media_key(0xB3)  # VK_MEDIA_PLAY_PAUSE

        await asyncio.sleep(0.12)
        await self._poll_windows_media(manager)

    async def _handle_next(self, manager):
        self._skip_grace_until = time.time() + 2.5
        if self._mock_mode:
            self._mock_index = (self._mock_index + 1) % len(MOCK_PLAYLIST)
            self._mock_position = 0
            self._emit_mock_state()
            return

        cur = self._resolve_active_session(manager)
        success = False
        if cur:
            try:
                success = await cur.try_skip_next_async()
            except Exception:
                success = False

        if not success:
            self._send_media_key(0xB0)  # VK_MEDIA_NEXT_TRACK

        await asyncio.sleep(0.2)
        await self._poll_windows_media(manager)

    async def _handle_prev(self, manager):
        self._skip_grace_until = time.time() + 2.5
        if self._mock_mode:
            self._mock_index = (self._mock_index - 1) % len(MOCK_PLAYLIST)
            self._mock_position = 0
            self._emit_mock_state()
            return

        cur = self._resolve_active_session(manager)
        success = False
        if cur:
            try:
                success = await cur.try_skip_previous_async()
            except Exception:
                success = False

        if not success:
            self._send_media_key(0xB1)  # VK_MEDIA_PREV_TRACK

        await asyncio.sleep(0.2)
        await self._poll_windows_media(manager)

    async def _handle_seek(self, manager, pos_sec: float):
        if self._mock_mode:
            self._mock_position = max(0, int(pos_sec))
            self._emit_mock_state()
            return

        cur = self._resolve_active_session(manager)
        if cur:
            try:
                ticks = int(pos_sec * 10_000_000)
                await cur.try_change_playback_position_async(ticks)
                await asyncio.sleep(0.1)
                await self._poll_windows_media(manager)
            except Exception:
                pass
            self._emit_mock_state()

    def _emit_mock_state(self):
        track = MOCK_PLAYLIST[self._mock_index]
        state = {
            "has_media": True,
            "is_playing": self._mock_playing,
            "is_video": False,
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
            state.get("is_video") != self._last_state.get("is_video") or
            state.get("album_art_path") != self._last_state.get("album_art_path") or
            state.get("has_media") != self._last_state.get("has_media")):
            self._last_state = dict(state)
            self.media_updated.emit(state)
        else:
            self._last_state["position"] = state.get("position", 0)
            self.media_updated.emit(state)
