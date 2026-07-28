"""
Guardian Checklist Definitions
================================
Every item that must be true before a game of A Mermaid's Tale can start.
Each check returns (status, detail) where status is one of:
    "pass"  — item verified good
    "fail"  — item broken (blocks game start if severity is "blocking")
    "warn"  — item off but the launcher or a human can absorb it
    "skip"  — item could not be evaluated (missing dep / not applicable now)

Checks receive a shared `ctx` dict: {"mqtt": MQTTClient} plus anything a
check caches for later checks (e.g. the device ping sweep results).

Severity:
    "blocking" — a fail here means the game WILL go wrong; start is refused.
    "advisory" — degraded-but-playable, or the START bat itself repairs it.
                 (config.GUARDIAN_BLOCK_ON_WARN=True makes these block too.)
"""

import os
import csv
import sys
import time
import socket
import shutil
import logging
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Callable, Optional

import config
from mqtt import DeviceStatus, DeviceType

logger = logging.getLogger(__name__)

# BAC controllers heartbeat every 5 min (HEARTBEAT_STANDARD); allow 2 cycles + slack.
BAC_HEARTBEAT_FRESH_S = 630

# When this module was loaded ≈ when WatchTower booted (used to tell "BAC is
# dead" apart from "WatchTower restarted and hasn't heard a heartbeat yet").
_PROCESS_START = time.time()


@dataclass
class Check:
    id: str
    title: str
    category: str
    severity: str                     # "blocking" | "advisory"
    layman: str                       # plain-English what/why for the operator
    func: Callable                    # (ctx) -> (status, detail)
    fix_id: Optional[str] = None      # auto-fix in guardian.fixes, if any
    human_fix: Optional[str] = None   # plain instructions when only a human can fix it
    ignorable: bool = False           # operator may Ignore a fail/warn for one run


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _tcp_check(host: str, port: int, timeout=4.0):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return "pass", f"{host}:{port} answered"
    except OSError as e:
        return "fail", f"{host}:{port} unreachable ({e})"


def _powershell(cmd: str, timeout=10) -> str:
    return subprocess.run(
        ["powershell", "-NoProfile", "-Command", cmd],
        capture_output=True, text=True, timeout=timeout,
        creationflags=subprocess.CREATE_NO_WINDOW,
    ).stdout.strip()


def _process_running(name: str) -> bool:
    out = _powershell(
        f"if (Get-Process -Name {name} -ErrorAction SilentlyContinue) "
        "{ 'YES' } else { 'NO' }"
    )
    return out == "YES"


# ─────────────────────────────────────────────
# Connections
# ─────────────────────────────────────────────

def check_broker_tcp(ctx):
    return _tcp_check(config.MQTT_BROKER, config.MQTT_PORT)


def check_wt_mqtt(ctx):
    mc = ctx.get("mqtt")
    if mc and mc.connected:
        return "pass", "WatchTower is live on the broker"
    return "fail", "WatchTower's own MQTT connection is down — device checks are blind"


def check_internet_voices(ctx):
    host, port = config.ELEVENLABS_ENDPOINT
    status, detail = _tcp_check(host, port, timeout=6.0)
    return status, detail


def check_a2f_endpoint(ctx):
    host, port = config.A2F_ENDPOINT
    return _tcp_check(host, port, timeout=4.0)


def check_docker(ctx):
    try:
        rc = subprocess.run(["docker", "version"], capture_output=True, timeout=20).returncode
        if rc == 0:
            return "pass", "Docker daemon answering"
        return "warn", "Docker daemon not responding — the launcher will start Docker Desktop itself"
    except FileNotFoundError:
        return "warn", "docker CLI not found on PATH"
    except subprocess.TimeoutExpired:
        return "warn", "docker version timed out — daemon likely starting up"


# ─────────────────────────────────────────────
# Files & Builds
# ─────────────────────────────────────────────

def check_game_build(ctx):
    try:
        names = sorted(
            (n for n in os.listdir(config.UNREAL_BUILDS_DIR)
             if n.startswith("Windows_") and n.endswith("_DEV")),
            reverse=True,
        )
    except OSError as e:
        return "fail", f"builds folder unreadable: {e}"
    for n in names:
        if os.path.exists(os.path.join(config.UNREAL_BUILDS_DIR, n, "EscapeRoom.exe")):
            ctx["newest_build"] = n
            return "pass", f"launching {n}"
    return "fail", "no build folder with EscapeRoom.exe found"


