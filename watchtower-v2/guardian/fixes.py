"""
Guardian Fix Registry
======================
Software-only remediations for known failure modes. Every fix:
  - is ONLY run after the operator clicks Approve in the Game Control tab
    (the API call itself is the permission grant),
  - explains the problem and the action in plain English first,
  - is logged to guardian_actions + the debug log,
  - never publishes to a /command or /reset topic (reboot-loop landmine),
  - never pretends it can fix hardware — those checks carry human_fix
    instructions instead.

Each fix's run(ctx) returns {"ok": bool, "output": str}.
`ctx` is {"mqtt": MQTTClient or None}.
"""

import os
import sys
import time
import logging
import subprocess

import config

logger = logging.getLogger(__name__)

AI_BRAIN_CMD_TOPIC = "MermaidsTale/RedBeard/Cmd"


def _run(cmd, timeout=90, cwd=None):
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=timeout, cwd=cwd)
        out = ((proc.stdout or "") + (proc.stderr or "")).strip()
        return proc.returncode == 0, out[-2000:]
    except subprocess.TimeoutExpired:
        return False, f"timed out after {timeout}s"
    except Exception as e:  # noqa: BLE001
        return False, str(e)


# ─────────────────────────────────────────────
# Fix implementations
# ─────────────────────────────────────────────

def fix_clear_retained(ctx):
    """Wipe every retained MermaidsTale/# topic + all /command //reset topics,
    using the same curated script the launcher runs (safe by design)."""
    script = os.path.join(config.SCRIPT_DIR, "clear_retained_mqtt.py")
    if not os.path.exists(script):
        return {"ok": False, "output": "clear_retained_mqtt.py not found"}
    ok1, out1 = _run([sys.executable, script, "wildcard"], cwd=config.SCRIPT_DIR)
    ok2, out2 = _run([sys.executable, script, "commands"], cwd=config.SCRIPT_DIR)
    # Resync the landmine tracker from the broker's actual retained store —
    # wipes done while WatchTower is connected arrive with retain=0 and are
    # otherwise invisible to it (the "still flagging after a wipe" bug).
    mc = ctx.get("mqtt")
    if mc:
        mc.refresh_retained_landmines()
    return {"ok": ok1 and ok2, "output": f"wildcard: {out1}\ncommands: {out2}"}


def fix_restart_m3(ctx):
    """Kill and relaunch Mystery.exe — the standing fix for wedged M3 audio."""
    _run(["taskkill", "/F", "/IM", f"{config.M3_PROCESS_NAME}.exe"], timeout=20)
    time.sleep(2)
    try:
        subprocess.Popen(f'start "" "{config.MYTHRIC_PATH}"', shell=True)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "output": f"relaunch failed: {e}"}
    time.sleep(4)
    return {"ok": True, "output": "Mystery.exe restarted — give it ~30s to reload the story, "
                                  "then run the checklist again"}


def fix_m3_volume(ctx):
    """Force every Mystery.exe mixer session to 100% and unmuted."""
    if not os.path.exists(config.SVCL_PATH):
        return {"ok": False, "output": "SoundVolumeView.exe not found"}
    ok1, out1 = _run([config.SVCL_PATH, "/SetVolume", "Mystery.exe", "100"], timeout=20)
    ok2, out2 = _run([config.SVCL_PATH, "/Unmute", "Mystery.exe"], timeout=20)
    return {"ok": ok1 and ok2,
            "output": "Mystery.exe mixer forced to 100% and unmuted on every device"}


def fix_default_output(ctx):
    """Pin the Windows default playback device to the OUT 1-10 Behringer master
    (all three roles — console/multimedia/communications)."""
    if not os.path.exists(config.SVCL_PATH):
        return {"ok": False, "output": "SoundVolumeView.exe not found"}
    results = []
    for role in ("0", "1", "2"):
        ok, _ = _run([config.SVCL_PATH, "/SetDefault",
                      r"BEHRINGER UMC 1820\Device\OUT 1-10\Render", role], timeout=20)
        results.append(ok)
    return {"ok": all(results),
            "output": "Default playback pinned to OUT 1-10 (BEHRINGER) on all three roles"}


def _make_pip_fix(package):
    def fn(ctx):
        ok, out = _run([sys.executable, "-m", "pip", "install", package], timeout=300)
        return {"ok": ok, "output": out}
    return fn


