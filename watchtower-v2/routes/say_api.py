"""
Talk to the Players (2026-09-06)
================================
Operator types a line on /game -> it is spoken over the room speakers in the
voice of the character the players are with right now.

Wraps Helm/say_to_players.py (in Pirate Original/Helm) — the desk tool built
2026-09-05. That script does the actual work: ElevenLabs TTS in the
character's own voice (Windows voice fallback) -> Helm live lane "operator"
-> the chosen speaker zone(s). Helm must be up (:52100).

"Auto" room + voice follow Unreal's RoomStatus heartbeat
(MermaidsTale/Unreal/RoomStatus, audioRoom = Ship | Jungle | Cove):
    Ship   -> ship speaker,   RedBeard
    Jungle -> jungle speaker, Evalee
    Cove   -> cove speakers,  RedBeard
    (no heartbeat / unknown) -> every room speaker, RedBeard

Zone names MUST match helm.yaml `zones:` (ship, jungle, cove,
captains_quarters, monkey, desk, all_rooms). Voice names MUST match
say_to_players.py --voice (redbeard, evalee, plain).
"""
import logging
import os
import subprocess
import sys
import threading
import time
from datetime import datetime

from flask import Blueprint, jsonify, request

import config

logger = logging.getLogger(__name__)
say_api = Blueprint("say_api", __name__, url_prefix="/api/say")

HELM_DIR = os.path.join(config.SCRIPT_DIR, "Helm")
SAY_SCRIPT = os.path.join(HELM_DIR, "say_to_players.py")

ZONES = ["all_rooms", "ship", "jungle", "cove", "captains_quarters", "monkey", "desk"]
VOICES = ["redbeard", "evalee", "plain"]
ZONE_LABELS = {
    "all_rooms": "every room", "ship": "Ship", "jungle": "Jungle", "cove": "Cove",
    "captains_quarters": "Captain's Quarters", "monkey": "Monkey Tomb", "desk": "desk speaker",
}
VOICE_LABELS = {"redbeard": "RedBeard", "evalee": "Evalee", "plain": "plain voice"}

# audioRoom (Unreal RoomStatus) -> (zone, voice). Mirrors helm.yaml lane_follow.
ROOM_AUTO = {
    "ship":   ("ship", "redbeard"),
    "jungle": ("jungle", "evalee"),
    "cove":   ("cove", "redbeard"),
}
FALLBACK_AUTO = ("all_rooms", "redbeard")

_mqtt_client = None
_lock = threading.Lock()          # one message at a time — they share ONE Helm lane
_history = []                     # newest first, max 12
_busy = {"text": None, "since": None}


def set_mqtt_client(client):
    global _mqtt_client
    _mqtt_client = client


def _port_open() -> bool:
    import socket
    try:
        with socket.create_connection(("127.0.0.1", 52100), timeout=0.5):
            return True
    except OSError:
        return False


def _helm_health() -> dict:
    """Is Helm up AND does it actually own the sound card?

    Helm publishes MermaidsTale/Audio/status every 2 s: {"ok": true, "device":
    "..."} or {"ok": false, "reason": "..."}. 2026-09-06 lesson: the lane port
    (:52100) kept answering for 30 min after the Behringer dropped off USB, so
    a port probe alone said "ready" while every line went into the void.
    The port is only consulted when WatchTower has no status message at all.
    """
    import json
    sig = (_mqtt_client.get_system_signals() if _mqtt_client else {}).get("helm_audio", {})
    age = sig.get("age_s")
    detail = sig.get("detail")
    out = {"up": False, "ok": False, "reason": None, "device": None, "age_s": age, "source": "mqtt"}
    if detail is not None and age is not None and age < 15:
        try:
            data = json.loads(detail)
        except (ValueError, TypeError):
            data = {}
        out["up"] = True
        out["ok"] = bool(data.get("ok"))
        out["device"] = data.get("device")
        out["reason"] = data.get("reason")
        if not out["ok"]:
            reason = out["reason"] or "Helm reports its audio device is not open"
            if "offline" in reason or "stopped" in reason:
                out["up"] = False
                out["reason"] = "Helm is not running"
            else:
                out["reason"] = f"Helm is running but has NO sound card: {reason}"
        return out
    # No fresh status on MQTT — fall back to the port probe (old behaviour).
    out["source"] = "port"
    out["up"] = out["ok"] = _port_open()
    if not out["up"]:
        out["reason"] = "Helm is not running (nothing on :52100)"
    return out