def check_bats_exist(ctx):
    missing = [p for p in (config.START_BAT, config.STOP_BAT) if not os.path.exists(p)]
    if missing:
        return "fail", "missing: " + ", ".join(os.path.basename(m) for m in missing)
    return "pass", "START + STOP launchers on disk"


def check_launcher_scripts(ctx):
    missing = [s for s in config.REQUIRED_LAUNCHER_SCRIPTS
               if not os.path.exists(os.path.join(config.SCRIPT_DIR, s))]
    missing += [f"AI\\{s}" for s in config.REQUIRED_AI_SCRIPTS
                if not os.path.exists(os.path.join(config.AI_DIR, s))]
    if missing:
        return "fail", "missing: " + ", ".join(missing)
    total = len(config.REQUIRED_LAUNCHER_SCRIPTS) + len(config.REQUIRED_AI_SCRIPTS)
    return "pass", f"all {total} launch scripts present"


def check_mythric_installed(ctx):
    if os.path.exists(config.MYTHRIC_PATH):
        return "pass", "Mystery.exe installed"
    return "fail", f"not found: {config.MYTHRIC_PATH}"


def _amt_blank_topics(path):
    """{element-name: True} for every element with topic=\"\" in an AMT xml."""
    tree = ET.parse(path)
    out = set()
    for elem in tree.iter():
        if "topic" in elem.attrib and elem.attrib["topic"].strip() == "":
            out.add(elem.attrib.get("name") or elem.attrib.get("id") or elem.tag)
    return out


def check_amt_xml(ctx):
    """The live story file. An editor save can WIPE a device's topic to \"\",
    deafening its triggers (the 2026-07-03 item3 save hit Cannons/BattleEnded/
    MapSolved). Some devices are legitimately topic-less (audio-only), so a
    wipe = blank in LIVE but non-blank in the newest backup."""
    import glob
    path = config.AMT_XML_LIVE
    if not os.path.exists(path):
        return "fail", f"live story file missing: {path}"
    try:
        live_blank = _amt_blank_topics(path)
    except ET.ParseError as e:
        return "fail", f"AMT.xml does not parse: {e}"

    baks = sorted(glob.glob(os.path.join(config.SCRIPT_DIR, "logs", "*AMT*")),
                  key=os.path.getmtime, reverse=True)
    if not baks:
        return "pass", (f"story file parses ({len(live_blank)} known topic-less devices; "
                        "no backup found to diff against)")
    try:
        bak_blank = _amt_blank_topics(baks[0])
    except ET.ParseError:
        return "pass", f"story file parses (newest backup unreadable, wipe-diff skipped)"
    wiped = live_blank - bak_blank
    if wiped:
        shown = ", ".join(sorted(wiped)[:8]) + ("…" if len(wiped) > 8 else "")
        return "fail", (f"{len(wiped)} device topic(s) WIPED vs backup "
                        f"{os.path.basename(baks[0])}: {shown}")
    return "pass", f"story file parses, no wiped topics vs {os.path.basename(baks[0])}"


def check_disk_space(ctx):
    try:
        free_gb = shutil.disk_usage("C:\\").free / (1024 ** 3)
    except OSError as e:
        return "skip", f"could not read disk usage: {e}"
    if free_gb < config.GUARDIAN_MIN_FREE_GB:
        return "warn", f"only {free_gb:.1f} GB free on C: (floor {config.GUARDIAN_MIN_FREE_GB} GB)"
    return "pass", f"{free_gb:.0f} GB free on C:"


# ─────────────────────────────────────────────
# Software Environment
# ─────────────────────────────────────────────

def _make_module_check(module: str):
    def fn(ctx):
        rc = subprocess.run(
            [sys.executable, "-c", f"import {module}"],
            capture_output=True, timeout=30,
        ).returncode
        if rc == 0:
            return "pass", f"{module} imports"
        return "fail", f"'import {module}' fails in {os.path.basename(sys.executable)}"
    return fn


def check_clickup_token(ctx):
    if config.CLICKUP_API_TOKEN:
        return "pass", "task sync configured"
    return "warn", "no ClickUp token — issues won't sync to task list"


# ─────────────────────────────────────────────
# Audio
# ─────────────────────────────────────────────