def fix_restart_brain(ctx):
    """Ask the AI machine's brain_watchdog to relaunch the AI character brain."""
    mc = ctx.get("mqtt")
    if not mc or not mc.connected:
        return {"ok": False, "output": "MQTT not connected — can't reach the brain watchdog"}
    result = mc.publish_raw(AI_BRAIN_CMD_TOPIC, "restart")
    if "error" in result:
        return {"ok": False, "output": result["error"]}
    return {"ok": True, "output": f"restart published on {AI_BRAIN_CMD_TOPIC} — "
                                  "give the brain ~30s to come back"}


# ─────────────────────────────────────────────
# Registry
# ─────────────────────────────────────────────
# title/problem/action are the plain-English text shown on the Approve dialog.

FIXES = {
    "clear_retained": {
        "title": "Wipe stale MQTT leftovers",
        "problem": "Old retained messages are sitting on the broker and will replay "
                   "into devices the moment they reconnect — that's how games "
                   "self-start and boards reboot-loop.",
        "action": "Run the same safe wipe the launcher uses (clear_retained_mqtt.py "
                  "wildcard + commands). Device status repopulates within seconds.",
        "run": fix_clear_retained,
    },
    "restart_m3": {
        "title": "Restart the M3 story engine",
        "problem": "Mystery.exe has been running long enough that its audio is at "
                   "risk of silently dying mid-game (known long-run bug).",
        "action": "Close Mystery.exe and start it fresh. Takes about 30 seconds; "
                  "no story data is lost.",
        "run": fix_restart_m3,
    },
    "restart_m3_full": {
        "title": "Full M3 restart — rebind audio devices",
        "problem": "Mystery.exe locks in its speaker numbers ONCE, at startup. The "
                   "Windows device list has shifted since then (projectors going to "
                   "sleep or waking up does this), so M3 would fire sound effects "
                   "into the WRONG rooms.",
        "action": "Fully close every Mystery.exe process and relaunch it so it "
                  "re-binds to the current device list — the safe fix from "
                  "ROUTING_MAP.md section 8 (never the enforcer). Takes ~30s, no "
                  "story data is lost. Do NOT use mid-game. Re-run the checklist "
                  "after.",
        "run": fix_restart_m3,
    },
    "fix_m3_volume": {
        "title": "Restore M3's mixer volume",
        "problem": "Windows remembered a turned-down (or muted) volume slider for the "
                   "story engine and reapplies it every launch — sound effects "
                   "come out near-silent.",
        "action": "Force Mystery.exe to 100% volume and unmuted on every output device.",
        "run": fix_m3_volume,
    },
    "fix_default_output": {
        "title": "Re-pin the Windows default speaker",
        "problem": "The Windows default output drifted off the Behringer master — "
                   "Unreal's opening soundtrack plays to the default, so it's "
                   "currently going to the wrong (possibly dead) output.",
        "action": "Set 'OUT 1-10 (BEHRINGER UMC 1820)' as the Windows default "
                  "playback device on all three roles.",
        "run": fix_default_output,
    },
    "pip_openpyxl": {
        "title": "Install the missing Excel library",
        "problem": "Python can't load 'openpyxl'. The AI voiceline bridge needs it and "
                   "silently disables itself without it — scripted character lines "
                   "just don't play.",
        "action": "Run: pip install openpyxl",
        "run": _make_pip_fix("openpyxl"),
    },
    "pip_paho": {
        "title": "Install the missing MQTT library",
        "problem": "Python can't load 'paho-mqtt'; every helper script needs it to talk "
                   "to the room.",
        "action": "Run: pip install paho-mqtt",
        "run": _make_pip_fix("paho-mqtt"),
    },
    "pip_pyaudio": {
        "title": "Install the missing audio library",
        "problem": "Python can't load 'pyaudio'; the AI can't hear mics or route audio "
                   "without it.",
        "action": "Run: pip install pyaudio",
        "run": _make_pip_fix("pyaudio"),
    },
    "restart_brain": {
        "title": "Restart the AI character brain",
        "problem": "The AI character process has gone quiet.",
        "action": "Publish a restart command to the brain watchdog (same as the "
                  "dashboard's Reset Brain button).",
        "run": fix_restart_brain,
    },
}


def get_fix_info(fix_id):
    fix = FIXES.get(fix_id)
    if not fix:
        return None
    return {"id": fix_id, "title": fix["title"],
            "problem": fix["problem"], "action": fix["action"]}