def _room() -> dict:
    """Where the players are, per Unreal's 5 s heartbeat."""
    sig = (_mqtt_client.get_system_signals() if _mqtt_client else {}).get("unreal_room", {})
    out = {"audio_room": None, "map": None, "age_s": sig.get("age_s"), "fresh": False}
    detail = sig.get("detail")
    if detail:
        try:
            import json
            data = json.loads(detail)
            out["audio_room"] = data.get("audioRoom")
            out["map"] = data.get("map")
        except (ValueError, TypeError):
            pass
    age = out["age_s"]
    out["fresh"] = age is not None and age < 30
    return out


def _auto_pick(room: dict):
    if room["fresh"] and room["audio_room"]:
        return ROOM_AUTO.get(str(room["audio_room"]).lower(), FALLBACK_AUTO)
    return FALLBACK_AUTO


def _context() -> dict:
    room = _room()
    zone, voice = _auto_pick(room)
    helm = _helm_health()
    return {
        "helm_up": helm["ok"],          # true only when Helm is up AND owns the Behringer
        "helm": helm,
        "script_present": os.path.isfile(SAY_SCRIPT),
        "room": room,
        "auto": {"zone": zone, "voice": voice,
                 "zone_label": ZONE_LABELS[zone], "voice_label": VOICE_LABELS[voice]},
        "zones": [{"id": z, "label": ZONE_LABELS[z]} for z in ZONES],
        "voices": [{"id": v, "label": VOICE_LABELS[v]} for v in VOICES],
        "busy": _busy["text"],
        "history": _history[:12],
    }


@say_api.route("/context")
def say_context():
    return jsonify(_context())


@say_api.route("", methods=["POST"])
def say():
    body = request.get_json(silent=True) or {}
    text = " ".join(str(body.get("text", "")).split()).strip()
    zone = str(body.get("zone") or "auto").lower()
    voice = str(body.get("voice") or "auto").lower()
    if not text:
        return jsonify({"ok": False, "error": "Nothing to say — type a line first."}), 400
    if len(text) > 600:
        return jsonify({"ok": False, "error": "Keep it under 600 characters (that's ~40 s of speech)."}), 400
    if zone != "auto" and zone not in ZONES:
        return jsonify({"ok": False, "error": f"Unknown room '{zone}'."}), 400
    if voice != "auto" and voice not in VOICES:
        return jsonify({"ok": False, "error": f"Unknown voice '{voice}'."}), 400
    if not os.path.isfile(SAY_SCRIPT):
        return jsonify({"ok": False, "error": f"say_to_players.py not found at {SAY_SCRIPT}"}), 500
    helm = _helm_health()
    if not helm["ok"]:
        hint = (" Start Helm (START bat step 2.95 or Helm\\START_HELM.bat)." if not helm["up"]
                else " Check the Behringer: USB cable + power at the PC. Helm re-opens it by itself within 2 s of it coming back.")
        return jsonify({"ok": False, "error": (helm["reason"] or "Helm not ready") + " — nothing would be heard." + hint,
                        "helm": helm}), 503

    room = _room()
    auto_zone, auto_voice = _auto_pick(room)
    if zone == "auto":
        zone = auto_zone
    if voice == "auto":
        voice = auto_voice

    # Wait our turn: a second line typed while one is still playing queues up
    # behind it instead of talking over it on the same Helm lane.
    if not _lock.acquire(timeout=90):
        return jsonify({"ok": False, "error": "Still busy with the previous message — try again."}), 429
    t0 = time.time()
    _busy.update(text=text, since=datetime.now().strftime("%H:%M:%S"))
    try:
        cmd = [sys.executable, SAY_SCRIPT, "--voice", voice, "--zone", zone, text]
        logger.info(f"SAY [{voice} -> {zone}] {text!r}")
        proc = subprocess.run(
            cmd, cwd=HELM_DIR, capture_output=True, text=True, timeout=120,
            encoding="utf-8", errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        out = (proc.stdout or "").strip()
        err = (proc.stderr or "").strip()
        ok = proc.returncode == 0
        fell_back = "falling back to the Windows voice" in out
        entry = {
            "time": datetime.now().strftime("%H:%M:%S"),
            "text": text, "zone": zone, "voice": voice,
            "zone_label": ZONE_LABELS[zone], "voice_label": VOICE_LABELS[voice],
            "ok": ok, "fell_back": fell_back,
            "secs": round(time.time() - t0, 1),
            "detail": (out if ok else (err or out))[-400:],
        }
        _history.insert(0, entry)
        del _history[12:]
        if not ok:
            logger.warning(f"SAY failed rc={proc.returncode}: {err[-300:] or out[-300:]}")
        return jsonify({"ok": ok, "sent": entry,
                        "error": None if ok else (err.splitlines()[-1] if err else out[-200:] or "say_to_players.py failed")})
    except subprocess.TimeoutExpired:
        return jsonify({"ok": False, "error": "Timed out after 120 s (ElevenLabs hung?)."}), 504
    finally:
        _busy.update(text=None, since=None)
        _lock.release()
