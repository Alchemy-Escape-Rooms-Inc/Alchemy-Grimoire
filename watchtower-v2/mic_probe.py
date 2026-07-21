#!/usr/bin/env python3
"""
mic_probe.py — Live Pirate Ship microphone health probe for WatchTower.
=======================================================================
The Pirate Ship mic is NOT an MQTT device (it doesn't PING/PONG like the
ESP32s), so it can't ride the normal device-status pipeline. Instead this
module opens the SAME physical mic Red Beard listens through and measures
its live input level in a background thread, then exposes a snapshot the
API merges into /api/status under a top-level "mic" key.

Why this exists: the recurring "Red Beard goes deaf" failure (mic unplugged
/ muted / zero gain / held by another app / wrong device enumeration) used
to only get caught by the interactive mic_check.py at launch. This makes it
a LIVE, always-on tile on the WatchTower dashboard so the GM can glance and
see the mic is hearing — at any point, not just at startup.

Device resolution + RMS math are deliberately the SAME as mic_check.py /
camera_conversation_client.py so this can NEVER drift from what the AI opens.

Status semantics exposed in snapshot():
  status: "online"  -> stream open AND a real voice/signal seen recently
          "idle"    -> stream open, device healthy, but quiet right now
          "offline" -> device not found, or stream won't open (THE bad one)
          "unknown" -> probe hasn't completed its first read yet
"""
import sys
import os
import time
import struct
import threading
import logging

logger = logging.getLogger(__name__)

# --- Resolve the mic the SAME way the AI does -------------------------------
# Pull the AI's own device-resolution helper + canonical name so this probe
# opens EXACTLY the device Red Beard opens. The AI System lives next to the
# game; add it to sys.path so the import works regardless of CWD. If that
# import fails we fall back to the well-known name + a local resolver so the
# probe still works (belt-and-suspenders, same pattern as mic_check.py).
_AI_PATH = r"C:\Users\Alchemy\Desktop\EscapeRoom Pirate Original\AI Character System"

MIC_SUBSTR = "Pirate Ship Microphone"
_find_input_device_index = None
try:
    if _AI_PATH not in sys.path and os.path.isdir(_AI_PATH):
        sys.path.insert(0, _AI_PATH)
    from camera_conversation_client import (  # type: ignore
        find_input_device_index as _find_input_device_index,
        INPUT_MIC_DEVICE_MAP,
    )
    MIC_SUBSTR = INPUT_MIC_DEVICE_MAP.get("redbeard", MIC_SUBSTR)
    logger.info("mic_probe: using AI device resolver, mic substr '%s'", MIC_SUBSTR)
except Exception as e:  # noqa: BLE001 - any import/path problem -> fall back
    logger.warning("mic_probe: could not import AI mic config (%s); using default name", e)

# --- Capture / level config (matches mic_check.py) --------------------------
RATE = 16000          # match rtsp_audio_interface input_sample_rate
CHUNK = 1024
SILENT_RMS = 120      # below this = effectively dead/quiet
SPEAK_OK = 600        # a peak above this = a real voice/signal was heard
RECENT_VOICE_SECS = 4.0   # how long a "voice seen" keeps status == online
REOPEN_BACKOFF = 3.0      # seconds to wait before retrying a failed open


def _rms(block: bytes) -> float:
    n = len(block) // 2
    if n == 0:
        return 0.0
    samples = struct.unpack(f"<{n}h", block[: n * 2])
    return (sum(s * s for s in samples) / n) ** 0.5


