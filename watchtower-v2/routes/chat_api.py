"""
WatchTower V2 — Tink (resident fairy, ex-Smee) chat backend
===============================================
Claude-powered assistant with tool access to everything WatchTower knows:
device registry, live MQTT feed, on-disk MQTT wire logs, Guardian game state,
checklist runs, debug log, todos, and the Grimoire device docs.

Endpoints:
    POST /api/chat          {"message": "..."}  -> {"reply": "...", "tools_used": [...]}
    POST /api/chat/reset    clears the conversation
    GET  /api/chat/history  simplified transcript for page reload
"""

import glob
import json
import logging
import os
import re
import threading
from collections import deque
from datetime import datetime

from flask import Blueprint, jsonify, request

import config
import guardian
from models import database as db
from models import grimoire_loader

logger = logging.getLogger(__name__)

chat_api = Blueprint("chat_api", __name__, url_prefix="/api")

_mqtt_client = None
_history = []            # full API-shaped conversation (single operator)
_history_lock = threading.Lock()

MAX_AGENT_TURNS = 10     # tool-use round trips per user message
MAX_HISTORY_MSGS = 40    # trim threshold; trimmed down to a clean user boundary
TOOL_RESULT_CAP = 30000  # chars per tool result fed back to the model

MQTT_LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")


def init_chat(mqtt_client):
    """Called from app.py after the MQTT client exists."""
    global _mqtt_client
    _mqtt_client = mqtt_client


# =============================================================================
# TOOLS
# =============================================================================