def check_out_master(ctx):
    try:
        out = _powershell(
            "$d = Get-AudioDevice -List | Where-Object { $_.Type -eq 'Playback' "
            "-and $_.Name -match 'OUT 1-10' } | Select-Object -First 1; "
            "if ($d) { $d.Name } else { 'MISSING' }", timeout=15)
    except Exception as e:  # noqa: BLE001
        return "skip", f"audio device query failed: {e}"
    if out and out != "MISSING":
        return "pass", out
    return "fail", "OUT 1-10 room-wide master not in Windows playback devices"


def check_default_output(ctx):
    """Unreal's opening ambience plays to the Windows DEFAULT output until the
    game's first per-room swap (ROUTING_MAP §4) — the default must be the
    room-wide Behringer master. Driver/Windows updates love drifting it
    (2026-07-24: default drifted to a 6%-volume projector endpoint = silent
    opening soundtrack)."""
    try:
        out = _powershell(
            "$d = Get-AudioDevice -List | Where-Object { $_.Type -eq 'Playback' "
            "-and $_.Default } | Select-Object -First 1; "
            "if ($d) { $d.Name } else { 'NONE' }", timeout=15)
    except Exception as e:  # noqa: BLE001
        return "skip", f"audio device query failed: {e}"
    if out and "OUT 1-10" in out:
        return "pass", f"default output = {out}"
    return "fail", (f"Windows default output is '{out}' — must be OUT 1-10 "
                    "(BEHRINGER master); Unreal's opening ambience follows the default")


def check_pirate_mic(ctx):
    try:
        out = _powershell(
            "$d = Get-AudioDevice -List | Where-Object { $_.Type -eq 'Recording' "
            "-and $_.Name -match 'Pirate Ship' } | Select-Object -First 1; "
            "if ($d) { $d.Name } else { 'MISSING' }", timeout=15)
    except Exception as e:  # noqa: BLE001
        return "skip", f"audio device query failed: {e}"
    if out and out != "MISSING":
        return "pass", out
    return "fail", "'Pirate Ship Microphone' not in Windows recording devices"