class MicProbe:
    """Background thread that keeps the Pirate Ship mic open and measures level."""

    def __init__(self):
        self._lock = threading.Lock()
        self._thread = None
        self._stop = threading.Event()

        # Snapshot fields (guarded by _lock)
        self._present = False        # device exists in the enumeration
        self._live = False           # stream currently open and reading
        self._device_name = None
        self._device_index = None
        self._level = 0.0            # most recent RMS
        self._peak = 0.0            # rolling peak (decays)
        self._last_voice_ts = 0.0   # monotonic time we last saw SPEAK_OK
        self._last_read_ts = 0.0    # monotonic time of last successful read
        self._error = None
        self._started = False        # has the loop completed at least one cycle

    # -- lifecycle -----------------------------------------------------------
    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="mic-probe", daemon=True)
        self._thread.start()
        logger.info("mic_probe: probe thread started")

    def stop(self):
        self._stop.set()

    # -- the probe loop ------------------------------------------------------
    def _resolve_index(self, p):
        """Find the mic index the same way the AI does, with a local fallback."""
        idx = None
        if _find_input_device_index is not None:
            try:
                idx = _find_input_device_index(MIC_SUBSTR)
            except Exception as e:  # noqa: BLE001
                logger.debug("mic_probe: AI resolver error (%s); using local scan", e)
                idx = None
        if idx is None:
            target = MIC_SUBSTR.lower()
            for i in range(p.get_device_count()):
                info = p.get_device_info_by_index(i)
                if info.get("maxInputChannels", 0) > 0 and target in info["name"].lower():
                    idx = i
                    break
        return idx

    def _run(self):
        try:
            import pyaudio
        except Exception as e:  # noqa: BLE001
            with self._lock:
                self._error = f"pyaudio unavailable: {e}"
                self._started = True
            logger.warning("mic_probe: %s", self._error)
            return

        while not self._stop.is_set():
            p = None
            stream = None
            try:
                p = pyaudio.PyAudio()
                idx = self._resolve_index(p)

                if idx is None:
                    with self._lock:
                        self._present = False
                        self._live = False
                        self._device_index = None
                        self._device_name = None
                        self._error = f"mic '{MIC_SUBSTR}' not found"
                        self._level = 0.0
                        self._started = True
                    p.terminate()
                    self._sleep(REOPEN_BACKOFF)
                    continue

                name = p.get_device_info_by_index(idx)["name"]
                try:
                    stream = p.open(
                        format=p.get_format_from_width(2), channels=1, rate=RATE,
                        input=True, input_device_index=idx, frames_per_buffer=CHUNK,
                    )
                except Exception as e:  # noqa: BLE001 - exists but won't open
                    with self._lock:
                        self._present = True
                        self._live = False
                        self._device_index = idx
                        self._device_name = name
                        self._error = f"stream won't open: {e}"
                        self._level = 0.0
                        self._started = True
                    if p:
                        p.terminate()
                    self._sleep(REOPEN_BACKOFF)
                    continue

                with self._lock:
                    self._present = True
                    self._live = True
                    self._device_index = idx
                    self._device_name = name
                    self._error = None
                logger.info("mic_probe: listening on '%s' (index %s)", name, idx)

                # Read until told to stop or the stream faults.
                while not self._stop.is_set():
                    block = stream.read(CHUNK, exception_on_overflow=False)
                    level = _rms(block)
                    now = time.monotonic()
                    with self._lock:
                        self._level = level
                        # peak decays slowly so the meter doesn't stick high
                        self._peak = max(level, self._peak * 0.9)
                        self._last_read_ts = now
                        if level >= SPEAK_OK:
                            self._last_voice_ts = now
                        self._started = True

            except Exception as e:  # noqa: BLE001 - stream fault mid-read, etc.
                with self._lock:
                    self._live = False
                    self._error = f"read fault: {e}"
                    self._level = 0.0
                logger.warning("mic_probe: %s — reopening", e)
            finally:
                try:
                    if stream is not None:
                        stream.stop_stream()
                        stream.close()
                except Exception:  # noqa: BLE001
                    pass
                try:
                    if p is not None:
                        p.terminate()
                except Exception:  # noqa: BLE001
                    pass
            self._sleep(REOPEN_BACKOFF)

    def _sleep(self, secs):
        # Interruptible sleep so stop() is responsive.
        self._stop.wait(secs)

    # -- snapshot for the API ------------------------------------------------
    def snapshot(self) -> dict:
        now = time.monotonic()
        with self._lock:
            if not self._started:
                status = "unknown"
            elif not self._present or not self._live:
                status = "offline"
            elif (now - self._last_voice_ts) <= RECENT_VOICE_SECS:
                status = "online"
            else:
                status = "idle"

            level = self._level
            peak = self._peak
            # how long since we last had a real read (staleness guard)
            age = (now - self._last_read_ts) if self._last_read_ts else None
            return {
                "name": "Pirate Ship Microphone",
                "device_name": self._device_name,
                "device_index": self._device_index,
                "icon": "🎤",
                "color": "#4A90D9",
                "room": "Ship Deck",
                "status": status,
                "present": self._present,
                "live": self._live,
                "level": round(level, 1),
                "peak": round(peak, 1),
                "silent_rms": SILENT_RMS,
                "speak_ok": SPEAK_OK,
                "error": self._error,
                "age_secs": round(age, 1) if age is not None else None,
            }


# Module-level singleton the app wires up once.
probe = MicProbe()