TOOLS = [
    {
        "name": "get_device_status",
        "description": (
            "Full device registry snapshot: every prop/controller with its online/offline "
            "status, room, MQTT topic, last response time, and error state. Call this first "
            "for any 'is X up / what's offline' question."
        ),
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "get_live_mqtt_feed",
        "description": (
            "The most recent MQTT messages WatchTower has seen since boot (in-memory ring "
            "buffer, newest first, max 200). Good for 'what just happened on the wire'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "How many messages (default 50, max 200)"}
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "search_mqtt_logs",
        "description": (
            "Search or tail the on-disk MQTT wire logs (logs/mqtt_*.txt — the source of truth "
            "for what actually fired on the broker, one line per message: [time] topic | payload). "
            "With a query: returns matching lines (case-insensitive substring). Without a query: "
            "returns the last lines of the file. file_index 0 = current session's log, 1 = previous, etc."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Substring to match (topic or payload). Omit to tail."},
                "max_matches": {"type": "integer", "description": "Max lines returned, most recent kept (default 40)"},
                "file_index": {"type": "integer", "description": "0=current log file, 1=previous session, ... (default 0)"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "get_game_state",
        "description": (
            "Current show state: Unreal/M3 process status, game-in-progress flag, recent Guardian "
            "actions, system heartbeats (ai_brain, ai_launcher, m3), and pre-game readiness signals "
            "(retained-message landmines, prop states, boot loops)."
        ),
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "get_checklist_run",
        "description": "Latest Guardian pre-game checklist run with per-item pass/warn/fail results.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "get_debug_log",
        "description": "Debug-log entries operators have filed (issues seen on props/systems), newest first.",
        "input_schema": {
            "type": "object",
            "properties": {
                "device_name": {"type": "string", "description": "Filter to one device (optional)"},
                "limit": {"type": "integer", "description": "Max entries (default 30)"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "get_todos",
        "description": "WatchTower todo items (open work on the room), newest first.",
        "input_schema": {
            "type": "object",
            "properties": {
                "device_name": {"type": "string", "description": "Filter to one device (optional)"},
                "status": {"type": "string", "description": "Filter by status, e.g. 'open' (optional)"},
                "limit": {"type": "integer", "description": "Max entries (default 30)"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "list_grimoire_devices",
        "description": "Index of devices documented in the Grimoire operations manual (name + slug).",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "get_grimoire_device_doc",
        "description": (
            "Full Grimoire documentation for one device (wiring, MQTT protocol, quirks, flash "
            "instructions). Use the slug from list_grimoire_devices."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"slug": {"type": "string", "description": "Device slug"}},
            "required": ["slug"],
            "additionalProperties": False,
        },
    },
]


_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(value):
    """Recursively strip HTML tags from string fields so docs don't waste tokens."""
    if isinstance(value, str):
        return _TAG_RE.sub("", value)
    if isinstance(value, dict):
        return {k: _strip_html(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_strip_html(v) for v in value]
    return value


def _mqtt_log_files():
    return sorted(glob.glob(os.path.join(MQTT_LOG_DIR, "mqtt_*.txt")), reverse=True)


def _tool_search_mqtt_logs(query="", max_matches=40, file_index=0):
    files = _mqtt_log_files()
    if not files:
        return {"error": f"No mqtt_*.txt logs found in {MQTT_LOG_DIR}"}
    file_index = max(0, min(int(file_index or 0), len(files) - 1))
    path = files[file_index]
    max_matches = max(1, min(int(max_matches or 40), 200))
    query = (query or "").lower()
    kept = deque(maxlen=max_matches)
    total_matches = 0
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if not query or query in line.lower():
                total_matches += 1
                kept.append(line.rstrip("\n"))
    return {
        "file": os.path.basename(path),
        "available_log_files": len(files),
        "total_matching_lines": total_matches,
        "showing_most_recent": len(kept),
        "lines": list(kept),
    }


def _execute_tool(name, tool_input):
    """Run one tool and return its result as a JSON string (never raises)."""
    try:
        if name == "get_device_status":
            result = _mqtt_client.get_status_summary() if _mqtt_client else {"error": "MQTT client not connected"}
        elif name == "get_live_mqtt_feed":
            limit = max(1, min(int(tool_input.get("limit") or 50), 200))
            result = _mqtt_client.get_feed(limit) if _mqtt_client else {"error": "MQTT client not connected"}
        elif name == "search_mqtt_logs":
            result = _tool_search_mqtt_logs(
                tool_input.get("query", ""),
                tool_input.get("max_matches", 40),
                tool_input.get("file_index", 0),
            )
        elif name == "get_game_state":
            result = {
                "game": guardian.game_state(),
                "system_signals": _mqtt_client.get_system_signals() if _mqtt_client else {},
                "pregame_signals": _mqtt_client.get_pregame_signals() if _mqtt_client else {},
            }
        elif name == "get_checklist_run":
            run = guardian.latest_run()
            result = run if run is not None else {"info": "No checklist run recorded since WatchTower started"}
        elif name == "get_debug_log":
            result = db.get_debug_entries(
                device_name=tool_input.get("device_name"),
                limit=max(1, min(int(tool_input.get("limit") or 30), 100)),
            )
        elif name == "get_todos":
            result = db.get_todos(
                device_name=tool_input.get("device_name"),
                status=tool_input.get("status"),
                limit=max(1, min(int(tool_input.get("limit") or 30), 100)),
            )
        elif name == "list_grimoire_devices":
            result = grimoire_loader.get_device_index()
        elif name == "get_grimoire_device_doc":
            doc = grimoire_loader.get_device_section(tool_input.get("slug", ""))
            result = _strip_html(doc) if doc is not None else {"error": "Unknown slug — call list_grimoire_devices"}
        else:
            result = {"error": f"Unknown tool: {name}"}
    except Exception as e:  # noqa: BLE001 - tool errors go back to the model, never crash the request
        logger.exception(f"Tink tool {name} failed")
        result = {"error": f"{type(e).__name__}: {e}"}

    text = json.dumps(result, default=str, ensure_ascii=False)
    if len(text) > TOOL_RESULT_CAP:
        text = text[:TOOL_RESULT_CAP] + '... [truncated — narrow the query for more]"'
    return text


# =============================================================================
# CLAUDE
# =============================================================================

def _system_prompt():
    return f"""You are Tink — short for Tinkerbell — the resident fairy of WatchTower, the operations \
dashboard for "A Mermaid's Tale", a pirate/mermaid escape room by Alchemy Escape Rooms. \
Today's date is {datetime.now().strftime('%Y-%m-%d')}.

Personality: classic Tinkerbell. Quick, clever, a little sassy, fiercely loyal to the operator. \
You have opinions and you share them; you get a touch impatient with misbehaving props ("oh, NOW \
the cove door wants to talk"). A light sprinkle of fairy flavor is welcome — sparkle, pixie dust, \
fluttering off to check a log — but never let the whimsy bury the answer. Lead with the answer, \
keep it concise, and spell out technical findings in plain sentences. Under the sass you are \
rigorous: data first, sources named, no hand-waving.

The room, in one breath: ESP32-based physical props (BarrelPiston, BalancingScale, MiniBarrels, \
TridentCabinet, CaptainsCuffs, CoveDoor, SunDial, RuinsWall, Cannons...) talk over MQTT \
(broker {config.MQTT_BROKER}). "M3" = Mythric Mystery Master (Mystery.exe), the story/game-runner \
app. An Unreal Engine program drives the ship screens (RedBeard, Evalee, the mermaid finale). \
An AI Character system does guest-facing voice via ElevenLabs + Audio2Face. WatchTower (this app) \
watches all of it. Props typically use topics like <Prop>/command, <Prop>/status, <Prop>/log. \
Retained MQTT messages on /command topics are a known hazard (reboot loops, command echo storms).

Ground rules:
- ALWAYS check the live data with your tools before theorizing. The on-disk MQTT wire logs \
(search_mqtt_logs) are the source of truth for what actually fired on the broker.
- When diagnosing a prop, pull its Grimoire doc and its debug-log history — most props have \
documented quirks.
- Report what the data shows, plainly. If a log contradicts a theory, say so.
- You are read-only: you can look at everything but you cannot publish MQTT messages, restart \
apps, or change files. If a fix needs action, tell the operator exactly what to do."""


class ChatUnavailable(Exception):
    """Raised when the Claude call cannot be made or completed."""


_use_server_fallbacks = True  # flipped off if the API/SDK rejects the fallbacks param


def _call_claude(client, messages):
    """One model call. Prefers server-side refusal fallback to Opus 4.8; degrades gracefully."""
    global _use_server_fallbacks
    import anthropic

    system = [{"type": "text", "text": _system_prompt(), "cache_control": {"type": "ephemeral"}}]
    kwargs = dict(
        model=config.TINK_MODEL,
        max_tokens=8000,
        system=system,
        tools=TOOLS,
        messages=messages,
    )
    if _use_server_fallbacks:
        try:
            return client.beta.messages.create(
                betas=["server-side-fallback-2026-06-01"],
                extra_body={"fallbacks": [{"model": config.TINK_FALLBACK_MODEL}]},
                **kwargs,
            )
        except anthropic.BadRequestError as e:
            if "fallback" in str(e).lower():
                logger.warning("Server-side fallbacks rejected; continuing without them")
                _use_server_fallbacks = False
            else:
                raise
    return client.messages.create(**kwargs)


def _run_agent_loop(messages):
    """Manual tool-use loop. Mutates `messages` in place; returns (final_text, tools_used)."""
    import anthropic

    if not config.ANTHROPIC_API_KEY:
        raise ChatUnavailable(
            "No Anthropic API key configured. Set the ANTHROPIC_API_KEY environment variable, "
            "or paste your key into watchtower-v2\\anthropic_key.txt, then restart WatchTower."
        )

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    tools_used = []
    response = None

    for _ in range(MAX_AGENT_TURNS):
        try:
            response = _call_claude(client, messages)
        except anthropic.AuthenticationError:
            raise ChatUnavailable("Anthropic API key was rejected — check the key and restart WatchTower.")
        except anthropic.RateLimitError:
            raise ChatUnavailable("Rate limited by the Anthropic API — wait a minute and try again.")
        except anthropic.APIConnectionError:
            raise ChatUnavailable("Couldn't reach the Anthropic API — check the internet connection.")
        except anthropic.APIStatusError as e:
            raise ChatUnavailable(f"Anthropic API error ({e.status_code}): {e.message}")

        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "refusal":
            return (
                "Sorry — the model declined that one (safety classifier). "
                "Try rephrasing the question.",
                tools_used,
            )
        if response.stop_reason == "pause_turn":
            continue
        if response.stop_reason != "tool_use":
            break

        results = []
        for block in response.content:
            if block.type == "tool_use":
                tools_used.append(block.name)
                results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": _execute_tool(block.name, block.input),
                })
        messages.append({"role": "user", "content": results})
    else:
        return ("I hit my tool-call limit on that one — ask again with a narrower question.", tools_used)

    final_text = "\n\n".join(
        b.text for b in response.content if getattr(b, "type", None) == "text" and b.text
    )
    return (final_text or "(no reply)", tools_used)


def _trim_history():
    """Drop oldest turns down to a clean user-text boundary so tool pairs stay intact."""
    if len(_history) <= MAX_HISTORY_MSGS:
        return
    keep_from = None
    # scan from ~1/3 in for the first plain user message (a real operator turn)
    for i in range(len(_history) - MAX_HISTORY_MSGS // 2, len(_history)):
        m = _history[i]
        if m.get("role") == "user" and isinstance(m.get("content"), str):
            keep_from = i
            break
    if keep_from:
        del _history[:keep_from]


# =============================================================================
# ROUTES
# =============================================================================

@chat_api.route("/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()
    if not message:
        return jsonify({"error": "Empty message"}), 400

    with _history_lock:
        _trim_history()
        _history.append({"role": "user", "content": message})
        try:
            reply, tools_used = _run_agent_loop(_history)
        except ChatUnavailable as e:
            _history.pop()  # keep history consistent: the turn never happened
            return jsonify({"error": str(e)})
        except Exception as e:  # noqa: BLE001 - surface anything unexpected to the UI
            logger.exception("Tink chat turn failed")
            _history.pop()
            return jsonify({"error": f"Unexpected error: {type(e).__name__}: {e}"})

    return jsonify({"reply": reply, "tools_used": tools_used})


@chat_api.route("/chat/reset", methods=["POST"])
def chat_reset():
    with _history_lock:
        _history.clear()
    return jsonify({"ok": True})


@chat_api.route("/chat/history", methods=["GET"])
def chat_history():
    """Simplified transcript (user text + assistant text only) for page reload."""
    out = []
    with _history_lock:
        for m in _history:
            if m["role"] == "user" and isinstance(m["content"], str):
                out.append({"role": "user", "text": m["content"]})
            elif m["role"] == "assistant":
                text = "\n\n".join(
                    b.text for b in m["content"] if getattr(b, "type", None) == "text" and b.text
                )
                if text:
                    out.append({"role": "assistant", "text": text})
    return jsonify({"history": out, "has_key": bool(config.ANTHROPIC_API_KEY)})