def check_m3_app_volume(ctx):
    """Windows remembers Mystery.exe's mixer volume PER DEVICE and reapplies
    it forever — a 15% Ship slider silenced all M3 SFX across restarts."""
    if not os.path.exists(config.SVCL_PATH):
        return "skip", "SoundVolumeView not installed — can't audit per-app volume"
    if not _process_running(config.M3_PROCESS_NAME):
        return "skip", "Mystery.exe not running yet — will be checked after launch"
    dump = os.path.join(tempfile.gettempdir(), "guardian_svv.csv")
    try:
        subprocess.run([config.SVCL_PATH, "/scomma", dump], capture_output=True, timeout=20)
        problems = []
        with open(dump, newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                if "Mystery.exe" not in (row.get("Process Path") or ""):
                    continue
                vol_txt = (row.get("Volume Percent") or "").rstrip("%")
                vol = float(vol_txt) if vol_txt else None
                muted = (row.get("Muted") or "").lower() == "yes"
                dev = row.get("Device Name") or "?"
                if muted:
                    problems.append(f"MUTED on {dev}")
                elif vol is not None and vol < config.M3_APP_VOLUME_MIN:
                    problems.append(f"{vol:.0f}% on {dev}")
        if problems:
            return "fail", "; ".join(problems)
        return "pass", f"all Mystery.exe sessions ≥{config.M3_APP_VOLUME_MIN:.0f}%"
    except Exception as e:  # noqa: BLE001
        return "skip", f"volume audit failed: {e}"


def check_routing_verify(ctx):
    """verify_routing.py cross-checks M3 AMT.xml PC:X refs, Unreal room
    substrings, and the AI output map against the live device list. Read-only."""
    script = os.path.join(config.SCRIPT_DIR, "verify_routing.py")
    if not os.path.exists(script):
        return "skip", "verify_routing.py not found"
    try:
        proc = subprocess.run(
            [sys.executable, script], cwd=config.SCRIPT_DIR,
            capture_output=True, text=True, timeout=120,
        )
    except subprocess.TimeoutExpired:
        return "fail", "verify_routing.py timed out (120s)"
    if proc.returncode == 0:
        return "pass", "M3 / Unreal / AI audio routing all agree with the live device list"
    if proc.returncode == 3:
        return "skip", "routing verify dependency missing (exit 3)"
    tail = "\n".join((proc.stdout or "").strip().splitlines()[-6:])
    # Only real [FAIL] lines — the "RESULT: N FAIL / ..." summary line used to
    # sneak into this list and poison the all-M3 triage below (button never
    # showed even when a full M3 restart was the whole cure).
    fails = [ln.strip() for ln in (proc.stdout or "").splitlines()
             if ln.strip().startswith("[FAIL]")]
    detail = "; ".join(fails[:4]) or tail or f"exit {proc.returncode}"
    if len(fails) > 4:
        detail += f" ...and {len(fails) - 4} more fails"
    # Failure triage (ROUTING_MAP.md §8): if EVERY fail is an M3-* index
    # mismatch — no missing endpoints ("matches NO live"), no Behringer
    # rename ("OUT 0X" raw names) — then M3 is simply holding a stale device
    # list and the documented cure is a FULL Mystery.exe restart. Offer that
    # as a one-click fix. Anything else still needs human eyes first (wake
    # the projectors / run the rename script), so no button.
    all_text = " ".join(fails)  # triage against EVERY fail, not just the 4 shown
    if fails and all("M3-" in f for f in fails) \
            and "matches NO live" not in all_text and "OUT 0" not in all_text:
        return ("fail",
                detail + " || All endpoints present — M3 is holding a stale device "
                         "list; the one-click Full M3 restart below is the fix.",
                "restart_m3_full")
    # Explain WHY there is no one-click fix, so the operator isn't left hunting
    # for a button that is deliberately withheld.
    if fails:
        kinds = sorted({f.split()[1] for f in fails if len(f.split()) > 1})
        detail += (" || NO one-click fix on purpose: failure types ["
                   + ", ".join(kinds) + "] mean endpoints are missing/renamed "
                   "or names drifted -- the device list itself changed, so an M3 "
                   "restart alone would NOT cure it. Fix names/endpoints per "
                   "ROUTING_MAP.md section 8 FIRST, then do the full M3 restart.")
    return "fail", detail


# ─────────────────────────────────────────────
# MQTT State
# ─────────────────────────────────────────────

def check_retained_landmines(ctx):
    mc = ctx.get("mqtt")
    if not mc:
        return "skip", "no MQTT client"
    with mc.lock:
        mines = dict(mc.retained_landmines)
    if not mines:
        return "pass", "no retained GameStart / command / reset topics on the broker"
    shown = ", ".join(sorted(mines)[:5]) + ("…" if len(mines) > 5 else "")
    return "warn", f"{len(mines)} retained landmine(s): {shown} (the launcher wipes these, or fix now)"


def check_boot_loops(ctx):
    """Fail only on an ACTIVE loop (a boot event in the last QUIET_S seconds).
    A board that looped but has been quiet since the fix is recovered — old
    events sitting in the 10-min window must not keep failing the gate."""
    mc = ctx.get("mqtt")
    if not mc:
        return "skip", "no MQTT client"
    loops = mc.get_pregame_signals()["boot_loops"]
    active = {d: i for d, i in loops.items()
              if i["last_age_s"] <= config.PREGAME_BOOTLOOP_QUIET_S}
    if active:
        detail = ", ".join(f"{d} ({i['count']}x, last {int(i['last_age_s'])}s ago)"
                           for d, i in sorted(active.items()))
        return "fail", f"actively reboot-looping: {detail}"
    if loops:
        detail = ", ".join(f"{d} quiet for {int(i['last_age_s'])}s after {i['count']} reboots"
                           for d, i in sorted(loops.items()))
        return "pass", f"loop STOPPED (recovered): {detail}"
    return "pass", "no boards reboot-looping"


def check_prop_positions(ctx):
    mc = ctx.get("mqtt")
    if not mc:
        return "skip", "no MQTT client"
    props = mc.get_pregame_signals()["props"]
    wrong, unseen = [], 0
    for row in config.PREGAME_PROP_STATES:
        state = props.get(row["topic"])
        if state is None:
            unseen += 1
            continue
        if row["expect"].lower() not in state["payload"].lower():
            wrong.append(f"{row['label']} = '{state['payload'][:40]}'")
    if wrong:
        return "fail", "; ".join(wrong)
    note = f" ({unseen} not reported yet)" if unseen else ""
    return "pass", f"props in start position{note}"


# ─────────────────────────────────────────────
# Game Systems
# ─────────────────────────────────────────────

def check_m3_freshness(ctx):
    """Stale Mystery.exe is the #1 known killer: audio wedges silently on
    long runs. If it's up past the limit, restart before the game."""
    out = _powershell(
        f"$p = Get-Process -Name {config.M3_PROCESS_NAME} -ErrorAction SilentlyContinue "
        "| Select-Object -First 1; if ($p) { $p.StartTime.ToString('o') } else { 'NOT_RUNNING' }")
    if out == "NOT_RUNNING":
        return "pass", "Mystery.exe not running — launcher starts it fresh"
    try:
        from datetime import datetime
        started = datetime.fromisoformat(out)
        uptime_h = (datetime.now(started.tzinfo) - started).total_seconds() / 3600.0
    except Exception:  # noqa: BLE001
        return "skip", f"could not parse Mystery.exe start time: {out!r}"
    if uptime_h >= config.M3_RESTART_AFTER_HOURS:
        return "fail", (f"Mystery.exe up {uptime_h:.1f}h "
                        f"(limit {config.M3_RESTART_AFTER_HOURS}h) — audio wedge risk")
    return "pass", f"Mystery.exe up {uptime_h:.1f}h"


def check_no_game_running(ctx):
    mc = ctx.get("mqtt")
    signals = mc.get_system_signals() if mc else {}
    m3 = signals.get("m3", {})
    if m3.get("detail") == "Running" and m3.get("age_s") is not None and m3["age_s"] <= 120:
        return "fail", "M3 story state is 'Running' — a game looks live right now"
    if _process_running(config.UNREAL_PROCESS_NAME):
        return "warn", "a stale EscapeRoom.exe is up — the launcher clears it automatically"
    return "pass", "no game in progress"


# ─────────────────────────────────────────────
# Device sweep (one checklist item per prop board)
# ─────────────────────────────────────────────

def _ensure_device_sweep(ctx):
    """Ping every ESP32, wait for answers, then RETRY the silent ones with a
    generous wait. A power-saving ESP32 can take >10s to process its first
    PING after idle (BarrelPiston, 2026-07-10: 12s first reply, 200ms after)
    — the first ping wakes it, the retry proves it. Late PONGs inside
    LATE_PONG_GRACE_S flip a board back online (mqtt module), so the retry
    wait just has to outlast the wake-up. BACs are judged on their passive
    heartbeat instead (pinging them only wipes their known state)."""
    if ctx.get("sweep_done"):
        return
    mc = ctx["mqtt"]
    esp_names = [n for n, d in mc.devices.items() if d.device_type == DeviceType.ESP32]

    for name in esp_names:
        mc.ping_device(name)
    deadline = time.time() + config.ESP32_PING_TIMEOUT + 2
    while time.time() < deadline:
        with mc.lock:
            testing = any(d.status == DeviceStatus.TESTING for d in mc.devices.values())
        if not testing:
            break
        time.sleep(0.4)
    mc.check_timeouts()

    with mc.lock:
        stragglers = [n for n in esp_names
                      if mc.devices[n].status == DeviceStatus.OFFLINE]
    if stragglers:
        for name in stragglers:
            mc.ping_device(name)
        deadline = time.time() + 15  # outlast a slow wake, not just the 3s timeout
        while time.time() < deadline:
            mc.check_timeouts()
            with mc.lock:
                if all(mc.devices[n].status == DeviceStatus.ONLINE for n in stragglers):
                    break
            time.sleep(0.5)
        mc.check_timeouts()
    ctx["sweep_done"] = True


def _make_device_check(name: str):
    def fn(ctx):
        mc = ctx.get("mqtt")
        if not mc or not mc.connected:
            return "skip", "MQTT down — can't reach the board"
        _ensure_device_sweep(ctx)
        dev = mc.devices[name]
        if dev.device_type == DeviceType.BAC:
            if dev.last_test is None:
                # BACs heartbeat every 5 min; right after a WatchTower restart
                # silence is expected, not proof of death. Still a fail (the
                # gate must not pass an unproven zone controller), but say why.
                wt_up = time.time() - _PROCESS_START
                if wt_up < BAC_HEARTBEAT_FRESH_S:
                    return "fail", (f"no heartbeat yet — WatchTower restarted {int(wt_up)}s ago "
                                    "and BACs report every 5 min; re-run the checklist in a few minutes")
                return "fail", "no heartbeat seen since WatchTower started"
            from datetime import datetime
            age = (datetime.now() - dev.last_test).total_seconds()
            if age <= BAC_HEARTBEAT_FRESH_S:
                return "pass", f"heartbeat {int(age)}s ago"
            return "fail", f"last heartbeat {int(age / 60)} min ago"
        if dev.status == DeviceStatus.ONLINE:
            ms = f" ({dev.response_time_ms}ms)" if dev.response_time_ms else ""
            return "pass", f"answered ping{ms}"
        return "fail", f"no ping response ({dev.status.value})"
    return fn


# ─────────────────────────────────────────────
# The checklist
# ─────────────────────────────────────────────

def build_checklist(mqtt_client) -> list:
    checks = [
        # Connections
        Check("broker_tcp", "MQTT broker answering", "Connections", "blocking",
              "The message hub every prop, the story engine, and the game talk through. "
              "Nothing in the room works without it.",
              check_broker_tcp,
              human_fix="Check the broker PC (10.1.10.115) is on and Mosquitto is running."),
        Check("wt_mqtt", "WatchTower connected to broker", "Connections", "blocking",
              "WatchTower itself must be on the broker to test the prop boards below.",
              check_wt_mqtt),
        Check("internet_voices", "Internet for AI voices (ElevenLabs)", "Connections", "blocking",
              "The characters' voices are generated in the cloud — no internet means "
              "RedBeard and Evalee go mute mid-show.",
              check_internet_voices,
              human_fix="Check the internet connection / router. Voices cannot work offline."),
        Check("a2f_endpoint", "Face animation server (COMMANDCENTER)", "Connections", "advisory",
              "Drives RedBeard's mouth movement. If down, he still talks but his face freezes.",
              check_a2f_endpoint,
              human_fix="Check COMMANDCENTER (10.1.10.228) is on and its A2F Docker container is up."),
        Check("docker", "Docker daemon", "Connections", "advisory",
              "Runs the local face-animation container. The launcher can start Docker "
              "Desktop itself, it just adds ~2 min to launch.",
              check_docker),

        # Files & Builds
        Check("game_build", "Packaged game build on disk", "Files & Builds", "blocking",
              "The actual Unreal game the players see. The launcher auto-picks the "
              "newest dated build folder.",
              check_game_build),
        Check("bats_exist", "START / STOP launcher files", "Files & Builds", "blocking",
              "The two batch files that boot and shut down the whole room.",
              check_bats_exist),
        Check("launcher_scripts", "Launch helper scripts", "Files & Builds", "blocking",
              "The launcher calls ~13 helper scripts (retained-MQTT guards, audio "
              "verify, AI launcher…). A missing one breaks launch midway.",
              check_launcher_scripts),
        Check("mythric_installed", "M3 story engine installed", "Files & Builds", "blocking",
              "Mythric Mystery Master runs the story: puzzle triggers, room audio, cues.",
              check_mythric_installed),
        Check("amt_xml", "Story file (AMT.xml) intact", "Files & Builds", "blocking",
              "The story's wiring. A device with a blanked-out topic goes DEAF — its "
              "puzzle triggers silently never fire (this exact bug killed triggers on 7/3).",
              check_amt_xml,
              human_fix="Restore AMT.xml from the newest backup in EscapeRoom Pirate Original\\logs, "
                        "then fully restart M3."),
        Check("disk_space", "Disk space on C:", "Files & Builds", "advisory",
              "Unreal, logs, and audio caches all live on C:. A full disk crashes mid-game.",
              check_disk_space),

        # Software Environment
        Check("py_paho", "Python MQTT library", "Software Environment", "blocking",
              "Every helper script talks MQTT through this library.",
              _make_module_check("paho.mqtt.client"), fix_id="pip_paho"),
        Check("py_openpyxl", "Python Excel library (openpyxl)", "Software Environment", "blocking",
              "The AI's voiceline bridge silently disables itself without it — "
              "characters' scripted lines just don't play, no error shown.",
              _make_module_check("openpyxl"), fix_id="pip_openpyxl"),
        Check("py_pyaudio", "Python audio library (pyaudio)", "Software Environment", "blocking",
              "How the AI hears the mics and plays sound to the right speakers.",
              _make_module_check("pyaudio"), fix_id="pip_pyaudio"),
        Check("clickup_token", "ClickUp task sync", "Software Environment", "advisory",
              "Lets WatchTower file issues to the task list automatically.",
              check_clickup_token),

        # Audio
        Check("out_master", "Room-wide speaker master (OUT 1-10)", "Audio", "blocking",
              "The Behringer output every room hears. If Windows can't see it, the whole "
              "room is silent.",
              check_out_master,
              human_fix="Check the Behringer UMC1820 USB cable and power, then re-run."),
        Check("default_output", "Windows default output = Behringer master", "Audio", "blocking",
              "Unreal's opening soundtrack plays to whatever Windows calls the default "
              "output until the game's first room swap. Driver updates drift it — on "
              "07-24 it landed on a dead projector endpoint at 6% volume and the "
              "opening music vanished.",
              check_default_output, fix_id="fix_default_output",
              human_fix="Windows Sound settings → set 'OUT 1-10 (BEHRINGER UMC 1820)' as the "
                        "default output device, or approve the auto-fix."),
        Check("pirate_mic", "Pirate Ship microphone present", "Audio", "blocking",
              "How RedBeard hears the players. Without it he asks a question, hears "
              "nothing, and the show stalls.",
              check_pirate_mic,
              human_fix="Plug in / reseat the TONOR 'Pirate Ship Microphone' USB mic, then re-run."),
        Check("m3_app_volume", "M3 mixer volume not turned down", "Audio", "blocking",
              "Windows remembers a per-app volume slider forever — a slider once left at "
              "15% silenced every sound effect through multiple restarts.",
              check_m3_app_volume, fix_id="fix_m3_volume"),
        Check("routing_verify", "Audio routing cross-check", "Audio", "blocking",
              "Verifies the story engine, the game, and the AI all agree on which "
              "physical speaker each sound goes to. Wrong = SFX in the wrong room.",
              check_routing_verify,
              human_fix="If a one-click 'Full M3 restart' fix is offered below, that's the whole "
                        "cure — approve it, then re-run. Otherwise: wake/power on any sleeping "
                        "projectors (missing endpoints) or fix names per ROUTING_MAP.md section 8, "
                        "THEN do a full M3 restart. NEVER run audio_channel_enforcer.py."),

        # MQTT State
        Check("retained_landmines", "No stale MQTT leftovers", "MQTT State", "advisory",
              "Old 'retained' messages replay into devices when they reconnect — a stale "
              "GameStart re-triggers the game, a stale RESET reboot-loops a board. The "
              "launcher wipes these automatically, but wiping now is safer.",
              check_retained_landmines, fix_id="clear_retained"),
        Check("boot_loops", "No boards reboot-looping", "MQTT State", "blocking",
              "A board stuck rebooting loses its puzzle state mid-game.",
              check_boot_loops, fix_id="clear_retained",
              human_fix="If clearing retained MQTT doesn't stop it, power-cycle the board."),
        Check("prop_positions", "Props in start position", "MQTT State", "blocking",
              "Doors closed, cabinet shut, puzzles not left SOLVED from the last game "
              "(compass trio scrambled, driftwood pieces off their sensors). Blocks the "
              "start until the props read right — or the operator clicks Ignore (e.g. a "
              "prop sensor is known to be lying).",
              check_prop_positions,
              human_fix="Walk the room and physically reset anything listed (scramble the "
                        "compasses, pull the driftwood pieces), then re-run — "
                        "or click Ignore to start this game anyway.",
              ignorable=True),

        # Game Systems
        Check("m3_freshness", "M3 story engine fresh (not stale)", "Game Systems", "blocking",
              "Mystery.exe's audio silently dies on long runs. Past 12 hours it must be "
              "restarted before a game.",
              check_m3_freshness, fix_id="restart_m3"),
        Check("no_game_running", "No game currently in progress", "Game Systems", "blocking",
              "Starting the launcher during a live game would kill it for the players inside.",
              check_no_game_running),
    ]

    # One checklist item per prop board — the room can't run with a dead puzzle.
    if mqtt_client:
        for name, dev in sorted(mqtt_client.devices.items(),
                                key=lambda kv: (kv[1].room, kv[0])):
            kind = "zone controller" if dev.device_type == DeviceType.BAC else "prop board"
            checks.append(Check(
                f"device_{name}", f"{dev.icon} {name}", f"Prop Boards — {dev.room}",
                "blocking",
                f"The {kind} for {name} ({dev.room}). If it doesn't answer, its puzzle "
                "is dead and the game can't be completed.",
                _make_device_check(name),
                human_fix=f"Check power/network on {name}. Try PING from the Device Registry; "
                          "power-cycle the board if it stays silent.",
            ))

    return checks
